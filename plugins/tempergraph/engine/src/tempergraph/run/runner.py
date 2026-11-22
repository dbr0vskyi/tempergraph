"""Start and resume a run (DUR-B9, DUR-B11; CON-B12, CON-B13 exit codes; HUM-B2; RCT-B6, RCT-B7).

Everything that can refuse runs before anything is created: validation and preflight, the thread
state (DUR-B1), the workspace plan and the lock. A refusal is exit 2 with nothing written (OVR-B15).
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tempergraph import provenance
from tempergraph import settings as rst
from tempergraph.compiler import compile_workflow
from tempergraph.constants import ENGINE_VERSION, ExitCode
from tempergraph.contracts import Decision, ResolvedSettings, RunOptions, ThreadState, WorkflowSpec, thread_id
from tempergraph.docs import read_json, write_json
from tempergraph.durability import alias as aliases
from tempergraph.durability import carry as carrymod
from tempergraph.durability import engine_file as enginefile
from tempergraph.durability.checkpoint import (
    classify_snapshot,
    open_saver,
    resume_input,
    snapshot,
    update_values,
)
from tempergraph.durability.control import StopWatcher, take_stop
from tempergraph.durability.lock import LockHeld, RunLock, is_held
from tempergraph.durability.status import breakpoint_at, classify
from tempergraph.executors.launcher import StopRequest
from tempergraph.executors.preflight import preflight
from tempergraph.executors.registry import Registry
from tempergraph.git import main_checkout
from tempergraph.model import flow, subworkflow
from tempergraph.model.diagram import diagram_model
from tempergraph.model.validate import Finding
from tempergraph.run import gate as gatemod
from tempergraph.run import outcome_record, supervision
from tempergraph.run.log import CostTotals, Ledger, RunLog, cost_so_far, last_record
from tempergraph.run.nodes import Drain, EngineNodes, RunContext
from tempergraph.run.outcome import with_outcome
from tempergraph.security.scrub import clip, scrub
from tempergraph.store import manifest as manifestmod
from tempergraph.store.layout import (
    NotInRepository,
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
    degraded: bool = False  # a gate's fallback target was taken (FLX-B9)
    thread_id: str = ""
    warnings: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    auto_reopen: int = 0  # `run.auto_reopen` of the segment that ended (BUD-B6)


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
    flags: Mapping[str, Any] = field(default_factory=dict)  # `--set` and its named spellings (RST-B22, RST-B23 layer 1)
    profiles: tuple[str, ...] | None = None  # None keeps the thread's profiles on resume
    unset: tuple[str, ...] = ()
    reload_settings: bool = False
    ruling: bool = False  # `--ruling`: the feedback is a lasting ruling (RRN-B14, RRN-B15)
    ruling_for: tuple[str, ...] = ()
    revoke_rulings: tuple[str, ...] = ()
    accept_external: bool = False  # consent to rewind or rerun past external effects (RRN-B16)
    relayed: bool = False  # `--relayed`: the call carries a person's decision (PRV-B14)
    dry_run: bool = False  # `--dry-run`: self-improvement files nothing for this run (ROP-B1 to ROP-B13)
    home: Path | None = None  # the user config folder's parent; default `home_path()`
    escalate: bool = False  # `resume --escalate`: take the offered escalation (LAD-B12)
    escalation_record: Callable[[str], bool] | None = None  # a seam for LAD-B13's escalation record
    judge_state: Callable[[str], str] | None = None  # a seam for a gate's judge binding state (JCL-B17)
    carry: bool = False  # `--carry`: carry this thread's state on its own branch (CAR-B5)
    answers: Mapping[str, Any] = field(default_factory=dict)  # `answer:<name>=<value>` and `--answers` (ASK-B8)
    apply_deadline: bool = False  # `resume --apply-deadline` (FLX-B8)
    pause_before: tuple[str, ...] = ()  # `--pause-before <unit>`: operator breakpoints of this segment (FLX-B10)
    unit: str | None = None  # `resume --unit`: which of several pending gates the decision answers (HUM-B3)

    def all_flags(self) -> dict[str, Any]:
        """The named run options are spellings of `--set` (ROP-B1 to ROP-B13)."""
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
    """A resolution applied: the spec the run executes, its settings and the snapshot to keep (RST-B26)."""

    spec: WorkflowSpec
    resolved: ResolvedSettings
    options: RunOptions
    changed: list[str] = field(default_factory=list)
    before: ResolvedSettings | None = None

    def grant_changes(self) -> list[dict[str, Any]]:
        """Grants given or removed by this call, against the thread's previous snapshot (RST-B28, RST-B29, RST-B30)."""
        new = rst.grants(self.resolved)
        old = rst.grants(self.before) if self.before is not None else []
        return ([{**g, "action": "given"} for g in new if g not in old]
                + [{**g, "action": "removed"} for g in old if g not in new])

    @property
    def run(self) -> dict[str, Any]:
        return rst.run_values(self.resolved)

    def snapshot_json(self) -> dict[str, Any]:
        return {"settings": self.options.settings, "profiles": list(self.options.profiles)}


def decided(settings: RunSettings, *, deciding: bool, words: Sequence[str] = (), since: str | None = None
            ) -> RunSettings:
    """PRV-B14: fill the decider of a deciding call; `--relayed` on a call that decides nothing is refused."""
    if not deciding:
        if settings.relayed:
            raise SettingsRefused([Finding(code="relay_not_applicable", unit=None,
                                           message="--relayed on a call that decides nothing")])
        return settings
    block = provenance.decide(settings.caller, relayed=settings.relayed, words=words, since=since,
                              home=settings.home or home_path())
    return dataclasses.replace(settings, caller=block)


def _widen_kind(settings: RunSettings) -> str:
    """The caller kind the widening rule sees: `person` only for a person or a `turn_named` relay (PRV-B21, PRV-B22)."""
    if not settings.caller:  # `run --check` and `config show` read no signals (OVR-B15); the call itself checks
        return "person"
    return "person" if provenance.may_widen(settings.caller) else str(settings.caller.get("decided_by")
                                                                       or settings.caller.get("kind") or "unknown")


class SettingsRefused(Exception):
    def __init__(self, findings: list[Any]) -> None:
        super().__init__(findings[0].message)
        self.findings = findings


def settle_start(spec: WorkflowSpec, settings: RunSettings, root: Path | None) -> Settled:
    """Read both files once, resolve, validate before spend (RST-B26 Start)."""
    files = rst.load_files(root, settings.home or home_path())
    opts, findings = rst.options_snapshot(spec, settings.all_flags(), tuple(settings.profiles or ()), files,
                                          via=settings.origin, caller_kind=_widen_kind(settings))
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
    for k, v in settings.all_flags().items():  # a later grant adds to the thread's grants (RST-B28, RST-B29, RST-B30 Kept)
        if rst.is_widening(k) and k in flags:
            v = list(dict.fromkeys(rst.as_list(flags[k]) + rst.as_list(v)))
        flags[k] = v
    for k in settings.unset:
        flags.pop(k, None)
    profiles = tuple(settings.profiles) if settings.profiles is not None else old.profiles
    if settings.reload_settings or settings.profiles is not None:
        files = rst.load_files(root, settings.home or home_path())
        new, findings = rst.options_snapshot(spec, flags, profiles, files, via=settings.origin,
                                             caller_kind=_widen_kind(settings))
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
        findings += rst.validate_layers(spec, new.settings, _widen_kind(settings))
    if findings:
        raise SettingsRefused(findings)
    res = rst.resolve(spec, new)
    before = rst.resolve(spec, old) if snap else None
    changed = rst.changed_keys(before, res)
    return Settled(spec=rst.effective_spec(spec, res), resolved=res, options=new, changed=changed, before=before)


def _refuse(reason: str, message: str, refusals: list[str] | None = None, tid: str = "") -> RunOutcome:
    return RunOutcome(exit_code=ExitCode.USAGE, reason=reason, message=message, refusals=refusals or [], thread_id=tid)


def _answers(log_path: Path, g: Mapping[str, Any]) -> dict[str, Any] | None:
    """The pause a grant answers: the refusal class it fixes and that pause's `seq` (EVT-B10 to EVT-B16 `grant`)."""
    pause = last_record(log_path, "pause", unit=g["unit"])
    for item in (pause or {}).get("tool_access") or []:
        if item.get("capability") == g.get("capability"):
            return {"class": item.get("class"), "seq": pause.get("seq") if pause else None}
    return None


def _grants_used(spec: WorkflowSpec, registry: Registry, settled: Settled, values: Mapping[str, Any]
                 ) -> list[dict[str, Any]]:
    """The ledger row's `grants[]`: whether the unit's last attempt used each grant (RST-B28, RST-B29, RST-B30, IMD-B18)."""
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
    return _refuse(first.code, f"{first.code}: {first.message}", [f"{f.code}: {f.message}" for f in exc.findings],
                   tid)


def _root(target: Path) -> Path:
    return state_root_path(target)


def exit_file(state_root: Path, workflow: str, task_id: str) -> Path:
    return run_dir(state_root, workflow, task_id) / "exit.json"


def _content_version(spec: WorkflowSpec) -> str:
    from tempergraph.package.loader import full_version

    return full_version(spec)


def _stage(spec: WorkflowSpec, settings: RunSettings) -> tuple[str, bool]:
    from tempergraph.improve.promotion import stage_of

    return stage_of(spec, settings.caller)


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
                     settings=rst.workflow_settings(settled.resolved), origin=settings.origin, judge_state=settings.judge_state,
                     escalation_record=settings.escalation_record,
                     stage=_stage(spec, settings)[0], self_check_limit=int(rv.get("self_check_limit") or 3))
    if settings.sleep is not None:
        ctx.sleep = settings.sleep
    return ctx


def _observers(cap: rst.Capture) -> tuple[Any, list[str]]:
    """The observers the operator config names (EVT-B22, EVT-B23, EVT-B24); none is enabled by default."""
    if not cap.observers:
        return None, []
    from tempergraph.run.events import ObserverHub, register_observers

    found, missing = register_observers(names=cap.observers)
    return (ObserverHub(found) if found else None), missing


def _drive(spec: WorkflowSpec, task_id: str, root: Path, registry: Registry, settings: RunSettings,
           judges: Mapping[str, str], first_input: Any, settled: Settled, *,
           before: Callable[[Any], None] | None = None, executors: Mapping[str, str] | None = None,
           ruling_records: Sequence[Mapping[str, Any]] = (), rerun_of: Mapping[str, Any] | None = None,
           workspace: Mapping[str, Any] | None = None, skip_breakpoint: str | None = None) -> RunOutcome:
    """Run the graph from `first_input` while holding the lock, then turn the thread state into an exit."""
    tid = thread_id(spec.name, task_id)
    stops = [flow.step_node(u) for u in settings.pause_before if u != skip_breakpoint]  # FLX-B10
    cap = rst.capture(rst.load_files(root, settings.home or home_path()))  # operator config, per segment
    hub, missing = _observers(cap)
    log = RunLog(run_dir(root, spec.name, task_id) / "run.jsonl", observers=hub)
    stop = StopRequest()
    box: dict[str, Any] = {}
    main = main_checkout(root.parent)
    ctx = _context(spec, task_id, root, registry, settings, judges, log, stop, box, main, settled)
    ctx.capture = cap
    saver = open_saver(enginefile.checkpoint_of(root, spec.name, task_id))
    try:
        cw = compile_workflow(spec, EngineNodes(ctx), saver)
        cfg = cw.config(tid)
        if before is not None:
            before(cw)
        if callable(first_input):  # an answer to one of several pending gates is addressed after `before`
            first_input = first_input(cw)
        meta = (((cw.graph.get_state(cfg).values or {}).get("run") or {}).get("meta") or {})
        shape = diagram_model(spec)["digest"]
        was = enginefile.last(enginefile.read(root, spec.name, task_id))
        try:  # MIG-B8: the thread's engine record; never changes the run (OVR-B4)
            moved = enginefile.record(root, spec, task_id, content_version=_content_version(spec),
                                      shape_digest=shape, resumed=bool(meta))
        except OSError:
            moved = None
        log.write("run_started", origin=settings.origin, caller=dict(settings.caller),
                  alias=aliases.alias_of(root, tid), label=settings.label or meta.get("label"),
                  engine_version=ENGINE_VERSION, shape_digest=shape, **({"moved_from": moved} if moved else {}),
                  workflow_version=spec.version, content_version=_content_version(spec), plan_digest=shape,
                  executors={"steps": dict(executors or {}), "judges": dict(judges)},
                  settings_digest=settled.resolved.digest, profiles=list(settled.options.profiles),
                  **({"rerun_of": dict(rerun_of)} if rerun_of else {}),
                  **({"dry_run": True} if settings.dry_run or meta.get("dry_run") else {}),
                  overridden_keys=rst.overridden_keys(settled.resolved),
                  **({"capture_lowered": cap.lowered()} if cap.lowered() else {}),
                  **({"observers": list(cap.observers), "observers_missing": missing} if cap.observers else {}))
        rec: dict[str, Any] = {"settings_digest": settled.resolved.digest, "rows": rst.rows_json(settled.resolved),
                               "changed_keys": settled.changed, "stage": ctx.stage}
        if _stage(spec, settings)[1]:
            rec["unpromoted_pipeline"] = True
        if settled.changed:
            rec["caller"] = dict(settings.caller)
        log.write("settings_resolved", **rec)
        if moved and moved.get("workflow_version") and moved["workflow_version"] != _content_version(spec):  # MIG-B15
            log.write("workflow_changed", from_version=moved.get("workflow_version"),
                      to_version=_content_version(spec), units=enginefile.changed_units(was, spec))
        if workspace:
            workspace_record(log, workspace)
        for r in ruling_records:
            log.write("ruling", **r)
        for g in settled.grant_changes():
            log.write("grant", unit=g["unit"], capability=g.get("capability"), prefix=g.get("prefix"),
                      action=g["action"], answers=_answers(log.path, g), by=dict(settings.caller), via=settings.origin)
        outcome: RunOutcome
        with StopWatcher(root, spec.name, task_id, stop, poll_s=1.0) as watcher:
            box["w"] = watcher
            try:
                cw.graph.invoke(first_input, cfg, **({"interrupt_before": stops} if stops else {}))
                outcome = _settle(cw, cfg, spec, task_id, root, stops, log)
            except Drain as d:
                code = ExitCode.BUDGET_OR_INFRA if d.reason == "cost_cap" else ExitCode.STOPPED
                outcome = RunOutcome(exit_code=code, reason=d.reason, thread_id=tid,
                                     message=f"{tid} stopped at a boundary ({d.reason}); resume continues it")
        final = cw.graph.get_state(cfg).values or {}
        if outcome.exit_code is ExitCode.FINISHED and (final.get("workspace") or {}).get("state") == "released":
            workspace_record(log, final["workspace"])
        cost = CostTotals.from_json((final.get("run") or {}).get("cost"))
        orec = outcome_record.build(spec, final, log.path)
        if orec is not None and orec["verdict"] != "not_reached":
            log.write("outcome", **orec)  # OUT-B18, OUT-B19; a thread's latest `outcome` record is its record
        sup = supervision.build(root / "ledger.jsonl", log.path, tid, supervision.path_units(final))
        log.write("supervision", **sup)  # SUP-B10, before run_exit
        degraded = (final.get("run") or {}).get("degraded") or None  # FLX-B9: a fallback was taken
        deg = {"degraded": True, "degraded_unit": degraded.get("unit")} if degraded else {}
        outcome.degraded = bool(degraded)
        log.write("run_exit", exit_code=int(outcome.exit_code), reason=outcome.reason, cost=cost.to_json(),
                  cost_so_far=cost_so_far(cost.to_json()), **deg)
        try:
            write_json(exit_file(root, spec.name, task_id), {"schema_version": 1,
                                                              "exit_code": int(outcome.exit_code),
                                                              "reason": outcome.reason, **deg})
        except OSError as exc:  # OBS-B3: logging never changes the exit; one record of the failure is attempted
            log.write("engine_error", scope="exit_file", error=type(exc).__name__)
        ledger = Ledger(path=root / "ledger.jsonl")
        ledger.append({"kind": "run_segment", "thread_id": tid, "workflow": spec.name,
                       "workflow_version": spec.version, **join_keys(root, settings),
                       "exit_code": int(outcome.exit_code), "reason": outcome.reason,
                       "cost": cost.to_json(), "origin": settings.origin, "stage": _stage(spec, settings)[0],
                       "settings_digest": settled.resolved.digest, **deg,
                       "overridden_keys": rst.overridden_keys(settled.resolved),
                       "grants": _grants_used(spec, registry, settled, final),
                       "supervision": sup, **({"outcome": orec} if orec is not None else {})})
        if ledger.failures:
            log.write("engine_error", scope="ledger", error="write_failed")
        try:  # SIL-B8: every exit is recorded, no model call; never changes the exit (OVR-B4)
            from tempergraph.improve.record import record_exit

            seg_row = next((r for r in reversed(ledger_rows(root)) if r.get("kind") == "run_segment"
                            and r.get("thread_id") == tid), None)
            if seg_row is not None:
                summary = record_exit(root, spec, task_id, log.path, final, seg_row)
                from tempergraph.improve.reliability import after_exit

                summary["labels"] = after_exit(root, spec.name, task_id, seg_row)  # FBK-B9, FBK-B14
                log.write("finding_recorded", **summary)
                _loop(root, spec, task_id, tid, summary, settings, registry, judges,
                      operator_review=settled.run.get("session_review"), run_cost_usd=cost.reported + cost.estimated_only,
                      daily_cap_usd=settled.run.get("daily_cap_usd"), loop_model=settled.run.get("loop_model"),
                      loop_effort=settled.run.get("loop_effort"))
        except Exception as exc:  # noqa: BLE001
            log.write("engine_error", scope="improve", error=type(exc).__name__)
        outcome.thread_id = tid
        outcome.auto_reopen = int(settled.run.get("auto_reopen") or 0)
        return outcome
    finally:
        saver.conn.close()
        if hub is not None:
            hub.close()


def _loop(root: Path, spec: WorkflowSpec, task_id: str, tid: str, summary: Mapping[str, Any],
          settings: RunSettings, registry: Registry, judges: Mapping[str, str], *,
          operator_review: str | None = None, run_cost_usd: float = 0.0, daily_cap_usd: float | None = None,
          loop_model: str | None = None, loop_effort: str | None = None) -> None:
    """SIL-B1: hand the judged lenses to the detached loop child; `TEMPERGRAPH_LOOP=inline|off` for tests."""
    from tempergraph.improve import child

    if child.mode() == "off" or spec.builtin:
        return
    names = list(judges.values())
    executor = max(set(names), key=names.count) if names else spec.default_executor
    # `--dry-run` holds for the thread: any segment that started with it
    dry = settings.dry_run or last_record(run_dir(root, spec.name, task_id) / "run.jsonl", "run_started",
                                          dry_run=True) is not None
    if child.hand_off(root, spec, task_id, tid, summary, dry_run=dry, judge_executor=executor,
                      operator_review=operator_review, run_cost_usd=run_cost_usd,
                      trial=settings.origin == "trial", daily_cap_usd=daily_cap_usd, loop_model=loop_model,
                      loop_effort=loop_effort) is None:
        return
    if child.mode() == "inline":
        child.drain(registry=registry)
    else:
        child.launch()


def ledger_rows(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        lines = (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        with contextlib.suppress(ValueError):
            r = json.loads(ln)
            if isinstance(r, dict):
                out.append(r)
    return out


def join_keys(root: Path, settings: RunSettings) -> dict[str, Any]:
    """IMD-B5: the pseudonymous machine id and repository digest every ledger row carries."""
    from tempergraph import identity

    return {"machine": identity.machine_id(settings.home), "repo": identity.repo_id(main_checkout(root.parent))}


def workspace_record(log: RunLog, ws: Mapping[str, Any]) -> None:
    """EVT-B10 to EVT-B16 `workspace`: prepared, reused, attached, external_change or kept (WTR-B22, WTR-B26).

    The path goes to the local run log only; the ledger and exports never carry it.
    """
    boot = ws.get("bootstrap") or {}
    counts = {k: boot[k] for k in ("external_commits", "external_changed") if k in boot}
    log.write("workspace", action=ws.get("action") or "prepared", mode=ws.get("mode"),
              resolved_by=ws.get("resolved_by"), branch=ws.get("branch") or None,
              base_commit=ws.get("base_commit") or None, reason=ws.get("requested"), counts=counts,
              path=ws.get("path"))


def breakpoint_file(root: Path, workflow: str, task_id: str) -> Path:
    return run_dir(root, workflow, task_id) / "breakpoint.json"  # read by `durability.status.breakpoint_at`


def _settle(cw: Any, cfg: Mapping[str, Any], spec: WorkflowSpec, task_id: str, root: Path,
            stops: Sequence[str] = (), log: RunLog | None = None) -> RunOutcome:
    snap = snapshot(cw, cfg["configurable"]["thread_id"])
    state = classify_snapshot(snap, lock_held=False)
    tid = cfg["configurable"]["thread_id"]
    at = next((n for n in snap.next if n in stops), None) if state is ThreadState.UNFINISHED else None
    if at is not None:  # FLX-B10: nothing of the unit ran; no session and no attempt record
        unit = at.rsplit(".", 1)[0]
        u = spec.units.get(unit)
        prompt = u.step.prompt if u is not None and u.step is not None else None
        words = ["proceed", "stop"]
        payload: Any = {"kind": "breakpoint", "unit": unit, "item": None, "reason": "breakpoint", "decisions": words,
                   "prompt": str(getattr(prompt, "path", "") or "inline") if prompt is not None else None,
                   "resume": gatemod.resume_command(spec, task_id, words)}
        write_json(breakpoint_file(root, spec.name, task_id), {"schema_version": 1, **payload})
        if log is not None:
            log.write("pause", unit=unit, item=None, pause_kind="breakpoint", decisions=words,
                      resume=payload["resume"], reason="breakpoint",
                      cost_so_far=cost_so_far((snap.values.get("run") or {}).get("cost")))
        return RunOutcome(exit_code=ExitCode.PAUSED, reason="breakpoint", payload=payload,
                          message=f"{tid} is paused before {unit}")
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
    return _reopening(_start(spec, task_id, inputs, target, registry, settings), spec, task_id, target, registry,
                      settings)


def _bad_breakpoint(spec: WorkflowSpec, settings: RunSettings) -> RunOutcome | None:
    """FLX-B11: `--pause-before` naming a unit the workflow does not have is refused before spend."""
    for name in settings.pause_before:
        if name in spec.units or name == flow.OUTCOME_UNIT and spec.outcome is not None:
            continue
        if name.split(".", 1)[0] in spec.units:
            return _refuse("not_in_release", f"--pause-before {name}: a breakpoint on one item of a map is not "
                                             "built in this release; name the unit")
        return _refuse("breakpoint_unknown", f"--pause-before {name}: the workflow has no such unit")
    return None


def needs_git(spec: WorkflowSpec, settings: RunSettings) -> list[str]:
    """WSP-B15 to WSP-B18: what a run outside a git repository cannot use; empty when it can start."""
    out: list[str] = []
    if settings.carry:
        out.append("--carry (run state on a branch)")
    out += subworkflow.unit_reasons(spec)
    out += subworkflow.needs_git(spec)  # SWF-B6: a child, or a child of a child, that needs git
    return out


def subworkflow_stop(spec: WorkflowSpec) -> RunOutcome | None:
    """SWF-B11: a workflow with a sub-workflow unit stops here until running a child is built, after every other refusal."""
    message = subworkflow.stop_message(spec)
    return None if message is None else _refuse("not_in_release", message)


def _start(spec: WorkflowSpec, task_id: str, inputs: Mapping[str, str], target: Path, registry: Registry,
           settings: RunSettings) -> RunOutcome:
    tid = thread_id(spec.name, task_id)
    bad = _bad_breakpoint(spec, settings)
    if bad is not None:
        return bad
    try:
        root = _root(target)
    except NotInRepository as exc:
        return _refuse("not_git", str(exc))
    if classify(root, spec, task_id) is not ThreadState.NONE:
        return _refuse("thread_exists", f"{tid} already exists; resume it with `tempergraph resume {spec.name} "
                                        f"{task_id}` or start a new thread with another task id", tid=tid)
    try:
        settings = decided(settings, deciding=any(rst.is_widening(k) for k in settings.all_flags()),
                           words=("grant",))
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
                                 prefix=str(rv["worktree.branch_prefix"]), base=str(rv.get("worktree.base") or "head"))
    except WorkspaceRefused as exc:
        return _refuse(exc.word, str(exc), tid=tid)
    if plan.main is None:  # WSP-B15 to WSP-B18: what needs git is refused before anything is created
        needs = needs_git(spec, settings)
        if needs:
            return _refuse("needs_git", f"outside a git repository this run cannot use {needs[0]}",
                           [f"needs_git: {n}" for n in needs], tid)
        guarded = any(u.gate is not None and u.gate.judge is not None for u in spec.units.values())
        if guarded and manifestmod.count_over(plan.path):
            return _refuse("workspace_too_large", f"{plan.path} holds more than {manifestmod.MAX_FILES} files; "
                           "outside git the guard cannot watch it for a read-only session", tid=tid)
    carry_remote = None
    if settings.carry:  # CAR-B5, CAR-B8, CAR-B11, CAR-B6: refused at start without a remote, before anything is created
        try:
            carry_remote = carrymod.remote_of(root.parent)
        except carrymod.CarryRefused as exc:
            return _refuse(exc.code, str(exc), tid=tid)
    stopped = subworkflow_stop(spec)  # SWF-B11: nothing is created for a run that cannot start a child
    if stopped is not None:
        return dataclasses.replace(stopped, thread_id=tid)
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
        if carry_remote:
            carrymod.set_marker(root, spec.name, task_id, on=True, remote=carry_remote, state="on")
        if plan.main is None:  # the thread's first manifest: what `changed_paths` is measured against
            with contextlib.suppress(OSError, manifestmod.TooManyFiles):
                write_json(run_dir(root, spec.name, task_id) / "manifest.json",
                           {"schema_version": 1, "files": {k: list(v) for k, v in manifestmod.scan(plan.path).items()}})
        RunLog(run_dir(root, spec.name, task_id) / "run.jsonl").write(
            "task", chars=sum(len(v) for v in inputs.values()), request=clip(scrub(inputs.get("request", "")), 200))
        initial = {"request": {"task_id": task_id, "inputs": dict(inputs)}, "workspace": rec.to_json(),
                   "run": {"meta": {"origin": settings.origin, "label": clip(scrub(settings.label or ""), 80) or None,
                                    **({"dry_run": True} if settings.dry_run else {})},
                           "options": settled.snapshot_json()}}
        out = _drive(spec, task_id, root, registry, settings, rep.judges, initial, settled,
                     executors=rep.step_executors, workspace=rec.to_json())
        out.warnings = list(plan.warnings) + [f"{w.code}: {w.message}" for w in rep.warnings]
        return _carry_exit(root, spec, task_id, settings, out)
    finally:
        lock.release()


def _carry_exit(root: Path, spec: WorkflowSpec, task_id: str, settings: RunSettings, out: RunOutcome) -> RunOutcome:
    """CAR-B8, CAR-B3: push the new state at a pause or an unfinished exit, delete the branch at the finish. The
    exit never changes (OVR-B4); what is left to do is a warning and the thread's carry record."""
    try:
        warn = carrymod.after_exit(root, root.parent, spec.name, task_id, exit_code=int(out.exit_code),
                                   workflow_version=_content_version(spec),
                                   machine=join_keys(root, settings)["machine"])
    except Exception as exc:  # noqa: BLE001
        warn = f"carry: failed ({type(exc).__name__})"
    if warn:
        out.warnings.append(warn)
    return out


def _live(root: Path, spec: WorkflowSpec, tid: str) -> bool:
    w, _, task = tid.partition("/")
    if w != spec.name:
        return is_held(lock_path(root, w, task))
    return classify(root, spec, task) not in (ThreadState.FINISHED, ThreadState.NONE)


def resume(spec: WorkflowSpec, task_id: str, target: Path, registry: Registry, *, decision: str | None = None,
           feedback: str | None = None, settings: RunSettings | None = None) -> RunOutcome:
    settings = settings or RunSettings()
    out = _resume(spec, task_id, target, registry, decision=decision, feedback=feedback, settings=settings)
    return _reopening(out, spec, task_id, target, registry, settings)


# BUD-B6: the stop reasons an automatic re-open answers (spent retries, a step timeout or an infra failure).
REOPEN_REASONS = frozenset({"budget", "infra"})
ENGINE_CALLER: Mapping[str, Any] = {"kind": "engine", "confidence": "attested", "decided_by": "engine",
                                    "relay": "none", "host": "engine", "host_session": None, "caller_app": None,
                                    "parent": None, "schedule": None, "trace_id": None, "evidence": []}


def _reopens(root: Path, tid: str) -> int:
    path = root / "ledger.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    n = 0
    for ln in lines:
        with contextlib.suppress(ValueError):
            r = json.loads(ln)
            n += isinstance(r, dict) and r.get("kind") == "intervention" and r.get("thread_id") == tid \
                and r.get("cause") == "auto_reopen"
    return n


def _reopening(out: RunOutcome, spec: WorkflowSpec, task_id: str, target: Path, registry: Registry,
               settings: RunSettings) -> RunOutcome:
    """BUD-B6: re-open a stopped run at most `run.auto_reopen` times on the thread, as a retry given in advance.

    Never answers a pause, never undoes a person's stop or a cost cap drain.
    """
    warnings = list(out.warnings)
    while (out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason in REOPEN_REASONS and out.auto_reopen > 0):
        try:
            root = _root(target)
        except NotInRepository:
            break
        if _reopens(root, thread_id(spec.name, task_id)) >= out.auto_reopen:
            break
        engine = dataclasses.replace(settings, caller=dict(ENGINE_CALLER, call_id=uuid.uuid4().hex), relayed=False,
                                     flags={}, profiles=None, unset=(), reload_settings=False, ruling=False,
                                     ruling_for=(), revoke_rulings=(), accept_external=False)
        nxt = _resume(spec, task_id, target, registry, decision="retry", feedback=None, settings=engine)
        if nxt.exit_code is ExitCode.USAGE:
            warnings.append(f"auto_reopen_refused: {nxt.reason}")
            break
        warnings.append(f"auto_reopen: {out.reason}")
        out = nxt
        warnings.extend(out.warnings)
    out.warnings = warnings
    return out


def _resume(spec: WorkflowSpec, task_id: str, target: Path, registry: Registry, *, decision: str | None,
            feedback: str | None, settings: RunSettings) -> RunOutcome:
    tid = thread_id(spec.name, task_id)
    try:
        root = _root(target)
    except NotInRepository as exc:
        return _refuse("not_git", str(exc))
    action, detail = enginefile.at_resume(root, spec.name, task_id, write=False)  # MIG-B12, MIG-B13, MIG-B14; the CLI dispatches
    if action != "move":
        return _refuse("engine_pinned", str(detail) if action == "refuse" else
                       f"{tid} resumes on engine {detail}, not this one", tid=tid)
    bad = _bad_breakpoint(spec, settings)
    if bad is not None:
        return bad
    state = classify(root, spec, task_id)
    if state in (ThreadState.NONE, ThreadState.RUNNING, ThreadState.FINISHED):
        hint = {"none": "no such thread", "running": "it is running",
                "finished": f"it finished; `tempergraph rerun {spec.name} {task_id}` starts a linked thread"}
        return _refuse(str(state), f"{tid}: {hint[str(state)]}", tid=tid)
    try:
        d = Decision.parse(decision) if decision else None
    except ValueError as exc:
        return _refuse("decision_invalid", str(exc), tid=tid)
    if feedback and len(feedback) > gatemod.FEEDBACK_LIMIT:
        return _refuse("feedback_too_long", f"feedback is {len(feedback)} characters; at most "
                                            f"{gatemod.FEEDBACK_LIMIT}", tid=tid)
    if settings.ruling and not feedback:
        return _refuse("ruling_without_text", "--ruling needs --feedback or --feedback-file", tid=tid)
    unknown = [u for u in settings.ruling_for if u not in spec.units]
    if unknown:
        return _refuse("ruling_for_unknown", f"--ruling-for names no unit {', '.join(unknown)}", tid=tid)
    if settings.escalate:
        if d is not None and d.word != "retry":
            return _refuse("decision_invalid", "--escalate goes with a retry, not another decision", tid=tid)
        d = Decision.parse("retry")
    human_payload: dict[str, Any] = {"feedback": feedback, "caller": dict(settings.caller),
                                     "escalate": settings.escalate,
                                     "ruling": {"applies_to": list(settings.ruling_for)} if settings.ruling else None,
                                     "revoke": list(settings.revoke_rulings)}
    declared = spec
    ensure_state_root(root)  # MIG-B9, MIG-B10, MIG-B5: a resume is a writing verb, so an older layout moves forward here
    lock = RunLock(lock_path(root, spec.name, task_id))
    try:
        lock.acquire()
    except LockHeld:
        return _refuse("running", f"{tid} is running", tid=tid)
    try:
        stale = take_stop(root, spec.name, task_id, stale=True)
        saver = open_saver(enginefile.checkpoint_of(root, spec.name, task_id))
        try:
            cw = compile_workflow(with_outcome(declared), _Inert(), saver)
            snap = snapshot(cw, tid)
            values = snap.values
        finally:
            saver.conn.close()
        was = enginefile.last(enginefile.read(root, spec.name, task_id))
        if was.get("units") and was.get("workflow_version") != _content_version(declared):  # MIG-B15
            pending = [n.rsplit(".", 1)[0] for n, _ in snap.interrupts] or \
                [n.rsplit(".", 1)[0] for n in snap.next if n.rsplit(".", 1)[0] in was["units"]]
            if not pending:  # the unit it waits at is gone from the new graph
                at = last_record(run_dir(root, spec.name, task_id) / "run.jsonl", "pause")
                pending = [str(at["unit"])] if at and at.get("unit") else []
            broken = enginefile.breaks(was, with_outcome(declared), values, list(dict.fromkeys(pending)))
            if broken:
                return _refuse("workflow_changed", f"{tid} cannot resume on workflow version "
                               f"{_content_version(declared)}: {'; '.join(broken)}. Reinstall the version it ran "
                               f"on ({was.get('workflow_version')}) and resume, or start a new thread", broken,
                               tid=tid)
        try:
            pause = last_record(run_dir(root, spec.name, task_id) / "run.jsonl", "pause")
            deciding = bool(d is not None or feedback or settings.ruling or settings.revoke_rulings
                            or any(rst.is_widening(k) for k in settings.all_flags()))
            settings = decided(settings, deciding=deciding, words=(d.word,) if d else ("grant",),
                               since=(pause or {}).get("ts"))
            human_payload["caller"] = dict(settings.caller)
            if settings.escalate:
                if not (pause or {}).get("escalation"):
                    return _refuse("no_escalation_offered", f"{tid} offers no escalation", tid=tid)
                if settings.caller and not provenance.may_widen(settings.caller):  # LAD-B6, PRV-B21, PRV-B22
                    return _refuse("escalate_needs_person",
                                   "--escalate is a person's choice: run it at a terminal, or relay it", tid=tid)
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
        if d is not None and d.word == "rewind" and d.unit and not settings.accept_external:
            from tempergraph.run.rerun import cleared_units, external_effects

            effects = external_effects(spec, cleared_units(spec, d.unit, values), values)
            if effects:
                return _refuse("external_effects", f"rewind:{d.unit} clears units with external effects: "
                                                   f"{'; '.join(effects)}; pass --accept-external", effects, tid=tid)
        try:
            gatemod.check_rulings(values, feedback if settings.ruling else None, settings.revoke_rulings)
        except gatemod.DecisionRefused as exc:
            return _refuse("ruling_refused", str(exc), tid=tid)
        skip_bp: str | None = None
        row_decision: str | None = None
        if state is ThreadState.PAUSED and not snap.interrupts:  # an operator's breakpoint (FLX-B10)
            bp = breakpoint_at(root, spec.name, task_id) or {}
            unit = str(bp.get("unit") or "")
            if d is None or d.word not in ("proceed", "stop"):
                return _refuse("decision_missing" if d is None else "decision_refused",
                               f"{tid} is paused before {unit}; pass --decision proceed or stop", tid=tid)
            touch = (unit, "breakpoint", "")
            with contextlib.suppress(OSError):
                breakpoint_file(root, spec.name, task_id).unlink()
            if d.word == "stop":  # the segment ends; the thread stays unfinished and a resume continues it
                intervention(root, spec, task_id, touch, d, feedback, settings, settled)
                RunLog(run_dir(root, spec.name, task_id) / "run.jsonl").write(
                    "human", unit=unit, decision="stop", caller=dict(settings.caller), feedback=False)
                write_json(exit_file(root, spec.name, task_id), {"schema_version": 1,
                                                                  "exit_code": int(ExitCode.STOPPED),
                                                                  "reason": "person"})
                return RunOutcome(exit_code=ExitCode.STOPPED, reason="person", thread_id=tid,
                                  message=f"{tid} stopped before {unit}; resume continues it")
            first_input, before, skip_bp = None, None, unit
        elif state is ThreadState.PAUSED:
            gates: dict[str, dict[str, Any]] = {n.rsplit(".", 1)[0]: (p if isinstance(p, dict) else {})
                                                for n, p in snap.interrupts}
            if len(gates) > 1 and settings.unit not in gates:  # HUM-B3: each gate is answered by unit
                lines = [f"{u}: tempergraph resume {spec.name} {task_id} --unit {u} --decision "
                         f"<{'|'.join(p.get('decisions') or [])}>" for u, p in gates.items()]
                return _refuse("unit_missing", f"{tid} has {len(gates)} pending gates; name one with --unit",
                               lines, tid=tid)
            if settings.unit is not None and settings.unit not in gates:
                return _refuse("unit_unknown", f"{tid} is not paused at {settings.unit}", tid=tid)
            unit = settings.unit or next(iter(gates))
            pause = gates[unit]
            kind = str(pause.get("kind") or "escalation")
            touch = (unit, kind, str(pause.get("reason") or ""))
            extra: dict[str, Any] = {}
            if settings.apply_deadline:  # FLX-B8
                if d is not None or settings.answers:
                    return _refuse("decision_refused", "--apply-deadline goes with no decision", tid=tid)
                if settings.caller.get("kind") == "orchestrator":
                    return _refuse("deadline_needs_person", "an orchestration supervisor never applies a deadline",
                                   tid=tid)
                due = str(pause.get("deadline_at") or "")
                if not due or datetime.fromisoformat(due) > datetime.now(datetime.fromisoformat(due).tzinfo):
                    return _refuse("deadline_not_passed", f"{tid} has no overdue pause at {unit}"
                                   + (f"; its deadline is {due}" if due else ""), tid=tid)
                row_decision = "deadline"
                d = Decision(word="proceed")  # only for the intervention row's shape; the node applies the deadline
                first_input = resume_input({"decision": "deadline", **human_payload})
            elif kind == "input":
                got = _answers_step(spec, task_id, root, unit, values, d, settings)
                if isinstance(got, RunOutcome):
                    if got.exit_code is ExitCode.PAUSED:  # accepted, still asking: the graph does not move
                        intervention(root, spec, task_id, touch, Decision(word="answer", name="", value=""),
                                     feedback, settings, settled)
                    got.thread_id = tid
                    return got
                extra = got
                d = d or Decision(word="proceed")
            elif d is None:
                return _refuse("decision_missing", f"{tid} is paused at {', '.join(gates)}; pass --decision",
                               tid=tid)
            if row_decision is None:
                try:
                    gatemod.check_decision(spec, unit, values, d, human_cap=human_cap)
                except gatemod.DecisionRefused as exc:
                    return _refuse("decision_refused", str(exc), tid=tid)
                payload_in = {"decision": str(d), **human_payload, **extra}
                if len(gates) == 1:
                    first_input = resume_input(payload_in)
                else:
                    def first_input(cw2: Any, payload_in: dict[str, Any] = payload_in, unit: str = unit) -> Any:
                        ids = snapshot(cw2, tid).interrupt_ids
                        return resume_input({i: payload_in for i, u in ids.items() if u == unit})
            before = None
        elif state is ThreadState.UNFINISHED:
            if d is not None and d.word != "rewind":
                return _refuse("decision_refused", "an unfinished thread accepts only `rewind:<unit>`", tid=tid)
            first_input, before = None, None
            touch = None
            if d is not None:
                unit = _last_unit(values)
                before = _human_update(spec, unit, values, d, human_payload)
                touch = (unit, "unfinished", "rewind")
            elif feedback or settings.revoke_rulings:  # RRN-B4: the pending unit's next attempt and its judge
                waiting = next((n.rsplit(".", 1)[0] for n in snap.next if n.endswith(".step")), _last_unit(values))
                before = _pending_update(spec, waiting, values, human_payload)
        else:  # stopped
            if d is None or d.word not in ("retry", "back", "rewind"):
                return _refuse("decision_refused", "a stopped thread re-opens with retry, back:<unit> or rewind:<unit>",
                               tid=tid)
            unit = str(((values.get("run") or {}).get("stopped") or {}).get("unit") or _last_unit(values))
            try:
                gatemod.check_decision(spec, unit, values, d, human_cap=human_cap)
            except gatemod.DecisionRefused as exc:
                return _refuse("decision_refused", str(exc), tid=tid)
            first_input, before = None, _human_update(spec, unit, values, d, human_payload)
            reason = str(((values.get("run") or {}).get("stopped") or {}).get("reason") or "")
            touch = (unit, "stopped", reason)
        carry_warnings: list[str] = []
        if settings.carry and not carrymod.is_on(root, spec.name, task_id):
            try:
                carrymod.set_marker(root, spec.name, task_id, on=True, remote=carrymod.remote_of(root.parent),
                                    state="on")
            except carrymod.CarryRefused as exc:
                return _refuse(exc.code, str(exc), tid=tid)
        ws = values.get("workspace") or {}
        if carrymod.is_on(root, spec.name, task_id):  # CAR-B9, CAR-B4: the lease, before the first attempt
            try:
                carry_warnings = carrymod.before_resume(
                    root, root.parent, spec.name, task_id, workflow_version=_content_version(declared),
                    machine=join_keys(root, settings)["machine"])
            except carrymod.CarryRefused as exc:
                return _refuse(exc.code, str(exc), tid=tid)
            ws = carrymod.relocate(root, root.parent, spec.name, task_id, ws) if ws else ws
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
            intervention(root, spec, task_id, touch, d, feedback, settings, settled, decision=row_decision)

        def before_all(cw2: Any) -> None:
            cfg = cw2.config(tid)
            for update in ({"run": {"options": settled.snapshot_json()}},
                           *([{"workspace": ws_update}] if ws_update is not None else [])):
                if not update_values(cw2, cfg, update):  # several nodes pending: the first to run carries it
                    cw2.engine.defer(update)
            if prior is not None:
                prior(cw2)

        out = _drive(spec, task_id, root, registry, settings, rep.judges, first_input, settled, before=before_all,
                     executors=rep.step_executors, workspace=ws_update, skip_breakpoint=skip_bp, ruling_records=_ruling_records(spec, values, d, touch, settings,
                                                                                  feedback, snap.next))
        if stale is not None:
            out.warnings.append("stale_stop_request_removed")
        out.warnings.extend(carry_warnings)
        return _carry_exit(root, spec, task_id, settings, out)
    finally:
        lock.release()


RESCUE_PAUSES = frozenset({"escalation", "budget", "tool_access"})


def touches(pause_kind: str, stop_reason: str, d: Decision) -> list[dict[str, str]]:
    """SUP-B9 touch classes of one accepted resume."""
    out: list[dict[str, str]] = []
    if pause_kind == "approval":
        out.append({"class": "designed", "action": "approve"})
    elif pause_kind == "input" and d.word != "stop":
        out.append({"class": "designed", "action": "answer"})
    elif pause_kind == "event_wait" and d.word != "stop":
        out.append({"class": "designed", "action": "event"})
    elif pause_kind == "breakpoint" and d.word != "stop":
        out.append({"class": "steer", "action": "breakpoint"})
    elif pause_kind in RESCUE_PAUSES or pause_kind == "stopped" and stop_reason in ("budget", "infra"):
        out.append({"class": "rescue", "action": "decide"})
    if d.word == "rewind":
        out.append({"class": "steer", "action": "rewind"})
    elif d.word == "stop":
        out.append({"class": "steer", "action": "stop"})
    elif pause_kind == "stopped" and stop_reason not in ("budget", "infra") and not out:
        out.append({"class": "steer", "action": "decide"})
    return out


def _answers_step(spec: WorkflowSpec, task_id: str, root: Path, unit: str, values: Mapping[str, Any],
                  d: Decision | None, settings: RunSettings) -> dict[str, Any] | RunOutcome:
    """ASK-B8: validate and keep this resume's answers. Returns the human node's extra payload when the set
    is complete and the check passes, else the outcome of this call: a refusal, or `still asking` (exit 3)."""
    from tempergraph.run import asking

    tid = thread_id(spec.name, task_id)
    u = spec.units[unit]
    assert u.ask is not None
    if d is not None and d.word == "stop":
        return {}
    if d is not None and d.word != "proceed":
        return _refuse("decision_refused", "an ask accepts answer:<name>=<value>, proceed and stop", tid=tid)
    if d is None and not settings.answers:
        return _refuse("decision_missing", f"{tid} is asking at {unit}; pass --decision answer:<name>=<value>",
                       tid=tid)
    qs = [asking.of_json(q) for q in ((values.get("attempts") or {}).get(unit) or {}).get("questions") or []]
    ws = values.get("workspace") or {}
    workdir = Path(str(ws.get("path"))) if ws.get("path") else root.parent
    try:
        new = asking.accept(qs, settings.answers, workdir)
    except asking.AnswerRefused as exc:
        return _refuse("answer_refused", str(exc), tid=tid)
    path = asking.answers_path(run_dir(root, spec.name, task_id), unit)
    merged = {**asking.load(path), **new}
    if d is not None and asking.unanswered(qs, merged, defaults=True):  # `proceed` needs the set complete
        return _refuse("answers_missing", f"{unit} still needs "
                       f"{', '.join(asking.unanswered(qs, merged, defaults=True))}", tid=tid)
    log = RunLog(run_dir(root, spec.name, task_id) / "run.jsonl")
    missing = asking.unanswered(qs, merged, defaults=False) if d is None else []
    final = asking.complete(qs, merged)
    problems = [] if missing else asking.check_problems(u.ask, final)
    log.write("answers", unit=unit, answered=sorted(new), missing=missing, check_passed=not problems and not missing,
              caller=dict(settings.caller))
    if missing or problems:
        asking.store(path, unit, merged, done=False)
        payload = {"kind": "input", "unit": unit, "questions": asking.shown(qs, merged), "missing": missing,
                   "check_problems": problems,
                   "resume": f"tempergraph resume {spec.name} {task_id} --decision answer:<name>=<value>"}
        why = f"still needs {', '.join(missing)}" if missing else f"the answers check: {'; '.join(problems)}"
        return RunOutcome(exit_code=ExitCode.PAUSED, reason="input", payload=payload,
                          message=f"{tid}: answers kept; {unit} {why}")
    asking.store(path, unit, final, done=True)
    return {"answers": final, "answers_path": str(path)}


def intervention(root: Path, spec: WorkflowSpec, task_id: str, touch: tuple[str, str, str], d: Decision,
                 feedback: str | None, settings: RunSettings, settled: Settled | None = None, *,
                 decision: str | None = None) -> dict[str, Any]:
    """HUM-B6: one metadata-only ledger row per accepted resume, appended before the graph runs."""
    unit, kind, reason = touch
    pause = last_record(run_dir(root, spec.name, task_id) / "run.jsonl", "pause", unit=unit)
    wait_s = None
    engine = settings.caller.get("kind") == "engine"  # an automatic re-open waits on no one (SUP-B9)
    if pause and pause.get("ts") and not engine:
        with contextlib.suppress(ValueError, TypeError):
            wait_s = round((datetime.now(datetime.fromisoformat(pause["ts"]).tzinfo)
                            - datetime.fromisoformat(pause["ts"])).total_seconds(), 1)
    row = {"kind": "intervention", "id": uuid.uuid4().hex, "thread_id": thread_id(spec.name, task_id),
           "workflow": spec.name, "workflow_version": spec.version, **join_keys(root, settings), "unit": unit, "caller": dict(settings.caller),
           "touches": [{"class": "engine", "action": "reopen"}] if engine
           else [{"class": "designed", "action": "deadline"}] if decision == "deadline"
           else touches(kind, reason if kind == "stopped" else "", d), "pause_kind": kind,
           "decision": decision or d.word + (f":{d.unit}" if d.unit else ""), "wait_s": wait_s, "feedback": bool(feedback) and not settings.ruling,
           "ruling": settings.ruling, "settings_changed": list(settled.changed) if settled else [],
           "grants": [{k: v for k, v in g.items() if k != "key"} for g in (settled.grant_changes() if settled else [])],
           "cause": "auto_reopen" if engine else reason or kind}
    Ledger(path=root / "ledger.jsonl").append(row)
    return row


def _last_unit(values: Mapping[str, Any]) -> str:
    units = ((values.get("run") or {}).get("path") or {}).get("units") or []
    return str(units[-1]) if units else ""


def _ruling_records(spec: WorkflowSpec, values: Mapping[str, Any], d: Decision | None,
                    touch: tuple[str, str, str] | None, settings: RunSettings, feedback: str | None,
                    pending: Sequence[str]) -> list[dict[str, Any]]:
    """EVT `ruling`: given and revoked rulings of this resume, ids and lengths only, never the text."""
    out: list[dict[str, Any]] = [{"id": rid, "action": "revoked", "by": dict(settings.caller)}
                                 for rid in settings.revoke_rulings]
    if settings.ruling and feedback:
        if d is not None and touch is not None:
            at = gatemod.decision_target(spec, touch[0], d)
        else:
            at = next((n.rsplit(".", 1)[0] for n in pending if n.endswith(".step")), _last_unit(values))
        out.append({"id": f"r{len(values.get('rulings') or {}) + 1}", "action": "given", "given_at": at,
                    "applies_to": list(settings.ruling_for), "by": dict(settings.caller), "chars": len(feedback)})
    return out


def _pending_update(spec: WorkflowSpec, unit: str, values: Mapping[str, Any], payload: Mapping[str, Any]
                    ) -> Callable[[Any], None]:
    """Feedback, a ruling or a revocation on an unfinished thread, with no decision (RRN-B14, RRN-B15, RRN-B4)."""

    def apply(cw: Any) -> None:
        w: dict[str, Any] = {}
        rulings = gatemod.ruling_writes(values, payload, unit)
        if rulings:
            w["rulings"] = rulings
        if payload.get("feedback") and not payload.get("ruling"):
            w["feedback"] = {unit: {"text": payload["feedback"], "as": "feedback"}}
        if w:
            cw.graph.update_state(cw.config(thread_id(spec.name, str((values.get("request") or {}).get("task_id")))),
                                  w)

    return apply


def _human_update(spec: WorkflowSpec, unit: str, values: Mapping[str, Any], d: Decision,
                  payload: Mapping[str, Any]) -> Callable[[Any], None]:
    """Re-open a stopped thread, or rewind an unfinished one, through the human node's own update."""

    def apply(cw: Any) -> None:
        w = gatemod.apply_decision(spec, unit, values, {"decision": str(d), **payload})
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
