"""A slot is started exactly once (TCK-B12, TCK-B2, SCH-B7; TCK-AC2, SCH-AC5; AC 12).

With a fake clock and a scripted launcher: a tick killed at each of its steps and run again, the loop and an external
call at the same moment, and 1,000 runs of two concurrent ticks."""

from __future__ import annotations

import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tempergraph.schedule import credentials, policies, store, tick, token
from tempergraph.store.layout import home_path

NOW = datetime(2026, 11, 23, 9, 0, 30, tzinfo=UTC)
OK = credentials.Check(checked=[{"executor": "claude", "role": "step", "kinds": ["api_key"], "result": "ok"}])
STEPS = ("lock", "settle", "decide", "started", "launch", "ended")


class Killed(BaseException):
    """A tick killed at a step: not an `Exception`, so nothing in the tick catches it."""


def make(home: Path, sid: str, *, repo: Path, rule: str = "FREQ=HOURLY;BYMINUTE=0") -> dict[str, Any]:
    created = "2026-11-23T08:30:00Z"
    entry = store.build_entry(
        schedule_id=sid, name=sid, target={"kind": "workflow", "workflow": "demo", "repo": str(repo), "request": "x", "inputs": {}},
        when={"kind": "recur", "rule": rule, "zone": "UTC", "starts": "2026-11-23T00:00"}, options={"flag": {}, "profiles": []},
        run_cost_cap_usd=3.0, budget=None, catch_up="latest", catch_up_window_s=3600, overlap="skip", max_live=1,
        pause_after_failures=3, created={"at": created, "caller": {"kind": "person", "decided_by": "person"}, "from": "x"},
        now=datetime.fromisoformat(created), executors_checked=[{"executor": "claude", "role": "step", "kinds": ["api_key"],
                                                                 "result": "ok"}], token_digest=token.digest("t"))
    store.write_entry(entry, home)
    store.append_event(sid, "created", now=datetime.fromisoformat(created), home=home)
    return entry


class Launcher:
    def __init__(self) -> None:
        self.fires: Counter[str] = Counter()
        self.lock = threading.Lock()

    def __call__(self, entry: dict[str, Any], start: dict[str, Any]) -> bool:
        with self.lock:
            self.fires[start["fire_id"]] += 1
        return True


def edges(launcher: Launcher, *, trigger_kill: str | None = None, status: Any = None) -> tick.Edges:
    def checkpoint(step: str) -> None:
        if step == trigger_kill:
            raise Killed(step)

    return tick.Edges(clock=lambda: NOW, launcher=launcher, resolver=lambda e: OK, repo_ok=lambda r: True,
                      status_of=status or (lambda e, t: {"state": "running"}), checkpoint=checkpoint)


def handled(home: Path, sid: str) -> Counter[str]:
    """How many handling events (started, skipped, missed, refused) each slot of the fire log has."""
    return Counter(e["slot"] for e in store.read_log(sid, home) if e["kind"] in policies.HANDLED)


@pytest.mark.parametrize("step", STEPS)
def test_tck_ac2_a_tick_killed_at_each_step_and_run_again_never_starts_a_slot_twice(step: str, tmp_path: Path) -> None:
    home = home_path()
    for sid in ("alpha-0001", "beta-0002"):
        make(home, sid, repo=tmp_path)
    # a started fire of a third schedule that has finished: the tick settles it (the step `ended`)
    make(home, "gamma-0003", repo=tmp_path)
    store.append_event("gamma-0003", "started", now=NOW, slot="2026-11-23T08:00:00Z", fire_id="gamma-0003@20261123T0800Z",
                       thread="demo/s-gamma-0003-20261123T0800", home=home)
    done = {"demo/s-gamma-0003-20261123T0800": {"state": "finished", "exit_code": 0, "cost": {"reported": 0.1}}}
    launcher = Launcher()

    def status(entry: dict[str, Any], thread: str) -> dict[str, Any]:
        return done.get(thread, {"state": "running"})

    with pytest.raises(Killed):
        tick.run_tick(home, edges(launcher, trigger_kill=step, status=status))
    for _ in range(2):  # run again, and once more: nothing changes the second time
        tick.run_tick(home, edges(launcher, status=status))
    for sid in ("alpha-0001", "beta-0002", "gamma-0003"):
        slots = handled(home, sid)
        assert slots["2026-11-23T09:00:00Z"] == 1, (step, sid, slots)  # started or missed or skipped or refused: once
        assert all(n == 1 for n in slots.values()), (step, sid, slots)
        ended = [e for e in store.read_log(sid, home) if e["kind"] == "ended"]
        assert len(ended) <= 1
    assert all(n <= 1 for n in launcher.fires.values()), launcher.fires  # never started twice
    assert not tick.run_tick(home, edges(launcher, status=status)).locked  # the killed tick's lock is free again


def test_tck_b12_the_loop_and_an_external_call_at_the_same_moment_start_each_slot_once(tmp_path: Path) -> None:
    home = home_path()
    for i in range(4):  # at most 4 runs start in one tick (TCK-B16)
        make(home, f"digest-000{i}", repo=tmp_path)
    launcher = Launcher()
    gate = threading.Barrier(2)

    def go(kind: str) -> None:
        gate.wait()
        tick.run_tick(home, edges(launcher), trigger=kind)

    threads = [threading.Thread(target=go, args=(k,)) for k in ("loop", "external")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(launcher.fires) == [f"digest-000{i}@20261123T0900Z" for i in range(4)] and set(launcher.fires.values()) == {1}
    for i in range(4):
        assert [e["kind"] for e in store.read_log(f"digest-000{i}", home)].count("started") == 1
    again = tick.run_tick(home, edges(launcher), trigger="external")  # a later tick finds them handled and exits 0
    assert again.exit_code == 0 and not again.started and again.deferred == []


def test_sch_ac5_1000_runs_of_two_concurrent_ticks_start_each_slot_once(tmp_path: Path) -> None:
    for i in range(1000):
        launcher = Launcher()
        home = tmp_path / f"h{i}"
        make(home, "digest-0001", repo=tmp_path)
        gate = threading.Barrier(2)

        def go(gate: threading.Barrier = gate, home: Path = home, launcher: Launcher = launcher) -> None:
            gate.wait()
            tick.run_tick(home, edges(launcher), trigger="external")

        threads = [threading.Thread(target=go) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        kinds = [e["kind"] for e in store.read_log("digest-0001", home)]
        assert kinds.count("started") == 1, (i, kinds)
        assert handled(home, "digest-0001")["2026-11-23T09:00:00Z"] == 1
        assert sum(launcher.fires.values()) == 1, (i, launcher.fires)  # started once, launched once
