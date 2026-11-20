"""Sinks for run rows (CST §2.3) and the readers over this machine's rows and the fleet copy (CST §2.5).

With no sink configured nothing leaves the machine (CST-B1); the directory sink, outbox, flush, sync and the
live view come with T10.1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tempergraph.observe.rows import read_rows


def enqueue(home: Path, row: dict[str, Any], log: Path) -> int:
    """Appends the row to each configured sink's outbox; returns how many sinks took it."""
    return 0


def flush(home: Path) -> dict[str, Any]:
    return {"schema_version": 1, "sinks": []}


def sync(home: Path) -> dict[str, Any]:
    return {"schema_version": 1, "sinks": []}


def live(home: Path, source: str | None) -> dict[str, Any]:
    return {"schema_version": 1, "machines": [], "runs": []}


def _month_ok(row: dict[str, Any], month: str | None, since: str | None) -> bool:
    ended = str(row.get("ended_at") or "")
    if month:
        return ended[:7] == month
    if since:
        return ended[:10] >= since
    return True


def rows_for(home: Path, source: str | None, local: bool, month: str | None,
             since: str | None) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None]:
    """This machine's stats rows (and, from T10.1, the fleet copy or a sink), filtered by month or start date."""
    paths = sorted((home / "stats").glob("*.jsonl")) if (home / "stats").is_dir() else []
    if month:
        paths = [p for p in paths if p.stem == month]
    found, unknown = read_rows(paths)
    return [r for r in found if _month_ok(r, month, since)], unknown, None
