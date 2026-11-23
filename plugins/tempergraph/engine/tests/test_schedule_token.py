"""The fire token and caller kind `scheduler` (TCK-B17; TCK-AC4, AC 3)."""

from __future__ import annotations

import hashlib
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tempergraph.cli import schedule_cli
from tempergraph.provenance import CallerRefused, classify
from tempergraph.schedule import launch, policies, store, token
from tempergraph.store.layout import home_path

from .conftest import hash_tree
from .test_cli import cli, happy
from .test_schedule_cli import CATALOG, NOW, WARSAW, add, home_hash, saved

SLOT = "2026-11-24T08:00:00Z"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))


def fire_of(sid: str) -> str:
    return f"{sid}@20261124T0800Z"


def test_tck_ac4_add_makes_a_random_token_and_stores_only_its_sha256(repo: Path) -> None:
    code, doc, err = add(repo)
    assert code == 0, err
    sid = str(doc["schedule_id"])
    secret = token.read_token(sid)
    entry = store.read_entry(sid)
    assert secret and entry["token_digest"] == hashlib.sha256(secret.encode()).hexdigest()
    assert len(entry["token_digest"]) == 64 and token.matches(secret, entry["token_digest"])
    assert not token.matches(secret + "x", entry["token_digest"])
    other = saved(repo, "--name", "other")
    assert token.read_token(other) != secret  # random per schedule


def test_tck_ac4_the_token_is_in_a_private_file_and_in_no_other_file_stdout_or_stderr(repo: Path) -> None:
    code, doc, err = add(repo)
    sid = str(doc["schedule_id"])
    secret = token.read_token(sid)
    path = store.token_path(sid)
    assert path.is_file() and path.parent == store.entry_path(sid).parent  # beside the entry
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert secret not in err and secret not in str(doc)
    for p in sorted(home_path().rglob("*")):
        if p.is_file() and p != path:
            assert secret not in p.read_text(encoding="utf-8", errors="replace"), p


def test_tck_ac4_the_right_token_for_the_fire_id_classifies_as_scheduler_attested(repo: Path) -> None:
    sid = saved(repo)
    secret = token.read_token(sid)
    block = classify({"TEMPERGRAPH_SCHEDULE_TOKEN": secret}, False, schedule=fire_of(sid), entry_for_fire=token.entry_for_fire)
    assert (block["kind"], block["confidence"], block["host"]) == ("scheduler", "attested", "schedule")
    assert block["schedule"] == {"schedule_id": sid, "fire_id": fire_of(sid), "slot": SLOT,
                                 "created_by": {"kind": "person", "decided_by": "person"}}
    manual = policies.fire_id(sid, NOW, manual_at=NOW)
    again = classify({"TEMPERGRAPH_SCHEDULE_TOKEN": secret}, False, schedule=manual, entry_for_fire=token.entry_for_fire)
    assert again["schedule"]["slot"] == "2026-11-23T08:30:30Z"


def test_tck_ac4_a_wrong_or_missing_token_is_schedule_token_invalid(repo: Path) -> None:
    sid = saved(repo)
    with pytest.raises(CallerRefused) as exc:
        classify({"TEMPERGRAPH_SCHEDULE_TOKEN": "wrong"}, False, schedule=fire_of(sid), entry_for_fire=token.entry_for_fire)
    assert exc.value.code == "schedule_token_invalid"
    with pytest.raises(CallerRefused) as exc:  # a token with no fire id to check it against
        classify({"TEMPERGRAPH_SCHEDULE_TOKEN": token.read_token(sid)}, False, entry_for_fire=token.entry_for_fire)
    assert exc.value.code == "schedule_token_invalid"
    with pytest.raises(CallerRefused) as exc:  # a fire id that names no entry
        classify({"TEMPERGRAPH_SCHEDULE_TOKEN": token.read_token(sid)}, False, schedule="nobody-0000@20261124T0800Z",
                 entry_for_fire=token.entry_for_fire)
    assert exc.value.code == "schedule_token_invalid"


def test_tck_ac4_schedule_given_by_hand_without_a_token_is_schedule_reserved(repo: Path) -> None:
    sid = saved(repo)
    with pytest.raises(CallerRefused) as exc:
        classify({}, True, schedule=fire_of(sid), entry_for_fire=token.entry_for_fire)
    assert exc.value.code == "schedule_reserved"


def test_tck_ac4_a_run_with_a_bad_token_or_none_exits_2_and_writes_nothing(repo: Path) -> None:
    sid = saved(repo)
    before, repo_before = home_hash(), hash_tree(repo)
    code, _, err = cli(repo, happy(), "run", "demo", "daily digest", "--schedule", fire_of(sid),
                       signals=({"TEMPERGRAPH_SCHEDULE_TOKEN": "wrong"}, False), catalog=CATALOG)
    assert code == 2 and "schedule_token_invalid" in err, err
    code, _, err = cli(repo, happy(), "run", "demo", "daily digest", "--schedule", fire_of(sid), signals=({}, True),
                       catalog=CATALOG)
    assert code == 2 and "schedule_reserved" in err, err
    assert home_hash() == before and hash_tree(repo) == repo_before


def test_tck_ac4_a_run_with_the_right_token_starts_from_its_ticket_and_is_classified_as_scheduler(repo: Path) -> None:
    sid = saved(repo)
    secret = token.read_token(sid)
    slot = datetime(2026, 11, 24, 8, 0, tzinfo=UTC)
    start = policies.plan_start(store.read_entry(sid), slot, [])
    launch.write_ticket(store.read_entry(sid), start)
    code, doc, err = cli(repo, happy(), "run", "demo", "--schedule", fire_of(sid), "--task-id", start["thread"].split("/", 1)[1],
                         "--json", signals=({"TEMPERGRAPH_SCHEDULE_TOKEN": secret}, False), catalog=CATALOG)
    assert code == 0 and doc["thread_id"] == start["thread"], err
    assert secret not in err and secret not in str(doc)
    assert launch.read_ticket(fire_of(sid)) is None  # the run removed the ticket


def test_tck_ac4_a_run_whose_ticket_is_missing_exits_2_and_starts_nothing(repo: Path) -> None:
    sid = saved(repo)
    code, _, err = cli(repo, happy(), "run", "demo", "--schedule", fire_of(sid), "--task-id", "s-x",
                       signals=({"TEMPERGRAPH_SCHEDULE_TOKEN": token.read_token(sid)}, False), catalog=CATALOG)
    assert code == 2 and "schedule_ticket_invalid" in err
