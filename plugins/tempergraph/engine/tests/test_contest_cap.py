"""A contest skips the slots it has not started once the attempt's cost has reached `cost_cap_usd` (CTS-AC5, AC 5; CTS-B6)."""

from __future__ import annotations

from pathlib import Path

from tempergraph.constants import ExitCode

from .test_contest_run import BySlot, contest_spec, go, recs


def test_slots_that_would_start_after_the_cap_is_reached_never_start_CTS_AC5(repo: Path) -> None:  # AC 5, CTS-AC5 (CTS-B6)
    ex = BySlot(step_cost=0.30)
    out = go(repo, contest_spec(slots=3, concurrency=1, cost_cap_usd=0.40, then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.sessions.get("step.s1") == 1 and ex.sessions.get("step.s2") == 1  # 0.30, then 0.60: the cap is reached
    assert "step.s3" not in ex.sessions and "judge.s3" not in ex.sessions  # `s3` never starts: it has no session
    assert not [r for r in ex.requests if r.session_key.startswith("pick.s3.")]
    (rec,) = recs(repo, "contest")
    by = {s["name"]: s for s in rec["slots"]}
    assert by["s3"] == {"slot": 3, "name": "s3", "skipped": True}  # recorded as skipped, with no check, verdict or cost
    assert by["s1"]["verdict"] == "PROCEED" and by["s2"]["verdict"] == "PROCEED" and rec["winner"] in (1, 2)
    started = [r["session_key"] for r in recs(repo, "attempt_start") if r["session_key"].startswith("pick.s3")]
    assert started == []


def test_a_cap_not_yet_reached_leaves_every_slot_to_run_AC_5(repo: Path) -> None:  # AC 5 (CTS-B6)
    ex = BySlot(step_cost=0.10)
    out = go(repo, contest_spec(slots=3, concurrency=1, cost_cap_usd=0.40, then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert {k for k in ex.sessions if k.startswith("step.")} == {"step.s1", "step.s2", "step.s3"}
    (rec,) = recs(repo, "contest")
    assert not [s for s in rec["slots"] if s.get("skipped")]


def test_slots_that_run_at_once_are_not_stopped_by_each_other_AC_5(repo: Path) -> None:  # AC 5 (CTS-B6)
    ex = BySlot(step_cost=0.30, hold_s=0.1)
    out = go(repo, contest_spec(slots=3, concurrency=3, cost_cap_usd=0.40, then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert {k for k in ex.sessions if k.startswith("step.")} == {"step.s1", "step.s2", "step.s3"}  # all three started at 0
