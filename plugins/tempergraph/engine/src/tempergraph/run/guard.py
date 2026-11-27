"""Judge view sets and the after-the-fact guard (GRD-B1, GRD-B8, GRD-B1–B5).

The view catalog is keyed by full executor tool name; nothing is inferred from a name pattern (GRD-AC1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from tempergraph.contracts import Capabilities, Deferred, StepSpec, ToolCall, ViewSet
from tempergraph.executors import viewcatalog
from tempergraph.executors.capabilities import tool_names
from tempergraph.git import Fingerprint

BASE_VIEWS = ("read", "search", "list")


@dataclass(frozen=True, kw_only=True)
class GuardResult:
    status: Literal["clean", "discarded", "warned", "unavailable"]
    reason: str | None = None


def view_set(step: StepSpec, step_calls: Sequence[ToolCall], judge_caps: Capabilities,
             judge_tools: Sequence[str] | None = None, granted: Sequence[str] = ()) -> ViewSet:
    """GRD-B1: the base read views, plus a read view per MCP write; an author may narrow, never widen. An MCP
    view comes from the catalog, never from the step's own tool (GRD-B7, GRD-AC6): a tool the catalog does not
    list gives no view and is recorded as deferred."""
    caps = list(BASE_VIEWS)
    deferred: list[Deferred] = []
    for t in step.tools:
        if t.startswith("mcp:"):
            if not judge_caps.judge_mcp:
                deferred.append(Deferred(capability=t, reason="judge_mcp"))
                continue
            found = viewcatalog.read_views(t)
            if not found:
                deferred.append(Deferred(capability=t, reason="view_unlisted"))
            caps += [v for v in found if v not in caps]
    if judge_tools is not None:
        caps = [c for c in caps if c in judge_tools]
        caps = caps or list(BASE_VIEWS)
    caps += [g for g in granted if g not in caps]  # a person's read-only view grant (RST-B28, RST-B29, RST-B30)
    names: list[str] = []
    for c in caps:
        names.extend(tool_names(judge_caps, c))
    return ViewSet(tools=tuple(dict.fromkeys(names)), deferred=tuple(deferred))


def _filter_owned(fp: Fingerprint, owned: Sequence[str]) -> Fingerprint:
    """EXI-B30, GRD-B3: strip launcher-owned paths from a git status fingerprint before comparing."""
    if not owned or fp.manifest:
        return fp
    lines = [ln for ln in fp.status.splitlines()
             if not any(ln[3:].startswith(p) for p in owned)]
    return replace(fp, status="\n".join(lines))


def filter_owned_changed_paths(paths: tuple[str, ...], owned: Sequence[str]) -> tuple[str, ...]:
    """EXI-B30, CHK-B10: exclude launcher-owned paths from the changed_paths a check receives."""
    if not owned:
        return paths
    return tuple(p for p in paths if not any(p.startswith(o) for o in owned))


def guard(views: ViewSet, judge_calls: Sequence[ToolCall], before: Fingerprint, after: Fingerprint, *,
          workspace_mode: str, step_session_id: str | None, judge_session_id: str | None,
          reports_actions: bool = True, launcher_owned_paths: Sequence[str] = ()) -> GuardResult:
    if judge_session_id and step_session_id and judge_session_id == step_session_id:
        return GuardResult(status="discarded", reason="same_session")  # GRD-B4, EXI-B9
    allowed = set(views.tools)
    for call in judge_calls:
        if not call.name or call.name not in allowed or call.subagent:
            return GuardResult(status="discarded", reason=f"outside_call:{call.name or '<unnamed>'}")
    # EXI-B30, GRD-B3: exclude launcher-owned paths before comparing fingerprints
    before_cmp = _filter_owned(before, launcher_owned_paths)
    after_cmp = _filter_owned(after, launcher_owned_paths)
    if before_cmp != after_cmp:
        if workspace_mode == "worktree":
            return GuardResult(status="discarded", reason="workspace_changed")
        return GuardResult(status="warned", reason="workspace_changed")
    if not judge_calls and not reports_actions:
        return GuardResult(status="unavailable", reason="no_action_report")
    return GuardResult(status="clean")
