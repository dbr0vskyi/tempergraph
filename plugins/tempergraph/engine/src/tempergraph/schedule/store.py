"""The schedule entry and its fire log under `schedules/<schedule_id>/` of the home store (SCH-B13, SCH-B14, SCH-B28;
LOS-B10).

`entry.json` is owner-only (0600) and written atomically; `fires.jsonl` is append-only JSON lines of metadata, never
request, input or feedback text (SCH-AC8): the request lives only in the entry. A failed fire-log write is recorded on
standard error and the verb goes on (C2). Read-only callers use `read_entry`, `list_entries` and `read_log`, which
create nothing.
"""

from __future__ import annotations

import os
import re
import secrets
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from tempergraph.docs import append_jsonl, iter_jsonl, write_json
from tempergraph.schedule.model import When, floor_minute, next_slots
from tempergraph.security.scrub import scrub
from tempergraph.store.layout import ensure_home, home_path

SCHEMA_VERSION = 1
MAX_ID = 64
MAX_SCHEDULES = 64
LOG_KINDS = ("created", "edited", "paused", "resumed", "due", "started", "skipped", "queued", "missed", "refused",
             "ended", "removed")
CHECK_KEYS = frozenset({"executor", "role", "kinds", "result", "may_expire", "reason"})  # a row of `executors_checked`
TEXT_KEYS = frozenset({"request", "inputs", "input", "feedback", "args"})  # never in a fire-log line (SCH-B28)


def schedules_root(home: Path | None = None) -> Path:
    return (home or home_path()) / "schedules"


def entry_path(schedule_id: str, home: Path | None = None) -> Path:
    return schedules_root(home) / schedule_id / "entry.json"


def token_path(schedule_id: str, home: Path | None = None) -> Path:
    """The fire token's private file, beside the entry (TCK-B17)."""
    return schedules_root(home) / schedule_id / "token"


def log_path(schedule_id: str, home: Path | None = None) -> Path:
    return schedules_root(home) / schedule_id / "fires.jsonl"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "schedule"


def new_schedule_id(name: str, taken: set[str], hexgen: Callable[[], str] | None = None) -> str:
    """`<name>-<4 hex>`, at most 64 characters, unique on the machine: the four digits are drawn again until unused."""
    slug = slugify(name)[: MAX_ID - 5].strip("-") or "schedule"
    draw = hexgen or (lambda: secrets.token_hex(2))
    while True:
        sid = f"{slug}-{draw()}"
        if sid not in taken:
            return sid


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_entry(*, schedule_id: str, name: str, target: dict[str, Any], when: dict[str, Any], options: dict[str, Any],
                run_cost_cap_usd: float, budget: dict[str, Any] | None, catch_up: str, catch_up_window_s: int,
                overlap: str, max_live: int, pause_after_failures: int, created: dict[str, Any], now: datetime,
                token_digest: str | None = None, executors_checked: list[dict[str, Any]] | None = None
                ) -> dict[str, Any]:
    """Every field of SCH-B14; `token_digest` (TCK-B17) and `executors_checked` (TCK-B19) are what `add` gives it, and
    empty or null when it gives none. No credential value is ever kept here, only kinds."""
    request = str(target.get("request") or "")
    first = next_slots(When.from_doc(when), floor_minute(now), 1)
    return {
        "schema_version": SCHEMA_VERSION, "schedule_id": schedule_id, "name": name,
        "description": scrub(request)[:200], "state": "active", "target": target, "when": when, "options": options,
        "run_cost_cap_usd": run_cost_cap_usd, "budget": budget, "catch_up": catch_up,
        "catch_up_window_s": catch_up_window_s, "overlap": overlap, "max_live": max_live,
        "pause_after_failures": pause_after_failures, "executors_checked": list(executors_checked or []),
        "created": created, "edited": None, "token_digest": token_digest, "next_slot": _iso(first[0].utc) if first else None, "last_fire": None,
    }


def write_entry(entry: dict[str, Any], home: Path | None = None) -> Path:
    """Owner-only (0600), atomic (a temporary file, then a rename)."""
    ensure_home(home)
    path = entry_path(str(entry["schedule_id"]), home)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    entry = dict(entry, executors_checked=[{k: v for k, v in c.items() if k in CHECK_KEYS}  # kinds, never a credential value
                                           for c in entry.get("executors_checked") or []])
    write_json(path, entry)
    return path


def read_entry(schedule_id: str, home: Path | None = None) -> dict[str, Any]:
    import json

    doc = json.loads(entry_path(schedule_id, home).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"{schedule_id}: the entry is not a JSON object")
    return doc


def list_entries(home: Path | None = None) -> list[dict[str, Any]]:
    """Every readable entry, in id order; an unreadable folder is left out, not an error."""
    root = schedules_root(home)
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        try:
            out.append(read_entry(d.name, home))
        except (OSError, ValueError):
            continue
    return out


def read_log(schedule_id: str, home: Path | None = None) -> list[dict[str, Any]]:
    return list(iter_jsonl(log_path(schedule_id, home)))


def append_event(schedule_id: str, kind: str, *, now: datetime, slot: str | None = None, fire_id: str | None = None,
                 caller: dict[str, Any] | None = None, err: IO[str] | None = None, home: Path | None = None,
                 **meta: Any) -> dict[str, Any] | None:
    """One fire-log line: `seq`, `at`, `kind`, `slot`, `fire_id`, metadata, and the `caller` block of a person-made
    event. Text of the request is refused by name; a failed write is reported on standard error and returns None."""
    bad = TEXT_KEYS & set(meta)
    if bad:
        raise ValueError(f"the fire log holds metadata only, never {sorted(bad)[0]} text (SCH-B28)")
    if kind not in LOG_KINDS:
        raise ValueError(f"{kind!r} is not a fire-log kind")
    try:
        last = read_log(schedule_id, home)
        record: dict[str, Any] = {"seq": (int(last[-1].get("seq") or len(last)) if last else 0) + 1, "at": _iso(now),
                                  "kind": kind, "slot": slot, "fire_id": fire_id, **meta}
        if caller is not None:
            record["caller"] = caller
        append_jsonl(log_path(schedule_id, home), record)
        return record
    except OSError as exc:
        (err or sys.stderr).write(f"tempergraph: schedule {schedule_id}: the fire log could not be written "
                                  f"({type(exc).__name__}); going on\n")
        return None
