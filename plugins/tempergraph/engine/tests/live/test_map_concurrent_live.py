"""Live: a concurrent map runs its items' sessions at once on the real `claude` executor (MAP-B7, MAP-B9; MAP-AC5 live).

Skipped unless TEMPERGRAPH_LIVE=1. Engine fixture workflow (plan, a read-only concurrent map, join), not a shipped
workflow; the run is capped at 2 USD. A pause by a judge asking a person is a pass, as in M1: the point is that the
items' sessions overlapped and each kept its own slot.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.registry import default_registry
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from ..test_map_concurrent import concurrent

pytestmark = pytest.mark.live


def _ts(rec: dict[str, object]) -> datetime:
    return datetime.fromisoformat(str(rec["ts"]).replace("Z", "+00:00"))


def test_map_live_items_run_at_once(repo: Path) -> None:  # MAP-AC5 live (MAP-B7, MAP-B9)
    spec = dataclasses.replace(concurrent(concurrency=2), run_cost_cap_usd=2.0)
    request = ('Write the file phases.json holding exactly this JSON list and nothing else: '
               '[{"id": "p1", "text": "Name one prime number"}, {"id": "p2", "text": "Name one even number"}]')
    out = start(spec, "LIVE-MAP", {"request": request}, repo, default_registry(), RunSettings())
    print("exit:", out.exit_code, out.reason)
    rd = run_dir(state_root_path(repo), spec.name, "LIVE-MAP")
    recs = [json.loads(ln) for ln in (rd / "run.jsonl").read_text().splitlines()]
    runs = [r for r in recs if r.get("kind") == "agent_run"]
    print("sessions:", [(r["session_key"], r.get("ok")) for r in runs])
    steps = {k: [r for r in recs if r.get("session_key") == k] for k in ("phase.p1.1.step", "phase.p2.1.step")}
    assert all(steps.values()), steps.keys()
    spans = {k: (_ts(v[0]), _ts(v[-1])) for k, v in steps.items()}
    (a0, a1), (b0, b1) = spans.values()
    print("spans:", spans)
    assert a0 < b1 and b0 < a1  # the two items' step sessions overlapped (MAP-B9)
    assert all(r.get("ok") for r in runs)
    assert out.exit_code in (ExitCode.FINISHED, ExitCode.PAUSED)
