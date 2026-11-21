"""Scripted stand-in executors (ADR-0091 item 2, CLAUDE.md test rule).

A stand-in carries one of the four declared capability sets and answers each session from a script
instead of a process, so the engine's gate funnel, cross-executor judging, estimate-only cost and every
refusal path are tested offline. The recorded-CLI conformance stand-in that goes through the real
launcher lives with the tests.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import ClassVar

from tempergraph.contracts import (
    Capabilities,
    Event,
    EventSink,
    ProbeReport,
    SessionRequest,
    SessionResult,
    ToolCall,
    Usage,
    ViewSet,
)
from tempergraph.executors.capabilities import DECLARED

Reply = SessionResult | Callable[[SessionRequest], SessionResult]


@dataclass(kw_only=True)
class Call:
    kind: str
    request: SessionRequest
    views: ViewSet | None = None


def answer(text: str, *, tools: Iterable[str] = (), cost: float | None = 0.01, session_id: str = "",
           tokens: tuple[int, int] = (100, 50), **fields: object) -> SessionResult:
    """A successful scripted session with the given final text."""
    usage = Usage(input_tokens=tokens[0], output_tokens=tokens[1], reported_cost_usd=cost, turns=1)
    calls = [ToolCall(name=t, ok=True, call_id=f"t{i}") for i, t in enumerate(tools)]
    return SessionResult(ok=True, text=text, session_id=session_id or None, usage=usage, tool_calls=calls,
                         **fields)  # type: ignore[arg-type]


@dataclass(kw_only=True)
class ScriptedExecutor:
    scripted: ClassVar[bool] = True  # makes no model call; a live suite's guard reads this (EVS §4)
    caps: Capabilities
    steps: list[Reply] = field(default_factory=list)
    judges: list[Reply] = field(default_factory=list)
    probe_report: ProbeReport = field(default_factory=lambda: ProbeReport(ok=True, version="standin"))
    calls: list[Call] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.caps.name

    def capabilities(self) -> Capabilities:
        return replace(self.caps, version=self.probe_report.version)

    def probe(self) -> ProbeReport:
        return self.probe_report

    def run_step(self, req: SessionRequest, sink: EventSink) -> SessionResult:
        self.calls.append(Call(kind="step", request=req))
        return self._reply(self.steps, req, sink, "step")

    def run_judge(self, req: SessionRequest, views: ViewSet, sink: EventSink) -> SessionResult:
        self.calls.append(Call(kind="judge", request=req, views=views))
        return self._reply(self.judges, req, sink, "judge")

    def _reply(self, queue: list[Reply], req: SessionRequest, sink: EventSink, what: str) -> SessionResult:
        if not queue:
            raise AssertionError(f"stand-in {self.caps.name}: no scripted {what} reply left for {req.session_key}")
        item = queue.pop(0)
        res = item(req) if callable(item) else item
        if not self.caps.reports_cost and res.usage.reported_cost_usd is not None:
            res = replace(res, usage=replace(res.usage, reported_cost_usd=None))  # estimate-only executors
        sink.push(Event(kind="session_started", data={"session_id": res.session_id, "model": res.model,
                                                      "tools": list(res.tools_at_start)}))
        for c in res.tool_calls:
            sink.push(Event(kind="tool_started", data={"name": c.name, "call_id": c.call_id, "subagent": c.subagent}))
            sink.push(Event(kind="tool_finished", data={"call_id": c.call_id, "ok": c.ok}))
        sink.push(Event(kind="result", data={"ok": res.ok, "usage": res.usage}))
        return replace(res, cli_version=res.cli_version or self.probe_report.version)


def standin(name: str, **kw: object) -> ScriptedExecutor:
    """A stand-in carrying the declared capability set of executor ``name``."""
    return ScriptedExecutor(caps=DECLARED[name], **kw)  # type: ignore[arg-type]
