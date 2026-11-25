"""The word grammar (SCH-B16, SCH-B17, SCH-B2; ADR `exact-formats-first-and-an-optional-word-grammar-echoed-back`): English phrases into the canonical form of their exact twins.

A grammar, not a guesser: a phrase is read by fixed rules, ends in the same builders as the exact formats, and a
phrase with more than one reading is a `Needs` with the readings as choices, each reading being a phrase that says
it explicitly. A phrase that matches no rule is refused `when_unparsed` with the nearest phrases.
"""

from __future__ import annotations

import dataclasses
import difflib
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from tempergraph.schedule.exact import (
    ABBREVIATIONS,
    Parsed,
    build_once,
    build_recur,
    check_zone,
    interval_rule,
    local_now,
    parse_wall,
    resolve_zone,
    with_bounds,
)
from tempergraph.schedule.model import Needs, Reading, Rule, ScheduleError, floor_minute, zone_of

TEMPLATES = (
    "in 2 hours", "tomorrow at 9am", "at 18:00", "next monday at 10:00", "on dec 1 at 08:00", "2026-12-01 08:00",
    "every day at 9am", "daily at 09:00", "every weekday at 8:00", "every monday and thursday at 7pm",
    "every 2 weeks on friday at 16:00", "every month on the 1st at 9am", "every month on the last day at 17:00",
    "every first monday of the month at 9am", "every 2 hours", "every 30 minutes", "hourly",
    "every 2 hours between 9am and 5pm on weekdays",
)
WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3,
            "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
          "september": 9, "october": 10, "november": 11, "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4,
          "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1}
_WD = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_STRICT = r"(?:noon|midnight|\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{1,2}:\d{2})"
_TIME = rf"(?:{_STRICT}|\d{{1,2}})"
WEEKDAY_SET = tuple((0, d) for d in range(5))


@dataclass
class _Ctx:
    now: datetime
    zone: str
    notes: list[str]
    tail: str = ""
    suffix: str = ""
    from_date: date | None = None
    until: str | None = None
    count: int | None = None

    @property
    def now_wall(self) -> datetime:
        return local_now(self.now, self.zone)

    @property
    def today(self) -> date:
        return self.now_wall.date()

    def compose(self, main: str) -> str:
        return main + self.tail + self.suffix


def _unparsed(raw: str) -> ScheduleError:
    near = difflib.get_close_matches(raw.lower(), TEMPLATES, n=3, cutoff=0.0)
    return ScheduleError("when_unparsed", f"{raw!r} matches no rule; the nearest phrases are: " + "; ".join(near))


def _hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _time_of(tok: str, raw: str) -> tuple[int, int, tuple[int, int] | None]:
    """(hour, minute, the other reading of a bare hour 1 to 12, else None)."""
    tok = re.sub(r"\s+", "", tok)
    if tok == "noon":
        return 12, 0, None
    if tok == "midnight":
        return 0, 0, None
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(am|pm)", tok)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if not 1 <= h <= 12 or mi > 59:
            raise _unparsed(raw)
        return h % 12 + (12 if m.group(3) == "pm" else 0), mi, None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", tok)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            raise _unparsed(raw)
        return h, mi, None
    if tok.isdigit():
        h = int(tok)
        if 1 <= h <= 12:
            return h, 0, ((h + 12) % 24, 0)  # 9 is 09:00 or 21:00; 12 is 12:00 or 00:00
        if h == 0 or 13 <= h <= 23:
            return h, 0, None
    raise _unparsed(raw)


def _yearless(month: int, day: int, c: _Ctx, raw: str) -> date:
    try:
        cand = date(c.today.year, month, day)
        return cand if cand >= c.today else date(c.today.year + 1, month, day)
    except ValueError:
        raise _unparsed(raw) from None


def _date_of(tok: str, c: _Ctx, raw: str) -> date:
    tok = tok.strip()
    if tok == "today":
        return c.today
    if tok == "tomorrow":
        return c.today + timedelta(days=1)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", tok)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            raise _unparsed(raw) from None
    m = re.fullmatch(rf"({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?", tok)
    mon, day, year = (m.group(1), m.group(2), m.group(3)) if m else (None, None, None)
    if not m:
        m = re.fullmatch(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\.?(?:,?\s+(\d{{4}}))?", tok)
        if m:
            day, mon, year = m.group(1), m.group(2), m.group(3)
    if m and mon and day:
        if year:
            try:
                return date(int(year), MONTHS[mon], int(day))
            except ValueError:
                raise _unparsed(raw) from None
        return _yearless(MONTHS[mon], int(day), c, raw)
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?", tok)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        isos: list[str] = []
        for month, dom in ((a, b), (b, a)):
            try:
                if m.group(3):
                    y = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
                    found = date(y, month, dom)
                else:
                    found = _yearless(month, dom, c, raw)
            except (ValueError, ScheduleError):
                continue
            if found.isoformat() not in isos:
                isos.append(found.isoformat())
        if not isos:
            raise _unparsed(raw)
        raise ScheduleError("date_ambiguous", f"{tok!r} is a month and a day in either order; write an ISO date: "
                                              + " or ".join(isos))
    raise _unparsed(raw)


def _daylist(text: str) -> list[int] | None:
    names = [n.strip() for n in re.split(r",|\band\b", text) if n.strip()]
    days = []
    for n in names:
        n = n[:-1] if n.endswith("s") and n[:-1] in WEEKDAYS else n
        if n not in WEEKDAYS:
            return None
        days.append(WEEKDAYS[n])
    return sorted(set(days)) or None


def _need_time(c: _Ctx, core: str, tail_suffix: str) -> Needs:
    return Needs("the phrase gives no time of day; 09:00 is offered and never applied silently",
                 [Reading("09:00", c.compose(f"{core} at 09:00{tail_suffix}"))])


# --- once --------------------------------------------------------------------------------------------------------


def _once(c: _Ctx, main: str, raw: str) -> Parsed:
    if c.from_date or c.until or c.count:
        raise _unparsed(raw)  # a bound belongs to a recurrence
    if main == "in half an hour":
        return build_once(c.now_wall + timedelta(minutes=30), c.zone, c.now, c.notes)
    m = re.fullmatch(r"in (?:(\d+)|an?) (minute|hour|day|week)s?", main)
    if m:
        n = int(m.group(1)) if m.group(1) else 1
        if n == 0:
            raise _unparsed(raw)
        unit = m.group(2)
        if unit in ("minute", "hour"):  # now plus the elapsed time, as local time in the zone
            at = floor_minute(c.now) + timedelta(**{unit + "s": n})
            wall = at.astimezone(zone_of(c.zone)).replace(tzinfo=None)
        else:
            wall = c.now_wall + timedelta(days=n * (7 if unit == "week" else 1))
        return build_once(wall, c.zone, c.now, c.notes)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}(?::\d{2})?\s*(?:z|[+-]\d{2}:?\d{2})?", main):
        wall, _ = parse_wall(main.upper(), c.zone, "the phrase", c.notes)
        return build_once(wall, c.zone, c.now, c.notes)
    body = main[3:] if main.startswith("on ") else main
    day_text, tok = "", None
    m = re.fullmatch(rf"at\s+({_TIME})", body)
    if m:
        tok = m.group(1)
    else:
        m = re.fullmatch(rf"(.+?)\s+at\s+({_TIME})", body) or re.fullmatch(rf"(.+?)\s+({_STRICT})", body)
        if m:
            day_text, tok = m.group(1), m.group(2)
        else:
            day_text = body
    if tok is None:
        _day_of(c, day_text, time(0), raw)  # a day that does not read is unparsed before the question
        raise _need_time(c, main, "")
    h, mi, alt = _time_of(tok, raw)
    if alt is not None:
        head = main[: -len(tok)]
        raise Needs("the hour has no am, pm or minutes; a 24-hour reading is offered",
                    [Reading(_hhmm(h, mi), c.compose(head + _hhmm(h, mi))), Reading(_hhmm(*alt), c.compose(head + _hhmm(*alt)))])
    if not day_text:
        wall = datetime.combine(c.today, time(h, mi))
        if wall < c.now_wall:
            tomorrow = f"tomorrow at {_hhmm(h, mi)}"
            raise Needs(f"{_hhmm(h, mi)} has passed today", [Reading(tomorrow, c.compose(tomorrow)),
                                                              Reading("refuse: it has passed today", None)])
    else:
        wall = datetime.combine(_day_of(c, day_text, time(h, mi), raw), time(h, mi))
    return build_once(wall, c.zone, c.now, c.notes)


def _day_of(c: _Ctx, text: str, t: time, raw: str) -> date:
    m = re.fullmatch(rf"(?:(next|this)\s+)?({_WD})", text)
    if not m:
        return _date_of(text, c, raw)
    wd = WEEKDAYS[m.group(2)]
    monday = c.today - timedelta(days=c.today.weekday())
    if m.group(1) == "next":
        return monday + timedelta(days=7 + wd)  # next week's, never this week's
    if m.group(1) == "this":
        return monday + timedelta(days=wd)
    d = c.today + timedelta(days=(wd - c.today.weekday()) % 7)
    return d + timedelta(days=7) if d == c.today and datetime.combine(d, t) < c.now_wall else d


# --- recur -------------------------------------------------------------------------------------------------------


def _finish(c: _Ctx, rule: Rule, starts: datetime | None) -> Parsed:
    rule = with_bounds(rule, c.until, c.count, c.zone, c.notes)
    if starts is None and c.from_date is not None:
        starts = datetime.combine(c.from_date, time(0))
    return build_recur(rule, c.zone, starts, c.now, c.notes)


def _between(c: _Ctx, m: re.Match[str], raw: str) -> Parsed:
    k = int(m.group(1))
    (h1, m1, a1), (h2, m2, a2) = _time_of(m.group(2), raw), _time_of(m.group(3), raw)
    if k == 0 or a1 or a2 or m1 or m2 or h1 > h2:
        raise _unparsed(raw)
    if 24 % k:
        raise ScheduleError("rule_unsupported", f"every {k} hours between two times: {k} does not divide 24, so the hours "
                                                "would drift from day to day")
    days: tuple[tuple[int, int], ...] = ()
    if m.group(4) and m.group(4) not in ("every day", "days"):
        if m.group(4) in ("weekday", "weekdays"):
            days = WEEKDAY_SET
        else:
            lst = _daylist(m.group(4))
            if lst is None:
                raise _unparsed(raw)
            days = tuple((0, d) for d in lst)
    rule = Rule(freq="HOURLY", interval=k, byday=days, byhour=tuple(range(h1, h2 + 1, k)))
    return _finish(c, rule, datetime.combine(c.from_date or c.today, time(h1, 0)))


def _recur(c: _Ctx, main: str, raw: str) -> Parsed:
    if main in ("hourly", "every hour"):
        return _finish(c, interval_rule(60), None)
    m = re.fullmatch(r"every (\d+) (minute|hour)s?", main)
    if m:
        if int(m.group(1)) == 0:
            raise _unparsed(raw)
        return _finish(c, interval_rule(int(m.group(1)) * (60 if m.group(2) == "hour" else 1)), None)
    m = re.fullmatch(rf"every (\d+) hours? between ({_STRICT}|\d{{1,2}}) and ({_STRICT}|\d{{1,2}})(?: on (.+))?", main)
    if m:
        return _between(c, m, raw)
    skip = re.search(r",?\s+skipping short months$", main)
    core = main[: skip.start()] if skip else main
    skip_text = ", skipping short months" if skip else ""
    base, tok = core, None
    m = re.fullmatch(rf"(.+?)\s+at\s+({_TIME})", core)
    if m:
        base, tok = m.group(1), m.group(2)
    rule = _calendar_rule(base, raw)
    if tok is None:
        raise _need_time(c, core, skip_text)
    h, mi, alt = _time_of(tok, raw)
    if alt is not None:
        head = core[: -len(tok)]
        raise Needs("the hour has no am, pm or minutes; a 24-hour reading is offered",
                    [Reading(_hhmm(h, mi), c.compose(head + _hhmm(h, mi) + skip_text)),
                     Reading(_hhmm(*alt), c.compose(head + _hhmm(*alt) + skip_text))])
    if len(rule.bymonthday) == 1 and rule.bymonthday[0] in (29, 30, 31) and not skip:
        day = rule.bymonthday[0]
        raise Needs(f"not every month has a {day}th day",
                    [Reading("skip short months", c.compose(core + ", skipping short months")),
                     Reading("use the last day", c.compose(re.sub(r"on the \d{1,2}(?:st|nd|rd|th)", "on the last day",
                                                                  core)))])
    rule = dataclasses.replace(rule, byhour=(h,), byminute=(mi,))
    return _finish(c, rule, None)


def _calendar_rule(base: str, raw: str) -> Rule:
    """The recurrence without its time of day: a frequency, an interval and the days."""
    if base == "daily":
        return Rule(freq="DAILY")
    if not base.startswith("every "):
        raise _unparsed(raw)
    body = base[6:]
    if body == "day":
        return Rule(freq="DAILY")
    if body in ("weekday", "weekdays"):
        return Rule(freq="WEEKLY", byday=WEEKDAY_SET)
    if body in ("weekend", "weekends"):
        return Rule(freq="WEEKLY", byday=((0, 5), (0, 6)))
    m = re.fullmatch(r"(\d+) days?", body)
    if m and int(m.group(1)) >= 1:
        return Rule(freq="DAILY", interval=int(m.group(1)))
    m = re.fullmatch(r"(?:(\d+) )?weeks?(?: on (.+))?", body)
    if m and int(m.group(1) or 1) >= 1:
        days = _daylist(m.group(2)) if m.group(2) else []
        if days is None:
            raise _unparsed(raw)
        return Rule(freq="WEEKLY", interval=int(m.group(1) or 1), byday=tuple((0, d) for d in days))
    m = re.fullmatch(r"(?:(\d+) )?months?(?: on the (.+))?", body)
    if m and int(m.group(1) or 1) >= 1:
        interval, what = int(m.group(1) or 1), m.group(2)
        if what is None:
            return Rule(freq="MONTHLY", interval=interval)
        if what == "last day":
            return Rule(freq="MONTHLY", interval=interval, bymonthday=(-1,))
        d = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)", what)
        if d and 1 <= int(d.group(1)) <= 31:
            return Rule(freq="MONTHLY", interval=interval, bymonthday=(int(d.group(1)),))
        o = re.fullmatch(rf"({'|'.join(ORDINALS)}) ({_WD})", what)
        if o:
            return Rule(freq="MONTHLY", interval=interval, byday=((ORDINALS[o.group(1)], WEEKDAYS[o.group(2)]),))
        raise _unparsed(raw)
    m = re.fullmatch(rf"({'|'.join(ORDINALS)}) ({_WD}) of the month", body)
    if m:
        return Rule(freq="MONTHLY", byday=((ORDINALS[m.group(1)], WEEKDAYS[m.group(2)]),))
    days = _daylist(body)
    if days is not None:
        return Rule(freq="WEEKLY", byday=tuple((0, d) for d in days))
    raise _unparsed(raw)


# --- the entry point ---------------------------------------------------------------------------------------------


def _parse(phrase: str, now: datetime, tz: str | None, machine: tuple[str, str] | None) -> Parsed:
    raw = " ".join(phrase.split()).rstrip(".").strip()
    if not raw:
        raise _unparsed(raw)
    zone_phrase: str | None = None
    z = re.search(r"\s+in\s+((?:[A-Za-z_]+/[A-Za-z0-9_+\-/]+)|[Uu][Tt][Cc])$", raw)
    if z:
        zone_phrase = "UTC" if z.group(1).lower() == "utc" else z.group(1)
        raw_main = raw[: z.start()]
    else:
        raw_main = raw
        if raw.split()[-1].upper() in ABBREVIATIONS:
            check_zone(raw.split()[-1])  # EST, CET: an abbreviation names no rules
    if zone_phrase and tz and zone_phrase != tz:
        raise ScheduleError("when_malformed", f"two zones for one schedule: {zone_phrase} in the phrase and {tz} given")
    notes: list[str] = []
    zone = resolve_zone(zone_phrase or tz, machine, notes)
    c = _Ctx(now=now, zone=zone, notes=notes, suffix=f" in {zone_phrase}" if zone_phrase else "")
    t = raw_main.lower()
    parts = re.split(r"\s+(?=(?:from|until)\s|for\s+\d+\s+times?\b)", t)
    main, clauses = parts[0], parts[1:]
    c.tail = "".join(" " + x for x in clauses)
    for clause in clauses:
        m = re.fullmatch(r"for (\d+) times?", clause)
        if m:
            c.count = int(m.group(1))
            continue
        m = re.fullmatch(r"(from|until) (.+)", clause)
        if not m:
            raise _unparsed(raw)
        d = _date_of(m.group(2), c, raw)
        if m.group(1) == "from":
            c.from_date = d
        else:
            c.until = d.isoformat()
    if main in ("hourly", "daily") or main.startswith(("every ", "daily ")):
        parsed = _recur(c, main, raw)
    else:
        parsed = _once(c, main, raw)
    return parsed


def parse_words(phrase: str, *, now: datetime, tz: str | None = None, machine: tuple[str, str] | None = None,
                choose: int | None = None) -> Parsed:
    """A phrase to the canonical form; `Needs` for an ambiguity, answered by `choose` (the reading's number)."""
    try:
        parsed = _parse(phrase, now, tz, machine)
    except Needs as ask:
        if choose is None:
            raise
        if not 1 <= choose <= len(ask.readings):
            raise ScheduleError("choose_invalid", f"--choose {choose}: the readings are 1 to {len(ask.readings)}") from None
        reading = ask.readings[choose - 1]
        if reading.phrase is None:
            raise ScheduleError("when_in_past", f"refused by the choice: {reading.label}") from None
        return parse_words(reading.phrase, now=now, tz=tz, machine=machine)  # the choice is spent; a second question is asked
    if choose is not None:
        raise ScheduleError("choose_invalid", f"--choose {choose}: the phrase has one reading; leave --choose out")
    parsed.phrase = phrase
    return parsed
