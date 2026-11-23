"""What a scheduled run writes (TCK-B17, TCK-B24; TCK-AC4; AC 6) with a scripted run through `run --schedule`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tempergraph.cli import schedule_cli
from tempergraph.observe import rows, sinks
from tempergraph.run.events import records
from tempergraph.schedule import launch, policies, store, token
from tempergraph.store.layout import home_path

from .test_cli import cli, happy
from .test_schedule_cli import CATALOG, NOW, WARSAW, saved

SLOT = datetime(2026, 11, 24, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))


def scheduled_run(repo: Path) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
    """A scheduled run as the tick starts it: a ticket, the fire id and the token in the environment."""
    sid = saved(repo)
    entry = store.read_entry(sid)
    start = policies.plan_start(entry, SLOT, [])
    launch.write_ticket(entry, start)
    secret = str(token.read_token(sid))
    code, doc, err = cli(repo, happy(), "run", "demo", "--schedule", start["fire_id"], "--task-id", start["thread"].split("/", 1)[1],
                         "--json", signals=({token.ENV_VAR: secret}, False), catalog=CATALOG)
    assert code == 0, err
    return sid, start, secret, doc


def test_tck_ac4_the_status_document_has_origin_and_the_schedule_block(repo: Path) -> None:
    sid, start, _, _ = scheduled_run(repo)
    code, st, _ = cli(repo, None, "status", catalog=CATALOG)
    (row,) = st["threads"]
    assert code == 0 and row["origin"] == "schedule" and row["thread_id"] == start["thread"]
    assert row["schedule"] == {"schedule_id": sid, "fire_id": start["fire_id"], "slot": "2026-11-24T08:00:00Z"}


def test_tck_ac4_run_started_has_origin_the_schedule_block_and_the_scheduler_caller(repo: Path) -> None:
    sid, start, _, _ = scheduled_run(repo)
    task = start["thread"].split("/", 1)[1]
    (started,) = [r for r in records(repo / ".tempergraph" / "runs" / "demo" / task / "run.jsonl") if r["kind"] == "run_started"]
    assert started["origin"] == "schedule"
    assert started["schedule"] == {"schedule_id": sid, "fire_id": start["fire_id"], "slot": "2026-11-24T08:00:00Z"}
    caller = started["caller"]
    assert (caller["kind"], caller["confidence"], caller["host"]) == ("scheduler", "attested", "schedule")
    assert caller["schedule"]["created_by"] == {"kind": "person", "decided_by": "person"}
    assert started["label"] == start["label"]  # from the ticket


def test_tck_ac4_the_stats_row_and_the_sink_row_carry_origin_and_the_schedule_id_as_an_hmac(repo: Path, tmp_path: Path) -> None:
    sid, _, _, _ = scheduled_run(repo)
    found, _ = rows.read_rows(sorted((home_path() / "stats").glob("*.jsonl")))
    (row,) = [r for r in found if r.get("kind") == "run"]
    assert row["origin"] == "schedule" and row["schedule_id"] == sid
    key = b"k" * 32
    out = sinks.sink_row(row, sinks.Sink(name="share", kind="folder", path=tmp_path / "share"), key)
    assert out["origin"] == "schedule" and out["schedule_id"] == sinks.digest(key, sid) and out["schedule_id"] != sid


def test_tck_ac4_the_token_is_in_no_record_log_ledger_row_ticket_or_environment(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    monkeypatch.setenv(token.ENV_VAR, "placeholder")
    sid = saved(repo)
    secret = str(token.read_token(sid))
    start = policies.plan_start(store.read_entry(sid), SLOT, [])
    launch.write_ticket(store.read_entry(sid), start)
    monkeypatch.setenv(token.ENV_VAR, secret)
    code, _, err = cli(repo, happy(), "run", "demo", "--schedule", start["fire_id"], "--task-id", start["thread"].split("/", 1)[1],
                       signals=({token.ENV_VAR: secret}, False), catalog=CATALOG)
    assert code == 0 and secret not in err
    assert token.ENV_VAR not in os.environ  # no step session of this process inherits it
    for base in (repo / ".tempergraph", home_path()):
        for p in sorted(base.rglob("*")):
            if p.is_file() and p != store.token_path(sid):
                assert secret not in p.read_text(encoding="utf-8", errors="replace"), p
    assert launch.read_ticket(start["fire_id"]) is None  # the ticket is gone, with the request it held


def test_tck_ac4_a_scheduled_run_that_pauses_exits_3_and_the_thread_keeps_its_fire(repo: Path) -> None:
    from .test_cli import standin
    from .test_run import DRAFT, judge, verdict_block

    sid = saved(repo)
    entry = store.read_entry(sid)
    start = policies.plan_start(entry, SLOT, [])
    launch.write_ticket(entry, start)
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    code, _, err = cli(repo, ex, "run", "demo", "--schedule", start["fire_id"], "--task-id", start["thread"].split("/", 1)[1],
                       signals=({token.ENV_VAR: str(token.read_token(sid))}, False), catalog=CATALOG)
    assert code == 3, err  # a pause waits for a person (CLI-B4)
    _, st, _ = cli(repo, None, "status", catalog=CATALOG)
    assert st["threads"][0]["state"] == "paused" and st["threads"][0]["schedule"]["schedule_id"] == sid
