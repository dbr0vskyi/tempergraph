"""The generated tests of a scaffolded package (SCF §2.4), as engine functions: the package's own
`tests/test_<module>_generated.py` calls them, and `author verify` rung 4 calls them in process, so both
give the same answer. Each returns the problems found; an empty list passes. Model-free."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec


def _spec(root: Path) -> WorkflowSpec:
    from tempergraph.package.loader import load_package

    return load_package(root).spec


def diagram_current(root: Path, tmp: Path) -> list[str]:
    from tempergraph.model.diagram import diagram_model

    try:
        have = json.loads((root / "diagram" / "model.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["diagram/model.json is missing; run `tempergraph scaffold <session> --out <dir> --update` or "
                "`tempergraph upgrade-check <workflow> --stamp`"]
    if not (root / "diagram" / "workflow.md").is_file():
        return ["diagram/workflow.md is missing; regenerate it with `tempergraph upgrade-check <workflow> --stamp`"]
    want = diagram_model(_spec(root))["digest"]
    return [] if have.get("digest") == want else [
        "diagram/model.json does not match the spec (digest); regenerate it with "
        "`tempergraph upgrade-check <workflow> --stamp`"]


def summaries(root: Path, tmp: Path) -> list[str]:
    out = []
    spec = _spec(root)
    for name in spec.order:
        u = spec.units[name]
        text = (u.step.summary if u.step else u.script.summary if u.script else "x") or ""
        if u.kind in ("step", "script") and not (0 < len(text) <= 60):
            out.append(f"{name}: a summary of 1 to 60 characters is required (has {len(text)})")
    return out


def examples_resolve(root: Path, tmp: Path) -> list[str]:
    spec = _spec(root)
    decl = spec.input
    out = []
    for ex in decl.examples:
        if not str(ex).strip():
            out.append("an empty start example")
        elif decl.kind == "resolver" and decl.resolver is not None:
            got = decl.resolver.resolve()(str(ex))
            if getattr(got, "status", "error") == "error":
                out.append(f"start example {ex!r} does not resolve: {getattr(got, 'message', '')}")
    return out


def _fixture_dirs(root: Path, unit: str) -> dict[str, list[Path]]:
    base = root / "evals" / "checks" / unit
    return {w: sorted(p for p in (base / w).glob("*") if p.is_file()) for w in ("must-pass", "must-fail")}


def check_fixtures(root: Path, tmp: Path) -> list[str]:
    """Every check passes its must-pass and fails its must-fail fixtures, naming a criterion id; each fixture
    also with CRLF line endings (EVS §2.2)."""
    from tempergraph.run.checks import CheckContext, run_check

    spec = _spec(root)
    out = []
    for name in spec.order:
        u = spec.units[name]
        if u.gate.check is None:
            continue
        dirs = _fixture_dirs(root, name)
        ids = {c.id for c in u.gate.criteria if c.mechanical or c.verified_by == "check"}
        if not dirs["must-pass"] or not dirs["must-fail"]:
            out.append(f"{name}: the check needs a must-pass and a must-fail fixture under evals/checks/{name}/")
            continue
        for which, paths in dirs.items():
            for p in paths:
                for crlf in (False, True):
                    work = tmp / f"{name}-{which}-{p.name}-{int(crlf)}"
                    work.mkdir(parents=True, exist_ok=True)
                    data = p.read_bytes()
                    if crlf:
                        data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                    (work / p.name).write_bytes(data)
                    arts = {k: p.name for k in (u.step.produces if u.step else {}) if p.stem == k} or {
                        k: p.name for k in (u.step.produces if u.step else {})}
                    ctx = CheckContext(unit=name, workdir=work, request={}, artifacts={name: arts},
                                       allow=spec.allow_commands, out_dir=work / ".out")
                    res, _ = run_check(u.gate, ctx)
                    named = {f.criterion for f in res.findings} & ids
                    tag = f"{name} {which}/{p.name}{' (CRLF)' if crlf else ''}"
                    if which == "must-pass" and res.result != "PASS":
                        out.append(f"{tag}: expected PASS, got {res.result} ({res.evidence[:120]})")
                    if which == "must-fail" and res.result != "FAIL":
                        out.append(f"{tag}: expected FAIL, got {res.result}")
                    if not named:
                        out.append(f"{tag}: the check names none of its criteria {sorted(i for i in ids if i)}")
    return out


def standin_run(root: Path, tmp: Path) -> list[str]:
    """A scripted executor stands in for each step and judge and for the outcome judge; the run reaches the
    finalizer (SCF §2.4). The step stand-in writes the unit's must-pass fixtures as its files."""
    from tempergraph import git
    from tempergraph.constants import ExitCode
    from tempergraph.executors.scripted import answer, scripted_registry
    from tempergraph.run.runner import RunSettings, start

    spec = _spec(root)
    repo = tmp / "standin-repo"
    repo.mkdir(parents=True, exist_ok=True)
    git.git(["init", "-q", "-b", "main"], repo)
    git.git(["-c", "user.email=standin@example.invalid", "-c", "user.name=standin", "commit", "-q",
             "--allow-empty", "-m", "start"], repo)
    executors = {(st.executor if (st := spec.units[n].step) is not None else None) or spec.default_executor
                 for n in spec.order}
    if executors - {"claude"}:
        return [f"stand-in run: executors {sorted(executors - {'claude'})} are not in release 1"]

    def step_reply(unit: str) -> Callable[[Any], Any]:
        def reply(req: Any) -> Any:
            u = spec.units[unit]
            lines = []
            fixtures = {p.stem: p for p in _fixture_dirs(root, unit)["must-pass"]}
            for key, kind in (u.step.produces if u.step else {}).items():
                if kind == "file":
                    src = fixtures.get(key) or next(iter(fixtures.values()), None)
                    name = src.name if src else f"{key}.md"
                    target = Path(req.workdir) / name
                    if src is not None:
                        shutil.copyfile(src, target)
                    else:
                        target.write_text(f"# {key}\n\nStand-in output.\n", encoding="utf-8")
                    lines.append(f"ARTIFACT {key}: {name}")
                else:
                    lines.append(f"ARTIFACT {key}: stand-in")
            return answer("Stand-in.\n" + "\n".join(lines), session_id=f"s-{unit}")
        return reply

    def verdict(n: int, sid: str) -> Any:
        rows = [{"n": i, "status": "MET", "evidence": "stand-in", "defect_in": None, "no_change": False}
                for i in range(1, n + 1)]
        return answer("Stand-in.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.9})
                      + "\n```", tools=("Read",), session_id=sid)

    steps, judges = [], []
    for name in spec.order:
        u = spec.units[name]
        if u.kind == "step":
            steps.append(step_reply(name))
        if u.gate.judge is not None:
            judges.append(verdict(len(u.gate.criteria), f"j-{name}"))  # the judge rows every criterion
    if spec.outcome is not None and any(c.verified_by == "judge" for c in spec.outcome.final):
        judges.append(verdict(sum(1 for c in spec.outcome.final if c.verified_by == "judge"), "j-outcome"))
    r = scripted_registry("claude", steps, judges)
    try:
        got = start(spec, "STANDIN-1", {"request": "stand-in"}, repo, r, RunSettings(sleep=lambda s: None))
    except AssertionError as exc:  # a stand-in queue ran dry: the run asked for more sessions than scripted
        return [f"stand-in run: {exc}"]
    if got.exit_code is not ExitCode.FINISHED:
        return [f"stand-in run ended {got.exit_code.name}: {got.reason} {got.message}".strip()]
    return []


def compatibility(root: Path, tmp: Path) -> list[str]:
    from tempergraph.executors.capabilities import DECLARED
    from tempergraph.model.validate import validate
    from tempergraph.package.changelog import compatibility as compat
    from tempergraph.package.loader import PackageNotLoaded, load_package
    from tempergraph.package.stamp import read_stamp

    try:
        lp = load_package(root)
    except PackageNotLoaded as exc:
        return [str(exc)]
    errors = [f"{f.code}: {f.message}" for f in validate(lp.spec, {"claude": DECLARED["claude"]})
              if f.severity == "error"]
    state = compat(lp.spec, root, read_stamp(root), finding_codes=set())["state"]
    if state not in ("current", "unstamped", "compatible"):
        errors.append(f"compatibility state {state}")
    return errors


def docs(root: Path, tmp: Path) -> list[str]:
    from tempergraph.package.docs_check import docs_check

    return [f.message for f in docs_check(_spec(root), root, "stable")]


CHECKS: dict[str, Callable[[Path, Path], list[str]]] = {
    "diagram_current": diagram_current, "summaries": summaries, "examples_resolve": examples_resolve,
    "check_fixtures": check_fixtures, "standin_run": standin_run, "compatibility": compatibility, "docs": docs,
}
NAMES = tuple(CHECKS)


def run(name: str, root: Path, tmp: Path) -> list[str]:
    try:
        return CHECKS[name](root, tmp)
    except Exception as exc:  # noqa: BLE001 - a broken package is a problem, not a crash
        return [f"{name}: {type(exc).__name__}: {exc}"]
