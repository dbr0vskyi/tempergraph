"""One re-read before the verdict (JDG-B17 to JDG-B21; JDG-AC11, JDG-AC12, JDG-AC13; task i204 AC 2, AC 3, AC 4)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

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
                 judges=[judge(t) if isinstance(t, str) else t for t in judges] + [judge(CLEAN)] * 4)
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


PARTIAL_FIRST = block([("MET", False, ""), ("PARTIAL", True, "open notes.md lines 1-9")])


def placeholder_checks(out: Any, ex: ScriptedExecutor, repo: Path) -> None:
    """The re-read's judgement is unparsed: ESCALATE, confidence 0.0, never derived from the first (JDG-B21)."""
    assert out.exit_code is ExitCode.PAUSED, out.message
    (rec,) = [r for r in records(repo) if r["kind"] == "judgement"]
    assert rec["confidence"] == 0.0 and rec["confidence_source"] == "engine_placeholder"
    assert rec["blockers"] == [] and "retry" not in request_kinds(ex)


def test_jdg_ac14_a_reread_that_times_out_is_an_unparsed_judgement(repo: Path) -> None:  # JDG-AC14, AC 3
    timed_out = dataclasses.replace(judge(CLEAN), timed_out=True, ok=False)
    out, ex = drive(repo, [PARTIAL_FIRST, timed_out], steps=1)
    assert request_kinds(ex)[:3] == ["step", "judge", "judge_reread"]
    placeholder_checks(out, ex, repo)


def test_jdg_ac14_a_reread_the_guard_discards_is_an_unparsed_judgement(repo: Path) -> None:  # AC 3, AC 6
    outside = judge(CLEAN, tools=("Read", "Write"))
    out, ex = drive(repo, [PARTIAL_FIRST, outside], steps=1)
    assert request_kinds(ex)[:3] == ["step", "judge", "judge_reread"]
    placeholder_checks(out, ex, repo)
    (rec,) = [r for r in records(repo) if r["kind"] == "judgement"]
    assert rec["guard"] == "discarded"


def test_jdg_ac14_a_reread_with_no_block_after_its_reask_is_an_unparsed_judgement(repo: Path) -> None:  # AC 3
    out, ex = drive(repo, [PARTIAL_FIRST, judge("no block"), judge("still none")], steps=1)
    assert request_kinds(ex)[:4] == ["step", "judge", "judge_reread", "judge_reask"]
    assert request_kinds(ex).count("judge_reread") == 1 and request_kinds(ex).count("judge") == 1
    placeholder_checks(out, ex, repo)


def test_jdg_ac14_a_reread_with_no_block_is_derived_from_its_reask(repo: Path) -> None:  # AC 3
    out, ex = drive(repo, [PARTIAL_FIRST, judge("no block"), judge(CLEAN)], steps=2)
    assert request_kinds(ex)[:4] == ["step", "judge", "judge_reread", "judge_reask"]
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert request_kinds(ex)[4] == "step"  # the next unit's step, no retry of this one


def test_jdg_ac14_a_first_session_the_guard_discards_starts_no_reread(repo: Path) -> None:  # AC 3
    out, ex = drive(repo, [judge(PARTIAL_FIRST, tools=("Read", "Write"))], steps=1)
    assert "judge_reread" not in request_kinds(ex)
    assert out.exit_code is ExitCode.PAUSED


def test_jdg_ac14_an_infra_failure_of_the_reread_ends_the_attempt_as_judge_infra(repo: Path) -> None:  # AC 3
    from tempergraph.contracts import InfraCause, SessionResult, Usage

    broken = SessionResult(ok=False, infra_cause=InfraCause.BROKEN_PIPE, usage=Usage())
    ex = standin("claude", steps=[DRAFT] * 4, judges=[judge(PARTIAL_FIRST), broken, broken, broken] * 4)
    out = go(repo, ex, two_blockers())
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "infra"
    assert not [r for r in records(repo) if r["kind"] == "judgement"]
    assert "retry" not in request_kinds(ex)
    assert set(request_kinds(ex)) <= {"step", "judge", "judge_reread"}


def _failure(name: str) -> list[Any]:
    """The answers of one judge session that fails in the way `name` says (a JDG-B2 re-ask follows a missing block)."""
    from tempergraph.contracts import InfraCause, SessionResult, Usage

    broken = SessionResult(ok=False, infra_cause=InfraCause.BROKEN_PIPE, usage=Usage())
    return {
        "timeout": [dataclasses.replace(judge(CLEAN), timed_out=True, ok=False)],
        "unparsed": [judge("no block"), judge("still none")],
        "guard": [judge(CLEAN, tools=("Read", "Write"))],
        "infra": [broken] * 12,
    }[name]


@pytest.mark.parametrize("name", ["timeout", "unparsed", "guard", "infra"])
@pytest.mark.parametrize("where", ["first", "reread"])
def test_jdg_ac4_no_judging_failure_ever_yields_proceed(repo: Path, where: str, name: str) -> None:  # JDG-AC4, AC 3
    answers = _failure(name) if where == "first" else [judge(PARTIAL_FIRST)] + _failure(name)
    out, ex = drive(repo, answers, steps=1)
    assert out.exit_code is not ExitCode.FINISHED, out.message
    expected = ExitCode.BUDGET_OR_INFRA if name == "infra" else ExitCode.PAUSED
    assert out.exit_code is expected
    assert request_kinds(ex).count("step") == 1 and "retry" not in request_kinds(ex)
    if where == "first":
        assert "judge_reread" not in request_kinds(ex)


def test_jdg_ac9_a_reread_runs_on_the_risk_rules_model_with_one_risk_record(repo: Path) -> None:  # JDG-AC9, AC 6
    from tempergraph.api import Risk
    from tempergraph.executors.standins import standin as make
    from tempergraph.run.runner import RunSettings, start

    from .test_judge_risk import LEVELS, always_code, recs, wf, writes
    from .test_run import registry

    first = block([("MET", False, "")], gap=True, gap_unread=True, summary="open notes.md")
    clean = block([("MET", False, "")])
    ex = make("claude", steps=[writes("src/x.py")], judges=[judge(first), judge(clean)])
    out = start(wf(Risk(levels=LEVELS, rule=always_code)), "R-1", {"request": "x"}, repo, registry(ex),
                RunSettings(sleep=lambda s: None))
    assert out.exit_code is ExitCode.FINISHED, out.message
    one, two = [c for c in ex.calls if c.kind in ("judge", "judge_reread")]
    assert two.request.kind == "judge_reread"
    assert (one.request.alias, two.request.alias) == ("large", "large")
    assert one.views is not None and two.views is not None and one.views.tools == two.views.tools
    assert len(recs(repo, "judge_risk")) == 1


# -- the re-read in the records, the counts and the cost (JDG-B22 to JDG-B24; JDG-AC15; AC 5) ------------------------

MARKED_FIRST = block([("MET", False, ""), ("PARTIAL", True, "open notes.md lines 1-9")], gap=True, gap_unread=True,
                     summary="open notes.md")


def reread_run(repo: Path) -> tuple[Any, ScriptedExecutor]:
    return drive(repo, [MARKED_FIRST, CLEAN], steps=2)


def test_jdg_ac15_the_reread_has_its_own_agent_run_folder_and_cost(repo: Path) -> None:  # AC 5
    out, ex = reread_run(repo)
    assert out.exit_code is ExitCode.FINISHED, out.message
    runs = [r for r in records(repo) if r["kind"] == "agent_run"]
    (own,) = [r for r in runs if r["session_kind"] == "judge_reread"]
    assert own["session_key"].endswith("draft.1.judge_reread") and own["usage"]
    assert len({r["session_key"] for r in runs}) == len(runs)
    keys = {r["session_key"] for r in runs if r["session_kind"] in ("judge", "judge_reread")
            and r["session_key"].startswith("draft.")}
    assert keys == {"draft.1.judge", "draft.1.judge_reread"}
    exit_rec = [r for r in records(repo) if r["kind"] == "run_exit"][0]
    assert exit_rec["cost_so_far"]["reported"] == pytest.approx(0.01 * len(runs))


def test_jdg_ac15_the_judgement_record_says_reread_with_criteria_and_gap(repo: Path) -> None:  # AC 5
    reread_run(repo)
    first = [r for r in records(repo) if r["kind"] == "judgement"][0]
    assert first["reread"] == {"criteria": ["c-two"], "gap": True}
    assert first["gap"] is False and first["blockers"] == []  # the re-read's judgement fills the other fields


def test_jdg_ac15_a_reread_with_a_criterion_without_an_id_names_its_number(repo: Path) -> None:  # AC 5
    spec = two_step()  # one criterion, read as number 1 when it has no id
    units = dict(spec.units)
    gate = units["draft"].gate
    units["draft"] = dataclasses.replace(units["draft"], gate=dataclasses.replace(
        gate, criteria=(dataclasses.replace(gate.criteria[0], id=None),)))
    spec = dataclasses.replace(spec, units=units)
    first = block([("PARTIAL", True, "open notes.md")])
    ex = standin("claude", steps=[DRAFT] * 2 + [REVIEW] * 2, judges=[judge(first), judge(block([("MET", False, "")]))]
                 + [judge(CLEAN)] * 4)
    go(repo, ex, spec)
    assert [r for r in records(repo) if r["kind"] == "judgement"][0]["reread"] == {"criteria": [1], "gap": False}


def test_jdg_ac15_an_attempt_with_no_reread_has_no_reread_key(repo: Path) -> None:  # AC 5
    drive(repo, [CLEAN, CLEAN], steps=2)
    judgements = [r for r in records(repo) if r["kind"] == "judgement"]
    assert judgements and all("reread" not in r for r in judgements)


def test_jdg_ac15_the_report_counts_the_reread_with_the_judges_sessions(repo: Path) -> None:  # AC 5
    from tempergraph.observe import report as rep
    from tempergraph.store.layout import state_root_path

    reread_run(repo)
    runs = [r for r in records(repo) if r["kind"] == "agent_run"]
    judges = [r for r in runs if r["session_kind"] in ("judge", "judge_reask", "judge_reread")]
    doc = rep.report(state_root_path(repo), None)
    assert doc["steps_and_judges"]["judges"]["sessions"] == len(judges)
    assert doc["steps_and_judges"]["steps"]["sessions"] == len(runs) - len(judges)
    thread = rep.fold(records(repo))
    assert thread is not None
    assert [s.cause for s in thread.sessions if s.kind == "judge_reread"] == ["re-read"]


def test_jdg_ac15_the_detail_document_files_the_reread_with_the_judge_sessions(repo: Path) -> None:  # AC 5
    from tempergraph.observe.detail import detail
    from tempergraph.store.layout import state_root_path

    reread_run(repo)
    doc = detail(state_root_path(repo), two_blockers(), "demo/T-1")
    assert doc is not None
    att = doc["units"][0]["visits"][0]["attempts"][0]
    assert [s["kind"] for s in att["judge"]["sessions"]] == ["judge", "judge_reread"]
    assert [s["kind"] for s in att["step"]["sessions"]] == ["step"]


def test_los_ac1_a_run_with_a_reread_has_the_stated_session_folders(repo: Path) -> None:  # LOS-AC1, AC 5
    import os
    import sys

    from tempergraph.store.layout import run_dir, state_root_path

    reread_run(repo)
    sessions = run_dir(state_root_path(repo), "demo", "T-1") / "sessions"
    names = sorted(p.name for p in sessions.iterdir() if p.name.startswith("draft."))
    assert names == ["draft.1.judge", "draft.1.judge_reread", "draft.1.step"]
    for name in names:
        folder = sessions / name
        assert (folder / "meta.json").is_file(), name  # the stand-in executor writes no raw.jsonl
        if sys.platform != "win32":
            for p in [folder, *folder.iterdir()]:
                assert os.stat(p).st_mode & 0o077 == 0, p


def test_obs_ac4_only_agent_run_records_count_as_model_calls_and_the_reread_has_its_fields(repo: Path) -> None:  # OBS-AC4, AC 5
    from tempergraph.observe import report as rep
    from tempergraph.store.layout import state_root_path

    _, ex = reread_run(repo)
    runs = [r for r in records(repo) if r["kind"] == "agent_run"]
    assert len(runs) == len(ex.calls)  # one record for every model call: step, judge and judge_reread
    doc = rep.report(state_root_path(repo), None)
    sj = doc["steps_and_judges"]
    assert sj["steps"]["sessions"] + sj["judges"]["sessions"] == len(runs)
    (own,) = [r for r in runs if r["session_kind"] == "judge_reread"]
    for field in ("session_key", "session_kind", "alias", "usage", "unit", "attempt"):
        assert own.get(field) not in (None, "", {}), field
    assert own["alias"] == [r for r in runs if r["session_kind"] == "judge"][0]["alias"]


def test_ssn_ac2_the_reread_request_holds_the_fields_of_a_session_request(repo: Path) -> None:  # SSN-AC2, AC 5
    from tempergraph.executors.claude import judge_argv

    _, ex = reread_run(repo)
    call = [c for c in ex.calls if c.request.kind == "judge_reread"][0]
    req = call.request
    assert req.kind == "judge_reread" and req.prompt.strip() and req.workdir.is_absolute()
    assert req.alias and req.timeout_s > 0 and req.options is not None
    assert isinstance(req.tools, tuple) and isinstance(req.commands, tuple)
    assert req.session_key.endswith("draft.1.judge_reread")
    assert call.views is not None and call.views.tools
    argv = judge_argv(call.views, None, isolated=False)
    assert not any(req.prompt in a or a in req.prompt and len(a) > 40 for a in argv)


def test_jdg_ac15_the_digest_knows_the_reread_as_a_judge_kind() -> None:  # AC 5
    from tempergraph.improve import digest

    assert "judge_reread" in digest.KINDS and "judge_reread" in digest.JUDGE_KINDS
