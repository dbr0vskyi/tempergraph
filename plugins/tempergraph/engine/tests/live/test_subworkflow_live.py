"""Live: a parent runs a sub-workflow child on the real `claude` executor (SWF-B1, SWF-B8; SWF-AC1, SWF-AC2 live).

Skipped unless TEMPERGRAPH_LIVE=1. Engine fixture parent and child, neither a shipped workflow; the run is capped
at 2 USD. A pause by a judge asking a person is a pass, as in M1: the point is that the child ran inside the parent.
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

from ..fixtures.subworkflows import home_dir, register_workflow
from ..test_subworkflow_run import parent

pytestmark = pytest.mark.live


def test_swf_live_parent_runs_its_child(repo: Path, tmp_path: Path) -> None:  # SWF-AC1, SWF-AC2 live
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=("overview",))
    spec = dataclasses.replace(parent(), run_cost_cap_usd=2.0)
    out = start(spec, "LIVE-SWF", {"request": "a one-paragraph overview of a scratch repository"}, repo,
                default_registry(), RunSettings())
    print("exit:", out.exit_code, out.reason)
    rd = run_dir(state_root_path(repo), "deliver", "LIVE-SWF")
    recs = [json.loads(ln) for ln in (rd / "run.jsonl").read_text().splitlines()]
    runs = [r for r in recs if r.get("kind") == "agent_run"]
    print("sessions:", [(r["session_key"], r.get("ok"), r.get("child")) for r in runs])
    child_runs = [r for r in runs if r.get("child") == "setup"]
    assert child_runs and all(r["session_key"].startswith("setup/") for r in child_runs)
    assert all(r.get("ok") for r in runs)
    assert out.exit_code in (ExitCode.FINISHED, ExitCode.PAUSED)
    assert not (state_root_path(repo) / "runs" / "child").exists()  # one run folder, the parent's (SWF-AC2)
