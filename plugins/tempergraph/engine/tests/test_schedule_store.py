"""The schedule entry and its fire log in the home store (SCH-B13, SCH-B14, SCH-B28; SCH-AC8)."""

from __future__ import annotations

import io
import json
import os
import re
import stat
from datetime import UTC, datetime

import pytest

from tempergraph.schedule import store
from tempergraph.store.layout import home_path

NOW = datetime(2026, 11, 23, 8, 0, tzinfo=UTC)
SECRET = "ship the SECRET-REQUEST-TEXT to prod"
CALLER = {"kind": "person", "confidence": "observed", "decided_by": "person", "relay": "direct"}


def entry(sid: str = "digest-1a2b", **kw: object) -> dict[str, object]:
    base: dict[str, object] = dict(
        schedule_id=sid, name="digest", target={"kind": "workflow", "workflow": "demo", "repo": "/r", "request": SECRET,
                                                  "inputs": {"note": SECRET}},
        when={"input": {"format": "--every", "value": "PT2H"}, "phrase": None, "kind": "recur",
              "rule": "FREQ=HOURLY;INTERVAL=2", "zone": "UTC", "starts": "2026-11-23T08:00", "ends": None,
              "count": None},
        options={"flag": {}, "profiles": []}, run_cost_cap_usd=3.0, budget=None, catch_up="latest",
        catch_up_window_s=3600, overlap="skip", max_live=1, pause_after_failures=3,
        created={"at": "2026-11-23T08:00:00Z", "caller": CALLER, "from": "schedule add"}, now=NOW)
    base.update(kw)
    return store.build_entry(**base)  # type: ignore[arg-type]


def test_sch_ac8_the_entry_is_written_owner_only_under_the_home_store() -> None:
    e = entry()
    path = store.write_entry(e)
    assert path == home_path() / "schedules" / "digest-1a2b" / "entry.json"  # TEMPERGRAPH_HOME is honoured
    assert stat.S_IMODE(path.stat().st_mode) == 0o600  # SCH-B14
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert store.read_entry("digest-1a2b") == e
    assert not [p for p in path.parent.iterdir() if p.name != "entry.json"]  # no temporary file left behind


def test_sch_ac8_the_entry_holds_every_field_of_sch_b14() -> None:
    e = entry()
    for key in ("schema_version", "schedule_id", "name", "description", "state", "target", "when", "options",
                "run_cost_cap_usd", "budget", "catch_up", "catch_up_window_s", "overlap", "max_live",
                "pause_after_failures", "executors_checked", "created", "edited", "token_digest", "next_slot",
                "last_fire"):
        assert key in e, key
    assert e["schema_version"] == 1 and e["state"] == "active"
    assert e["executors_checked"] == [] and e["token_digest"] is None  # unset until `add` gives them (TCK-B17, TCK-B19)
    assert e["edited"] is None and e["last_fire"] is None
    assert len(str(e["description"])) <= 200 and e["max_live"] == 1 and e["pause_after_failures"] == 3
    assert e["next_slot"] == "2026-11-23T08:00:00Z"  # derived: readers trust the fire log over it


def test_tck_ac4_build_entry_keeps_a_given_digest_and_the_checked_executors() -> None:  # TCK-AC4
    digest = "ab" * 32
    checked = [{"executor": "claude", "kinds": ["api_key"], "result": "ok"}]
    e = entry(token_digest=digest, executors_checked=checked)
    assert e["token_digest"] == digest and e["executors_checked"] == checked


def test_tck_ac4_the_token_file_is_beside_the_entry_and_owner_only() -> None:  # TCK-AC4
    from tempergraph.schedule import token

    path = store.token_path("digest-1a2b")
    assert path == store.entry_path("digest-1a2b").parent / "token" and path.parent == home_path() / "schedules" / "digest-1a2b"
    secret = token.make_token()
    assert len(secret) >= 32 and token.digest(secret) == token.digest(secret) and len(token.digest(secret)) == 64
    written = token.write_token("digest-1a2b", secret)
    assert written == path and token.read_token("digest-1a2b") == secret
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert token.read_token("nobody-0000") is None


def test_sch_ac8_the_write_is_atomic(monkeypatch: pytest.MonkeyPatch) -> None:
    path = store.write_entry(entry())
    before = path.read_text(encoding="utf-8")

    def boom(*a: object, **k: object) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="disk gone"):
        store.write_entry(entry(name="other"))
    assert path.read_text(encoding="utf-8") == before  # the old entry stands whole
    assert [p.name for p in path.parent.iterdir()] == ["entry.json"]


def test_sch_ac8_a_schedule_id_is_name_dash_four_hex_and_at_most_64() -> None:
    sid = store.new_schedule_id("Daily Digest!", set())
    assert re.fullmatch(r"daily-digest-[0-9a-f]{4}", sid)
    long = store.new_schedule_id("x" * 200, set())
    assert len(long) <= 64 and re.fullmatch(r"x+-[0-9a-f]{4}", long)
    taken: set[str] = set()
    for _ in range(50):
        taken.add(store.new_schedule_id("a", taken))
    assert len(taken) == 50  # never an id that is in use
    draws = iter(["0001", "0001", "0002"])
    assert store.new_schedule_id("a", {"a-0001"}, hexgen=lambda: next(draws)) == "a-0002"  # drawn again until unused
    assert store.slugify("  ") == "schedule"


def test_sch_ac8_the_fire_log_appends_json_lines_of_the_sch_b28_kinds() -> None:
    sid = "digest-1a2b"
    for kind in store.LOG_KINDS:
        assert store.append_event(sid, kind, now=NOW, slot="2026-11-23T08:00:00Z", fire_id=f"{sid}@20261123T0800Z") is not None
    lines = (home_path() / "schedules" / sid / "fires.jsonl").read_text(encoding="utf-8").splitlines()
    docs = [json.loads(x) for x in lines]
    assert [d["kind"] for d in docs] == list(store.LOG_KINDS) and [d["seq"] for d in docs] == list(range(1, 13))
    assert set(store.LOG_KINDS) == {"created", "edited", "paused", "resumed", "due", "started", "skipped", "queued",
                                    "missed", "refused", "ended", "removed"}
    for d in docs:
        assert d["at"] == "2026-11-23T08:00:00Z" and d["slot"] == "2026-11-23T08:00:00Z"
        assert d["fire_id"] == f"{sid}@20261123T0800Z"
    assert stat.S_IMODE((home_path() / "schedules" / sid / "fires.jsonl").stat().st_mode) == 0o600
    assert store.read_log(sid) == docs


def test_sch_ac8_person_made_events_carry_the_caller_block() -> None:
    store.append_event("s-0001", "paused", now=NOW, reason="person", caller=CALLER)
    store.append_event("s-0001", "due", now=NOW, slot="2026-11-23T08:00:00Z")
    a, b = store.read_log("s-0001")
    assert a["caller"] == CALLER and a["reason"] == "person" and "caller" not in b


def test_sch_ac8_a_failed_log_write_goes_to_standard_error_and_the_call_returns() -> None:
    d = home_path() / "schedules" / "s-0002"
    (d / "fires.jsonl").mkdir(parents=True)  # a folder where the log should be: the append fails
    err = io.StringIO()
    assert store.append_event("s-0002", "due", now=NOW, err=err) is None  # no exception: the verb goes on
    assert "s-0002" in err.getvalue() and "fire log" in err.getvalue()


def test_sch_ac8_no_log_line_carries_request_input_or_feedback_text() -> None:
    e = entry()
    store.write_entry(e)
    sid = str(e["schedule_id"])
    store.append_event(sid, "created", now=NOW, caller=CALLER, when=e["when"])  # metadata: the canonical form
    store.append_event(sid, "edited", now=NOW, caller=CALLER, changed=["when"], old={"rule": "a"}, new={"rule": "b"})
    store.append_event(sid, "started", now=NOW, slot="2026-11-23T08:00:00Z", thread="demo/s-digest-202611230800")
    store.append_event(sid, "ended", now=NOW, exit=0, outcome="finished",
                       cost={"reported": 0.5, "estimated": 0.5, "incomplete": False})
    for forbidden in ("request", "inputs", "input", "feedback", "args"):
        with pytest.raises(ValueError, match=forbidden):
            store.append_event(sid, "created", now=NOW, **{forbidden: SECRET})
    log = (home_path() / "schedules" / sid / "fires.jsonl").read_text(encoding="utf-8")
    assert "SECRET-REQUEST-TEXT" not in log and len(log.splitlines()) == 4
    assert "SECRET-REQUEST-TEXT" in (home_path() / "schedules" / sid / "entry.json").read_text(encoding="utf-8")  # only here


def test_sch_ac8_the_description_is_the_scrubbed_request_cut_to_200_characters() -> None:
    e = entry(target={"kind": "workflow", "workflow": "demo", "repo": "/r", "request": "r" * 500, "inputs": {}})
    assert len(e["description"]) == 200  # type: ignore[arg-type]


def test_sch_ac8_entries_list_in_id_order_and_a_missing_one_is_reported() -> None:
    store.write_entry(entry("b-0002"))
    store.write_entry(entry("a-0001"))
    assert [e["schedule_id"] for e in store.list_entries()] == ["a-0001", "b-0002"]
    with pytest.raises(FileNotFoundError):
        store.read_entry("nope-0000")
    assert store.list_entries(home=home_path() / "elsewhere") == []
