"""The node bodies the compiler wires into the graph (CMP `UnitNodes`): step, judge, gate, human, finalizer.

The step and judge nodes are the only places a model session starts (contract C1); the gate is pure;
the human node's interrupt is the compiler's. Budgets follow BUD §2.2: the cause picks the counter.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph import git as gitmod
from tempergraph.compiler.state import RunState
from tempergraph.contracts import (
    CheckResult,
    Executor,
    SessionOptions,
    SessionRequest,
    SessionResult,
    Verdict,
    WorkflowSpec,
)
from tempergraph.executors.launcher import StopRequest
from tempergraph.executors.registry import Registry
from tempergraph.model import flow
from tempergraph.model.text import load_text, split_judge_file
from tempergraph.render.output import parse_output
from tempergraph.render.prompt import AttemptContext, Blocker, render_step
from tempergraph.run import checks as checkmod
from tempergraph.run import gate as gatemod
from tempergraph.run.check_worker import run_in_worker
from tempergraph.run.commands import ResolvedCommand, run_command
from tempergraph.run.guard import guard, view_set
from tempergraph.run.judging import JudgeInputs, Unparsed, derive, parse_judgement, reask_prompt, render_judge
from tempergraph.run.log import CostTotals, LiveSink, RunLog, estimate
from tempergraph.security.scrub import clip, scrub
from tempergraph.store.layout import session_dir, session_key

ATTEMPT_CAP = 15
INFRA_TRIES = 3
BACKOFF_S = (10, 20, 40)
DEFAULT_TIMEOUT_S = 600


class Drain(Exception):
    """End this process's segment at a boundary; the thread stays resumable (CMP-B5, RCT-B1, BUD cost cap)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(kw_only=True)
class RunContext:
    spec: WorkflowSpec
    task_id: str
    state_root: Path
    registry: Registry
    log: RunLog
    judges: Mapping[str, str] = field(default_factory=dict)
    enforce_tools: bool = False
    judge_override: str | None = None
    stop: StopRequest = field(default_factory=StopRequest)
    drain_requested: Callable[[], str | None] = lambda: None
    sleep: Callable[[float], None] = time.sleep
    attempt_cap: int = ATTEMPT_CAP
    infra_tries: int = INFRA_TRIES
    main_checkout: Path | None = None
    attempts_started: int = 0

    @property
    def thread(self) -> str:
        return f"{self.spec.name}/{self.task_id}"


def _aliases(v: object) -> list[str]:
    if v is None:
        return []
    return [v] if isinstance(v, str) else [str(x) for x in v]  # type: ignore[attr-defined]


class EngineNodes:
    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx

    # -- helpers ---------------------------------------------------------------------------------

    def _workdir(self, state: Mapping[str, Any]) -> Path:
        return Path((state.get("workspace") or {}).get("path") or self.ctx.state_root.parent)

    def _in_worktree(self, state: Mapping[str, Any]) -> bool:
        return (state.get("workspace") or {}).get("mode") == "worktree"

    def _boundary(self, state: Mapping[str, Any]) -> None:
        reason = self.ctx.drain_requested()
        if reason:
            raise Drain(reason)
        if self.ctx.attempts_started >= self.ctx.attempt_cap:
            raise Drain("attempt_cap")
        cap = self.ctx.spec.run_cost_cap_usd
        if cap is not None and CostTotals.from_json((state.get("run") or {}).get("cost")).figure() >= cap:
            raise Drain("cost_cap")

    def _session(self, ex: Executor, req: SessionRequest, judge_views: Any = None) -> tuple[SessionResult, list]:
        """One session with infra tries and backoff outside the retry budget (BUD-B1, JDG-B5)."""
        results: list[SessionResult] = []
        for n in range(self.ctx.infra_tries):
            sink = LiveSink(req.session_dir)
            self.ctx.log.write("attempt_start", session_key=req.session_key, kind=req.kind, executor=ex.name,
                               alias=req.alias, timeout_s=req.timeout_s)
            if judge_views is None:
                res = ex.run_step(req, sink)
            else:
                res = ex.run_judge(req, judge_views, sink)
            if res.usage.estimated_cost_usd is None:
                res.usage.estimated_cost_usd = estimate(res.usage, res.model)
            results.append(res)
            self.ctx.log.write("agent_run", session_key=req.session_key, kind=req.kind, executor=ex.name,
                               alias=req.alias, usage=res.usage, ok=res.ok, tools=[c.name for c in res.tool_calls],
                               cli_version=res.cli_version, session_id=res.session_id,
                               infra_cause=str(res.infra_cause) if res.infra_cause else None,
                               error_kind=res.error_kind, timed_out=res.timed_out, stalled=res.stalled)
            if res.infra_cause is None or n + 1 >= self.ctx.infra_tries:
                break
            self.ctx.sleep(BACKOFF_S[min(n, len(BACKOFF_S) - 1)])
        return results[-1], results

    def _cost(self, state: Mapping[str, Any], results: list[SessionResult]) -> dict[str, Any]:
        totals = CostTotals.from_json((state.get("run") or {}).get("cost"))
        for r in results:
            totals.add(r.usage)
        return totals.to_json()

    # -- step ------------------------------------------------------------------------------------

    def step(self, unit: str, state: RunState) -> dict[str, Any]:
        spec = self.ctx.spec
        u = spec.units[unit]
        self._boundary(state)
        if u.kind == "script":
            return self._script_unit(unit, state)
        st = u.step
        assert st is not None
        prev = (state.get("attempts") or {}).get(unit) or {}
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        counters = (state.get("counters") or {}).get(unit) or {}
        first = prev.get("visit") != visit
        attempt = int(prev.get("attempt", 0)) + 1
        retries = int(counters.get("retries", 0))
        self.ctx.attempts_started += 1
        workdir = self._workdir(state)
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        if first:
            fp = gitmod.fingerprint(workdir)
            self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=bool(fp.status),
                               entered_from=_entered_from(state, unit))
        ladder = _aliases(st.model) or _aliases(spec.model_profile.get(unit)) or ["inherit"]
        alias = ladder[min(retries, len(ladder) - 1)]
        ex = self.ctx.registry.get(st.executor or spec.default_executor)
        caps = ex.capabilities()
        fields = self._fields(unit, state, attempt, visit, workdir)
        judged = (state.get("judgements") or {}).get(unit) or {}
        fb = (state.get("feedback") or {}).get(unit) or {}
        retry = not first and bool(prev)
        prev_unit = self._previous_unit(unit, path_units)
        prev_judged = ((state.get("judgements") or {}).get(prev_unit) or {}) if prev_unit else {}
        notes = tuple(prev_judged.get("notes") or ()) if first else ()
        ctx = AttemptContext(
            template=load_text(spec, st.prompt), fields=fields, attempt=attempt, retry=retry,
            blockers=tuple(Blocker(criterion=str(b.get("criterion", "")), place=str(b.get("place", "")),
                                   problem=str(b.get("problem", "")), fix=str(b.get("fix", "")))
                           for b in (judged.get("blockers") or [])) if retry else (),
            check_evidence=str(((prev.get("check") or {}).get("evidence")) or "") if retry else "",
            previous_report=str(prev.get("text") or "") if retry else "",
            paths_only=retry and bool(prev.get("cut_off")),
            notes=notes + ((str(fb.get("text")),) if fb.get("as") == "notes" else ()),
            visit_reason=str(((state.get("visits") or {}).get(unit) or {}).get("reason") or "") if first else "",
            visit_from=str(((state.get("visits") or {}).get(unit) or {}).get("from") or "") if first else "",
            feedback=str(fb.get("text") or "") if fb.get("as") == "feedback" else "",
            rulings=tuple(str(r.get("text")) for r in (state.get("rulings") or {}).values()
                          if isinstance(r, dict) and unit in (r.get("applies_to") or [unit])),
            upstream_targets=tuple(u.gate.back_targets))
        rendered = render_step(unit, u, ctx, caps)
        key = session_key(unit, attempt, "retry" if retry else "step")
        req = SessionRequest(
            kind="retry" if retry else "step", prompt=rendered.text, workdir=workdir, alias=alias, session_key=key,
            tools=tuple(st.tools), commands=tuple(st.commands), timeout_s=st.timeout_s or DEFAULT_TIMEOUT_S,
            idle_s=st.idle_s, options=st.session_options or SessionOptions(),
            session_dir=session_dir(self.ctx.state_root, spec.name, self.ctx.task_id, key),
            enforce_tools=self.ctx.enforce_tools, in_engine_worktree=self._in_worktree(state),
            plugin_dir=spec.package_root)
        before = gitmod.fingerprint(workdir)
        res, results = self._session(ex, req)
        after = gitmod.fingerprint(workdir)
        parsed = parse_output(res.text, st.produces, tuple(u.gate.back_targets))
        escalate: str | None = None
        if res.error_kind in ("auth", "refused"):
            escalate = res.error_kind
        elif res.denied and (not res.ok or parsed.blocked):
            escalate = "tool_access"
        elif parsed.blocked:
            escalate = "blocked"
        elif parsed.upstream:
            escalate = "upstream"
        record = {
            "attempt": attempt, "visit": visit, "ok": res.ok, "text": clip(scrub(res.text), 8000), "blocked": parsed.blocked, "upstream": parsed.upstream,
            "issues": parsed.issues, "infra_cause": str(res.infra_cause) if res.infra_cause else None,
            "infra_spent": res.infra_cause is not None, "timed_out": res.timed_out, "stalled": res.stalled,
            "error_kind": res.error_kind, "denied": list(res.denied), "tools": [c.name for c in res.tool_calls],
            "session_id": res.session_id, "executor": ex.name, "alias": alias, "model": res.model,
            "changed": before != after, "escalate": escalate, "cut_off": res.partial, "check": None,
            "duration_s": res.duration_s, "tool_wall_share": res.tool_wall_share,
            "slow_host": res.timed_out and res.tool_wall_share >= 0.6, "missing_fields": rendered.missing_fields,
        }
        if record["slow_host"]:
            record.update(infra_cause="slow_host", infra_spent=False)
        run: dict[str, Any] = {"cost": self._cost(state, results),
                               "executors": {**((state.get("run") or {}).get("executors") or {}),
                                             ex.name: res.cli_version}}
        if first and unit not in path_units:
            run["path"] = {"units": path_units + [unit]}
        return {"attempts": {unit: record}, "artifacts": {unit: parsed.artifacts or None},
                "values": {unit: parsed.values or None}, "feedback": {unit: None}, "run": run}

    def _previous_unit(self, unit: str, path_units: list[str]) -> str | None:
        before = [p for p in path_units if p != unit]
        return before[-1] if before else None

    def _fields(self, unit: str, state: Mapping[str, Any], attempt: int, visit: int, workdir: Path
                ) -> dict[str, str | None]:
        req = state.get("request") or {}
        out: dict[str, str | None] = {k: str(v) for k, v in (req.get("inputs") or {}).items()}
        ws = state.get("workspace") or {}
        out.update(task_id=self.ctx.task_id, thread_id=self.ctx.thread, workflow=self.ctx.spec.name, unit=unit,
                   attempt=str(attempt), visit=str(visit), branch=ws.get("branch") or gitmod.branch(workdir),
                   base=ws.get("base_branch") or "", workdir=str(workdir), run_label=None)
        for chan in ("artifacts", "values"):
            for vals in (state.get(chan) or {}).values():
                if isinstance(vals, dict):
                    out.update({k: str(v) for k, v in vals.items()})
        return out

    # -- script units (SCR) ------------------------------------------------------------------------

    def _script_unit(self, unit: str, state: RunState) -> dict[str, Any]:
        sc = self.ctx.spec.units[unit].script
        assert sc is not None
        prev = (state.get("attempts") or {}).get(unit) or {}
        attempt = int(prev.get("attempt", 0)) + 1
        workdir = self._workdir(state)
        t0 = time.monotonic()
        artifacts: dict[str, str] = {}
        ok, env, exit_code = True, False, None
        if sc.run:
            out = self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "scripts" / unit / f"{attempt}.out"
            r = run_command(ResolvedCommand(argv=sc.run, prefix=sc.run[0]), workdir, out, sc.timeout_s,
                            main=self.ctx.main_checkout)
            exit_code = r.exit_code
            ok = r.finished and r.exit_code == 0
            env = r.exit_code in sc.environmental_exit_codes or "error" in r.extra
            artifacts = parse_output(Path(out).read_text(encoding="utf-8", errors="replace") if Path(out).exists()
                                     else "", sc.produces).artifacts
        elif sc.call is not None:
            try:
                got = sc.call.resolve()(checkmod.CheckContext(unit=unit, workdir=workdir,
                                                              request=state.get("request") or {}))
                artifacts = {str(k): str(v) for k, v in (got or {}).items()} if isinstance(got, dict) else {}
            except Exception as exc:  # noqa: BLE001
                ok, env = False, True
                artifacts = {}
                self.ctx.log.write("engine_error", unit=unit, error=type(exc).__name__)
        self.ctx.log.write("script", name=sc.name or unit, phase="unit", exit_code=exit_code,
                           duration_s=round(time.monotonic() - t0, 3), environmental=env)
        record = {"attempt": attempt, "visit": 1, "ok": ok, "text": "", "escalate": "environmental" if env else None,
                  "infra_spent": False, "check": None, "script": True}
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        return {"attempts": {unit: record}, "artifacts": {unit: artifacts or None}, "run": run}

    # -- judge -----------------------------------------------------------------------------------

    def judge(self, unit: str, state: RunState) -> dict[str, Any]:
        spec = self.ctx.spec
        u = spec.units[unit]
        g = u.gate
        att = dict((state.get("attempts") or {}).get(unit) or {})
        if att.get("infra_spent") or att.get("escalate"):
            return {"judgements": {unit: {"verdict": str(Verdict.ESCALATE), "reason": att.get("escalate") or "infra",
                                          "confidence": 1.0, "confidence_source": "engine_placeholder"}}}
        if not att.get("ok"):
            return {"judgements": {unit: {"verdict": str(Verdict.RETRY), "reason": "step_failed", "blockers": [
                {"criterion": "step", "problem": att.get("error_kind") or ("timed out" if att.get("timed_out")
                                                                            else "the step failed")}]}}}
        bad = [i for i in att.get("issues") or [] if i.startswith(("value_missing", "value_invalid"))]
        if bad:
            return {"judgements": {unit: {"verdict": str(Verdict.RETRY), "reason": "output_contract", "blockers": [
                {"criterion": "output", "problem": i} for i in bad]}}}
        workdir = self._workdir(state)
        cres, notes = self._check(unit, state, att, workdir)
        att["check"] = checkmod.to_json(cres)
        write: dict[str, Any] = {"attempts": {unit: att}, "facts": {unit: cres.facts or None}}
        self.ctx.log.write("check", unit=unit, result=cres.result, environmental=cres.environmental,
                           evidence=clip(cres.evidence, 200), notes=notes)
        if cres.result == "FAIL":
            if cres.environmental:
                att["escalate"] = "environmental"
                write["judgements"] = {unit: {"verdict": str(Verdict.ESCALATE), "reason": "environmental"}}
            else:
                write["judgements"] = {unit: {"verdict": str(Verdict.RETRY), "reason": "check_fail", "blockers": [
                    {"criterion": f.criterion or "check", "place": f.place, "problem": f.message, "fix": f.fix}
                    for f in cres.findings if f.status == "fail"] or [{"criterion": "check", "problem": "check FAIL"}]}}
            return write
        if g.judge is None:  # a script unit gated by its check alone
            write["judgements"] = {unit: {"verdict": str(Verdict.PROCEED), "reason": "check_only"}}
            return write
        write["judgements"] = {unit: self._judge_session(unit, state, att, cres, workdir)}
        if write["judgements"][unit].get("infra_spent"):
            att["infra_spent"] = True
            att["infra_cause"] = "judge_infra"
        return {**write, "run": {"cost": write["judgements"][unit].pop("_cost")}} if "_cost" in write["judgements"][
            unit] else write

    def _check(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any], workdir: Path
               ) -> tuple[CheckResult, list[str]]:
        u = self.ctx.spec.units[unit]
        facts = {k: v for k, v in (state.get("facts") or {}).items() if k != unit}
        ctx = checkmod.CheckContext(
            unit=unit, workdir=workdir, request=state.get("request") or {}, attempt=int(att.get("attempt", 1)),
            visit=int(att.get("visit", 1)), main_checkout=self.ctx.main_checkout,
            artifacts=state.get("artifacts") or {}, values=state.get("values") or {}, facts=facts,
            git=checkmod.git_facts(workdir, (state.get("workspace") or {}).get("base_commit") or ""),
            criteria=tuple({"id": c.id, "mechanical": c.mechanical} for c in u.gate.criteria),
            allow=tuple(self.ctx.spec.allow_commands),
            out_dir=self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "checks" / unit
            / str(att.get("attempt", 1)))
        return run_in_worker(u.gate, ctx)

    def _judge_session(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any], cres: CheckResult,
                       workdir: Path) -> dict[str, Any]:
        spec = self.ctx.spec
        u = spec.units[unit]
        g = u.gate
        st = u.step
        assert g.judge is not None and st is not None
        j = g.judge
        step_ex = st.executor or spec.default_executor
        judge_name = self.ctx.judges.get(unit) or self.ctx.registry.judge_executor(step_ex, j.executor,
                                                                                  self.ctx.judge_override)
        ex = self.ctx.registry.get(judge_name)
        caps = ex.capabilities()
        from tempergraph.contracts import ToolCall  # local: keeps the module's import list short

        views = view_set(st, [ToolCall(name=t) for t in att.get("tools") or []], caps, j.tools)
        stance, brief = j.stance, j.brief
        if j.file:
            from tempergraph.contracts import TextRef

            stance, brief = split_judge_file(load_text(spec, TextRef(path=j.file)))
        arts = (state.get("artifacts") or {}).get(unit) or {}
        vals = (state.get("values") or {}).get(unit) or {}
        refs: dict[str, str] = {}
        for ref in j.references:
            for chan in ("artifacts", "values"):
                for vs in (state.get(chan) or {}).values():
                    if isinstance(vs, dict) and ref in vs:
                        refs[ref] = str(vs[ref])
        req_text = str(((state.get("request") or {}).get("inputs") or {}).get("request", ""))
        prompt = render_judge(JudgeInputs(
            gate=g, stance=stance, brief=brief, request=req_text, references=refs,
            subject={**{k: str(v) for k, v in arts.items()}, **{k: str(v) for k, v in vals.items()}},
            out_of_reach=[d.capability for d in views.deferred], check=cres, step_account=str(att.get("text") or ""),
            workspace_facts={"branch": gitmod.branch(workdir), "changed": len(gitmod.changed_paths(workdir))},
            feedback=str(((state.get("feedback") or {}).get(unit) or {}).get("text") or ""),
            visit_reason=str(((state.get("visits") or {}).get(unit) or {}).get("reason") or "")))
        ladder = _aliases(st.model)
        profile = _aliases(spec.model_profile.get(f"judge:{unit}"))
        alias = j.model or (profile[0] if profile else None) or (ladder[-1] if ladder else "inherit")
        attempt = int(att.get("attempt", 1))
        key = session_key(unit, attempt, "judge")
        req = SessionRequest(kind="judge", prompt=prompt, workdir=workdir, alias=alias, session_key=key,
                             timeout_s=j.timeout_s or DEFAULT_TIMEOUT_S,
                             session_dir=session_dir(self.ctx.state_root, spec.name, self.ctx.task_id, key))
        before = gitmod.fingerprint(workdir)
        res, results = self._session(ex, req, views)
        all_results = list(results)
        out: dict[str, Any] = {"judge_executor": judge_name, "alias": alias, "views": list(views.tools)}
        if res.infra_cause is not None:
            out.update(verdict=str(Verdict.ESCALATE), infra_spent=True, reason="judge_infra")
            out["_cost"] = self._cost(state, all_results)
            return out
        judgement = None
        if not res.timed_out:
            try:
                judgement = parse_judgement(res.text, g)
            except Unparsed:
                rkey = session_key(unit, attempt, "judge_reask")
                rreq = SessionRequest(kind="judge_reask", prompt=reask_prompt(res.text, g), workdir=workdir,
                                      alias=alias, session_key=rkey, timeout_s=req.timeout_s,
                                      session_dir=session_dir(self.ctx.state_root, spec.name, self.ctx.task_id, rkey))
                res2, r2 = self._session(ex, rreq, views)
                all_results += r2
                try:
                    judgement = parse_judgement(res2.text, g)
                except Unparsed:
                    judgement = None
        after = gitmod.fingerprint(workdir)
        gr = guard(views, res.tool_calls, before, after, workspace_mode=(state.get("workspace") or {}).get(
            "mode", "in_place"), step_session_id=att.get("session_id"), judge_session_id=res.session_id,
            reports_actions=caps.reports_actions)
        if gr.status == "discarded":
            judgement = None
        back_units: dict[str, str] = {}
        for target in flow.effective_order(spec):
            if target in g.back_targets:
                tu = spec.units[target]
                for k in (tu.step.produces if tu.step else {}):
                    back_units[k] = target
        outcome = derive(judgement, g, cres, back_units)
        if judgement is None and gr.status == "discarded":
            outcome.reason = f"guard:{gr.reason}"
        self.ctx.log.write("judgement", unit=unit, statuses=outcome.statuses, blockers=[
            b["criterion"] for b in outcome.blockers], confidence=outcome.confidence,
            confidence_source=outcome.confidence_source, gap=outcome.gap, guard=gr.status, views=list(views.tools),
            judge_executor=judge_name)
        out.update(outcome.to_json())
        out["guard"] = gr.status
        out["_cost"] = self._cost(state, all_results)
        return out

    # -- gate, human, finalizer --------------------------------------------------------------------

    def gate(self, unit: str, state: RunState) -> dict[str, Any]:
        w = gatemod.decide(self.ctx.spec, unit, state, self.ctx.task_id)
        r = w["route"][unit]
        self.ctx.log.write("gate", unit=unit, verdict=((state.get("judgements") or {}).get(unit) or {}).get("verdict"),
                           token=r["token"], route_target=r["node"])
        if unit in (w.get("pause") or {}) and w["pause"][unit]:
            p = w["pause"][unit]
            self.ctx.log.write("pause", unit=unit, pause_kind=p["kind"], decisions=p["decisions"], resume=p["resume"])
        return w

    def human(self, unit: str, state: RunState, decision: Any) -> dict[str, Any]:
        payload = decision if isinstance(decision, dict) else {"decision": str(decision)}
        w = gatemod.apply_decision(self.ctx.spec, unit, state, payload)
        self.ctx.log.write("human", unit=unit, decision=payload.get("decision"), caller=payload.get("caller"),
                           feedback=bool(payload.get("feedback")))
        return w

    def finalizer(self, state: RunState) -> dict[str, Any]:
        from tempergraph.run.finalize import run_finalizer

        result = run_finalizer(self.ctx, state)
        self.ctx.log.write("finalize", **result)
        return {"finalized": {"done": True, **result}}


def _entered_from(state: Mapping[str, Any], unit: str) -> str:
    """EVT §2.2 `entered_from`: `start`, `proceed`, `back:<unit>`, `rewind:<unit>` or `resume`."""
    v = (state.get("visits") or {}).get(unit) or {}
    if v.get("entered_from"):
        return str(v["entered_from"])
    if int(v.get("visit", 1)) > 1 and v.get("from"):
        return f"back:{v['from']}"
    path = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
    return "proceed" if path else "start"

