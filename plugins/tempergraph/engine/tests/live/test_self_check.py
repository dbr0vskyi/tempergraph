"""Live check L-29 (CHK-B7): a real step session runs its check preview. Skipped unless TEMPERGRAPH_LIVE=1.

The step must make `config.txt` hold the line `mode: strict`, and its prompt does not say so: only the
check's finding does. A session that runs `tempergraph self-check <ticket>` learns it from the preview. The
run is capped at 1 USD on the `small` tier unless TEMPERGRAPH_LIVE_TIER names another.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import CheckFinding, CheckResult, Gate, Judge, Routing, Step, Workflow
from tempergraph.executors.registry import default_registry
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from ..fixtures.workflows import crit, named

pytestmark = pytest.mark.live
MODEL = os.environ.get("TEMPERGRAPH_LIVE_TIER", "small")


def strict_check(ctx: Any) -> CheckResult:
    path = ctx.workdir / "config.txt"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    ok = "mode: strict" in text.splitlines()
    return CheckResult(result="PASS" if ok else "FAIL", evidence=f"preview={ctx.preview}", findings=[CheckFinding(
        status="pass" if ok else "fail", criterion="c-mode", place="config.txt",
        message="config.txt sets the mode" if ok else "config.txt must hold the exact line `mode: strict`",
        fix="" if ok else "add the line `mode: strict` to config.txt")])


def test_l_29_a_real_step_runs_its_check_preview(repo: Path) -> None:
    units = {"fix": Step(
        prompt="Set up config.txt in the repository root for {request}. Before you finish, run the check preview "
               "command you were given and fix whatever it reports; repeat until it passes.",
        tools=["read", "edit", "write"], self_check=True, model=MODEL,
        gate=Gate(check=strict_check, judge=Judge(stance="Verify.", brief="Read config.txt", model=MODEL),
                  criteria=[crit("c-mode")]))}
    spec = named(Workflow(order=["fix"], units=units, issue_repository="acme/x", run_cost_cap_usd=1.0,
                          routing=Routing(description="Set up a config file")))
    out = start(spec, "LIVE-29", {"request": "the strict profile"}, repo, default_registry(), RunSettings())
    rd = run_dir(state_root_path(repo), "demo", "LIVE-29")
    recs = [json.loads(ln) for ln in (rd / "run.jsonl").read_text().splitlines()]
    previews = [r for r in recs if r.get("kind") == "self_check"]
    checks = [r for r in recs if r.get("kind") == "check" and r.get("unit") == "fix"]
    runs = [r for r in recs if r.get("kind") == "agent_run" and r.get("session_kind") == "step"]
    print("exit:", out.exit_code, out.reason)
    print("previews:", [(r.get("result"), r.get("n")) for r in previews])
    print("gate checks:", [r.get("result") for r in checks])
    print("step tools:", [r.get("tools") for r in runs], "denied:", [r.get("denied") for r in runs])
    assert previews, "the session never ran its check preview"
    assert previews[0].get("result") == "FAIL"  # the preview reported the finding before the fix
    assert checks and checks[-1].get("result") == "PASS"  # the gate's own check ran after the session
    assert not any("self-check" in str(d) for r in runs for d in (r.get("denied") or []))
