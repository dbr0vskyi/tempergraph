"""One re-read before the verdict (JDG-B17 to JDG-B21; JDG-AC11, JDG-AC12, JDG-AC13; task i204 AC 2, AC 3, AC 4)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import ScriptedExecutor, standin

from .fixtures.workflows import crit, two_step
from .test_run import DRAFT, REVIEW, go, judge, records


def block(rows: list[tuple[str, bool, str]], gap: bool = False, gap_unread: bool = False,
          summary: str = "one line") -> str:
    """A judgement block: one row per criterion (status, unread, fix); evidence is given for every row."""
    crits = [{"n": i, "status": s, "evidence": "notes.md:1 shows it" if s == "MET" else "not opened",
              "place": "notes.md", "fix": fix, "unread": unread} for i, (s, unread, fix) in enumerate(rows, 1)]
    return "Reviewed.\n```json\n" + json.dumps({"criteria": crits, "gap": gap, "gap_unread": gap_unread,
                                                "confidence": 0.8, "summary": summary}) + "\n```"


CLEAN = block([("MET", False, ""), ("MET", False, "")])


def two_blockers() -> Any:
    spec = two_step()
    units = dict(spec.units)
    gate = units["draft"].gate
    units["draft"] = dataclasses.replace(units["draft"], gate=dataclasses.replace(
        gate, criteria=(gate.criteria[0], crit("c-two"))))
    return dataclasses.replace(spec, units=units)


def request_kinds(ex: ScriptedExecutor) -> list[str]:
    return [c.request.kind for c in ex.calls]


def drive(repo: Path, judges: list[str], steps: int = 4) -> tuple[Any, ScriptedExecutor]:
    """The scripted judges first, then spare answers so a run that goes on never meets an empty queue."""
    ex = standin("claude", steps=[DRAFT] * steps + [REVIEW] * 2,
                 judges=[judge(t) for t in judges] + [judge(CLEAN)] * 4)
    return go(repo, ex, two_blockers()), ex


def test_jdg_ac11_a_marked_gap_runs_one_reread_before_any_verdict(repo: Path) -> None:
    first = block([("MET", False, ""), ("MET", False, "")], gap=True, gap_unread=True, summary="open notes.md")
    out, ex = drive(repo, [first, CLEAN, CLEAN], steps=2)
    assert request_kinds(ex)[:3] == ["step", "judge", "judge_reread"]
    assert out.exit_code is not ExitCode.PAUSED


def test_jdg_ac11_a_marked_only_failing_blocker_runs_one_reread(repo: Path) -> None:
    first = block([("MET", False, ""), ("PARTIAL", True, "open notes.md lines 1-9")])
    _, ex = drive(repo, [first, CLEAN], steps=2)
    assert request_kinds(ex)[:3] == ["step", "judge", "judge_reread"]


def test_jdg_ac11_one_marked_and_one_unmarked_blocker_start_no_reread(repo: Path) -> None:  # AC 4
    first = block([("PARTIAL", True, "open notes.md"), ("UNMET", False, "write it")])
    out, ex = drive(repo, [first], steps=1)
    assert "judge_reread" not in request_kinds(ex)
    assert request_kinds(ex)[:2] == ["step", "judge"]
    assert [r for r in records(repo) if r["kind"] == "judgement"][0]["blockers"] == ["c-file", "c-two"]


def test_jdg_ac11_a_marked_blocker_with_an_unmarked_gap_starts_no_reread(repo: Path) -> None:  # AC 4
    first = block([("MET", False, ""), ("PARTIAL", True, "open notes.md")], gap=True, gap_unread=False)
    out, ex = drive(repo, [first], steps=1)
    assert "judge_reread" not in request_kinds(ex)
    assert out.exit_code is ExitCode.PAUSED  # ESCALATE of today: an unresolved gap


def test_jdg_ac12_the_reread_prompt_and_request(repo: Path) -> None:
    first = block([("MET", False, ""), ("PARTIAL", True, "open notes.md lines 1-9")], summary="did not open notes")
    _, ex = drive(repo, [first, CLEAN], steps=2)
    one, two = ex.calls[1], ex.calls[2]
    assert two.request.kind == "judge_reread" and one.request.kind == "judge"
    prompt = two.request.prompt
    assert "did not open notes" in prompt and "open notes.md lines 1-9" in prompt
    assert "read tool" in prompt and "every criterion" in prompt and "## How to answer" in prompt
    assert "Release 1.2 notes" in prompt
    assert prompt != one.request.prompt
    a, b = one.request, two.request
    assert (a.alias, a.options, a.workdir, a.timeout_s, a.idle_s) == (b.alias, b.options, b.workdir, b.timeout_s, b.idle_s)
    assert one.views is not None and two.views is not None and one.views.tools == two.views.tools
    assert a.session_key != b.session_key and a.session_dir != b.session_dir


def test_jdg_ac12_a_clean_reread_goes_on_with_no_pause_no_retry(repo: Path) -> None:  # AC 2
    first = block([("MET", False, ""), ("MET", False, "")], gap=True, gap_unread=True, summary="open notes.md")
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(first), judge(CLEAN), judge()])
    out = go(repo, ex, two_blockers())
    assert out.exit_code is ExitCode.FINISHED, out.message
    kinds = request_kinds(ex)
    assert kinds.count("retry") == 0 and kinds.count("step") == 2
    recs = records(repo)
    assert not [r for r in recs if r["kind"] in ("pause", "escalate")]
    assert [r for r in recs if r["kind"] == "judgement"][0]["gap"] is False


def test_jdg_ac12_the_verdict_comes_from_the_reread_alone(repo: Path) -> None:
    first = block([("MET", False, ""), ("PARTIAL", True, "open notes.md")])
    second = block([("MET", False, ""), ("UNMET", False, "write it")])
    _, ex = drive(repo, [first, second, CLEAN, CLEAN], steps=2)
    first_judgement = [r for r in records(repo) if r["kind"] == "judgement"][0]
    assert first_judgement["blockers"] == ["c-two"]
    assert request_kinds(ex)[:4] == ["step", "judge", "judge_reread", "retry"]


def test_jdg_ac13_a_reread_that_marks_its_gap_again_gets_no_third_session(repo: Path) -> None:
    first = block([("MET", False, ""), ("MET", False, "")], gap=True, gap_unread=True, summary="open it")
    out, ex = drive(repo, [first, first], steps=1)
    assert request_kinds(ex) == ["step", "judge", "judge_reread"]
    assert out.exit_code is ExitCode.PAUSED


def test_jdg_ac13_a_reread_that_marks_a_partial_blocker_again_retries(repo: Path) -> None:
    first = block([("MET", False, ""), ("PARTIAL", True, "open notes.md")])
    _, ex = drive(repo, [first, first, CLEAN], steps=2)
    assert request_kinds(ex)[:4] == ["step", "judge", "judge_reread", "retry"]
    assert request_kinds(ex).count("judge_reread") == 1
