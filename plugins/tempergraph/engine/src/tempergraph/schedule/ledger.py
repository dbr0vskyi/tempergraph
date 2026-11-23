"""The machine-wide scheduled-run ledger `schedules/runs.jsonl` of the home store (TCK-B13, TCK-B23; LOS-B10).

One `fire` row for each fire the tick or `schedule fire` handles (started, skipped, missed or refused), and one `ended`
row for a started fire, which `read` lays over its fire row. Metadata only (never request, input or feedback text),
scrubbed, kept when the schedule, the state root or the repository is gone, and shortened only by `prune`
(`store prune --schedules --older-than <days>`). Reading creates nothing.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import IO, Any

from tempergraph.docs import append_jsonl, iter_jsonl
from tempergraph.schedule.store import TEXT_KEYS, schedules_root
from tempergraph.security.scrub import scrub

OUTCOMES = ("started", "skipped", "missed", "refused")


def ledger_path(home: Path | None = None) -> Path:
    return schedules_root(home) / "runs.jsonl"


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fire_row(entry: dict[str, Any], *, fire_id: str, slot: str | None, outcome: str, at: datetime, reason: str | None = None,
             thread_id: str | None = None, state_root: Path | None = None, trigger: str = "tick",
             orchestration_id: str | None = None) -> dict[str, Any]:
    """The row of one handled fire, from the schedule's entry (SCH-B14) and what the tick decided."""
    target = entry.get("target") or {}
    repo = str(target.get("repo") or "")
    return {"kind": "fire", "fire_id": fire_id, "schedule_id": entry["schedule_id"], "name": entry.get("name"), "slot": slot,
            "fired_at": _iso(at),
            "target": {"kind": target.get("kind"), "workflow": target.get("workflow") or target.get("orchestration_file"),
                       "repo": repo, "repo_name": Path(repo).name if repo else None},
            "created_from": (entry.get("created") or {}).get("from"), "outcome": outcome, "reason": reason,
            "thread_id": thread_id, "orchestration_id": orchestration_id,
            "state_root": str(state_root) if state_root is not None else None, "trigger": trigger}


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _write(row: dict[str, Any], home: Path | None, err: IO[str] | None) -> bool:
    bad = TEXT_KEYS & set(row)
    if bad:
        raise ValueError(f"the ledger holds metadata only, never {sorted(bad)[0]} text (TCK-B23)")
    try:
        append_jsonl(ledger_path(home), _clean(row))
        return True
    except OSError as exc:
        (err or sys.stderr).write(f"tempergraph: the schedule ledger could not be written ({type(exc).__name__}); going on\n")
        return False


def append(row: dict[str, Any], home: Path | None = None, err: IO[str] | None = None) -> bool:
    """One fire row. A failed write is reported on standard error and returns False; the fire goes on."""
    return _write(dict(row, kind="fire"), home, err)


def settle(fire_id: str, ended: dict[str, Any], *, at: datetime, home: Path | None = None, err: IO[str] | None = None) -> bool:
    """The `ended` row of a started fire: exit, run outcome and cost (`reported`, `estimated`, `incomplete`)."""
    return _write({"kind": "ended", "fire_id": fire_id, "at": _iso(at), **{k: v for k, v in ended.items() if k != "at"}},
                  home, err)


def _rows(home: Path | None) -> list[dict[str, Any]]:
    return list(iter_jsonl(ledger_path(home)))


def read(home: Path | None = None, *, schedule: str | None = None, repo: str | None = None, workflow: str | None = None,
         since: date | None = None, outcome: str | None = None) -> list[dict[str, Any]]:
    """Every fire in file order with its `ended` block laid over it (or None); read-only."""
    ended: dict[str, dict[str, Any]] = {}
    fires: list[dict[str, Any]] = []
    for r in _rows(home):
        if r.get("kind") == "ended" and r.get("fire_id"):
            ended[str(r["fire_id"])] = {k: v for k, v in r.items() if k not in ("kind", "fire_id")}
        elif r.get("kind") == "fire":
            fires.append(r)
    out: list[dict[str, Any]] = []
    cut = datetime.combine(since, time(0), tzinfo=UTC) if since else None
    for r in fires:
        t = r.get("target") or {}
        if schedule and r.get("schedule_id") != schedule:
            continue
        if repo and t.get("repo") != repo:
            continue
        if workflow and t.get("workflow") != workflow:
            continue
        if outcome and r.get("outcome") != outcome:
            continue
        if cut and datetime.fromisoformat(str(r["fired_at"]).replace("Z", "+00:00")) < cut:
            continue
        out.append({**r, "ended": ended.get(str(r.get("fire_id")))})
    return out


def prune(older_than_days: float, now: datetime, home: Path | None = None, *, dry_run: bool = False) -> int:
    """Drop the fire rows fired before `now - older_than_days`, with their `ended` rows; atomic. Returns how many fires."""
    cut = now - timedelta(days=older_than_days)
    rows = _rows(home)
    old = {str(r["fire_id"]) for r in rows if r.get("kind") == "fire" and r.get("fired_at")
           and datetime.fromisoformat(str(r["fired_at"]).replace("Z", "+00:00")) < cut}
    if dry_run or not old:
        return len(old)
    keep = [r for r in rows if str(r.get("fire_id")) not in old]
    path = ledger_path(home)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".runs.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return len(old)
