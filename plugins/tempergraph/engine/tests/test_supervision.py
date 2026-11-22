"""The supervision record (SUP-B10, SUP-B11, SUP-B1, B2, B3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.run import supervision

from .test_cli import cli, happy
from .test_feedback import Seen, paused, records
from .test_run import DRAFT, REVIEW, judge


def row(unit: str, *classes: str, by: str = "person", wait: float | None = 5.0, **extra: Any) -> dict[str, Any]:
    return {"kind": "intervention", "thread_id": "demo/T", "unit": unit, "wait_s": wait,
            "caller": {"kind": by, "decided_by": by, "relay": "direct" if by == "person" else "none"},
            "touches": [{"class": c} for c in classes], **extra}


def build(tmp_path: Path, *rows: dict[str, Any], units: tuple[str, ...] = ("draft", "review", "ship", "close")
          ) -> dict[str, Any]:
    ledger, log = tmp_path / "ledger.jsonl", tmp_path / "run.jsonl"
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    log.write_text(json.dumps({"kind": "run_started", "caller": {"kind": "person"}}) + "\n")
    return supervision.build(ledger, log, "demo/T", units)


@pytest.mark.parametrize(("rows", "level", "level_by"), [
    ([], "observer", "none"),
    ([row("ship", "designed")], "approver", "none"),
    ([row("review", "rescue")], "consultant", "person"),
    ([row("review", "rescue"), row("review", "steer", by="agent")], "collaborator", "mixed"),
    ([row("draft", "rescue"), row("review", "steer")], "operator", "person"),
])
def test_level_rules(tmp_path: Path, rows: list[dict[str, Any]], level: str, level_by: str) -> None:  # SUP-B11
    rec = build(tmp_path, *rows)
    assert (rec["level"], rec["level_by"]) == (level, level_by)
    assert rec["supervision_cost"] is None and rec["observations"] is None  # unmeasured is never zero


def test_counts_waits_and_agent_approvals(tmp_path: Path) -> None:  # SUP-B2
    rec = build(tmp_path, row("ship", "designed", by="agent", wait=2.0), row("close", "designed", by="agent",
                                                                             wait=4.0))
    assert rec["touches"]["designed"]["agent"] == 2 and rec["undesigned"] == 0
    assert rec["wait_s"] == {"agent": 6.0} and rec["person_wait_s"] == 0.0
    assert rec["latency_s"] == {"median": 3.0, "max": 4.0}
    assert rec["level"] == "approver" and rec["designed_by"] == "agent"
    other = build(tmp_path, row("review", "rescue", pause_kind="tool_access"), row("x", "bogus"))
    assert other["touches"]["rescue_by_pause"] == {"tool_access": 1} and other["undesigned"] == 1


def test_a_finished_run_writes_its_record(repo: Path) -> None:  # SUP-B1
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "S-1")
    assert code == 0, err
    sup = records(repo, "S-1", "supervision")
    assert len(sup) == 1 and sup[0]["level"] == "observer"
    kinds = [json.loads(x)["kind"] for x in (repo / ".tempergraph" / "runs" / "demo" / "S-1" / "run.jsonl")
             .read_text().splitlines()]
    assert kinds.index("supervision") < kinds.index("run_exit")
    seg = [json.loads(x) for x in (repo / ".tempergraph" / "ledger.jsonl").read_text().splitlines()]
    assert [r["supervision"]["level"] for r in seg if r["kind"] == "run_segment"] == ["observer"]


def test_a_rescue_and_a_rerun_count_on_the_thread(repo: Path) -> None:  # SUP-B3
    seen = Seen()
    ex = paused(repo, "S-2", seen)
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge()]
    code, _, err = cli(repo, ex, "resume", "demo", "S-2", "--decision", "retry")
    assert code == 0, err
    last = records(repo, "S-2", "supervision")[-1]
    assert last["touches"]["rescue"]["person"] == 1 and last["level"] in ("consultant", "operator")
    assert last["person_wait_s"] >= 0
    ex.steps, ex.judges = [REVIEW], [judge()]
    code, _, err = cli(repo, ex, "rerun", "demo", "S-2", "--from", "review")
    assert code == 0, err
    rows = [json.loads(x) for x in (repo / ".tempergraph" / "ledger.jsonl").read_text().splitlines()]
    steer = [r for r in rows if r["kind"] == "intervention" and r["cause"] == "rerun"]
    assert steer and steer[0]["thread_id"] == "demo/S-2" and steer[0]["rerun"] == "demo/S-2~r1"
