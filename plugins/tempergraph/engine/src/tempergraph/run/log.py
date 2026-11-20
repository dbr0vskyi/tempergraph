"""The run log, cost rules and the live progress file (OBS §2.1–§2.3, EVT §2.2; contract C2).

Every write is best effort: a failing write is counted and never changes the run.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.constants import SCHEMA
from tempergraph.contracts import Event, EventSink, Usage
from tempergraph.docs import append_jsonl, write_json
from tempergraph.security.scrub import clip, scrub
from tempergraph.store.layout import now_iso

# Engine default prices, USD per million tokens, by model family, for the current generation that the tier
# aliases resolve to (first-party list prices as of 2026-11; OBS §2.2). The binding table overrides per model.
# A row without `cache_read` prices cache reads at CACHE_READ_FACTOR of input.
DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "haiku": {"input": 0.10, "output": 0.50},
    "sonnet": {"input": 2.0, "output": 10.0, "cache_read": 0.10},
    "opus": {"input": 4.0, "output": 20.0, "cache_read": 0.20},
}
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25


def family(model: str | None) -> str | None:
    m = (model or "").lower()
    return next((f for f in DEFAULT_PRICES if f in m), None)


def estimate(usage: Usage, model: str | None, prices: Mapping[str, Mapping[str, float]] | None = None
             ) -> float | None:
    """The engine's own estimate for a session with tokens; None when unmeasured (OBS §2.2)."""
    if not usage.has_tokens():
        return None
    row = (prices or {}).get(model or "") or DEFAULT_PRICES.get(family(model) or "")
    if row is None:
        return None
    pin, pout = row["input"], row["output"]
    total = (usage.input_tokens or 0) * pin + (usage.output_tokens or 0) * pout
    total += (usage.cache_read_tokens or 0) * row.get("cache_read", pin * CACHE_READ_FACTOR)
    total += (usage.cache_write_tokens or 0) * pin * CACHE_WRITE_FACTOR
    return round(total / 1_000_000, 6)


@dataclass(kw_only=True)
class CostTotals:
    """Run cost so far: reported and estimated kept apart (OBS §2.2)."""

    reported: float = 0.0
    estimated: float = 0.0
    estimated_only: float = 0.0  # estimates of sessions that reported nothing
    sessions: int = 0
    reported_sessions: int = 0
    estimated_sessions: int = 0
    unmeasured: int = 0

    def add(self, usage: Usage) -> None:
        self.sessions += 1
        if usage.reported_cost_usd is not None:
            self.reported += usage.reported_cost_usd
            self.reported_sessions += 1
        if usage.estimated_cost_usd is not None:
            self.estimated += usage.estimated_cost_usd
            self.estimated_sessions += 1
            if usage.reported_cost_usd is None:
                self.estimated_only += usage.estimated_cost_usd
        if usage.reported_cost_usd is None and usage.estimated_cost_usd is None:
            self.unmeasured += 1

    @property
    def completeness(self) -> str:
        if self.unmeasured:
            return "incomplete"
        return "complete" if self.reported_sessions == self.sessions else "estimated"

    def figure(self) -> float:
        """The run line's figure: reported where present, else estimated, per session (BUD §2)."""
        return round(self.reported + self.estimated_only, 6)

    def to_json(self) -> dict[str, Any]:
        return {"reported": round(self.reported, 6) if self.reported_sessions else None,
                "estimated": round(self.estimated, 6) if self.estimated_sessions else None,
                "incomplete": self.completeness == "incomplete", "completeness": self.completeness,
                "counters": {k: getattr(self, k) for k in ("reported", "estimated", "estimated_only", "sessions",
                                                          "reported_sessions", "estimated_sessions", "unmeasured")}}

    @classmethod
    def from_json(cls, d: Mapping[str, Any] | None) -> CostTotals:
        t = cls()
        for k, v in ((d or {}).get("counters") or {}).items():
            if k in cls.__dataclass_fields__ and isinstance(v, int | float):
                setattr(t, k, v)
        return t


class RunLog:
    """`runs/<workflow>/<task_id>/run.jsonl`; the first line carries the schema."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.failures = 0
        self.seq = 0

    def write(self, record: str, /, **fields: Any) -> int:
        self.seq += 1
        rec = {**fields, "kind": record, "ts": now_iso(), "seq": self.seq}
        if "kind" in fields:
            rec["session_kind"] = fields["kind"]
        try:
            if not self.path.exists():
                append_jsonl(self.path, {"kind": "schema", "schema": SCHEMA["run_log"]})
            append_jsonl(self.path, _jsonable(rec))
        except Exception:  # noqa: BLE001 - observability never changes the run (C2)
            self.failures += 1
        return self.seq


def _jsonable(v: Any) -> Any:
    if isinstance(v, Usage):
        return v.to_json()
    if isinstance(v, Mapping):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_jsonable(x) for x in v]
    if isinstance(v, str | int | float | bool) or v is None:
        return v
    return str(v)


class LiveSink(EventSink):
    """The live progress file (OBS §2.3) and the activity journal (EVT §2.3), written at most once a second."""

    def __init__(self, session_dir: Path | None, clock: Any = time.monotonic) -> None:
        super().__init__()
        self.dir = session_dir
        self.clock = clock
        self.last_write = 0.0
        self.recent: list[dict[str, Any]] = []
        self.open_tool: dict[str, Any] | None = None
        self.last_text = ""
        self.n = 0
        self.failures = 0

    def push(self, event: Event) -> None:
        super().push(event)
        if self.dir is None:
            return
        self.n += 1
        d = dict(event.data)
        if event.kind == "tool_started":
            self.open_tool = {"name": d.get("name"), "input_summary": d.get("input_summary", "")}
            self.recent = (self.recent + [self.open_tool])[-10:]
        elif event.kind == "tool_finished":
            self.open_tool = None
        elif event.kind == "text":
            self.last_text = clip(scrub(str(d.get("last_line", ""))), 200)
        try:
            row = {"t": round(event.ts, 3), "n": self.n, "ev": event.kind,
                   **{k: v for k, v in d.items() if k != "usage"}}
            append_jsonl(self.dir / "activity.jsonl", _jsonable(row))
            now = self.clock()
            if now - self.last_write >= 1.0 or event.kind == "result":
                self.last_write = now
                write_json(self.dir / "live.json", {"open_tool": self.open_tool, "recent": self.recent,
                                                    "last_text": self.last_text, "updated_at": now_iso(),
                                                    "pid": os.getpid()})
        except Exception:  # noqa: BLE001
            self.failures += 1


@dataclass(kw_only=True)
class Ledger:
    """`<state root>/ledger.jsonl`: one metadata-only row per run segment and per intervention."""

    path: Path
    failures: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)

    def append(self, row: dict[str, Any]) -> None:
        try:
            append_jsonl(self.path, _jsonable({"ts": now_iso(), **row}))
        except Exception:  # noqa: BLE001
            self.failures += 1


def dumps(v: Any) -> str:
    return json.dumps(_jsonable(v), ensure_ascii=False)
