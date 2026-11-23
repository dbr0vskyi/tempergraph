"""The portable loop and the `host` adapter (TCK-B1, TCK-B3, TCK-B8, TCK-B14, TCK-B15; TCK-AC1; AC 7) with a fake clock and a
fake sleeper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph import detach
from tempergraph.cli import schedule_cli
from tempergraph.durability.lock import RunLock, is_held
from tempergraph.schedule import loop, store, tick
from tempergraph.store.layout import home_path

from .test_schedule_cli import NOW, WARSAW, add, sched
from .test_schedule_tick import Launcher, edges, make

START = datetime(2026, 11, 23, 8, 30, 30, tzinfo=UTC)


class Time:
    """A wall clock and a monotonic clock that a fake sleeper moves together, and a jump that moves only the wall clock."""

    def __init__(self, wall: datetime = START) -> None:
        self.wall, self.mono, self.slept = wall, 0.0, []
        self.during_sleep: Any = None

    def clock(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    def sleeper(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.wall += timedelta(seconds=seconds)
        self.mono += seconds
        if self.during_sleep is not None:
            hook, self.during_sleep = self.during_sleep, None
            hook(self)

    def loop_edges(self, tick_fn: Any, **kw: Any) -> loop.Edges:
        return loop.Edges(clock=self.clock, monotonic=self.monotonic, sleeper=self.sleeper, tick=tick_fn, **kw)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))


def test_tck_ac1_the_sleep_ends_at_the_earlier_of_the_next_slot_of_any_schedule_and_60_seconds(tmp_path: Path) -> None:
    home = home_path()
    assert loop.sleep_for(START, []) == 60.0  # nothing is scheduled
    make("hourly-0001", repo=tmp_path)
    entries = store.list_entries(home)
    assert loop.sleep_for(datetime(2026, 11, 23, 8, 59, 30, tzinfo=UTC), entries) == 30.0  # the slot is sooner
    assert loop.sleep_for(datetime(2026, 11, 23, 8, 10, 0, tzinfo=UTC), entries) == 60.0  # the cap
    make("paused-0002", repo=tmp_path, state="paused", rule="FREQ=HOURLY;BYMINUTE=15")
    assert loop.sleep_for(datetime(2026, 11, 23, 8, 14, 50, tzinfo=UTC), store.list_entries(home)) == 60.0  # paused: ignored
    make("quarter-0003", repo=tmp_path, rule="FREQ=HOURLY;BYMINUTE=15")
    assert loop.sleep_for(datetime(2026, 11, 23, 8, 14, 50, tzinfo=UTC), store.list_entries(home)) == 10.0


def test_tck_ac1_a_wall_clock_jump_ends_the_sleep_and_the_slot_missed_while_asleep_is_ticked_at_once(tmp_path: Path) -> None:
    home = home_path()
    made = "2026-11-23T08:30:00Z"
    make("hourly-0001", repo=tmp_path, created=made)
    t = Time()
    launcher = Launcher(home)
    ticks: list[datetime] = []

    def one_tick() -> tick.Result:
        ticks.append(t.wall)
        return tick.run_tick(home, edges(home, clock=t.clock, launcher=launcher), trigger="loop")

    def asleep(time: Time) -> None:
        time.wall += timedelta(minutes=50)  # the lid was closed: only the wall clock moved
        make("hourly-0002", repo=tmp_path, created=made)  # a schedule added meanwhile: nothing was held in memory

    t.during_sleep = asleep
    assert loop.run_loop(home, t.loop_edges(one_tick), max_ticks=2) == 0
    assert len(ticks) == 2 and t.slept == [5.0]  # one slice, then the jump ended the sleep
    assert ticks[1] == datetime(2026, 11, 23, 9, 20, 35, tzinfo=UTC)  # ticked at once on waking, not 60 s later
    assert sorted(c["fire_id"] for c in launcher.calls) == ["hourly-0001@20261123T0900Z", "hourly-0002@20261123T0900Z"]


def test_tck_ac1_a_quiet_sleep_runs_the_slices_up_to_the_wait_and_ticks_again(tmp_path: Path) -> None:
    home = home_path()
    t = Time()
    count: list[int] = []
    assert loop.run_loop(home, t.loop_edges(lambda: count.append(1)), max_ticks=2) == 0
    assert len(count) == 2 and sum(t.slept) == 60.0 and set(t.slept) == {5.0}
    info = loop.running(home)
    assert info is None  # the loop has ended: the lock is free and its info is gone
    assert not (store.schedules_root(home) / loop.INFO).exists() and not is_held(loop.lock_path(home))


def test_tck_ac1_one_loop_per_user_under_loop_lock(tmp_path: Path) -> None:
    home = home_path()
    t = Time()
    inner: list[int] = []

    def tick_fn() -> None:
        inner.append(loop.run_loop(home, t.loop_edges(lambda: inner.append(99)), max_ticks=1))  # a second loop, while this runs
        assert loop.running(home) is not None  # the lock is held now

    assert loop.run_loop(home, t.loop_edges(tick_fn), max_ticks=1) == 0
    assert inner == [0]  # the second loop found the lock held, ticked nothing and ended


def test_tck_ac1_stop_ends_the_loop_within_one_slice(tmp_path: Path) -> None:
    home = home_path()
    t = Time()
    t.during_sleep = lambda time: loop.stop(home)  # `schedule loop --stop` from another process
    n: list[int] = []
    assert loop.run_loop(home, t.loop_edges(lambda: n.append(1))) == 0
    assert len(n) == 1 and t.slept == [5.0]
    assert not (store.schedules_root(home) / loop.STOP).exists() and loop.stop(home) is False  # nothing runs any more


def test_tck_ac1_after_an_engine_switch_the_loop_finishes_its_tick_and_re_executes_through_the_shim(tmp_path: Path) -> None:
    home = home_path()
    t = Time()
    seen: list[Any] = []
    n: list[int] = []

    def reexec() -> bool:
        seen.append(is_held(loop.lock_path(home)))  # the new loop must be able to take the lock
        return True

    code = loop.run_loop(home, t.loop_edges(lambda: n.append(1), switched=lambda: True, reexec=reexec))
    assert code == 0 and n == [1] and seen == [False] and t.slept == []  # one finished tick, no sleep, one hand-over


def test_tck_ac1_the_engine_switch_is_read_from_engines_current_json(tmp_path: Path) -> None:
    import sys

    home = home_path()
    assert loop.engine_switched(home) is False  # no current.json: a development install
    (home / "engines").mkdir(parents=True)
    (home / "engines" / "current.json").write_text(f'{{"path": "{Path(sys.prefix).as_posix()}"}}')
    assert loop.engine_switched(home) is False
    (home / "engines" / "current.json").write_text(f'{{"path": "{tmp_path.as_posix()}/engines/new"}}')
    assert loop.engine_switched(home) is True


def test_tck_ac1_loop_detach_twice_reports_the_running_loop_and_exits_0_and_writes_no_os_entry(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[Path] = []
    monkeypatch.setattr(detach, "start_loop", lambda home, shim=None: started.append(home) or True)
    code, out, err = sched(repo, "loop", "--detach")
    assert code == 0 and "loop started" in out and len(started) == 1, err
    held = RunLock(loop.lock_path(home_path())).acquire()  # the loop it started is now running
    try:
        code, out, _ = sched(repo, "loop", "--detach")
        assert code == 0 and "already running" in out and len(started) == 1
    finally:
        held.release()


def test_tck_ac1_loop_stop_ends_a_running_loop_and_reports_none_when_nothing_runs(repo: Path) -> None:
    code, out, _ = sched(repo, "loop", "--stop")
    assert code == 0 and "no loop is running" in out
    held = RunLock(loop.lock_path(home_path())).acquire()
    try:
        code, out, _ = sched(repo, "loop", "--stop")
        assert code == 0 and "stop requested" in out and (store.schedules_root(home_path()) / loop.STOP).is_file()
    finally:
        held.release()


def test_tck_ac1_detach_and_stop_exclude_each_other(repo: Path) -> None:
    code, _, err = sched(repo, "loop", "--detach", "--stop")
    assert code == 2 and err


def test_tck_ac1_add_with_no_live_trigger_saves_with_one_warning_offering_the_loop_and_naming_the_adapters(repo: Path) -> None:
    code, doc, err = add(repo)
    assert code == 0 and doc["status"] == "saved"  # saved all the same
    assert err.count("schedule loop --detach") == 1 and err.count("schedule trigger install --os") == 1
    assert "loop_autostart" in err and "schedule tick" in err  # the optional adapters, named once
    assert "schedule loop --detach" in doc["trigger_warning"]


def test_tck_ac1_add_with_a_live_trigger_gives_no_warning(repo: Path) -> None:
    held = RunLock(loop.lock_path(home_path())).acquire()
    try:
        code, doc, err = add(repo)
    finally:
        held.release()
    assert code == 0 and "trigger_warning" not in doc and "schedule loop --detach" not in err


def test_tck_ac1_a_recent_heartbeat_counts_as_a_live_trigger(repo: Path) -> None:
    from tempergraph.docs import write_json

    write_json(tick.heartbeat_path(home_path()), {"schema_version": 1, "last_tick_at": (NOW - timedelta(minutes=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "interval_s": 300})
    assert "trigger_warning" not in add(repo)[1]
    write_json(tick.heartbeat_path(home_path()), {"schema_version": 1, "last_tick_at": (NOW - timedelta(minutes=20)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "interval_s": 300})
    assert "trigger_warning" in add(repo)[1]


@pytest.mark.parametrize(("setting", "running", "starts"), [(True, False, 1), (False, False, 0), (True, True, 0)])
def test_tck_ac1_the_host_adapter_starts_the_loop_only_with_autostart_on_and_no_loop(
        repo: Path, monkeypatch: pytest.MonkeyPatch, setting: bool, running: bool, starts: int) -> None:
    import json

    cfg = home_path() / "config"
    cfg.mkdir(parents=True)
    (cfg / "settings.json").write_text(json.dumps({"schema_version": 1, "schedule": {"loop_autostart": setting}}))
    started: list[int] = []
    monkeypatch.setattr(detach, "start_loop", lambda home, shim=None: started.append(1) or True)
    held = RunLock(loop.lock_path(home_path())).acquire() if running else None
    try:
        code, out, err = sched(repo, "loop", "--if-autostart")
    finally:
        if held:
            held.release()
    assert code == 0 and not out and len(started) == starts, err  # silent: a hook never writes into a session


def test_tck_ac1_the_host_adapter_exits_0_on_every_failure(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    cfg = home_path() / "config"
    cfg.mkdir(parents=True)
    (cfg / "settings.json").write_text(json.dumps({"schema_version": 1, "schedule": {"loop_autostart": True}}))

    def boom(home: Path, shim: Path | None = None) -> bool:
        raise RuntimeError("no interpreter")

    monkeypatch.setattr(detach, "start_loop", boom)
    assert sched(repo, "loop", "--if-autostart")[0] == 0
    (cfg / "settings.json").write_text("{not json")  # an unreadable file leaves the default: off
    assert sched(repo, "loop", "--if-autostart")[0] == 0
