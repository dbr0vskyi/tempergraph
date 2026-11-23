"""Live: a council of three members and a chair runs on the real `claude` executor (CNL-B1, CNL-B12, CNL-B14; CNL-AC4
live).

Skipped unless TEMPERGRAPH_LIVE=1. Engine fixture workflow (one `synthesize` council), not a shipped workflow; the run
is capped at 2 USD. A pause by a judge asking a person, or the council's own no-decision pause, is a pass, as in M1:
the point is that every member answered, the chair ran and the run stayed under the cap.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.registry import default_registry
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from ..test_council_run import council_wf

pytestmark = pytest.mark.live


def test_cnl_live_a_council_runs_its_members_and_chair(repo: Path) -> None:  # CNL-AC4 live (CNL-B1, CNL-B12, CNL-B14)
    spec = dataclasses.replace(council_wf(), run_cost_cap_usd=2.0)
    out = start(spec, "LIVE-CNL", {"request": "a small team's issue tracker (SQLite or Postgres)"}, repo,
                default_registry(), RunSettings())
    print("exit:", out.exit_code, out.reason)
    rd = run_dir(state_root_path(repo), spec.name, "LIVE-CNL")
    recs = [json.loads(ln) for ln in (rd / "run.jsonl").read_text().splitlines()]
    runs = [r for r in recs if r.get("kind") == "agent_run"]
    print("sessions:", [(r["session_key"], r.get("ok")) for r in runs])
    cost = (next(r for r in recs if r.get("kind") == "run_exit").get("cost") or {}).get("reported")
    print("cost:", cost)
    print("gates:", [(r.get("unit"), r.get("verdict"), r.get("token")) for r in recs if r.get("kind") == "gate"])
    print("budget:", [(r.get("counter"), r.get("cause")) for r in recs if r.get("kind") == "budget"])
    keys = [r["session_key"] for r in runs]
    assert {m for m in ("a", "b", "c") if any(f".member.{m}." in k for k in keys)} == {"a", "b", "c"}
    assert any("chair" in k for k in keys)
    assert all(r.get("ok") for r in runs)
    assert cost is not None and cost <= 2.0
    assert out.exit_code in (ExitCode.FINISHED, ExitCode.PAUSED)
