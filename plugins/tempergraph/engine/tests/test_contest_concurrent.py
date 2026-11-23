"""A contest runs `concurrency` slots at once and never one more, the next starting when one ends (CTS-AC5; CTS-B6)."""

from __future__ import annotations

from pathlib import Path

from tempergraph.constants import ExitCode

from .test_contest_run import BySlot, contest_spec, go


def steps_in_time(ex: BySlot) -> tuple[dict[str, float], dict[str, float]]:
    started = {s: t for e, k, s, t in ex.timeline if e == "start" and k == "step"}
    ended = {s: t for e, k, s, t in ex.timeline if e == "end" and k == "step"}
    return started, ended


def test_two_slots_run_at_once_and_never_a_third_CTS_AC5(repo: Path) -> None:  # CTS-AC5 (CTS-B6)
    ex = BySlot(hold_s=0.15)
    out = go(repo, contest_spec(slots=3, concurrency=2, then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.sessions["step.s1"] == ex.sessions["step.s2"] == ex.sessions["step.s3"] == 1  # every slot runs
    started, ended = steps_in_time(ex)
    assert ex.peak == 2, ex.peak  # two sessions open at once, never a third
    assert started["s3"] >= min(ended["s1"], ended["s2"])  # the third starts when one of them ends


def test_a_concurrency_of_one_runs_the_slots_one_at_a_time_CTS_AC5(repo: Path) -> None:  # CTS-AC5 (CTS-B6)
    ex = BySlot(hold_s=0.05)
    out = go(repo, contest_spec(slots=3, concurrency=1, then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    started, ended = steps_in_time(ex)
    assert ex.peak == 1
    assert started["s2"] >= ended["s1"] and started["s3"] >= ended["s2"]  # in the order of the slots
    assert [s for e, k, s, _ in ex.timeline if e == "start" and k == "step"] == ["s1", "s2", "s3"]


def test_a_concurrency_above_the_slot_count_runs_every_slot_at_once_CTS_AC5(repo: Path) -> None:  # CTS-AC5 (CTS-B6)
    ex = BySlot(hold_s=0.15)
    out = go(repo, contest_spec(slots=3, concurrency=5, then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.peak == 3
