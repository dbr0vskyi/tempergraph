"""The code gate compares a command that fails with the run's base commit (ts-code-verify, ts-code-base to
ts-code-spend). The file builds its own scratch repository, so it passes alone."""

from __future__ import annotations

import importlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, git_facts, run_check
from tempergraph.run.commands import CommandRun

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
DONE = ROOT / "evals" / "checks" / "code" / "must-pass" / "1-done"
OWNER = {key: unit for unit in SPEC.order for key in (SPEC.units[unit].step.produces if SPEC.units[unit].step else {})}
GATE = SPEC.units["code"].gate
ABSENT = "git show HEAD:absent.txt"  # exits 128 in the workspace and at the base alike
GONE = "git show HEAD:gone.txt"  # the base commit holds the file and the head deleted it: exit 0 at the base
PYTEST = "pytest tests/test_config.py"
IN_SUB = "cd sub && pytest tests/test_x.py"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


def _repo(root: Path, command: str) -> tuple[Path, str]:
    """A repository with a base commit, and as its head the finished plan of the `1-done` fixture whose
    verification command is `command`, with a file of `sub` and the file `gone.txt` deleted."""
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("base readme\n")
    (root / "gone.txt").write_text("held by the base commit\n")
    (root / "tempergraph.commands.json").write_text(json.dumps({"schema_version": 1, "commands": ["pytest"]}))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD").strip()
    for f in sorted(p for p in DONE.rglob("*") if p.is_file()):
        target = root / f.relative_to(DONE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.read_text().replace("`git --version`", f"`{command}`"))
    (root / "sub" / "tests").mkdir(parents=True)
    (root / "sub" / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
    _git(root, "rm", "-q", "gone.txt")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the code step")
    return root, base


class _Ctx(CheckContext):
    """A check context that records `(command, at_base)` and answers a scripted command with a scripted run."""

    calls: list[tuple[str, bool]]
    script: dict[tuple[str, bool], CommandRun]

    def run(self, cmd: str, **kw: Any) -> Any:  # type: ignore[override]
        at_base = bool(kw.get("at_base"))
        if not cmd.startswith(READING_DIFF):  # the judge-reading count is not a plan command
            self.calls.append((cmd, at_base))
        got = self.script.get((cmd, at_base))
        if got is None:
            return super().run(cmd, **kw)
        self.runs.append(got)
        return got


READING_DIFF = "git diff --numstat"


def _plan_runs(res: Any) -> list[dict[str, Any]]:
    """The command runs of the plan's commands, without the reading budget's own git count (judge-reading)."""
    return [r for r in res.runs if "--numstat" not in str(r.get("argv", r.get("command", "")))]


def _ctx(root: Path, base: str | None, *, script: dict[tuple[str, bool], CommandRun] | None = None,
         store: Path | None = None, values: dict[str, Any] | None = None) -> _Ctx:
    artifacts: dict[str, dict[str, str]] = {}
    for f in sorted(p for p in DONE.rglob("*") if p.is_file()):
        if f.stem in OWNER:
            artifacts.setdefault(OWNER[f.stem], {})[f.stem] = f.relative_to(DONE).as_posix()
    facts = git_facts(root, base) if base else GitFacts()
    ctx = _Ctx(unit="code", workdir=root, request={}, artifacts=artifacts, git=facts, allow=SPEC.allow_commands,
               values={"triage": {"route": "plan"}, **(values or {})}, out_dir=root.parent / f"{root.name}.out",
               deadline_at=time.monotonic() + 120, reuse_store=store)
    ctx.calls, ctx.script = [], script or {}
    return ctx


def _run(cmd: str, exit_code: int | None, *, at_base: bool, tail: str = "", **kw: Any) -> CommandRun:
    ok = exit_code is not None and not kw
    return CommandRun(argv=tuple(cmd.split()), exit_code=exit_code, finished=ok, at_base=at_base, duration_s=0.1,
                      tail=tail, **kw)


def _verify_finding(res: Any) -> Any:
    return next(f for f in res.findings if f.criterion == "ts-code-verify")


def _failing(res: Any) -> list[str]:
    return [str(f.criterion) for f in res.findings if f.status == "fail"]


def test_a_command_that_fails_the_same_at_the_base_is_environmental(tmp_path: Path) -> None:
    # ts-code-base, ts-code-verify, ts-code-evidence, AC 1, AC 4: whatever the step reported about its own run
    root, base = _repo(tmp_path / "repo", ABSENT)
    ctx = _ctx(root, base, values={"code": {"tests_passed": "no"}})
    res, _ = run_check(GATE, ctx)
    assert res.result == "FAIL" and res.environmental, res.evidence
    assert _failing(res) == ["ts-code-verify"]
    first = res.evidence.splitlines()[0]
    assert first.startswith(f"ts-code-verify: `{ABSENT}` exit 128 at the gate, 128 at the base: environmental"), first
    assert ctx.calls == [(ABSENT, False), (ABSENT, True)]  # the command ran at the gate, then once at the base
    assert [(r["exit_code"], r["at_base"]) for r in _plan_runs(res)] == [(128, False), (128, True)]
    assert not (tmp_path / "repo" / "absent.txt").exists() and _git(root, "status", "--porcelain") == ""


def test_a_command_that_passes_at_the_base_and_fails_at_the_gate_is_a_retry(tmp_path: Path) -> None:
    # ts-code-passes, AC 3, ts-code-evidence, AC 4
    root, base = _repo(tmp_path / "repo", GONE)
    res, _ = run_check(GATE, _ctx(root, base))
    assert res.result == "FAIL" and not res.environmental
    found = _verify_finding(res)
    assert found.status == "fail" and found.fix
    assert f"`{GONE}` exit 128 at the gate, 0 at the base: caused by the change" in found.message


def test_a_different_exit_at_the_base_is_environmental_unless_a_changed_file_is_named(tmp_path: Path) -> None:
    # ts-code-touch, AC 2
    root, base = _repo(tmp_path / "repo", PYTEST)
    here = {(PYTEST, False): lambda tail: _run(PYTEST, 1, at_base=False, tail=tail)}
    there = _run(PYTEST, 2, at_base=True, tail="ERROR: no tests ran")

    def gate(tail: str) -> Any:
        script = {(PYTEST, False): here[(PYTEST, False)](tail), (PYTEST, True): there}
        return run_check(GATE, _ctx(root, base, script=script))[0]

    named = gate("FAILED tests/test_config.py::test_a - assert 1 == 2")  # a path the run changed, from the root
    assert named.result == "FAIL" and not named.environmental
    assert "caused by the change: its output names the changed file tests/test_config.py" in \
        _verify_finding(named).message and _verify_finding(named).status == "fail"
    unnamed = gate("ModuleNotFoundError: No module named 'missing_tool'")
    assert unnamed.result == "FAIL" and unnamed.environmental and _failing(unnamed) == ["ts-code-verify"]
    assert "exit 1 at the gate, 2 at the base: environmental" in unnamed.evidence.splitlines()[0]
    other = gate("FAILED tests/test_config.py_other - nothing")  # a longer name is not the changed file
    assert other.environmental


def test_a_changed_path_is_read_from_the_folder_the_command_ran_in(tmp_path: Path) -> None:
    # ts-code-touch, AC 2
    root, base = _repo(tmp_path / "repo", IN_SUB)
    script = {(IN_SUB, False): _run(IN_SUB, 1, at_base=False, tail="FAILED tests/test_x.py::test_x"),
              (IN_SUB, True): _run(IN_SUB, 4, at_base=True, tail="usage: pytest")}
    res, _ = run_check(GATE, _ctx(root, base, script=script))  # sub/tests/test_x.py is a changed path
    assert res.result == "FAIL" and not res.environmental
    assert "names the changed file sub/tests/test_x.py" in _verify_finding(res).message
    script[(IN_SUB, False)] = _run(IN_SUB, 1, at_base=False, tail="FAILED tests/test_y.py::test_y")
    res, _ = run_check(GATE, _ctx(root, base, script=script))
    assert res.environmental


def test_a_command_that_was_not_compared_fails_the_check(tmp_path: Path) -> None:
    # ts-code-nobase, ts-code-evidence, AC 3, AC 4
    root, base = _repo(tmp_path / "repo", PYTEST)
    fails = _run(PYTEST, 1, at_base=False, tail="boom")
    cases = {
        "no base commit": (None, {(PYTEST, False): fails}, "the run has no base commit"),
        "could not start": (base, {(PYTEST, False): fails, (PYTEST, True): _run(PYTEST, None, at_base=True, not_started=True)},
                            "could not start at the base commit"),
        "base timed out": (base, {(PYTEST, False): fails, (PYTEST, True): _run(PYTEST, -9, at_base=True, timed_out=True)},
                           "did not finish at the base commit"),
        "gate timed out": (base, {(PYTEST, False): _run(PYTEST, -9, at_base=False, timed_out=True)},
                           "did not finish at the gate"),
    }
    for name, (head, script, reason) in cases.items():
        ctx = _ctx(root, head, script=script)
        res, _ = run_check(GATE, ctx)
        found = _verify_finding(res)
        assert res.result == "FAIL" and not res.environmental, name
        assert found.status == "fail" and "not compared" in found.message and reason in found.message, (name, found)
        if name in ("no base commit", "gate timed out"):
            assert (PYTEST, True) not in ctx.calls, name


def test_a_mixed_failure_lists_only_what_the_step_can_fix(tmp_path: Path) -> None:
    # ts-code-mixed, AC 1, AC 2
    root, base = _repo(tmp_path / "repo", ABSENT)
    (root / "stray.txt").write_text("not committed\n")  # ts-code-commit fails as well
    res, _ = run_check(GATE, _ctx(root, base))
    assert res.result == "FAIL" and not res.environmental
    assert _failing(res) == ["ts-code-commit"]
    assert _verify_finding(res).status == "maybe"
    assert res.evidence.splitlines()[0].startswith(f"ts-code-verify: `{ABSENT}` exit 128 at the gate, 128 at the base")


def test_the_evidence_leads_with_the_command_both_exits_and_the_reason(tmp_path: Path) -> None:
    # ts-code-evidence, AC 4: the first 200 characters hold all three
    root, base = _repo(tmp_path / "repo", ABSENT)
    res, _ = run_check(GATE, _ctx(root, base))
    head = res.evidence[:200]
    assert ABSENT in head and "exit 128 at the gate, 128 at the base" in head and "environmental" in head


def test_a_command_that_passes_is_never_run_at_the_base(tmp_path: Path) -> None:
    # ts-code-spend, AC 5
    root, base = _repo(tmp_path / "repo", "git --version")
    ctx = _ctx(root, base)
    res, _ = run_check(GATE, ctx)
    assert _verify_finding(res).status == "pass" and ("git --version", False) in ctx.calls
    assert not [c for c in ctx.calls if c[1]] and not any(r["at_base"] for r in res.runs)


def test_a_failing_command_is_run_at_the_base_once_per_visit(tmp_path: Path) -> None:
    # ts-code-spend, ts-code-reuse, AC 5: a retry of the visit on the same tree and the same store
    root, base = _repo(tmp_path / "repo", ABSENT)
    store = tmp_path / "store" / "command_runs.jsonl"
    answers = []
    for attempt in (1, 2):
        ctx = _ctx(root, base, store=store)
        ctx.attempt = attempt
        res, _ = run_check(GATE, ctx)
        assert res.environmental
        assert [f.status for f in res.findings if f.criterion == "ts-code-reuse"] == ["pass"], res.evidence
        answers.append([(r["at_base"], r["reused"]) for r in _plan_runs(res)])
    assert answers == [[(False, False), (True, False)], [(False, True), (True, True)]]  # started once at the base
    later = _ctx(root, base, store=store)
    later.visit = 2
    res, _ = run_check(GATE, later)
    assert [(r["at_base"], r["reused"]) for r in _plan_runs(res)][1] == (True, False)  # the next visit asks again


def test_the_outcome_gate_asks_for_no_run_at_the_base(tmp_path: Path) -> None:
    # ts-verify, AC 3: its call of `_verify` is as before, with no comparison
    root, base = _repo(tmp_path / "repo", ABSENT)
    ctx = _ctx(root, base)
    plan, _ = checks._plan(ctx)
    found = checks._verify(ctx, plan, "ts-verify")
    assert [(f.status, f.criterion) for f in found] == [("fail", "ts-verify")]
    assert found[0].message.startswith("exit 128: ") and not [c for c in ctx.calls if c[1]]


# -- the package's criteria and its README say the same ---------------------------------------------------------

CODE_IDS = ("ts-code-verify", "ts-code-base", "ts-code-touch", "ts-code-passes", "ts-code-nobase", "ts-code-mixed",
            "ts-code-evidence", "ts-code-spend")


def test_outcome_json_holds_the_criteria_of_the_code_spec() -> None:
    # ts-code-verify, ts-code-base, ts-code-touch, ts-code-passes, ts-code-nobase, ts-code-mixed, ts-code-evidence,
    # ts-code-spend, AC 1, AC 2, AC 3, AC 4, AC 5: the same text, a check, and the revision that added them
    spec = (ROOT / "docs" / "specs" / "code.spec.md").read_text(encoding="utf-8")
    texts = dict(re.findall(r"^- \[ \] (ts-code-[a-z]+) (.+)$", spec, re.M))
    assert set(CODE_IDS) <= set(texts)
    doc = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
    rows = {c["id"]: c for c in doc["intermediate"]["code"]["criteria"]}
    for cid in CODE_IDS:
        row = rows[cid]
        assert row["text"] == texts[cid].strip(), cid
        assert row["verified_by"] == "check" and row["check_method"].strip(), cid
        assert row["verifier"] == {"check": "tgwf_temperspec.checks:code_check"}, cid
    # The entry for this change, wherever later changes put the file's revision.
    entry = next(r for r in doc["revisions"] if "issue 54" in r.get("note", ""))
    assert entry["revision"] >= 8 and entry["origin"] == "authored"
    assert doc["revision"] == doc["revisions"][-1]["revision"] >= entry["revision"]


def test_the_readme_says_the_code_gate_compares_a_failing_command_with_the_base() -> None:
    # ts-code-base, ts-code-passes, AC 1, AC 3
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    para = next(p for p in text.split("\n\n") if "The code gate runs the commands itself" in p)
    flat = " ".join(para.split())
    assert "base commit" in flat and "compares" in flat and "escalation" in flat and "retry" in flat
