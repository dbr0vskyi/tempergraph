"""Judge view sets and the after-the-fact guard (GRD-B1, GRD-B8, GRD-B1–B5).

The view catalog is keyed by full executor tool name; nothing is inferred from a name pattern (GRD-AC1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from tempergraph.contracts import Capabilities, Deferred, StepSpec, ToolCall, ViewSet
from tempergraph.executors.capabilities import tool_names
from tempergraph.git import Fingerprint

BASE_VIEWS = ("read", "search", "list")


@dataclass(frozen=True, kw_only=True)
class GuardResult:
    status: Literal["clean", "discarded", "warned", "unavailable"]
    reason: str | None = None


def view_set(step: StepSpec, step_calls: Sequence[ToolCall], judge_caps: Capabilities,
             judge_tools: Sequence[str] | None = None, granted: Sequence[str] = ()) -> ViewSet:
    """GRD-B1: the base read views, plus a read view per MCP write; an author may narrow, never widen."""
    caps = list(BASE_VIEWS)
    deferred: list[Deferred] = []
    for t in step.tools:
        if t.startswith("mcp:"):
            if judge_caps.judge_mcp:
                caps.append(t)
            else:
                deferred.append(Deferred(capability=t, reason="judge_mcp"))
    if judge_tools is not None:
        caps = [c for c in caps if c in judge_tools]
        caps = caps or list(BASE_VIEWS)
    caps += [g for g in granted if g not in caps]  # a person's read-only view grant (RST-B28, RST-B29, RST-B30)
    names: list[str] = []
    for c in caps:
        names.extend(tool_names(judge_caps, c))
    return ViewSet(tools=tuple(dict.fromkeys(names)), deferred=tuple(deferred))


def guard(views: ViewSet, judge_calls: Sequence[ToolCall], before: Fingerprint, after: Fingerprint, *,
          workspace_mode: str, step_session_id: str | None, judge_session_id: str | None,
          reports_actions: bool = True) -> GuardResult:
    if judge_session_id and step_session_id and judge_session_id == step_session_id:
        return GuardResult(status="discarded", reason="same_session")  # GRD-B4, EXI-B9
    allowed = set(views.tools)
    for call in judge_calls:
        if not call.name or call.name not in allowed or call.subagent:
            return GuardResult(status="discarded", reason=f"outside_call:{call.name or '<unnamed>'}")
    if before != after:
        if workspace_mode == "worktree":
            return GuardResult(status="discarded", reason="workspace_changed")
        return GuardResult(status="warned", reason="workspace_changed")
    if not judge_calls and not reports_actions:
        return GuardResult(status="unavailable", reason="no_action_report")
    return GuardResult(status="clean")
