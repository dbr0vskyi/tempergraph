"""Scripted runs through the tick, end to end (SCH-AC5, SCH-AC7; TCK-B24; AC 6): `report --by schedule`, supervision, overlap
`skip` and `queue`, `max_live` and a paused run that blocks after three skipped slots."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tempergraph.cli import schedule_cli
from tempergraph.contracts import ThreadState
from tempergraph.durability import status as dstatus
from tempergraph.run.events import records
from tempergraph.run.supervision import schedule_setup
from tempergraph.schedule import credentials, launch, ledger, policies, store, tick, token
from tempergraph.store.layout import home_path

from .test_cli import cli, happy, standin
from .test_run import DRAFT, REVIEW, judge, verdict_block
from .test_schedule_cli import CATALOG, NOW, WARSAW, saved, sched

HOURLY = "FREQ=HOURLY;BYMINUTE=0"
OK = credentials.Check(checked=[{"executor": "claude", "role": "step", "kinds": ["api_key"], "result": "ok"}])


def at(hour: int, minute: int = 0, second: int = 30) -> datetime:
    return datetime(2026, 11, 23, hour, minute, second, tzinfo=UTC)


def pausing() -> Any:
    return standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])


class Rig:
    """A tick whose launcher runs `run --schedule` in this process on a scripted executor, and whose status is the real one."""

    def __init__(self, repo: Path, sid: str, executors: list[Any] | None = None) -> None:
        self.repo, self.sid, self.executors = repo, sid, list(executors or [])
        self.root = repo / ".tempergraph"

    def edges(self, now: datetime) -> tick.Edges:
        def launcher(entry: dict[str, Any], start: dict[str, Any]) -> bool:
            launch.write_ticket(entry, start)
            ex = self.executors.pop(0) if self.executors else happy()
            code, _, err = cli(self.repo, ex, "run", "demo", "--schedule", start["fire_id"], "--task-id",
                               start["thread"].split("/", 1)[1], signals=({token.ENV_VAR: str(token.read_token(self.sid))}, False),
                               catalog=CATALOG)
            assert code in (0, 3), err
            return True

        def status_of(entry: dict[str, Any], thread: str) -> dict[str, Any] | None:
            row = dstatus.row(self.root, CATALOG.specs["demo"], thread) if self.root.is_dir() else None
            return None if row is None else {"state": row["state"], "exit_code": row.get("exit_code"), "cost": row.get("cost")}

        return tick.Edges(clock=lambda: now, launcher=launcher, resolver=lambda e: OK, status_of=status_of,
                          state_root_of=lambda e: self.root)

    def tick(self, now: datetime) -> tick.Result:
        return tick.run_tick(home_path(), self.edges(now))

    def kinds(self) -> list[tuple[str, str]]:
        return [(e["kind"], str(e.get("slot"))[11:16]) for e in store.read_log(self.sid) if e["kind"] != "created"]


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")


def test_sch_ac7_report_by_schedule_totals_equal_the_fire_logs_ended_costs_and_supervision_counts_the_setup_once(repo: Path) -> None:
    sid = saved(repo, rule=HOURLY)
    assert sched(repo, "edit", sid, "--overlap", "queue", "--yes")[0] == 0  # the person's `edit`: still one setup touch
    rig = Rig(repo, sid)
    assert rig.tick(at(9)).started == [f"{sid}@20261123T0900Z"]
    assert rig.tick(at(10)).started == [f"{sid}@20261123T1000Z"] and rig.tick(at(11)).started == [f"{sid}@20261123T1100Z"]
    store.append_event(sid, "skipped", now=at(11), slot="2026-11-23T12:00:00Z", fire_id=f"{sid}@20261123T1200Z", reason="person")
    log = store.read_log(sid)
    ended = [e for e in log if e["kind"] == "ended"]
    assert len(ended) == 2 and {e["exit"] for e in ended} == {0}  # the third is settled by the next tick
    code, doc, err = cli(repo, None, "report", "--by", "schedule", "--json", catalog=CATALOG)
    assert code == 0, err
    g = doc["groups"][sid]
    assert g["fires"] == 3 and g["ended"] == 2 and g["skipped"] == 1 and g["outcomes"] == {"finished": 2}
    assert g["estimated_usd"] == sum(e["cost"]["estimated"] or 0.0 for e in ended) == doc["totals"]["estimated_usd"]
    assert doc["totals"]["fires"] == 3 and len(ledger.read(schedule=sid)) == 3  # one ledger row for each fire the tick handled
    setup = schedule_setup(log)  # SUP: one designed touch for the add and the edit together, none for a fire
    assert setup["touches"]["designed"]["person"] == 1 and sum(setup["touches"]["designed"].values()) == 1
    assert setup["fire_touches"] == 0 and setup["start_cost"] == "measured_zero" and setup["fires"] == 3
    run_log = repo / ".tempergraph" / "runs" / "demo" / f"s-{sid}-20261123T0900" / "run.jsonl"
    (s,) = [r for r in records(run_log) if r["kind"] == "supervision"]
    assert s["start_cost"] == "measured_zero" and s["undesigned"] == 0
    assert all(v == 0 for cls in s["touches"].values() if isinstance(cls, dict) for v in cls.values())


def test_sch_ac5_overlap_skip_a_paused_run_blocks_and_blocking_schedule_is_raised_after_three_skipped_slots(repo: Path) -> None:
    sid = saved(repo, rule=HOURLY)
    rig = Rig(repo, sid, [pausing()])
    assert rig.tick(at(9)).started == [f"{sid}@20261123T0900Z"]  # exits 3: a pause waits for a person
    for hour in (10, 11, 12):
        assert rig.tick(at(hour)).skipped == 1
    assert rig.kinds() == [("started", "09:00"), ("skipped", "10:00"), ("skipped", "11:00"), ("skipped", "12:00")]
    assert {e["reason"] for e in store.read_log(sid) if e["kind"] == "skipped"} == {"overlap"}
    code, att, err = cli(repo, None, "attention", "--json", catalog=CATALOG)
    items = {i["kind"]: i for i in att["items"]}
    assert code == 0 and items["blocking_schedule"]["blocking_schedule"] == 3 and items["blocking_schedule"]["schedule_id"] == sid, err
    assert any(i.get("schedule", {}).get("schedule_id") == sid for i in att["items"] if i.get("thread_id"))  # the pause, with its schedule
    assert len(ledger.read(outcome="skipped")) == 3


def test_sch_ac5_overlap_queue_holds_one_slot_and_starts_it_when_the_run_ends(repo: Path) -> None:
    sid = saved(repo, "--overlap", "queue", rule=HOURLY)
    rig = Rig(repo, sid, [pausing(), happy(), happy()])
    rig.tick(at(9))
    rig.tick(at(10))  # 10:00 is held
    rig.tick(at(11))  # 11:00 replaces it: the held slot is skipped
    assert rig.kinds() == [("started", "09:00"), ("queued", "10:00"), ("skipped", "10:00"), ("queued", "11:00")]
    ex = standin("claude", steps=[REVIEW], judges=[judge()])
    code, _, err = cli(repo, ex, "resume", "demo", f"s-{sid}-20261123T0900", "--decision", "proceed", catalog=CATALOG)
    assert code == 0, err  # a person answers the pause
    result = rig.tick(at(12))
    assert result.started[0] == f"{sid}@20261123T1100Z" and policies.pending_slot(store.read_log(sid)) == "2026-11-23T12:00:00Z"


def test_sch_ac5_parallel_runs_up_to_max_live_and_skips_the_next_slot(repo: Path) -> None:
    sid = saved(repo, "--overlap", "parallel", "--max-live", "2", rule=HOURLY)
    launched: list[str] = []

    def launcher(entry: dict[str, Any], start: dict[str, Any]) -> bool:
        launched.append(start["fire_id"])
        return True

    def status_of(entry: dict[str, Any], thread: str) -> dict[str, Any]:
        return {"state": str(ThreadState.PAUSED)}  # every run stays live

    for hour in (9, 10, 11):
        tick.run_tick(home_path(), tick.Edges(clock=lambda hour=hour: at(hour), launcher=launcher, resolver=lambda e: OK,
                                              status_of=status_of, repo_ok=lambda r: True))
    assert launched == [f"{sid}@20261123T0900Z", f"{sid}@20261123T1000Z"]
    skipped = [e for e in store.read_log(sid) if e["kind"] == "skipped"]
    assert [(e["slot"][11:16], e["reason"]) for e in skipped] == [("11:00", "overlap")]  # two are live: the third waits for none
