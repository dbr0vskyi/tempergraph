"""Rule model and slots with daylight saving (SCH-B18, SCH-B20, SCH-B3; ADR-0097).

Pure and clock-injected: nothing here reads the clock, the home store or a process. A schedule's When is a `once`
(`at` and a zone) or a `recur` (a stored RECUR rule, `starts` and a zone). Slots are computed in the schedule's one
IANA zone and carried as UTC with their local time. A *calendar* rule steps the local wall clock (every day at 09:00
is 09:00 on both sides of a change); an *interval* rule (`MINUTELY`, or `HOURLY` with `INTERVAL` and no other `BY`
part) steps elapsed UTC time from `starts`. A local time in a gap takes the offset from before the gap (02:30 on a
spring-forward day is 03:30, RFC 5545 section 3.3.5); a local time in an overlap is taken once, at the first
occurrence (`fold=0`).
"""

from __future__ import annotations

import calendar
import contextlib
import heapq
import os
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

Clock = Callable[[], datetime]

DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
FREQS = ("MINUTELY", "HOURLY", "DAILY", "WEEKLY", "MONTHLY")
MIN_INTERVAL_MIN = 15
HORIZON_DAYS = 400  # SCH-B15: a first slot more than 400 days ahead is `when_too_far`


class ScheduleError(Exception):
    """A refusal with its reason code (exit 2, or 3 for `needs`); nothing was written."""

    def __init__(self, code: str, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.code, self.message, self.exit_code = code, message, exit_code


@dataclass(frozen=True)
class Reading:
    """One reading of an ambiguous phrase: its label, and the phrase that says it explicitly (None: refuse)."""

    label: str
    phrase: str | None


class Needs(Exception):
    """A phrase with more than one reading (SCH-B2): exit 3 with the readings as choices."""

    def __init__(self, question: str, readings: list[Reading]) -> None:
        super().__init__(question)
        self.question, self.readings = question, readings


def system_clock() -> datetime:
    return datetime.now(UTC)


def floor_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def zone_of(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ScheduleError("zone_unknown", f"{name!r} is not an IANA time zone name (for example Europe/Warsaw)") from exc


def machine_zone() -> tuple[str, str]:
    """The machine's zone and where it was read from: `TZ`, the `/etc/localtime` link, `/etc/timezone`, else UTC."""
    tz = (os.environ.get("TZ") or "").lstrip(":")
    candidates: list[tuple[str, str]] = [(tz, "TZ")] if tz else []
    try:
        link = Path("/etc/localtime").resolve()
        if "zoneinfo/" in str(link):
            candidates.append((str(link).split("zoneinfo/", 1)[1], "/etc/localtime"))
    except OSError:
        pass
    with contextlib.suppress(OSError):
        candidates.append((Path("/etc/timezone").read_text(encoding="utf-8").strip(), "/etc/timezone"))
    for name, source in candidates:
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            continue
        return name, source
    return "UTC", "default"


def wall_to_utc(wall: datetime, zone: ZoneInfo) -> datetime:
    """The gap rule (offset from before the gap) and the overlap rule (first occurrence) are `fold=0`."""
    return wall.replace(tzinfo=zone, fold=0).astimezone(UTC)


def wall_note(wall: datetime, zone: ZoneInfo) -> str:
    """`gap` when the local time does not exist, `overlap` when it happens twice, else empty."""
    first, second = wall.replace(tzinfo=zone, fold=0).utcoffset(), wall.replace(tzinfo=zone, fold=1).utcoffset()
    if first == second:
        return ""
    return "gap" if first is not None and second is not None and first < second else "overlap"


def utc_offset(zone: ZoneInfo, at: datetime) -> str:
    off = at.astimezone(zone).utcoffset() or timedelta(0)
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    return f"{sign}{abs(total) // 60:02d}:{abs(total) % 60:02d}"


# --- the stored rule --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    freq: str
    interval: int = 1
    byday: tuple[tuple[int, int], ...] = ()  # (ordinal, weekday), ordinal 0 for every such weekday, 0 = MO
    bymonthday: tuple[int, ...] = ()
    byhour: tuple[int, ...] = ()
    byminute: tuple[int, ...] = ()
    count: int | None = None
    until: datetime | None = None  # UTC

    @property
    def is_interval(self) -> bool:
        return self.freq in ("MINUTELY", "HOURLY") and not (self.byday or self.bymonthday or self.byhour
                                                            or self.byminute)

    @property
    def period(self) -> timedelta:
        """The elapsed period of an interval rule; for a calendar rule, FREQ times INTERVAL (catch-up window)."""
        unit = {"MINUTELY": timedelta(minutes=1), "HOURLY": timedelta(hours=1), "DAILY": timedelta(days=1),
                "WEEKLY": timedelta(weeks=1), "MONTHLY": timedelta(days=31)}[self.freq]
        return unit * self.interval

    def render(self) -> str:
        """The stored form: parts in this order, each list ascending (SCH-B18)."""
        parts = [f"FREQ={self.freq}"]
        if self.interval != 1:
            parts.append(f"INTERVAL={self.interval}")
        if self.byday:
            parts.append("BYDAY=" + ",".join((str(n) if n else "") + DAYS[w]
                                              for n, w in sorted(self.byday, key=lambda x: (x[1], x[0]))))
        for key, vals in (("BYMONTHDAY", self.bymonthday), ("BYHOUR", self.byhour), ("BYMINUTE", self.byminute)):
            if vals:
                parts.append(f"{key}=" + ",".join(str(v) for v in sorted(vals)))
        if self.count is not None:
            parts.append(f"COUNT={self.count}")
        if self.until is not None:
            parts.append("UNTIL=" + self.until.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"))
        return ";".join(parts)


_UNSUPPORTED_PARTS = ("BYMONTH", "BYSETPOS", "BYWEEKNO", "BYYEARDAY", "BYSECOND", "WKST")
_DAY = re.compile(r"^([+-]?\d{1,2})?(MO|TU|WE|TH|FR|SA|SU)$")


def _ints(key: str, text: str, lo: int, hi: int) -> tuple[int, ...]:
    try:
        vals = [int(x) for x in text.split(",")]
    except ValueError:
        raise ScheduleError("when_malformed", f"{key}={text!r}: a comma-separated list of whole numbers is needed") from None
    if not vals or any(v < lo or v > hi for v in vals):
        raise ScheduleError("when_malformed", f"{key}={text!r}: values must be {lo} to {hi}")
    return tuple(sorted(set(vals)))


def parse_rule(text: str) -> Rule:
    """An RFC 5545 RECUR of the stored subset (SCH-B18, SCH-B31) as a Rule; `when_malformed` or `rule_unsupported`."""
    body = text.strip()
    if body.upper().startswith("RRULE:"):
        body = body[6:]
    upper = body.upper()
    for line in ("DTSTART", "RDATE", "EXDATE"):
        if line in upper:
            raise ScheduleError("rule_unsupported", f"{line}: the rule is one RECUR; give the start with --starts")
    if not body or "\n" in body:
        raise ScheduleError("when_malformed", "--rrule: an RFC 5545 RECUR such as FREQ=DAILY;BYHOUR=9;BYMINUTE=0 is needed")
    parts: dict[str, str] = {}
    for item in body.split(";"):
        key, sep, val = item.partition("=")
        key = key.strip().upper()
        if not sep or not key or not val.strip() or key in parts:
            raise ScheduleError("when_malformed", f"--rrule: {item!r} is not a KEY=VALUE part, or repeats a part")
        parts[key] = val.strip().upper()
    freq = parts.pop("FREQ", None)
    if freq is None:
        raise ScheduleError("when_malformed", "--rrule: FREQ is needed")
    if freq in ("YEARLY", "SECONDLY"):
        raise ScheduleError("rule_unsupported", f"FREQ={freq}: the stored rule has MINUTELY, HOURLY, DAILY, WEEKLY and MONTHLY")
    if freq not in FREQS:
        raise ScheduleError("when_malformed", f"--rrule: FREQ={freq} is not a frequency")
    for key in _UNSUPPORTED_PARTS:
        if key in parts:
            raise ScheduleError("rule_unsupported", f"{key}: the stored rule leaves this part out")
    unknown = sorted(set(parts) - {"INTERVAL", "BYDAY", "BYMONTHDAY", "BYHOUR", "BYMINUTE", "COUNT", "UNTIL"})
    if unknown:
        raise ScheduleError("when_malformed", f"--rrule: {unknown[0]} is not an RFC 5545 part")
    interval = 1
    if "INTERVAL" in parts:
        if not parts["INTERVAL"].isdigit() or int(parts["INTERVAL"]) < 1:
            raise ScheduleError("when_malformed", f"INTERVAL={parts['INTERVAL']}: a whole number of 1 or more is needed")
        interval = int(parts["INTERVAL"])
    byday: list[tuple[int, int]] = []
    for tok in parts.get("BYDAY", "").split(",") if "BYDAY" in parts else []:
        m = _DAY.match(tok)
        if not m:
            raise ScheduleError("when_malformed", f"BYDAY={tok!r}: MO to SU, with an ordinal on MONTHLY, is needed")
        n = int(m.group(1)) if m.group(1) else 0
        if m.group(1) is not None and (n == 0 or abs(n) > 5):
            raise ScheduleError("when_malformed", f"BYDAY={tok!r}: an ordinal is 1 to 5 or -1 to -5")
        if n and freq != "MONTHLY":
            raise ScheduleError("rule_unsupported", f"BYDAY={tok}: an ordinal on BYDAY needs FREQ=MONTHLY")
        byday.append((n, DAYS.index(m.group(2))))
    if byday and len({n == 0 for n, _ in byday}) > 1:
        raise ScheduleError("rule_unsupported", "BYDAY: weekdays with and without an ordinal in one rule")
    bymonthday: tuple[int, ...] = ()
    if "BYMONTHDAY" in parts:
        try:
            raw = [int(x) for x in parts["BYMONTHDAY"].split(",")]
        except ValueError:
            raise ScheduleError("when_malformed", f"BYMONTHDAY={parts['BYMONTHDAY']!r}: whole numbers are needed") from None
        if any(v != -1 and not 1 <= v <= 31 for v in raw):
            raise ScheduleError("rule_unsupported", "BYMONTHDAY: the stored rule has 1 to 31 and -1")
        bymonthday = tuple(sorted(set(raw)))
    byhour = _ints("BYHOUR", parts["BYHOUR"], 0, 23) if "BYHOUR" in parts else ()
    byminute = _ints("BYMINUTE", parts["BYMINUTE"], 0, 59) if "BYMINUTE" in parts else ()
    count = None
    if "COUNT" in parts:
        if not parts["COUNT"].isdigit() or int(parts["COUNT"]) < 1:
            raise ScheduleError("when_malformed", f"COUNT={parts['COUNT']}: a whole number of 1 or more is needed")
        count = int(parts["COUNT"])
    until = None
    if "UNTIL" in parts:
        try:
            until = datetime.strptime(parts["UNTIL"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            raise ScheduleError("when_malformed", f"UNTIL={parts['UNTIL']}: a UTC time like 20271231T235900Z is needed") from None
    if count is not None and until is not None:
        raise ScheduleError("when_malformed", "COUNT and UNTIL in one rule (RFC 5545 allows one)")
    rule = Rule(freq=freq, interval=interval, byday=tuple(sorted(set(byday))), bymonthday=bymonthday, byhour=byhour,
                byminute=byminute, count=count, until=until)
    if freq == "MINUTELY":
        if interval < MIN_INTERVAL_MIN:
            raise ScheduleError("interval_too_short", f"FREQ=MINUTELY;INTERVAL={interval}: the shortest gap is {interval} "
                                                      f"minutes; the least is {MIN_INTERVAL_MIN}")
        if byday or bymonthday or byhour or byminute:
            raise ScheduleError("rule_unsupported", "FREQ=MINUTELY takes INTERVAL only, no BY part")
    return rule


# --- When and slots ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class When:
    """The canonical form: `once` as `{at, zone}`, `recur` as a stored rule, `starts` and `zone` (SCH-B18)."""

    kind: str  # "once" | "recur"
    zone: str
    at: str | None = None  # local ISO date-time to the minute
    rule: str | None = None  # the stored RECUR text
    starts: str | None = None  # local ISO date-time to the minute

    def to_doc(self) -> dict[str, Any]:
        if self.kind == "once":
            return {"kind": "once", "at": self.at, "zone": self.zone}
        return {"kind": "recur", "rule": self.rule, "starts": self.starts, "zone": self.zone}

    @staticmethod
    def from_doc(doc: dict[str, Any]) -> When:
        return When(kind=str(doc["kind"]), zone=str(doc["zone"]), at=doc.get("at"), rule=doc.get("rule"),
                    starts=doc.get("starts"))


@dataclass(frozen=True)
class Slot:
    utc: datetime
    local: datetime  # the instant on the zone's clock (aware)
    wall: datetime  # the local time the rule asked for (naive); differs from `local` inside a gap
    note: str = ""  # "gap" | "overlap" | ""

    @property
    def local_text(self) -> str:
        return self.local.strftime("%Y-%m-%d %H:%M")


def _slot(wall: datetime, utc: datetime, zone: ZoneInfo) -> Slot:
    return Slot(utc=utc, local=utc.astimezone(zone), wall=wall, note=wall_note(wall, zone))


class _Calendar:
    """The local-clock days and times of one calendar rule, as dateutil's rrule counts them (RFC 5545)."""

    def __init__(self, rule: Rule, dt0: datetime) -> None:
        self.rule, self.dt0, self.d0 = rule, dt0, dt0.date()
        byday, bymd = rule.byday, rule.bymonthday
        if not byday and not bymd:  # RFC 5545: the start names the day when no part does
            if rule.freq == "MONTHLY":
                bymd = (dt0.day,)
            elif rule.freq == "WEEKLY":
                byday = ((0, dt0.weekday()),)
        self.plain = {w for n, w in byday if n == 0}
        self.nth = [(n, w) for n, w in byday if n != 0]
        self.pos = {x for x in bymd if x > 0}
        self.neg = {x for x in bymd if x < 0}
        self.minutes = sorted(rule.byminute or (dt0.minute,))
        self.byhour = set(rule.byhour)
        if rule.freq != "HOURLY":
            self.times = [time(h, m) for h in sorted(rule.byhour or (dt0.hour,)) for m in self.minutes]
        self.idx0 = self.d0.toordinal() * 24 + dt0.hour

    def day_ok(self, d: date) -> bool:
        r = self.rule
        if r.freq == "DAILY":
            if (d - self.d0).days % r.interval:
                return False
        elif r.freq == "WEEKLY":
            weeks = ((d - timedelta(days=d.weekday())) - (self.d0 - timedelta(days=self.d0.weekday()))).days // 7
            if weeks % r.interval:
                return False
        elif r.freq == "MONTHLY" and ((d.year * 12 + d.month) - (self.d0.year * 12 + self.d0.month)) % r.interval:
            return False
        if self.plain and d.weekday() not in self.plain:
            return False
        if self.pos or self.neg:
            last = calendar.monthrange(d.year, d.month)[1]
            if d.day not in self.pos and (d.day - last - 1) not in self.neg:
                return False
        if self.nth:
            last = calendar.monthrange(d.year, d.month)[1]
            if not any(d.weekday() == w and ((d.day - 1) // 7 + 1 == n if n > 0 else (last - d.day) // 7 + 1 == -n)
                       for n, w in self.nth):
                return False
        return True

    def walls(self, d: date) -> list[datetime]:
        if not self.day_ok(d):
            return []
        if self.rule.freq == "HOURLY":
            k = self.rule.interval
            first = (self.idx0 - d.toordinal() * 24) % k
            hours = [h for h in range(first, 24, k) if not self.byhour or h in self.byhour]
            out = [datetime.combine(d, time(h, m)) for h in hours for m in self.minutes]
        else:
            out = [datetime.combine(d, t) for t in self.times]
        return [w for w in out if w >= self.dt0]


def _stream(when: When, start: datetime, stop: datetime) -> Iterator[Slot]:
    """Slots in UTC order that can fall at or before `stop`; the caller drops those before `start`."""
    zone = zone_of(when.zone)
    if when.kind == "once":
        wall = datetime.fromisoformat(str(when.at))
        yield _slot(wall, wall_to_utc(wall, zone), zone)
        return
    rule = parse_rule(str(when.rule))
    dt0 = datetime.fromisoformat(str(when.starts))
    if rule.is_interval:
        s0, period = wall_to_utc(dt0, zone), rule.period
        n = 0 if start <= s0 else -((s0 - start) // period)
        while True:
            u = s0 + n * period
            if (rule.count is not None and n >= rule.count) or (rule.until and u > rule.until) or u > stop:
                return
            local = u.astimezone(zone)
            yield Slot(utc=u, local=local, wall=local.replace(tzinfo=None), note="")
            n += 1
    cal = _Calendar(rule, dt0)
    day = cal.d0 if rule.count is not None else max(cal.d0, start.astimezone(zone).date() - timedelta(days=2))
    end_day = stop.astimezone(zone).date() + timedelta(days=2)
    heap: list[tuple[datetime, datetime]] = []
    last: datetime | None = None
    emitted, done = 0, False
    while not done and day <= end_day:
        for wall in cal.walls(day):
            if rule.count is not None and emitted >= rule.count:
                done = True
                break
            u = wall_to_utc(wall, zone)
            if rule.until is not None and u > rule.until:
                done = True
                break
            emitted += 1
            heapq.heappush(heap, (u, wall))
        day += timedelta(days=1)
        # nothing later can come before the next midnight less the largest shift of a gap
        frontier = wall_to_utc(datetime.combine(day, time(0)), zone) - timedelta(hours=3)
        while heap and (done or day > end_day or heap[0][0] <= frontier):
            u, wall = heapq.heappop(heap)
            if u == last:  # two local times that land on one instant after a gap shift are one slot
                continue
            last = u
            if u > stop:
                return
            yield _slot(wall, u, zone)
    while heap:
        u, wall = heapq.heappop(heap)
        if u != last and u <= stop:
            last = u
            yield _slot(wall, u, zone)


def slots_between(when: When, start: datetime, end: datetime) -> list[Slot]:
    """Every slot with `start <= utc <= end`, in order, one per instant."""
    return [s for s in _stream(when, start, end) if s.utc >= start]


def next_slots(when: When, after: datetime, n: int, horizon_days: int = 800) -> list[Slot]:
    """The first `n` slots at or after `after` within the horizon (a rule that never matches gives fewer)."""
    out: list[Slot] = []
    for s in _stream(when, after, after + timedelta(days=horizon_days)):
        if s.utc >= after:
            out.append(s)
            if len(out) >= n:
                break
    return out


def shortest_gap_minutes(when: When, start: datetime, days: int = HORIZON_DAYS, cap: int = 3000) -> int | None:
    """The shortest gap between consecutive slots on the local clock, from the first slots of the horizon."""
    if when.kind == "once":
        return None
    last: datetime | None = None
    best: int | None = None
    for i, s in enumerate(_stream(when, start, start + timedelta(days=days))):
        if s.utc < start:
            continue
        wall = s.local.replace(tzinfo=None)
        if last is not None:
            gap = int((wall - last).total_seconds() // 60)
            best = gap if best is None else min(best, gap)
        last = wall
        if i > cap:
            break
    return best
