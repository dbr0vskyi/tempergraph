"""The echo: a sentence rendered from the canonical form only (SCH-B18, SCH-B20, SCH-B2; ADR `exact-formats-first-and-an-optional-word-grammar-echoed-back`).

Never rendered from the phrase the person typed: the same stored rule gives the same sentence, and the `rule:`,
`starts:`, `zone:` and `at:` lines of the text re-parse (through the exact formats) to the stored form.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from tempergraph.schedule.model import (
    Rule,
    Slot,
    When,
    floor_minute,
    next_slots,
    parse_rule,
    utc_offset,
    zone_of,
)

NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", -1: "last"}


def _join(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _nums(values: Sequence[int]) -> str:
    return ", ".join(str(v) for v in sorted(values))


def _ordinal(n: int) -> str:
    return ORDINALS.get(n, f"{-n}th from last" if n < 0 else f"{n}th")


def _weekdays(days: Sequence[int]) -> str:
    days = sorted(set(days))
    if days == [0, 1, 2, 3, 4]:
        return "Monday to Friday"
    if len(days) == 7:
        return "every day"
    return _join([NAMES[d] for d in days])


def _monthdays(rule: Rule, default: int | None = None) -> str:
    vals = sorted(rule.bymonthday) if rule.bymonthday else [default or 1]
    return "on " + _join([f"day {v}" if v > 0 else "the last day" for v in vals]) + " of the month"


def _times(rule: Rule, dt0: datetime) -> str:
    minutes = rule.byminute or (dt0.minute,)
    if rule.freq == "HOURLY":
        text = f"At minute {_nums(minutes)}"
        if rule.byhour:
            text += f" past hour {_nums(rule.byhour)}"
            return text + (f", every {rule.interval} hours" if rule.interval > 1 else "")
        return text + (" of every hour" if rule.interval == 1 else f" of every {rule.interval} hours")
    hours = rule.byhour or (dt0.hour,)
    times = [f"{h:02d}:{m:02d}" for h in sorted(hours) for m in sorted(minutes)]
    return "At " + _join(times) if len(times) <= 6 else f"At minute {_nums(minutes)} past hour {_nums(hours)}"


def _days(rule: Rule, dt0: datetime) -> str:
    plain = [w for n, w in rule.byday if n == 0]
    nth = [(n, w) for n, w in rule.byday if n != 0]
    k = rule.interval
    if rule.freq == "MONTHLY":
        if nth:
            day = "on the " + _join([f"{_ordinal(n)} {NAMES[w]}" for n, w in nth]) + " of the month"
        elif plain:
            day = "on every " + _join([NAMES[w] for w in sorted(set(plain))]) + " of the month"
            if rule.bymonthday:
                day += " " + _monthdays(rule)
        else:
            day = _monthdays(rule, dt0.day)
        return day + (f", every {k} months" if k > 1 else "")
    names = plain or ([] if rule.bymonthday else [dt0.weekday()])
    parts = ([_weekdays(names)] if names and (rule.freq == "WEEKLY" or plain) else []) + (
        [_monthdays(rule)] if rule.bymonthday else [])
    if rule.freq == "WEEKLY":
        return " ".join(parts) + (f", every {k} weeks" if k > 1 else "")
    day = " ".join(parts) or "every day"  # DAILY and HOURLY
    if rule.freq == "DAILY" and k > 1:
        return f"every {k} days" if not parts else f"{day}, every {k} days"
    return day


def sentence(when: When) -> str:
    """The echo's sentence, a fixed template over the canonical form (SCH-B18's "At 08:00, Monday to Friday.")."""
    zone = zone_of(when.zone)
    if when.kind == "once":
        at = datetime.fromisoformat(str(when.at))
        return f"Once, on {at:%Y-%m-%d} at {at:%H:%M}."
    rule = parse_rule(str(when.rule))
    dt0 = datetime.fromisoformat(str(when.starts))
    if rule.is_interval:
        if rule.freq == "HOURLY":
            base = "Every hour" if rule.interval == 1 else f"Every {rule.interval} hours"
        else:
            base = f"Every {rule.interval} minutes"
        base += f", from {dt0:%Y-%m-%d %H:%M}"
    else:
        base = f"{_times(rule, dt0)}, {_days(rule, dt0)}"
    if rule.until is not None:
        base += f", until {rule.until.astimezone(zone):%Y-%m-%d %H:%M}"
    if rule.count is not None:
        base += f", for {rule.count} times"
    return base + "."


def _note(s: Slot, zone_name: str) -> str:
    if s.note == "gap":
        return (f"{s.wall:%Y-%m-%d %H:%M} does not exist in {zone_name}; the offset from before the gap makes it "
                f"{s.local:%H:%M}")
    if s.note == "overlap":
        return f"{s.wall:%Y-%m-%d %H:%M} happens twice in {zone_name}; the first occurrence is used"
    return ""


@dataclass
class Echo:
    sentence: str
    doc: dict[str, Any]

    def to_doc(self) -> dict[str, Any]:
        return self.doc

    def text(self) -> str:
        d = self.doc
        lines = [d["sentence"]]
        if d["kind"] == "once":
            lines.append(f"at: {d['at']}")
        else:
            lines += [f"rule: {d['rule']}", f"starts: {d['starts']}"]
        lines.append(f"zone: {d['zone']} (UTC{d['utc_offset']})")
        if not d["slots"]:
            lines.append("next slots: none")
        else:
            lines.append("next slot:" if d["kind"] == "once" else f"next {len(d['slots'])} slots:")
        for s in d["slots"]:
            lines.append(f"  {s['local']} local = {s['utc'].replace('T', ' ').replace('Z', '')} UTC")
        lines += [f"  note: {n}" for n in d["notes"]]
        lines += [f"assumed: {a}" for a in d["assumptions"]]
        return "\n".join(lines) + "\n"


def build_echo(when: When, assumptions: Sequence[str], now: datetime, n: int = 3) -> Echo:
    """The echo of a canonical When: the sentence, the zone with its current UTC offset, the next `n` slots (one for
    a `once`) in local and UTC time, any gap or overlap on a listed slot, and each assumption."""
    zone = zone_of(when.zone)
    start = floor_minute(now)
    slots = next_slots(when, start, 1 if when.kind == "once" else n)
    doc: dict[str, Any] = {
        "sentence": sentence(when), "kind": when.kind, "zone": when.zone, "utc_offset": utc_offset(zone, start),
        "slots": [{"local": s.local.strftime("%Y-%m-%d %H:%M"), "utc": s.utc.strftime("%Y-%m-%dT%H:%MZ"), "note": s.note}
                  for s in slots],
        "notes": [t for t in (_note(s, when.zone) for s in slots) if t], "assumptions": list(assumptions),
        "canonical": when.to_doc(),
    }
    if when.kind == "once":
        doc["at"] = when.at
    else:
        doc.update(rule=when.rule, starts=when.starts)
    return Echo(sentence=str(doc["sentence"]), doc=doc)
