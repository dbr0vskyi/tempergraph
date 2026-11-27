"""Task i197a: the outcome check marks a fact no step can change as environmental, so the gate pauses instead of
sending the run back (OGT-B13 to OGT-B17, SBS-B1, SBS-B4). The file builds its own scratch repository."""

from __future__ import annotations

import dataclasses
import importlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, git_facts
from tempergraph.run.commands import CommandRun

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
DONE = ROOT / "evals" / "checks" / "code" / "must-pass" / "1-done"
OWNER = {key: unit for unit in SPEC.order for key in (SPEC.units[unit].step.produces if SPEC.units[unit].step else {})}
SPEC_PATH = "docs/specs/pause.spec.md"
ABSENT = "git show HEAD:absent.txt"  # exits 128 at the gate and at the base alike
GONE = "git show HEAD:gone.txt"  # exits 0 at the base, 128 at the gate
PYTEST = "pytest tests/test_config.py"
FIX = "bring the head of the base branch into the run's branch, then answer retry"
SPEC_V1 = ("# Pause\n\n## Purpose\n\nA scratch spec.\n\n## Behaviours\n\n### PSE-B1 A thing\n\n"
           "WHEN a thing happens THE service SHALL answer.\n\n- GIVEN a state WHEN an event THEN a result\n\n"
           "## Acceptance criteria\n\n- PSE-AC1 (PSE-B1): A request is answered\n")
SPEC_RUN = SPEC_V1.replace("A request is answered", "A request is answered with a body")
SPEC_MAIN = SPEC_V1.replace("A request is answered", "A request is answered at once")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def _repo(root: Path, command: str, *, moved: bool, traced: bool = True) -> tuple[Path, str, str]:
    """`main` holds a spec and a file `gone.txt`; the run's branch edits the spec, deletes the file and holds the
    finished plan of the `1-done` fixture with `command` as its verification command. With `moved`, `main` then
    changes the same spec. Returns the root, the run's base commit and the base branch's head."""
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (root / SPEC_PATH).parent.mkdir(parents=True)
    (root / SPEC_PATH).write_text(SPEC_V1)
    (root / "gone.txt").write_text("held by the base commit\n")
    (root / "tempergraph.commands.json").write_text(json.dumps({"schema_version": 1, "commands": ["pytest"]}))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "-b", "run")
    for f in sorted(p for p in DONE.rglob("*") if p.is_file()):
        target = root / f.relative_to(DONE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.read_text().replace("`git --version`", f"`{command}`"))
    if traced:
        with (root / "tests" / "test_config.py").open("a") as out:
            out.write("\n# PSE-AC1\n")
    (root / SPEC_PATH).write_text(SPEC_RUN)
    _git(root, "rm", "-q", "gone.txt")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the run")
    head = base
    if moved:
        _git(root, "checkout", "-q", "main")
        (root / SPEC_PATH).write_text(SPEC_MAIN)
        _git(root, "commit", "-q", "-am", "main moves")
        head = _git(root, "rev-parse", "HEAD")
        _git(root, "checkout", "-q", "run")
    return root, base, head


class _Ctx(CheckContext):
    """A check context that records `(command, at_base)` and answers a scripted command with a scripted run."""

    calls: list[tuple[str, bool]]
    script: dict[tuple[str, bool], CommandRun]

    def run(self, cmd: str, **kw: Any) -> Any:  # type: ignore[override]
        at_base = bool(kw.get("at_base"))
        self.calls.append((cmd, at_base))
        got = self.script.get((cmd, at_base))
        if got is None:
            return super().run(cmd, **kw)
        self.runs.append(got)
        return got


def _ctx(root: Path, base: str | None, head: str, *, script: dict[tuple[str, bool], CommandRun] | None = None,
         store: Path | None = None) -> _Ctx:
    artifacts: dict[str, dict[str, str]] = {}
    for f in sorted(p for p in DONE.rglob("*") if p.is_file()):
        if f.stem in OWNER:
            artifacts.setdefault(OWNER[f.stem], {})[f.stem] = f.relative_to(DONE).as_posix()
    facts = dataclasses.replace(git_facts(root, base) or GitFacts(), base_head=head) if base else GitFacts()
    ctx = _Ctx(unit="outcome", workdir=root, request={}, artifacts=artifacts, git=facts, allow=SPEC.allow_commands,
               values={"triage": {"route": "plan"}}, out_dir=root.parent / f"{root.name}.out",
               deadline_at=time.monotonic() + 120, reuse_store=store)
    ctx.settings = {"deliverables": [], "outcome_check": SPEC.outcome.check.ref}  # type: ignore[union-attr]
    ctx.calls, ctx.script = [], script or {}
    return ctx


def _run(cmd: str, exit_code: int | None, *, at_base: bool, tail: str = "", **kw: Any) -> CommandRun:
    ok = exit_code is not None and not kw
    return CommandRun(argv=tuple(cmd.split()), exit_code=exit_code, finished=ok, at_base=at_base, duration_s=0.1,
                      tail=tail, **kw)


def _failing(res: Any) -> list[str]:
    return [str(f.criterion) for f in res.findings if f.status == "fail"]


def _finding(res: Any, criterion: str) -> Any:
    return next(f for f in res.findings if f.criterion == criterion)


def _lead(res: Any) -> str:
    return str(res.evidence.splitlines()[0])


# -- a stale spec pauses (OGT-AC23, SBS-AC6, AC 1) ------------------------------------------------------------


def test_a_stale_spec_marks_the_result_environmental(tmp_path: Path) -> None:  # OGT-AC23, SBS-AC6, AC 1
    root, base, head = _repo(tmp_path / "repo", "git --version", moved=True)
    res = checks.outcome_check(_ctx(root, base, head))
    assert res.result == "FAIL" and res.environmental, res.evidence
    assert _failing(res) == ["ts-spec-fresh"]
    found = _finding(res, "ts-spec-fresh")
    assert isinstance(found, checks._Environmental) and found.place == SPEC_PATH
    assert SPEC_PATH in found.message and base[:10] in found.message and head[:10] in found.message
    assert FIX in found.fix
    assert "ts-spec-fresh" in res.evidence[:200] and SPEC_PATH in res.evidence[:200]
    lines = res.evidence.splitlines()
    action = next(i for i, ln in enumerate(lines) if FIX in ln)
    push = next(i for i, ln in enumerate(lines) if "branch is" in ln and "pushed" in ln)
    assert action < push


def test_the_result_passes_the_guard_after_the_head_is_merged(tmp_path: Path) -> None:  # OGT-AC23, SBS-AC6, AC 1
    root, base, head = _repo(tmp_path / "repo", "git --version", moved=True)
    _git(root, "merge", "-q", "-s", "ours", "-m", "merge main", "main")
    res = checks.outcome_check(_ctx(root, base, head))
    assert _finding(res, "ts-spec-fresh").status == "pass"
    assert not res.environmental and res.result == "PASS", res.evidence


# -- a verification command compared with the base (OGT-AC24, OGT-AC28, OGT-AC29, OGT-AC30) ------------------


def test_a_command_that_fails_the_same_at_the_base_pauses(tmp_path: Path) -> None:  # OGT-AC24, OGT-AC29, AC 2
    root, base, head = _repo(tmp_path / "repo", ABSENT, moved=False)
    ctx = _ctx(root, base, head)
    res = checks.outcome_check(ctx)
    assert res.result == "FAIL" and res.environmental and _failing(res) == ["ts-verify"]
    assert _lead(res).startswith(f"ts-verify: `{ABSENT}` exit 128 at the gate, 128 at the base: environmental")
    first = res.evidence[:200]
    assert ABSENT in first and "128 at the gate" in first and "environmental" in first
    assert (ABSENT, True) in ctx.calls


def test_a_command_the_change_caused_goes_back(tmp_path: Path) -> None:  # OGT-AC28, AC 4
    root, base, head = _repo(tmp_path / "repo", GONE, moved=False)
    res = checks.outcome_check(_ctx(root, base, head))
    assert res.result == "FAIL" and not res.environmental
    found = _finding(res, "ts-verify")
    assert found.status == "fail" and not isinstance(found, checks._Environmental) and found.fix
    assert f"`{GONE}` exit 128 at the gate, 0 at the base: caused by the change" in found.message
    assert "To clear" not in res.evidence


def test_the_four_cases_and_the_not_compared_cases(tmp_path: Path) -> None:  # OGT-AC29, AC 2
    root, base, head = _repo(tmp_path / "repo", PYTEST, moved=False)
    fails = _run(PYTEST, 1, at_base=False, tail="boom")

    def gate(here: CommandRun, there: CommandRun | None, with_base: bool = True) -> Any:
        script = {(PYTEST, False): here}
        if there is not None:
            script[(PYTEST, True)] = there
        return checks.outcome_check(_ctx(root, base if with_base else None, head, script=script))

    named = gate(_run(PYTEST, 1, at_base=False, tail="FAILED tests/test_config.py::test_a"),
                 _run(PYTEST, 2, at_base=True, tail="usage"))
    assert not named.environmental and "names the changed file tests/test_config.py" in \
        _finding(named, "ts-verify").message
    unnamed = gate(_run(PYTEST, 1, at_base=False, tail="No module named 'x'"), _run(PYTEST, 2, at_base=True))
    assert unnamed.environmental and "its output names no file the run changed" in _lead(unnamed)
    cases = {
        "no base commit": (fails, None, False, "the run has no base commit"),
        "could not start": (fails, _run(PYTEST, None, at_base=True, not_started=True), True,
                            "could not start at the base commit"),
        "did not finish": (fails, _run(PYTEST, -9, at_base=True, timed_out=True), True,
                           "did not finish at the base commit"),
    }
    for name, (here, there, with_base, reason) in cases.items():
        res = gate(here, there, with_base)
        found = _finding(res, "ts-verify")
        assert res.result == "FAIL" and not res.environmental, name
        assert "not compared" in found.message and reason in found.message, (name, found.message)


def test_a_passing_command_is_never_run_at_the_base(tmp_path: Path) -> None:  # OGT-AC30, AC 3
    root, base, head = _repo(tmp_path / "repo", "git --version", moved=False)
    ctx = _ctx(root, base, head)
    res = checks.outcome_check(ctx)
    assert _finding(res, "ts-verify").status == "pass" and ("git --version", False) in ctx.calls
    assert not [c for c in ctx.calls if c[1]] and not any(r.at_base for r in ctx.runs)


def test_a_failing_command_is_started_at_the_base_once_per_visit(tmp_path: Path) -> None:  # OGT-AC30, AC 3
    root, base, head = _repo(tmp_path / "repo", ABSENT, moved=False)
    store = tmp_path / "store" / "command_runs.jsonl"
    answers = []
    for attempt in (1, 2):
        ctx = _ctx(root, base, head, store=store)
        ctx.attempt = attempt
        assert checks.outcome_check(ctx).environmental
        answers.append([(r.at_base, r.reused) for r in ctx.runs if r.argv == tuple(ABSENT.split())])
    assert answers == [[(False, False), (True, False)], [(False, True), (True, True)]]
    later = _ctx(root, base, head, store=store)
    later.visit = 2
    checks.outcome_check(later)
    assert [(r.at_base, r.reused) for r in later.runs if r.argv == tuple(ABSENT.split())][1] == (True, False)


# -- a fact no step can change beside a failure a step could repair (OGT-AC25, OGT-AC27, AC 5) ----------------


def test_a_stale_spec_beside_a_failing_trace_leads_the_evidence(tmp_path: Path) -> None:  # OGT-AC25, AC 5
    root, base, head = _repo(tmp_path / "repo", "git --version", moved=True, traced=False)
    res = checks.outcome_check(_ctx(root, base, head))
    assert res.result == "FAIL" and res.environmental
    assert {"ts-spec-fresh", "ts-traced"} <= set(_failing(res))
    assert _lead(res).startswith("ts-spec-fresh:")
    assert res.evidence.index("ts-spec-fresh") < res.evidence.index("ts-traced")


def test_an_environmental_command_beside_a_failing_trace_leads_the_evidence(tmp_path: Path) -> None:
    # OGT-AC25, AC 5
    root, base, head = _repo(tmp_path / "repo", ABSENT, moved=False, traced=False)
    res = checks.outcome_check(_ctx(root, base, head))
    assert res.environmental and {"ts-verify", "ts-traced"} <= set(_failing(res))
    assert _lead(res).startswith("ts-verify:")
    assert res.evidence.index("ts-verify") < res.evidence.index("ts-traced")


def test_a_stale_spec_beside_a_failure_the_change_caused_names_both(tmp_path: Path) -> None:  # OGT-AC25, AC 5
    root, base, head = _repo(tmp_path / "repo", GONE, moved=True)
    res = checks.outcome_check(_ctx(root, base, head))
    assert res.environmental and set(_failing(res)) == {"ts-spec-fresh", "ts-verify"}
    assert _lead(res).startswith("ts-spec-fresh:") and "ts-verify:" in res.evidence
    assert res.evidence.index("ts-spec-fresh") < res.evidence.index("ts-verify")


def test_each_fact_alone_is_the_one_failing_criterion(tmp_path: Path) -> None:  # OGT-AC27, AC 5
    root, base, head = _repo(tmp_path / "one", "git --version", moved=True)
    assert _failing(checks.outcome_check(_ctx(root, base, head))) == ["ts-spec-fresh"]
    root, base, head = _repo(tmp_path / "two", ABSENT, moved=False)
    assert _failing(checks.outcome_check(_ctx(root, base, head))) == ["ts-verify"]


def test_a_failing_trace_alone_is_not_marked(tmp_path: Path) -> None:  # OGT-AC25, AC 5
    root, base, head = _repo(tmp_path / "repo", "git --version", moved=False, traced=False)
    res = checks.outcome_check(_ctx(root, base, head))
    assert res.result == "FAIL" and _failing(res) == ["ts-traced"] and not res.environmental


# -- the criteria file says the same as the specs (OGT-AC23, AC 7, AC 8) -------------------------------------


def test_outcome_json_words_the_pause_and_carries_revision_29() -> None:  # OGT-AC23, AC 7, AC 8
    doc = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
    rows = {c["id"]: c for c in doc["final"]}
    overview = (ROOT / "docs" / "specs" / "overview.spec.md").read_text(encoding="utf-8")
    fresh, verify = rows["ts-spec-fresh"], rows["ts-verify"]
    for row in (fresh, verify):
        assert f"- [ ] {row['id']} {row['text']}" in overview
    method = fresh["check_method"]
    assert "pause" in method and "base commit" in method and "head" in method and "retry" in method
    method = verify["check_method"]
    assert "base commit" in method and "code gate" in method and "environmental" in method and "pause" in method
    text = " ".join(doc["assumptions"])
    assert "a person starts the task again" not in text
    assert "outcome gate pauses" in text and "ts-spec-fresh" in text and "retry" in text
    assert doc["revision"] == 29
    last = doc["revisions"][-1]
    assert last["revision"] == 29 and last["origin"] == "authored" and "issue 197" in last["note"]
    assert "outcome-gate" in last["note"] and "side-by-side-runs" in last["note"]
    for name in ("outcome-gate", "side-by-side-runs"):
        path = ROOT / "docs" / "specs" / f"{name}.spec.md"
        raw = path.read_bytes()
        assert len(raw.decode("utf-8").splitlines()) <= 400 and len(raw) <= 30720, name
