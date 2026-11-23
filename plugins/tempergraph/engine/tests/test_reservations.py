"""Reservations for the sessions of parallel branches (BUD-B12 to BUD-B15, OBS-B7).

Each test carries, in a comment, the task criteria (r3-t1-1b) it proves."""

from __future__ import annotations

import dataclasses
import json
import threading
import time
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionOptions, SessionRequest, SessionResult
from tempergraph.run.reserve import Ledger
from tempergraph.store.layout import run_dir, state_root_path

from .test_contest_run import BySlot, contest_spec
from .test_contest_run import go as go_contest
from .test_map import THREE
from .test_map_concurrent import ByItem, concurrent
from .test_map_concurrent import go as go_map
from .test_parallel import ByUnit, go, recs, steps, wf

BRANCHES = ("security", "perf")
CAP = 5.0
HEADS = ("reserved_usd", "source", "spent_usd", "in_flight_usd", "cap_usd")


class Costed(ByUnit):
    """`ByUnit` with a cost per session: the plan step and its judge cost `plan` each, a branch step `branch`
    (the first branch step to start, `first`), a branch judge 0.01. With `wait_for_waiting` the first branch step
    blocks until the log shows a branch waiting; with `barrier` both branch steps are in flight together."""

    def __init__(self, repo: Path, *, plan: float = 0.5, branch: float = 0.4, first: float | None = None,
                 wait_for_waiting: bool = False, barrier: bool = False) -> None:
        super().__init__()
        self.repo, self.plan, self.branch, self.first = repo, plan, branch, first
        self.wait_for_waiting = wait_for_waiting
        self.barrier = threading.Barrier(2, timeout=10) if barrier else None
        self.lock = threading.Lock()
        self.started: list[str] = []

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit = req.session_key.split(".")[0]
        res = super().run_step(req, sink)
        cost = self.plan if unit == "plan" else self.branch
        if unit in BRANCHES:
            with self.lock:
                self.started.append(unit)
                lead = len(self.started) == 1
            if self.barrier is not None:
                self.barrier.wait()
            if lead and self.wait_for_waiting:
                end = time.monotonic() + 10
                while time.monotonic() < end and not self._waiting():
                    time.sleep(0.02)
            if lead and self.first is not None:
                cost = self.first
        res.usage.reported_cost_usd = cost
        return res

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        unit = req.session_key.split(".")[0]
        res = super().run_judge(req, views, sink)
        res.usage.reported_cost_usd = self.plan if unit == "plan" else 0.01
        return res

    def _waiting(self) -> bool:
        p = run_dir(state_root_path(self.repo), "demo", "P-1") / "run.jsonl"
        try:
            return any(json.loads(ln).get("kind") == "reservation" and json.loads(ln).get("action") == "waiting"
                       for ln in p.read_text().splitlines())
        except (OSError, ValueError):
            return False


def spec(cap: float = CAP, session_cap: float | None = 2.5) -> Any:
    base = wf()
    units = dict(base.units)
    if session_cap is not None:
        for name in BRANCHES:
            step = units[name].step
            units[name] = dataclasses.replace(
                units[name], step=dataclasses.replace(step, session_options=SessionOptions(cost_cap_usd=session_cap)))
    return dataclasses.replace(base, units=units, run_cost_cap_usd=cap)


def holds(repo: Path, action: str | None = None) -> list[dict[str, Any]]:
    return [r for r in recs(repo, "reservation") if action is None or r["action"] == action]


def of_branch_step(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r["unit"] in BRANCHES and r["session_key"].endswith(".step")]


def all_records(repo: Path) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", "P-1") / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def crossing(repo: Path, first: float | None = None) -> tuple[Costed, Any]:
    ex = Costed(repo, first=first, wait_for_waiting=True)
    return ex, go(repo, spec(), ex)


def test_two_branches_that_cross_the_cap_start_one_and_wait_BUD_AC2(repo: Path) -> None:  # BUD-AC2, AC 2, AC 3
    ex, out = crossing(repo)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert sorted(steps(ex)) == ["perf", "plan", "report", "security"]
    rows = [r for r in all_records(repo) if r["kind"] in ("attempt_start", "agent_run")
            and r["unit"] in BRANCHES and r["session_key"].endswith(".step")]
    assert [r["kind"] for r in rows] == ["attempt_start", "agent_run", "attempt_start", "agent_run"]
    assert len(holds(repo, "waiting")) == 1
    (exit_rec,) = recs(repo, "run_exit")
    assert exit_rec["cost"]["counters"]["estimated_only"] + exit_rec["cost"]["counters"]["reported"] < CAP


def test_branches_that_all_fit_run_as_before_BUD_AC2(repo: Path) -> None:  # BUD-AC2, AC 2, AC 3
    ex = Costed(repo)
    out = go(repo, dataclasses.replace(spec(), run_cost_cap_usd=50.0), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    got = steps(ex)
    assert got[0] == "plan" and sorted(got[1:3]) == ["perf", "security"] and got[3:] == ["report"]
    assert not holds(repo, "waiting") and not holds(repo, "refused")
    assert holds(repo, "held")


def test_held_records_carry_amount_source_and_figures_BUD_AC5(repo: Path) -> None:  # BUD-AC5, AC 1, AC 4
    ex = Costed(repo, barrier=True)
    out = go(repo, spec(session_cap=None), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert {r["action"] for r in holds(repo)} == {"held"}
    steps_held = of_branch_step(holds(repo))
    assert sorted(r["unit"] for r in steps_held) == sorted(BRANCHES)
    seqs = {r["session_key"]: r["seq"] for r in all_records(repo) if r["kind"] == "attempt_start"}
    for r in steps_held:
        assert (r["reserved_usd"], r["source"], r["spent_usd"], r["cap_usd"]) == (2.0, "share", 1.0, CAP)
        assert r["seq"] < seqs[r["session_key"]]


def test_a_ledger_holds_a_session_cap_with_nothing_running_BUD_AC5() -> None:  # BUD-AC5, AC 1, AC 4
    calls: list[tuple[str, dict[str, Any]]] = []
    got = Ledger().acquire("a.1.step", snapshot=2, spent_usd=1.0, cap_usd=CAP, amount=lambda spent: (2.5, "session_cap"),
                           write=lambda action, **kw: calls.append((action, kw)), drain=lambda: None)
    assert got is None
    assert calls == [("held", {"reserved_usd": 2.5, "source": "session_cap", "spent_usd": 1.0, "in_flight_usd": 0,
                               "cap_usd": CAP})]


def test_a_reservation_that_lands_exactly_on_the_cap_fits_BUD_AC5() -> None:  # BUD-AC5, AC 1
    ledger = Ledger()
    for key, amount in (("a", 2.0), ("b", 2.0), ("c", 1.0)):
        got = ledger.acquire(key, snapshot=1, spent_usd=0.0, cap_usd=CAP, amount=lambda spent, a=amount: (a, "share"),
                             write=lambda action, **kw: None, drain=lambda: None)
        assert got is None


def test_a_waiting_branch_logs_one_waiting_record_then_held_BUD_AC6(repo: Path) -> None:  # BUD-AC6, AC 1, AC 2, AC 4
    crossing(repo)
    waits = holds(repo, "waiting")
    assert len(waits) == 1
    (wait,) = waits
    keys = {r["session_key"] for r in of_branch_step(holds(repo, "held"))}
    assert len(keys) == 2 and wait["session_key"] in keys
    other = (keys - {wait["session_key"]}).pop()
    assert (wait["reserved_usd"], wait["in_flight_usd"], wait["spent_usd"], wait["waiting_for"]) == (
        2.5, 2.5, 1.0, [other])
    (later,) = [r for r in of_branch_step(holds(repo, "held")) if r["session_key"] == wait["session_key"]]
    ended = [r for r in all_records(repo) if r["kind"] == "agent_run" and r["session_key"] == other]
    assert later["seq"] > ended[0]["seq"] > wait["seq"]
    assert (later["spent_usd"], later["in_flight_usd"]) == (1.4, 0)


def test_a_wait_ends_when_a_drain_is_requested_BUD_AC6() -> None:  # BUD-AC6, AC 2
    ledger = Ledger()
    quiet = lambda action, **kw: None  # noqa: E731
    assert ledger.acquire("a", snapshot=1, spent_usd=0.0, cap_usd=CAP, amount=lambda s: (2.0, "share"),
                          write=quiet, drain=lambda: None) is None
    begun = time.monotonic()
    got = ledger.acquire("b", snapshot=1, spent_usd=0.0, cap_usd=CAP, amount=lambda s: (4.0, "share"),
                         write=quiet, drain=lambda: "stopped_by_request")
    assert got == "stopped_by_request" and time.monotonic() - begun < 5
    assert sorted(ledger.held) == ["a"]


def test_a_reservation_that_cannot_fit_is_refused_and_the_run_drains_BUD_AC7(repo: Path) -> None:  # BUD-AC7, AC 2, AC 4
    ex = Costed(repo, plan=1.5)
    out = go(repo, spec(), ex)
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "cost_cap", out.message
    records = all_records(repo)
    exit_seq = next(r["seq"] for r in records if r["kind"] == "run_exit")
    refused = of_branch_step(holds(repo, "refused"))
    assert refused and all(r["reserved_usd"] == 2.5 and r["spent_usd"] == 3.0 and r["seq"] < exit_seq for r in refused)
    assert not [r for r in records if r["kind"] == "attempt_start" and r["unit"] in BRANCHES]
    (exit_rec,) = recs(repo, "run_exit")
    assert (exit_rec["exit_code"], exit_rec["reason"]) == (5, "cost_cap")


def test_a_waiting_branch_is_refused_when_the_running_session_costs_too_much_BUD_AC7(repo: Path) -> None:  # BUD-AC7, AC 2, AC 4
    ex, out = crossing(repo, first=2.4)
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "cost_cap", out.message
    (wait,) = holds(repo, "waiting")
    (refused,) = of_branch_step(holds(repo, "refused"))
    assert refused["session_key"] == wait["session_key"] and refused["seq"] > wait["seq"]
    assert len(steps(ex)) == 2 and set(steps(ex)) - {"plan"} in ({"perf"}, {"security"})
    started = [r["session_key"] for r in all_records(repo) if r["kind"] == "attempt_start" and r["unit"] in BRANCHES]
    assert started and wait["session_key"] not in started
    (exit_rec,) = recs(repo, "run_exit")
    assert (exit_rec["exit_code"], exit_rec["reason"]) == (5, "cost_cap")


class CostedItems(ByItem):
    """`ByItem` with a cost per session: the plan step and its judge cost `plan` each, an item step `item`, an item judge
    0.01. The first item step to start blocks until the log shows an item waiting for its reservation."""

    def __init__(self, repo: Path, items: list[dict[str, str]], *, plan: float = 0.5, item: float = 0.4) -> None:
        super().__init__(items)
        self.repo, self.plan, self.item_cost = repo, plan, item
        self.first = threading.Lock()
        self.begun: list[str] = []

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit, item = self.whose(req)
        res = super().run_step(req, sink)
        res.usage.reported_cost_usd = self.plan if unit == "plan" else self.item_cost
        if unit == "phase":
            with self.first:
                self.begun.append(req.session_key)
                lead = len(self.begun) == 1
            end = time.monotonic() + 10
            while lead and time.monotonic() < end and not self._waiting():
                time.sleep(0.02)
        return res

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        unit, _ = self.whose(req)
        res = super().run_judge(req, views, sink)
        res.usage.reported_cost_usd = self.plan if unit == "plan" else 0.01
        return res

    def _waiting(self) -> bool:
        p = run_dir(state_root_path(self.repo), "demo", "M-1") / "run.jsonl"
        try:
            return any(json.loads(ln).get("kind") == "reservation" and json.loads(ln).get("action") == "waiting"
                       for ln in p.read_text().splitlines())
        except (OSError, ValueError):
            return False


def item_spec(cap: float, session_cap: float = 2.5) -> Any:
    """A concurrent map of read-only items, two at once, each item step with a per-session cost cap, under `cap`."""
    base = concurrent(concurrency=2)
    phase = base.units["phase"]
    step = dataclasses.replace(phase.step, session_options=SessionOptions(cost_cap_usd=session_cap))
    return dataclasses.replace(base, units={**base.units, "phase": dataclasses.replace(phase, step=step)},
                               run_cost_cap_usd=cap)


def item_records(repo: Path) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", "M-1") / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def test_concurrent_items_take_reservations_from_the_one_ledger_BUD_AC9(repo: Path) -> None:  # BUD-AC9 (BUD-B12, BUD-B14), AC 5
    ex = CostedItems(repo, THREE[:2])
    out = go_map(repo, item_spec(5.0), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    rows = item_records(repo)
    reserve = [r for r in rows if r["kind"] == "reservation"]
    waits = [r for r in reserve if r["action"] == "waiting" and r["session_key"].endswith(".step")]
    (wait,) = waits  # the item that waited, once
    (lead,) = [r["session_key"] for r in rows if r["kind"] == "attempt_start" and r["session_key"].startswith("phase.")
               and r["session_key"] != wait["session_key"] and r["session_key"].endswith(".step")][:1]
    assert wait["waiting_for"] == [lead]  # the running item's session
    ended = next(r for r in rows if r["kind"] == "agent_run" and r["session_key"] == lead)
    held = next(r for r in reserve if r["action"] == "held" and r["session_key"] == wait["session_key"])
    assert held["seq"] > ended["seq"] and held["spent_usd"] > wait["spent_usd"]  # after that session's `agent_run`
    assert [r["session_key"] for r in waits] == [wait["session_key"]]  # and no second `waiting` record
    for r in reserve:
        if r["action"] == "held":  # no `held` record of the run adds up to more than the cap
            assert round(r["spent_usd"] + r["in_flight_usd"] + r["reserved_usd"], 6) <= r["cap_usd"], r


def test_no_item_starts_when_the_reserved_spend_would_cross_the_cap_BUD_AC9(repo: Path) -> None:  # BUD-AC9 (BUD-B12, BUD-B15), AC 5
    ex = CostedItems(repo, THREE[:2])
    out = go_map(repo, item_spec(3.0), ex)  # the plan spent 1.00; an item reserves 2.50, which does not fit under 3.00
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "cost_cap", out.message
    rows = item_records(repo)
    assert [r for r in rows if r["kind"] == "reservation" and r["action"] == "refused"]
    assert not [r for r in rows if r["kind"] == "attempt_start" and r["session_key"].startswith("phase.")]
    assert not ex.sessions.get("phase.p1") and not ex.sessions.get("phase.p2")


class CostedSlots(BySlot):
    """`BySlot` where the first slot step to start blocks until the log shows a slot waiting for its reservation, and each
    step session costs `step_cost`, a judge 0.01."""

    def __init__(self, repo: Path, *, wait: bool = True, step_cost: float = 0.4) -> None:
        super().__init__(step_cost=step_cost, judge_cost=0.01)
        self.repo, self.wait = repo, wait
        self.begun: list[str] = []
        self.first = threading.Lock()

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        with self.first:
            self.begun.append(req.session_key)
            lead = len(self.begun) == 1
        end = time.monotonic() + 10
        while self.wait and lead and time.monotonic() < end and not self._waiting():
            time.sleep(0.02)
        return super().run_step(req, sink)

    def _waiting(self) -> bool:
        p = run_dir(state_root_path(self.repo), "demo", "C-1") / "run.jsonl"
        try:
            return any(json.loads(ln).get("kind") == "reservation" and json.loads(ln).get("action") == "waiting"
                       for ln in p.read_text().splitlines())
        except (OSError, ValueError):
            return False


def slot_spec(cap: float, session_cap: float | None = 0.8, concurrency: int = 2) -> Any:
    """A contest of three read-only slots, `concurrency` at once, each slot step with a per-session cost cap, under `cap`."""
    base = contest_spec(slots=3, concurrency=concurrency, then=False, run_cost_cap_usd=cap)
    pick = base.units["pick"]
    step = dataclasses.replace(pick.step, session_options=SessionOptions(cost_cap_usd=session_cap))
    return dataclasses.replace(base, units={"pick": dataclasses.replace(pick, step=step)})


def slot_rows(repo: Path) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", "C-1").joinpath("run.jsonl")
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def test_contest_slots_take_reservations_from_the_one_ledger_BUD_AC11(repo: Path) -> None:  # BUD-AC11 (BUD-B12, BUD-B13, BUD-B14)
    ex = CostedSlots(repo, step_cost=0.2)
    out = go_contest(repo, slot_spec(1.5), ex)  # two slots reserve 0.80 each; the second would cross 1.50 with the first held
    assert out.exit_code is ExitCode.FINISHED, out.message
    rows = slot_rows(repo)
    reserve = [r for r in rows if r["kind"] == "reservation"]
    waits = [r for r in reserve if r["action"] == "waiting" and r["session_key"].endswith(".step")]
    (wait,) = waits  # the slot that waited, once
    (lead,) = [r["session_key"] for r in rows if r["kind"] == "attempt_start" and r["session_key"].endswith(".step")
               and r["session_key"] != wait["session_key"]][:1]
    assert wait["waiting_for"] == [lead]  # the running slot's session
    ended = next(r for r in rows if r["kind"] == "agent_run" and r["session_key"] == lead)
    held = next(r for r in reserve if r["action"] == "held" and r["session_key"] == wait["session_key"])
    assert held["seq"] > ended["seq"] and held["spent_usd"] > wait["spent_usd"]  # after that session's `agent_run`
    for r in reserve:
        if r["action"] == "held":  # no `held` record of the run adds up to more than the cap
            assert round(r["spent_usd"] + r["in_flight_usd"] + r["reserved_usd"], 6) <= r["cap_usd"], r
    assert {r["session_key"].split(".")[1] for r in reserve if r["action"] == "held"} == {"s1", "s2", "s3"}


def test_a_slot_session_without_a_cap_of_its_own_reserves_a_share_of_the_cap_BUD_AC11(repo: Path) -> None:  # BUD-AC11 (BUD-B12)
    ex = CostedSlots(repo, wait=False, step_cost=0.1)
    out = go_contest(repo, slot_spec(10.0, session_cap=None, concurrency=2), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    held = [r for r in slot_rows(repo) if r["kind"] == "reservation" and r["action"] == "held"]
    assert held and all(r["source"] == "share" for r in held)
    first = min(held, key=lambda r: r["seq"])
    assert first["reserved_usd"] == round((10.0 - first["spent_usd"]) / 2, 6)  # the cap left over the lower of 2 and 3


def test_a_slot_whose_reservation_cannot_fit_is_refused_BUD_AC11(repo: Path) -> None:  # BUD-AC11 (BUD-B12, BUD-B15)
    ex = CostedSlots(repo, wait=False)
    out = go_contest(repo, slot_spec(0.5), ex)  # a slot reserves 0.80, which does not fit under 0.50 with nothing held
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "cost_cap", out.message
    rows = slot_rows(repo)
    assert [r for r in rows if r["kind"] == "reservation" and r["action"] == "refused"]
    assert not [r for r in rows if r["kind"] == "attempt_start"]


def test_ac_5_the_not_built_line_names_neither_councils_nor_contests() -> None:  # AC 5, BUD-AC9, BUD-AC11, BUD-AC12
    """Reservations are built for parallel branches, writer branches included, for the items of a concurrent map, for
    the slots of a contest and for the member and chair sessions of a council; the spec 08 line names what is not."""
    root = next(p for p in Path(__file__).resolve().parents if (p / "plugins" / "tempergraph" / "docs").is_dir())
    docs = root / "plugins" / "tempergraph" / "docs"
    lines = [ln for ln in (docs / "specs" / "08-budgets-and-failures.spec.md").read_text().splitlines()
             if ln.startswith("- Not built yet")]
    assert len(lines) == 1
    line = lines[0].lower()
    assert all(w in line for w in ("projection", "bud-b12", "bud-b15", "contest", "council"))
    assert "not built for" not in line and "maps" not in line  # councils and contests reserve too (BUD-AC11, BUD-AC12)
    assert "maps" not in line  # the items of a concurrent map reserve too
    assert "check spend only" not in line
    assert "read-only branches" not in line  # a writer branch reserves too
    plan =(docs / "plans" / "third-release.plan.md").read_text()
    section = plan.split("#### R3-T1.1 Reservations", 1)[1].split("\n####", 1)[0]
    assert "Status: built" in section
