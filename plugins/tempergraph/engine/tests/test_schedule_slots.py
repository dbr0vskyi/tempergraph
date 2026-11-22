"""Schedule slots with daylight saving (SCH-B20, SCH-B3; SCH-AC2) and the dependencies they rest on (AC 11)."""

from __future__ import annotations

import random
import tomllib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tempergraph.schedule import model
from tempergraph.schedule.model import When, next_slots, parse_rule, slots_between

ENGINE = Path(__file__).resolve().parents[1]


def utc(*a: int) -> datetime:
    return datetime(*a, tzinfo=UTC)


def recur(rule: str, starts: str, zone: str) -> When:
    return When(kind="recur", zone=zone, rule=parse_rule(rule).render(), starts=starts)


def instants(when: When, start: datetime, end: datetime) -> list[str]:
    return [s.utc.strftime("%Y-%m-%dT%H:%MZ") for s in slots_between(when, start, end)]


# --- SCH-AC2 fixtures: one zone, a fake clock ---------------------------------------------------------------------


def test_sch_ac2_warsaw_gap_takes_the_offset_before_the_gap() -> None:
    # SCH-B3: every day at 02:30 in Europe/Warsaw, around 2027-03-28 and 2027-10-31
    w = recur("FREQ=DAILY;BYHOUR=2;BYMINUTE=30", "2027-03-26T00:00", "Europe/Warsaw")
    got = instants(w, utc(2027, 3, 27), utc(2027, 3, 30))
    assert got == ["2027-03-27T01:30Z", "2027-03-28T01:30Z", "2027-03-29T00:30Z"]
    gap = [s for s in slots_between(w, utc(2027, 3, 28), utc(2027, 3, 29)) if s.note][0]
    assert gap.note == "gap" and gap.local.strftime("%H:%M") == "03:30"  # 02:30 does not exist; 03:30 local


def test_sch_ac2_warsaw_overlap_fires_once_at_the_first_occurrence() -> None:
    w = recur("FREQ=DAILY;BYHOUR=2;BYMINUTE=30", "2027-10-29T00:00", "Europe/Warsaw")
    got = slots_between(w, utc(2027, 10, 30), utc(2027, 11, 2))
    assert [s.utc.strftime("%Y-%m-%dT%H:%MZ") for s in got] == ["2027-10-30T00:30Z", "2027-10-31T00:30Z",
                                                                   "2027-11-01T01:30Z"]
    assert [s.note for s in got] == ["", "overlap", ""]


def test_sch_ac2_new_york_gap_and_overlap() -> None:
    w = recur("FREQ=DAILY;BYHOUR=1,2;BYMINUTE=30", "2027-03-13T00:00", "America/New_York")
    assert instants(w, utc(2027, 3, 14), utc(2027, 3, 15)) == ["2027-03-14T06:30Z", "2027-03-14T07:30Z"]
    # 02:30 is in the gap: EST offset (-5) before the gap gives 07:30 UTC, which is 03:30 EDT
    w2 = recur("FREQ=DAILY;BYHOUR=1;BYMINUTE=30", "2027-11-05T00:00", "America/New_York")
    assert instants(w2, utc(2027, 11, 7), utc(2027, 11, 8)) == ["2027-11-07T05:30Z"]  # first 01:30, EDT


def test_sch_ac2_calendar_rules_keep_wall_clock_time_on_both_sides() -> None:
    w = recur("FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "2027-03-20T00:00", "Europe/Warsaw")
    got = slots_between(w, utc(2027, 3, 26), utc(2027, 3, 30))
    assert {s.local.strftime("%H:%M") for s in got} == {"09:00"}
    assert [s.utc.hour for s in got] == [8, 8, 7, 7]  # +01:00 before 2027-03-28, +02:00 after


def test_sch_ac2_interval_rules_step_elapsed_utc_time() -> None:
    w = recur("FREQ=HOURLY;INTERVAL=6", "2027-03-27T12:00", "Europe/Warsaw")
    got = slots_between(w, utc(2027, 3, 27), utc(2027, 3, 29))
    gaps = {b.utc - a.utc for a, b in zip(got, got[1:], strict=False)}
    assert gaps == {timedelta(hours=6)}  # every elapsed 6 hours
    assert [s.local.strftime("%d %H:%M") for s in got][:5] == ["27 12:00", "27 18:00", "28 00:00", "28 07:00", "28 13:00"]


def test_sch_ac2_once_takes_the_gap_rule_too() -> None:
    w = When(kind="once", zone="Europe/Warsaw", at="2027-03-28T02:30")
    (s,) = slots_between(w, utc(2027, 3, 1), utc(2027, 4, 1))
    assert s.utc == utc(2027, 3, 28, 1, 30) and s.note == "gap" and s.local.hour == 3
    assert next_slots(w, utc(2027, 3, 28, 1, 31), 3) == []  # past


def test_sch_ac2_count_until_and_monthly_forms() -> None:
    w = recur("FREQ=DAILY;BYHOUR=9;BYMINUTE=0;COUNT=3", "2027-01-04T00:00", "UTC")
    assert instants(w, utc(2027, 1, 1), utc(2027, 2, 1)) == ["2027-01-04T09:00Z", "2027-01-05T09:00Z", "2027-01-06T09:00Z"]
    w = recur("FREQ=DAILY;BYHOUR=9;BYMINUTE=0;UNTIL=20270106T090000Z", "2027-01-04T00:00", "UTC")
    assert len(instants(w, utc(2027, 1, 1), utc(2027, 2, 1))) == 3  # UNTIL is inclusive
    w = recur("FREQ=MONTHLY;BYMONTHDAY=-1;BYHOUR=17;BYMINUTE=0", "2027-01-01T00:00", "UTC")
    assert instants(w, utc(2027, 1, 1), utc(2027, 4, 1)) == ["2027-01-31T17:00Z", "2027-02-28T17:00Z", "2027-03-31T17:00Z"]
    w = recur("FREQ=MONTHLY;BYDAY=1MO;BYHOUR=9;BYMINUTE=0", "2027-01-01T00:00", "UTC")
    assert instants(w, utc(2027, 1, 1), utc(2027, 3, 1)) == ["2027-01-04T09:00Z", "2027-02-01T09:00Z"]
    w = recur("FREQ=MONTHLY;BYDAY=-1FR;BYHOUR=9;BYMINUTE=0", "2027-01-01T00:00", "UTC")
    assert instants(w, utc(2027, 1, 1), utc(2027, 3, 1)) == ["2027-01-29T09:00Z", "2027-02-26T09:00Z"]
    w = recur("FREQ=WEEKLY;INTERVAL=2;BYDAY=FR;BYHOUR=16;BYMINUTE=0", "2027-01-04T00:00", "UTC")
    assert instants(w, utc(2027, 1, 1), utc(2027, 2, 10)) == ["2027-01-08T16:00Z", "2027-01-22T16:00Z", "2027-02-05T16:00Z"]


def test_sch_ac2_slots_are_recomputed_from_zone_data_at_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    w = recur("FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "2027-06-01T00:00", "Test/Zone")
    monkeypatch.setattr(model, "zone_of", lambda name: ZoneInfo("Europe/Warsaw"))
    a = next_slots(w, utc(2027, 6, 1), 1)[0].utc
    monkeypatch.setattr(model, "zone_of", lambda name: ZoneInfo("America/New_York"))
    b = next_slots(w, utc(2027, 6, 1), 1)[0].utc
    assert (a.hour, b.hour) == (7, 13)  # nothing about the zone is kept between calls


def test_sch_ac2_next_slots_bounds_a_rule_that_never_matches() -> None:
    w = recur("FREQ=MONTHLY;INTERVAL=12;BYMONTHDAY=31;BYHOUR=9;BYMINUTE=0", "2027-04-01T00:00", "UTC")
    assert next_slots(w, utc(2027, 4, 1), 3) == []  # an empty answer, not a loop to the year 9999


# --- SCH-AC2: 5,000 random rules in 20 zones against dateutil -----------------------------------------------------

ZONES = ("Europe/Warsaw", "Europe/London", "Europe/Dublin", "Europe/Moscow", "Europe/Berlin", "America/New_York",
         "America/Chicago", "America/Los_Angeles", "America/Santiago", "America/Havana", "America/Sao_Paulo",
         "Australia/Sydney", "Australia/Lord_Howe", "Pacific/Auckland", "Asia/Tokyo", "Asia/Kolkata",
         "Asia/Kathmandu", "Asia/Beirut", "Africa/Cairo", "UTC")
DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


def _random_rule(rnd: random.Random) -> tuple[dict[str, object], str]:
    """A random rule of the stored subset, as parts, and its starts; no rule that dateutil cannot iterate."""
    d0 = date(2026, 6, 1) + timedelta(days=rnd.randrange(0, 420))
    pick = rnd.random()
    spec: dict[str, object] = {}
    hour0 = rnd.choice((0, 1, 2, 3, 2, 1, rnd.randrange(24)))
    minute0 = rnd.choice((0, 30, 15, 45, rnd.randrange(60)))
    if pick < 0.03:  # an interval rule: MINUTELY (15 minutes and more) or HOURLY with INTERVAL
        if rnd.random() < 0.5:
            spec.update(freq="MINUTELY", interval=rnd.choice((15, 20, 30, 45, 75, 90, 180, 600)))
        else:
            spec.update(freq="HOURLY", interval=rnd.choice((1, 2, 3, 5, 6, 8, 12, 24, 36)))
    elif pick < 0.08:  # an hourly calendar rule: a BY part on the local clock
        k = rnd.choice((1, 2, 3, 4, 6, 8, 12))
        spec.update(freq="HOURLY", interval=k, byminute=sorted(rnd.sample((0, 10, 15, 30, 45, 50), rnd.randrange(1, 3))))
        if rnd.random() < 0.6:  # the start hour stays in the hours, so that dateutil can reach one
            hours = {hour0} | {h for h in range(24) if rnd.random() < 0.4 and (h - hour0) % k == 0}
            spec["byhour"] = sorted(hours)
        if rnd.random() < 0.4:
            spec["byday"] = [(0, w) for w in sorted(rnd.sample(range(7), rnd.randrange(1, 6)))]
    else:
        freq = rnd.choice(("DAILY", "DAILY", "DAILY", "WEEKLY", "WEEKLY", "MONTHLY", "MONTHLY"))
        spec.update(freq=freq, interval=rnd.choice((1, 1, 1, 2, 3)))
        spec["byhour"] = sorted(set(rnd.sample(range(24), rnd.randrange(1, 3)) + ([hour0] if rnd.random() < 0.5 else [])))
        spec["byminute"] = sorted(set(rnd.sample((0, 15, 30, 45, rnd.randrange(60)), rnd.randrange(1, 3))))
        if freq == "DAILY" and rnd.random() < 0.3:
            spec["byday"] = [(0, w) for w in sorted(rnd.sample(range(7), rnd.randrange(1, 6)))]
        if freq == "WEEKLY" and rnd.random() < 0.8:
            spec["byday"] = [(0, w) for w in sorted(rnd.sample(range(7), rnd.randrange(1, 4)))]
        if freq == "MONTHLY":
            what = rnd.random()
            if what < 0.45:
                spec["bymonthday"] = sorted(set(rnd.sample((1, 5, 15, 28, 29, 30, 31, -1), rnd.randrange(1, 3))))
            elif what < 0.7:
                spec["byday"] = [(rnd.choice((1, 2, 3, 4, -1)), rnd.randrange(7))]
            elif what < 0.85:
                spec["byday"] = [(0, w) for w in sorted(rnd.sample(range(7), rnd.randrange(1, 3)))]
        if freq == "WEEKLY" and rnd.random() < 0.1:
            spec["bymonthday"] = sorted(rnd.sample(range(1, 29), 6))
    if rnd.random() < 0.2:
        spec["count"] = rnd.randrange(1, 60)
    elif rnd.random() < 0.25:
        spec["until"] = utc(2026, 11, 23) + timedelta(minutes=rnd.randrange(0, 2 * 365 * 1440))
    return spec, f"{d0.isoformat()}T{hour0:02d}:{minute0:02d}"


def _text(spec: dict[str, object]) -> str:
    parts = [f"FREQ={spec['freq']}"]
    if spec["interval"] != 1:
        parts.append(f"INTERVAL={spec['interval']}")
    byday = spec.get("byday")
    if byday:
        parts.append("BYDAY=" + ",".join((f"{n}" if n else "") + DAYS[w] for n, w in sorted(byday, key=lambda x: (x[1], x[0]))))  # type: ignore[attr-defined]
    for key in ("bymonthday", "byhour", "byminute"):
        if spec.get(key):
            parts.append(f"{key.upper()}=" + ",".join(str(v) for v in sorted(spec[key])))  # type: ignore[call-overload]
    if spec.get("count"):
        parts.append(f"COUNT={spec['count']}")
    if spec.get("until"):
        parts.append("UNTIL=" + spec["until"].strftime("%Y%m%dT%H%M%SZ"))  # type: ignore[attr-defined]
    return ";".join(parts)


def _reference(spec: dict[str, object], starts: str, zone: ZoneInfo, a: datetime, b: datetime) -> list[datetime]:
    from dateutil import rrule as dr

    freq = {"MINUTELY": dr.MINUTELY, "HOURLY": dr.HOURLY, "DAILY": dr.DAILY, "WEEKLY": dr.WEEKLY,
            "MONTHLY": dr.MONTHLY}[str(spec["freq"])]
    dt0 = datetime.fromisoformat(starts)
    interval_rule = spec["freq"] == "MINUTELY" or (spec["freq"] == "HOURLY" and not any(
        spec.get(k) for k in ("byday", "bymonthday", "byhour", "byminute")))
    kw: dict[str, object] = {"interval": spec["interval"], "count": spec.get("count"), "until": spec.get("until")}
    if interval_rule:  # steps elapsed UTC time from the start
        kw["dtstart"] = dt0.replace(tzinfo=zone).astimezone(UTC)
    else:  # steps the local clock: a zone-aware start
        kw["dtstart"] = dt0.replace(tzinfo=zone)
        kw["bysecond"] = 0
        if spec.get("byday"):
            kw["byweekday"] = [dr.weekday(w, n or None) for n, w in spec["byday"]]  # type: ignore[attr-defined]
        for key in ("bymonthday", "byhour", "byminute"):
            if spec.get(key):
                kw[key] = list(spec[key])  # type: ignore[call-overload]
    rule = dr.rrule(freq, **kw)  # type: ignore[arg-type]
    return sorted({x.astimezone(UTC) for x in rule.between(a, b, inc=True)})


def test_sch_ac2_five_thousand_random_rules_equal_dateutil_over_two_years() -> None:
    rnd = random.Random(20261123)
    a, b = utc(2026, 11, 23), utc(2028, 11, 23)
    seen = {"gap": 0, "overlap": 0}
    total = 0
    for i in range(5000):
        spec, starts = _random_rule(rnd)
        zone_name = ZONES[i % len(ZONES)]
        zone = ZoneInfo(zone_name)
        text = _text(spec)
        when = recur(text, starts, zone_name)
        assert when.rule == text, (text, when.rule)  # the model writes what the test wrote: canonical order
        mine = slots_between(when, a, b)
        want = _reference(spec, starts, zone, a, b)
        assert [s.utc for s in mine] == want, (i, zone_name, starts, text)
        total += len(mine)
        for s in mine:
            if s.note:
                seen[s.note] += 1
    assert total > 100_000  # the corpus is not a handful of empty rules
    assert seen["gap"] > 0 and seen["overlap"] > 0  # the years hold gaps and overlaps, and they were compared


# --- AC 11: the dependencies ------------------------------------------------------------------------------------


def test_ac11_tzdata_is_a_dependency_and_dateutil_a_dev_dependency() -> None:
    import dateutil  # noqa: F401
    import tzdata  # noqa: F401

    doc = tomllib.loads((ENGINE / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    deps = [d.split(">")[0].split("=")[0].split("<")[0].strip() for d in doc["dependencies"]]
    dev = [d.split(">")[0].split("=")[0].split("<")[0].strip() for d in doc["optional-dependencies"]["dev"]]
    assert "tzdata" in deps and "python-dateutil" not in deps
    assert "python-dateutil" in dev
