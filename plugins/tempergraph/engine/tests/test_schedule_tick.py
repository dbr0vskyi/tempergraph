"""The tick with a fake clock and a scripted run launcher (TCK-B2, TCK-B5, TCK-B16; TCK-AC1, TCK-AC3, TCK-AC6; AC 1)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ENGINE_VERSION
from tempergraph.durability.lock import RunLock
from tempergraph.schedule import credentials, launch, ledger, policies, store, tick, token
from tempergraph.store.layout import home_path

NOW = datetime(2026, 11, 23, 9, 0, 30, tzinfo=UTC)  # 30 s after the 09:00 slots
HOURLY = "FREQ=HOURLY;BYMINUTE=0"
OK = credentials.Check(checked=[{"executor": "claude", "role": "step", "kinds": ["api_key"], "result": "ok",
                                 "may_expire": False}])


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class Launcher:
    """A scripted run launcher: it records each call and what the fire log held at that moment."""

    def __init__(self, home: Path) -> None:
        self.home, self.calls, self.fail = home, [], set()

    def __call__(self, entry: dict[str, Any], start: dict[str, Any]) -> bool:
        log = store.read_log(str(entry["schedule_id"]), self.home)
        self.calls.append({"fire_id": start["fire_id"], "thread": start["thread"],
                           "started_logged": any(e["kind"] == "started" and e["fire_id"] == start["fire_id"]
                                                 and e["thread"] == start["thread"] for e in log)})
        return start["fire_id"] not in self.fail


def make(sid: str, *, repo: Path, rule: str = HOURLY, state: str = "active", overlap: str = "skip", catch_up: str = "latest",
         pause_after: int = 3, created: str = "2026-11-23T05:30:00Z", **kw: Any) -> dict[str, Any]:
    entry = store.build_entry(
        schedule_id=sid, name=sid, target={"kind": "workflow", "workflow": "demo", "repo": str(repo),
                                           "request": "digest for {fire.date}", "inputs": {"day": "{fire.date}"}},
        when={"kind": "recur", "rule": rule, "zone": "UTC", "starts": "2026-11-23T00:00"},
        options={"flag": {"run.run_cost_cap_usd": {"value": 3.0, "ref": "--set", "via": "schedule"}}, "profiles": []},
        run_cost_cap_usd=3.0, budget=None, catch_up=catch_up, catch_up_window_s=3600, overlap=overlap, max_live=1,
        pause_after_failures=pause_after, created={"at": created, "caller": {"kind": "person", "decided_by": "person"},
                                                   "from": "schedule add"}, now=datetime.fromisoformat(created),
        executors_checked=[{"executor": "claude", "role": "step", "kinds": ["api_key"], "result": "ok"}],
        token_digest=token.digest("s3cret"), **kw)
    entry["state"] = state
    store.write_entry(entry)
    store.append_event(sid, "created", now=datetime.fromisoformat(created), caller=entry["created"]["caller"])
    token.write_token(sid, "s3cret")
    return entry


def edges(home: Path, *, clock: Clock | None = None, launcher: Launcher | None = None, **kw: Any) -> tick.Edges:
    return tick.Edges(clock=clock or Clock(), launcher=launcher or Launcher(home), resolver=lambda entry: OK,
                      repo_ok=lambda repo: True, **kw)


def log_of(sid: str) -> list[dict[str, Any]]:
    return store.read_log(sid)


def kinds(sid: str) -> list[str]:
    return [e["kind"] for e in log_of(sid)]


@pytest.fixture
def home() -> Path:
    h = home_path()
    h.mkdir(parents=True, exist_ok=True)
    return h


def test_tck_ac1_a_held_lock_exits_0_at_once_and_reads_no_schedule(home: Path, tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    make("digest-0001", repo=tmp_path)
    store.schedules_root(home).mkdir(parents=True, exist_ok=True)
    held = RunLock(store.schedules_root(home) / "tick.lock").acquire()

    def boom(*a: object, **k: object) -> None:
        raise AssertionError("a schedule was read")

    monkeypatch.setattr(store, "list_entries", boom)
    monkeypatch.setattr(store, "read_entry", boom)
    t0 = datetime.now()
    try:
        result = tick.run_tick(home, edges(home))
    finally:
        held.release()
    assert result.locked and result.exit_code == 0 and (datetime.now() - t0) < timedelta(seconds=1)
    assert not tick.heartbeat_path(home).exists()  # it read and wrote nothing


def test_tck_ac1_the_heartbeat_has_the_tick_time_version_trigger_interval_kinds_and_deferred(home: Path, tmp_path: Path) -> None:
    make("digest-0001", repo=tmp_path)
    tick.run_tick(home, edges(home), trigger="loop", interval_s=60)
    beat = json.loads(tick.heartbeat_path(home).read_text(encoding="utf-8"))
    assert beat["last_tick_at"] == "2026-11-23T09:00:30Z" and beat["engine_version"] == ENGINE_VERSION
    assert (beat["trigger"], beat["interval_s"], beat["deferred"]) == ("loop", 60, [])
    assert beat["credentials"] == {"claude": ["api_key"]}  # presence only: kinds, never a value
    assert "s3cret" not in tick.heartbeat_path(home).read_text(encoding="utf-8")
    assert tick.read_heartbeat(home) == beat
    assert stat.S_IMODE(tick.heartbeat_path(home).stat().st_mode) == 0o600


def test_tck_ac1_a_started_fire_is_settled_from_its_threads_status_with_exit_outcome_and_cost(home: Path, tmp_path: Path) -> None:
    make("digest-0001", repo=tmp_path)
    store.append_event("digest-0001", "started", now=NOW - timedelta(hours=1), slot="2026-11-23T08:00:00Z",
                       fire_id="digest-0001@20261123T0800Z", thread="demo/s-digest-0001-20261123T0800")
    seen: list[str] = []

    def status_of(entry: dict[str, Any], thread: str) -> dict[str, Any]:
        seen.append(thread)
        return {"state": "finished", "exit_code": 0, "cost": {"reported": 0.5, "estimated_only": 0.25}}

    result = tick.run_tick(home, edges(home, status_of=status_of))
    ended = [e for e in log_of("digest-0001") if e["kind"] == "ended"]
    assert [e["fire_id"] for e in ended] == ["digest-0001@20261123T0800Z"] and result.settled == [ended[0]["fire_id"]]
    assert (ended[0]["exit"], ended[0]["outcome"], ended[0]["cost"]) == (0, "finished", {"reported": 0.5, "estimated": 0.75,
                                                                                         "incomplete": False})
    assert seen[0] == "demo/s-digest-0001-20261123T0800"
    assert policies.failure_count(log_of("digest-0001")) == 0


def test_tck_ac1_a_failed_fire_updates_the_failure_count_and_a_running_one_is_left(home: Path, tmp_path: Path) -> None:
    make("digest-0001", repo=tmp_path, pause_after=1)
    make("digest-0002", repo=tmp_path)
    for sid, slot in (("digest-0001", "20261123T0700"), ("digest-0002", "20261123T0800")):
        store.append_event(sid, "started", now=NOW - timedelta(hours=1), slot=f"{slot[:4]}-{slot[4:6]}-{slot[6:8]}T{slot[9:11]}:00:00Z",
                           fire_id=f"{sid}@{slot}Z", thread=f"demo/s-{sid}-{slot}")
    states = {"demo/s-digest-0001-20261123T0700": {"state": "stopped", "exit_code": 5},
              "demo/s-digest-0002-20261123T0800": {"state": "running"}}
    hooked: list[str] = []
    tick.run_tick(home, edges(home, status_of=lambda e, t: states[t], on_hook=lambda ev, e, facts: hooked.append(ev)))
    assert policies.failure_count(log_of("digest-0001")) == 1 and "paused" in kinds("digest-0001")
    assert store.read_entry("digest-0001")["state"] == "paused" and hooked == ["schedule_paused"]
    assert "ended" not in kinds("digest-0002")  # still running


def test_tck_ac1_passed_slots_become_missed_skipped_or_refused_through_decide_tick(home: Path, tmp_path: Path) -> None:
    now = datetime(2026, 11, 23, 11, 0, 30, tzinfo=UTC)
    make("latest-0001", repo=tmp_path)  # 09:00 and 10:00 are missed, 11:00 fires
    make("paused-0001", repo=tmp_path, state="paused")  # decides nothing
    make("busy-0001", repo=tmp_path)  # a live run makes its slot skipped (overlap)
    store.append_event("busy-0001", "started", now=NOW, slot="2026-11-23T10:00:00Z", fire_id="busy-0001@20261123T1000Z",
                       thread="demo/s-busy-0001-20261123T1000")
    result = tick.run_tick(home, edges(home, clock=Clock(now), status_of=lambda e, t: {"state": "running"}))
    assert kinds("latest-0001") == ["created", *["missed"] * 5, "started"]
    assert [e["slot"][11:16] for e in log_of("latest-0001") if e["kind"] == "missed"] == ["06:00", "07:00", "08:00", "09:00", "10:00"]
    assert kinds("paused-0001") == ["created"]
    skipped = [e for e in log_of("busy-0001") if e["kind"] == "skipped"]
    assert [(e["slot"], e["reason"]) for e in skipped] == [("2026-11-23T11:00:00Z", "overlap")]
    assert result.missed == 5 + 4 and result.skipped == 1  # the busy schedule's 06:00 to 09:00 are missed too


def test_tck_ac1_an_unhandled_error_goes_to_the_code_log_and_the_heartbeat_and_the_lock_is_released(home: Path, tmp_path: Path) -> None:
    make("digest-0001", repo=tmp_path)
    store.append_event("digest-0001", "started", now=NOW, slot="2026-11-23T08:00:00Z", fire_id="digest-0001@20261123T0800Z",
                       thread="demo/s-digest-0001-20261123T0800")
    logged: list[BaseException] = []

    def broken(entry: dict[str, Any], thread: str) -> dict[str, Any]:
        raise RuntimeError("the status reader broke")

    result = tick.run_tick(home, edges(home, status_of=broken, log_error=logged.append))
    assert result.exit_code == 0 and [str(e) for e in logged] == ["the status reader broke"]
    assert "RuntimeError" in json.loads(tick.heartbeat_path(home).read_text(encoding="utf-8"))["last_error"]
    assert not tick.run_tick(home, edges(home, status_of=lambda e, t: None)).locked  # the lock was released


def test_tck_ac1_an_unwritable_home_store_exits_non_zero_and_starts_nothing(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    launcher = Launcher(blocker / "home")
    result = tick.run_tick(blocker / "home", edges(blocker / "home", launcher=launcher))
    assert result.exit_code != 0 and launcher.calls == []


def test_tck_ac3_started_is_appended_with_the_thread_id_before_the_launcher_is_called(home: Path, tmp_path: Path) -> None:
    make("digest-0001", repo=tmp_path)
    launcher = Launcher(home)
    result = tick.run_tick(home, edges(home, launcher=launcher))
    assert launcher.calls == [{"fire_id": "digest-0001@20261123T0900Z", "thread": "demo/s-digest-0001-20261123T0900",
                               "started_logged": True}]
    assert result.started == ["digest-0001@20261123T0900Z"]
    assert kinds("digest-0001") == ["created", "missed", "missed", "missed", "started"]  # 06:00 to 08:00 were past the window


def test_tck_ac3_six_due_slots_start_four_and_leave_two_oldest_first_with_deferred(home: Path, tmp_path: Path) -> None:
    for i in range(6):  # six schedules, each due at 09:0<i>: the later two are the youngest slots
        make(f"digest-000{i}", repo=tmp_path, rule=f"FREQ=HOURLY;BYMINUTE={i}")
    launcher = Launcher(home)
    clock = Clock(datetime(2026, 11, 23, 9, 10, 30, tzinfo=UTC))
    result = tick.run_tick(home, edges(home, clock=clock, launcher=launcher))
    assert [c["fire_id"].split("@")[0] for c in launcher.calls] == [f"digest-000{i}" for i in range(4)]
    assert result.deferred == [{"schedule_id": "digest-0004", "slot": "2026-11-23T09:04:00Z"},
                               {"schedule_id": "digest-0005", "slot": "2026-11-23T09:05:00Z"}]
    beat = json.loads(tick.heartbeat_path(home).read_text(encoding="utf-8"))
    assert beat["deferred"] == result.deferred and beat["started"] == 4
    for d in result.deferred:
        assert "started" not in kinds(d["schedule_id"])  # nothing handled for that slot: the next tick takes it
    again = tick.run_tick(home, edges(home, clock=clock, launcher=launcher))
    assert len(again.started) == 2 and again.deferred == [] and len(launcher.calls) == 6


def test_tck_ac3_the_20_second_budget_stops_launching(home: Path, tmp_path: Path) -> None:
    for i in range(3):
        make(f"digest-000{i}", repo=tmp_path)
    clock = {"t": 0.0}
    launcher = Launcher(home)

    def slow(entry: dict[str, Any], start: dict[str, Any]) -> bool:
        clock["t"] += 12.0  # each launch takes 12 s
        return launcher(entry, start)

    result = tick.run_tick(home, tick.Edges(clock=Clock(), launcher=slow, resolver=lambda e: OK, repo_ok=lambda r: True,
                                            monotonic=lambda: clock["t"]))
    assert len(launcher.calls) == 2 and len(result.deferred) == 1  # 0 s, 12 s: launch; 24 s: over the budget


def test_tck_ac3_a_moved_or_deleted_repository_is_refused_repo_missing(home: Path, tmp_path: Path) -> None:
    make("digest-0001", repo=tmp_path / "moved")
    launcher = Launcher(home)
    result = tick.run_tick(home, tick.Edges(clock=Clock(), launcher=launcher, resolver=lambda e: OK,
                                            repo_ok=lambda r: Path(r).is_dir()))
    assert launcher.calls == [] and result.refused == ["digest-0001@20261123T0900Z"]
    refused = [e for e in log_of("digest-0001") if e["kind"] == "refused"]
    assert [e["reason"] for e in refused] == ["repo_missing"] and policies.failure_count(log_of("digest-0001")) == 1


def test_tck_ac6_a_missing_credential_is_refused_counts_as_a_failure_and_starts_no_session(home: Path, tmp_path: Path) -> None:
    make("digest-0001", repo=tmp_path, pause_after=1)
    launcher = Launcher(home)
    gone = credentials.check([{"executor": "claude", "role": "step"}], {"claude": frozenset()}, at_fire=True)
    hooked: list[tuple[str, dict[str, Any]]] = []
    result = tick.run_tick(home, tick.Edges(clock=Clock(), launcher=launcher, resolver=lambda e: gone,
                                            repo_ok=lambda r: True, on_hook=lambda ev, e, facts: hooked.append((ev, facts))))
    assert launcher.calls == [] and result.started == []  # no session
    (refused,) = [e for e in log_of("digest-0001") if e["kind"] == "refused"]
    assert refused["reason"] == "credential" and refused["executor"] == "claude"  # `schedule_refused` names it (attention)
    assert policies.failure_count(log_of("digest-0001")) == 1  # a failure: the limit of 1 pauses the schedule
    assert store.read_entry("digest-0001")["state"] == "paused" and hooked[0][0] == "schedule_paused"
    (row,) = ledger.read(outcome="refused")
    assert row["reason"] == "credential" and row["fire_id"] == "digest-0001@20261123T0900Z"


def test_tck_ac6_the_resolver_reads_the_ticks_own_environment_for_the_executors_recorded_at_add(home: Path, tmp_path: Path) -> None:
    entry = make("digest-0001", repo=tmp_path)
    assert tick.entry_resolver({"ANTHROPIC_API_KEY": "k"}, {})(entry).refusal is None
    gone = tick.entry_resolver({}, {})(entry)
    assert gone.refusal is not None and gone.refusal[0] == "credential" and "claude" in gone.refusal[1]


def test_tck_ac3_process_audit_the_only_process_the_tick_starts_is_the_engines_run(home: Path, tmp_path: Path,
                                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    make("digest-0001", repo=tmp_path)
    started: list[tuple[list[str], dict[str, str]]] = []

    class Spy:
        def __init__(self, argv: list[str], **kw: Any) -> None:
            started.append((argv, kw))

    monkeypatch.setattr(subprocess, "Popen", Spy)
    result = tick.run_tick(home, tick.Edges(clock=Clock(), launcher=lambda e, s: launch.launch_run(e, s, home=home),
                                            resolver=lambda e: OK, repo_ok=lambda r: True))
    assert result.started == ["digest-0001@20261123T0900Z"] and len(started) == 1
    argv, kw = started[0]
    assert argv == [sys.executable, "-m", "tempergraph", "run", "demo", "--schedule", "digest-0001@20261123T0900Z",
                    "--task-id", "s-digest-0001-20261123T0900"]
    assert kw["env"][token.ENV_VAR] == "s3cret" and "s3cret" not in " ".join(argv)  # the token is in the environment only
    assert kw["start_new_session"] is (os.name == "posix") and kw["stdin"] == subprocess.DEVNULL
    ticket = json.loads(launch.ticket_path("digest-0001", "digest-0001@20261123T0900Z", home).read_text(encoding="utf-8"))
    assert ticket["request"] == "digest for 2026-11-23" and ticket["inputs"] == {"day": "2026-11-23"}  # rendered
    assert ticket["flags"] == {"run.run_cost_cap_usd": 3.0} and ticket["label"] == "schedule digest-0001 2026-11-23"
    assert "digest for" not in " ".join(argv)  # no person-typed text on argv
    assert stat.S_IMODE(launch.ticket_path("digest-0001", "digest-0001@20261123T0900Z", home).stat().st_mode) == 0o600
    assert launch.read_ticket("digest-0001@20261123T0900Z", home)["request"] == "digest for 2026-11-23"
    assert launch.read_ticket("digest-0001@20261123T0900Z", home) is None  # the run removes it once read


def test_tck_ac3_the_launcher_refuses_what_is_not_a_checked_value(home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tempergraph import detach

    def boom(*a: object, **k: object) -> None:
        raise AssertionError("a process was started")

    monkeypatch.setattr(subprocess, "Popen", boom)
    for words in (("run", "demo; rm -rf ~", "--schedule", "a@20261123T0900Z", "--task-id", "t"),
                  ("run", "demo", "--schedule", "a@20261123T0900Z", "--task-id", "t", "--extra"),
                  ("orchestrate", "demo", "--schedule", "a@20261123T0900Z", "--task-id", "t")):
        assert detach.start_run(words, home) is False
