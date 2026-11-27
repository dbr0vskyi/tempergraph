"""Task i197a: stand-in runs of the loaded package with the real outcome check and a recording finalizer. A fact no step
can change (a spec the base branch changed, a command that fails the same at the base) ends the first invocation paused
at the outcome gate with kind `escalation`, no step entered and no outcome judge session; after a merge of the head and
`retry` the run goes on (OGT-B13 to OGT-B16, SBS-B4). The routing is the engine's own; only sessions are stand-ins."""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tempergraph.api import CheckResult
from tempergraph.constants import ExitCode
from tempergraph.contracts import CallableRef, SessionRequest, SessionResult
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin
from tempergraph.package.loader import load_package
from tempergraph.run.finalize import FinalizerResult
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
TASK = "P-1"
SPEC_PATH = "docs/specs/pause.spec.md"
ABSENT = "git show HEAD:absent.txt"  # exits 128 at the gate and at the base alike
GONE = "git show HEAD:gone.txt"  # exits 0 at the base; the run deletes the file, so 128 at the gate
OK = "git --version"
SPEC_V1 = ("# Pause\n\n## Purpose\n\nA scratch spec.\n\n## Behaviours\n\n### PSE-B1 A thing\n\n"
           "WHEN a thing happens THE service SHALL answer.\n\n- GIVEN a state WHEN an event THEN a result\n\n"
           "## Acceptance criteria\n\n- PSE-AC1 (PSE-B1): A request is answered\n")
SPEC_RUN = SPEC_V1.replace("A request is answered", "A request is answered with a body")
SPEC_MAIN = SPEC_V1.replace("A request is answered", "A request is answered at once")
REASON = "Why this unit runs again"
NOTE = ("# Triage: P-1\n\n## Task\n\nA task.\n\n## Acceptance criteria\n\n1. A thing\n\n## Existing documents\n\n- None\n\n"
        "## Gaps\n\nNone\n\n## Owner decisions\n\nNone\n\n## Route\n\n- Deliver: code\n- Route: quick\n\n"
        "## Change\n\n- Files: `README.md`\n- Tests: `tests/test_pause_x.py`\n- Verify: `{command}`\n")
FINALS: list[str] = []


def passes(ctx: Any) -> CheckResult:
    return CheckResult(result="PASS", evidence="stand-in")


def ready(ctx: Any) -> dict[str, str]:
    return {"setup_ready": "yes"}


def record_final(ctx: Any) -> FinalizerResult:
    FINALS.append(ctx.task_id)
    return FinalizerResult(outcome="skipped", reason="recorded by the test")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


class Stand:
    """A stand-in executor: the quick lane's triage and code sessions, a clean review and an outcome judge that grades
    every criterion MET. It records each session by kind and unit. The first code session edits the spec, adds the
    test that names its criterion (unless `traced` is false), deletes `gone.txt` and, with `moved`, makes a commit to
    the same spec on the main checkout's branch; a later code session puts `gone.txt` back."""

    def __init__(self, main: Path, command: str, *, moved: bool, traced: bool = True) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.main, self.command, self.moved, self.traced = main, command, moved, traced
        self.sessions: list[dict[str, Any]] = []
        self.workdir: Path | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def _enter(self, kind: str, req: SessionRequest) -> dict[str, Any]:
        row = {"kind": kind, "unit": req.session_key.split(".")[0], "prompt": req.prompt}
        self.sessions.append(row)
        return row

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit = str(self._enter("step", req)["unit"])
        work = Path(req.workdir)
        if unit == "triage":
            (work / "triage_note.md").write_text(NOTE.replace("{command}", self.command), encoding="utf-8")
            return answer("Triaged.\nARTIFACT triage_note: triage_note.md\nARTIFACT gaps: none\nARTIFACT route: quick",
                          session_id="s-triage")
        if unit == "code":
            self.workdir = work
            first = sum(1 for s in self.sessions if s["kind"] == "step" and s["unit"] == "code") == 1
            if first:
                (work / SPEC_PATH).parent.mkdir(parents=True, exist_ok=True)
                (work / SPEC_PATH).write_text(SPEC_RUN, encoding="utf-8")
                if self.traced:
                    (work / "tests").mkdir(exist_ok=True)
                    (work / "tests" / "test_pause_x.py").write_text(
                        "def test_a_request_is_answered() -> None:  # PSE-AC1\n    assert True\n", encoding="utf-8")
                (work / "gone.txt").unlink(missing_ok=True)
                if self.moved:
                    (self.main / SPEC_PATH).write_text(SPEC_MAIN, encoding="utf-8")
                    _git(self.main, "add", SPEC_PATH)
                    _git(self.main, "commit", "-q", "-m", "main moves")
            else:  # the session that was sent back repairs what the change caused
                (work / "gone.txt").write_text("held by the base commit\n", encoding="utf-8")
                (work / "tests").mkdir(exist_ok=True)
                (work / "tests" / "test_pause_x.py").write_text(
                    "def test_a_request_is_answered() -> None:  # PSE-AC1\n    assert True\n", encoding="utf-8")
            (work / "report.md").write_text(f"# Code report\n\n<!-- code session {len(self.sessions)} -->\n",
                                            encoding="utf-8")
            return answer("Coded.\nARTIFACT code_report: report.md\nARTIFACT tests_passed: yes",
                          session_id=f"s-code-{len(self.sessions)}")
        if unit == "independent_review":
            (work / ".tempergraph" / "review").mkdir(parents=True, exist_ok=True)
            (work / ".tempergraph" / "review" / "findings.md").write_text("## Findings\n\nNone\n", encoding="utf-8")
            return answer("Read.", session_id=f"s-review-{len(self.sessions)}")
        raise AssertionError(f"a session of {unit} that the stand-in does not answer")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        unit = str(self._enter("judge", req)["unit"])
        count = (len(re.findall(r"^\d+\. \[", req.prompt, re.MULTILINE)) if unit == "outcome"
                 else max(len(SPEC.units[unit].gate.criteria), 1))
        rows = [{"n": i, "status": "MET", "evidence": "stand-in", "defect_in": None, "no_change": False}
                for i in range(1, count + 1)]
        text = "Reviewed.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.9}) + "\n```"
        return answer(text, tools=("Read",), session_id=f"j-{unit}-{len(self.sessions)}")

    def judged(self) -> int:
        return sum(1 for s in self.sessions if s["kind"] == "judge" and s["unit"] == "outcome")

    def steps(self) -> list[str]:
        return [str(s["unit"]) for s in self.sessions if s["kind"] == "step"]


def _spec() -> Any:
    """The package with the checks of its units replaced by one that passes, `prepare` answered by a callable, the
    code step not asked for its own check run and a recording finalizer; the outcome and its real check stay."""
    units = {}
    for name, u in SPEC.units.items():
        gate = u.gate
        if gate.check is not None:
            gate = dataclasses.replace(gate, check=CallableRef(module=__name__, qualname="passes", func=passes))
        step = dataclasses.replace(u.step, self_check=False) if u.step is not None and name == "code" else u.step
        units[name] = dataclasses.replace(u, gate=gate, step=step)
    script = dataclasses.replace(SPEC.units["prepare"].script, run=None,
                                 call=CallableRef(module=__name__, qualname="ready", func=ready))
    units["prepare"] = dataclasses.replace(units["prepare"], script=script)
    assert SPEC.outcome is not None and SPEC.finalizer is not None
    final = CallableRef(module=__name__, qualname="record_final", func=record_final)
    return dataclasses.replace(SPEC, units=units, finalizer=final)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / SPEC_PATH).parent.mkdir(parents=True)
    _git(root.parent, "init", "-q", "-b", "main", str(root))
    (root / SPEC_PATH).write_text(SPEC_V1, encoding="utf-8")
    (root / "gone.txt").write_text("held by the base commit\n", encoding="utf-8")
    (root / "README.md").write_text("scratch\n", encoding="utf-8")
    (root / ".gitignore").write_text(".tempergraph/\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    FINALS.clear()
    return root


def _settings() -> RunSettings:
    return RunSettings(sleep=lambda s: None, flags={"code_mode.arm": "single"})


def _registry(stand: Stand) -> Registry:
    registry = Registry()
    registry.register(stand)
    return registry


def _go(repo: Path, stand: Stand) -> Any:
    return start(_spec(), TASK, {"request": "x"}, repo, _registry(stand), _settings())


def _retry(repo: Path, stand: Stand) -> Any:
    return resume(_spec(), TASK, repo, _registry(stand), decision="retry", settings=_settings())


def _rows(repo: Path, kind: str) -> list[dict[str, Any]]:
    path = run_dir(state_root_path(repo), SPEC.name, TASK) / "run.jsonl"
    rows = map(json.loads, path.read_text(encoding="utf-8").splitlines())
    return [r for r in rows if r["kind"] == kind and r.get("unit") == "outcome"]


def _paused_at_the_outcome(repo: Path, stand: Stand, out: Any) -> str:
    """The first invocation ended paused at the outcome gate, kind `escalation`, with no step entered after the
    review and no outcome judge session; returns the evidence the check logged."""
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert out.reason == "escalation" and (out.payload or {}).get("unit") == "outcome", out.payload
    assert stand.steps() == ["triage", "code"], stand.steps()  # no step entered after the code step
    assert stand.judged() == 0
    checks = _rows(repo, "check")
    assert len(checks) == 1 and checks[0]["environmental"] is True, checks
    gates = _rows(repo, "gate")
    assert [g["token"] for g in gates] == ["ESCALATE"], gates
    return str(checks[0]["evidence"])


def test_a_moved_base_pauses_and_a_merged_head_with_retry_reaches_the_finalizer(repo: Path) -> None:
    # OGT-AC23, OGT-AC26, SBS-AC6, AC 1, AC 6
    stand = Stand(repo, OK, moved=True)
    out = _go(repo, stand)
    evidence = _paused_at_the_outcome(repo, stand, out)
    assert "ts-spec-fresh" in evidence and SPEC_PATH in evidence, evidence
    assert FINALS == []
    assert stand.workdir is not None
    _git(stand.workdir, "merge", "-q", "-s", "ours", "-m", "merge main", "main")
    again = _retry(repo, stand)
    assert again.exit_code is ExitCode.FINISHED, again.message
    assert FINALS == [TASK]
    assert stand.judged() == 1  # none before the answer, one session after it
    assert [g["token"] for g in _rows(repo, "gate")] == ["ESCALATE", "PROCEED"]


def test_a_command_that_fails_the_same_at_the_base_pauses(repo: Path) -> None:  # OGT-AC24, OGT-AC26, AC 2, AC 6
    stand = Stand(repo, ABSENT, moved=False)
    out = _go(repo, stand)
    evidence = _paused_at_the_outcome(repo, stand, out)
    assert ABSENT in evidence and "128 at the gate, 128 at the base" in evidence and "environmental" in evidence, evidence
    assert FINALS == []


def test_a_moved_base_beside_a_failing_trace_pauses_then_goes_back_for_the_trace(repo: Path) -> None:
    # OGT-AC25, OGT-AC26, AC 5, AC 6
    stand = Stand(repo, OK, moved=True, traced=False)
    out = _go(repo, stand)
    evidence = _paused_at_the_outcome(repo, stand, out)
    # the log keeps 200 characters, where the cut falls inside the name of the trace: the stale spec comes first
    assert SPEC_PATH in evidence and evidence.index("ts-spec-fresh") < evidence.index("ts-trace"), evidence
    assert stand.workdir is not None
    _git(stand.workdir, "merge", "-q", "-s", "ours", "-m", "merge main", "main")
    seen = len(stand.sessions)
    again = _retry(repo, stand)
    assert again.exit_code is ExitCode.FINISHED, (again.message, again.payload)  # the second failure is routed, no pause
    entered = [s for s in stand.sessions[seen:] if s["kind"] == "step"]
    serving = [u for u in SPEC.order if u in SPEC.outcome.intermediate  # type: ignore[union-attr]
               and any("ts-traced" in c.serves for c in SPEC.outcome.intermediate[u].criteria)]  # type: ignore[union-attr]
    taken = [u for u in SPEC.order if u in set(stand.steps())]
    target = next(u for u in serving if u in taken)
    assert entered and entered[0]["unit"] == target, ([s["unit"] for s in entered], target)
    assert "PSE-AC1 is named by no test" in str(entered[0]["prompt"]).split(REASON, 1)[1]  # the ts-traced finding
    gates = _rows(repo, "gate")
    assert [g["token"] for g in gates][:2] == ["ESCALATE", "BACK"], gates


def test_a_command_the_change_caused_goes_back_without_a_pause(repo: Path) -> None:  # OGT-AC28, AC 4
    stand = Stand(repo, GONE, moved=False)
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    gates = _rows(repo, "gate")
    assert [g["token"] for g in gates] == ["BACK", "PROCEED"], gates
    assert all(c["environmental"] is False for c in _rows(repo, "check")[:1])
    taken = [u for u in SPEC.order if u in set(stand.steps())]
    serving = [u for u in SPEC.order if u in SPEC.outcome.intermediate  # type: ignore[union-attr]
               and any("ts-verify" in c.serves for c in SPEC.outcome.intermediate[u].criteria)]  # type: ignore[union-attr]
    target = next(u for u in serving if u in taken)
    at = next(i for i, s in enumerate(stand.sessions) if s["unit"] == "code")
    after = [s for s in stand.sessions[at + 1:] if s["kind"] == "step"]
    assert after and after[0]["unit"] == target, ([s["unit"] for s in after], target)
    reason = str(after[0]["prompt"]).split(REASON, 1)[1]
    assert "gone.txt" in reason, reason
    assert FINALS == [TASK]
