"""The fire-decision policies as pure functions with a fake clock (SCH-B5 to SCH-B9, SCH-B11, SCH-B21 to SCH-B26;
SCH-AC5). Nothing here starts a process or touches a file: the functions read an entry, its fire log, the live runs
and a clock, and say what to record and raise."""

from __future__ import annotations

import copy
import random
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tempergraph.render.template import TemplateError
from tempergraph.schedule import policies as pol
from tempergraph.schedule.policies import Decision, LiveRun


@pytest.fixture(autouse=True)
def _no_process(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **k: object) -> None:
        raise AssertionError("a policy function started a process")

    monkeypatch.setattr(subprocess, "Popen", boom)


def at(*a: int) -> datetime:
    return datetime(*a, tzinfo=UTC)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def entry(rule: str = "FREQ=DAILY;BYHOUR=9;BYMINUTE=0", zone: str = "UTC", starts: str = "2026-11-01T00:00",
          **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schedule_id": "digest-1a2b", "name": "digest", "state": "active",
        "target": {"kind": "workflow", "workflow": "demo", "repo": "/r", "request": "daily digest for {fire.date}",
                   "inputs": {}},
        "when": {"kind": "recur", "rule": rule, "starts": starts, "zone": zone}, "catch_up": "latest",
        "catch_up_window_s": 86400, "overlap": "skip", "max_live": 1, "pause_after_failures": 3,
        "run_cost_cap_usd": 4.0, "budget": None, "created": {"at": "2026-11-20T00:00:00Z"}, "edited": None}
    base.update(kw)
    return base


def ev(kind: str, when: datetime, slot: datetime | None = None, **meta: Any) -> dict[str, Any]:
    return {"kind": kind, "at": iso(when), "slot": iso(slot) if slot else None,
            "fire_id": f"digest-1a2b@{slot:%Y%m%dT%H%MZ}" if slot else None, **meta}


def kinds(d: Decision) -> list[tuple[str, str | None]]:
    return [(e["kind"], e["slot"]) for e in d.events]


# --- SCH-B21, SCH-B6: catch-up -------------------------------------------------------------------------------------


def friday_log() -> list[dict[str, Any]]:
    return [ev("started", at(2026, 11, 20, 9, 0), at(2026, 11, 20, 9, 0), thread="demo/s-digest-1a2b-202611200900")]


def test_sch_ac5_latest_fires_the_most_recent_slot_and_records_the_older_ones_missed() -> None:
    # SCH-B6: off from Friday evening to Monday 10:00, the first tick at 10:05
    d = pol.decide_tick(entry(), friday_log(), [], at(2026, 11, 23, 10, 5))
    assert kinds(d) == [("missed", "2026-11-21T09:00:00Z"), ("missed", "2026-11-22T09:00:00Z")]
    assert [s["slot"] for s in d.start] == ["2026-11-23T09:00:00Z"]
    # the machine back on Sunday 10:00: Sunday's fires, Saturday's is missed
    d = pol.decide_tick(entry(), friday_log(), [], at(2026, 11, 22, 10, 0))
    assert kinds(d) == [("missed", "2026-11-21T09:00:00Z")] and [s["slot"] for s in d.start] == ["2026-11-22T09:00:00Z"]


def test_sch_ac5_a_slot_found_on_time_fires_under_every_policy() -> None:
    now = at(2026, 11, 23, 9, 0, 30)
    for policy in ("latest", "none", "all"):
        d = pol.decide_tick(entry(catch_up=policy), [*friday_log(), *_handled(21, 22)], [], now)
        assert [s["slot"] for s in d.start] == ["2026-11-23T09:00:00Z"] and not d.events, policy


def _handled(*days: int) -> list[dict[str, Any]]:
    return [ev("missed", at(2026, 11, d, 12, 0), at(2026, 11, d, 9, 0)) for d in days]


def test_sch_ac5_none_records_every_late_slot_missed_and_waits_for_the_next() -> None:
    d = pol.decide_tick(entry(catch_up="none"), friday_log(), [], at(2026, 11, 23, 10, 5))
    assert kinds(d) == [("missed", "2026-11-21T09:00:00Z"), ("missed", "2026-11-22T09:00:00Z"),
                        ("missed", "2026-11-23T09:00:00Z")] and d.start == []


def test_sch_ac5_all_fires_each_slot_within_the_window_in_order_at_most_three_a_tick() -> None:
    e = entry(catch_up="all", catch_up_window_s=5 * 86400, overlap="parallel", max_live=4,
              created={"at": "2026-11-14T00:00:00Z"})
    log = [ev("started", at(2026, 11, 14, 9), at(2026, 11, 14, 9))]
    d = pol.decide_tick(e, log, [], at(2026, 11, 20, 10, 0))  # 15, 16, 17, 18, 19, 20 have passed
    assert [s["slot"] for s in d.start] == ["2026-11-16T09:00:00Z", "2026-11-17T09:00:00Z", "2026-11-18T09:00:00Z"]
    assert kinds(d) == [("missed", "2026-11-15T09:00:00Z")]  # older than the window (5 days from the 20th)
    # the three the tick left are still unhandled: the next tick takes them
    log += _started(d, at(2026, 11, 20, 10))
    nxt = pol.decide_tick(e, log, [], at(2026, 11, 20, 10, 1))
    assert [s["slot"] for s in nxt.start] == ["2026-11-19T09:00:00Z", "2026-11-20T09:00:00Z"]


def test_sch_ac5_the_window_defaults_to_the_period_capped_at_24_hours() -> None:
    assert pol.default_window_s(entry()) == 86400
    assert pol.default_window_s(entry("FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0")) == 86400
    assert pol.default_window_s(entry("FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=9;BYMINUTE=0")) == 86400
    assert pol.default_window_s(entry("FREQ=HOURLY;INTERVAL=2")) == 7200
    assert pol.default_window_s(entry("FREQ=MINUTELY;INTERVAL=30")) == 1800
    assert pol.default_window_s(entry("FREQ=HOURLY;INTERVAL=48")) == 86400
    once = entry(when={"kind": "once", "at": "2026-11-24T09:00", "zone": "UTC"})
    assert pol.default_window_s(once) == 86400


def test_sch_ac5_a_slot_outside_the_window_is_missed_even_for_the_latest() -> None:
    e = entry(catch_up_window_s=3600)
    d = pol.decide_tick(e, friday_log(), [], at(2026, 11, 23, 10, 30))  # Monday 09:00 is 90 minutes old
    assert d.start == [] and [k for k, _ in kinds(d)] == ["missed"] * 3


def test_sch_ac5_a_missed_once_raises_schedule_missed_and_the_schedule_is_done() -> None:
    e = entry(when={"kind": "once", "at": "2026-11-23T09:00", "zone": "UTC"}, catch_up_window_s=600,
              created={"at": "2026-11-22T00:00:00Z"})
    d = pol.decide_tick(e, [], [], at(2026, 11, 23, 12, 0))
    assert kinds(d) == [("missed", "2026-11-23T09:00:00Z")] and d.state == "done"
    assert d.attention == [{"kind": "schedule_missed", "schedule_id": "digest-1a2b", "slot": "2026-11-23T09:00:00Z",
                            "answer": "schedule fire digest-1a2b"}]
    fires = pol.decide_tick(e, [], [], at(2026, 11, 23, 9, 0, 20))  # on time: it fires, and the schedule is done
    assert [s["slot"] for s in fires.start] == ["2026-11-23T09:00:00Z"] and fires.state == "done" and not fires.attention


def test_sch_ac5_a_handled_slot_is_never_decided_again_and_a_paused_schedule_decides_nothing() -> None:
    log = [*friday_log(), *_handled(21, 22), ev("skipped", at(2026, 11, 23, 9, 1), at(2026, 11, 23, 9, 0), reason="overlap")]
    assert pol.decide_tick(entry(), log, [], at(2026, 11, 23, 9, 5)).events == []
    assert pol.decide_tick(entry(state="paused"), friday_log(), [], at(2026, 11, 23, 10, 5)) == Decision()
    assert pol.decide_tick(entry(state="done"), [], [], at(2026, 11, 23, 10, 5)) == Decision()
    assert pol.decide_slot(entry(state="paused"), [], [], at(2026, 11, 23, 9, 0), at(2026, 11, 23, 9, 0)).events[0][
        "reason"] == "paused"  # a slot decided while not active is skipped `paused`


def test_sch_ac5_resume_records_the_slots_passed_while_paused_missed_unless_catch_up() -> None:
    log = [*friday_log(), ev("paused", at(2026, 11, 21, 12, 0), reason="person")]
    e = entry(state="paused")
    got = pol.resume_events(e, log, at(2026, 11, 23, 12, 0), catch_up=False)
    assert [(x["kind"], x["slot"]) for x in got] == [("missed", "2026-11-22T09:00:00Z"), ("missed", "2026-11-23T09:00:00Z"),
                                                     ("resumed", None)]
    got = pol.resume_events(e, log, at(2026, 11, 23, 12, 0), catch_up=True)
    assert [x["kind"] for x in got] == ["resumed"] and got[0]["catch_up"] is True


# --- SCH-B22, SCH-B5: overlap --------------------------------------------------------------------------------------


def run(slot: datetime, state: str = "running", n: int = 1) -> LiveRun:
    return LiveRun(fire_id=f"digest-1a2b@{slot:%Y%m%dT%H%MZ}", slot=iso(slot), thread=f"demo/s-digest-1a2b-{n}",
                   state=state, started_at=iso(slot + timedelta(seconds=5)))


def test_sch_ac5_skip_records_overlap_and_starts_nothing() -> None:
    mon = at(2026, 11, 23, 9)
    log = [*friday_log(), *_handled(21, 22), ev("started", mon, mon)]
    d = pol.decide_tick(entry(), log, [run(mon)], at(2026, 11, 24, 9, 0, 10))
    assert kinds(d) == [("skipped", "2026-11-24T09:00:00Z")] and d.events[0]["reason"] == "overlap" and d.start == []


def test_sch_ac5_parallel_starts_while_live_runs_are_under_max_live() -> None:
    mon = at(2026, 11, 23, 9)
    e = entry(overlap="parallel", max_live=2)
    log = [*friday_log(), *_handled(21, 22), ev("started", mon, mon)]
    d = pol.decide_tick(e, log, [run(mon)], at(2026, 11, 24, 9, 0, 10))
    assert [s["slot"] for s in d.start] == ["2026-11-24T09:00:00Z"] and not d.events
    d = pol.decide_tick(e, log, [run(mon), run(mon, n=2)], at(2026, 11, 24, 9, 0, 10))
    assert d.start == [] and d.events[0]["reason"] == "overlap"  # at max_live: skipped


def test_sch_ac5_queue_holds_one_pending_fire_a_later_slot_replaces_it() -> None:
    mon, tue, wed = at(2026, 11, 23, 9), at(2026, 11, 24, 9), at(2026, 11, 25, 9)
    e = entry(overlap="queue")
    log = [*friday_log(), *_handled(21, 22), ev("started", mon, mon)]
    d = pol.decide_tick(e, log, [run(mon)], at(2026, 11, 24, 9, 0, 10))
    assert kinds(d) == [("queued", "2026-11-24T09:00:00Z")] and d.start == []
    log += [dict(x, at=iso(tue)) for x in d.events]
    d = pol.decide_tick(e, log, [run(mon)], at(2026, 11, 25, 9, 0, 10))  # Wednesday replaces Tuesday's pending fire
    assert kinds(d) == [("skipped", "2026-11-24T09:00:00Z"), ("queued", "2026-11-25T09:00:00Z")]
    assert d.events[0]["reason"] == "overlap"
    log += [dict(x, at=iso(wed)) for x in d.events]
    d = pol.decide_tick(e, log, [], at(2026, 11, 25, 9, 30))  # the run ended: the first tick starts the pending one
    assert [s["slot"] for s in d.start] == ["2026-11-25T09:00:00Z"] and d.events == []


def test_sch_ac5_a_paused_run_counts_as_live_and_the_pause_is_marked_blocking_after_three_skips() -> None:
    mon = at(2026, 11, 23, 9)
    log = [*friday_log(), *_handled(21, 22), ev("started", mon, mon)]
    paused = run(mon, "paused")
    items: list[dict[str, Any]] = []
    for n, day in enumerate((24, 25, 26), start=1):  # SCH-B5: Tuesday, Wednesday and Thursday come due
        d = pol.decide_tick(entry(), log, [paused], at(2026, 11, day, 9, 0, 10))
        assert kinds(d) == [("skipped", f"2026-11-{day}T09:00:00Z")] and d.events[0]["reason"] == "overlap"
        assert d.start == []
        log += [dict(x, at=iso(at(2026, 11, day, 9, 0, 10))) for x in d.events]
        items = d.attention
        assert (len(items) == 1) == (n >= 3)  # raised when the count reaches 3
    assert items == [{"kind": "blocking_schedule", "schedule_id": "digest-1a2b", "thread": paused.thread,
                      "blocking_schedule": 3}]
    d = pol.decide_tick(entry(), log, [paused], at(2026, 11, 27, 9, 0, 10))
    assert d.attention[0]["blocking_schedule"] == 4  # and on each further skip


def test_sch_ac5_two_slots_in_one_tick_under_skip_start_the_first_and_skip_the_second() -> None:
    e = entry(catch_up="all", catch_up_window_s=3 * 86400, created={"at": "2026-11-18T00:00:00Z"})
    d = pol.decide_tick(e, [ev("started", at(2026, 11, 18, 9), at(2026, 11, 18, 9))], [], at(2026, 11, 20, 10))
    assert [s["slot"] for s in d.start] == ["2026-11-19T09:00:00Z"]
    assert kinds(d) == [("skipped", "2026-11-20T09:00:00Z")] and d.events[0]["reason"] == "overlap"


# --- SCH-B23, SCH-B9: failures -------------------------------------------------------------------------------------


def fire_log(*exits: int, start: int = 1) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, code in enumerate(exits):
        slot = at(2026, 11, start + i, 9)
        out += [ev("started", slot, slot, thread=f"demo/s-{i}"),
                ev("ended", slot + timedelta(minutes=5), slot, exit=code, outcome="x", thread=f"demo/s-{i}",
                   cost={"reported": 1.0, "estimated": 1.0, "incomplete": False})]
    return out


def test_sch_ac5_failures_count_in_a_row_and_exit_zero_resets() -> None:
    assert pol.failure_count(fire_log(5, 4)) == 2
    assert pol.failure_count(fire_log(5, 4, 0)) == 0  # SCH-B23: exit 0 resets
    assert pol.failure_count(fire_log(5, 0, 5)) == 1
    assert pol.failure_count(fire_log(3, 6, 1)) == 0  # other exits change nothing
    refused = [*fire_log(5), ev("refused", at(2026, 11, 2, 9), at(2026, 11, 2, 9), reason="settings")]
    assert pol.failure_count(refused) == 2  # a start refused with exit 2 is a failure
    assert pol.failure_count([*fire_log(5, 5), ev("resumed", at(2026, 11, 3, 9), None)]) == 0  # resume resets
    assert pol.failure_count([*fire_log(5, 5), ev("skipped", at(2026, 11, 3, 9), at(2026, 11, 3, 9), reason="overlap"),
                              ev("missed", at(2026, 11, 3, 9), at(2026, 11, 3, 9))]) == 2


def test_sch_ac5_three_failures_pause_the_schedule_with_the_reason_failures() -> None:
    log = fire_log(5, 5, 5)
    d = pol.decide_after(entry(), log, at(2026, 11, 3, 9, 6))
    assert d.state == "paused" and d.hooks == ["schedule_paused"]
    assert [(e["kind"], e["reason"]) for e in d.events] == [("paused", "failures")]
    assert d.attention == [{"kind": "schedule_paused", "schedule_id": "digest-1a2b", "thread": "demo/s-2",
                            "cause": "exit 5 x"}]  # the last failure's thread and cause
    assert pol.decide_after(entry(), fire_log(5, 5), at(2026, 11, 3, 9, 6)) == Decision()
    assert pol.decide_after(entry(pause_after_failures=2), fire_log(5, 5), at(2026, 11, 3, 9, 6)).state == "paused"
    assert pol.decide_after(entry(state="paused"), log, at(2026, 11, 3, 9, 6)) == Decision()  # already paused


# --- SCH-B24, SCH-B8: spend ----------------------------------------------------------------------------------------


def spend_log() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for day, cost in ((2, 6.10), (3, 5.80), (4, 4.30)):
        slot = at(2026, 11, day, 9)
        out += [ev("started", slot, slot), ev("ended", slot + timedelta(minutes=5), slot, exit=0,
                                              cost={"reported": cost, "estimated": cost, "incomplete": False})]
    return out


def test_sch_ac5_a_fire_that_would_pass_the_period_budget_is_skipped_with_one_item_a_period() -> None:
    e = entry(budget={"period": "month", "cap_usd": 20.0}, created={"at": "2026-11-02T00:00:00Z"})
    log = [ev("created", at(2026, 11, 2), None), *spend_log()]
    assert pol.period_spend(e, log, at(2026, 11, 5, 9, 0, 10)) == pytest.approx(16.20)
    d = pol.decide_tick(e, log, [], at(2026, 11, 5, 9, 0, 10))
    assert kinds(d)[-1] == ("skipped", "2026-11-05T09:00:00Z") and d.events[-1]["reason"] == "budget"  # 16.20 + 4 > 20
    assert d.start == [] and [a["kind"] for a in d.attention] == ["schedule_budget"]
    log += [dict(x, at=iso(at(2026, 11, 5, 9, 0, 10))) for x in d.events]
    d = pol.decide_tick(e, log, [], at(2026, 11, 6, 9, 0, 10))
    assert d.events[-1]["reason"] == "budget" and d.attention == []  # once per period
    d = pol.decide_tick(e, [*log, *_handled(5, 6)], [], at(2026, 12, 1, 9, 0, 10))  # the next period
    assert [s["slot"] for s in d.start] == ["2026-12-01T09:00:00Z"]


def test_sch_ac5_an_incomplete_fire_counts_at_the_run_cap() -> None:
    e = entry(budget={"period": "month", "cap_usd": 20.0})
    slot = at(2026, 11, 2, 9)
    log = [ev("started", slot, slot), ev("ended", slot, slot, exit=0, cost={"reported": 0.0, "estimated": 0.5,
                                                                            "incomplete": True}),
           *[x for x in spend_log() if x["slot"] != iso(slot)]]
    assert pol.period_spend(e, log, at(2026, 11, 5, 9)) == pytest.approx(4.0 + 5.80 + 4.30)  # the run cap, not 0.5
    unended = [ev("started", slot, slot)]
    assert pol.period_spend(e, unended, at(2026, 11, 5, 9)) == pytest.approx(4.0)  # a fire not yet ended counts too


def test_sch_ac5_a_period_is_a_calendar_day_week_or_month_in_the_schedule_zone() -> None:
    e = entry(zone="Europe/Warsaw", budget={"period": "month", "cap_usd": 10.0})
    s, f = pol.period_bounds(e, at(2026, 11, 30, 23, 30))  # 00:30 on 1 December in Warsaw
    assert (s, f) == (at(2026, 11, 30, 23, 0), at(2026, 12, 31, 23, 0))
    assert pol.period_bounds(entry(budget={"period": "week", "cap_usd": 1}), at(2026, 11, 25, 12)) == (
        at(2026, 11, 23), at(2026, 11, 30))  # ISO week from Monday
    assert pol.period_bounds(entry(budget={"period": "day", "cap_usd": 1}), at(2026, 11, 25, 12)) == (
        at(2026, 11, 25), at(2026, 11, 26))
    slot = at(2026, 11, 30, 23, 30)
    log = [ev("started", slot, slot), ev("ended", slot, slot, exit=0, cost={"estimated": 3.0, "incomplete": False})]
    assert pol.period_spend(e, log, at(2026, 12, 1, 8)) == pytest.approx(3.0)  # December in Warsaw
    assert pol.period_spend(e, log, at(2026, 11, 30, 22, 45)) == pytest.approx(0.0)  # but not November's


# --- SCH-B26, SCH-B11: fire identity and keys ----------------------------------------------------------------------


def test_sch_ac5_fire_identity_thread_and_orchestration_ids() -> None:
    slot = at(2026, 11, 23, 8, 0)
    assert pol.fire_id("digest-1a2b", slot) == "digest-1a2b@20261123T0800Z"
    assert pol.fire_id("digest-1a2b", slot, manual_at=at(2026, 11, 23, 8, 15, 42)) == "digest-1a2b@manual-20261123T081542Z"
    assert pol.thread_id("demo", "digest-1a2b", slot) == "demo/s-digest-1a2b-20261123T0800"
    assert pol.orchestration_id("release", slot, "ab12") == "release-s20261123T0800-ab12"


def test_sch_ac5_fire_keys_render_by_the_template_grammar() -> None:
    e = entry(zone="Europe/Warsaw")
    slot, prev = at(2026, 11, 23, 7, 0), at(2026, 11, 20, 8, 0)
    keys = pol.fire_keys(e, slot, [ev("started", prev, prev)])
    assert keys == {"fire.slot": "2026-11-23T08:00", "fire.date": "2026-11-23", "fire.previous_slot": "2026-11-20T09:00",
                    "fire.schedule": "digest-1a2b"}
    assert pol.render_fire_text("daily digest for {fire.date}", keys) == "daily digest for 2026-11-23"  # SCH-B11
    assert pol.render_fire_text("{fire.schedule} at {fire.slot} after {fire.previous_slot}; {{literal}}", keys) == (
        "digest-1a2b at 2026-11-23T08:00 after 2026-11-20T09:00; {literal}")
    assert pol.fire_keys(e, slot, [])["fire.previous_slot"] == ""
    with pytest.raises(TemplateError):
        pol.render_fire_text("{unbalanced", keys)
    with pytest.raises(TemplateError):  # the grammar has no other fire key
        pol.render_fire_text("{fire.nothing}", keys)


def test_sch_ac5_a_start_carries_its_identity_keys_and_label() -> None:
    d = pol.decide_tick(entry(), friday_log(), [], at(2026, 11, 21, 9, 0, 30))
    (s,) = d.start
    assert s["fire_id"] == "digest-1a2b@20261121T0900Z" and s["thread"] == "demo/s-digest-1a2b-20261121T0900"
    assert s["label"] == "schedule digest 2026-11-21" and s["keys"]["fire.date"] == "2026-11-21"
    assert pol.render_fire_text(entry()["target"]["request"], s["keys"]) == "daily digest for 2026-11-21"


# --- SCH-B7: a slot never runs twice -------------------------------------------------------------------------------


def test_sch_ac5_two_ticks_over_one_shared_log_never_give_a_slot_two_started_events() -> None:
    rnd = random.Random(7)
    for trial in range(1000):
        shared: list[dict[str, Any]] = []
        now = at(2026, 11, 23, 9, 0, rnd.randrange(0, 50))
        e = entry(catch_up=rnd.choice(("latest", "none", "all")), overlap=rnd.choice(("skip", "queue", "parallel")),
                  max_live=rnd.randrange(1, 4))
        a = pol.decide_tick(e, copy.deepcopy(shared), [], now)  # tick A reads the log
        if rnd.random() < 0.5:  # tick B reads before A has written: the two ticks overlap in time
            b_log = copy.deepcopy(shared)
            pol.commit_events(shared, _started(a, now))
            b = pol.decide_tick(e, b_log, [], now)
        else:  # or after
            pol.commit_events(shared, _started(a, now))
            b = pol.decide_tick(e, copy.deepcopy(shared), [], now)
        pol.commit_events(shared, _started(b, now))
        starts = [x["slot"] for x in shared if x["kind"] == "started"]
        assert len(starts) == len(set(starts)), (trial, starts)  # no slot has two `started` events
        handled = [x["slot"] for x in shared if x["kind"] in pol.HANDLED]
        assert len(handled) == len(set(handled))  # nor is a slot handled in two ways


def _started(d: Decision, now: datetime) -> list[dict[str, Any]]:
    return [pol.started_event(s, now) for s in d.start] + [dict(x, at=iso(now)) for x in d.events]


def test_sch_ac5_commit_events_drops_an_event_for_a_slot_already_handled() -> None:
    slot = at(2026, 11, 23, 9)
    shared = [ev("started", slot, slot)]
    assert pol.commit_events(shared, [ev("skipped", slot, slot, reason="overlap"), ev("started", slot, slot)]) == []
    assert pol.commit_events(shared, [ev("due", slot, slot)]) == [ev("due", slot, slot)]  # `due` handles nothing
    assert len(shared) == 2


def test_sch_ac5_the_functions_change_neither_their_inputs_nor_the_world() -> None:
    e, log, live = entry(), [*friday_log(), ev("paused", at(2026, 11, 21, 12), reason="person")], [run(at(2026, 11, 20, 9))]
    before = copy.deepcopy((e, log, live))
    pol.decide_tick(e, log, live, at(2026, 11, 23, 10, 5))
    pol.decide_after(e, log, at(2026, 11, 23, 10, 5))
    pol.resume_events(e, log, at(2026, 11, 23, 10, 5), catch_up=False)
    assert (e, log, live) == before
