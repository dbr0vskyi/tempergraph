"""Fixture runs of the file removal (spec file-removal, FRM-B2 to FRM-B6) on the loaded workflow, each arm: the package's
own `after` lists are kept, the sessions are the stand-ins of the independent review's tests."""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from tempergraph.constants import ExitCode
from tempergraph.run.checks import CheckContext, git_facts, run_check

ROOT = Path(__file__).resolve().parents[1]
TASK = "I-1"
MARK = "✓ 2026-11-28"
ARMS = ["single", "phases"]


def _load(name: str) -> Any:
    here = str(ROOT / "tests")
    if here not in sys.path:
        sys.path.insert(0, here)  # the engine imports the module's check functions by name
    return importlib.import_module(name)


irv = _load("test_independent_review")
fr = _load("test_file_removal")
checks = importlib.import_module("tgwf_temperspec.checks")
removal = importlib.import_module("tgwf_temperspec.removal")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("scratch\n", encoding="utf-8")
    for rel, text in {"src/old.py": "old\n", "src/other.py": "other\n", "src/pkg/a.py": "a\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "files")
    return root


def _work(repo: Path) -> Path:
    return repo.parent / "repo.worktrees" / f"temperspec--{TASK}"


def _plan(rows: list[tuple[str, str, str]], marked: set[str]) -> str:
    out = ["---\ntask: I-1\ncomplexity: complex\nstatus: in-progress\nspecs: []\n---\n", "# Plan: t\n",
           "## 2. Phases\n", "### Phase 1: part\n\nGoal: the part is in place.\nWeight: light\n",
           "| Row | Kind | Req | File | Proves | Change | Completed |", "|---|---|---|---|---|---|---|"]
    for i, kind, f in rows:
        out.append(f"| {i} | {kind} | R1 | `{f}` | {'AC 3' if kind == 'test' else ''} | A change of {f} | "
                   f"{MARK if i in marked else ''} |")
    return "\n".join(out) + "\n"


def _marked_in(path: Path) -> set[str]:
    return {m.group(1) for m in re.finditer(r"^\| (\S+) \|.*\| ✓ [\d-]+ \|$", path.read_text(encoding="utf-8"),
                                                                              re.MULTILINE)}


class RemStand(irv.Stand):
    """The review's stand-in with a plan of one phase. The first build session (the code step on `single`, the phase
    on `phases`) writes `src/new.py` and marks the rows of `marks`; on `phases` the code session, the join, then marks
    `late`. `timeout_first` ends the first build session in a timeout after it marked."""

    def __init__(self, rows: list[tuple[str, str, str]], marks: set[str], *, late: set[str] | None = None,
                 timeout_first: bool = False, after_build: Any = None) -> None:
        super().__init__()
        self.rows, self.marks, self.late = rows, marks, late or set()
        self.timeout_first, self.after_build = timeout_first, after_build
        self.builds = 0
        self.seen: list[bool] = []

    def _write(self, work: Path, rel: str, marked: set[str]) -> None:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(_plan(self.rows, marked), encoding="utf-8")

    def _plan_file(self, work: Path) -> str:
        return "phases.md" if (work / "phases.md").is_file() else f"docs/plans/{TASK}.plan.md"

    def _build(self, work: Path, marks: set[str]) -> bool:
        """The session's work; true when the session ends in a timeout."""
        from tempergraph.executors.standins import answer  # noqa: F401

        self.builds += 1
        self.seen.append((work / "src/old.py").is_file())
        rel = self._plan_file(work)
        timed_out = self.timeout_first and self.builds == 1
        if self.timeout_first and self.builds > 1:
            marks = set()  # the retry marks nothing
        (work / "src").mkdir(exist_ok=True)
        (work / "src/new.py").write_text(f"new = {self.builds}\n", encoding="utf-8")
        self._write(work, rel, marks)
        return timed_out

    def run_step(self, req: Any, sink: Any) -> Any:
        from tempergraph.contracts import SessionResult
        from tempergraph.executors.standins import answer

        unit, work = req.session_key.split(".")[0], Path(req.workdir)
        if unit == "plan":
            self.sessions.append({"kind": "step", "unit": unit, "prompt": req.prompt})
            self._write(work, f"docs/plans/{TASK}.plan.md", set())
            return answer(f"Planned.\nARTIFACT plan: docs/plans/{TASK}.plan.md\nARTIFACT complexity: complex",
                          session_id=f"s-{len(self.units())}")
        if unit == "expand":
            self.sessions.append({"kind": "step", "unit": unit, "prompt": req.prompt})
            self._write(work, "phases.md", set())
            return answer("Expanded.\nARTIFACT phases: phases.md", session_id=f"s-{len(self.units())}")
        arm_phases = (work / "phases.md").is_file()
        if unit == "phase" or (unit == "code" and not arm_phases):
            if self._build(work, self.marks):
                self.sessions.append({"kind": "step", "unit": unit, "prompt": req.prompt})
                return SessionResult(ok=False, text="", timed_out=True)
            if unit == "phase":
                self.sessions.append({"kind": "step", "unit": unit, "prompt": req.prompt})
                self._finish(work)
                return answer("Built.\nARTIFACT phase_note: built the phase", session_id=f"s-{len(self.units())}")
        elif unit == "code":
            rel = self._plan_file(work)
            self._write(work, rel, _marked_in(work / rel) | self.late)
        result = super().run_step(req, sink)
        if unit == "code":
            self._finish(work)
        return result

    def _finish(self, work: Path) -> None:
        """What the test does to the workspace once the session has written its files."""
        if self.after_build is not None:
            self.after_build(work)


def _spec(refusal_gates: bool = False) -> Any:
    spec = irv._spec()
    if refusal_gates:
        from tempergraph.contracts import CallableRef

        units = dict(spec.units)
        for name in ("code", "phase"):
            gate = dataclasses.replace(units[name].gate, check=CallableRef(module=__name__, qualname="refusal_check",
                                                                           func=refusal_check))
            units[name] = dataclasses.replace(units[name], gate=gate)
        spec = dataclasses.replace(spec, units=units)
    return spec


def refusal_check(ctx: Any) -> Any:
    """The code and phase gates as far as a refused removal is concerned (the criteria of the real checks)."""
    criterion = "ts-code-changed" if ctx.unit == "code" else "ts-phs-changed"
    found, _ = checks._refused_removals(ctx, criterion)
    return checks._result(ctx, found)


def _go(repo: Path, stand: Any, arm: str, refusal_gates: bool = False) -> Any:
    from tempergraph.executors.registry import Registry
    from tempergraph.run.runner import RunSettings, start

    registry = Registry()
    registry.register(stand)
    return start(_spec(refusal_gates), TASK, {"request": "x"}, repo, registry,
                 RunSettings(sleep=lambda s: None, flags={"code_mode.arm": arm}))


ROWS = [("1.1", "test", "tests/test_new.py"), ("1.2", "code", "src/new.py"), ("1.3", "remove", "src/old.py")]
TWO = [*ROWS, ("1.4", "remove", "src/other.py")]


def _ok(out: Any) -> None:
    assert out.exit_code is ExitCode.FINISHED, json.dumps(out.payload, default=str)[:1500]


@pytest.mark.parametrize("arm", ARMS)
def test_frm_ac2_a_marked_removal_row_ends_with_the_file_absent_and_no_pause(repo: Path, arm: str) -> None:
    # FRM-AC2, AC 3
    out = _go(repo, RemStand(ROWS, {"1.1", "1.2", "1.3"}), arm)
    _ok(out)
    work = _work(repo)
    assert not (work / "src/old.py").exists() and (work / "src/other.py").exists()
    assert "src/old.py" not in _git(work, "ls-tree", "-r", "--name-only", "HEAD").split()
    assert _git(work, "status", "--porcelain") == ""


@pytest.mark.parametrize("arm", ARMS)
def test_frm_ac3_an_unmarked_row_keeps_its_file(repo: Path, arm: str) -> None:
    # FRM-AC3, AC 3
    _ok(_go(repo, RemStand(ROWS, {"1.1", "1.2"}), arm))
    assert (_work(repo) / "src/old.py").is_file()


@pytest.mark.parametrize("arm", ARMS)
def test_frm_ac3_a_marked_row_whose_session_times_out_keeps_its_file(repo: Path, arm: str) -> None:
    # FRM-AC3, AC 3
    stand = RemStand(ROWS, {"1.1", "1.2", "1.3"}, timeout_first=True)
    _go(repo, stand, arm)
    assert stand.seen[:2] in ([True], [True, True])  # the file was there when the retry, if any, began
    assert (_work(repo) / "src/old.py").is_file()


@pytest.mark.parametrize("arm", ARMS)
def test_frm_ac4_the_removal_starts_no_session(repo: Path, arm: str) -> None:
    # FRM-AC4, AC 3
    removed, kept = RemStand(ROWS, {"1.1", "1.2", "1.3"}), RemStand(ROWS, {"1.1", "1.2"})
    _ok(_go(repo, removed, arm))
    assert not (_work(repo) / "src/old.py").exists()
    other = repo.parent / "second"
    other.mkdir()
    for args in (("init", "-q", "-b", "main"), ("add", "-A")):
        _git(other, *args)
    for rel in ("README.md", "src/old.py", "src/other.py", "src/pkg/a.py"):
        (other / rel).parent.mkdir(parents=True, exist_ok=True)
        (other / rel).write_text("x\n", encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-q", "-m", "init")
    _ok(_go(other, kept, arm))
    assert removed.units() == kept.units() and removed.units("judge") == kept.units("judge")
    assert "removal" not in removed.units() + removed.units("judge")


@pytest.mark.parametrize("arm", ARMS)
def test_frm_ac5_the_phase_commit_holds_the_change_the_marks_and_the_deletion(repo: Path, arm: str) -> None:
    # FRM-AC5, AC 3
    _ok(_go(repo, RemStand(ROWS, {"1.1", "1.2", "1.3"}), arm))
    work = _work(repo)
    unit = "phase" if arm == "phases" else "code"
    base = _git(work, "merge-base", "main", "HEAD").strip()
    commits = _git(work, "log", "--format=%H %s", f"{base}..HEAD").splitlines()
    mine = [c.split()[0] for c in commits if f" {unit} for {TASK}" in c]
    assert len(mine) == 1
    shown = _git(work, "show", "--name-status", "--format=", mine[0]).splitlines()
    plan = "phases.md" if arm == "phases" else f"docs/plans/{TASK}.plan.md"
    assert "D\tsrc/old.py" in shown and "A\tsrc/new.py" in shown and f"M\t{plan}" in shown
    assert _git(work, "status", "--porcelain") == ""
    # the plan check accepts the kept mark of the removal row after a trip back to the plan step
    ctx = CheckContext(unit="plan", workdir=work, request={}, artifacts={"plan": {"plan": plan}}, values={},
                       git=git_facts(work, base), allow=fr.SPEC.allow_commands,
                       out_dir=work.parent / f"{work.name}.out", deadline_at=time.monotonic() + 60)
    res, _ = run_check(fr.SPEC.units["plan"].gate, ctx)
    failing = [f for f in res.findings if f.criterion == "ts-plan-form" and f.status == "fail" and "`1.3`" in f.message]
    assert failing == []


@pytest.mark.parametrize("arm", ARMS)
def test_frm_ac6_a_second_visit_removes_nothing_and_does_not_fail_for_the_row(repo: Path, arm: str) -> None:
    # FRM-AC6, AC 3: the removal runs after the first session, and again after the code step on `phases`
    stand = RemStand(ROWS, {"1.1", "1.2", "1.3"}, late={"1.3"})
    _ok(_go(repo, stand, arm))
    assert not (_work(repo) / "src/old.py").exists()
    assert removal.refused(_work(repo)) == []


def test_frm_ac2_two_removal_rows_of_one_phase_are_both_removed(repo: Path) -> None:
    # FRM-AC2, AC 3
    _ok(_go(repo, RemStand(TWO, {"1.1", "1.2", "1.3", "1.4"}), "phases"))
    work = _work(repo)
    assert not (work / "src/old.py").exists() and not (work / "src/other.py").exists()


def test_frm_ac2_a_join_session_that_marks_a_row_its_phase_left_unmarked_has_its_file_removed(repo: Path) -> None:
    # FRM-AC2, AC 3
    stand = RemStand(ROWS, {"1.1", "1.2"}, late={"1.3"})
    _ok(_go(repo, stand, "phases"))
    work = _work(repo)
    assert (stand.seen and stand.seen[0]) and not (work / "src/old.py").exists()
    assert _git(work, "status", "--porcelain") == ""


def test_frm_ac2_the_code_gate_evidence_shows_each_verification_command_run_or_reused(tmp_path: Path) -> None:
    # FRM-AC2, AC 3: a plan with a removal row makes the gate run each command itself
    ctx = fr._gate_ctx(tmp_path, "code", [("5.1", "src/old.py", MARK)], changed=(*fr.CHANGED, "src/old.py"))
    res, _ = run_check(fr.SPEC.units["code"].gate, ctx)
    verify = [f for f in res.findings if f.criterion in ("ts-code-verify", "ts-code-reuse")]
    assert verify and all(f.status != "fail" for f in verify), [(f.criterion, f.message) for f in verify]


# -- FRM-B6: a path that cannot be removed pauses the run -----------------------------------------------------------


def _record(repo: Path, out: Any) -> str:
    """The pause as a person reads it: the payload and the run's record, which holds the gate's evidence."""
    from tempergraph.store.layout import run_dir, state_root_path

    log = run_dir(state_root_path(repo), irv.SPEC.name, TASK) / "run.jsonl"
    return json.dumps(out.payload, default=str) + log.read_text(encoding="utf-8")


def _outside(work: Path) -> None:
    (work.parent / "outside.txt").write_text("o\n", encoding="utf-8")


def _readonly(work: Path) -> None:
    os.chmod(work / "src", 0o555)


@pytest.mark.parametrize("arm", ARMS)
def test_frm_ac7_a_folder_pauses_at_once_naming_it_and_leaves_its_files(repo: Path, arm: str) -> None:
    # FRM-AC7, AC 3
    rows = [("1.1", "test", "tests/test_new.py"), ("1.2", "remove", "src/pkg")]
    stand = RemStand(rows, {"1.1", "1.2"})
    out = _go(repo, stand, arm, refusal_gates=True)
    assert out.exit_code is ExitCode.PAUSED, json.dumps(out.payload, default=str)[:1500]
    assert "src/pkg" in _record(repo, out) and "folder" in _record(repo, out)
    assert (_work(repo) / "src/pkg/a.py").is_file()
    assert stand.units().count("phase" if arm == "phases" else "code") == 1


@pytest.mark.parametrize("arm", ARMS)
def test_frm_ac7_a_path_outside_the_workspace_pauses_at_once_and_leaves_the_file(repo: Path, arm: str) -> None:
    # FRM-AC7, AC 3
    rows = [("1.1", "test", "tests/test_new.py"), ("1.2", "remove", "../outside.txt")]
    stand = RemStand(rows, {"1.1", "1.2"}, after_build=_outside)
    out = _go(repo, stand, arm, refusal_gates=True)
    assert out.exit_code is ExitCode.PAUSED, json.dumps(out.payload, default=str)[:1500]
    assert "../outside.txt" in _record(repo, out)
    assert (_work(repo).parent / "outside.txt").is_file()
    assert stand.units().count("phase" if arm == "phases" else "code") == 1


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores a read-only folder")
@pytest.mark.parametrize("arm", ARMS)
def test_frm_ac7_a_refusal_of_the_file_system_pauses_at_once_naming_the_file(repo: Path, arm: str) -> None:
    # FRM-AC7, AC 3
    rows = [("1.1", "test", "tests/test_new.py"), ("1.2", "remove", "src/old.py")]
    stand = RemStand(rows, {"1.1", "1.2"}, after_build=_readonly)
    try:
        out = _go(repo, stand, arm, refusal_gates=True)
    finally:
        if (_work(repo) / "src").is_dir():
            os.chmod(_work(repo) / "src", 0o755)
    assert out.exit_code is ExitCode.PAUSED, json.dumps(out.payload, default=str)[:1500]
    assert "src/old.py" in _record(repo, out)
    assert (_work(repo) / "src/old.py").is_file()
    assert stand.units().count("phase" if arm == "phases" else "code") == 1
