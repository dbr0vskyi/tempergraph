"""`schedule fire` through the tick's path (SCH-B26, SCH-B27, TCK-B22; SCH-AC5; AC 2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tempergraph.cli import schedule_cli
from tempergraph.schedule import launch, ledger, policies, store
from tempergraph.store.layout import home_path

from .test_schedule_cli import NO_TTY, NOW, WARSAW, home_hash, saved, sched
from .test_schedule_person import AGENT

MANUAL = "20261123T083030Z"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")  # the credential check of a fire reads the tick's own environment


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(launch, "launch_run", lambda entry, start, **kw: calls.append(start) or True)
    return calls


def test_sch_ac5_fire_starts_one_fire_through_the_ticks_launcher_with_a_manual_fire_id(repo: Path,
                                                                                        launched: list[dict[str, Any]]) -> None:
    sid = saved(repo)
    code, doc, err = sched(repo, "fire", sid, "--yes", "--json")
    assert code == 0 and doc["status"] == "started", err
    assert doc["fire_id"] == f"{sid}@manual-{MANUAL}" and doc["thread_id"] == f"demo/s-{sid}-manual-20261123T083030"
    assert [s["fire_id"] for s in launched] == [doc["fire_id"]]  # the tick's launcher, once
    started = [e for e in store.read_log(sid) if e["kind"] == "started"]
    assert [(e["fire_id"], e["thread"]) for e in started] == [(doc["fire_id"], doc["thread_id"])]
    (row,) = ledger.read()
    assert (row["fire_id"], row["outcome"], row["trigger"]) == (doc["fire_id"], "started", "manual")
    assert [e["kind"] for e in store.read_log(sid)] == ["created", "started"]  # no catch-up: no `missed` for earlier slots


def test_sch_ac5_fire_does_not_catch_up_the_slots_passed(repo: Path, launched: list[dict[str, Any]],
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    sid = saved(repo)
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW.replace(day=26, hour=9))  # three daily slots have passed
    code, doc, _ = sched(repo, "fire", sid, "--yes", "--json")
    assert code == 0 and policies.handled_slots(store.read_log(sid)) == {"2026-11-26T09:30:30Z"} and len(launched) == 1


def test_sch_ac5_fire_needs_a_person_and_an_agent_without_a_turn_is_refused(repo: Path, launched: list[dict[str, Any]]) -> None:
    sid = saved(repo)
    before = home_hash()
    for who in (AGENT, NO_TTY):
        code, _, err = sched(repo, "fire", sid, "--yes", signals=who)
        assert code == 2 and "schedule_not_by_person" in err, err
    assert home_hash() == before and launched == []


def test_sch_ac5_fire_without_yes_exits_3_with_the_echo_and_starts_nothing(repo: Path, launched: list[dict[str, Any]]) -> None:
    sid = saved(repo)
    before = home_hash()
    code, doc, _ = sched(repo, "fire", sid)
    assert code == 3 and doc["status"] == "needs" and doc["questions"][0]["name"] == "confirm" and "echo" in doc
    assert home_hash() == before and launched == []


@pytest.mark.parametrize("state", ["paused", "removed"])
def test_sch_ac5_a_paused_or_removed_schedule_is_refused_schedule_state(repo: Path, launched: list[dict[str, Any]],
                                                                         state: str) -> None:
    sid = saved(repo)
    sched(repo, "pause" if state == "paused" else "remove", sid, *(["--yes"] if state == "removed" else []))
    before = home_hash()
    code, _, err = sched(repo, "fire", sid, "--yes")
    assert code == 2 and "schedule_state" in err and home_hash() == before and launched == []


def test_sch_ac5_the_credential_check_applies_to_a_manual_fire(repo: Path, launched: list[dict[str, Any]],
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    sid = saved(repo)
    monkeypatch.delenv("ANTHROPIC_API_KEY")  # the key is gone from the environment and the profile
    code, _, err = sched(repo, "fire", sid, "--yes")
    assert code == 2 and "credential" in err and launched == []
    (refused,) = [e for e in store.read_log(sid) if e["kind"] == "refused"]
    assert refused["reason"] == "credential" and refused["fire_id"] == f"{sid}@manual-{MANUAL}"
    assert ledger.read()[0]["outcome"] == "refused"
    assert (home_path() / "schedules" / "runs.jsonl").is_file()


def test_sch_ac5_a_second_manual_fire_in_another_second_is_its_own_fire(repo: Path, launched: list[dict[str, Any]],
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    sid = saved(repo)
    assert sched(repo, "fire", sid, "--yes")[0] == 0
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW.replace(second=45))
    assert sched(repo, "fire", sid, "--yes")[0] == 0
    assert [s["fire_id"][-16:] for s in launched] == ["20261123T083030Z", "20261123T083045Z"]
