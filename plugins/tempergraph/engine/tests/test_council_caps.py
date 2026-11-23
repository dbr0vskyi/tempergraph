"""The council's own cost cap, and the run's cost cap through the reservations of a council's sessions
(CNL-B8, CNL-AC7, BUD-B9, BUD-B12 to BUD-B15, BUD-AC12 to BUD-AC14; task AC 5)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.store.layout import run_dir, state_root_path

from .test_council_run import UNIT, Crew, council_wf, go, recs

CAP = 5.0


def capped(spec: Any, cap: float) -> Any:
    return dataclasses.replace(spec, run_cost_cap_usd=cap)


def log(repo: Path) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", "C-1") / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def per_session(amount: float) -> dict[str, Any]:
    return {"flags": {"steps.session_cost_cap_usd": amount}}


def test_cnl_ac7_the_councils_own_cost_cap_starts_no_new_member_session_and_ends_the_attempt_cap_reached(repo: Path) -> None:  # CNL-AC7 (CNL-B8)
    ex = Crew(cost=1.0)
    spec = council_wf(("a", "b"), rounds=1, cost_cap_usd=2.0)
    units = dict(spec.units)
    units[UNIT] = dataclasses.replace(units[UNIT], gate=dataclasses.replace(units[UNIT].gate, retry_budget=0))
    out = go(repo, dataclasses.replace(spec, units=units), ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget", out.message
    assert out.payload["blockers"][0]["problem"] == "cap_reached"
    assert sorted(k for k in ex.sessions if ".member." in k) == [f"{UNIT}.1.member.{n}.0" for n in "ab"]  # round 1 never started
    assert not ex.of("chair") and not ex.of("judge")


def test_the_councils_cap_lets_the_running_sessions_finish(repo: Path) -> None:  # CNL-AC7 (CNL-B8)
    ex = Crew(cost=1.0, hold_s=0.1)
    spec = council_wf(("a", "b", "c"), cost_cap_usd=0.5)  # reached by the first session to end, while the others run
    units = dict(spec.units)
    units[UNIT] = dataclasses.replace(units[UNIT], gate=dataclasses.replace(units[UNIT].gate, retry_budget=0))
    out = go(repo, dataclasses.replace(spec, units=units), ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["blockers"][0]["problem"] == "cap_reached", out.message
    assert all(n == 1 for n in ex.sessions.values()) and len(ex.of("member")) == 3  # all three ran: none was cut off


def test_bud_ac12_a_council_member_reserves_the_share_of_the_remaining_cap(repo: Path) -> None:  # BUD-AC12 (BUD-B13)
    ex = Crew(cost=0.1, hold_s=0.05)
    out = go(repo, capped(council_wf(), 6.0), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    rows = log(repo)
    for n in "abc":
        key = f"{UNIT}.1.member.{n}.0"
        held = next(i for i, r in enumerate(rows) if r["kind"] == "reservation" and r["session_key"] == key)
        start = next(i for i, r in enumerate(rows) if r["kind"] == "attempt_start" and r["session_key"] == key)
        assert held < start  # the reservation comes before the session's first attempt_start record
        r = rows[held]
        assert (r["action"], r["source"], r["reserved_usd"], r["cap_usd"]) == ("held", "share", 2.0, 6.0)  # 6.00 over 3 members
    chair = next(r for r in rows if r["kind"] == "reservation" and r["session_key"] == f"{UNIT}.1.chair")
    assert chair["action"] == "held" and chair["source"] == "share" and chair["reserved_usd"] > 0  # alone: width 1


def test_bud_ac12_a_member_with_a_per_session_cap_reserves_it(repo: Path) -> None:  # BUD-AC12 (BUD-B12, BUD-B13)
    ex = Crew(cost=0.1)
    out = go(repo, capped(council_wf(("a", "b")), 20.0), ex, **per_session(2.5))
    assert out.exit_code is ExitCode.FINISHED, out.message
    held = [r for r in recs(repo, "reservation") if ".member." in r["session_key"]]
    assert {(r["source"], r["reserved_usd"]) for r in held} == {("session_cap", 2.5)}
    sent = next(r for r in ex.requests if r.session_key == f"{UNIT}.1.member.a.0")
    assert sent.options.cost_cap_usd == 2.5  # the same cap reaches the session


def test_bud_ac13_members_whose_reservations_cross_the_cap_start_one_and_wait(repo: Path) -> None:  # BUD-AC13 (BUD-B12, BUD-B14)
    ex = Crew(cost=0.4, hold_s=0.3)
    out = go(repo, capped(council_wf(), CAP), ex, **per_session(2.5))
    assert out.exit_code is ExitCode.FINISHED, out.message
    rows = log(repo)
    waits = [r for r in rows if r["kind"] == "reservation" and r["action"] == "waiting"]
    assert len(waits) == 1  # one record, when the wait begins
    waited = waits[0]["session_key"]
    assert waits[0]["waiting_for"] and all(".member." in k for k in waits[0]["waiting_for"])
    at = next(i for i, r in enumerate(rows) if r["kind"] == "reservation" and r["session_key"] == waited
              and r["action"] == "held")
    ended = [i for i, r in enumerate(rows) if r["kind"] == "agent_run" and r["session_key"] in waits[0]["waiting_for"]]
    assert ended and min(ended) < at  # the held record follows the agent_run of a session it waited for
    for r in (r for r in rows if r["kind"] == "reservation" and r["action"] == "held"):
        assert round(r["spent_usd"] + r["in_flight_usd"] + r["reserved_usd"], 6) <= r["cap_usd"]


def test_bud_ac14_a_member_reservation_that_does_not_fit_with_none_running_is_refused_and_the_run_drains(repo: Path) -> None:  # BUD-AC14 (BUD-B15)
    ex = Crew(cost=2.4, hold_s=0.2)
    out = go(repo, capped(council_wf(("a", "b")), 4.0), ex, **per_session(2.5))
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "cost_cap", out.message
    rows = log(repo)
    refused = [r for r in rows if r["kind"] == "reservation" and r["action"] == "refused"]
    assert len(refused) == 1 and ".member." in refused[0]["session_key"]
    waiting = next(i for i, r in enumerate(rows) if r["kind"] == "reservation" and r["action"] == "waiting")
    assert waiting < rows.index(refused[0]) < max(i for i, r in enumerate(rows) if r["kind"] == "run_exit")
    exit_rec = [r for r in rows if r["kind"] == "run_exit"][-1]
    assert exit_rec["exit_code"] == 5 and exit_rec["reason"] == "cost_cap"
    assert len(ex.of("member")) == 1 and not ex.of("chair") and not ex.of("judge")  # no later session of the council


def test_bud_ac14_a_chair_that_runs_alone_meets_the_check_made_before_an_attempt(repo: Path) -> None:  # BUD-AC14 (BUD-B9, BUD-B12)
    ex = Crew(cost=3.0, hold_s=0.05)
    out = go(repo, capped(council_wf(("a", "b")), CAP), ex)  # the members' shares (2.5 each) fit; they cost 6.0
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "cost_cap", out.message
    assert len(ex.of("member")) == 2 and not ex.of("chair") and not ex.of("judge")  # the run cap stopped it before the chair

