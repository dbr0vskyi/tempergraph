"""Live: a contest runs three slots on the real `claude` executor and picks one within the cap (CTS-B1, CTS-B7; CTS-AC2
live; milestone N3 of the third-release plan).

Skipped unless TEMPERGRAPH_LIVE=1. Engine fixture workflow (a read-only contest of three slots, then a step), not a
shipped workflow; the run is capped at 2 USD. A pause by a judge asking a person is a pass, as in M1: the point is that
three slots ran and the pick was made by rule under the cap.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.registry import default_registry
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from ..test_contest_run import contest_spec

pytestmark = pytest.mark.live


def test_cts_live_a_contest_picks_one_of_three_within_the_cap(repo: Path) -> None:  # CTS-AC2 live (CTS-B1, CTS-B7)
    spec = contest_spec(slots=3, run_cost_cap_usd=2.0)
    out = start(spec, "LIVE-CTS", {"request": "a one-sentence note naming one prime number"}, repo,
                default_registry(), RunSettings())
    print("exit:", out.exit_code, out.reason)
    rd = run_dir(state_root_path(repo), spec.name, "LIVE-CTS")
    recs = [json.loads(ln) for ln in (rd / "run.jsonl").read_text().splitlines()]
    runs = [r for r in recs if r.get("kind") == "agent_run"]
    print("sessions:", [(r["session_key"], r.get("ok")) for r in runs])
    picks = [r for r in recs if r.get("kind") == "contest"]
    print("picks:", [(p.get("winner"), [(s.get("name"), s.get("check"), s.get("verdict"), s.get("cost"))
                                       for s in p.get("slots") or []]) for p in picks])
    cost = (next(r for r in recs if r.get("kind") == "run_exit").get("cost") or {}).get("reported")
    print("cost:", cost)
    assert picks and len(picks[0]["slots"]) == 3 and picks[0]["winner"] is not None
    assert {k for r in runs for k in [r["session_key"].split(".")[1]] if r["session_key"].startswith("pick.")} == {
        "s1", "s2", "s3"}
    assert all(r.get("ok") for r in runs)
    assert cost is not None and cost <= 2.0
    assert out.exit_code in (ExitCode.FINISHED, ExitCode.PAUSED)
