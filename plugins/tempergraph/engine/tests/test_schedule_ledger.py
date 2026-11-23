"""The scheduled-run ledger `~/.tempergraph/schedules/runs.jsonl` and `schedule runs` (TCK-B13, TCK-B23; TCK-AC5)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.cli import schedule_cli
from tempergraph.schedule import ledger, store
from tempergraph.store.layout import home_path

from .test_cli import cli, happy
from .test_schedule_cli import CATALOG, NOW, WARSAW, home_hash, saved, sched


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))


def fire(entry: dict[str, Any], day: int, outcome: str = "started", *, root: Path | None = None, reason: str | None = None,
         at: Any = None) -> dict[str, Any]:
    slot = NOW.replace(day=day, hour=8, minute=0, second=0)
    return ledger.fire_row(entry, fire_id=f"{entry['schedule_id']}@202611{day:02d}T0800Z", slot=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           outcome=outcome, at=at or slot, reason=reason, thread_id=f"demo/s-{day}", state_root=root,
                           trigger="tick")


def test_tck_ac5_a_fire_is_one_row_with_the_fields_of_tck_b23_under_the_home_store(repo: Path) -> None:
    sid = saved(repo)
    entry = store.read_entry(sid)
    ledger.append(fire(entry, 24, root=repo / "state"))
    assert ledger.ledger_path() == home_path() / "schedules" / "runs.jsonl"  # TEMPERGRAPH_HOME is honoured
    (row,) = ledger.read()
    for key in ("fire_id", "schedule_id", "name", "slot", "fired_at", "target", "created_from", "outcome", "thread_id",
                "orchestration_id", "state_root", "trigger"):
        assert key in row, key
    assert row["target"] == {"kind": "workflow", "workflow": "demo", "repo": str(repo), "repo_name": "repo"}
    assert (row["schedule_id"], row["name"], row["created_from"], row["outcome"], row["trigger"]) == (
        sid, "demo", "schedule add", "started", "tick")
    assert row["state_root"] == str(repo / "state") and row["ended"] is None


def test_tck_ac5_an_ended_row_updates_its_started_row_and_the_rest_are_skipped_missed_or_refused(repo: Path) -> None:
    entry = store.read_entry(saved(repo))
    for day, outcome, reason in ((24, "started", None), (25, "skipped", "overlap"), (26, "missed", "catch_up"),
                                 (27, "refused", "credential")):
        ledger.append(fire(entry, day, outcome, reason=reason))
    ledger.settle(f"{entry['schedule_id']}@20261124T0800Z", {"exit": 0, "outcome": "finished",
                                                              "cost": {"estimated": 0.5, "reported": 0.5}}, at=NOW)
    rows = ledger.read()
    assert [(r["outcome"], r["reason"]) for r in rows] == [("started", None), ("skipped", "overlap"), ("missed", "catch_up"),
                                                          ("refused", "credential")]
    assert rows[0]["ended"] == {"exit": 0, "outcome": "finished", "cost": {"estimated": 0.5, "reported": 0.5},
                                "at": "2026-11-23T08:30:30Z"}
    assert all(r["ended"] is None for r in rows[1:])
    assert len((home_path() / "schedules" / "runs.jsonl").read_text(encoding="utf-8").splitlines()) == 5  # four, plus the `ended`


def test_tck_ac5_a_row_holds_metadata_only_and_is_scrubbed(repo: Path) -> None:
    entry = store.read_entry(saved(repo))
    row = fire(entry, 24)
    with pytest.raises(ValueError, match="metadata only"):
        ledger.append(dict(row, request="the request text"))
    ledger.append(dict(row, reason="token sk-ant-api03-" + "A" * 40))
    text = (home_path() / "schedules" / "runs.jsonl").read_text(encoding="utf-8")
    assert "sk-ant-api03-" + "A" * 40 not in text


def test_tck_ac5_removing_the_schedule_pruning_a_state_root_and_a_plain_prune_delete_no_row(repo: Path) -> None:
    sid = saved(repo)
    entry = store.read_entry(sid)
    root = repo / "state"
    root.mkdir()
    ledger.append(fire(entry, 24, root=root))
    before = (home_path() / "schedules" / "runs.jsonl").read_text(encoding="utf-8")
    assert sched(repo, "remove", sid, "--yes")[0] == 0
    root.rmdir()
    code, _, err = cli(repo, happy(), "store", "prune", "--older-than", "0", catalog=CATALOG)
    assert code == 0, err
    assert (home_path() / "schedules" / "runs.jsonl").read_text(encoding="utf-8") == before
    assert len(ledger.read()) == 1


def test_tck_ac5_store_prune_with_schedules_and_older_than_shortens_the_ledger_only(repo: Path) -> None:
    entry = store.read_entry(saved(repo))
    old, new = NOW - timedelta(days=40), NOW - timedelta(days=2)
    ledger.append(fire(entry, 1, at=old))
    ledger.append(fire(entry, 21, at=new))
    ledger.settle(f"{entry['schedule_id']}@20261101T0800Z", {"exit": 0, "outcome": "finished", "cost": {}}, at=old)
    code, _, err = cli(repo, happy(), "store", "prune", "--schedules", "--older-than", "30", catalog=CATALOG)
    assert code == 0, err
    rows = ledger.read()
    assert [r["slot"][:10] for r in rows] == ["2026-11-21"]  # the old fire and its `ended` row go together
    assert len((home_path() / "schedules" / "runs.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_tck_ac5_every_slot_the_tick_handles_yields_one_row_and_a_started_fire_gets_its_ended_update(tmp_path: Path) -> None:
    from tempergraph.schedule import tick

    from .test_schedule_tick import Launcher, edges, make

    home = home_path()
    make("digest-0001", repo=tmp_path)  # 06:00 to 08:00 missed, 09:00 started
    make("digest-0002", repo=tmp_path, state="active", overlap="skip")
    store.append_event("digest-0002", "started", now=NOW, slot="2026-11-23T08:00:00Z", fire_id="digest-0002@20261123T0800Z",
                       thread="demo/s-digest-0002-20261123T0800")
    finished = {"state": "finished", "exit_code": 0, "cost": {"reported": 0.2}}
    result = tick.run_tick(home, edges(home, launcher=Launcher(home), status_of=lambda e, t: finished))
    rows = ledger.read()
    handled = [(r["schedule_id"], r["slot"], r["outcome"]) for r in rows]
    assert len(handled) == len(set(handled)) == 4 + 3  # each slot once: 06:00 to 08:00 missed and 09:00 started, and 06:00, 07:00, 09:00
    assert {r["outcome"] for r in rows} == {"missed", "started"} and result.settled == ["digest-0002@20261123T0800Z"]
    raw = (home / "schedules" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert sum('"kind": "ended"' in ln for ln in raw) == 1  # one `ended` row, laid over its started fire when read
    started = next(r for r in rows if r["schedule_id"] == "digest-0001" and r["outcome"] == "started")
    assert started["ended"] is None and started["thread_id"] == "demo/s-digest-0001-20261123T0900"


def runs(cwd: Path, *argv: str) -> tuple[int, Any, str]:
    return cli(cwd, happy(), "schedule", "runs", "--json", *argv, catalog=CATALOG)


def test_tck_ac5_schedule_runs_reads_from_any_directory_and_filters(repo: Path, tmp_path: Path) -> None:
    api = store.read_entry(saved(repo, "--name", "api"))
    web = store.read_entry(saved(repo, "--name", "web"))
    gone = tmp_path / "gone-root"
    ledger.append(fire(api, 24, root=repo))
    ledger.append(fire(api, 25, "skipped", reason="overlap"))
    ledger.append(fire(web, 26, "refused", root=gone, reason="credential"))
    ledger.settle(f"{api['schedule_id']}@20261124T0800Z", {"exit": 0, "outcome": "finished", "cost": {"estimated": 1.0}}, at=NOW)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    before = home_hash()
    code, doc, err = runs(elsewhere)  # not a repository: the ledger is machine-wide
    assert code == 0 and [r["schedule_id"] for r in doc["runs"]] == [api["schedule_id"]] * 2 + [web["schedule_id"]], err
    assert [r["fire_id"] for r in runs(elsewhere, "--schedule", web["schedule_id"])[1]["runs"]] == [
        f"{web['schedule_id']}@20261126T0800Z"]
    assert len(runs(elsewhere, "--repo", str(repo))[1]["runs"]) == 3
    assert runs(elsewhere, "--repo", str(tmp_path / "nowhere"))[1]["runs"] == []
    assert len(runs(elsewhere, "--workflow", "demo")[1]["runs"]) == 3 and runs(elsewhere, "--workflow", "other")[1]["runs"] == []
    assert [r["outcome"] for r in runs(elsewhere, "--outcome", "skipped")[1]["runs"]] == ["skipped"]
    assert len(runs(elsewhere, "--since", "2026-11-25")[1]["runs"]) == 2
    assert home_hash() == before  # read-only


def test_tck_ac5_a_row_whose_state_root_is_gone_is_marked_records_gone(repo: Path, tmp_path: Path) -> None:
    entry = store.read_entry(saved(repo))
    ledger.append(fire(entry, 24, root=repo))
    ledger.append(fire(entry, 26, root=tmp_path / "deleted"))
    ledger.append(fire(entry, 27, "missed", reason="catch_up"))  # no thread, no state root: nothing is gone
    _, doc, _ = runs(repo)
    assert [r["records_gone"] for r in doc["runs"]] == [False, True, False]
    code, plain, _ = cli(repo, happy(), "schedule", "runs", catalog=CATALOG)
    assert code == 0 and "records_gone" in plain and plain.count("\n") == 3
    _, detail, _ = runs(repo, "--detail")
    assert detail["runs"][1]["detail"] is None and "detail" in detail["runs"][0]

