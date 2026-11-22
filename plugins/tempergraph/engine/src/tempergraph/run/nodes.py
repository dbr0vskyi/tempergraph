"""The node bodies the compiler wires into the graph (CMP `UnitNodes`): step, judge, gate, human, finalizer.

The step and judge nodes are the only places a model session starts (OVR-B3); the gate is pure;
the human node's interrupt is the compiler's. Budgets follow BUD-B1, BUD-B11: the cause picks the counter.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import threading
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
    MapItem,
    MeasureContext,
    ScriptSpec,
    SessionOptions,
    SessionRequest,
    SessionResult,
    UnitSpec,
    Verdict,
    WorkflowSpec,
)
from tempergraph.executors.launcher import StopRequest
from tempergraph.executors.registry import Registry
from tempergraph.improve import lessons as lessonsmod
from tempergraph.model import flow
from tempergraph.model.text import load_text, split_judge_file
from tempergraph.render.output import parse_output
from tempergraph.render.prompt import AttemptContext, Blocker, render_step
from tempergraph.run import checks as checkmod
from tempergraph.run import complexity, mapping, reserve, tool_access
from tempergraph.run import gate as gatemod
from tempergraph.run import ladder as laddermod
from tempergraph.run.check_worker import run_in_worker
from tempergraph.run.commands import ResolvedCommand, run_command
from tempergraph.run.commands import expand as expand_commands
from tempergraph.run.guard import guard, view_set
from tempergraph.run.judging import (
    CLAIM_CRITERION_ID,
    JudgeInputs,
    Unparsed,
    brief_digest,
    claim_criterion,
    criteria_digest,
    derive,
    judged,
    parse_judgement,
    reask_prompt,
    render_judge,
)
from tempergraph.run.log import CostTotals, RunLog, cost_so_far, estimate, session_sink
from tempergraph.security.scrub import clip, scrub
from tempergraph.settings import Capture
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
    backoff_max_s: int = 300
    settings: Mapping[str, Any] = field(default_factory=dict)  # workflow-declared settings (RST-B25)
    capture: Capture = field(default_factory=Capture)  # the operator's capture level (LOS-B17)
    main_checkout: Path | None = None
    attempts_started: int = 0
    origin: str = "cli"
    stage: str = "local-dev"  # PRO-B7, PRO-B4
    judge_state: Callable[[str], str] | None = None  # a gate's judge binding state (JCL-B17); None reads it
    escalation_record: Callable[[str], bool] | None = None  # LAD-B13; None reads the ledger
    self_check_limit: int = 3  # CHK-B17

    @property
    def thread(self) -> str:
        return f"{self.spec.name}/{self.task_id}"


def _aliases(v: object) -> list[str]:
    if v is None:
        return []
    return [v] if isinstance(v, str) else [str(x) for x in v]  # type: ignore[attr-defined]


class EngineNodes:
    def __init__(self, ctx: RunContext) -> None:
        self._deferred: list[dict[str, Any]] = []
        self._deferred_lock = threading.Lock()
        self.ledger = reserve.Ledger()  # what each running session of a parallel block holds (BUD-B12)
        self.ctx = ctx

    # -- helpers ---------------------------------------------------------------------------------

    def defer(self, update: Mapping[str, Any]) -> None:
        """A state write the runner could not make before the graph ran, because several nodes are pending
        (branches of a parallel block): the first node to finish carries it."""
        with self._deferred_lock:
            self._deferred.append(dict(update))

    def settle(self, w: dict[str, Any]) -> dict[str, Any]:
        with self._deferred_lock:
            held, self._deferred = self._deferred, []
        for update in held:
            for ch, val in update.items():
                w[ch] = {**val, **w[ch]} if isinstance(val, dict) and isinstance(w.get(ch), dict) else \
                    w.get(ch, val) if ch in w else val
        return w

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

    def _hold(self, unit: str, state: Mapping[str, Any]) -> dict[str, Any] | None:
        """What a session of `unit` needs to take a reservation (BUD-B12): only a branch of a parallel block, in
        a run with a cost cap. Units outside a block run one session at a time and keep the BUD-B9 check."""
        spec = self.ctx.spec
        cap = spec.run_cost_cap_usd
        block = flow.block_of(spec, unit)
        if cap is None or block is None:
            return None
        totals = CostTotals.from_json((state.get("run") or {}).get("cost"))
        return {"cap": float(cap), "width": len(spec.units[block].branches), "snapshot": totals.sessions,
                "spent": totals.figure()}

    def _session(self, ex: Executor, req: SessionRequest, judge_views: Any = None,
                 lessons_digest: str | None = None, extra: Mapping[str, Any] | None = None,
                 hold: Mapping[str, Any] | None = None) -> tuple[SessionResult, list]:
        """One session with infra tries and backoff outside the retry budget (BUD-B1, JDG-B5). With `hold`, each
        try takes a reservation first and gives it back, replaced by its real cost, when it ends (BUD-B12)."""
        results: list[SessionResult] = []
        if req.kind in ("step", "retry"):  # the rendered prompt, kept local for the session review (SRV-B17)
            from tempergraph.improve.record import write_prompt

            write_prompt(self.ctx.state_root, self.ctx.spec.name, self.ctx.task_id, req.session_key, req.prompt)
        key = req.session_key
        for n in range(self.ctx.infra_tries):
            if hold is not None:
                reason = self.ledger.acquire(
                    key, snapshot=hold["snapshot"], spent_usd=hold["spent"], cap_usd=hold["cap"],
                    amount=lambda spent: reserve.session_amount(req.options.cost_cap_usd, hold["cap"], spent,
                                                                hold["width"]),
                    write=lambda action, **fig: self.ctx.log.write("reservation", action=action, session_key=key,
                                                                   **fig),
                    drain=self.ctx.drain_requested)
                if reason:
                    raise Drain(reason)
            try:
                sink = session_sink(self.ctx.log, req, ex.name, tool_inputs=self.ctx.capture.tool_inputs)
                self.ctx.log.write("attempt_start", session_key=req.session_key, kind=req.kind, executor=ex.name,
                                   alias=req.alias, timeout_s=req.timeout_s,
                                   prompt_digest=hashlib.sha256((req.prompt or "").encode()).hexdigest()[:16],
                                   **{k: extra[k] for k in ("sources", "ladder") if extra and k in extra})
                try:
                    if judge_views is None:
                        res = ex.run_step(req, sink)
                    else:
                        res = ex.run_judge(req, judge_views, sink)
                finally:
                    sink.close()
                    if not self.ctx.capture.raw and req.session_dir is not None:  # `observe.raw = off` (LOS-B17)
                        with contextlib.suppress(OSError):
                            (req.session_dir / "raw.jsonl").unlink(missing_ok=True)
                if res.usage.estimated_cost_usd is None:
                    res.usage.estimated_cost_usd = estimate(res.usage, res.model)
                results.append(res)
                self.ctx.log.write("agent_run", session_key=req.session_key, kind=req.kind, executor=ex.name,
                                   alias=req.alias, usage=res.usage, ok=res.ok,
                                   tools=[c.name for c in res.tool_calls],
                                   cli_version=res.cli_version, session_id=res.session_id,
                                   unknown_tools=sorted({c.name for c in res.tool_calls
                                                         if not ex.capabilities().knows_tool(c.name)}),
                                   infra_cause=str(res.infra_cause) if res.infra_cause else None,
                                   error_kind=res.error_kind, timed_out=res.timed_out, stalled=res.stalled,
                                   duration_s=res.duration_s, tool_wall_share=res.tool_wall_share,
                                   slow_host=bool(res.timed_out and res.tool_wall_share >= 0.6),
                                   **({"lessons_digest": lessons_digest} if lessons_digest else {}),
                                   **dict(extra or {}))
                if hold is not None:
                    spent = CostTotals()
                    spent.add(res.usage)
                    self.ledger.release(key, snapshot=hold["snapshot"], real_usd=spent.figure())
            finally:
                if hold is not None:
                    self.ledger.release(key, snapshot=hold["snapshot"], real_usd=0.0)  # a no-op once released
            if res.infra_cause is None or n + 1 >= self.ctx.infra_tries:
                break
            self.ctx.sleep(min(BACKOFF_S[min(n, len(BACKOFF_S) - 1)], self.ctx.backoff_max_s))
        return results[-1], results

    def _cost(self, state: Mapping[str, Any], results: list[SessionResult]) -> dict[str, Any]:
        totals = CostTotals.from_json((state.get("run") or {}).get("cost"))
        base = dict(totals.to_json()["counters"])  # what this writer read: the reducer adds only its delta
        for r in results:
            totals.add(r.usage)
        return {**totals.to_json(), "_base": base}

    # -- step ------------------------------------------------------------------------------------

    def step(self, unit: str, state: RunState) -> dict[str, Any]:
        spec = self.ctx.spec
        u = spec.units[unit]
        self._boundary(state)
        if u.kind == "script":
            return self._script_unit(unit, state)
        if u.kind in ("route", "switch"):
            return self._flow_unit(unit, state)
        if u.kind in ("ask", "wait"):
            return self._person_unit(unit, state)
        if u.kind == "parallel":
            return self._join_unit(unit, state)
        if u.extra.get("outcome"):
            return self._outcome_step(unit, state)
        st = u.step
        assert st is not None
        prev = (state.get("attempts") or {}).get(unit) or {}
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        counters = (state.get("counters") or {}).get(unit) or {}
        entered = prev.get("visit") != visit
        workdir = self._workdir(state)
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        if entered:
            fp = gitmod.fingerprint(workdir)
            self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                               entered_from=_entered_from(state, unit))
        item: dict[str, Any] | None = None
        maps: dict[str, Any] = {}
        if u.map is not None:  # the list is read once per visit; the item in hand is the first not passed
            done, m, item = self._map_item(unit, state, visit, workdir, prev, path_units)
            if done is not None:
                return done
            assert item is not None
            maps = {unit: m}
        iid = item["id"] if item else None
        first = entered or prev.get("item") != iid
        attempt = int(item["attempt"]) if item else int(prev.get("attempt", 0)) + 1
        self.ctx.attempts_started += 1
        ov, layer = gatemod.arm_overrides(spec, unit, state)  # below the operator layers (SWM-B6, RST-B22, RST-B23)
        ov = {k: v for k, v in ov.items() if k in ("model", "timeout_s", "idle_s", "effort")
              and k not in (u.extra.get("operator_set") or ())}
        sources = {k: layer for k in ov}
        # one alias per attempt: release 1's retry-count list is retired (LAD-B18) and validation refuses it
        alias = (_aliases(ov.get("model")) or _aliases(st.model) or _aliases(spec.model_profile.get(unit)) or ["inherit"])[0]
        full_ov, _ = gatemod.arm_overrides(spec, unit, state)
        rungs, pinned = laddermod.rungs_of(u, full_ov)
        rung = laddermod.held_rung(counters, visit, iid) if rungs and not pinned else 0
        climb: dict[str, Any] | None = None
        if rungs and not pinned:  # the effort of this attempt is its rung's (LAD-B9); a pin switches it off
            ov["effort"] = rungs[rung]
            sources["effort"] = f"ladder:effort[{rung}]"
        held = counters.get("ladder") or {}
        up = held.get("escalate") if held.get("visit") == visit and held.get("item") == iid and not first else None
        if up:  # LAD-B12: one attempt on the tier above, at the escalation's effort
            alias = str(up["to"])
            sources["model"] = "escalation:+1"
            if up.get("effort"):
                ov["effort"] = up["effort"]
                sources["effort"] = "escalation:+1"
        if item and u.map is not None and u.map.item_model is not None:
            try:
                chosen = str(u.map.item_model.resolve()(MapItem(id=item["id"], text=item["text"])))
            except Exception as exc:  # noqa: BLE001 - a workflow fault, recorded
                chosen = f"<{type(exc).__name__}>"
            if chosen not in u.map.models:  # MAP-B8, MAP-B10, MAP-B9: the attempt fails before launch
                self.ctx.log.write("engine_error", unit=unit, item=iid, error="item_model",
                                   detail=f"{chosen!r} is not one of {list(u.map.models)}")
                record: dict[str, Any] = {
                    "attempt": attempt, "visit": visit, "item": iid, "ok": False, "text": "", "issues": [],
                          "tools": [], "session_id": None, "error_kind": "item_model", "infra_spent": False,
                          "check": None, "escalate": "workflow_fault", "timed_out": False}
                return {"attempts": {unit: record}, "maps": maps}
            alias = chosen
        ex = self.ctx.registry.get(st.executor or spec.default_executor)
        caps = ex.capabilities()
        fields = self._fields(unit, state, attempt, visit, workdir)
        if item:  # VAL-B8 item keys
            fields.update(item_id=item["id"], item_index=str(item["index"]), item_count=str(item["count"]),
                          item=item["text"])
        failed, env, hybrid = self._scripts(st.before, unit, attempt, "before", state, workdir)
        fields.update(hybrid)  # a `before` script's keys are the session's to read (SCR-B5)
        if failed is not None:
            return self._script_failed(unit, state, attempt, visit, failed, env, path_units, first, hybrid)
        judged = (state.get("judgements") or {}).get(unit) or {}
        fb = (state.get("feedback") or {}).get(unit) or {}
        retry = not first and bool(prev)
        prev_unit = self._previous_unit(unit, path_units)
        prev_judged = ((state.get("judgements") or {}).get(prev_unit) or {}) if prev_unit else {}
        notes = tuple(prev_judged.get("notes") or ()) if first else ()
        lessons_text = lessonsmod.block(lessonsmod.load(spec, unit))
        ctx = AttemptContext(
            template=load_text(spec, st.prompt), fields=fields, attempt=attempt, retry=retry, lessons=lessons_text,
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
            rulings=tuple(gatemod.active_rulings(spec, state, unit)),
            upstream_targets=tuple(u.gate.back_targets))
        commands = expand_commands(st.commands, workdir)  # `@repository`: what the repository declares (CHK-B11)
        shown = u if commands == tuple(st.commands) else dataclasses.replace(
            u, step=dataclasses.replace(st, commands=commands))
        ticket: str | None = None
        if st.self_check and u.gate.check is not None:  # CHK-B17: a ticket for this attempt only
            from tempergraph.run import selfcheck

            ticket = selfcheck.issue(
                self.ctx.state_root, u.gate,
                self._check_context(unit, state, {"item": iid, "attempt": attempt, "visit": visit}, workdir,
                                    sub="-preview"), thread=self.ctx.thread, limit=self.ctx.self_check_limit)
            ctx = dataclasses.replace(ctx, self_check=selfcheck.command(ticket))
        rendered = render_step(unit, shown, ctx, caps)
        key = session_key(unit, attempt, "retry" if retry else "step", item=iid)
        req = SessionRequest(
            kind="retry" if retry else "step", prompt=rendered.text, workdir=workdir, alias=alias, session_key=key,
            tools=tuple(st.tools), commands=(*commands, *([ctx.self_check] if ctx.self_check else [])),
            timeout_s=ov.get("timeout_s") or st.timeout_s or DEFAULT_TIMEOUT_S,
            idle_s=ov.get("idle_s") or st.idle_s,
            options=dataclasses.replace(st.session_options or SessionOptions(),
                                        **({"effort": ov["effort"]} if "effort" in ov else {})),
            session_dir=session_dir(self.ctx.state_root, spec.name, self.ctx.task_id, key),
            enforce_tools=self.ctx.enforce_tools, in_engine_worktree=self._in_worktree(state),
            plugin_dir=spec.package_root)
        if rungs or up or laddermod.escalation_of(u, full_ov) is not None:
            last = (counters.get("ladder") or {}) if not first else {}
            climb = {"rung": rung, "effort": req.options.effort, "alias": alias,
                     "source": "escalation:+1" if up else "operator" if pinned else f"ladder:effort[{rung}]"
                     if rungs else "declared",
                     "evidence": last.get("evidence"), "held_by": last.get("held_by")}
            if up:
                climb["taken_by"] = up.get("taken_by")
        extra: dict[str, Any] = {"sources": sources} if sources else {}
        if climb:
            extra["ladder"] = climb
        before = gitmod.fingerprint(workdir)
        try:
            res, results = self._session(ex, req, lessons_digest=lessonsmod.digest(lessons_text),
                                         extra=extra or None, hold=self._hold(unit, state))
        finally:
            if ticket is not None:  # the ticket ends with its attempt; one record a preview (CHK-B17 Record)
                from tempergraph.run import selfcheck

                for call in selfcheck.close(self.ctx.state_root, ticket):
                    self.ctx.log.write("self_check", unit=unit, item=iid, attempt=attempt, result=call.get("result"),
                                       findings=call.get("findings"), duration_s=call.get("duration_s"))
        after = gitmod.fingerprint(workdir)
        parsed = parse_output(res.text, st.produces, tuple(u.gate.back_targets))
        after_failed, after_env = None, False
        if res.ok and st.after:
            after_failed, after_env, after_arts = self._scripts(st.after, unit, attempt, "after", state, workdir)
            hybrid.update(after_arts)
        escalate: str | None = None
        reach = tool_access.refused(unit, st, caps, res.denied, res.tools_at_start)
        if res.error_kind in ("auth", "refused"):
            escalate = res.error_kind
        elif reach and (not res.ok or parsed.blocked):
            escalate = "tool_access"  # no retry spent; the pause offers the grants (BUD-B1, BUD-B11, RST-B28, RST-B29, RST-B30)
        elif parsed.blocked:
            escalate = "blocked"
        elif parsed.upstream:
            escalate = "upstream"
        record = {
            "item": iid,
            "attempt": attempt, "visit": visit, "ok": res.ok, "text": clip(scrub(res.text), 8000), "blocked": parsed.blocked, "upstream": parsed.upstream,
            "issues": parsed.issues, "infra_cause": str(res.infra_cause) if res.infra_cause else None,
            "infra_spent": res.infra_cause is not None, "timed_out": res.timed_out, "stalled": res.stalled,
            "error_kind": res.error_kind, "denied": list(res.denied), "tools": [c.name for c in res.tool_calls],
            "tool_access": reach,
            "session_id": res.session_id, "executor": ex.name, "alias": alias, "model": res.model,
            "changed": before != after, "escalate": escalate, "cut_off": res.partial, "check": None,
            "duration_s": res.duration_s, "tool_wall_share": res.tool_wall_share,
            "slow_host": res.timed_out and res.tool_wall_share >= 0.6, "missing_fields": rendered.missing_fields,
        }
        esc_spec = laddermod.escalation_of(u, full_ov)
        if up:
            record.update(escalated=True, escalated_to=alias)
        elif esc_spec is not None:  # E6: what this attempt's tokens would cost one tier up (OBS-B10 to OBS-B13 prices)
            priced = estimate(res.usage, laddermod.TIER_FAMILY.get(laddermod.tier(esc_spec.to)))
            usages = [*(prev.get("up_estimates") or [])] if not first else []
            record["up_estimates"] = [*usages, priced][-5:]
        if record["slow_host"]:
            record.update(infra_cause="slow_host", infra_spent=False)
        if res.ok and before != after and flow.block_of(spec, unit):  # WSP-B11, WSP-B12: a branch is read-only
            record.update(ok=False, error_kind="branch_changed_the_workspace")
        if after_failed is not None:
            record.update(ok=False, error_kind=f"script_failed:{after_failed}",
                          escalate="environmental" if after_env else record["escalate"])
        run: dict[str, Any] = {"cost": self._cost(state, results),
                               "executors": {**((state.get("run") or {}).get("executors") or {}),
                                             ex.name: res.cli_version}}
        if entered and unit not in path_units:
            run["path"] = {"units": path_units + [unit]}
        arts: dict[str, Any] = {**hybrid, **parsed.artifacts}
        vals: dict[str, Any] = dict(parsed.values)
        if iid:  # an item's keys are kept as `<key>[<item id>]`; the plain key is the item in hand (MAP-B8, MAP-B9, MAP-B10)
            arts.update({mapping.item_key(k, iid): v for k, v in list(arts.items())})
            vals.update({mapping.item_key(k, iid): v for k, v in list(vals.items())})
            return {"attempts": {unit: record}, "artifacts": {unit: arts} if arts else {},
                    "values": {unit: vals} if vals else {}, "run": run, "maps": maps}
        return {"attempts": {unit: record}, "artifacts": {unit: arts or None},
                "values": {unit: vals or None}, "run": run}  # feedback is cleared at the gate

    def _map_item(self, unit: str, state: Mapping[str, Any], visit: int, workdir: Path, prev: Mapping[str, Any],
                  path_units: list[str]) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any] | None]:
        """Fan-out at the start of a visit, then the item in hand (MAP-B8, MAP-B9, MAP-B10). Returns a finished state write
        when the list stops or skips the map, else the `maps` record and the item with its attempt number."""
        m = mapping.record(state, unit)
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        base = {"attempt": int(prev.get("attempt", 0)) + 1, "visit": visit, "ok": True, "text": "", "issues": [],
                "tools": [], "session_id": None, "escalate": None, "infra_spent": False, "check": None,
                "item": None, "timed_out": False}
        if m.get("visit") != visit:
            try:
                items = mapping.read_items(self.ctx.spec, unit, state, workdir)
            except mapping.MapFault as exc:
                self.ctx.log.write("map_items", unit=unit, visit=visit, count=exc.count, ids=[], error=exc.code,
                                   detail=str(exc))
                return ({"attempts": {unit: {**base, "ok": False, "map_fault": f"{unit}: {exc}"}}, "run": run},
                        m, None)
            m = {"visit": visit, "items": [{"id": i.id, "text": i.text} for i in items], "passed": [],
                 "attempts": dict(m.get("attempts") or {})}
            self.ctx.log.write("map_items", unit=unit, visit=visit, count=len(items), ids=[i.id for i in items])
            if not items:  # `on_empty: skip` passes the map with no item
                return {"attempts": {unit: {**base, "map_skip": True}}, "maps": {unit: m}, "run": run}, m, None
        item = mapping.pending(m)
        if item is None:  # every item passed already (a resume at the gate): nothing to run
            return {"attempts": {unit: {**dict(prev), "visit": visit}}, "maps": {unit: m}, "run": run}, m, None
        n = int((m.get("attempts") or {}).get(item["id"], 0)) + 1
        m["attempts"] = {**(m.get("attempts") or {}), item["id"]: n}
        return None, m, {**item, "attempt": n}

    def _script_failed(self, unit: str, state: Mapping[str, Any], attempt: int, visit: int, name: str, env: bool,
                       path_units: list[str], first: bool, arts: dict[str, str]) -> dict[str, Any]:
        """A failed `before` script fails the attempt with no session (SCR-B7, SCR-B2)."""
        record = {"attempt": attempt, "visit": visit, "ok": False, "text": "", "issues": [], "tools": [],
                  "session_id": None, "error_kind": f"script_failed:{name}", "infra_spent": False, "check": None,
                  "escalate": "environmental" if env else None, "timed_out": False}
        run = {"path": {"units": path_units + [unit]}} if first and unit not in path_units else {}
        return {"attempts": {unit: record}, "artifacts": {unit: arts or None}, "run": run}

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

    def _run_script(self, sc: ScriptSpec, unit: str, attempt: int, phase: str, state: Mapping[str, Any],
                    workdir: Path) -> tuple[bool, bool, dict[str, str]]:
        """One script through the command runner or its callable (SCR-B5); returns ok, environmental, artifacts."""
        t0 = time.monotonic()
        artifacts: dict[str, str] = {}
        ok, env, exit_code = True, False, None
        name = sc.name or (sc.run[0] if sc.run else unit)
        if sc.run:
            tag = unit if phase == "unit" else f"{unit}.{phase}.{name}"
            out = self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "scripts" / tag / f"{attempt}.out"
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
                self.ctx.log.write("engine_error", unit=unit, error=type(exc).__name__)
        self.ctx.log.write("script", unit=unit, name=name, phase=phase, exit_code=exit_code,
                           command_prefix=sc.run[0] if sc.run else None, duration_s=round(time.monotonic() - t0, 3), environmental=env, cached=False)
        return ok, env, artifacts

    def _scripts(self, scripts: tuple[ScriptSpec, ...], unit: str, attempt: int, phase: str,
                 state: Mapping[str, Any], workdir: Path) -> tuple[str | None, bool, dict[str, str]]:
        """Hybrid `before` or `after` scripts in declaration order; the first failure ends the phase."""
        arts: dict[str, str] = {}
        for sc in scripts:
            ok, env, got = self._run_script(sc, unit, attempt, phase, state, workdir)
            arts.update(got)
            if not ok:
                return sc.name or (sc.run[0] if sc.run else phase), env, arts
        return None, False, arts

    def _script_unit(self, unit: str, state: RunState) -> dict[str, Any]:
        sc = self.ctx.spec.units[unit].script
        assert sc is not None
        prev = (state.get("attempts") or {}).get(unit) or {}
        attempt = int(prev.get("attempt", 0)) + 1
        ok, env, artifacts = self._run_script(sc, unit, attempt, "unit", state, self._workdir(state))
        record = {"attempt": attempt, "visit": 1, "ok": ok, "text": "", "escalate": "environmental" if env else None,
                  "infra_spent": False, "check": None, "script": True}
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        return {"attempts": {unit: record}, "artifacts": {unit: artifacts or None}, "run": run}

    def _flow_unit(self, unit: str, state: RunState) -> dict[str, Any]:
        """A route or switch unit runs no session: its pick is made in the gate node (CMP-B10 to CMP-B16)."""
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        record: dict[str, Any] = {"attempt": 1, "visit": visit, "ok": True, "text": "", "escalate": None,
                                  "infra_spent": False, "check": None, "flow": True}
        sw = self.ctx.spec.units[unit].switch
        if sw is not None and sw.complexity is not None:
            prev = ((state.get("attempts") or {}).get(unit) or {}).get("complexity")
            record["complexity"] = prev or self._complexity(unit, state)  # once per run (CXR-B7)
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        return {"attempts": {unit: record}, "run": run}

    def _join_unit(self, unit: str, state: RunState) -> dict[str, Any]:
        """A parallel block's join runs nothing: every branch has passed when this node starts (CMP-B4)."""
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        prev = (state.get("attempts") or {}).get(unit) or {}
        if prev.get("visit") != visit:
            fp = gitmod.fingerprint(self._workdir(state))
            self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                               entered_from="join", branches=list(self.ctx.spec.units[unit].branches))
        record = {"attempt": int(prev.get("attempt", 0)) + 1, "visit": visit, "ok": True, "text": "",
                  "escalate": None, "infra_spent": False, "check": None, "join": True}
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        return {"attempts": {unit: record}, "run": run}

    def _person_unit(self, unit: str, state: RunState) -> dict[str, Any]:
        """An ask or a wait runs nothing: its step node records the entry and the human node pauses (CMP-B10 to CMP-B16).
        An ask reads its questions here, once per visit, and starts the visit with no answers (ASK-B2)."""
        from tempergraph.run import asking

        u = self.ctx.spec.units[unit]
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        prev = (state.get("attempts") or {}).get(unit) or {}
        workdir = self._workdir(state)
        if prev.get("visit") != visit:
            fp = gitmod.fingerprint(workdir)
            self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                               entered_from=_entered_from(state, unit))
        record: dict[str, Any] = {"attempt": int(prev.get("attempt", 0)) + 1, "visit": visit, "ok": True, "text": "",
                                  "escalate": None, "infra_spent": False, "check": None, u.kind: True}
        if u.ask is not None:
            folder = self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id
            with contextlib.suppress(OSError):
                asking.answers_path(folder, unit).unlink()
            try:
                record["questions"] = [asking.to_json(q) for q in asking.questions(u.ask, state, workdir)]
            except asking.AskFault as exc:
                record.update(ok=False, ask_fault=str(exc))
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        return {"attempts": {unit: record}, "artifacts": {unit: None}, "values": {unit: None}, "run": run}

    def _escalation_facts(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any],
                          write: Mapping[str, Any]) -> dict[str, Any]:
        """What the gate cannot read from state for E1, E6 and E7 (LAD-B12): the stage, whether the escalation
        record is met, the median estimate of one attempt on the tier above and what the run cost cap leaves."""
        ctx = self.ctx
        met = ctx.escalation_record or (lambda u: laddermod.record_met(ctx.state_root, ctx.spec.name,
                                                                         ctx.spec.version, u))
        try:
            record_met = bool(met(unit))
        except Exception:  # noqa: BLE001 - LAD-B14: a record that cannot be read is not met
            record_met = False
        known = sorted(float(x) for x in att.get("up_estimates") or [] if isinstance(x, int | float))
        estimate_usd = known[len(known) // 2] if known and len(known) == len(att.get("up_estimates") or []) else None
        cap = ctx.spec.run_cost_cap_usd
        cost = (write.get("run") or {}).get("cost") or write["judgements"][unit].get("_cost") or (
            state.get("run") or {}).get("cost")
        left = round(float(cap) - CostTotals.from_json(cost).figure(), 6) if cap is not None else None
        return {"stage": ctx.stage, "record_met": record_met, "estimate_usd": estimate_usd, "cap_left_usd": left}

    def _judge_state(self) -> Callable[[str], str]:
        if self.ctx.judge_state is None:
            from tempergraph.improve import calibration

            self.ctx.judge_state = calibration.state_name_for(self.ctx.spec, self.ctx.state_root)
        return self.ctx.judge_state

    def _complexity(self, unit: str, state: Mapping[str, Any]) -> dict[str, Any]:
        """CXR-B9, CXR-B10, CXR-B1: the measures, the rules in force and the zone, evaluated in the switch's step node."""
        ctx = self.ctx
        workdir = self._workdir(state)
        maps = (dict, Mapping)
        mctx = MeasureContext(
            request=dict(state.get("request") or {}),
            facts={u: dict(f) for u, f in (state.get("facts") or {}).items() if isinstance(f, maps)},
            artifacts={u: dict(a) for u, a in (state.get("artifacts") or {}).items() if isinstance(a, maps)},
            settings=dict(ctx.settings), stage=ctx.stage, workdir=workdir,
            git=checkmod.git_facts(workdir, (state.get("workspace") or {}).get("base_commit") or ""))
        return complexity.evaluate(ctx.spec, unit, state, mctx, state_root=ctx.state_root, thread=ctx.thread,
                                   origin=ctx.origin,
                                   recent=complexity.explored_recent(ctx.state_root, ctx.spec.name, unit))

    # -- judge -----------------------------------------------------------------------------------

    def _outcome_step(self, unit: str, state: RunState) -> dict[str, Any]:
        """OUT-B15, OUT-B16, OUT-B17: no session; the subject is final state, recorded for the judge and the record."""
        prev = (state.get("attempts") or {}).get(unit) or {}
        visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
        attempt = int(prev.get("attempt", 0)) + 1
        path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        if prev.get("visit") != visit:
            fp = gitmod.fingerprint(self._workdir(state))
            self.ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                               entered_from=_entered_from(state, unit))
        o = self.ctx.spec.outcome
        record = {"attempt": attempt, "visit": visit, "ok": True, "text": "", "issues": [], "tools": [],
                  "session_id": None, "escalate": None, "infra_spent": False, "check": None,
                  "deliverables": [dict(d) for d in (o.deliverables if o else ())]}
        run = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
        return {"attempts": {unit: record}, "run": run}

    def judge(self, unit: str, state: RunState) -> dict[str, Any]:
        w = self._judge(unit, state)
        if self.ctx.spec.units[unit].extra.get("outcome"):
            w = self._route_outcome(unit, state, w)
        return w

    def _route_outcome(self, unit: str, state: RunState, w: dict[str, Any]) -> dict[str, Any]:
        """A failing outcome gate goes back to the earliest serving unit on the path, else escalates (OUT-B15, OUT-B16, OUT-B17)."""
        from tempergraph.run.outcome import derived_back

        j = dict((w.get("judgements") or {}).get(unit) or {})
        if j.get("verdict") not in (str(Verdict.RETRY), str(Verdict.BACK)):
            return w
        o = self.ctx.spec.outcome
        finals = [str(c.id) for c in (o.final if o else ())]
        failing = [b.get("criterion") for b in j.get("blockers") or [] if b.get("criterion") in finals] or finals
        path = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
        target = derived_back(self.ctx.spec, failing, path)
        if target:
            j.update(verdict=str(Verdict.BACK), back_to=target, reason="outcome_serves")
        else:
            j.update(verdict=str(Verdict.ESCALATE), reason="outcome_no_serving_unit")
        return {**w, "judgements": {**(w.get("judgements") or {}), unit: j}}

    def _judge(self, unit: str, state: RunState) -> dict[str, Any]:
        spec = self.ctx.spec
        u = spec.units[unit]
        g = u.gate
        att = dict((state.get("attempts") or {}).get(unit) or {})
        if att.get("map_fault"):
            return {"judgements": {unit: {"verdict": str(Verdict.ESCALATE), "reason": "map_fault"}}}
        if u.kind in ("ask", "wait"):  # no model and no judge: the person's input is the bar (ASK, WFM-B4)
            return {"judgements": {unit: {"verdict": str(Verdict.ESCALATE), "reason": u.kind}}}
        if att.get("map_skip"):
            return {"judgements": {unit: {"verdict": str(Verdict.PROCEED), "reason": "map_empty"}}}
        if (att.get("escalate") == "upstream" and att.get("upstream") and att.get("ok") and g.judge is not None
                and not att.get("infra_spent")):
            return self._judge_claim(unit, state, att)
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
        iid = att.get("item")
        facts: dict[str, Any] = dict(cres.facts or {})
        if iid:
            facts.update({mapping.item_key(k, str(iid)): v for k, v in list(facts.items())})
        write: dict[str, Any] = {"attempts": {unit: att},
                                 "facts": {unit: facts} if iid and facts else {} if iid else {unit: facts or None}}
        self.ctx.log.write("check", unit=unit, item=iid, attempt=att.get("attempt") if iid else None,  # per item
                           result=cres.result, environmental=cres.environmental,
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
        if u.step is not None and (u.step.effort_ladder or u.step.escalation is not None or any(
                sw.switch is not None and unit in sw.switch.rearm_units() for sw in spec.units.values())):
            level = (write["judgements"][unit].get("risk") or {}).get("level")  # a level is its own binding
            g_names = [lv.name for lv in g.judge.risk.levels] if g.judge.risk is not None else []
            raised = level in g_names[1:]
            # the gate reads trust from the judgement (LAD-B10)
            state_of = self._judge_state()(f"{unit}@{level}" if raised else unit)
            write["judgements"][unit].update(judge_state=state_of, trusted=laddermod.trusted(state_of, self.ctx.stage))
            if u.step.escalation is not None or gatemod.arm_overrides(spec, unit, state)[0].get("escalation"):
                write["judgements"][unit]["escalation"] = self._escalation_facts(unit, state, att, write)
        if write["judgements"][unit].get("infra_spent"):
            att["infra_spent"] = True
            att["infra_cause"] = "judge_infra"
        return {**write, "run": {"cost": write["judgements"][unit].pop("_cost")}} if "_cost" in write["judgements"][
            unit] else write

    def _judge_claim(self, unit: str, state: RunState, att: dict[str, Any]) -> dict[str, Any]:
        """A step's upstream claim is judged on its own against one criterion: confirmed goes BACK, refuted
        retries, undecided asks a person (BUD-B10, HUM-B7 to HUM-B11). No check runs: the step produced nothing to check."""
        target, defect = (str(x) for x in att["upstream"])
        j = self._judge_session(unit, state, att, None, self._workdir(state), claim=(target, defect))
        cost = j.pop("_cost", None)
        verdict = j.get("verdict")
        if j.get("infra_spent"):
            att["infra_spent"], att["infra_cause"] = True, "judge_infra"
        elif verdict == str(Verdict.PROCEED):  # the one criterion is MET: the defect is there
            j.update(verdict=str(Verdict.BACK), back_to=target, reason="upstream_confirmed",
                     blockers=[{"criterion": CLAIM_CRITERION_ID, "problem": defect}])
            att["escalate"] = None
        elif verdict == str(Verdict.RETRY):
            j.update(reason="upstream_refuted")
            att["escalate"] = None
        else:
            j.update(verdict=str(Verdict.ESCALATE), reason="upstream")
        write: dict[str, Any] = {"attempts": {unit: att}, "judgements": {unit: j}}
        return {**write, "run": {"cost": cost}} if cost is not None else write

    def _check(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any], workdir: Path
               ) -> tuple[CheckResult, list[str]]:
        u = self.ctx.spec.units[unit]
        ctx = self._check_context(unit, state, att, workdir)
        got = run_in_worker(u.gate, ctx)
        if not self.ctx.capture.check_output and ctx.out_dir is not None:  # `observe.check_output = off`
            for f in ctx.out_dir.glob("*.out"):
                with contextlib.suppress(OSError):
                    f.unlink()
        return got

    def _check_context(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any], workdir: Path,
                       sub: str = "") -> checkmod.CheckContext:
        u = self.ctx.spec.units[unit]
        facts = {k: v for k, v in (state.get("facts") or {}).items() if k != unit}
        gfacts = checkmod.git_facts(workdir, (state.get("workspace") or {}).get("base_commit") or "")
        return checkmod.CheckContext(
            changed_paths=checkmod.changed_paths(
                workdir, gfacts, self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "manifest.json"),
            unit=unit, item=att.get("item"), workdir=workdir, request=state.get("request") or {},
            attempt=int(att.get("attempt", 1)),
            visit=int(att.get("visit", 1)), main_checkout=self.ctx.main_checkout,
            artifacts=state.get("artifacts") or {}, values=state.get("values") or {}, facts=facts,
            git=gfacts,
            criteria=tuple({"id": c.id, "mechanical": c.mechanical} for c in u.gate.criteria),
            allow=tuple(self.ctx.spec.allow_commands),
            out_dir=self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "checks"
            / (f"{unit}.{att['item']}" if att.get("item") else unit) / (str(att.get("attempt", 1)) + sub),
            settings={**self._check_settings(u), **({"path_units": list(
                ((state.get("run") or {}).get("path") or {}).get("units") or [])} if u.extra.get("outcome") else {})},
            reuse_store=self.ctx.state_root / "runs" / self.ctx.spec.name / self.ctx.task_id / "command_runs.jsonl")

    def _check_settings(self, u: UnitSpec) -> dict[str, Any]:
        o = self.ctx.spec.outcome
        if not u.extra.get("outcome") or o is None:
            return dict(self.ctx.settings)  # the workflow-declared settings a check reads (RST-B25)
        from tempergraph.run.outcome import deliverable_producers

        return {**self.ctx.settings, "deliverables": [dict(d) for d in o.deliverables],
                "deliverable_producers": deliverable_producers(self.ctx.spec),
                "outcome_check": o.check.ref if o.check else None}

    def _judge_session(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any], cres: CheckResult | None,
                       workdir: Path, claim: tuple[str, str] | None = None) -> dict[str, Any]:
        spec = self.ctx.spec
        u = spec.units[unit]
        g = u.gate
        st = u.step
        assert g.judge is not None and st is not None
        j = g.judge
        if claim:  # one engine criterion replaces the gate's own; the subject is the claimed unit's output
            g = dataclasses.replace(g, criteria=(claim_criterion(*claim),))
        else:  # OUT-B10, OUT-B12: a judge grades no criterion a person signs or nobody verifies
            g = judged(g)
        step_ex = st.executor or spec.default_executor
        judge_name = self.ctx.judges.get(unit) or self.ctx.registry.judge_executor(step_ex, j.executor,
                                                                                  self.ctx.judge_override)
        ex = self.ctx.registry.get(judge_name)
        caps = ex.capabilities()
        from tempergraph.contracts import ToolCall  # local: keeps the module's import list short

        views = view_set(st, [ToolCall(name=t) for t in att.get("tools") or []], caps, j.tools,
                         granted=tuple(u.extra.get("views_add") or ()))
        stance, brief = j.stance, j.brief
        if j.file:
            from tempergraph.contracts import TextRef

            stance, brief = split_judge_file(load_text(spec, TextRef(path=j.file)))
        subject_unit = claim[0] if claim else unit
        arts = (state.get("artifacts") or {}).get(subject_unit) or {}
        vals = (state.get("values") or {}).get(subject_unit) or {}
        refs: dict[str, str] = {}
        for ref in j.references:
            for chan in ("artifacts", "values"):
                for vs in (state.get(chan) or {}).values():
                    if isinstance(vs, dict) and ref in vs:
                        refs[ref] = str(vs[ref])
        inputs = (state.get("request") or {}).get("inputs") or {}
        for ref in j.references:  # a reference may name a request input (validation allows it)
            if ref not in refs and ref != "request" and ref in inputs:
                refs[ref] = str(inputs[ref])
        req_text = str(inputs.get("request", ""))
        prompt = render_judge(JudgeInputs(
            gate=g, stance=stance, brief=brief, request=req_text, references=refs,
            subject={**{k: str(v) for k, v in arts.items()}, **{k: str(v) for k, v in vals.items()}},
            out_of_reach=[d.capability for d in views.deferred], check=cres, step_account=str(att.get("text") or ""),
            workspace_facts={"branch": gitmod.branch(workdir), "changed": len(gitmod.changed_paths(workdir))},
            feedback=str(((state.get("feedback") or {}).get(unit) or {}).get("text") or ""),
            rulings=tuple(gatemod.active_rulings(spec, state, unit)),
            visit_reason=str(((state.get("visits") or {}).get(unit) or {}).get("reason") or "")))
        alias = j.model or "inherit"  # resolved on the judge chain alone (RST-B22, RST-B23, CON-B3)
        attempt = int(att.get("attempt", 1))
        iid = att.get("item")
        jopts = j.session_options or SessionOptions()
        risk = self._risk(unit, state, att, cres, workdir, j) if j.risk is not None else None
        if risk is not None:  # JRK-B8: the level's alias and effort for this attempt; a pin keeps its own
            alias = risk.pop("model") or alias
            effort = risk.pop("effort")
            if effort:
                jopts = dataclasses.replace(jopts, effort=effort)
            self.ctx.log.write("judge_risk", unit=unit, item=iid, attempt=attempt, alias=alias,
                               effort=jopts.effort, **risk)
        key = session_key(unit, attempt, "judge", item=iid)
        req = SessionRequest(kind="judge", prompt=prompt, workdir=workdir, alias=alias, session_key=key,
                             timeout_s=j.timeout_s or DEFAULT_TIMEOUT_S, idle_s=j.idle_s,
                             options=jopts,
                             session_dir=session_dir(self.ctx.state_root, spec.name, self.ctx.task_id, key))
        before = gitmod.fingerprint(workdir)
        changed = list(gitmod.changed_paths(workdir))[:200]  # the digest's `changed_read` (SRV-B11)
        hold = self._hold(unit, state)
        res, results = self._session(ex, req, views, extra={"changed_paths": changed}, hold=hold)
        all_results = list(results)
        out: dict[str, Any] = {"judge_executor": judge_name, "alias": alias, "views": list(views.tools)}
        if risk is not None:
            out["risk"] = risk
        if res.infra_cause is not None:
            out.update(verdict=str(Verdict.ESCALATE), infra_spent=True, reason="judge_infra")
            out["_cost"] = self._cost(state, all_results)
            return out
        judgement = None
        if not res.timed_out:
            try:
                judgement = parse_judgement(res.text, g)
            except Unparsed:
                rkey = session_key(unit, attempt, "judge_reask", item=iid)
                rreq = SessionRequest(kind="judge_reask", prompt=reask_prompt(res.text, g), workdir=workdir,
                                      alias=alias, session_key=rkey, timeout_s=req.timeout_s, idle_s=req.idle_s,
                                      options=req.options,
                                      session_dir=session_dir(self.ctx.state_root, spec.name, self.ctx.task_id, rkey))
                res2, r2 = self._session(ex, rreq, views, hold=hold)
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
                for b in tu.branches:  # a defect in a branch's output sends the run back to its block
                    bu = spec.units.get(b)
                    for k in (bu.step.produces if bu is not None and bu.step else {}):
                        back_units[k] = target
        outcome = derive(judgement, g, cres, {} if claim else back_units)
        if judgement is None and gr.status == "discarded":
            outcome.reason = f"guard:{gr.reason}"
        self.ctx.log.write("judgement", unit=unit, item=iid, attempt=attempt, statuses=outcome.statuses, blockers=[
            b["criterion"] for b in outcome.blockers], confidence=outcome.confidence,
            confidence_source=outcome.confidence_source, gap=outcome.gap, guard=gr.status, views=list(views.tools),
            judge_executor=judge_name, brief_digest=brief_digest(stance, brief),
            criteria_digest=criteria_digest(g.criteria), **({"claim": claim[0]} if claim else {}),
            **({"level": risk["level"]} if risk is not None else {}))
        self._keep_evidence(unit, att, outcome.blockers)
        out.update(outcome.to_json())
        out["guard"] = gr.status
        out["_cost"] = self._cost(state, all_results)
        return out

    def _risk(self, unit: str, state: Mapping[str, Any], att: Mapping[str, Any], cres: CheckResult | None,
              workdir: Path, j: Any) -> dict[str, Any]:
        """JRK-B7, JRK-B8: the rule on model-free facts of the attempt, then the level that grades it."""
        from tempergraph.contracts import RiskContext
        from tempergraph.run import risk as riskmod

        ctx = self.ctx
        maps = (dict, Mapping)
        facts = {u: dict(f) for u, f in (state.get("facts") or {}).items() if isinstance(f, maps)}
        if cres is not None and cres.facts:
            facts[unit] = {**facts.get(unit, {}), **dict(cres.facts)}
        escalated = bool(att.get("escalated"))
        rctx = RiskContext(
            unit=unit, item=att.get("item"), visit=int(att.get("visit", 1)), attempt=int(att.get("attempt", 1)),
            git=riskmod.git_of(checkmod.git_facts(workdir, (state.get("workspace") or {}).get("base_commit") or ""),
                               workdir),
            facts=facts, request=dict((state.get("request") or {}).get("inputs") or {}), settings=dict(ctx.settings),
            stage=ctx.stage, producer={"alias": att.get("alias"), "escalated": escalated,
                                       "source": "escalation:+1" if escalated else "declared"})
        opts = j.session_options
        pinned = any(k in (ctx.spec.units[unit].extra.get("judge_operator_set") or ()) for k in riskmod.PIN_KEYS)
        return riskmod.resolve(j.risk, riskmod.run_rule(j.risk, rctx), base_model=j.model,
                               base_effort=opts.effort if opts else None, pinned=pinned,
                               producer_rank=riskmod.rank(att.get("alias")) if escalated else None)

    def _keep_evidence(self, unit: str, att: Mapping[str, Any], blockers: list[dict[str, Any]]) -> None:
        """One judgement's evidence and fix lines per attempt, scrubbed and local only (LOS-B7, LOS-B8, LOS-B9, RDD-B7 to RDD-B11, RDD-B13, RDD-B15)."""
        if not blockers:
            return
        from tempergraph.docs import write_json
        from tempergraph.store.layout import run_dir

        visit, attempt = int(att.get("visit", 1)), int(att.get("attempt", 1))
        path = (run_dir(self.ctx.state_root, self.ctx.spec.name, self.ctx.task_id) / "evidence" / "judgements"
                / (f"{unit}.{att['item']}" if att.get("item") else unit) / f"{visit}.{attempt}.json")
        rows = [{"criterion": b.get("criterion"),
                 "evidence": clip(scrub(str(b.get("evidence") or b.get("problem") or "")), 400),
                 "fix": clip(scrub(str(b.get("fix") or "")), 400)} for b in blockers]
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_json(path, {"schema_version": 1, "unit": unit, "visit": visit, "attempt": attempt,
                              "blockers": rows}, mode=0o600)

    # -- gate, human, finalizer --------------------------------------------------------------------

    def gate(self, unit: str, state: RunState) -> dict[str, Any]:
        w = gatemod.decide(self.ctx.spec, unit, state, self.ctx.task_id)
        if (state.get("feedback") or {}).get(unit):
            w.setdefault("feedback", {})[unit] = None  # one-time: seen by the attempt and its judge (RRN-B14, RRN-B15)
        r = w["route"][unit]
        so_far = cost_so_far((state.get("run") or {}).get("cost"))
        self.ctx.log.write("gate", unit=unit, item=((state.get("attempts") or {}).get(unit) or {}).get("item"),
                           verdict=((state.get("judgements") or {}).get(unit) or {}).get("verdict"),
                           token=r["token"], route_target=r["node"], cost_so_far=so_far)
        self._budget_records(unit, state, w)
        if r.get("ladder"):  # LAD-B16, LAD-B17: every gate that chose the next attempt's rung
            self.ctx.log.write("ladder_decision", unit=unit, **r["ladder"])
        att = (state.get("attempts") or {}).get(unit) or {}
        if att.get("escalated"):  # LAD-B16, LAD-B17: the escalation record
            laddermod.record_escalation(
                self.ctx.state_root, workflow=self.ctx.spec.name, version=self.ctx.spec.version, unit=unit,
                thread=self.ctx.thread, passed=r["token"] in ("PROCEED", "NEXT"), to=str(att.get("escalated_to")),
                judge_state=((state.get("judgements") or {}).get(unit) or {}).get("judge_state"))
        for name, rr in w["route"].items():  # every pick: predicate, default, operator or re-arm (OBS `route`)
            p = (rr or {}).get("pick")
            if p and (name == unit or p.get("chosen_by") == "rearm"):
                self.ctx.log.write("route", unit=name, arm=p["arm"], target=p["target"], chosen_by=p["chosen_by"],
                                   **{k: p[k] for k in ("shadow", "would_choose", "signals", "signals_clipped",
                                                        "fault", "rearmed_from", "rearm_unit", "rearm_cause",
                                                        *gatemod.COMPLEXITY_FIELDS)
                                      if k in p})
        if unit in (w.get("pause") or {}) and w["pause"][unit]:
            p = w["pause"][unit]
            self.ctx.log.write("pause", unit=unit, item=p.get("item"), pause_kind=p["kind"], decisions=p["decisions"], resume=p["resume"],
                               cost_so_far=so_far, reason=p.get("reason"), escalation=p.get("escalation"),
                               tool_access=[{k: t.get(k) for k in ("name", "capability", "class")}
                                            for t in p.get("tool_access") or []] or None,
                               **({"deadline_at": p["deadline_at"], "on_deadline": p.get("on_deadline")}
                                  if p.get("deadline_at") else {}),
                               **({"questions": len(p["questions"])} if p.get("questions") is not None else {}))
        return w

    def _budget_records(self, unit: str, state: RunState, w: Mapping[str, Any]) -> None:
        """EVT-B10 to EVT-B16 `budget`: one record per counter this gate charged, with its limit and cause."""
        g = self.ctx.spec.units[unit].gate
        before = (state.get("counters") or {}).get(unit) or {}
        after = (w.get("counters") or {}).get(unit) or {}
        cause = ((state.get("judgements") or {}).get(unit) or {}).get("reason") or "verdict"
        if int(after.get("retries", 0)) > int(before.get("retries", 0)):
            self.ctx.log.write("budget", unit=unit, counter="retries", used=int(after["retries"]),
                               limit=g.retry_budget, cause=cause)
        old_loops = before.get("loops") or {}
        for target, n in (after.get("loops") or {}).items():
            if int(n) > int(old_loops.get(target, 0)):
                self.ctx.log.write("budget", unit=unit, counter=f"loops:{target}", used=int(n), limit=g.loop_budget,
                                   cause=cause)

    def human(self, unit: str, state: RunState, decision: Any) -> dict[str, Any]:
        payload = decision if isinstance(decision, dict) else {"decision": str(decision)}
        w = gatemod.apply_decision(self.ctx.spec, unit, state, payload)
        self.ctx.log.write("human", unit=unit, decision=payload.get("decision"), caller=payload.get("caller"),
                           feedback=bool(payload.get("feedback")) and not payload.get("ruling"))
        p = (w.get("pause") or {}).get(unit)
        if p:  # an applied deadline turned the pause into an escalation (FLX-B8)
            self.ctx.log.write("pause", unit=unit, item=p.get("item"), pause_kind=p["kind"], decisions=p["decisions"],
                               resume=p["resume"], reason=p.get("reason"),
                               cost_so_far=cost_so_far((state.get("run") or {}).get("cost")))
        return w

    def finalizer(self, state: RunState) -> dict[str, Any]:
        from tempergraph.run.finalize import run_finalizer

        result = run_finalizer(self.ctx, state)
        self.ctx.log.write("finalize", **result)
        return {"finalized": {"done": True, **result}}


def _entered_from(state: Mapping[str, Any], unit: str) -> str:
    """EVT-B10 to EVT-B16 `entered_from`: `start`, `proceed`, `back:<unit>`, `rewind:<unit>` or `resume`."""
    v = (state.get("visits") or {}).get(unit) or {}
    if v.get("entered_from"):
        return str(v["entered_from"])
    if int(v.get("visit", 1)) > 1 and v.get("from"):
        return f"back:{v['from']}"
    path = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
    return "proceed" if path else "start"

