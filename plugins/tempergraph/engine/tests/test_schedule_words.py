"""The word grammar and its ambiguities (SCH-B16, SCH-B17, SCH-B2; SCH-AC1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from tempergraph.schedule.echo import build_echo
from tempergraph.schedule.exact import Parsed, parse_exact
from tempergraph.schedule.model import Needs, ScheduleError, When
from tempergraph.schedule.words import parse_words

NOW = datetime(2026, 11, 23, 8, 0, 30, tzinfo=UTC)  # a Monday; 09:00 in Warsaw
WARSAW = "Europe/Warsaw"
MACHINE = (WARSAW, "TZ")


def words(phrase: str, **kw: Any) -> Parsed:
    kw.setdefault("tz", WARSAW)
    return parse_words(phrase, now=NOW, machine=MACHINE, **kw)


def exact(**kw: Any) -> Parsed:
    kw.setdefault("tz", WARSAW)
    return parse_exact(now=NOW, machine=MACHINE, **kw)


def once(at: str, zone: str = WARSAW) -> When:
    return When(kind="once", zone=zone, at=at)


def needs(phrase: str, **kw: Any) -> Needs:
    with pytest.raises(Needs) as ei:
        words(phrase, **kw)
    return ei.value


def refused(phrase: str, **kw: Any) -> ScheduleError:
    with pytest.raises(ScheduleError) as ei:
        words(phrase, **kw)
    assert ei.value.exit_code == 2
    return ei.value


# --- once ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("phrase", "at"), [
    ("in 2 hours", "2026-11-23T11:00"), ("in half an hour", "2026-11-23T09:30"), ("in an hour", "2026-11-23T10:00"),
    ("in 90 minutes", "2026-11-23T10:30"), ("in 3 days", "2026-11-26T09:00"), ("in 1 week", "2026-11-30T09:00"),
    ("tomorrow at 9am", "2026-11-24T09:00"), ("today at 6pm", "2026-11-23T18:00"), ("at 18:00", "2026-11-23T18:00"),
    ("at 9:30pm", "2026-11-23T21:30"), ("tomorrow at noon", "2026-11-24T12:00"),
    ("tomorrow at midnight", "2026-11-24T00:00"), ("tomorrow at 18", "2026-11-24T18:00"),
    ("next monday at 10:00", "2026-11-30T10:00"),  # next week's Monday, never this week's
    ("next tuesday at 10:00", "2026-12-01T10:00"),  # the Tuesday 8 days later (SCH-B17)
    ("this friday at 10:00", "2026-11-27T10:00"), ("monday at 10:00", "2026-11-23T10:00"),
    ("monday at 8:00", "2026-11-30T08:00"), ("fri at 4pm", "2026-11-27T16:00"),
    ("on dec 1 at 08:00", "2026-12-01T08:00"), ("2026-12-01 08:00", "2026-12-01T08:00"),
    ("2026-12-01T08:00", "2026-12-01T08:00"), ("1 dec at 8:00", "2026-12-01T08:00"),
    ("december 1st at 8:00", "2026-12-01T08:00"), ("dec 1, 2027 at 08:00", "2027-12-01T08:00"),
    ("jan 5 at 9:00", "2027-01-05T09:00"),  # a past month-day without a year means next year
    ("2026-12-01T08:00:00Z", "2026-12-01T09:00"), ("2026-12-01T08:00+02:00", "2026-12-01T07:00"),
    ("  Tomorrow   AT  9AM. ", "2026-11-24T09:00"),  # case, spaces and a trailing period are ignored
])
def test_sch_ac1_phrases_give_a_once(phrase: str, at: str) -> None:
    assert words(phrase).when == once(at)


def test_sch_ac1_a_phrase_gives_the_canonical_form_of_its_exact_twin() -> None:
    for phrase, twin in [
        ("in 2 hours", {"at": "2026-11-23T11:00"}),
        ("every weekday at 8:00", {"rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0"}),
        ("daily at 09:00", {"rrule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"}),
        ("every 2 weeks on friday at 16:00", {"rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=FR;BYHOUR=16;BYMINUTE=0"}),
        ("every 2 hours", {"every": "PT2H"}), ("hourly", {"every": "PT1H"}), ("every 30 minutes", {"every": "PT30M"}),
        ("every day at 9am until 2027-01-31", {"rrule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "until": "2027-01-31"}),
    ]:
        a, b = words(phrase), exact(**twin)
        assert a.when == b.when and a.assumptions == b.assumptions, phrase
        assert build_echo(a.when, a.assumptions, NOW).text() == build_echo(b.when, b.assumptions, NOW).text()


def test_sch_ac1_the_zone_comes_from_the_phrase_the_option_or_the_machine() -> None:
    assert words("tomorrow at 9am in America/New_York", tz=None).when == once("2026-11-24T09:00", "America/New_York")
    assert words("tomorrow at 9am in UTC", tz=None).when.zone == "UTC"
    assert words("tomorrow at 9am", tz="Asia/Tokyo").when.zone == "Asia/Tokyo"
    p = words("tomorrow at 9am", tz=None)
    assert p.when.zone == WARSAW and p.assumptions[0].startswith("zone from this machine")
    assert refused("tomorrow at 9am in Asia/Tokyo", tz=WARSAW).code == "when_malformed"  # two zones, one schedule


# --- recur -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("phrase", "rule"), [
    ("every day at 9am", "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"), ("daily at 09:00", "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"),
    ("every weekday at 8:00", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0"),
    ("every monday and thursday at 7pm", "FREQ=WEEKLY;BYDAY=MO,TH;BYHOUR=19;BYMINUTE=0"),
    ("every mon, wed and fri at 07:30", "FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=7;BYMINUTE=30"),
    ("every weekend at 10:00", "FREQ=WEEKLY;BYDAY=SA,SU;BYHOUR=10;BYMINUTE=0"),
    ("every 2 days at 6am", "FREQ=DAILY;INTERVAL=2;BYHOUR=6;BYMINUTE=0"),
    ("every 2 weeks on friday at 16:00", "FREQ=WEEKLY;INTERVAL=2;BYDAY=FR;BYHOUR=16;BYMINUTE=0"),
    ("every week on tuesday at 9am", "FREQ=WEEKLY;BYDAY=TU;BYHOUR=9;BYMINUTE=0"),
    ("every month on the 1st at 9am", "FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=9;BYMINUTE=0"),
    ("every month on the 15th at 9am", "FREQ=MONTHLY;BYMONTHDAY=15;BYHOUR=9;BYMINUTE=0"),
    ("every 3 months on the 2nd at 9am", "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=2;BYHOUR=9;BYMINUTE=0"),
    ("every month on the last day at 17:00", "FREQ=MONTHLY;BYMONTHDAY=-1;BYHOUR=17;BYMINUTE=0"),
    ("every first monday of the month at 9am", "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=9;BYMINUTE=0"),
    ("every last friday of the month at 9am", "FREQ=MONTHLY;BYDAY=-1FR;BYHOUR=9;BYMINUTE=0"),
    ("every 2 hours", "FREQ=HOURLY;INTERVAL=2"), ("every hour", "FREQ=HOURLY"), ("hourly", "FREQ=HOURLY"),
    ("every 30 minutes", "FREQ=MINUTELY;INTERVAL=30"), ("every 15 minutes", "FREQ=MINUTELY;INTERVAL=15"),
    ("every 2 hours between 9am and 5pm on weekdays",
     "FREQ=HOURLY;INTERVAL=2;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9,11,13,15,17"),
    ("every 4 hours between 8:00 and 20:00", "FREQ=HOURLY;INTERVAL=4;BYHOUR=8,12,16,20"),
    ("every day at 9am for 5 times", "FREQ=DAILY;BYHOUR=9;BYMINUTE=0;COUNT=5"),
    ("every day at 9am until 2026-12-31", "FREQ=DAILY;BYHOUR=9;BYMINUTE=0;UNTIL=20261231T225900Z"),
    ("every day at 9am from dec 1 until dec 31 2026", "FREQ=DAILY;BYHOUR=9;BYMINUTE=0;UNTIL=20261231T225900Z"),
    ("EVERY   Monday  at 9AM.", "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0"),
])
def test_sch_ac1_phrases_give_a_recur(phrase: str, rule: str) -> None:
    p = words(phrase)
    assert p.when.kind == "recur" and p.when.rule == rule, phrase


def test_sch_ac1_bounds_and_starts() -> None:
    p = words("every day at 9am from 2026-12-01")
    assert p.when.starts == "2026-12-01T00:00"
    assert words("every 2 hours between 9am and 5pm on weekdays").when.starts == "2026-11-23T09:00"  # anchors the hours
    assert words("every day at 9am").when.starts == "2026-11-23T09:00"  # now, to the minute, in the zone
    e = build_echo(words("every weekday at 8:00").when, [], NOW)
    assert e.sentence == "At 08:00, Monday to Friday."


# --- ambiguity (SCH-B2) --------------------------------------------------------------------------------------------


def test_sch_ac1_a_bare_hour_is_asked_and_choose_picks_a_reading() -> None:
    n = needs("every day at 9")
    assert [r.label for r in n.readings] == ["09:00", "21:00"]  # SCH-B2
    assert words("every day at 9", choose=1).when.rule == "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
    assert words("every day at 9", choose=2).when.rule == "FREQ=DAILY;BYHOUR=21;BYMINUTE=0"
    assert [r.label for r in needs("tomorrow at 12").readings] == ["12:00", "00:00"]
    assert words("tomorrow at 9", choose=2).when == once("2026-11-24T21:00")


def test_sch_ac1_a_recurrence_with_no_time_offers_nine_and_never_applies_it() -> None:
    n = needs("every monday")
    assert [r.label for r in n.readings] == ["09:00"]
    assert words("every monday", choose=1).when.rule == "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0"
    assert [r.label for r in needs("every day").readings] == ["09:00"]
    assert [r.label for r in needs("tomorrow").readings] == ["09:00"]
    n = needs("every monday until 2026-12-31")  # the reading keeps the bound
    assert words(n.readings[0].phrase or "").when.rule.endswith("UNTIL=20261231T225900Z")  # type: ignore[union-attr]


def test_sch_ac1_at_a_time_that_has_passed_today_is_asked() -> None:
    n = needs("at 8:00")  # it is 09:00 in Warsaw
    assert [r.label for r in n.readings][0].startswith("tomorrow")
    assert n.readings[-1].phrase is None  # the other reading is to refuse
    assert words("at 8:00", choose=1).when == once("2026-11-24T08:00")
    assert refused_choose("at 8:00", 2).code == "when_in_past"
    assert words("at 18:00").when == once("2026-11-23T18:00")  # in the future today: no question


@pytest.mark.parametrize("day", ["29th", "30th", "31st"])
def test_sch_ac1_a_late_day_of_the_month_asks_skip_or_last_day(day: str) -> None:
    phrase = f"every month on the {day} at 9am"
    n = needs(phrase)
    assert [r.label for r in n.readings] == ["skip short months", "use the last day"]
    n_day = int(day[:2])
    assert words(phrase, choose=1).when.rule == f"FREQ=MONTHLY;BYMONTHDAY={n_day};BYHOUR=9;BYMINUTE=0"
    assert words(phrase, choose=2).when.rule == "FREQ=MONTHLY;BYMONTHDAY=-1;BYHOUR=9;BYMINUTE=0"


def test_sch_ac1_every_reading_phrase_parses_without_a_question() -> None:
    for phrase in ("every day at 9", "every monday", "at 8:00", "every month on the 31st at 9am", "tomorrow"):
        for r in needs(phrase).readings:
            if r.phrase is not None:
                assert words(r.phrase).when.kind in ("once", "recur"), (phrase, r)


def refused_choose(phrase: str, n: int) -> ScheduleError:
    with pytest.raises(ScheduleError) as ei:
        words(phrase, choose=n)
    return ei.value


def test_sch_ac1_a_choice_that_does_not_exist_is_refused() -> None:
    assert refused_choose("every day at 9", 3).code == "choose_invalid"
    assert refused_choose("every day at 9", 0).code == "choose_invalid"
    assert refused_choose("every day at 9am", 1).code == "choose_invalid"  # one reading: nothing to choose


# --- refusals ------------------------------------------------------------------------------------------------------


def test_sch_ac1_a_phrase_that_matches_no_rule_is_unparsed_with_the_nearest_phrases() -> None:
    e = refused("evry weekday at 8:00")
    assert e.code == "when_unparsed" and "every weekday at 8:00" in e.message
    assert refused("whenever you feel like it").code == "when_unparsed"
    assert refused("yesterday at 9am").code == "when_unparsed"
    assert refused("").code == "when_unparsed"
    assert refused("every 30 minutes between 9am and 5pm").code == "when_unparsed"
    assert refused("every 5 hours between 9am and 5pm").code == "rule_unsupported"  # 5 does not divide 24


def test_sch_ac1_numeric_dates_other_than_iso_are_date_ambiguous() -> None:
    e = refused("03/04 at 10:00")
    assert e.code == "date_ambiguous" and "2027-03-04" in e.message and "2027-04-03" in e.message  # SCH-B2
    assert refused("3.4.2027 at 10:00").code == "date_ambiguous"
    assert refused("every day at 9am from 03/04").code == "date_ambiguous"


def test_sch_ac1_abbreviations_and_unknown_zones_are_refused() -> None:
    assert refused("every day at 9 CET").code == "zone_unknown"  # SCH-B16
    assert refused("tomorrow at 9am in EST").code == "zone_unknown"
    assert refused("tomorrow at 9am PST").code == "zone_unknown"
    assert refused("tomorrow at 9am in Mars/Phobos", tz=None).code == "zone_unknown"
    assert refused("tomorrow at 9am", tz="CET").code == "zone_unknown"


def test_sch_ac1_an_interval_under_fifteen_minutes_is_too_short() -> None:
    assert refused("every 5 minutes").code == "interval_too_short"  # SCH-B17
    assert refused("every 14 minutes").code == "interval_too_short"
    assert refused("every 0 minutes").code == "when_unparsed"
    assert refused("in 2 hours from 2026-12-01").code == "when_unparsed"  # a bound belongs to a recurrence


def test_sch_ac1_the_past_and_too_far_still_refuse() -> None:
    assert refused("today at 8:15am").code == "when_in_past"
    assert refused("dec 1, 2028 at 8:00").code == "when_too_far"
    assert refused("this monday at 8:00").code == "when_in_past"  # this week's Monday is today, and 08:00 has gone
    assert words("this sunday at 10:00").when == once("2026-11-29T10:00")  # this week ends on Sunday
