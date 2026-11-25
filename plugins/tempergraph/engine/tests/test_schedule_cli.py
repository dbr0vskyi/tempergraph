"""The `schedule` verbs through `main` (SCH-B1, SCH-B8, SCH-B10, SCH-B12, SCH-B13, SCH-B19, SCH-B22, SCH-B24, SCH-B25,
SCH-B27, SCH-B33; SCH-AC3, SCH-AC4, SCH-AC6, SCH-AC12) and the engine naming no workflow package (ADR `the-engine-names-no-workflow`)."""

from __future__ import annotations

import random
import re
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.catalog import Catalog
from tempergraph.cli import schedule_cli
from tempergraph.schedule import store
from tempergraph.store.layout import home_path

from .conftest import ENGINE_ROOT, hash_tree, workflow_names
from .fixtures.workflows import named, two_step
from .test_cli import PERSON, cli, happy

NOW = datetime(2026, 11, 23, 8, 30, 30, tzinfo=UTC)  # a Monday; 09:30 in Warsaw, after that day's 09:00 slots
NO_TTY = ({}, False)
WARSAW = "Europe/Warsaw"
WEEKDAYS = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0"
DAILY = "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
CATALOG = Catalog(specs={"demo": two_step(), "capped": named(two_step(run_cost_cap_usd=10.0), "capped")})


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))


def sched(repo: Path, *argv: str, signals: Any = PERSON, catalog: Catalog | None = None) -> tuple[int, Any, str]:
    return cli(repo, happy(), "schedule", *argv, signals=signals, catalog=catalog or CATALOG)


def add(repo: Path, *extra: str, signals: Any = PERSON, rule: str = DAILY) -> tuple[int, Any, str]:
    return sched(repo, "add", "demo", "daily digest", "--rrule", rule, "--tz", WARSAW, "--run-cost-cap", "3", "--yes",
                 "--json", *extra, signals=signals)


def saved(repo: Path, *extra: str, rule: str = DAILY) -> str:
    code, doc, err = add(repo, *extra, rule=rule)
    assert code == 0 and doc["status"] == "saved", err
    return str(doc["schedule_id"])


def home_hash() -> dict[str, str]:
    return hash_tree(home_path())


def no_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """From here on, starting a process fails the test (called after the setup, which runs git)."""

    def boom(*a: object, **k: object) -> None:
        raise AssertionError("a process was started")

    monkeypatch.setattr(subprocess, "Popen", boom)


# --- SCH-AC3: exact formats never ask ----------------------------------------------------------------------------


def _corpus(rnd: random.Random) -> list[tuple[str, str, str | None]]:
    """1,000 valid values: (flag, value, the phrase that says the same, where one exists)."""
    out: list[tuple[str, str, str | None]] = []
    for _ in range(250):
        d = date(2026, 11, 24) + timedelta(days=rnd.randrange(0, 380))
        h, m = rnd.randrange(24), rnd.choice((0, 15, 30, 45, rnd.randrange(60)))
        out.append(("--at", f"{d.isoformat()}T{h:02d}:{m:02d}", f"{d.isoformat()} {h:02d}:{m:02d}"))
    for _ in range(250):
        h, m = rnd.randrange(24), rnd.choice((0, 15, 30, 45))
        pick = rnd.randrange(6)
        if pick == 0:
            out.append(("--rrule", f"FREQ=DAILY;BYHOUR={h};BYMINUTE={m}", f"every day at {h:02d}:{m:02d}"))
        elif pick == 1:
            out.append(("--rrule", f"FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR={h};BYMINUTE={m}",
                        f"every weekday at {h:02d}:{m:02d}"))
        elif pick == 2:
            days = ",".join(rnd.sample(("MO", "TU", "WE", "TH", "FR", "SA", "SU"), rnd.randrange(1, 4)))
            out.append(("--rrule", f"RRULE:FREQ=WEEKLY;BYDAY={days};BYHOUR={h},{(h + 5) % 24};BYMINUTE={m}", None))
        elif pick == 3:
            out.append(("--rrule", f"FREQ=MONTHLY;BYMONTHDAY={rnd.choice((1, 5, 15, 28))};BYHOUR={h};BYMINUTE={m}", None))
        elif pick == 4:
            out.append(("--rrule", f"FREQ=MONTHLY;BYDAY={rnd.choice((1, 2, 3, 4, -1))}{rnd.choice(('MO', 'TH', 'SU'))};"
                                   f"BYHOUR={h};BYMINUTE={m}", None))
        else:
            out.append(("--rrule", f"FREQ=HOURLY;INTERVAL={rnd.choice((2, 3, 4))};BYMINUTE=0,30", None))
    for _ in range(250):
        pick = rnd.randrange(4)
        if pick == 0:
            n = rnd.randrange(15, 60)
            out.append(("--every", f"PT{n}M", f"every {n} minutes"))
        elif pick == 1:
            n = rnd.randrange(1, 49)
            out.append(("--every", f"PT{n}H", f"every {n} hours" if n > 1 else "hourly"))
        elif pick == 2:
            out.append(("--every", f"P{rnd.randrange(1, 10)}D", None))
        else:
            out.append(("--every", f"PT{rnd.randrange(1, 20)}H{rnd.choice((15, 30, 45))}M", None))
    for _ in range(250):
        h, m = rnd.randrange(24), rnd.choice((0, 15, 30, 45))
        pick = rnd.randrange(5)
        if pick == 0:
            out.append(("--cron", f"{m} {h} * * *", f"every day at {h:02d}:{m:02d}"))
        elif pick == 1:
            out.append(("--cron", f"{m} {h} * * 1-5", f"every weekday at {h:02d}:{m:02d}"))
        elif pick == 2:
            out.append(("--cron", f"*/15 {rnd.randrange(0, 8)}-{rnd.randrange(8, 23)} * * *", None))
        elif pick == 3:
            out.append(("--cron", f"{m} {h} {rnd.choice(('1', '1,15', '*/10', '1-7'))} * *", None))
        else:
            out.append(("--cron", f"{m} * * * {rnd.choice(('mon-fri', 'sat,sun', '0', '3-5'))}", None))
    assert len(out) == 1000
    return out


def test_sch_ac3_exact_formats_with_yes_and_no_terminal_never_exit_3_in_a_corpus_of_1000(repo: Path) -> None:
    before = home_hash()
    for flag, value, _twin in _corpus(random.Random(1123)):
        code, _, err = sched(repo, "add", "demo", "daily digest", flag, value, "--tz", WARSAW, "--run-cost-cap", "3",
                             "--yes", "--check", signals=NO_TTY)
        assert code == 0, (flag, value, err)  # never 3, and in fact every valid value passes
    assert home_hash() == before  # `--check` saved nothing


def test_sch_ac3_each_value_gives_the_canonical_form_of_its_phrase_twin(repo: Path) -> None:
    twins = [(f, v, p) for f, v, p in _corpus(random.Random(1123)) if p]
    assert len(twins) > 400
    for flag, value, phrase in twins:
        code, exact, err = sched(repo, "parse", flag, value, "--tz", WARSAW, "--json")
        code2, words, err2 = sched(repo, "parse", phrase, "--tz", WARSAW, "--json")
        assert code == 0 and code2 == 0, (flag, value, phrase, err, err2)
        assert exact["canonical"] == words["canonical"] and exact["assumptions"] == words["assumptions"], (value, phrase)
        assert exact["sentence"] == words["sentence"] and exact["slots"] == words["slots"]


def test_sch_ac3_a_saved_exact_schedule_has_the_echo_of_its_word_grammar_twin(repo: Path) -> None:
    digest = Catalog(specs={"digest": named(two_step(), "digest")})
    code, doc, err = sched(repo, "add", "digest", "daily digest", "--rrule", WEEKDAYS, "--tz", WARSAW, "--run-cost-cap", "3",
                           "--yes", "--json", catalog=digest)  # SCH-B19: exit 0 and saved, never asking
    assert code == 0 and doc["status"] == "saved", err
    _, twin, _ = sched(repo, "parse", "every weekday at 8:00", "--tz", WARSAW, "--json")
    assert doc["echo"]["sentence"] == twin["sentence"] == "At 08:00, Monday to Friday."
    assert doc["echo"]["slots"] == twin["slots"] and doc["echo"]["rule"] == twin["rule"]


def test_sch_ac3_a_phrase_with_no_terminal_and_no_yes_exits_3_with_the_echo_and_saves_nothing(repo: Path) -> None:
    before = home_hash()
    code, doc, _ = sched(repo, "add", "demo", "open bugs", "--when", "every weekday at 8:00", "--tz", WARSAW,
                         "--run-cost-cap", "3", signals=NO_TTY)  # SCH-B1
    assert code == 3 and doc["status"] == "needs" and doc["echo"]["sentence"] == "At 08:00, Monday to Friday."
    assert doc["questions"][0]["name"] == "confirm"
    assert home_hash() == before
    code, doc, _ = sched(repo, "add", "demo", "open bugs", "--when", "every weekday at 8:00", "--tz", WARSAW,
                         "--run-cost-cap", "3", "--yes", "--json")
    assert code == 0 and doc["status"] == "saved"
    assert store.read_entry(doc["schedule_id"])["when"]["phrase"] == "every weekday at 8:00"


def test_sch_ac3_an_ambiguous_phrase_exits_3_with_its_readings_and_choose_saves(repo: Path) -> None:
    before = home_hash()
    code, doc, _ = sched(repo, "add", "demo", "x", "--when", "every day at 9", "--tz", WARSAW, "--run-cost-cap", "3", "--yes")
    assert code == 3 and doc["status"] == "needs" and doc["questions"][0]["choices"] == ["09:00", "21:00"]
    assert [r["choose"] for r in doc["readings"]] == [1, 2] and home_hash() == before
    code, doc, _ = sched(repo, "add", "demo", "x", "--when", "every day at 9", "--choose", "2", "--tz", WARSAW,
                         "--run-cost-cap", "3", "--yes", "--json")
    assert code == 0 and store.read_entry(doc["schedule_id"])["when"]["rule"] == "FREQ=DAILY;BYHOUR=21;BYMINUTE=0"
    code, doc, _ = sched(repo, "parse", "every monday")  # a recurrence with no time: 09:00 is offered, never applied
    assert code == 3 and doc["questions"][0]["choices"] == ["09:00"]


def test_sch_ac3_parse_count_bounds_the_recurrence(repo: Path) -> None:
    code, doc, _ = sched(repo, "parse", "every day at 9am", "--count", "3", "--tz", WARSAW, "--json")
    assert code == 0 and doc["rule"].endswith("COUNT=3") and len(doc["slots"]) == 3
    code, doc, _ = sched(repo, "parse", "every day at 9am", "--count", "2", "--tz", WARSAW, "--json")
    assert len(doc["slots"]) == 2  # the echo of `parse` is the echo `add` would give


# --- SCH-AC4: parse, list, show, history write nothing ------------------------------------------------------------


def test_sch_ac4_parse_list_show_and_history_leave_the_home_store_unchanged(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sid = saved(repo)
    store.append_event(sid, "started", now=NOW, slot="2026-11-23T08:00:00Z", fire_id=f"{sid}@20261123T0800Z",
                       thread="demo/s-x")
    before, repo_before = home_hash(), hash_tree(repo)
    no_process(monkeypatch)
    for argv in (["parse", "every weekday at 8:00", "--tz", WARSAW], ["parse", "--cron", "0 8 * * 1-5", "--tz", WARSAW],
                 ["parse", "--every", "PT2H", "--json"], ["list"], ["list", "--json"], ["list", "--all"], ["show", sid],
                 ["show", sid, "--json"], ["show", "demo"], ["history", sid], ["history", sid, "--json"],
                 ["history", sid, "--since", "2026-11-01"]):
        code, _, err = sched(repo, *argv)
        assert code == 0, (argv, err)
    assert home_hash() == before and hash_tree(repo) == repo_before


def test_sch_ac4_list_reports_the_fields_and_marks_a_zone_that_differs(repo: Path) -> None:
    a = saved(repo)
    code, doc, _ = sched(repo, "add", "demo", "other", "--rrule", DAILY, "--tz", "America/New_York", "--run-cost-cap", "3",
                         "--yes", "--json", "--name", "ny")
    assert code == 0
    _, listing, _ = sched(repo, "list", "--json")
    rows = {r["schedule_id"]: r for r in listing["schedules"]}
    ny = rows[doc["schedule_id"]]
    assert ny["zone_differs"] is True and rows[a]["zone_differs"] is False and listing["machine_zone"] == WARSAW
    for key in ("name", "target", "sentence", "zone", "state", "next_slot", "last_fire", "live_runs", "failures",
                "period_spend"):
        assert key in rows[a], key
    assert rows[a]["target"] == "demo" and rows[a]["state"] == "active" and rows[a]["next_slot"] == "2026-11-24T08:00:00Z"
    assert rows[a]["last_fire"] is None and rows[a]["live_runs"] == 0 and rows[a]["failures"] == 0
    assert rows[a]["period_spend"] is None  # no budget
    text = sched(repo, "list")[1]
    assert "(differs from this machine)" in text and "At 09:00, every day." in text


def test_sch_ac4_list_recomputes_the_next_slot_and_a_machine_zone_change_moves_no_schedule(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sid = saved(repo)
    entry = store.read_entry(sid)
    entry["next_slot"] = "1999-01-01T00:00:00Z"  # a stale stored value: readers trust the computation
    store.write_entry(entry)
    _, listing, _ = sched(repo, "list", "--json")
    assert listing["schedules"][0]["next_slot"] == "2026-11-24T08:00:00Z"
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: ("Asia/Tokyo", "TZ"))  # SCH-B20
    _, moved, _ = sched(repo, "list", "--json")
    row = moved["schedules"][0]
    assert row["next_slot"] == "2026-11-24T08:00:00Z" and row["zone"] == WARSAW and row["zone_differs"] is True


def test_sch_ac4_list_shows_active_and_paused_and_all_adds_done_and_removed(repo: Path) -> None:
    a, b = saved(repo), saved(repo)
    sched(repo, "pause", b)
    c = saved(repo)
    sched(repo, "remove", c, "--yes")
    _, listing, _ = sched(repo, "list", "--json")
    assert sorted(r["state"] for r in listing["schedules"]) == ["active", "paused"]
    _, every, _ = sched(repo, "list", "--all", "--json")
    assert sorted(r["state"] for r in every["schedules"]) == ["active", "paused", "removed"] and a != b


def test_sch_ac4_show_gives_the_entry_the_next_ten_slots_and_the_last_twenty_fires(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: datetime(2027, 3, 25, 12, tzinfo=UTC))
    sid = saved(repo, "--starts", "2027-03-20T00:00", rule="FREQ=DAILY;BYHOUR=2;BYMINUTE=30")
    for i in range(25):
        store.append_event(sid, "due", now=NOW, slot=f"2027-03-{i + 1:02d}T01:30:00Z")
    code, doc, _ = sched(repo, "show", sid, "--json")
    assert code == 0 and doc["entry"]["schedule_id"] == sid and len(doc["echo"]["slots"]) == 10
    assert len(doc["fires"]) == 20 and doc["fires"][-1]["seq"] == 26  # created, then 25 due events: the last 20
    gap = [s for s in doc["echo"]["slots"] if s["note"] == "gap"]  # SCH-B3: 2027-03-28 02:30 does not exist
    assert gap and gap[0]["local"] == "2027-03-28 03:30" and gap[0]["utc"] == "2027-03-28T01:30Z"
    assert any("does not exist" in n for n in doc["echo"]["notes"])


def test_sch_ac4_history_filters_by_date_and_a_name_or_an_unknown_id_is_handled(repo: Path) -> None:
    sid = saved(repo)
    store.append_event(sid, "due", now=datetime(2026, 12, 5, 9, tzinfo=UTC), slot="2026-12-05T08:00:00Z")
    _, doc, _ = sched(repo, "history", "demo", "--since", "2026-12-01", "--json")
    assert [e["kind"] for e in doc["fires"]] == ["due"]
    code, _, err = sched(repo, "show", "nope-0000")
    assert code == 2 and "schedule_unknown" in err
    code, _, err = sched(repo, "history", sid, "--since", "soon")
    assert code == 2 and "when_malformed" in err
    saved(repo)
    code, _, err = sched(repo, "show", "demo")  # two schedules share the name: the ids are listed
    assert code == 2 and "schedule_ambiguous" in err


# --- SCH-AC6: the mutating verbs and every refusal ----------------------------------------------------------------


def test_sch_ac6_add_writes_the_entry_with_its_caller_and_the_created_event(repo: Path) -> None:
    sid = saved(repo, "--budget", "month:20", "--max-live", "2", "--pause-after-failures", "5", "--catch-up", "none")
    e = store.read_entry(sid)
    assert e["target"] == {"kind": "workflow", "workflow": "demo", "repo": str(repo), "request": "daily digest", "inputs": {}}
    assert e["run_cost_cap_usd"] == 3.0 and e["budget"] == {"period": "month", "cap_usd": 20.0}
    assert (e["catch_up"], e["max_live"], e["pause_after_failures"], e["overlap"]) == ("none", 2, 5, "skip")
    assert re.fullmatch(r"[0-9a-f]{64}", e["token_digest"]) and e["state"] == "active"  # TCK-B17: the SHA-256 of the fire token
    assert e["executors_checked"] and all({"executor", "kinds", "result"} <= set(c) for c in e["executors_checked"])  # TCK-B19
    assert e["created"]["caller"]["kind"] == "person" and e["created"]["from"] == "schedule add"
    assert e["options"]["flag"]["run.run_cost_cap_usd"]["via"] == "schedule"
    (created,) = store.read_log(sid)
    assert created["kind"] == "created" and created["caller"]["kind"] == "person" and created["seq"] == 1
    assert "daily digest" not in (home_path() / "schedules" / sid / "fires.jsonl").read_text(encoding="utf-8")  # SCH-AC8
    code, doc, _ = add(repo, "--name", "Nightly Digest")
    assert doc["schedule_id"].startswith("nightly-digest-")
    code, _, err = add(repo, "--name", "Nightly Digest", signals=NO_TTY)  # TCK-B22: no terminal and no declaration is no person
    assert code == 2 and "schedule_not_by_person" in err
    code, _, err = add(repo, "--as-agent", signals=NO_TTY)
    assert code == 2 and "schedule_not_by_person" in err


def test_sch_ac6_edit_records_both_forms_and_the_caller_and_keeps_past_fires(repo: Path) -> None:
    sid = saved(repo, rule=WEEKDAYS)
    for i in range(12):
        store.append_event(sid, "started", now=NOW, slot=f"2026-11-{i + 1:02d}T07:00:00Z", fire_id=f"f{i}")
    before = (home_path() / "schedules" / sid / "fires.jsonl").read_text(encoding="utf-8")
    code, doc, err = sched(repo, "edit", sid, "--when", "every weekday at 7:30", "--tz", WARSAW, "--yes", "--json")
    assert code == 0 and doc["changed"] == ["when"], err
    log = store.read_log(sid)
    edited = log[-1]
    assert edited["kind"] == "edited" and edited["caller"]["kind"] == "person"
    assert edited["old"]["rule"] == WEEKDAYS and edited["new"]["rule"] == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=7;BYMINUTE=30"
    assert (home_path() / "schedules" / sid / "fires.jsonl").read_text(encoding="utf-8").startswith(before)  # past fires unchanged
    e = store.read_entry(sid)
    assert e["when"]["rule"].endswith("BYHOUR=7;BYMINUTE=30") and e["edited"]["from"] == "schedule edit"
    assert e["next_slot"] == "2026-11-24T06:30:00Z"  # recomputed from now
    assert e["target"]["workflow"] == "demo" and e["target"]["request"] == "daily digest"


def test_sch_ac6_edit_changes_options_and_needs_a_yes(repo: Path) -> None:
    sid = saved(repo)
    before = home_hash()
    code, doc, _ = sched(repo, "edit", sid, "--when", "every day at 7:00", "--tz", WARSAW, signals=NO_TTY)
    assert code == 3 and doc["status"] == "needs" and home_hash() == before  # no terminal and no --yes: nothing changes
    code, doc, err = sched(repo, "edit", sid, "--overlap", "queue", "--max-live", "3", "--run-cost-cap", "2", "--yes", "--json")
    e = store.read_entry(sid)
    assert code == 0 and (e["overlap"], e["max_live"], e["run_cost_cap_usd"]) == ("queue", 3, 2.0), err
    assert sorted(doc["changed"]) == ["max_live", "options", "overlap", "run_cost_cap_usd"]
    code, _, err = sched(repo, "edit", sid, "--yes")
    assert code == 2 and "nothing_to_edit" in err


def test_sch_ac6_edit_cannot_change_the_target(repo: Path) -> None:
    sid = saved(repo)
    before = home_hash()
    for extra in (["--workflow", "capped"], ["--repo", "/elsewhere"], ["--orchestration", "x.orch.json"], ["--program"]):
        code, _, err = sched(repo, "edit", sid, "--when", "every day at 7:00", "--yes", *extra)
        assert code == 2 and "target_fixed" in err, extra  # SCH-B27
    assert home_hash() == before


def test_sch_ac6_pause_and_resume_record_missed_slots_unless_catch_up(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sid = saved(repo)
    code, doc, _ = sched(repo, "pause", sid, "--reason", "away", "--json")
    assert code == 0 and store.read_entry(sid)["state"] == "paused"
    paused = store.read_log(sid)[-1]
    assert paused["kind"] == "paused" and paused["reason"] == "person" and paused["caller"]["kind"] == "person"
    assert sched(repo, "pause", sid, "--json")[1]["changed"] is False  # already paused
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW + timedelta(days=3, hours=4))
    code, doc, _ = sched(repo, "resume", sid, "--json")
    assert code == 0 and doc["missed"] == 3 and store.read_entry(sid)["state"] == "active"
    log = store.read_log(sid)
    assert [e["slot"] for e in log if e["kind"] == "missed"] == ["2026-11-24T08:00:00Z", "2026-11-25T08:00:00Z",
                                                                    "2026-11-26T08:00:00Z"]
    assert log[-1]["kind"] == "resumed" and log[-1]["caller"]["kind"] == "person" and log[-1]["catch_up"] is False
    other = saved(repo, "--name", "other")
    sched(repo, "pause", other)
    code, doc, _ = sched(repo, "resume", other, "--catch-up", "--json")
    assert doc["missed"] == 0 and not [e for e in store.read_log(other) if e["kind"] == "missed"]  # left to catch-up


def test_sch_ac6_skip_records_the_slot_skipped_by_a_person(repo: Path) -> None:
    sid = saved(repo)
    code, doc, _ = sched(repo, "skip", sid, "--json")
    assert code == 0 and doc["skipped"] == ["2026-11-24T08:00:00Z"]
    code, doc, _ = sched(repo, "skip", sid, "--next", "--json")
    assert doc["skipped"] == ["2026-11-25T08:00:00Z"]  # the next one not yet handled
    code, doc, _ = sched(repo, "skip", sid, "--until", "2026-11-28", "--json")
    assert doc["skipped"] == ["2026-11-26T08:00:00Z", "2026-11-27T08:00:00Z"]
    skipped = [e for e in store.read_log(sid) if e["kind"] == "skipped"]
    assert len(skipped) == 4 and {e["reason"] for e in skipped} == {"person"} and skipped[0]["caller"]["kind"] == "person"
    assert skipped[0]["fire_id"] == f"{sid}@20261124T0800Z"


def test_sch_ac6_remove_keeps_the_history(repo: Path) -> None:
    sid = saved(repo)
    before = home_hash()
    code, doc, _ = sched(repo, "remove", sid, signals=NO_TTY)
    assert code == 3 and doc["status"] == "needs" and home_hash() == before
    code, _, err = sched(repo, "remove", sid, "--yes")
    assert code == 0, err
    assert store.read_entry(sid)["state"] == "removed" and (home_path() / "schedules" / sid / "fires.jsonl").is_file()
    assert [e["kind"] for e in store.read_log(sid)] == ["created", "removed"]
    assert store.read_log(sid)[-1]["caller"]["kind"] == "person"
    code, _, err = sched(repo, "remove", sid, "--yes")
    assert code == 2 and "schedule_state" in err


def test_sch_ac6_the_cost_cap_is_required_and_a_workflow_cap_only_goes_lower(repo: Path) -> None:
    before = home_hash()
    code, _, err = sched(repo, "add", "demo", "x", "--rrule", DAILY, "--tz", WARSAW, "--yes")
    assert code == 2 and "cost_cap_required" in err and home_hash() == before  # SCH-B8
    code, doc, _ = sched(repo, "add", "capped", "x", "--rrule", DAILY, "--tz", WARSAW, "--yes", "--json")
    assert store.read_entry(doc["schedule_id"])["run_cost_cap_usd"] == 10.0  # the workflow's own satisfies it
    code, doc, _ = sched(repo, "add", "capped", "x", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "50", "--yes", "--json")
    e = store.read_entry(doc["schedule_id"])
    assert e["run_cost_cap_usd"] == 10.0 and e["options"]["flag"]["run.run_cost_cap_usd"]["value"] == 10.0
    assert any("stays 10" in n for n in doc["echo"]["assumptions"])  # the echo says so
    code, doc, _ = sched(repo, "add", "capped", "x", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "2", "--yes", "--json")
    assert store.read_entry(doc["schedule_id"])["run_cost_cap_usd"] == 2.0  # the flag lowers it


REFUSALS = [
    (["add", "demo", "x", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "3", "--yes", "--grant",
      "draft=mcp:tracker/get_issue"], 2, "widening_in_schedule"),
    (["add", "demo", "x", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "3", "--yes", "--allow-command", "draft=curl"],
     2, "widening_in_schedule"),
    (["add", "demo", "x", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "3", "--yes", "--set", "steps.timeout_s=banana"],
     2, "error"),  # the run's own settle step refuses the setting
    (["add", "demo", "x", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "3", "--yes", "--overlap", "parallel",
      "--in-place"], 2, "parallel_needs_worktree"),
    (["add", "demo", "x", "--program", "--rrule", DAILY, "--run-cost-cap", "3", "--yes"], 2, "program_target_reserved"),
    (["add", "nope", "x", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "3", "--yes"], 2, "workflow_unregistered"),
    (["add", "demo", "x", "--rrule", "FREQ=YEARLY", "--tz", WARSAW, "--run-cost-cap", "3", "--yes"], 2, "rule_unsupported"),
    (["add", "demo", "x", "--every", "PT10M", "--tz", WARSAW, "--run-cost-cap", "3", "--yes"], 2, "interval_too_short"),
    (["add", "demo", "x", "--at", "2020-01-01T00:00", "--tz", WARSAW, "--run-cost-cap", "3", "--yes"], 2, "when_in_past"),
    (["add", "demo", "x", "--rrule", DAILY, "--tz", "EST", "--run-cost-cap", "3", "--yes"], 2, "zone_unknown"),
    (["add", "demo", "x", "--when", "03/04 at 10:00", "--tz", WARSAW, "--run-cost-cap", "3", "--yes"], 2, "date_ambiguous"),
    (["add", "demo", "x", "--when", "whenever", "--tz", WARSAW, "--run-cost-cap", "3", "--yes"], 2, "when_unparsed"),
    (["add", "demo", "x", "--run-cost-cap", "3", "--yes"], 2, "when_malformed"),
    (["add", "demo", "x", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "3", "--yes", "--budget", "year:5"], 2, "budget_invalid"),
    (["add", "demo", "x", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "3", "--yes", "--max-live", "9"], 2, "option_invalid"),
    (["add", "demo", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "3", "--yes"], 3, "needs"),  # no request
    (["show", "nope-0000"], 2, "schedule_unknown"), (["pause", "nope-0000"], 2, "schedule_unknown"),
    (["resume", "nope-0000"], 2, "schedule_unknown"), (["skip", "nope-0000"], 2, "schedule_unknown"),
    (["remove", "nope-0000", "--yes"], 2, "schedule_unknown"), (["edit", "nope-0000", "--yes"], 2, "schedule_unknown"),
]


@pytest.mark.parametrize(("argv", "code", "named_"), REFUSALS)
def test_sch_ac6_every_refusal_exits_with_its_code_and_writes_nothing(repo: Path, argv: list[str], code: int,
                                                                         named_: str) -> None:
    before, repo_before = home_hash(), hash_tree(repo)
    got, doc, err = sched(repo, *argv, "--json") if argv[0] == "add" else sched(repo, *argv)
    assert got == code, (argv, err)
    assert named_ in err or (isinstance(doc, dict) and named_ in (doc.get("status"), *[
        r["code"] for r in doc.get("refusals", [])]))
    assert home_hash() == before and hash_tree(repo) == repo_before  # nothing written, no run started


def test_sch_ac6_the_settings_check_is_the_runs_own_and_gives_its_findings(repo: Path) -> None:
    code, doc, _ = sched(repo, "add", "demo", "x", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "3", "--yes",
                         "--set", "steps.timeout_s=banana", "--json")
    assert code == 2 and doc["status"] == "error" and doc["refusals"][0]["code"]
    code, doc, _ = sched(repo, "add", "demo", "--rrule", DAILY, "--tz", WARSAW, "--run-cost-cap", "3", "--yes", "--json")
    assert code == 3 and doc["status"] == "needs" and doc["questions"][0]["name"] == "request"  # `run --check`'s question


def test_sch_ac6_parallel_is_accepted_when_the_workspace_resolves_to_a_worktree(repo: Path) -> None:
    sid = saved(repo, "--overlap", "parallel", "--max-live", "2")  # `demo` writes files: `auto` is a worktree
    assert store.read_entry(sid)["overlap"] == "parallel"


def test_sch_ac6_at_most_64_schedules(repo: Path) -> None:
    code, _, _ = add(repo)
    assert code == 0
    for i in range(63):
        store.write_entry(store.build_entry(
            schedule_id=f"fill-{i:04x}", name="fill", target={"kind": "workflow", "workflow": "demo", "repo": str(repo),
                                                              "request": "x", "inputs": {}},
            when={"kind": "recur", "rule": DAILY, "zone": "UTC", "starts": "2026-11-23T00:00"}, options={}, run_cost_cap_usd=1.0,
            budget=None, catch_up="latest", catch_up_window_s=86400, overlap="skip", max_live=1, pause_after_failures=3,
            created={"at": "2026-11-23T08:00:00Z"}, now=NOW))
    before = home_hash()
    code, _, err = add(repo)
    assert code == 2 and "too_many_schedules" in err and home_hash() == before
    sched(repo, "remove", "fill-0000", "--yes")  # a removed schedule is not counted
    assert add(repo)[0] == 0


# --- SCH-AC12: the verbs of the next phase are refused ------------------------------------------------------------


def test_sch_ac12_only_add_orchestration_is_refused_not_in_release_and_writes_nothing(repo: Path,
                                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    sid = saved(repo)
    before, repo_before = home_hash(), hash_tree(repo)
    no_process(monkeypatch)
    code, _, err = sched(repo, "add", "--orchestration", "release-train.orch.json", "--when", "every weekday at 8:00", "--yes")
    assert code == 2 and "not_in_release" in err and "schedule add --orchestration" in err, err  # ADR `release-three-composes-runs-in-parallel-and-grades-in-the-pipeline`: release 4
    assert home_hash() == before and hash_tree(repo) == repo_before and sid  # written nothing, started nothing
    assert not hasattr(schedule_cli, "NOT_IN_RELEASE")  # every other verb is built


def test_sch_ac12_tick_runs_one_tick_and_prints_a_one_line_summary(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tempergraph.schedule import launch

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")  # a fire needs a credential in the tick's own environment (TCK-B19)
    sid = saved(repo, rule="FREQ=DAILY;BYHOUR=8;BYMINUTE=0")  # 08:00 in Warsaw: 07:00 UTC in November
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW + timedelta(days=1, hours=-1, minutes=-29, seconds=-30))  # 07:01 UTC
    launched: list[str] = []
    monkeypatch.setattr(launch, "launch_run", lambda entry, start, **kw: launched.append(start["fire_id"]) or True)
    code, out, err = sched(repo, "tick")
    assert code == 0 and out.count("\n") == 1 and out.startswith("tick: started 1"), (out, err)
    assert launched == [f"{sid}@20261124T0700Z"]
    code, doc, _ = sched(repo, "tick", "--json")  # the slot is handled: nothing more starts
    assert code == 0 and doc["started"] == [] and doc["summary"].startswith("tick:") and doc["locked"] is False
    assert launched == [f"{sid}@20261124T0700Z"]


def test_sch_ac12_loop_detach_and_stop_have_exit_codes(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tempergraph import detach

    monkeypatch.setattr(detach, "start_loop", lambda home, shim=None: True)
    assert sched(repo, "loop", "--detach")[0] == 0 and sched(repo, "loop", "--stop")[0] == 0  # each exits 0
    monkeypatch.setattr(detach, "start_loop", lambda home, shim=None: False)
    code, _, err = sched(repo, "loop", "--detach")
    assert code == 2 and "loop_not_started" in err  # a start that failed is a refusal
    assert sched(repo, "loop", "--detach", "--stop")[0] == 2  # the two modes exclude each other


def test_sch_ac12_a_bare_schedule_is_a_usage_error(repo: Path) -> None:
    code, _, err = cli(repo, happy(), "schedule")
    assert code == 2 and "schedule needs a verb" in err
    code, _, err = cli(repo, happy(), "schedule", "nonsense")
    assert code == 2 and err


# --- AC 10: the engine names no workflow package ------------------------------------------------------------------


def test_ac10_nothing_of_schedules_names_a_workflow_package() -> None:
    names = workflow_names()  # found by the packages' own manifests, never typed here
    assert names
    files = [*sorted((ENGINE_ROOT / "src" / "tempergraph" / "schedule").glob("*.py")),
             ENGINE_ROOT / "src" / "tempergraph" / "cli" / "schedule_cli.py", *sorted((ENGINE_ROOT / "tests").glob("test_schedule_*.py"))]
    assert len(files) >= 14
    for path in files:
        text = path.read_text(encoding="utf-8")
        for name in names:
            assert name not in text, f"{path.name} names the workflow package {name!r}"
