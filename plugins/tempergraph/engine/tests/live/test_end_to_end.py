"""Live end to end (first-release plan T11.2, M1; SRV live): one capped run of a two-step workflow on the real
`claude` executor, then the loop child inline, so the session digest and the session review read real logs.

Skipped unless TEMPERGRAPH_LIVE=1. The run is capped at 2 USD and the review at its own SRV-B21 cap.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.registry import default_registry
from tempergraph.improve import child, digest
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from ..fixtures.workflows import two_step

pytestmark = pytest.mark.live


def test_m1_two_step_run_and_session_review(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "inline")
    spec = two_step(run_cost_cap_usd=2.0)
    out = start(spec, "LIVE-1", {"request": "a two-line release note for version 0.1"}, repo, default_registry(),
                RunSettings())
    print("exit:", out.exit_code, out.reason)
    root = state_root_path(repo)
    rd = run_dir(root, "demo", "LIVE-1")
    recs = [json.loads(ln) for ln in (rd / "run.jsonl").read_text().splitlines()]
    runs = [r for r in recs if r.get("kind") == "agent_run"]
    print("sessions:", [(r["session_key"], r.get("ok"), (r.get("usage") or {}).get("reported_cost_usd")) for r in runs])
    assert runs and all(r.get("ok") for r in runs)
    assert out.exit_code in (ExitCode.FINISHED, ExitCode.PAUSED)  # a judge may ask a person; both are a pass
    caps = {r["session_key"]: (digest.read(root, "demo", "LIVE-1", r["session_key"]) or {}).get("capture")
            for r in runs}
    print("digest capture:", caps)
    assert set(caps.values()) == {"full"}
    loop = [json.loads(ln) for ln in child.loop_log(root, "demo", "LIVE-1").read_text().splitlines()]
    kinds = [r["kind"] for r in loop]
    print("loop records:", kinds)
    assert "review_planned" in kinds and ("review_done" in kinds or "review_failed" in kinds)
