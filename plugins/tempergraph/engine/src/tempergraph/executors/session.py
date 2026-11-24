"""Turn a launcher outcome into a `SessionResult` (EXI-B6, EXI-B7, SSN-B1 to SSN-B6).

The shared part: tool calls in order, denied names, tools at start, the share of wall time inside tool
calls, usage from the `result` event only (never 0 when unknown), and the process-level infra causes.
Each executor adds its own result-level classification, read from structured facts only.
"""

from __future__ import annotations

import errno
import signal
from dataclasses import dataclass
from typing import Any

from tempergraph.contracts import ErrorKind, Event, InfraCause, SessionResult, ToolCall, Usage
from tempergraph.executors.launcher import RawOutcome

RESOURCE_ERRNOS = frozenset({errno.EAGAIN, errno.ENOMEM, errno.EMFILE, errno.ENFILE})
KILLED_BY_OS = (-signal.SIGKILL, 137) if hasattr(signal, "SIGKILL") else ()


@dataclass(frozen=True, kw_only=True)
class Summary:
    tool_calls: list[ToolCall]
    denied: tuple[str, ...]
    tools_at_start: tuple[str, ...]
    session_id: str | None
    model: str | None
    result: dict[str, Any] | None
    retry_categories: tuple[str, ...]
    tool_wall_share: float


def summarize(events: list[Event], duration_s: float) -> Summary:
    calls: list[ToolCall] = []
    index: dict[str, int] = {}
    started: dict[str, float] = {}
    in_tools = 0.0
    denied: list[str] = []
    tools: tuple[str, ...] = ()
    session_id = model = None
    result: dict[str, Any] | None = None
    retries: list[str] = []
    for ev in events:
        d = ev.data
        if ev.kind == "session_started":
            tools = tuple(d.get("tools") or ())
            session_id = d.get("session_id") or session_id
            model = d.get("model") or model
        elif ev.kind == "tool_started":
            cid = str(d.get("call_id", ""))
            index[cid] = len(calls)
            started[cid] = ev.ts
            calls.append(ToolCall(name=str(d.get("name", "")), subagent=bool(d.get("subagent")), call_id=cid))
        elif ev.kind == "tool_finished":
            cid = str(d.get("call_id", ""))
            if cid in index:
                c = calls[index[cid]]
                calls[index[cid]] = ToolCall(name=c.name, ok=bool(d.get("ok")), subagent=c.subagent, call_id=cid)
            if cid in started:
                in_tools += max(0.0, ev.ts - started.pop(cid))
        elif ev.kind == "denied":
            denied.append(str(d.get("name", "")))
        elif ev.kind == "retrying":
            retries.append(str(d.get("category") or ""))
        elif ev.kind == "result":
            result = dict(d)
            session_id = d.get("session_id") or session_id
    share = min(1.0, in_tools / duration_s) if duration_s > 0 else 0.0
    return Summary(tool_calls=calls, denied=tuple(denied), tools_at_start=tools, session_id=session_id,
                   model=model, result=result, retry_categories=tuple(retries), tool_wall_share=share)


def process_cause(raw: RawOutcome) -> InfraCause | None:
    """Causes visible before any stream is read: spawn, stdin, an empty or OS-killed process."""
    if raw.spawn_error is not None:
        return InfraCause.SPAWN_FAILED
    if raw.prompt_timeout:
        return InfraCause.PROMPT_NOT_DELIVERED
    if raw.broken_pipe:
        return InfraCause.BROKEN_PIPE
    if raw.lines == 0 and raw.stop_reason is None:
        return InfraCause.NO_OUTPUT
    return None


def build_result(raw: RawOutcome, s: Summary, *, cli_version: str, argv: list[str], applied: tuple[str, ...],
                 infra: InfraCause | None, error_kind: ErrorKind | None, ok: bool, usage_limit: bool = False,
                 usage_limit_resets_at: float | None = None) -> SessionResult:
    usage = s.result.get("usage") if s.result else None
    text = str(s.result.get("text") or "") if s.result else ""
    timed_out = raw.stop_reason == "timeout"
    stalled = raw.stop_reason == "idle"
    partial = raw.stop_reason is not None and (raw.killed or s.result is None)
    built_ok = ok and infra is None and error_kind is None and not (timed_out or stalled or partial)
    return SessionResult(
        ok=built_ok, usage_limit=usage_limit and not built_ok,  # SSN-B11: never true for an ok session
        usage_limit_resets_at=usage_limit_resets_at if usage_limit and not built_ok else None,
        text=text, session_id=s.session_id, usage=usage if isinstance(usage, Usage) else Usage(),
        tool_calls=s.tool_calls, timed_out=timed_out, stalled=stalled, partial=partial, infra_cause=infra,
        error_kind=error_kind, applied_options=applied, cli_version=cli_version, model=s.model, denied=s.denied,
        tools_at_start=s.tools_at_start, tool_wall_share=s.tool_wall_share, prompt_gap_s=raw.prompt_gap_s,
        duration_s=raw.duration_s, argv=tuple(argv))


def killed_by_os(raw: RawOutcome) -> bool:
    return raw.stop_reason is None and raw.exit_code in KILLED_BY_OS
