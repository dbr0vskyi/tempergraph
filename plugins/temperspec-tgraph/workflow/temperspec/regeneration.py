"""The regeneration unit (spec regeneration, RGN-B1 to RGN-B16): after the code step, a script unit with no session
runs the commands a repository declares in `tempergraph.regenerations.json` for its generated files, when a file they
read changed in the run, and commits what they wrote. `regenerate` is the unit's call, `regeneration_check` its
gate's check: the call records what each command did in `.tempergraph/regeneration/report.json` (never committed), and
the check turns the record into a verdict and findings (spec regeneration-failures). Neither writes a document or
starts a session."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph.api import CheckFinding, CheckResult

from . import review
from .routing import _git, commit_step

DECLARATION = "tempergraph.regenerations.json"
STATE = Path(".tempergraph") / "regeneration"
REPORT = STATE / "report.json"
TIMEOUT_S = 600.0  # RGF-B8: a command that has not finished by then is ended
TAIL_LINES = 40


class DeclarationError(Exception):
    """The declaration exists and cannot be used (RGN-B4); the message says what is wrong with it."""


@dataclass(frozen=True)
class Regeneration:
    name: str
    command: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]


def _paths(entry: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    got = entry.get(key)
    if not isinstance(got, list) or not all(isinstance(p, str) for p in got):
        raise DeclarationError(f"{DECLARATION}: {where} lacks `{key}` as a list of paths")
    return tuple(p.strip().strip("/").removeprefix("./") for p in got)


def load_declaration(workdir: Path) -> list[Regeneration]:
    """RGN-B3, RGN-B4: the regenerations of the repository, in file order; none when the file is absent."""
    path = Path(workdir) / DECLARATION
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DeclarationError(f"{DECLARATION} is not valid JSON ({type(exc).__name__})") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise DeclarationError(f"{DECLARATION} has a `schema_version` other than 1")
    listed = doc.get("regenerations", [])
    if not isinstance(listed, list):
        raise DeclarationError(f"{DECLARATION}: `regenerations` is not a list")
    out: list[Regeneration] = []
    for i, entry in enumerate(listed, start=1):
        where = f"regeneration {i}"
        if not isinstance(entry, dict):
            raise DeclarationError(f"{DECLARATION}: {where} is not an object")
        for key in ("name", "command"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise DeclarationError(f"{DECLARATION}: {where} lacks a `{key}`")
        out.append(Regeneration(name=entry["name"].strip(), command=" ".join(entry["command"].split()),
                                inputs=_paths(entry, "inputs", where), outputs=_paths(entry, "outputs", where)))
    return out


def declared_outputs(workdir: Path) -> list[str]:
    """Every path the repository declares as an output; none when there is no usable declaration."""
    try:
        return [o for r in load_declaration(workdir) for o in r.outputs]
    except DeclarationError:
        return []


def _under(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder + "/")


def due(regenerations: list[Regeneration], changed: list[str]) -> list[Regeneration]:
    """RGN-B6, RGN-B7: the regenerations one of whose inputs is a changed path or a folder that holds one; a change to
    one of the regeneration's own outputs never counts."""
    out: list[Regeneration] = []
    for r in regenerations:
        seen = [p for p in changed if not any(_under(p, o) for o in r.outputs)]
        if any(_under(p, i) for p in seen for i in r.inputs):
            out.append(r)
    return out


def _task(ctx: Any) -> str:
    return str((ctx.request or {}).get("task_id") or "task")


def changed_paths(workdir: Path, task: str) -> list[str]:
    """The paths the run changed since its base commit, committed or not."""
    base, _ = review.run_base(workdir, task)
    if not base:
        return []
    names = _git(workdir, "diff", "--name-only", base, "HEAD").stdout.splitlines()
    status = _git(workdir, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    names += [line[3:].split(" -> ")[-1].strip('"') for line in status if len(line) > 3]
    return sorted({n for n in names if n and not n.startswith(".tempergraph/")})


def _dirty(workdir: Path) -> set[str]:
    lines = _git(workdir, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    return {line[3:].split(" -> ")[-1].strip('"') for line in lines if len(line) > 3}


def _restore(workdir: Path, before: set[str]) -> None:
    """RGN-B12: put back every path the pass changed and remove every file it created."""
    for path in sorted(_dirty(workdir) - before):
        if path.startswith(".tempergraph/"):
            continue
        tracked = _git(workdir, "ls-files", "--error-unmatch", "--", path).returncode == 0
        if tracked:
            _git(workdir, "checkout", "HEAD", "--", path)
        else:
            target = Path(workdir) / path
            if target.is_file() or target.is_symlink():
                target.unlink(missing_ok=True)


def _run_one(ctx: Any, r: Regeneration) -> dict[str, Any]:
    """Start one command through the engine's command runner, which the context gives (SEC-B5): its words as a list,
    no shell, refused for a shell metacharacter, an absolute path or a parent path. The command is its own allow-list,
    so nothing but the declaration names a command (RGN-B16)."""
    row: dict[str, Any] = {"name": r.name, "command": r.command, "state": "passed", "exit_code": None, "tail": ""}
    ctx.allow = (r.command,)
    ctx.out_dir = Path(ctx.workdir) / STATE
    ctx.deadline_at = time.monotonic() + TIMEOUT_S
    done = ctx.run(r.command, timeout_s=TIMEOUT_S)
    refused = (done.extra or {}).get("refused")
    if refused:
        return {**row, "state": "refused", "tail": str(refused)}
    row.update(exit_code=done.exit_code, tail=done.tail)
    if done.timed_out:
        row["state"] = "timeout"
    elif done.not_started or done.exit_code is None:
        row["state"] = "not_started"
    elif done.exit_code < 0:
        row["state"] = "signal"
    elif done.exit_code != 0:
        row["state"] = "failed"
    return row


ENVIRONMENT = {"refused", "not_started", "signal", "timeout"}


def regenerate(ctx: Any) -> dict[str, str]:
    """The call of the unit (RGN-B6 to RGN-B12): run every due command in declaration order, put the workspace back
    when anything failed and otherwise commit what the commands wrote. A refused command or one that cannot run
    ends the pass at once; a plain failure lets the later regenerations run (RGF-B2)."""
    workdir = Path(ctx.workdir)
    (workdir / STATE).mkdir(parents=True, exist_ok=True)
    (workdir / STATE / ".gitignore").write_text("*\n", encoding="utf-8")
    report: dict[str, Any] = {"declaration_error": "", "runs": []}
    try:
        regenerations = load_declaration(workdir)
    except DeclarationError as exc:
        report["declaration_error"] = str(exc)
        regenerations = []
    todo = due(regenerations, changed_paths(workdir, _task(ctx))) if regenerations else []
    before = _dirty(workdir)
    for r in todo:
        row = _run_one(ctx, r)
        report["runs"].append(row)
        if row["state"] in ENVIRONMENT:
            break
    if any(row["state"] != "passed" for row in report["runs"]):
        _restore(workdir, before)
    elif report["runs"]:
        commit_step(ctx)
    (workdir / REPORT).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {"regeneration_report": REPORT.as_posix()}


def _finding(row: dict[str, Any]) -> CheckFinding:
    """RGF-B4: one finding for a failed command, holding the command, its exit code and the last lines of its output."""
    tail = "\n".join(str(row.get("tail") or "").splitlines()[-TAIL_LINES:])
    return CheckFinding(status="fail", criterion=str(row["command"]), place=str(row["command"]),
                        message=f"exit code {row.get('exit_code')}\n{tail}".rstrip())


def findings_of(row: dict[str, Any]) -> list[CheckFinding]:
    """The findings of one failed command, in the order it reported them."""
    return [_finding(row)]


def regeneration_check(ctx: Any) -> CheckResult:
    """The gate's check (RGF-B1, RGF-B8): PASS when nothing failed; a FAIL marked environmental for an unusable
    declaration or a command that was refused, did not start, was ended by a signal or timed out; otherwise a FAIL
    with the findings of each failed command, in the order the regenerations ran."""
    try:
        report = json.loads((Path(ctx.workdir) / REPORT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return CheckResult(result="FAIL", environmental=True, evidence=f"no regeneration report at {REPORT.as_posix()}")
    if report.get("declaration_error"):
        return CheckResult(result="FAIL", environmental=True, evidence=str(report["declaration_error"]))
    runs = [r for r in report.get("runs", []) if isinstance(r, dict)]
    broken = [r for r in runs if r.get("state") in ENVIRONMENT]
    if broken:
        text = "; ".join(f"`{r['command']}` {str(r['state']).replace('_', ' ')}"
                         + (f" ({r['tail']})" if r.get("tail") else "") for r in broken)
        return CheckResult(result="FAIL", environmental=True, evidence=f"a regeneration could not run: {text}")
    failed = [r for r in runs if r.get("state") == "failed"]
    if failed:
        found = [f for r in failed for f in findings_of(r)]
        return CheckResult(result="FAIL", evidence=f"{len(failed)} regeneration(s) failed", findings=found)
    return CheckResult(result="PASS", evidence=f"{len(runs)} regeneration(s) passed" if runs else "nothing due")
