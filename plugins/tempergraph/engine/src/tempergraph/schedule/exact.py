"""The exact formats: `--at`, `--rrule`, `--every`, `--cron`, with `--tz`, `--starts`, `--until` and `--count`
(SCH-B15, SCH-B29 to SCH-B32, SCH-B34 to SCH-B36; ADR `exact-formats-first-and-an-optional-word-grammar-echoed-back`).

No model and no guess: a value is the canonical form or a refusal, and so never a `needs`. The word grammar
(`words.py`) ends in the same builders, so a phrase and its exact twin store one form.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta, timezone

from tempergraph.schedule.model import (
    HORIZON_DAYS,
    MIN_INTERVAL_MIN,
    Rule,
    ScheduleError,
    When,
    floor_minute,
    machine_zone,
    next_slots,
    parse_rule,
    shortest_gap_minutes,
    wall_to_utc,
    zone_of,
)

ISO_MINUTE = "%Y-%m-%dT%H:%M"
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$")
_MONTHS = {n: i + 1 for i, n in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                           "dec"))}
_DOWS = {n: i for i, n in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat"))}
ABBREVIATIONS = {"EST", "EDT", "CST", "CDT", "MST", "MDT", "PST", "PDT", "CET", "CEST", "EET", "EEST", "WET", "WEST",
                  "BST", "GMT", "IST", "JST", "KST", "HST", "AKST", "AKDT", "NZST", "NZDT", "AEST", "AEDT", "MSK"}


@dataclass
class Parsed:
    """A parsed When: the canonical form, what was assumed on the way, and what the person gave."""

    when: When
    assumptions: list[str] = field(default_factory=list)
    phrase: str | None = None
    given: dict[str, str] = field(default_factory=dict)


def check_zone(name: str) -> str:
    """An IANA name; `UTC` is accepted and an abbreviation such as `EST` or `CET` is refused: it names no rules."""
    if "/" not in name and name != "UTC":
        hint = " (an abbreviation names no rules)" if name.upper() in ABBREVIATIONS else ""
        raise ScheduleError("zone_unknown", f"{name!r} is not an IANA time zone name{hint}; use one like Europe/Warsaw")
    zone_of(name)
    return name


def resolve_zone(tz: str | None, machine: tuple[str, str] | None, assumptions: list[str]) -> str:
    if tz is not None:
        return check_zone(tz)
    name, source = machine or machine_zone()
    assumptions.append(f"zone from this machine ({source})")
    return name


def local_now(now: datetime, zone_name: str) -> datetime:
    return floor_minute(now).astimezone(zone_of(zone_name)).replace(tzinfo=None)


def parse_wall(text: str, zone_name: str, flag: str, assumptions: list[str], *, need_time: bool = True
               ) -> tuple[datetime, bool]:
    """ISO 8601 as a local date-time to the minute: local, or with an offset or `Z` (the same instant, in the zone).
    Returns the wall time and whether the text had a time; a date alone is midnight."""
    m = _ISO.match(text.strip())
    if not m:
        raise ScheduleError("when_malformed", f"{flag} {text!r}: ISO 8601 is needed, such as 2026-12-01T08:00")
    y, mo, d, hh, mi, ss, off = m.groups()
    if hh is None and (need_time or off):
        raise ScheduleError("when_malformed", f"{flag} {text!r}: a date and a time are needed, such as 2026-12-01T08:00")
    try:
        wall = datetime(int(y), int(mo), int(d), int(hh or 0), int(mi or 0))
    except ValueError:
        raise ScheduleError("when_malformed", f"{flag} {text!r}: not a date and time that exist") from None
    if ss and int(ss) != 0:
        assumptions.append(f"seconds dropped from {flag}")
    if off:
        if off == "Z":
            tzinfo = UTC
        else:
            sign = 1 if off[0] == "+" else -1
            digits = off[1:].replace(":", "")
            tzinfo = timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:])))
        zone = zone_of(zone_name)
        wall = wall.replace(tzinfo=tzinfo).astimezone(zone).replace(tzinfo=None)
        assumptions.append(f"{flag} {text} read as {wall.strftime(ISO_MINUTE)} in {zone_name}")
    return wall, hh is not None


def build_once(wall: datetime, zone_name: str, now: datetime, assumptions: list[str]) -> Parsed:
    zone = zone_of(zone_name)
    u = wall_to_utc(wall, zone)
    if u < floor_minute(now):
        raise ScheduleError("when_in_past", f"{wall.strftime(ISO_MINUTE)} in {zone_name} has passed")
    if u > now + timedelta(days=HORIZON_DAYS):
        raise ScheduleError("when_too_far", f"{wall.strftime(ISO_MINUTE)} is more than {HORIZON_DAYS} days ahead")
    return Parsed(When(kind="once", zone=zone_name, at=wall.strftime(ISO_MINUTE)), assumptions)


def build_recur(rule: Rule, zone_name: str, starts: datetime | None, now: datetime, assumptions: list[str]) -> Parsed:
    """The canonical recurrence, or the refusal: slots under 15 minutes apart, ended, or no slot within 400 days."""
    if starts is None:
        starts = local_now(now, zone_name)
        if rule.is_interval or rule.interval > 1:
            assumptions.append("starts now: the first slot, and the count of intervals, run from this minute")
    when = When(kind="recur", zone=zone_name, rule=rule.render(), starts=starts.strftime(ISO_MINUTE))
    start = floor_minute(now)
    if not rule.is_interval:
        gap = shortest_gap_minutes(when, start)
        if gap is not None and gap < MIN_INTERVAL_MIN:
            raise ScheduleError("interval_too_short", f"slots {gap} minutes apart; the least is {MIN_INTERVAL_MIN} minutes")
    if not next_slots(when, start, 1, HORIZON_DAYS):
        if next_slots(when, start, 1, 4000):
            raise ScheduleError("when_too_far", f"the first slot is more than {HORIZON_DAYS} days ahead")
        if rule.until is not None or rule.count is not None:
            raise ScheduleError("when_in_past", "the recurrence has ended: no slot at or after now")
        raise ScheduleError("when_too_far", f"no slot within {HORIZON_DAYS} days")
    return Parsed(when, assumptions)


# --- --every ----------------------------------------------------------------------------------------------------

_DURATION = re.compile(r"^P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(\d+S)?)?$")


def parse_every(text: str) -> Rule:
    """An ISO 8601 duration of weeks, days, hours and minutes (a day is 24 elapsed hours) as an interval rule."""
    m = _DURATION.match(text.strip().upper())
    if not m or not any(m.groups()[:4]) or m.group(5) or text.strip().upper() in ("P", "PT"):
        raise ScheduleError("when_malformed", f"--every {text!r}: an ISO 8601 duration of weeks, days, hours and minutes "
                                              "is needed, such as PT2H (years, months and seconds are not accepted)")
    w, d, h, mi = (int(x or 0) for x in m.groups()[:4])
    total = w * 10080 + d * 1440 + h * 60 + mi
    if total == 0:
        raise ScheduleError("when_malformed", f"--every {text!r}: a duration longer than zero is needed")
    return interval_rule(total)


def interval_rule(total_minutes: int) -> Rule:
    """The one interval rule for a period: whole hours are `HOURLY`, any other period `MINUTELY`; 15 minutes at least."""
    if total_minutes < MIN_INTERVAL_MIN:
        raise ScheduleError("interval_too_short", f"the shortest gap is {total_minutes} minutes; the least is "
                                                  f"{MIN_INTERVAL_MIN} minutes")
    if total_minutes % 60 == 0:
        return Rule(freq="HOURLY", interval=total_minutes // 60)
    return Rule(freq="MINUTELY", interval=total_minutes)


# --- --cron -----------------------------------------------------------------------------------------------------


def _cron_field(text: str, name: str, lo: int, hi: int, names: dict[str, int] | None) -> set[int]:
    def bad(why: str) -> ScheduleError:
        return ScheduleError("when_malformed", f"cron {name} field {text!r}: {why}")

    def number(tok: str) -> int:
        if tok.isdigit():
            return int(tok)
        if names and tok.lower() in names:
            return names[tok.lower()]
        raise bad(f"{tok!r} is not a number" + (" or a name" if names else ""))

    out: set[int] = set()
    for item in text.split(","):
        m = re.fullmatch(r"([^/]+)(?:/(\d+))?", item)
        if not m:
            raise bad("lists, ranges and steps are written like 1,5 and 9-17 and */15")
        body, step_text = m.groups()
        step = int(step_text) if step_text is not None else 1
        if step < 1:
            raise bad("a step is 1 or more")
        if body == "*":
            a, b = lo, (6 if name == "day of week" else hi)
        elif "-" in body:
            parts = body.split("-")
            if len(parts) != 2:
                raise bad("a range is a-b")
            a, b = number(parts[0]), number(parts[1])
        else:
            if step_text is not None:
                raise bad("a step goes on * or on a range")
            a = b = number(body)
        if a < lo or b > hi or a > b:
            raise bad(f"values are {lo} to {hi}, a range does not run backwards")
        out |= set(range(a, b + 1, step))
    return out


def parse_cron(text: str) -> Rule:
    """Five fields to the one stored rule that fires at the local times they name (SCH-B29, SCH-B30)."""
    fields = text.split()
    if len(fields) != 5:
        raise ScheduleError("when_malformed", f"cron {text!r}: five fields are needed (minute, hour, day of month, month, "
                                              "day of week); macros, seconds and a year are not accepted")
    mi = _cron_field(fields[0], "minute", 0, 59, None)
    ho = _cron_field(fields[1], "hour", 0, 23, None)
    dom = _cron_field(fields[2], "day of month", 1, 31, None)
    mon = _cron_field(fields[3], "month", 1, 12, _MONTHS)
    dow = {d % 7 for d in _cron_field(fields[4], "day of week", 0, 7, _DOWS)}
    hour_star, dom_star, mon_star, dow_star = len(ho) == 24, len(dom) == 31, len(mon) == 12, len(dow) == 7
    if not mon_star:
        raise ScheduleError("rule_unsupported", "cron month field: a restricted month has no stored form")
    if not dom_star and not dow_star:
        raise ScheduleError("rule_unsupported", "cron day of month and the day of week both restricted: no one rule holds "
                                                "cron's either-day reading")
    if hour_star:
        freq = "HOURLY"
    elif not dow_star:
        freq = "WEEKLY"
    elif not dom_star:
        freq = "MONTHLY"
    else:
        freq = "DAILY"
    return Rule(freq=freq, byday=tuple((0, (d - 1) % 7) for d in sorted(dow)) if not dow_star else (),
                bymonthday=tuple(sorted(dom)) if not dom_star else (), byhour=() if hour_star else tuple(sorted(ho)),
                byminute=tuple(sorted(mi)))


# --- the entry point --------------------------------------------------------------------------------------------


def with_bounds(rule: Rule, until: str | None, count: int | None, zone_name: str, assumptions: list[str]) -> Rule:
    if count is not None:
        if count < 1:
            raise ScheduleError("when_malformed", f"--count {count}: a whole number of 1 or more is needed")
        if rule.count is not None or rule.until is not None:
            raise ScheduleError("when_malformed", "--count with COUNT or UNTIL already in the rule")
        rule = dataclasses.replace(rule, count=count)
    if until is not None:
        if rule.count is not None or rule.until is not None:
            raise ScheduleError("when_malformed", "--until with COUNT or UNTIL already in the rule (RFC 5545 allows one)")
        wall, has_time = parse_wall(until, zone_name, "--until", assumptions, need_time=False)
        if not has_time:
            wall = datetime.combine(wall.date(), time(23, 59))
        rule = dataclasses.replace(rule, until=wall_to_utc(wall, zone_of(zone_name)))
    return rule


def parse_exact(*, at: str | None = None, rrule: str | None = None, every: str | None = None, cron: str | None = None,
                tz: str | None = None, starts: str | None = None, until: str | None = None, count: int | None = None,
                now: datetime, machine: tuple[str, str] | None = None) -> Parsed:
    """One exact format to the canonical form, with no model (SCH-B15); a refusal is a ScheduleError."""
    given = {flag: value for flag, value in (("--at", at), ("--rrule", rrule), ("--every", every), ("--cron", cron))
             if value is not None}
    if len(given) != 1:
        raise ScheduleError("when_malformed", "give exactly one of --at, --rrule, --every, --cron (or a phrase)")
    assumptions: list[str] = []
    zone_name = resolve_zone(tz, machine, assumptions)
    flag, value = next(iter(given.items()))
    if at is not None:
        if starts is not None or until is not None or count is not None:
            raise ScheduleError("when_malformed", "--starts, --until and --count belong to a recurrence, not to --at")
        wall, _ = parse_wall(at, zone_name, "--at", assumptions)
        parsed = build_once(wall, zone_name, now, assumptions)
    else:
        if rrule is not None:
            rule = parse_rule(rrule)
        elif every is not None:
            rule = parse_every(every)
        else:
            rule = parse_cron(str(cron))
        rule = with_bounds(rule, until, count, zone_name, assumptions)
        start = parse_wall(starts, zone_name, "--starts", assumptions, need_time=False)[0] if starts is not None else None
        parsed = build_recur(rule, zone_name, start, now, assumptions)
    parsed.given = {"format": flag, "value": value}
    return parsed
