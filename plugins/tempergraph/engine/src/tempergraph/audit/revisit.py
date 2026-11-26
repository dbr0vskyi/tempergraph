"""Decision records whose `Revisit when` trigger has fired (DRV-B1 to DRV-B4): the audit reads the decision records of
a workflow package's `docs/adr/`, parses the lines that name something the engine records, compares each trigger's
state with the one the last stamp recorded and reports `decision-revisit-due` (info, advisory). Model-free; an
issue's state is read through an injected reader, and an unreadable state never fires."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec

LIVE_CHECK = re.compile(r"\blive check `?((?:[A-Z][A-Z0-9]{0,7}-)?L-?\d+)`?", re.I)
ISSUE = re.compile(r"(?<![\w/#])#(\d+)\b")
MEASURE = re.compile(r"`([A-Za-z0-9_./-]+\.md)`\s+(chars|prohibitions|reasons|prohibitions_per_reason|"
                     r"goal_branch_share)\s+(above|below|at or above|at or below)\s+([0-9][0-9_,]*(?:\.[0-9]+)?)", re.I)
VERSION = re.compile(r"\b(engine|claude|claude code)\s+version\s+(moves|changes|reaches\s+([0-9]+\.[0-9]+\.[0-9]+))",
                     re.I)
SECTION = re.compile(r"^##\s+Revisit when\s*$", re.M)

Kind = str  # live_check, issue, measure, version


@dataclass(frozen=True)
class Trigger:
    record: str  # package-relative path of the decision record
    kind: Kind
    key: str  # what the stamp keys the state by, such as `issue:12` or `measure:prompts/a.md:chars>12000`
    text: str  # the line, as written


@dataclass(frozen=True)
class Prose:
    record: str
    text: str


def revisit_lines(text: str) -> list[str]:
    """The non-empty lines of a record's `Revisit when` section, list markers removed."""
    m = SECTION.search(text)
    if m is None:
        return []
    body = text[m.end():]
    nxt = re.search(r"^##\s", body, re.M)
    body = body[:nxt.start()] if nxt else body
    return [ln.strip().lstrip("-* ").strip() for ln in body.splitlines() if ln.strip()]


def parse(record: str, text: str) -> tuple[list[Trigger], list[Prose]]:
    """DRV-B1: each line's machine-readable triggers; a line with none is prose."""
    triggers: list[Trigger] = []
    prose: list[Prose] = []
    for line in revisit_lines(text):
        found: list[Trigger] = []
        for m in LIVE_CHECK.finditer(line):
            found.append(Trigger(record, "live_check", f"live_check:{m.group(1).upper()}", line))
        for m in MEASURE.finditer(line):
            op = {"above": ">", "below": "<", "at or above": ">=", "at or below": "<="}[m.group(3).lower()]
            value = m.group(4).replace(",", "").replace("_", "")
            found.append(Trigger(record, "measure", f"measure:{m.group(1)}:{m.group(2).lower()}{op}{value}", line))
        for m in VERSION.finditer(line):
            who = "engine" if m.group(1).lower() == "engine" else "claude"
            found.append(Trigger(record, "version", f"version:{who}" + (f">={m.group(3)}" if m.group(3) else ""),
                                 line))
        for m in ISSUE.finditer(line):
            found.append(Trigger(record, "issue", f"issue:{m.group(1)}", line))
        if found:
            triggers += found
        else:
            prose.append(Prose(record, line))
    return triggers, prose


def records(root: Path | None) -> list[tuple[str, str]]:
    if root is None:
        return []
    out = []
    for p in sorted((root / "docs" / "adr").glob("*.md")):
        if p.name.lower() in ("readme.md", "index.md"):
            continue
        try:
            out.append((p.relative_to(root).as_posix(), p.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return out


def read_all(root: Path | None) -> tuple[list[Trigger], list[Prose]]:
    triggers: list[Trigger] = []
    prose: list[Prose] = []
    for rel, text in records(root):
        t, p = parse(rel, text)
        triggers += t
        prose += p
    return triggers, prose


@dataclass
class Readers:
    """Where a trigger's state comes from; a reader that returns None leaves the state unknown."""
    issue: Callable[[int], str | None] = lambda n: None  # `open` or `closed`
    claude_version: Callable[[], str | None] = lambda: None
    engine_version: str = ""


def _live_row(root: Path, check: str) -> str | None:
    """The digest of the last row of a package plan whose first cell is the check id, `none` when no row has it."""
    last: str | None = None
    for p in sorted((root / "docs" / "plans").glob("*.md")):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for ln in lines:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if ln.lstrip().startswith("|") and cells and cells[0].upper() == check:
                last = ln.strip()
    return hashlib.sha256(last.encode()).hexdigest()[:16] if last else "none"


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def state(spec: WorkflowSpec, t: Trigger, readers: Readers) -> str | None:
    """DRV-B2: the trigger's state now, None when it cannot be read."""
    root = spec.package_root
    if root is None:
        return None
    kind, _, rest = t.key.partition(":")
    if kind == "live_check":
        return _live_row(root, rest)
    if kind == "issue":
        return readers.issue(int(rest))
    if kind == "measure":
        from tempergraph.audit.text_health import measure

        m = re.fullmatch(r"(.+):([a-z_]+)(>=|<=|>|<)([0-9.]+)", rest)
        if m is None:
            return None
        try:
            got = getattr(measure((root / m.group(1)).read_text(encoding="utf-8")), m.group(2))
        except (OSError, UnicodeDecodeError, AttributeError):
            return None
        v, limit = float(got), float(m.group(4))
        crossed = {">": v > limit, "<": v < limit, ">=": v >= limit, "<=": v <= limit}[m.group(3)]
        return "crossed" if crossed else "within"
    if kind == "version":
        who, _, at = rest.partition(">=")
        now = readers.engine_version if who == "engine" else readers.claude_version()
        if not now:
            return None
        if at:
            return "reached" if _version_tuple(now) >= _version_tuple(at) else "below"
        return now
    return None


def states(spec: WorkflowSpec, readers: Readers) -> dict[str, dict[str, str]]:
    """What the stamp records (DRV-B3): per record, each trigger's state that could be read."""
    out: dict[str, dict[str, str]] = {}
    for t in read_all(spec.package_root)[0]:
        s = state(spec, t, readers)
        if s is not None:
            out.setdefault(t.record, {})[t.key] = s
    return out


def fired(t: Trigger, was: str | None, now: str | None) -> bool:
    """DRV-B2: the trigger's state changed since the stamp in the direction its form names."""
    if now is None:
        return False
    kind = t.kind
    if kind == "issue":
        return now == "closed" and was != "closed"
    if kind == "measure":
        return now == "crossed" and was != "crossed"
    if kind == "version" and ">=" in t.key:
        return now == "reached" and was != "reached"
    return was is not None and was != now  # a live check's row, a version that moves


def rows(spec: WorkflowSpec, stamp: Mapping[str, Any] | None, readers: Readers) -> list[dict[str, Any]]:
    """`audit decisions`: one row per trigger and per prose line (DRV-B4)."""
    stamped = dict((stamp or {}).get("revisit") or {})
    triggers, prose = read_all(spec.package_root)
    out: list[dict[str, Any]] = []
    for t in triggers:
        was = (stamped.get(t.record) or {}).get(t.key)
        now = state(spec, t, readers)
        out.append({"record": t.record, "kind": t.kind, "trigger": t.key, "line": t.text, "stamped": was,
                    "now": now, "due": stamp is not None and fired(t, was, now)})
    out += [{"record": p.record, "kind": "not machine-readable", "line": p.text} for p in prose]
    return out


def findings(spec: WorkflowSpec, stamp: Mapping[str, Any] | None, readers: Readers) -> list[Any]:
    """DRV-B2: one `decision-revisit-due` finding per fired trigger; none without a stamp."""
    from tempergraph.audit.catalog import rule
    from tempergraph.audit.report import AuditFinding

    if stamp is None:
        return []
    r = rule("decision-revisit-due")
    out = []
    for row in rows(spec, stamp, readers):
        if not row.get("due"):
            continue
        out.append(AuditFinding(rule=r.id, layer=r.layer, severity=r.severity, confidence=r.confidence, cause=r.cause,
                                unit=None, item=row["trigger"], session=None,
                                statement=f"{row['record']}: its revisit trigger {row['trigger']!r} has fired "
                                          f"(stamped {row['stamped'] or 'unread'}, now {row['now']})",
                                evidence={"trigger": row["trigger"], "line": row["line"], "stamped": row["stamped"],
                                          "now": row["now"]},
                                remedy=r.remedy, location={"file": row["record"]}))
    return out
