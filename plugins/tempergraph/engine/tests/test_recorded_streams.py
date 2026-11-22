"""GRD-AC5 and ECC-B11 on streams recorded from a real `claude` (live check L-21, CLI 2.1.330, 2026-11-22).

`fixtures/recorded/` holds one judge session and one step session of the doc-refresh example, without the
partial-message events, with paths replaced by `/work` and `/scratch` and the host's own init fields dropped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.contracts import ViewSet
from tempergraph.executors.claude import parse_line
from tempergraph.executors.session import summarize
from tempergraph.git import Fingerprint
from tempergraph.run.guard import guard

HERE = Path(__file__).parent / "fixtures" / "recorded"
VIEWS = ViewSet(tools=("Glob", "Grep", "Read"))
FP = Fingerprint(head="abc", status="")


def records(name: str) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in (HERE / name).read_text().splitlines() if ln.strip()]


def summary(recs: list[dict[str, Any]]) -> Any:
    events = [e for r in recs for e in parse_line(json.dumps(r).encode())]
    return summarize(events, 10.0)


def judged(recs: list[dict[str, Any]]) -> Any:
    s = summary(recs)
    return guard(VIEWS, s.tool_calls, FP, FP, workspace_mode="worktree", step_session_id="step",
                 judge_session_id=s.session_id)


def planted(recs: list[dict[str, Any]], *extra: dict[str, Any]) -> list[dict[str, Any]]:
    at = next(i for i, r in enumerate(recs) if r.get("type") == "result")
    return [*recs[:at], *extra, *recs[at:]]


def use(name: str, cid: str, parent: str | None = None) -> dict[str, Any]:
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"content": [{"type": "tool_use", "id": cid, "name": name, "input": {}}]}}


def test_a_recorded_judge_session_is_clean() -> None:
    recs = records("claude-2.1.330-judge.jsonl")
    s = summary(recs)
    assert s.tools_at_start == ("Glob", "Grep", "Read") and s.result is not None
    assert {c.name for c in s.tool_calls} <= set(VIEWS.tools) and s.tool_calls
    assert judged(recs).status == "clean"


def test_a_planted_subagent_call_in_a_recorded_judge_stream_is_caught() -> None:  # GRD-AC5
    recs = records("claude-2.1.330-judge.jsonl")
    got = judged(planted(recs, use("Task", "p1"), use("Read", "p2", parent="p1")))
    assert (got.status, got.reason) == ("discarded", "outside_call:Task")
    child_only = judged(planted(recs, use("Read", "p3", parent="p0")))  # a child turn alone is a subagent too
    assert (child_only.status, child_only.reason) == ("discarded", "outside_call:Read")


def test_a_recorded_step_session_maps_to_events() -> None:  # ECC-B11 on 2.1.330
    s = summary(records("claude-2.1.330-step.jsonl"))
    assert s.session_id and s.model == "claude-sonnet-5-5" and s.result is not None
    names = [c.name for c in s.tool_calls]
    assert names.count("Read") == 6 and names[-1] == "Edit" and not any(c.subagent for c in s.tool_calls)
    assert [c.ok for c in s.tool_calls].count(False) == 3  # three reads of files that do not exist, as recorded
    assert s.result["usage"].reported_cost_usd and s.result["usage"].reported_cost_usd > 0
