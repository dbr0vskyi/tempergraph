"""A session the account's usage limit ends is read, logged and charged to nothing (BUD-AC15, EVT-AC9; task AC 1,
AC 4, AC 7)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.contracts import InfraCause, SessionResult, Usage
from tempergraph.executors.standins import standin
from tempergraph.run.runner import resume
from tempergraph.store.layout import state_root_path

from .fixtures.workflows import two_step
from .test_council_run import UNIT, Crew, council_wf
from .test_council_run import go as council_go
from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, records, registry


def refused(resets_at: float | None, **kw: Any) -> SessionResult:
    return SessionResult(ok=False, usage_limit=True, usage_limit_resets_at=resets_at, usage=Usage(), **kw)


def values(repo: Path, spec: Any, task: str) -> dict[str, Any]:
    from tempergraph.durability.checkpoint import observer_graph, open_readonly, snapshot
    from tempergraph.run.outcome import with_outcome

    with open_readonly(state_root_path(repo) / "checkpoints" / "demo.sqlite") as saver:
        assert saver is not None
        return dict(snapshot(observer_graph(with_outcome(spec), saver), f"demo/{task}").values)


def spent(vals: dict[str, Any], unit: str = "draft") -> tuple[int, int]:
    c = (vals.get("counters") or {}).get(unit) or {}
    return int(c.get("retries", 0)), int(c.get("infra", 0))


@pytest.mark.parametrize("flavour", [{"error_kind": "model"}, {"infra_cause": InfraCause.THROTTLED}])
def test_bud_ac15_a_refused_step_spends_no_retry_and_no_infra_try(repo: Path, flavour: dict[str, Any]) -> None:
    # BUD-AC15, EVT-AC9 (task AC 1, AC 4)
    at = time.time() + 3600
    ex = standin("claude", steps=[refused(at, **flavour)] * 3)
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert [c.kind for c in ex.calls] == ["step"]  # no infra rerun, no backoff
    vals = values(repo, two_step(), "T-1")
    assert spent(vals) == (0, 0)
    att = vals["attempts"]["draft"]
    assert att["escalate"] == "usage_limit" and att["infra_spent"] is False
    assert att["usage_limit_resets_at"] == at
    run = [r for r in records(repo) if r["kind"] == "agent_run"]
    assert len(run) == 1 and run[0]["usage_limit"] is True and run[0]["usage_limit_resets_at"] == at
    assert run[0]["error_kind"] == flavour.get("error_kind")  # the executor's own value stays


def test_evt_ac9_an_ok_session_records_no_limit(repo: Path) -> None:  # EVT-AC9 (task AC 4)
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    runs = [r for r in records(repo) if r["kind"] == "agent_run"]
    assert runs and all(r["usage_limit"] is False and r["usage_limit_resets_at"] is None for r in runs)


def test_bud_ac15_a_failure_without_the_limit_is_counted_as_before(repo: Path) -> None:  # BUD-AC15 (task AC 7)
    failed = SessionResult(ok=False, error_kind="model", usage=Usage())
    ex = standin("claude", steps=[failed, DRAFT, REVIEW], judges=[judge(), judge()])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [c.request.kind for c in ex.calls][:2] == ["step", "retry"]  # the retry was spent
    assert all(r["usage_limit"] is False for r in records(repo) if r["kind"] == "agent_run")


def test_bud_ac15_a_throttled_session_without_the_limit_is_rerun_until_infra_is_spent(repo: Path) -> None:
    # BUD-AC15 (task AC 7)
    throttled = SessionResult(ok=False, infra_cause=InfraCause.THROTTLED, usage_limit=False, usage=Usage())
    ex = standin("claude", steps=[throttled] * 3)
    out = go(repo, ex)
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "infra"
    assert len(ex.calls) == 3


def test_bud_ac15_a_refused_council_member_is_not_a_missing_answer(repo: Path) -> None:  # BUD-AC15 (task AC 1)
    at = time.time() + 3600
    ex = Crew({("b", 0): [refused(at, error_kind="model")]})
    out = council_go(repo, council_wf(), ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    vals = values(repo, council_wf(), "C-1")
    assert spent(vals, UNIT) == (0, 0)
    att = vals["attempts"][UNIT]
    assert att["escalate"] == "usage_limit" and att["infra_spent"] is False and att["usage_limit_resets_at"] == at
    assert att["ok"] is False and not ex.of("chair")  # no tally and no chair on a refused round


def _judge_refused_checks(repo: Path, ex: Any, at: float) -> None:
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert not [r for r in records(repo) if r["kind"] == "judgement"]  # no verdict is derived
    vals = values(repo, two_step(), "T-1")
    j = vals["judgements"]["draft"]
    assert j["verdict"] == "ESCALATE" and j["reason"] == "usage_limit"
    assert j["confidence"] == 1.0 and j["confidence_source"] == "engine_placeholder"
    assert spent(vals) == (0, 0)
    att = vals["attempts"]["draft"]
    assert att["escalate"] == "usage_limit" and att["usage_limit_resets_at"] == at
    assert att["usage_limit_stage"] == "judge" and not att.get("infra_spent")


def test_jdg_ac9_a_refused_judge_session_derives_no_verdict(repo: Path) -> None:
    # JDG-AC9, BUD-AC15 (task AC 1, AC 6)
    at = time.time() + 3600
    ex = standin("claude", steps=[DRAFT], judges=[refused(at, error_kind="model")] * 3)
    _judge_refused_checks(repo, ex, at)
    assert [c.request.kind for c in ex.calls] == ["step", "judge"]  # no re-ask, no backoff rerun


def test_jdg_ac9_a_refused_judge_throttled_is_not_rerun(repo: Path) -> None:  # JDG-AC9 (task AC 6)
    at = time.time() + 3600
    ex = standin("claude", steps=[DRAFT], judges=[refused(at, infra_cause=InfraCause.THROTTLED)] * 3)
    _judge_refused_checks(repo, ex, at)
    assert [c.request.kind for c in ex.calls] == ["step", "judge"]


def test_jdg_ac9_a_refused_reask_derives_no_verdict(repo: Path) -> None:  # JDG-AC9, BUD-AC15 (task AC 6)
    at = time.time() + 3600
    ex = standin("claude", steps=[DRAFT], judges=[judge("no block"), refused(at)])
    _judge_refused_checks(repo, ex, at)
    assert [c.request.kind for c in ex.calls] == ["step", "judge", "judge_reask"]


def test_jdg_ac9_a_refused_step_starts_no_judge_session(repo: Path) -> None:  # JDG-AC9 (task AC 6)
    at = time.time() + 3600
    ex = standin("claude", steps=[refused(at, error_kind="model")], judges=[judge()])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert [c.request.kind for c in ex.calls] == ["step"]
    vals = values(repo, two_step(), "T-1")
    j = vals["judgements"]["draft"]
    assert j["verdict"] == "ESCALATE" and j["reason"] == "usage_limit"  # not RETRY
    assert spent(vals) == (0, 0)


def test_bud_ac15_a_refused_chair_spends_nothing(repo: Path) -> None:  # BUD-AC15 (task AC 1)
    at = time.time() + 3600
    ex = Crew(chair=refused(at))
    out = council_go(repo, council_wf(), ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    vals = values(repo, council_wf(), "C-1")
    assert spent(vals, UNIT) == (0, 0)
    att = vals["attempts"][UNIT]
    assert att["escalate"] == "usage_limit" and att["infra_spent"] is False and att["usage_limit_resets_at"] == at


# ---- phase 3: the pause carries the reset instant to every reader


def _pause_payload(repo: Path, task: str = "T-1") -> dict[str, Any]:
    from tempergraph.durability.checkpoint import observer_graph, open_readonly, snapshot
    from tempergraph.run.outcome import with_outcome

    with open_readonly(state_root_path(repo) / "checkpoints" / "demo.sqlite") as saver:
        assert saver is not None
        snap = snapshot(observer_graph(with_outcome(two_step()), saver), f"demo/{task}")
    (_, payload), *_ = snap.interrupts
    return dict(payload)


@pytest.mark.parametrize("stage", ["step", "judge"])
@pytest.mark.parametrize("given", [True, False])
def test_hum_ac10_a_refused_session_pauses_with_the_reset_instant(repo: Path, stage: str, given: bool) -> None:
    # HUM-AC10 (task AC 2)
    at = time.time() + 3600 if given else None
    if stage == "step":
        ex = standin("claude", steps=[refused(at, error_kind="model")], judges=[judge()])
    else:
        ex = standin("claude", steps=[DRAFT], judges=[refused(at)])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert spent(values(repo, two_step(), "T-1")) == (0, 0)
    p = _pause_payload(repo)
    assert p["kind"] == "escalation" and p["reason"] == "usage_limit"
    assert p["usage_limit_resets_at"] == at
    assert p["resume"] == "tempergraph resume demo T-1" and "--decision" not in p["resume"]


def _pause_record(repo: Path, task: str = "T-1") -> dict[str, Any]:
    return [r for r in records(repo, task) if r["kind"] == "pause"][-1]


def test_evt_ac10_the_pause_record_status_row_and_detail_carry_the_instant(repo: Path) -> None:
    # EVT-AC10, DUR-AC11, RDD-AC11 (task AC 2, AC 8)
    from tempergraph.durability.status import row
    from tempergraph.observe.detail import detail

    at = time.time() + 3600
    out = go(repo, standin("claude", steps=[refused(at)]))
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert _pause_record(repo)["usage_limit_resets_at"] == at
    r = row(state_root_path(repo), two_step(), "demo/T-1")
    assert r["usage_limit_resets_at"] == at
    assert r["pending_gates"][0]["usage_limit_resets_at"] == at
    doc = detail(state_root_path(repo), two_step(), "demo/T-1")
    assert doc is not None and doc["pause"]["usage_limit_resets_at"] == at


def test_dur_ac11_a_null_instant_is_kept_as_null(repo: Path) -> None:  # DUR-AC11, EVT-AC10 (task AC 2)
    from tempergraph.durability.status import row

    assert go(repo, standin("claude", steps=[refused(None)])).exit_code is ExitCode.PAUSED
    assert _pause_record(repo)["usage_limit_resets_at"] is None
    r = row(state_root_path(repo), two_step(), "demo/T-1")
    assert "usage_limit_resets_at" in r and r["usage_limit_resets_at"] is None


def test_dur_ac11_the_row_holds_the_latest_reset_of_two_pending_gates(repo: Path) -> None:
    # DUR-AC11 (task AC 2)
    from tempergraph.durability.status import row

    from .test_parallel import ByUnit, wf
    from .test_parallel import go as pgo

    early, late = time.time() + 3600, time.time() + 7200

    class Limited(ByUnit):
        def run_step(self, req: Any, sink: Any) -> SessionResult:
            unit = req.session_key.split(".")[0]
            if unit in ("security", "perf"):
                self.calls.append(("step", unit))
                return refused(early if unit == "security" else late)
            return super().run_step(req, sink)

    spec = wf()
    out = pgo(repo, spec, Limited())
    assert out.exit_code is ExitCode.PAUSED, out.message
    r = row(state_root_path(repo), spec, "demo/P-1")
    assert sorted(g["unit"] for g in r["pending_gates"]) == ["perf", "security"]
    assert r["usage_limit_resets_at"] == late


def _plain(repo: Path, ex: Any, spec: Any = None, task: str = "T-1", **kw: Any) -> Any:
    """`resume` with no decision."""
    return resume(spec or two_step(), task, repo, registry(ex), settings=NO_SLEEP, **kw)


def _rows(repo: Path) -> list[dict[str, Any]]:
    path = state_root_path(repo) / "ledger.jsonl"
    return [r for r in map(json.loads, path.read_text().splitlines()) if r["kind"] == "intervention"]


def test_dur_ac10_three_refused_sessions_spend_nothing_and_keep_the_attempt(repo: Path) -> None:
    # DUR-AC10, BUD-AC15 (task AC 3, AC 5)
    at = time.time() + 3600
    ex = standin("claude", steps=[refused(at, error_kind="model")] * 3 + [DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    first = _plain(repo, ex)  # before the reset instant: not refused
    assert first.exit_code is ExitCode.PAUSED, first.message
    second = _plain(repo, ex)
    assert second.exit_code is ExitCode.PAUSED and second.reason != "budget", second.message
    assert [c.kind for c in ex.calls] == ["step"] * 3
    vals = values(repo, two_step(), "T-1")
    assert spent(vals) == (0, 0)  # the retry counter is 0 after three refused sessions of a budget of 2
    assert _pause_payload(repo)["reason"] == "usage_limit"
    keys = [r["session_key"] for r in records(repo) if r["kind"] == "agent_run"]
    assert len(keys) == 3 and len(set(keys)) == 1 and keys[0] == "draft.1.step"
    rows = _rows(repo)
    assert len(rows) == 2 and all(r["decision"] == "" and r["touches"] == [{"class": "rescue", "action": "decide"}]
                                  and r["pause_kind"] == "escalation" for r in rows)
    assert len([r for r in records(repo) if r["kind"] == "unit_entered"]) == 1  # no second entry record
    ok = _plain(repo, ex)  # the fourth session is ok and goes on to the judge
    assert ok.exit_code is ExitCode.FINISHED, ok.message
    assert [c.kind for c in ex.calls] == ["step"] * 4 + ["judge", "step", "judge"]
    assert len(_rows(repo)) == 3 and spent(values(repo, two_step(), "T-1")) == (0, 0)


def test_dur_ac10_a_judge_the_limit_ended_reruns_without_its_step(repo: Path) -> None:  # DUR-AC10, JDG-AC9 (AC 6)
    at = time.time() + 3600
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[refused(at), judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    out = _plain(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [c.kind for c in ex.calls] == ["step", "judge", "judge", "step", "judge"]  # the step is not run again
    keys = [r["session_key"] for r in records(repo) if r["kind"] == "agent_run" and r["session_key"].startswith("draft")]
    assert keys == ["draft.1.step", "draft.1.judge", "draft.1.judge"]
    assert [r["verdict"] for r in records(repo) if r["kind"] == "gate"][:2] == ["ESCALATE", "PROCEED"]
    assert spent(values(repo, two_step(), "T-1")) == (0, 0)


def test_dur_ac10_a_refused_reask_reruns_the_judge_session(repo: Path) -> None:  # DUR-AC10, JDG-AC9 (AC 6)
    at = time.time() + 3600
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge("no block"), refused(at), judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    out = _plain(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [c.request.kind for c in ex.calls] == ["step", "judge", "judge_reask", "judge", "step", "judge"]


def test_dur_ac10_a_refused_retry_reruns_with_the_same_blockers(repo: Path) -> None:  # DUR-AC10 (task AC 3)
    from .test_run import verdict_block

    at = time.time() + 3600
    ex = standin("claude", steps=[DRAFT, refused(at, error_kind="model"), DRAFT, REVIEW],
                 judges=[judge(verdict_block("UNMET")), judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    assert spent(values(repo, two_step(), "T-1")) == (1, 0)  # the first attempt's retry, spent before the refusal
    out = _plain(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [c.request.kind for c in ex.calls][:4] == ["step", "judge", "retry", "retry"]
    refused_call, rerun = ex.calls[2].request, ex.calls[3].request
    assert refused_call.session_key == rerun.session_key == "draft.2.retry"
    assert "The previous attempt was not accepted" in rerun.prompt and "c-file" in rerun.prompt
    assert rerun.prompt == refused_call.prompt
    assert spent(values(repo, two_step(), "T-1")) == (1, 0)  # the refusal and its rerun spent nothing more


def test_dur_ac10_a_refused_attempt_keeps_the_feedback_it_was_given(repo: Path) -> None:  # DUR-AC10 (task AC 3)
    from .test_run import verdict_block

    at = time.time() + 3600
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    ex.steps, ex.judges = [refused(at), DRAFT, REVIEW], [judge(), judge()]
    out = resume(two_step(), "T-1", repo, registry(ex), decision="retry", feedback="use bullets", settings=NO_SLEEP)
    assert out.exit_code is ExitCode.PAUSED and _pause_payload(repo)["reason"] == "usage_limit", out.message
    out = _plain(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [c.request.kind for c in ex.calls][:4] == ["step", "judge", "retry", "retry"]
    refused_call, rerun = ex.calls[2].request, ex.calls[3].request
    assert refused_call.session_key == rerun.session_key and "use bullets" in rerun.prompt
    assert rerun.prompt == refused_call.prompt


def test_rrn_b19_a_plain_resume_with_feedback_is_still_refused(repo: Path) -> None:  # DUR-AC10, RRN-B19
    ex = standin("claude", steps=[refused(time.time() + 3600)])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    out = _plain(repo, ex, feedback="try again")
    assert out.exit_code is ExitCode.USAGE and len(ex.calls) == 1 and not _rows(repo)


def test_dur_ac10_proceed_is_accepted_at_a_usage_limit_pause(repo: Path) -> None:  # DUR-AC10
    ex = standin("claude", steps=[refused(time.time() + 3600), REVIEW], judges=[judge()])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    out = resume(two_step(), "T-1", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert out.exit_code is not ExitCode.USAGE, out.message
    assert _rows(repo)[0]["decision"] == "proceed"


def test_dur_ac10_a_plain_resume_at_another_pause_is_still_refused(repo: Path) -> None:  # DUR-AC10
    from .test_run import verdict_block

    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    out = _plain(repo, ex)
    assert out.exit_code is ExitCode.USAGE and "--decision" in out.message


def test_dur_ac10_a_refused_council_attempt_reruns_under_its_attempt_number(repo: Path) -> None:  # DUR-AC10 (AC 3)
    at = time.time() + 3600
    ex = Crew({("b", 0): [refused(at, error_kind="model")]})
    assert council_go(repo, council_wf(), ex).exit_code is ExitCode.PAUSED
    out = _plain(repo, ex, council_wf(), "C-1")
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert sorted(ex.sessions) == sorted([f"{UNIT}.1.member.{n}.0" for n in "abc"] + [f"{UNIT}.1.chair", f"{UNIT}.1.judge"])
    assert spent(values(repo, council_wf(), "C-1"), UNIT) == (0, 0)


def test_bud_ac15_a_council_rerun_runs_only_the_refused_session(repo: Path) -> None:  # BUD-AC15 (task AC 3)
    at = time.time() + 3600
    ex = Crew({("b", 0): [refused(at, error_kind="model")]})
    assert council_go(repo, council_wf(), ex).exit_code is ExitCode.PAUSED
    before = len(ex.requests)
    assert _plain(repo, ex, council_wf(), "C-1").exit_code is ExitCode.FINISHED
    rerun = [r.session_key for r in ex.requests[before:] if r.kind in ("member", "member_reask")]
    assert rerun == [f"{UNIT}.1.member.b.0"]  # a and c ended ok and are taken from their kept results
    assert ex.sessions[f"{UNIT}.1.member.a.0"] == 1 and ex.sessions[f"{UNIT}.1.member.c.0"] == 1


def test_dur_ac11_an_approval_pause_carries_no_instant(repo: Path) -> None:  # EVT-AC10, DUR-AC11, RDD-AC11
    import dataclasses

    from tempergraph.durability.status import row
    from tempergraph.observe.detail import detail

    spec = two_step()
    units = dict(spec.units)
    units["draft"] = dataclasses.replace(units["draft"], gate=dataclasses.replace(units["draft"].gate, approval=True))
    spec = dataclasses.replace(spec, units=units)
    out = go(repo, standin("claude", steps=[DRAFT], judges=[judge()]), spec)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert "usage_limit_resets_at" not in _pause_record(repo)
    r = row(state_root_path(repo), spec, "demo/T-1")
    assert "usage_limit_resets_at" not in r
    assert all("usage_limit_resets_at" not in g for g in r["pending_gates"])
    doc = detail(state_root_path(repo), spec, "demo/T-1")
    assert doc is not None and "usage_limit_resets_at" not in doc["pause"]
