"""The check context and running a gate's check (CHK §2.1, §2.4; contract C5).

`run_check` is the call itself; the engine makes it inside the check worker (`run.check_worker`, CHK §2.6),
and the deadline is also enforced on every command the check runs.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph import git as gitmod
from tempergraph.contracts import CheckFinding, CheckResult, GateSpec
from tempergraph.run.commands import CommandRefusal, CommandRun, ResolvedCommand, resolve_command, run_command
from tempergraph.security.scrub import clip, scrub

ORDER = {"PASS": 0, "MAYBE": 1, "FAIL": 2}
FINDING_TO_RESULT = {"pass": "PASS", "n_a": "PASS", "maybe": "MAYBE", "fail": "FAIL"}
FACT_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
MAX_FACTS = 20


@dataclass(frozen=True, kw_only=True)
class GitFacts:
    branch: str = ""
    base: str = ""
    head: str = ""
    base_head: str = ""
    clean: bool = True
    pushed: bool = False
    changed_paths: tuple[str, ...] = ()
    commits_since_base: tuple[str, ...] = ()


def git_facts(workdir: Path, base: str = "") -> GitFacts | None:
    """The workspace's git facts; None outside a git repository (WSP §2.4)."""
    if gitmod.toplevel(workdir) is None:
        return None
    fp = gitmod.fingerprint(workdir)
    name = gitmod.branch(workdir)
    return GitFacts(branch=name, base=base, head=fp.head, clean=not fp.status, pushed=gitmod.pushed(workdir, name),
                    changed_paths=tuple(gitmod.changed_paths(workdir, base or None)))


def changed_paths(workdir: Path, facts: GitFacts | None, baseline: Path | None) -> tuple[str, ...]:
    """What changed in the workspace: git's answer, or outside git the manifest against the thread's first one."""
    if facts is not None:
        return tuple(facts.changed_paths)
    import json

    from tempergraph.store import manifest

    try:
        files = json.loads(baseline.read_text(encoding="utf-8")).get("files") if baseline is not None else None
    except (OSError, ValueError, AttributeError):
        files = None
    return tuple(manifest.changed(workdir, files)) if isinstance(files, dict) else ()


@dataclass(kw_only=True)
class CheckContext:
    unit: str
    workdir: Path
    request: Mapping[str, Any]
    item: str | None = None
    visit: int = 1
    attempt: int = 1
    preview: bool = False
    main_checkout: Path | None = None
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    values: Mapping[str, Any] = field(default_factory=dict)
    facts: Mapping[str, Any] = field(default_factory=dict)
    git: GitFacts | None = field(default_factory=GitFacts)  # None outside git (WSP §2.4)
    changed_paths: tuple[str, ...] = ()  # git's outside the state root, or the manifest's outside git
    settings: Mapping[str, Any] = field(default_factory=dict)
    criteria: tuple[dict[str, Any], ...] = ()
    allow: tuple[str, ...] = ()
    out_dir: Path | None = None
    deadline_at: float = 0.0
    runs: list[CommandRun] = field(default_factory=list)
    reuse_store: Path | None = None  # the thread's stored command runs (CHK §2.3 Reuse)
    no_reuse_exit_codes: Mapping[str, tuple[int, ...]] = field(default_factory=dict)  # per allow-list prefix

    @property
    def deadline_s(self) -> float:
        return max(0.0, self.deadline_at - time.monotonic())

    def read_text(self, path: str | Path, max_bytes: int = 1_000_000) -> str:
        p = (self.workdir / path).resolve()
        if not p.is_relative_to(self.workdir.resolve()):
            raise PermissionError(f"{path} is outside the workspace")
        with open(p, "rb") as fh:
            return fh.read(max_bytes).decode("utf-8", errors="replace")

    def resolve(self, text: str) -> ResolvedCommand | CommandRefusal:
        return resolve_command(self.allow, text, self.workdir)

    def run(self, cmd: ResolvedCommand | str, timeout_s: float | None = None, reuse: bool = False,
            min_start_s: float = 0) -> CommandRun:
        if isinstance(cmd, str):
            got = self.resolve(cmd)
            if isinstance(got, CommandRefusal):
                return CommandRun(argv=(clip(scrub(cmd), 200),), not_started=True, extra={"refused": got.reason})
            cmd = got
        left = self.deadline_s
        if left < min_start_s or left <= 0:
            r = CommandRun(argv=cmd.argv, not_started=True)
            self.runs.append(r)
            return r
        key = reuse_key(cmd, self.workdir) if reuse and self.reuse_store is not None else None
        if key is not None:
            hit = _stored(self.reuse_store, key)
            if hit is not None:
                self.runs.append(hit)
                return hit
        out_dir = self.out_dir or (self.workdir / ".tempergraph-check")
        limit = min(timeout_s, left) if timeout_s else left
        r = run_command(cmd, self.workdir, out_dir / f"{len(self.runs) + 1}.out", limit, main=self.main_checkout)
        self.runs.append(r)
        if key is not None and r.finished and r.exit_code not in self.no_reuse_exit_codes.get(cmd.prefix, ()):
            _store(self.reuse_store, key, r)
        return r


def reuse_key(cmd: ResolvedCommand, workdir: Path) -> str:
    """CHK §2.3: argv, resolved program, `head`, the status listing and the content of changed files."""
    raw = gitmod.git(["status", "--porcelain=v1", "-uall", "-z"], workdir, check=False)
    entries = [e for e in raw.split("\0") if e[3:] and not e[3:].startswith(".tempergraph")]  # not the state root
    h = hashlib.sha256()
    prog = shutil.which(cmd.argv[0]) if cmd.argv else None
    head = gitmod.git(["rev-parse", "HEAD"], workdir, check=False).strip()
    h.update(json.dumps([list(cmd.argv), cmd.cwd, prog, head, entries]).encode())
    for entry in entries:
        path = entry[3:]
        f = workdir / path
        h.update(path.encode() + b"\0")
        if f.is_file():
            h.update(hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def _stored(store: Path | None, key: str) -> CommandRun | None:
    if store is None:
        return None
    try:
        lines = store.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for ln in reversed(lines):
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if row.get("key") == key:
            r = row["run"]
            return CommandRun(argv=tuple(r.get("argv") or ()), program_path=str(r.get("program_path") or ""),
                              exit_code=r.get("exit_code"), finished=True, reused=True,
                              duration_s=float(r.get("duration_s") or 0), output_path=str(r.get("output_path") or ""),
                              tail=str(r.get("tail") or ""))
    return None


def _store(store: Path | None, key: str, run: CommandRun) -> None:
    if store is None:
        return
    try:
        store.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(store, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "run": run.to_json()}) + "\n")
    except OSError:
        pass  # a lost store entry only costs a rerun of the command


def normalise(res: CheckResult) -> tuple[CheckResult, list[str]]:
    """CHK §2.4: the worse of `result` and the worst finding; bounded, scrubbed facts."""
    notes: list[str] = []
    worst = res.result
    for f in res.findings:
        r = FINDING_TO_RESULT.get(f.status, "MAYBE")
        if ORDER[r] > ORDER[worst]:
            worst = r  # type: ignore[assignment]
    if worst != res.result:
        notes.append(f"check_result_mismatch: {res.result} -> {worst}")
    facts = {}
    for k, v in list(res.facts.items())[:MAX_FACTS]:
        if FACT_KEY.match(str(k)):
            facts[str(k)] = clip(scrub(str(v)), 200)
        else:
            notes.append(f"fact_key_invalid: {clip(str(k), 40)}")
    findings = [CheckFinding(status=f.status, criterion=f.criterion, place=clip(scrub(f.place), 200),
                             fix=clip(scrub(f.fix), 200), message=clip(scrub(f.message), 200), kind=f.kind)
                for f in res.findings]
    out = CheckResult(result=worst, evidence=scrub(res.evidence)[:8000], environmental=res.environmental,
                      untracked_only=res.untracked_only, findings=findings, facts=facts, runs=list(res.runs))
    return out, notes


def run_check(gate: GateSpec, ctx: CheckContext) -> tuple[CheckResult, list[str]]:
    """Call the gate's check; a raising check is an environmental FAIL, never a pass."""
    if gate.check is None:
        return CheckResult(result="PASS", evidence=""), []
    ctx.deadline_at = time.monotonic() + gate.check_timeout_s
    fn = gate.check.resolve()
    try:
        res = fn(ctx)
    except Exception as exc:  # noqa: BLE001 - a check's own failure is a result
        # CHK §4: a raising check is a workflow fault, not an environmental one; a retry is spent
        return CheckResult(result="FAIL", evidence=f"check raised {type(exc).__name__}"), [
            f"check_raised: {type(exc).__name__}"]
    if not isinstance(res, CheckResult):
        return CheckResult(result="FAIL", evidence="check returned no CheckResult"), ["check_result_invalid"]
    res.runs = [r.to_json() for r in ctx.runs]
    return normalise(res)


def to_json(res: CheckResult) -> dict[str, Any]:
    return {"result": res.result, "evidence": res.evidence, "environmental": res.environmental,
            "untracked_only": res.untracked_only,
            "findings": [{"status": f.status, "criterion": f.criterion, "place": f.place, "fix": f.fix,
                          "message": f.message, "kind": f.kind} for f in res.findings],
            "facts": res.facts, "runs": res.runs}
