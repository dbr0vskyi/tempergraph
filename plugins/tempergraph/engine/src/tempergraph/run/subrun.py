"""A sub-workflow's child run as one unit of its parent (SWF-B1 to SWF-B5, SWF-B8, SWF-B10; ADR-0133).

The unit's step node invokes the child's own graph with the node's config, so the child is a subgraph under the
parent's checkpointer, thread, workspace, lock and run cost cap. It has its own compiled graph, its own nodes and its own
run state (`compiler.state`), because every channel is keyed by one workflow's unit names and a child's `work` must not
meet the parent's `work`. Its context shares the parent's registry, state root, drain check and cost cap and starts from the
parent's cost, so one cap holds; its log writer adds `child: <unit>` to every record and its session keys read
`<unit>/<child unit>.<attempt>.<kind>`. The unit hands back only what `produces` exposes, the cost the child added and
the child's outcome record; the child's finalizer never runs from here and its outcome gate is never skipped.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tempergraph import settings as rst
from tempergraph.compiler.graph import CompiledWorkflow, compile_workflow
from tempergraph.compiler.state import RunState, child_input, flat
from tempergraph.contracts import RunOptions, UnitSpec, WorkflowSpec
from tempergraph.git import fingerprint
from tempergraph.improve import calibration
from tempergraph.model import subworkflow
from tempergraph.run import outcome_record
from tempergraph.run.log import ChildLog, CostTotals, RunLog, last_record
from tempergraph.run.nodes import EngineNodes, RunContext
from tempergraph.run.outcome import with_outcome


class ChildUpstream(Exception):
    """SWF-B5: the child's judge or step named a key the parent mapped into `inputs` as the defect. The child ends
    `upstream`; the parent's gate for the unit decides where the run goes."""

    def __init__(self, key: str, reason: str, cost: Mapping[str, Any] | None = None) -> None:
        super().__init__(f"upstream defect in {key}: {reason}")
        self.key = key
        self.reason = reason
        self.cost = dict(cost or {})


class ChildNodes(EngineNodes):
    """The node bodies of one child: the parent's, with the three differences a child has."""

    def __init__(self, ctx: RunContext, unit: str, declared: UnitSpec) -> None:
        super().__init__(ctx)
        self.unit = unit  # the sub-workflow unit of the parent
        self.declared = declared

    def finalizer(self, state: RunState) -> dict[str, Any]:
        """SWF-B10: a child's finalizer never runs from its parent, whose own finalizer can call the same code."""
        return {}

    def judge(self, unit: str, state: RunState) -> dict[str, Any]:
        w = super().judge(unit, state)
        self._upstream(unit, state, w)
        return w

    def _upstream(self, unit: str, state: RunState, w: Mapping[str, Any]) -> None:
        """SWF-B5: a defect in a key the parent mapped into `inputs` ends the child `upstream`."""
        cost = (w.get("run") or {}).get("cost") or (state.get("run") or {}).get("cost")
        for b in (((w.get("judgements") or {}).get(unit) or {}).get("blockers")) or []:
            key = b.get("defect_in")
            if key and subworkflow.is_input_name(self.declared, str(key)):
                raise ChildUpstream(str(key), str(b.get("problem") or b.get("evidence") or "an upstream defect"), cost)
        blocked = str(((state.get("attempts") or {}).get(unit) or {}).get("blocked") or "")
        for param, src in ((self.declared.subworkflow.inputs if self.declared.subworkflow else {}).items()):
            for name in (param, src):
                head = f"upstream claim on {name}:"
                if blocked.startswith(head):
                    raise ChildUpstream(name, blocked[len(head):].strip(), cost)

    def gate(self, unit: str, state: RunState) -> dict[str, Any]:
        """SWF-B2: a child's pause carries `unit` as `<unit>/<child unit>`."""
        w = super().gate(unit, state)
        p = (w.get("pause") or {}).get(unit)
        if p:
            w["pause"][unit] = {**p, "unit": f"{self.ctx.child}/{unit}"}
        return w


@dataclasses.dataclass
class Built:
    """One child ready to run or to read: its spec as this run executes it, its graph and its nodes."""

    name: str  # the child's name in the registry
    path: str  # the unit's path: `<unit>`, or `<unit>/<unit>` for a child of a child
    spec: WorkflowSpec  # with the outcome gate, the settings applied and the parent's cap
    graph: CompiledWorkflow
    nodes: ChildNodes
    version: str
    options: Mapping[str, Any]  # the operator layers as this child reads them


def root_log(log: Any) -> RunLog:
    return log.parent if isinstance(log, ChildLog) else log


def child_options(unit: str, options: Mapping[str, Any]) -> dict[str, Any]:
    """SWF-B8: the operator layers of a run as the child under `unit` reads them: a flag `<unit>/<child unit>.<key>` is
    `<child unit>.<key>` there, and no other key reaches it. The child's own declared defaults stay under every layer."""
    prefix = f"{unit}/"
    return {"settings": {layer: {k[len(prefix):]: cell for k, cell in cells.items() if k.startswith(prefix)}
                         for layer, cells in (options.get("settings") or {}).items()},
            "profiles": list(options.get("profiles") or ())}


def applied(parent: WorkflowSpec, child: subworkflow.Child, options: Mapping[str, Any]) -> tuple[WorkflowSpec, Any]:
    """The child's spec as the run executes it: its declared defaults and the layers `options` carries applied, the
    parent's cap, name and workspace (the child's own `run.workspace` is ignored), and its outcome gate."""
    res = rst.resolve(child.spec, RunOptions(settings=options.get("settings") or {},
                                             profiles=tuple(options.get("profiles") or ())))
    spec = dataclasses.replace(
        rst.effective_spec(child.spec, res), name=parent.name, run_cost_cap_usd=parent.run_cost_cap_usd,
        daily_cap_usd=parent.daily_cap_usd, workspace=parent.workspace, worktree=parent.worktree)
    return with_outcome(spec), res


def locate(spec: WorkflowSpec, path: str, options: Mapping[str, Any]) -> tuple[WorkflowSpec, str] | None:
    """The child spec and unit a pause path `<unit>/<child unit>` (or deeper) names, as the run executes them; None when
    a child on the path is not registered or the path names none."""
    head, _, rest = path.partition("/")
    held = spec.units.get(head)
    if held is None or held.subworkflow is None or not rest:
        return None
    child = subworkflow.read_child(held.subworkflow.workflow)
    if not isinstance(child, subworkflow.Child):
        return None
    mine = child_options(head, options)
    cspec, _ = applied(spec, child, mine)
    return locate(cspec, rest, mine) if "/" in rest else (cspec, rest)


def build(ctx: RunContext, unit: str, declared: UnitSpec, child: subworkflow.Child, options: Mapping[str, Any]
          ) -> Built:
    """SWF-B8: the child's spec with its declared defaults under every layer of the parent's run (a flag reaches a
    child unit as `<unit>/<child unit>.<key>`), the parent's cap, name and workspace; its nodes; its graph."""
    path = f"{ctx.child}/{unit}" if ctx.child else unit
    mine = child_options(unit, options)
    cspec, res = applied(ctx.spec, child, mine)
    # SWF-B9: the child's judges keep the child's own bindings and cases: a judge map of its own, and a judge state
    # read from its own calibration cases and its own gates' judgements, never the parent's (nor the parent's seam)
    cctx = dataclasses.replace(ctx, spec=cspec, log=ChildLog(root_log(ctx.log), path), judges={},
                               settings=rst.workflow_settings(res), child=path, parent_thread=ctx.thread,
                               judge_state=calibration.state_name_for(cspec, ctx.state_root, child=path))
    nodes = ChildNodes(cctx, unit, declared)
    return Built(name=child.name, path=path, spec=cspec, graph=compile_workflow(cspec, nodes, None), nodes=nodes,
                 version=child.version, options=mine)


def _earlier(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for chan in ("artifacts", "values"):
        for owner, vals in (state.get(chan) or {}).items():
            if isinstance(vals, dict):
                out.setdefault(owner, {}).update(vals)
    return out


def _failing(orec: Mapping[str, Any] | None, stopped: Mapping[str, Any] | None, name: str) -> list[dict[str, str]]:
    """SWF-B5: a child that stopped, or ended `unmet` or `needs_person`, fails the unit's gate with the child's
    failing final criteria as blockers."""
    bad = [c for c in (orec or {}).get("criteria", []) if c.get("severity", "blocker") == "blocker"
           and c["status"] not in outcome_record.PASSED]
    if (orec or {}).get("verdict") in ("unmet", "needs_person") and bad:
        return [{"criterion": str(c["id"]), "problem": f"the child {name!r}: its final criterion {c['id']} is "
                                                       f"{c['status']}"} for c in bad]
    if stopped:
        return [{"criterion": "child", "problem": f"the child {name!r} stopped at {stopped.get('unit')} "
                                                  f"({stopped.get('reason')})"}]
    return []


def run_child(parent: EngineNodes, unit: str, state: Mapping[str, Any], config: Any) -> dict[str, Any]:
    """The step node of a sub-workflow unit (SWF-B1): run the child to its end, or until it pauses, and hand back
    what the unit exposes."""
    ctx = parent.ctx
    declared = ctx.spec.units[unit]
    rec = declared.subworkflow
    assert rec is not None
    prev = (state.get("attempts") or {}).get(unit) or {}
    visit = int(((state.get("visits") or {}).get(unit) or {}).get("visit", 1))
    attempt = int(prev.get("attempt", 0)) + 1
    path_units = list(((state.get("run") or {}).get("path") or {}).get("units") or [])
    run: dict[str, Any] = {"path": {"units": path_units + [unit]}} if unit not in path_units else {}
    found = subworkflow.read_child(rec.workflow)
    record: dict[str, Any] = {"attempt": attempt, "visit": visit, "ok": True, "text": "", "issues": [], "tools": [],
                              "session_id": None, "escalate": None, "infra_spent": False, "check": None,
                              "subworkflow": True, "upstream_child": None, "child_failed": None, "error_kind": None}
    # (a key set to None is deleted by the attempts reducer, so nothing of an earlier attempt's end lingers)
    if not isinstance(found, subworkflow.Child):  # removed while this run was going: a person decides
        record.update(ok=False, escalate="workflow_fault", error_kind="child_unknown")
        ctx.log.write("engine_error", unit=unit, error="child_unknown", detail=f"{rec.workflow}: {found.reason}")
        return {"attempts": {unit: record}, "run": run}
    seen = last_record(root_log(ctx.log).path, "unit_entered", unit=unit, child=ctx.child)
    if not seen or seen.get("visit") != visit:
        fp = fingerprint(Path(((state.get("workspace") or {}).get("path")) or ctx.state_root.parent))
        ctx.log.write("unit_entered", unit=unit, visit=visit, head_commit=fp.head, dirty=fp.dirty,
                      entered_from=_entered(state, unit))
    built = build(ctx, unit, declared, found, (state.get("run") or {}).get("options") or {})
    note = subworkflow.workspace_note(found)
    if note and last_record(root_log(ctx.log).path, "note", child=built.path) is None:
        built.nodes.ctx.log.write("note", message=note)
    inputs = subworkflow.child_inputs(declared, state.get("request") or {}, _earlier(state))
    base = dict(((state.get("run") or {}).get("cost") or {}).get("counters") or {})
    try:
        final: Mapping[str, Any] = built.graph.graph.invoke(child_input(state, inputs, built.options),
                                                            _child_config(config, built.path, visit, attempt))
    except ChildUpstream as up:
        record["upstream_child"] = {"key": up.key, "unit": subworkflow.mapped_source(declared, up.key),
                                    "reason": up.reason}
        ctx.attempts_started = built.nodes.ctx.attempts_started
        if up.cost:
            run["cost"] = {**up.cost, "_base": base}
        run["children"] = {unit: {"workflow": built.name, "version": built.version, "upstream": up.key}}
        return {"attempts": {unit: record}, "artifacts": {unit: None}, "values": {unit: None}, "run": run}
    ctx.attempts_started = built.nodes.ctx.attempts_started
    arts, vals, missing = subworkflow.exposed(declared, found, flat(final.get("artifacts")), flat(final.get("values")))
    orec = outcome_record.build(built.spec, final, root_log(ctx.log).path, child=built.path)
    stopped = (final.get("run") or {}).get("stopped")
    failing = _failing(orec, stopped, built.name)
    record.update(issues=[f"value_missing:{k}" for k in missing], child_failed=failing or None)
    cost = (final.get("run") or {}).get("cost")
    if cost:
        run["cost"] = {**cost, "_base": base}
    run["children"] = {unit: {"workflow": built.name, "version": built.version, "outcome": orec,
                              "stopped": dict(stopped) if stopped else None}}
    return {"attempts": {unit: record}, "artifacts": {unit: arts or None}, "values": {unit: vals or None}, "run": run}


def child_states(cw: CompiledWorkflow, thread_id: str) -> dict[str, dict[str, Any]]:
    """The newest checkpointed state of each child namespace of a thread (a child is a subgraph, so its checkpoints sit
    in the parent's thread under a namespace of their own), keyed by the namespace; empty when there is none."""
    saver = getattr(cw.graph, "checkpointer", None)
    out: dict[str, dict[str, Any]] = {}
    if saver is None:
        return out
    try:
        for tup in saver.list(cw.config(thread_id)):  # newest first
            ns = str(tup.config["configurable"].get("checkpoint_ns") or "")
            if ns and ns not in out:
                out[ns] = dict(tup.checkpoint.get("channel_values") or {})
    except Exception:  # noqa: BLE001 - a store that cannot be read has no child to show
        return {}
    return out


def _child_config(config: Any, path: str, visit: int, attempt: int) -> dict[str, Any]:
    """The config the child's graph runs with: the parent's, so the checkpointer and thread are the parent's, and a
    checkpoint namespace of the unit's own (SWF-B8). The namespace belongs to one run of the unit (its visit and attempt),
    not to the parent's task, whose id changes whenever the parent's state is updated while it is paused; so a child
    resumes from where it paused, and a later visit or attempt starts a child with no state of the one before."""
    conf = dict((config or {}).get("configurable") or {})
    conf["checkpoint_ns"] = f"{path}.{visit}.{attempt}"
    conf.pop("checkpoint_id", None)
    return {**dict(config or {}), "configurable": conf}


def pending_cost(cw: CompiledWorkflow, thread_id: str) -> CostTotals | None:
    """SWF-B4: the run's cost as the child furthest along holds it. A child that paused or was drained has not handed its
    spend back to the parent's state, and that spend counts against the run and the day."""
    best: CostTotals | None = None
    for values in child_states(cw, thread_id).values():
        held = CostTotals.from_json((values.get("run") or {}).get("cost"))
        if best is None or held.sessions >= best.sessions:
            best = held
    return best


def _entered(state: Mapping[str, Any], unit: str) -> str:
    v = (state.get("visits") or {}).get(unit) or {}
    if v.get("entered_from"):
        return str(v["entered_from"])
    if int(v.get("visit", 1)) > 1 and v.get("from"):
        return f"back:{v['from']}"
    return "proceed" if ((state.get("run") or {}).get("path") or {}).get("units") else "start"
