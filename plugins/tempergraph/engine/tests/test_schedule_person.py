"""Who may create a schedule (TCK-B22, TCK-B10; TCK-AC7, AC 5): `add`, `edit`, `resume` and `fire` need a person."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.cli import schedule_cli
from tempergraph.schedule import store
from tempergraph.store.layout import home_path

from .test_schedule_cli import NO_TTY, NOW, WARSAW, add, home_hash, sched

AGENT = ({"CLAUDE_CODE_CHILD_SESSION": "1", "CLAUDE_CODE_SESSION_ID": "sess-1", "CLAUDECODE": "1"}, False)
PIPELINE = ({"GITHUB_ACTIONS": "true", "CI": "true"}, False)
NOT_PEOPLE = {"agent": AGENT, "pipeline": PIPELINE, "no terminal": NO_TTY}


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))


def turn(minutes_ago: float) -> None:
    """A person turn in the agent's host session, `minutes_ago` before the fixed clock."""
    path = home_path() / "supervision" / "claude-code" / "sess-1.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    at = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    path.write_text(json.dumps({"kind": "person_turn", "at": at, "names": []}) + "\n")


def first(repo: Path) -> str:
    code, doc, err = add(repo)
    assert code == 0, err
    return str(doc["schedule_id"])


@pytest.mark.parametrize("who", sorted(NOT_PEOPLE))
def test_tck_ac7_add_by_a_caller_that_is_not_a_person_is_refused_and_writes_nothing(repo: Path, who: str) -> None:
    before = home_hash()
    code, _, err = add(repo, signals=NOT_PEOPLE[who])
    assert code == 2 and "schedule_not_by_person" in err, err
    assert home_hash() == before


@pytest.mark.parametrize("who", sorted(NOT_PEOPLE))
def test_tck_ac7_edit_and_resume_by_a_caller_that_is_not_a_person_are_refused(repo: Path, who: str) -> None:
    sid = first(repo)
    code, _, err = sched(repo, "edit", sid, "--overlap", "queue", "--yes", signals=NOT_PEOPLE[who])
    assert code == 2 and "schedule_not_by_person" in err, err
    sched(repo, "pause", sid)
    before = home_hash()
    code, _, err = sched(repo, "resume", sid, signals=NOT_PEOPLE[who])
    assert code == 2 and "schedule_not_by_person" in err, err
    assert home_hash() == before and store.read_entry(sid)["state"] == "paused"


def test_tck_ac7_a_person_at_a_terminal_passes_add_edit_and_resume(repo: Path) -> None:
    sid = first(repo)
    assert sched(repo, "edit", sid, "--overlap", "queue", "--yes")[0] == 0
    sched(repo, "pause", sid)
    assert sched(repo, "resume", sid)[0] == 0
    assert store.read_entry(sid)["created"]["caller"]["decided_by"] == "person"


def test_tck_b10_an_agent_with_relayed_and_a_person_turn_saves_the_schedule(repo: Path) -> None:
    turn(2)
    sid = first_with(repo, AGENT, "--relayed")
    caller = store.read_entry(sid)["created"]["caller"]
    assert (caller["kind"], caller["decided_by"], caller["relay"]) == ("agent", "person", "turn_only")


def first_with(repo: Path, signals: Any, *extra: str) -> str:
    code, doc, err = add(repo, *extra, signals=signals)
    assert code == 0, err
    return str(doc["schedule_id"])


def test_tck_ac7_an_agent_with_relayed_and_no_turn_or_an_old_turn_is_refused(repo: Path) -> None:
    before = home_hash()
    code, _, err = add(repo, "--relayed", signals=AGENT)  # no journal at all
    assert code == 2 and "schedule_not_by_person" in err
    turn(30)  # a turn, but outside the 10 minutes
    code, _, err = add(repo, "--relayed", signals=AGENT)
    assert code == 2 and "schedule_not_by_person" in err
    turn(1)  # a recent turn is not enough without --relayed
    code, _, err = add(repo, signals=AGENT)
    assert code == 2 and "schedule_not_by_person" in err
    assert not (home_path() / "schedules").exists() and set(home_hash()) >= set(before)


@pytest.mark.parametrize("verb", ["pause", "skip"])
def test_tck_ac7_pause_and_skip_pass_from_an_agent_with_no_person_turn_and_record_it(repo: Path, verb: str) -> None:
    sid = first(repo)
    code, _, err = sched(repo, verb, sid, "--json", signals=AGENT)
    assert code == 0, err
    assert store.read_log(sid)[-1]["caller"]["kind"] == "agent"


def test_tck_ac7_remove_passes_from_a_pipeline_and_records_it(repo: Path) -> None:
    sid = first(repo)
    code, _, err = sched(repo, "remove", sid, "--yes", signals=PIPELINE)
    assert code == 0, err
    assert store.read_log(sid)[-1]["caller"]["kind"] == "pipeline"


@pytest.mark.parametrize("verb", ["pause", "skip", "remove"])
def test_tck_ac7_pause_skip_and_remove_are_refused_from_an_unknown_caller(repo: Path, verb: str) -> None:
    sid = first(repo)
    before = home_hash()
    code, _, err = sched(repo, verb, sid, *(["--yes"] if verb == "remove" else []), signals=NO_TTY)
    assert code == 2 and "caller_unknown" in err, err
    assert home_hash() == before
