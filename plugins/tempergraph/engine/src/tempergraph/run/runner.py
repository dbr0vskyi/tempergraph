"""Start and resume a run (DUR §2, §2.1; CON §2.9 exit codes; HUM-B2; RCT §2).

Everything that can refuse runs before anything is created: validation and preflight, the thread
state (DUR-B1), the workspace plan and the lock. A refusal is exit 2 with nothing written (C13).
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tempergraph import settings as rst
from tempergraph.compiler import compile_workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import Decision, ResolvedSettings, RunOptions, ThreadState, WorkflowSpec, thread_id
from tempergraph.docs import read_json, write_json
from tempergraph.durability import alias as aliases
from tempergraph.durability.checkpoint import classify_snapshot, open_saver, resume_input, snapshot
from tempergraph.durability.control import StopWatcher, take_stop
from tempergraph.durability.lock import LockHeld, RunLock, is_held
from tempergraph.durability.status import classify
from tempergraph.executors.launcher import StopRequest
from tempergraph.executors.preflight import preflight
from tempergraph.executors.registry import Registry
from tempergraph.git import main_checkout
from tempergraph.model import flow
from tempergraph.model.diagram import diagram_model
from tempergraph.run import gate as gatemod
from tempergraph.run.log import CostTotals, Ledger, RunLog, cost_so_far, last_record
from tempergraph.run.nodes import Drain, EngineNodes, RunContext
from tempergraph.run.outcome import with_outcome
from tempergraph.security.scrub import clip, scrub
from tempergraph.store.layout import (
    NotInRepository,
    checkpoint_path,
    ensure_state_root,
    home_path,
    lock_path,
    run_dir,
    state_root_path,
)
from tempergraph.workspace import (
    WorkspaceRecord,
    WorkspaceRefused,
    attach_workspace,
    prepare_workspace,
    release_workspace,
    resolve_workspace,
)

STOP_EXIT = {"infra": ExitCode.BUDGET_OR_INFRA, "budget": ExitCode.BUDGET_OR_INFRA, "person": ExitCode.STOPPED}


@dataclass(kw_only=True)
class RunOutcome:
    exit_code: ExitCode
    reason: str = ""
    message: str = ""
    payload: dict[str, Any] | None = None
    thread_id: str = ""
    warnings: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class RunSettings:
    workspace: str | None = None
    alias: str | None = None
    label: str | None = None
    origin: str = "cli"
    enforce_tools: bool = False
    strict_permissions: bool = False
    judge_override: str | None = None
    caller: Mapping[str, Any] = field(default_factory=dict)
    sleep: Callable[[float], None] | None = None
    infra_tries: int | None = None
    flags: Mapping[str, Any] = field(default_factory=dict)  # `--set` and its named spellings (RST §2.3 layer 1)
    profiles: tuple[str, ...] | None = None  # None keeps the thread's profiles on resume
    unset: tuple[str, ...] = ()
    reload_settings: bool = False
    home: Path | None = None  # the user config folder's parent; default `home_path()`

    def all_flags(self) -> dict[str, Any]:
        """The named run options are spellings of `--set` (CLI §2.1)."""
        f = dict(self.flags)
        for key, val in (("run.workspace", self.workspace), ("judges.executor", self.judge_override),
                         ("run.infra_tries", self.infra_tries)):
            if val is not None:
                f.setdefault(key, val)
        for key, on in (("run.enforce_tools", self.enforce_tools), ("run.strict_permissions", self.strict_permissions)):
            if on:
                f.setdefault(key, True)
        return f


@dataclass(kw_only=True)
class Settled:
    """A resolution applied: the spec the run executes, its settings and the snapshot to keep (RST §2.6)."""

    spec: WorkflowSpec
    resolved: ResolvedSettings
    options: RunOptions
    changed: list[str] = field(default_factory=list)
    before: ResolvedSettings | None = None

    def grant_changes(self) -> list[dict[str, Any]]:
        """Grants given or removed by this call, against the thread's previous snapshot (RST §2.8)."""
        new = rst.grants(self.resolved)
        old = rst.grants(self.before) if self.before is not None else []
        return ([{**g, "action": "given"} for g in new if g not in old]
                + [{**g, "action": "removed"} for g in old if g not in new])

    @property
    def run(self) -> dict[str, Any]:
        return rst.run_values(self.resolved)

    def snapshot_json(self) -> dict[str, Any]:
        return {"settings": self.options.settings, "profiles": list(self.options.profiles)}


class SettingsRefused(Exception):
    def __init__(self, findings: list[Any]) -> None:
        super().__init__(findings[0].message)
        self.findings = findings


def settle_start(spec: WorkflowSpec, settings: RunSettings, root: Path | None) -> Settled:
    """Read both files once, resolve, validate before spend (RST §2.6 Start)."""
    files = rst.load_files(root, settings.home or home_path())
    opts, findings = rst.options_snapshot(spec, settings.all_flags(), tuple(settings.profiles or ()), files,
                                          via=settings.origin, caller_kind=str(settings.caller.get("kind") or "unknown"))
    if findings:
        raise SettingsRefused(findings)
    res = rst.resolve(spec, opts)
    return Settled(spec=rst.effective_spec(spec, res), resolved=res, options=opts)


def settle_resume(spec: WorkflowSpec, settings: RunSettings, root: Path, values: Mapping[str, Any]) -> Settled:
    """Reapply the thread's snapshot, then this call's `--set`, `--unset`, `--profile`, `--reload-settings`."""
    snap = ((values.get("run") or {}).get("options") or {})
    old = RunOptions(settings={k: dict(v) for k, v in (snap.get("settings") or {}).items()},
                     profiles=tuple(snap.get("profiles") or ()))
    flags = {k: c["value"] for k, c in (old.settings.get("flag") or {}).items()}
    for k, v in settings.all_flags().items():  # a later grant adds to the thread's grants (RST §2.8 Kept)
        if rst.is_widening(k) and k in flags:
            v = list(dict.fromkeys(rst.as_list(flags[k]) + rst.as_list(v)))
        flags[k] = v
    for k in settings.unset:
        flags.pop(k, None)
    profiles = tuple(settings.profiles) if settings.profiles is not None else old.profiles
    if settings.reload_settings or settings.profiles is not None:
        files = rst.load_files(root, settings.home or home_path())
        new, findings = rst.options_snapshot(spec, flags, profiles, files, via=settings.origin,
                                             caller_kind=str(settings.caller.get("kind") or "unknown"))
        if not settings.reload_settings:  # a new profile list reads profiles only; the file layers stay
            new = RunOptions(settings={**{k: v for k, v in old.settings.items()}, "profile": new.settings["profile"],
                                       "flag": new.settings["flag"]}, profiles=profiles)
            findings = [f for f in findings if f.code in ("unknown_profile", "widening_in_file")]
    else:
        new = RunOptions(settings={**old.settings, "flag": rst.snapshot(spec, flags, (), rst.ConfigFiles(),
                                                                        via=settings.origin)[0]["flag"]},
                         profiles=profiles)
        findings = []
    if not (settings.reload_settings or settings.profiles is not None):
        findings += rst.validate_layers(spec, new.settings, str(settings.caller.get("kind") or "unknown"))
    if findings:
        raise SettingsRefused(findings)
    res = rst.resolve(spec, new)
    before = rst.resolve(spec, old) if snap else None
    changed = rst.changed_keys(before, res)
    return Settled(spec=rst.effective_spec(spec, res), resolved=res, options=new, changed=changed, before=before)


def _refuse(reason: str, message: str, refusals: list[str] | None = None, tid: str = "") -> RunOutcome:
    return RunOutcome(exit_code=ExitCode.USAGE, reason=reason, message=message, refusals=refusals or [], thread_id=tid)


def _answers(log_path: Path, g: Mapping[str, Any]) -> dict[str, Any] | None:
    """The pause a grant answers: the refusal class it fixes and that pause's `seq` (EVT §2.2 `grant`)."""
    pause = last_record(log_path, "pause", unit=g["unit"])
    for item in (pause or {}).get("tool_access") or []:
        if item.get("capability") == g.get("capability"):
            return {"class": item.get("class"), "seq": pause.get("seq") if pause else None}
    return None


def _grants_used(spec: WorkflowSpec, registry: Registry, settled: Settled, values: Mapping[str, Any]
                 ) -> list[dict[str, Any]]:
    """The ledger row's `grants[]`: whether the unit's last attempt used each grant (RST §2.8, IMD-R14)."""
    from tempergraph.executors.capabilities import tool_names

    out = []
    for g in rst.grants(settled.resolved):
        u = spec.units.get(g["unit"])
        att = ((values.get("attempts") or {}).get(g["unit"]) or {})
        used: bool | None = None
        if "capability" in g and u is not None and u.step is not None and att:
            ex = registry.get(u.step.executor or spec.default_executor)
            used = bool(set(tool_names(ex.capabilities(), g["capability"])) & set(att.get("tools") or []))
        out.append({**{k: v for k, v in g.items() if k != "key"}, "used": used,
                    "passed": att.get("ok") if att else None})
    return out


def _refuse_settings(exc: SettingsRefused, tid: str) -> RunOutcome:
    first = exc.findings[0]
    return _refuse(first.code, first.message, [f"{f.code}: {f.message}" for f in exc.findings], tid)


def _root(target: Path) -> Path:
    return state_root_path(target)


def exit_file(state_root: Path, workflow: str, task_id: str) -> Path:
    return run_dir(state_root, workflow, task_id) / "exit.json"


def _context(spec: WorkflowSpec, task_id: str, root: Path, registry: Registry, settings: RunSettings,
             judges: Mapping[str, str], log: RunLog, stop: StopRequest, watcher_box: dict[str, Any],
             main: Path | None, settled: Settled) -> RunContext:
    def drain() -> str | None:
        w = watcher_box.get("w")
        taken = w.check() if w is not None else None
        if taken is not None:
            if not watcher_box.get("logged"):
                log.write("stop_requested", mode=taken.mode, caller=taken.caller)
                watcher_box["logged"] = True
            return "stopped_by_request"
        return None

    rv = settled.run
    ctx = RunContext(spec=spec, task_id=task_id, state_root=root, registry=registry, log=log, judges=judges,
                     enforce_tools=bool(rv["enforce_tools"] or rv["strict_permissions"]), stop=stop,
                     drain_requested=drain, main_checkout=main, attempt_cap=int(rv["attempt_cap"]),
                     infra_tries=max(1, int(rv["infra_tries"])), backoff_max_s=int(rv["infra_backoff_max_s"]),
                     settings=rst.workflow_settings(settled.resolved))
    if settings.sleep is not None:
        ctx.sleep = settings.sleep
    return ctx


def _drive(spec: WorkflowSpec, task_id: str, root: Path, registry: Registry, settings: RunSettings,
           judges: Mapping[str, str], first_input: Any, settled: Settled, *,
           before: Callable[[Any], None] | None = None, executors: Mapping[str, str] | None = None) -> RunOutcome:
    """Run the graph from `first_input` while holding the lock, then turn the thread state into an exit."""
    tid = thread_id(spec.name, task_id)
    log = RunLog(run_dir(root, spec.name, task_id) / "run.jsonl")
    stop = StopRequest()
    box: dict[str, Any] = {}
    main = main_checkout(root.parent)
    ctx = _context(spec, task_id, root, registry, settings, judges, log, stop, box, main, settled)
    saver = open_saver(checkpoint_path(root, spec.name))
    try:
        cw = compile_workflow(spec, EngineNodes(ctx), saver)
        cfg = cw.config(tid)
        if before is not None:
            before(cw)
        meta = (((cw.graph.get_state(cfg).values or {}).get("run") or {}).get("meta") or {})
        log.write("run_started", origin=settings.origin, caller=dict(settings.caller),
                  alias=aliases.alias_of(root, tid), label=settings.label or meta.get("label"),
                  workflow_version=spec.version, plan_digest=diagram_model(spec)["digest"],
                  executors={"steps": dict(executors or {}), "judges": dict(judges)},
                  settings_digest=settled.resolved.digest, profiles=list(settled.options.profiles),
                  overridden_keys=rst.overridden_keys(settled.resolved))
        rec: dict[str, Any] = {"settings_digest": settled.resolved.digest, "rows": rst.rows_json(settled.resolved),
                               "changed_keys": settled.changed}
        if settled.changed:
            rec["caller"] = dict(settings.caller)
        log.write("settings_resolved", **rec)
        for g in settled.grant_changes():
            log.write("grant", unit=g["unit"], capability=g.get("capability"), prefix=g.get("prefix"),
                      action=g["action"], answers=_answers(log.path, g), by=dict(settings.caller), via=settings.origin)
        outcome: RunOutcome
        with StopWatcher(root, spec.name, task_id, stop, poll_s=1.0) as watcher:
            box["w"] = watcher
            try:
                cw.graph.invoke(first_input, cfg)
                outcome = _settle(cw, cfg, spec, task_id, root)
            except Drain as d:
                code = ExitCode.BUDGET_OR_INFRA if d.reason == "cost_cap" else ExitCode.STOPPED
                outcome = RunOutcome(exit_code=code, reason=d.reason, thread_id=tid,
                                     message=f"{tid} stopped at a boundary ({d.reason}); resume continues it")
        final = cw.graph.get_state(cfg).values or {}
        cost = CostTotals.from_json((final.get("run") or {}).get("cost"))
        log.write("run_exit", exit_code=int(outcome.exit_code), reason=outcome.reason, cost=cost.to_json(),
                  cost_so_far=cost_so_far(cost.to_json()))
        write_json(exit_file(root, spec.name, task_id), {"schema_version": 1, "exit_code": int(outcome.exit_code),
                                                          "reason": outcome.reason})
        Ledger(path=root / "ledger.jsonl").append({"kind": "run_segment", "thread_id": tid, "workflow": spec.name,
                                                   "exit_code": int(outcome.exit_code), "reason": outcome.reason,
                                                   "cost": cost.to_json(), "origin": settings.origin,
                                                   "settings_digest": settled.resolved.digest,
                                                   "overridden_keys": rst.overridden_keys(settled.resolved),
                                                   "grants": _grants_used(spec, registry, settled, final)})
        outcome.thread_id = tid
        return outcome
    finally:
        saver.conn.close()


def _settle(cw: Any, cfg: Mapping[str, Any], spec: WorkflowSpec, task_id: str, root: Path) -> RunOutcome:
    snap = snapshot(cw, cfg["configurable"]["thread_id"])
    state = classify_snapshot(snap, lock_held=False)
    tid = cfg["configurable"]["thread_id"]
    if state is ThreadState.PAUSED:
        payload = snap.interrupts[0][1] if snap.interrupts else None
        return RunOutcome(exit_code=ExitCode.PAUSED, reason=str((payload or {}).get("kind", "escalation")),
                          payload=payload, message=f"{tid} is waiting for a person")
    if state is ThreadState.FINISHED:
        ws = snap.values.get("workspace") or {}
        if ws:
            rec = release_workspace(WorkspaceRecord.from_json(ws))
            cw.graph.update_state(cfg, {"workspace": rec.to_json()}, as_node=flow.FINALIZER)
        fin = snap.values.get("finalized") or {}
        return RunOutcome(exit_code=ExitCode.FINISHED, reason=str(fin.get("outcome", "finished")),
                          message=f"{tid} finished")
    stopped = (snap.values.get("run") or {}).get("stopped") or {}
    reason = str(stopped.get("reason", "stopped"))
    return RunOutcome(exit_code=STOP_EXIT.get(reason, ExitCode.STOPPED), reason=reason,
                      message=f"{tid} stopped at {stopped.get('unit')} ({reason})")


def start(spec: WorkflowSpec, task_id: str, inputs: Mapping[str, str], target: Path, registry: Registry,
          settings: RunSettings | None = None) -> RunOutcome:
    settings = settings or RunSettings()
    tid = thread_id(spec.name, task_id)
    try:
        root = _root(target)
    except NotInRepository:
        return _refuse("not_git", "the engine keeps its state in a git repository's main checkout")
    if classify(root, spec, task_id) is not ThreadState.NONE:
        return _refuse("thread_exists", f"{tid} already exists; resume it with `tempergraph resume {spec.name} "
                                        f"{task_id}` or start a new thread with another task id", tid=tid)
    try:
        settled = settle_start(spec, settings, root)
    except SettingsRefused as exc:
        return _refuse_settings(exc, tid)
    rv = settled.run
    spec = settled.spec
    rep = preflight(spec, registry, enforce_tools=bool(rv["enforce_tools"]),
                    strict_permissions=bool(rv["strict_permissions"]))
    if not rep.ok:
        first = rep.refusals[0]
        return _refuse(first.code, f"{first.unit or spec.name}: {first.message}",
                       [f"{f.code}: {f.unit}: {f.message}" for f in rep.refusals], tid)
    spec = with_outcome(spec)
    try:
        plan = resolve_workspace(spec, target, rv["workspace"], task_id=task_id,
                                 prefix=str(rv["worktree.branch_prefix"]))
    except WorkspaceRefused as exc:
        return _refuse(exc.word, str(exc), tid=tid)
    ensure_state_root(root)
    lock = RunLock(lock_path(root, spec.name, task_id))
    try:
        lock.acquire()
    except LockHeld:
        return _refuse("running", f"{tid} is running", tid=tid)
    try:
        if settings.alias:
            try:
                aliases.claim(root, settings.alias, tid, lambda t: _live(root, spec, t))
            except (aliases.AliasTaken, aliases.AliasInvalid) as exc:
                return _refuse("alias", str(exc), tid=tid)
        try:
            rec = prepare_workspace(tid, plan, spec.worktree, root,
                                    read_include=bool(rv["worktree.read_worktreeinclude"]))
        except WorkspaceRefused as exc:
            return _refuse(exc.word, str(exc), tid=tid)
        RunLog(run_dir(root, spec.name, task_id) / "run.jsonl").write(
            "task", chars=sum(len(v) for v in inputs.values()), request=clip(scrub(inputs.get("request", "")), 200))
        initial = {"request": {"task_id": task_id, "inputs": dict(inputs)}, "workspace": rec.to_json(),
                   "run": {"meta": {"origin": settings.origin, "label": clip(scrub(settings.label or ""), 80) or None},
                           "options": settled.snapshot_json()}}
        out = _drive(spec, task_id, root, registry, settings, rep.judges, initial, settled,
                     executors=rep.step_executors)
        out.warnings = list(plan.warnings) + [f"{w.code}: {w.message}" for w in rep.warnings]
        return out
    finally:
        lock.release()


def _live(root: Path, spec: WorkflowSpec, tid: str) -> bool:
    w, _, task = tid.partition("/")
    if w != spec.name:
        return is_held(lock_path(root, w, task))
    return classify(root, spec, task) not in (ThreadState.FINISHED, ThreadState.NONE)


def resume(spec: WorkflowSpec, task_id: str, target: Path, registry: Registry, *, decision: str | None = None,
           feedback: str | None = None, settings: RunSettings | None = None) -> RunOutcome:
    settings = settings or RunSettings()
    tid = thread_id(spec.name, task_id)
    try:
        root = _root(target)
    except NotInRepository:
        return _refuse("not_git", "not inside a git repository")
    state = classify(root, spec, task_id)
    if state in (ThreadState.NONE, ThreadState.RUNNING, ThreadState.FINISHED):
        hint = {"none": "no such thread", "running": "it is running",
                "finished": f"it finished; `tempergraph rerun {spec.name} {task_id}` starts a linked thread"}
        return _refuse(str(state), f"{tid}: {hint[str(state)]}", tid=tid)
    try:
        d = Decision.parse(decision) if decision else None
    except ValueError as exc:
        return _refuse("decision_invalid", str(exc), tid=tid)
    declared = spec
    lock = RunLock(lock_path(root, spec.name, task_id))
    try:
        lock.acquire()
    except LockHeld:
        return _refuse("running", f"{tid} is running", tid=tid)
    try:
        stale = take_stop(root, spec.name, task_id, stale=True)
        saver = open_saver(checkpoint_path(root, spec.name))
        try:
            cw = compile_workflow(with_outcome(declared), _Inert(), saver)
            snap = snapshot(cw, tid)
            values = snap.values
        finally:
            saver.conn.close()
        try:
            settled = settle_resume(declared, settings, root, values)
        except SettingsRefused as exc:
            return _refuse_settings(exc, tid)
        rv = settled.run
        rep = preflight(settled.spec, registry, enforce_tools=bool(rv["enforce_tools"]),
                        strict_permissions=bool(rv["strict_permissions"]))
        if not rep.ok:
            first = rep.refusals[0]
            return _refuse(first.code, f"{first.unit or spec.name}: {first.message}", tid=tid)
        spec = with_outcome(settled.spec)
        human_cap = int(rv["human_cap"])
        if state is ThreadState.PAUSED:
            if d is None:
                units = [n.rsplit(".", 1)[0] for n, _ in snap.interrupts]
                return _refuse("decision_missing", f"{tid} is paused at {', '.join(units)}; pass --decision", tid=tid)
            unit = snap.interrupts[0][0].rsplit(".", 1)[0]
            try:
                gatemod.check_decision(spec, unit, values, d, human_cap=human_cap)
            except gatemod.DecisionRefused as exc:
                return _refuse("decision_refused", str(exc), tid=tid)
            first_input: Any = resume_input({"decision": str(d), "feedback": feedback, "caller": dict(settings.caller)})
            before = None
            pause = snap.interrupts[0][1] if isinstance(snap.interrupts[0][1], dict) else {}
            touch = (unit, str(pause.get("kind") or "escalation"), str(pause.get("reason") or ""))
        elif state is ThreadState.UNFINISHED:
            if d is not None and d.word != "rewind":
                return _refuse("decision_refused", "an unfinished thread accepts only `rewind:<unit>`", tid=tid)
            first_input, before = None, None
            touch = None
            if d is not None:
                unit = _last_unit(values)
                before = _human_update(spec, unit, values, d, feedback)
                touch = (unit, "unfinished", "rewind")
        else:  # stopped
            if d is None or d.word not in ("retry", "back", "rewind"):
                return _refuse("decision_refused", "a stopped thread re-opens with retry, back:<unit> or rewind:<unit>",
                               tid=tid)
            unit = str(((values.get("run") or {}).get("stopped") or {}).get("unit") or _last_unit(values))
            try:
                gatemod.check_decision(spec, unit, values, d, human_cap=human_cap)
            except gatemod.DecisionRefused as exc:
                return _refuse("decision_refused", str(exc), tid=tid)
            first_input, before = None, _human_update(spec, unit, values, d, feedback)
            reason = str(((values.get("run") or {}).get("stopped") or {}).get("reason") or "")
            touch = (unit, "stopped", reason)
        ws = values.get("workspace") or {}
        if ws:
            try:
                rec = attach_workspace(WorkspaceRecord.from_json(ws), tid, spec.worktree, root)
            except WorkspaceRefused as exc:
                return _refuse(exc.word, str(exc), tid=tid)
            ws_update = rec.to_json()
        else:
            ws_update = None
        prior = before
        if touch is not None and d is not None:
            intervention(root, spec, task_id, touch, d, feedback, settings, settled)

        def before_all(cw2: Any) -> None:
            cfg = cw2.config(tid)
            cw2.graph.update_state(cfg, {"run": {"options": settled.snapshot_json()}})
            if ws_update is not None:
                cw2.graph.update_state(cfg, {"workspace": ws_update})
            if prior is not None:
                prior(cw2)

        out = _drive(spec, task_id, root, registry, settings, rep.judges, first_input, settled, before=before_all,
                     executors=rep.step_executors)
        if stale is not None:
            out.warnings.append("stale_stop_request_removed")
        return out
    finally:
        lock.release()


RESCUE_PAUSES = frozenset({"escalation", "budget", "tool_access"})


def touches(pause_kind: str, stop_reason: str, d: Decision) -> list[dict[str, str]]:
    """SUP §2.1 touch classes of one accepted resume."""
    out: list[dict[str, str]] = []
    if pause_kind == "approval":
        out.append({"class": "designed", "action": "approve"})
    elif pause_kind in RESCUE_PAUSES or pause_kind == "stopped" and stop_reason in ("budget", "infra"):
        out.append({"class": "rescue", "action": "decide"})
    if d.word == "rewind":
        out.append({"class": "steer", "action": "rewind"})
    elif d.word == "stop":
        out.append({"class": "steer", "action": "stop"})
    elif pause_kind == "stopped" and stop_reason not in ("budget", "infra") and not out:
        out.append({"class": "steer", "action": "decide"})
    return out


def intervention(root: Path, spec: WorkflowSpec, task_id: str, touch: tuple[str, str, str], d: Decision,
                 feedback: str | None, settings: RunSettings, settled: Settled | None = None) -> dict[str, Any]:
    """HUM-B6: one metadata-only ledger row per accepted resume, appended before the graph runs."""
    unit, kind, reason = touch
    pause = last_record(run_dir(root, spec.name, task_id) / "run.jsonl", "pause", unit=unit)
    wait_s = None
    if pause and pause.get("ts"):
        with contextlib.suppress(ValueError, TypeError):
            wait_s = round((datetime.now(datetime.fromisoformat(pause["ts"]).tzinfo)
                            - datetime.fromisoformat(pause["ts"])).total_seconds(), 1)
    row = {"kind": "intervention", "id": uuid.uuid4().hex, "thread_id": thread_id(spec.name, task_id),
           "workflow": spec.name, "unit": unit, "caller": dict(settings.caller),
           "touches": touches(kind, reason if kind == "stopped" else "", d), "pause_kind": kind,
           "decision": d.word + (f":{d.unit}" if d.unit else ""), "wait_s": wait_s, "feedback": bool(feedback),
           "ruling": False, "settings_changed": list(settled.changed) if settled else [],
           "grants": [{k: v for k, v in g.items() if k != "key"} for g in (settled.grant_changes() if settled else [])],
           "cause": reason or kind}
    Ledger(path=root / "ledger.jsonl").append(row)
    return row


def _last_unit(values: Mapping[str, Any]) -> str:
    units = ((values.get("run") or {}).get("path") or {}).get("units") or []
    return str(units[-1]) if units else ""


def _human_update(spec: WorkflowSpec, unit: str, values: Mapping[str, Any], d: Decision, feedback: str | None
                  ) -> Callable[[Any], None]:
    """Re-open a stopped thread, or rewind an unfinished one, through the human node's own update."""

    def apply(cw: Any) -> None:
        w = gatemod.apply_decision(spec, unit, values, {"decision": str(d), "feedback": feedback})
        w.setdefault("run", {})["stopped"] = None
        cw.graph.update_state(cw.config(f"{spec.name}/{values.get('request', {}).get('task_id', '')}"), w,
                              as_node=flow.node_names(unit)[3])

    return apply


class _Inert:
    def _never(self, *_: Any) -> dict[str, Any]:
        raise RuntimeError("inert")

    step = judge = gate = human = _never

    def finalizer(self, state: Any) -> dict[str, Any]:
        return self._never(state)


def read_exit(state_root: Path, workflow: str, task_id: str) -> dict[str, Any] | None:
    p = exit_file(state_root, workflow, task_id)
    with contextlib.suppress(OSError, ValueError):
        return read_json(p, "status") if p.exists() else None
    return None
