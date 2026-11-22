"""T10.1: the directory sink, outbox, flush and sync, the fleet copy, `stats --source|--live` (CST-B10, CST-B12, CST-B13, CST-B11, CST-B14, CST-B15, CST-B16)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tempergraph.executors.standins import standin
from tempergraph.observe import rows, sinks
from tempergraph.store.layout import home_path, state_root_path

from .test_cli import cli
from .test_reports import paused_run
from .test_run import DRAFT, REVIEW, go, judge

CANARY = "canary"


def finished(repo: Path, task: str, **kw: object) -> None:
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), task=task, **kw)


def machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, sink: Path | None, **extra: object) -> Path:
    """Switches to the home folder of one simulated machine, with `sink` configured as `team`."""
    home = tmp_path / name / ".tempergraph"
    monkeypatch.setenv("TEMPERGRAPH_HOME", str(home))
    if sink is not None:
        (home / "config").mkdir(parents=True, exist_ok=True)
        (home / "config" / "sinks.json").write_text(json.dumps(
            {"schema_version": 1, "sinks": [{"name": "team", "kind": "directory", "path": str(sink), **extra}]}))
    return home


def files_under(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file()) if folder.exists() else []


def test_nothing_leaves_by_default(repo: Path, tmp_path: Path) -> None:  # CST-B1, CST-AC4
    outside = tmp_path / "outside"
    outside.mkdir()
    finished(repo, "T-1")
    home = home_path()
    assert not (home / "outbox").exists() and not (home / "fleet").exists()
    assert files_under(outside) == []
    assert len(list((home / "stats").glob("*.jsonl"))) == 1


def test_two_machines_one_folder(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # CST-B2, AC-2
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "inline")
    team = tmp_path / "share"
    team.mkdir()
    local: dict[str, float] = {}
    for name, tasks in (("a", ("T-1", "T-2", "T-3")), ("b", ("T-4", "T-5", "T-6"))):
        home = machine(monkeypatch, tmp_path, name, team)
        for t in tasks:
            finished(repo, t)
        found, _ = rows.read_rows(sorted((home / "stats").glob("*.jsonl")))
        local[json.loads((home / "machine.json").read_text())["machine_id"]] = sum(r["reported_cost_usd"] for r in found)
        assert not sinks.outbox(home, "team").exists()  # delivered at each exit
    for name in ("a", "b"):
        machine(monkeypatch, tmp_path, name, team)
        code, doc, err = cli(repo, None, "stats", "--source", "team", "--by", "machine")
        assert code == 0, err
        groups = doc["by"]["groups"]
        assert [g["runs"] for g in groups.values()] == [3, 3] and doc["totals"]["runs"] == 6
        assert doc["totals"]["reported_usd"] == pytest.approx(sum(local.values()))
    assert len({json.loads(p.read_text())["key"] for p in team.glob("sink.json")}) == 1


def test_offline_machine_delivers_once_in_order(repo: Path, tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:  # CST-B3, B6
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "inline")
    team = tmp_path / "share"  # not mounted yet
    home = machine(monkeypatch, tmp_path, "laptop", team)
    finished(repo, "T-1")
    finished(repo, "T-2")
    queued = [json.loads(x)["row_id"] for x in sinks.outbox(home, "team").read_text().splitlines()]
    assert len(queued) == 2 and not team.exists()  # nothing created on an unmounted path
    state = json.loads((home / "outbox" / "team.state.json").read_text())
    assert state["last_error"] == "unreachable"
    team.mkdir()
    finished(repo, "T-3")
    assert not sinks.outbox(home, "team").exists() and not (home / "outbox" / "team.state.json").exists()
    [runs] = list(team.glob("machines/*/runs/*.jsonl"))
    got = [json.loads(x)["row_id"] for x in runs.read_text().splitlines()]
    assert got[:2] == queued and len(got) == 3
    code, doc, _ = cli(repo, None, "stats")
    assert code == 0 and doc["totals"]["runs"] == 3  # the fleet copy and the local rows count each run once


def test_sink_failure_keeps_exit_and_outbox(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "inline")  # CST-B6
    team = tmp_path / "share"
    team.mkdir()
    home = machine(monkeypatch, tmp_path, "a", team)

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(sinks, "_append", boom)
    out = go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), task="T-1")
    assert int(out.exit_code) == 0
    assert len(sinks.outbox(home, "team").read_text().splitlines()) == 1
    st = home / "outbox" / "team.state.json"
    doc = json.loads(st.read_text())
    doc["first_failure_at"] = "2026-01-01T00:00:00Z"
    st.write_text(json.dumps(doc))
    code, status, _ = cli(repo, None, "status")
    assert code == 0 and "sink team has failed since" in status["warnings"][0]


def test_no_text_reaches_a_sink(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # CST-B5
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "inline")
    team = tmp_path / "share"
    team.mkdir()
    home = machine(monkeypatch, tmp_path, "a", team, include=["run", "heartbeat", "supervision", "session"])
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), task="PROJ-1-canary",
       alias="fix canary now", label="canary label")
    paused_run(repo, "PROJ-2-canary")
    assert cli(repo, None, "stats", "sync")[0] == 0
    leaked = [p for p in files_under(team) + files_under(home / "outbox") + files_under(home / "fleet")
              if CANARY in p.read_text(errors="replace") or "Release 1.2" in p.read_text(errors="replace")]
    assert leaked == []
    [runs] = list(team.glob("machines/*/runs/*.jsonl"))
    first = json.loads(runs.read_text().splitlines()[0])
    assert first["ticket"] is None and first["alias"] is None and len(first["thread_hash"]) == 32
    assert first["repo_id"] and first["repo_id"] != repo.name and first["user"] != "Test"


def test_tickets_and_names_only_when_set(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "inline")
    team = tmp_path / "share"
    team.mkdir()
    machine(monkeypatch, tmp_path, "a", team, tickets=True, repo="name", user="name")
    finished(repo, "T-7", alias="notes-run")
    [runs] = list(team.glob("machines/*/runs/*.jsonl"))
    row = json.loads(runs.read_text())
    assert (row["ticket"], row["repo_id"], row["user"], row["alias"]) == ("T-7", repo.name, "Test", "notes-run")


def test_live_across_machines(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # CST-B4
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "inline")
    team = tmp_path / "share"
    team.mkdir()
    machine(monkeypatch, tmp_path, "b", team)
    paused_run(repo, "T-1")
    [beat] = list(team.glob("machines/*/heartbeat.json"))
    doc = json.loads(beat.read_text())
    [t] = doc["threads"]
    assert t["state"] == "paused" and t["waiting_on"] == "person" and t["workflow"] == "demo"
    assert t["repo_id"] != repo.name and "thread_id" not in t
    old = json.loads(beat.read_text())
    old["at"] = "2026-01-01T00:00:00Z"  # forty minutes, or forty weeks: a paused wait never goes stale
    beat.write_text(json.dumps(old))
    machine(monkeypatch, tmp_path, "a", team)
    code, live, _ = cli(repo, None, "stats", "--source", "team", "--live")
    assert code == 0
    [run] = [r for r in live["runs"] if r["state"] == "paused"]
    assert run["workflow"] == "demo" and run["waiting_for_person_s"] > 0 and run["stale"] is False


def test_fleet_copy_serves_global_numbers(repo: Path, tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:  # CST-B7
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "inline")
    team = tmp_path / "share"
    team.mkdir()
    machine(monkeypatch, tmp_path, "b", team)
    finished(repo, "T-1")
    home_a = machine(monkeypatch, tmp_path, "a", team)
    finished(repo, "T-2")  # A's exit syncs B's row into A's fleet copy
    os.rename(team, tmp_path / "away")  # A goes offline
    code, doc, _ = cli(repo, None, "stats", "--by", "machine")
    assert code == 0 and doc["totals"]["runs"] == 2 and len(doc["by"]["groups"]) == 2
    machines = doc["synced"]["team"]["machines"]
    assert all(m["ago_s"] is not None for m in machines.values())
    rollups = list((home_a / "fleet" / "team" / "rollup").glob("*.json"))
    assert rollups and json.loads(rollups[0].read_text())["totals"]["runs"] == 2
    assert cli(repo, None, "stats", "sync")[1]["sinks"][0]["reachable"] is False


def test_config_errors_exit_2(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # CST-B10, CST-B14, CST-B8
    home = machine(monkeypatch, tmp_path, "a", None)
    (home / "config").mkdir(parents=True)
    dup = {"name": "team", "kind": "directory", "path": str(tmp_path)}
    (home / "config" / "sinks.json").write_text(json.dumps({"schema_version": 1, "sinks": [dup, dup]}))
    code, _, err = cli(repo, None, "stats", "flush")
    assert code == 2 and "two sinks named 'team'" in err
    (home / "config" / "sinks.json").write_text(json.dumps({"schema_version": 1, "sinks": [
        {"name": "otel", "kind": "otlp"}]}))
    assert cli(repo, None, "stats")[0] == 2
    (home / "config" / "sinks.json").unlink()
    assert cli(repo, None, "stats", "--source", "nope")[0] == 2


def test_state_root_sink_overrides_home(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = machine(monkeypatch, tmp_path, "a", tmp_path / "home-sink")
    cfg = state_root_path(repo) / "config"
    cfg.mkdir(parents=True)
    (cfg / "sinks.json").write_text(json.dumps({"schema_version": 1, "sinks": [
        {"name": "team", "kind": "directory", "path": str(tmp_path / "repo-sink")}]}))
    [s] = sinks.load(home, state_root_path(repo))
    assert s.path == tmp_path / "repo-sink" and s.user == "hash" and s.include == sinks.DEFAULT_KINDS  # `session` is opt-in


def test_normalize_origin() -> None:
    for url in ("git@github.com:Acme/Repo.git", "https://user:tok@GitHub.com/Acme/Repo", "ssh://git@github.com/Acme/Repo.git/"):
        assert sinks.normalize_origin(url) == "github.com/Acme/Repo"


def test_detached_flusher_delivers(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # CST-B10, CST-B12, CST-B13
    import time

    from tempergraph import detach

    monkeypatch.delenv("TEMPERGRAPH_FLUSHER", raising=False)
    team = tmp_path / "share"
    team.mkdir()
    home = machine(monkeypatch, tmp_path, "a", team)
    finished(repo, "T-1")
    deadline = time.monotonic() + 20
    while sinks.outbox(home, "team").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not sinks.outbox(home, "team").exists() and list(team.glob("machines/*/runs/*.jsonl"))
    assert detach.start("tempergraph.observe.sinks", ("sync",), home) is False  # constant words only
    assert detach.start("os", ("flush",), home) is False
