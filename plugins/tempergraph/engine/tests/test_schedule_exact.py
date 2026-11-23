"""Exact formats, cron, canonical form and echo (SCH-B15, SCH-B18, SCH-B29 to SCH-B32; SCH-AC1, SCH-AC9 to SCH-AC11)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tempergraph.schedule.echo import build_echo, sentence
from tempergraph.schedule.exact import Parsed, parse_exact
from tempergraph.schedule.model import ScheduleError, When, slots_between

NOW = datetime(2026, 11, 22, 10, 0, 30, tzinfo=UTC)  # a Sunday; 11:00 in Warsaw
MACHINE = ("Europe/Warsaw", "TZ")
WARSAW = "Europe/Warsaw"


def parse(**kw: Any) -> Parsed:
    kw.setdefault("tz", WARSAW)
    return parse_exact(now=NOW, machine=MACHINE, **kw)


def refused(**kw: Any) -> ScheduleError:
    with pytest.raises(ScheduleError) as ei:
        parse(**kw)
    assert ei.value.exit_code == 2
    return ei.value


# --- SCH-AC1: fixtures for the exact formats: canonical form, echo sentence, next three slots ------------------------


def test_sch_ac1_rrule_gives_the_canonical_form_and_the_echo() -> None:
    p = parse(rrule="FREQ=WEEKLY;BYDAY=TH,MO,FR,TU,WE;BYMINUTE=0;BYHOUR=8")  # parts in any order, lists in any order
    assert p.when == When(kind="recur", zone=WARSAW, rule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0",
                          starts="2026-11-22T11:00")
    e = build_echo(p.when, p.assumptions, NOW)
    assert e.sentence == "At 08:00, Monday to Friday."  # SCH-B18
    assert [s["local"] for s in e.to_doc()["slots"]] == ["2026-11-23 08:00", "2026-11-24 08:00", "2026-11-25 08:00"]
    assert [s["utc"] for s in e.to_doc()["slots"]] == ["2026-11-23T07:00Z", "2026-11-24T07:00Z", "2026-11-25T07:00Z"]
    assert e.to_doc()["zone"] == WARSAW and e.to_doc()["utc_offset"] == "+01:00"
    assert "zone: Europe/Warsaw (UTC+01:00)" in e.text()


def test_sch_ac1_the_zone_from_the_machine_is_an_assumption() -> None:
    p = parse_exact(rrule="FREQ=DAILY;BYHOUR=9;BYMINUTE=0", now=NOW, machine=MACHINE)
    assert p.when.zone == WARSAW and p.assumptions[0].startswith("zone from this machine")
    assert "assumed: zone from this machine" in build_echo(p.when, p.assumptions, NOW).text()


def test_sch_ac1_at_is_once_and_the_echo_lists_one_slot() -> None:
    p = parse(at="2026-12-01T08:00")
    assert p.when == When(kind="once", zone=WARSAW, at="2026-12-01T08:00")
    e = build_echo(p.when, p.assumptions, NOW)
    assert e.sentence == "Once, on 2026-12-01 at 08:00." and len(e.to_doc()["slots"]) == 1
    assert e.to_doc()["slots"][0]["utc"] == "2026-12-01T07:00Z"
    z = parse(at="2026-12-01T08:00Z")  # an offset or Z: the same instant, as local time in the zone
    assert z.when.at == "2026-12-01T09:00"


def test_sch_ac1_every_is_an_interval_rule_from_starts() -> None:
    assert parse(every="PT2H").when.rule == "FREQ=HOURLY;INTERVAL=2"
    assert parse(every="PT1H").when.rule == "FREQ=HOURLY"  # INTERVAL=1 is not written
    assert parse(every="PT90M").when.rule == "FREQ=MINUTELY;INTERVAL=90"
    assert parse(every="P1DT12H").when.rule == "FREQ=HOURLY;INTERVAL=36"
    assert parse(every="P1W").when.rule == "FREQ=HOURLY;INTERVAL=168"
    p = parse(every="PT2H")
    e = build_echo(p.when, p.assumptions, NOW)
    assert e.sentence.startswith("Every 2 hours")
    assert [s["utc"] for s in e.to_doc()["slots"]] == ["2026-11-22T10:00Z", "2026-11-22T12:00Z", "2026-11-22T14:00Z"]
    assert any("starts now" in a for a in p.assumptions)  # the first slot is `starts`, which defaults to now


def test_sch_ac1_starts_until_and_count() -> None:
    p = parse(rrule="FREQ=DAILY;BYHOUR=9;BYMINUTE=0", starts="2026-12-01", until="2026-12-03")
    assert p.when.starts == "2026-12-01T00:00"
    assert p.when.rule == "FREQ=DAILY;BYHOUR=9;BYMINUTE=0;UNTIL=20261203T225900Z"  # the end of 12-03 local, as UTC
    assert parse(rrule="FREQ=DAILY;BYHOUR=9;BYMINUTE=0", count=5).when.rule == "FREQ=DAILY;BYHOUR=9;BYMINUTE=0;COUNT=5"
    assert parse(rrule="RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0").when.rule == "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
    p = parse(rrule="FREQ=DAILY;BYHOUR=9;BYMINUTE=0", starts="2026-12-01T00:00:00Z")  # an instant, in the zone
    assert p.when.starts == "2026-12-01T01:00"
    e = build_echo(parse(rrule="FREQ=DAILY;BYHOUR=9;BYMINUTE=0;COUNT=2").when, [], NOW)
    assert e.sentence == "At 09:00, every day, for 2 times." and len(e.to_doc()["slots"]) == 2


def test_sch_ac1_the_echo_names_a_gap_and_an_overlap_on_a_listed_slot() -> None:
    gap = build_echo(parse(at="2027-03-28T02:30").when, [], NOW)
    assert gap.to_doc()["slots"][0] == {"local": "2027-03-28 03:30", "utc": "2027-03-28T01:30Z", "note": "gap"}
    assert "does not exist" in gap.text() and "03:30" in gap.text()
    p = parse(rrule="FREQ=DAILY;BYHOUR=2;BYMINUTE=30", starts="2027-10-30T00:00")
    over = build_echo(p.when, [], datetime(2027, 10, 30, 12, tzinfo=UTC))
    assert [s["note"] for s in over.to_doc()["slots"]] == ["overlap", "", ""]
    assert "happens twice" in over.text() and "first occurrence" in over.text()


@pytest.mark.parametrize("given", [
    {"rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0"},
    {"rrule": "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=9;BYMINUTE=0", "starts": "2026-12-01T00:00"},
    {"rrule": "FREQ=MONTHLY;BYMONTHDAY=-1,15;BYHOUR=17;BYMINUTE=0", "count": 4},
    {"rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=FR;BYHOUR=16;BYMINUTE=0", "until": "2027-06-30"},
    {"rrule": "FREQ=HOURLY;INTERVAL=2;BYDAY=MO,TU;BYHOUR=9,11,13,15,17"},
    {"every": "PT2H"}, {"every": "PT45M", "starts": "2026-12-01T09:00"}, {"cron": "*/15 9-17 * * *"},
    {"at": "2026-12-01T08:00"},
])
def test_sch_ac1_the_echo_is_rendered_from_the_canonical_form_and_reparses_to_it(given: dict[str, Any]) -> None:
    p = parse(**given)
    text = build_echo(p.when, p.assumptions, NOW).text()
    zone = re.search(r"^zone: (\S+)", text, re.M).group(1)  # type: ignore[union-attr]
    if p.when.kind == "once":
        again = parse(at=re.search(r"^at: (\S+)", text, re.M).group(1), tz=zone)  # type: ignore[union-attr]
    else:
        rule = re.search(r"^rule: (\S+)", text, re.M).group(1)  # type: ignore[union-attr]
        starts = re.search(r"^starts: (\S+)", text, re.M).group(1)  # type: ignore[union-attr]
        again = parse(rrule=rule, starts=starts, tz=zone)
    assert again.when == p.when
    assert sentence(p.when) == build_echo(p.when, ["something assumed"], NOW).sentence  # from the canonical form only


# --- SCH-AC9: cron --------------------------------------------------------------------------------------------------

CRON_RULES = {
    "0 8 * * 1-5": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0",
    "*/15 9-17 * * *": "FREQ=DAILY;BYHOUR=9,10,11,12,13,14,15,16,17;BYMINUTE=0,15,30,45",
    "0 9 1,15 * *": "FREQ=MONTHLY;BYMONTHDAY=1,15;BYHOUR=9;BYMINUTE=0",
    "30 * * * mon-fri": "FREQ=HOURLY;BYDAY=MO,TU,WE,TH,FR;BYMINUTE=30",
    "0 9 * * 7": "FREQ=WEEKLY;BYDAY=SU;BYHOUR=9;BYMINUTE=0",
    "0 9 1-31 1-12 0-7": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
    "0 0 * * *": "FREQ=DAILY;BYHOUR=0;BYMINUTE=0",
    "15 2 * * *": "FREQ=DAILY;BYHOUR=2;BYMINUTE=15",
    "0 */6 * * *": "FREQ=DAILY;BYHOUR=0,6,12,18;BYMINUTE=0",
    "5,35 6-22/4 * * SAT,Sun": "FREQ=WEEKLY;BYDAY=SA,SU;BYHOUR=6,10,14,18,22;BYMINUTE=5,35",
    "0 12 31 * *": "FREQ=MONTHLY;BYMONTHDAY=31;BYHOUR=12;BYMINUTE=0",
    "0 9 */10 * *": "FREQ=MONTHLY;BYMONTHDAY=1,11,21,31;BYHOUR=9;BYMINUTE=0",
    "0 3 * * Mon,wed,FRI": "FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=3;BYMINUTE=0",
    "0 22 * * 0,6": "FREQ=WEEKLY;BYDAY=SA,SU;BYHOUR=22;BYMINUTE=0",
    "0 12 * jan-dec *": "FREQ=DAILY;BYHOUR=12;BYMINUTE=0",
    "10 */2 * * *": "FREQ=DAILY;BYHOUR=0,2,4,6,8,10,12,14,16,18,20,22;BYMINUTE=10",
}


def test_sch_ac9_every_accepted_form_gives_the_stated_rule() -> None:
    for cron, rule in CRON_RULES.items():
        assert parse(cron=cron).when.rule == rule, cron
    assert parse(cron="0 8 * * 1-5").when.kind == "recur"


def _expand(field: str, lo: int, hi: int, names: dict[str, int] | None = None) -> set[int] | None:
    """A cron field read by a plain loop, for the minute-by-minute reference; None for `*`."""
    if field == "*":
        return None
    out: set[int] = set()
    for item in field.split(","):
        rng, _, step = item.partition("/")
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = (int((names or {}).get(x.lower(), x)) for x in rng.split("-"))
        else:
            a = b = int((names or {}).get(rng.lower(), rng))
        out |= set(range(a, b + 1, int(step) if step else 1))
    return out


def _local_clock_reference(cron: str, zone: ZoneInfo, a: datetime, b: datetime) -> list[datetime]:
    """Every minute of the local clock for two years, matched against the five fields."""
    mi, ho, dom, mo, dow = cron.split()
    names = {n: i for i, n in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat"))}
    minutes, hours = _expand(mi, 0, 59), _expand(ho, 0, 23)
    doms = _expand(dom, 1, 31)
    months = _expand(mo, 1, 12, {n: i + 1 for i, n in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                                                  "sep", "oct", "nov", "dec"))})
    dows = _expand(dow, 0, 7, names)
    if dows is not None:
        dows = {d % 7 for d in dows}
    out: set[datetime] = set()
    day = a.date() - timedelta(days=1)
    while day <= b.date() + timedelta(days=1):
        cron_dow = (day.weekday() + 1) % 7  # cron counts Sunday as 0
        if ((doms is None or day.day in doms) and (months is None or day.month in months)
                and (dows is None or cron_dow in dows)):
            for h in range(24):
                if hours is not None and h not in hours:
                    continue
                for m in range(60):  # every minute of a matching hour
                    if minutes is None or m in minutes:
                        out.add(datetime.combine(day, time(h, m)).replace(tzinfo=zone).astimezone(UTC))
        day += timedelta(days=1)
    return sorted(u for u in out if a <= u <= b)


def test_sch_ac9_cron_slots_over_two_years_equal_a_match_of_the_five_fields_against_the_local_clock() -> None:
    a, b = datetime(2026, 11, 23, tzinfo=UTC), datetime(2028, 11, 23, tzinfo=UTC)
    seen_notes: set[str] = set()
    for zone_name in (WARSAW, "America/New_York", "Australia/Sydney"):
        zone = ZoneInfo(zone_name)
        for cron in CRON_RULES:
            when = parse(cron=cron, tz=zone_name).when
            mine = slots_between(when, a, b)
            assert [s.utc for s in mine] == _local_clock_reference(cron, zone, a, b), (zone_name, cron)
            seen_notes |= {s.note for s in mine}
    assert {"gap", "overlap"} <= seen_notes  # `15 2 * * *` meets a gap in each zone and an overlap in Warsaw and Sydney


# --- SCH-AC10: what is refused, and why -----------------------------------------------------------------------------


@pytest.mark.parametrize("cron", ["@daily", "0 9 * *", "0 9 * * * *", "0 9 * * ?", "0 9 L * *", "0 9 15W * *", "0 9 * * 5#2",
                                   "60 9 * * *", "0 24 * * *", "0 9 32 * *", "0 9 * 13 *", "0 9 * * 8", "0 9 5-1 * *",
                                   "0 9 * * foo", "*/0 * * * *", "0 9 1/5 * *", "a b c d e", "0 9 , * *", "0 9 1-3-5 * *",
                                   "0 0 0 * *", "0 0 0 9 * *", ""])
def test_sch_ac10_cron_outside_the_accepted_forms_is_when_malformed(cron: str) -> None:
    err = refused(cron=cron)
    assert err.code == "when_malformed" and "cron" in err.message


@pytest.mark.parametrize(("cron", "named"), [("0 9 * 6 *", "month"), ("0 9 * jun-aug *", "month"),
                                             ("0 9 1 * 1", "day of month and the day of week"),
                                             ("0 9 1,15 * mon-fri", "day of month and the day of week")])
def test_sch_ac10_a_restricted_month_or_both_day_fields_is_rule_unsupported(cron: str, named: str) -> None:
    err = refused(cron=cron)
    assert err.code == "rule_unsupported" and named in err.message


@pytest.mark.parametrize(("rrule", "named"), [
    ("FREQ=YEARLY;BYMONTH=6;BYMONTHDAY=1", "FREQ=YEARLY"), ("FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1", "BYSETPOS"),
    ("FREQ=WEEKLY;BYDAY=1MO", "ordinal"), ("FREQ=DAILY;BYMONTH=6", "BYMONTH"), ("FREQ=DAILY;BYWEEKNO=3", "BYWEEKNO"),
    ("FREQ=DAILY;BYYEARDAY=3", "BYYEARDAY"), ("FREQ=DAILY;BYSECOND=3", "BYSECOND"), ("FREQ=WEEKLY;WKST=SU", "WKST"),
    ("FREQ=MONTHLY;BYMONTHDAY=32", "BYMONTHDAY"), ("FREQ=MONTHLY;BYMONTHDAY=-2", "BYMONTHDAY"),
    ("DTSTART:20261201T090000\nRRULE:FREQ=DAILY", "DTSTART"), ("FREQ=DAILY;RDATE=20261201", "RDATE"),
    ("FREQ=DAILY;EXDATE=20261201", "EXDATE"), ("FREQ=SECONDLY", "SECONDLY"),
    ("FREQ=MONTHLY;BYDAY=1MO,TU;BYHOUR=9", "BYDAY"), ("FREQ=MINUTELY;INTERVAL=30;BYHOUR=9", "MINUTELY"),
])
def test_sch_ac10_an_rrule_outside_the_stored_subset_is_rule_unsupported(rrule: str, named: str) -> None:
    err = refused(rrule=rrule)
    assert err.code == "rule_unsupported" and named in err.message


def test_sch_ac10_an_rrule_inside_the_subset_is_accepted() -> None:
    assert parse(rrule="FREQ=MONTHLY;BYDAY=1MO;BYHOUR=9;BYMINUTE=0").when.rule == "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=9;BYMINUTE=0"
    assert parse(rrule="FREQ=MONTHLY;BYDAY=-1FR;BYHOUR=9;BYMINUTE=0").when.rule.endswith("BYHOUR=9;BYMINUTE=0")  # type: ignore[union-attr]


@pytest.mark.parametrize("given", [
    {"rrule": "garbage"}, {"rrule": "FREQ=DAILY;BYHOUR=25"}, {"rrule": "FREQ=DAILY;COUNT=3;UNTIL=20271231T000000Z"},
    {"rrule": "FREQ=DAILY;BYHOUR=9", "count": 3, "until": "2027-01-01"}, {"rrule": "FREQ=DAILY;COUNT=2", "count": 3},
    {"rrule": "FREQ=DAILY;INTERVAL=0"}, {"rrule": "FREQ=FORTNIGHTLY"}, {"rrule": "FREQ=DAILY;BYDAY=XX"},
    {"at": "tomorrow"}, {"at": "2026-12-01"}, {"at": "2026-12-01T08:00", "count": 2}, {"every": "PT1S"},
    {"every": "P1M"}, {"every": "2h"}, {"every": "PT0M"}, {"rrule": "FREQ=DAILY;BYHOUR=9", "starts": "next week"},
    {"rrule": "FREQ=DAILY;BYHOUR=9", "count": 0}, {}, {"at": "2026-12-01T08:00", "every": "PT2H"},
])
def test_sch_ac10_a_malformed_value_is_when_malformed(given: dict[str, Any]) -> None:
    assert refused(**given).code == "when_malformed"


def test_sch_ac10_past_too_far_and_unknown_zone() -> None:
    assert refused(at="2026-11-01T08:00").code == "when_in_past"
    assert refused(at="2028-01-01T08:00").code == "when_too_far"  # more than 400 days ahead
    assert parse(at="2026-11-22T11:00").when.at == "2026-11-22T11:00"  # the current minute is due, not past
    assert refused(rrule="FREQ=DAILY;BYHOUR=9;BYMINUTE=0;COUNT=1", starts="2026-01-01T00:00").code == "when_in_past"
    assert refused(rrule="FREQ=DAILY;BYHOUR=9;BYMINUTE=0", until="2026-11-01").code == "when_in_past"
    assert refused(rrule="FREQ=DAILY;BYHOUR=9;BYMINUTE=0", starts="2028-06-01T00:00").code == "when_too_far"
    for tz in ("Mars/Olympus", "EST", "CET", "Nowhere"):
        assert refused(at="2026-12-01T08:00", tz=tz).code == "zone_unknown"
    assert parse(at="2026-12-01T08:00", tz="UTC").when.zone == "UTC"


# --- SCH-AC11: slots under fifteen minutes apart --------------------------------------------------------------------


@pytest.mark.parametrize("given", [
    {"every": "PT14M"}, {"every": "PT10M"}, {"rrule": "FREQ=MINUTELY;INTERVAL=10"}, {"rrule": "FREQ=MINUTELY"},
    {"rrule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0,14"}, {"rrule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0,10"},
    {"rrule": "FREQ=HOURLY;BYMINUTE=0,50,55"}, {"cron": "0,14 9 * * *"}, {"cron": "*/10 * * * *"}, {"cron": "* * * * *"},
    {"rrule": "FREQ=DAILY;BYHOUR=23,0;BYMINUTE=55,0"},  # 23:55 then 00:00 of the next day
])
def test_sch_ac11_slots_under_fifteen_minutes_apart_are_interval_too_short(given: dict[str, Any]) -> None:
    err = refused(**given)
    assert err.code == "interval_too_short" and "minutes" in err.message


@pytest.mark.parametrize("given", [
    {"every": "PT15M"}, {"rrule": "FREQ=MINUTELY;INTERVAL=15"}, {"rrule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0,15"},
    {"cron": "0,15 9 * * *"}, {"cron": "*/15 * * * *"}, {"rrule": "FREQ=HOURLY;BYMINUTE=0,45"},
])
def test_sch_ac11_the_same_inputs_at_fifteen_minutes_are_accepted(given: dict[str, Any]) -> None:
    assert parse(**given).when.kind == "recur"


def test_sch_ac11_the_shortest_gap_is_named() -> None:
    assert "14 minutes" in refused(cron="0,14 9 * * *").message
    assert "10 minutes" in refused(every="PT10M").message
