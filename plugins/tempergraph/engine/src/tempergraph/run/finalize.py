"""The finalizer contract (FIN-B6 to FIN-B10): one call after the last pass, no model, never the request text."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tempergraph.run import checks as checkmod
from tempergraph.run.commands import CommandRefusal, CommandRun, ResolvedCommand, resolve_command, run_command
from tempergraph.security.scrub import clip, scrub

if TYPE_CHECKING:
    from tempergraph.run.nodes import RunContext

FINALIZER_LIMIT_S = 600
COMMAND_LIMIT_S = 120


@dataclass(kw_only=True)
class FinalizerContext:
    task_id: str
    thread_id: str
    workflow: str
    branch: str
    base: str
    workdir: Path
    artifacts: Mapping[str, Any]
    values: Mapping[str, Any]
    facts: Mapping[str, Any]
    open_warnings: int
    degraded: bool
    run_options: Mapping[str, Any]
    git: checkmod.GitFacts | None  # None outside a git repository (WSP-B15 to WSP-B18)
    allow: tuple[str, ...] = ()
    main: Path | None = None
    out_dir: Path | None = None
    runs: list[CommandRun] = field(default_factory=list)

    def resolve(self, text: str) -> ResolvedCommand | CommandRefusal:
        return resolve_command(self.allow, text, self.workdir)

    def run(self, cmd: ResolvedCommand | str, timeout_s: float = COMMAND_LIMIT_S) -> CommandRun:
        if isinstance(cmd, str):
            got = self.resolve(cmd)
            if isinstance(got, CommandRefusal):
                return CommandRun(argv=(clip(scrub(cmd), 200),), not_started=True, extra={"refused": got.reason})
            cmd = got
        out = (self.out_dir or self.workdir) / f"{len(self.runs) + 1}.out"
        r = run_command(cmd, self.workdir, out, timeout_s, main=self.main)
        self.runs.append(r)
        return r

    @staticmethod
    def scrub(text: str) -> str:
        return scrub(text)

    @staticmethod
    def clip(text: str, n: int) -> str:
        return clip(text, n)


@dataclass(kw_only=True)
class FinalizerResult:
    outcome: str
    reason: str = ""
    url: str | None = None
    manual_steps: list[str] = field(default_factory=list)


def run_finalizer(ctx: RunContext, state: Mapping[str, Any]) -> dict[str, Any]:
    spec = ctx.spec
    if spec.finalizer is None:
        return {"outcome": "none"}
    ws = state.get("workspace") or {}
    workdir = Path(ws.get("path") or ctx.state_root.parent)
    open_warnings = sum(len((j or {}).get("notes") or []) for j in (state.get("judgements") or {}).values())
    fctx = FinalizerContext(
        task_id=ctx.task_id, thread_id=ctx.thread, workflow=spec.name, branch=str(ws.get("branch") or ""),
        base=str(ws.get("base_branch") or ""), workdir=workdir, artifacts=state.get("artifacts") or {},
        values=state.get("values") or {}, facts=state.get("facts") or {}, open_warnings=open_warnings,
        degraded=False, run_options={"mode": ws.get("mode")}, git=checkmod.git_facts(workdir),
        allow=tuple(spec.allow_commands), main=ctx.main_checkout,
        out_dir=ctx.state_root / "runs" / spec.name / ctx.task_id / "finalizer")
    box: dict[str, Any] = {}
    fn = spec.finalizer.resolve()

    def call() -> None:
        try:
            box["result"] = fn(fctx)
        except Exception as exc:  # noqa: BLE001 - recorded as `error`
            box["error"] = type(exc).__name__

    t0 = time.monotonic()
    th = threading.Thread(target=call, name="finalizer", daemon=True)
    th.start()
    th.join(FINALIZER_LIMIT_S)
    dur = round(time.monotonic() - t0, 3)
    if th.is_alive():
        return {"outcome": "error", "reason": "timed_out", "duration_s": dur}
    if "error" in box:
        return {"outcome": "error", "reason": box["error"], "duration_s": dur}
    res = box.get("result")
    if not isinstance(res, FinalizerResult):
        return {"outcome": "invalid", "reason": clip(scrub(repr(res)), 200), "duration_s": dur}
    outcome = res.outcome if res.outcome in spec.finalizer_outcomes else "invalid"
    reason = clip(scrub(res.reason if outcome != "invalid" else res.outcome), 200)
    return {"outcome": outcome, "reason": reason, "url": res.url, "manual_steps": [clip(scrub(m), 300) for m in
                                                                                   res.manual_steps[:5]],
            "duration_s": dur}
