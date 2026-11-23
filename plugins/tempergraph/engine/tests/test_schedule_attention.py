"""`attention` and `trigger_stale` for schedules, and the hooks of a pause (TCK-B4, TCK-B7, TCK-B24; TCK-AC4; AC 6)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph import detach
from tempergraph.cli import schedule_cli
from tempergraph.docs import write_json
from tempergraph.schedule import credentials, launch, policies, store, tick, token
from tempergraph.store.layout import home_path

from .test_cli import cli, standin
from .test_run import DRAFT, judge, verdict_block
from .test_schedule_cli import CATALOG, NOW, WARSAW, home_hash, saved, sched
from .test_schedule_tick import Clock, Launcher

OK = credentials.Check(checked=[{"executor": "claude", "role": "step", "kinds": ["api_key"], "result": "ok"}])


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))


def attention(repo: Path) -> dict[str, Any]:
    code, doc, err = cli(repo, None, "attention", "--json", catalog=CATALOG)
    assert code == 0, err
    return dict(doc)


def test_tck_ac4_attention_lists_the_schedule_items_with_their_schedule_and_the_command_that_answers_them(repo: Path) -> None:
    paused, once, budget, refused = (saved(repo, "--name", n) for n in ("paused", "once", "budget", "refused"))
    entry = store.read_entry(paused)
    store.write_entry(dict(entry, state="paused"))
    store.append_event(paused, "paused", now=NOW, slot=None, reason="failures", failures=3)
    store.write_entry(dict(store.read_entry(once), when={**store.read_entry(once)["when"], "kind": "once"}))
    store.append_event(once, "missed", now=NOW, slot="2026-11-23T05:00:00Z", fire_id=f"{once}@20261123T0500Z", reason="catch_up")
    store.append_event(budget, "skipped", now=NOW, slot="2026-11-23T06:00:00Z", fire_id=f"{budget}@20261123T0600Z", reason="budget")
    store.append_event(refused, "refused", now=NOW, slot="2026-11-23T07:00:00Z", fire_id=f"{refused}@20261123T0700Z",
                       reason="credential", executor="claude", message="claude: no credential")
    before = home_hash()
    items = {i["kind"]: i for i in attention(repo)["items"]}
    assert home_hash() == before  # attention reads only
    assert set(items) == {"schedule_paused", "schedule_missed", "schedule_budget", "schedule_refused"}
    assert items["schedule_paused"]["schedule_id"] == paused and items["schedule_paused"]["command"] == f"tempergraph schedule resume {paused}"
    assert items["schedule_missed"]["command"] == f"tempergraph schedule fire {once}"
    assert items["schedule_refused"]["executor"] == "claude" and "claude" in items["schedule_refused"]["reason"]
    assert items["schedule_budget"]["schedule_id"] == budget
    code, text, _ = cli(repo, None, "attention", catalog=CATALOG)
    assert code == 0 and f"schedule_paused  {paused}" in text and f"tempergraph schedule resume {paused}" in text


def test_tck_ac4_a_resumed_schedule_and_a_removed_one_raise_nothing(repo: Path) -> None:
    sid = saved(repo)
    store.append_event(sid, "refused", now=NOW, slot="2026-11-23T07:00:00Z", fire_id=f"{sid}@20261123T0700Z", reason="credential")
    assert [i["kind"] for i in attention(repo)["items"]] == ["schedule_refused"]
    store.append_event(sid, "started", now=NOW, slot="2026-11-23T08:00:00Z", fire_id=f"{sid}@20261123T0800Z", thread="demo/s-x")
    assert attention(repo)["items"] == []  # the latest handled slot started: nothing is refused any more
    sched(repo, "remove", sid, "--yes")
    assert attention(repo)["items"] == []


def beat(age: timedelta, interval: int = 300) -> None:
    write_json(tick.heartbeat_path(home_path()), {"schema_version": 1, "last_tick_at": (NOW - age).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                  "engine_version": "x", "trigger": "loop", "interval_s": interval,
                                                  "credentials": {}, "deferred": [], "started": 0, "last_error": None})


def test_tck_ac4_a_heartbeat_older_than_three_intervals_shows_trigger_stale_in_list_status_and_attention_and_writes_nothing(
        repo: Path) -> None:
    saved(repo)
    beat(timedelta(minutes=20))  # 5-minute interval
    before = home_hash()
    _, listing, _ = sched(repo, "list", "--json")
    _, status, _ = cli(repo, None, "status", catalog=CATALOG)
    att = attention(repo)
    for doc in (listing, status, att):
        s = doc["trigger_stale"]
        assert s["kind"] == "trigger_stale" and s["age_s"] == 1200.0 and s["command"] == "tempergraph schedule trigger status"
    assert "trigger_stale" in sched(repo, "list")[1] and "schedule trigger status" in cli(repo, None, "attention", catalog=CATALOG)[1]
    assert home_hash() == before  # read-only verbs still write nothing


def test_tck_ac4_a_fresh_heartbeat_or_no_active_schedule_shows_no_trigger_stale(repo: Path) -> None:
    beat(timedelta(minutes=20))
    assert "trigger_stale" not in attention(repo)  # no active schedule
    sid = saved(repo)
    beat(timedelta(minutes=14))  # under three intervals
    assert "trigger_stale" not in attention(repo) and "trigger_stale" not in sched(repo, "list", "--json")[1]
    beat(timedelta(minutes=20))
    sched(repo, "pause", sid)
    assert "trigger_stale" not in attention(repo)  # a paused schedule needs no tick


@pytest.fixture
def started_children(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[str, ...]]]:
    seen: list[tuple[str, tuple[str, ...]]] = []
    monkeypatch.setattr(detach, "start", lambda module, words, home: seen.append((module, words)) or True)
    return seen


def test_tck_ac4_failures_that_pause_a_schedule_fire_the_schedule_paused_hook_with_facts(
        repo: Path, tmp_path: Path, started_children: list[tuple[str, tuple[str, ...]]], monkeypatch: pytest.MonkeyPatch) -> None:
    assert cli(repo, None, "hooks", "add", "schedule_paused", "--", "true", catalog=CATALOG)[0] == 0  # accepted now
    sid = saved(repo, "--pause-after-failures", "1", "--name", "digest")
    entry = store.read_entry(sid)
    gone = credentials.check([{"executor": "claude", "role": "step"}], {"claude": frozenset()}, at_fire=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    hooked: list[str] = []

    def on_hook(event: str, e: dict[str, Any], facts: dict[str, Any]) -> None:
        from tempergraph.observe import hooks

        hooked.append(event)
        hooks.on_schedule_event(repo / ".tempergraph", event, "demo", str(e["schedule_id"]), facts)

    clock = Clock(NOW.replace(day=24, hour=8, minute=1, second=0))
    tick.run_tick(home_path(), tick.Edges(clock=clock, launcher=Launcher(home_path()), resolver=lambda e: gone,
                                          repo_ok=lambda r: True, on_hook=on_hook))
    assert hooked == ["schedule_paused"] and store.read_entry(sid)["state"] == "paused" and entry
    facts = list((repo / ".tempergraph" / "runs" / "demo" / f"schedule-{sid}" / "hooks").glob("schedule_paused-*.facts.json"))
    assert len(facts) == 1 and f'"schedule_id": "{sid}"' in facts[0].read_text(encoding="utf-8")
    assert ("tempergraph.observe.hooks", ("drain",)) in started_children  # the one drain child runs the registered hook


def test_tck_ac4_a_scheduled_run_that_pauses_exits_3_and_fires_the_paused_hook(
        repo: Path, started_children: list[tuple[str, tuple[str, ...]]]) -> None:
    assert cli(repo, None, "hooks", "add", "paused", "--", "true", catalog=CATALOG)[0] == 0
    sid = saved(repo)
    entry = store.read_entry(sid)
    start = policies.plan_start(entry, NOW.replace(day=24, hour=8, minute=0, second=0), [])
    launch.write_ticket(entry, start)
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    code, _, err = cli(repo, ex, "run", "demo", "--schedule", start["fire_id"], "--task-id", start["thread"].split("/", 1)[1],
                       signals=({token.ENV_VAR: str(token.read_token(sid))}, False), catalog=CATALOG)
    assert code == 3, err
    hooks_dir = repo / ".tempergraph" / "runs" / "demo" / start["thread"].split("/", 1)[1] / "hooks"
    assert list(hooks_dir.glob("paused-*.facts.json")) and ("tempergraph.observe.hooks", ("drain",)) in started_children
