"""`rerun`: a new thread forked from an earlier one, linked to its source (RRN §2.4; ADR-0073).

The fork is LangGraph's time travel: the source's checkpoint just before the unit's step node on its last
visit is copied to the new thread id, and the unit and everything after it are cleared as a trip back. The
source's history is never written. `--from start` starts the new thread from the source's resolved input.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph import git as gitmod
from tempergraph.compiler import compile_workflow
from tempergraph.contracts import ThreadState, WorkflowSpec, thread_id
from tempergraph.docs import write_json
from tempergraph.durability import engine_file
from tempergraph.durability.checkpoint import open_readonly
from tempergraph.durability.lock import LockHeld, RunLock
from tempergraph.durability.status import classify
from tempergraph.executors.preflight import preflight
from tempergraph.executors.registry import Registry
from tempergraph.git import is_safe_ref
from tempergraph.model import flow
from tempergraph.run import gate as gatemod
from tempergraph.run.log import Ledger, last_record
from tempergraph.run.outcome import with_outcome
from tempergraph.run.runner import (
    RunOutcome,
    RunSettings,
    SettingsRefused,
    _drive,
    _Inert,
    _refuse,
    _refuse_settings,
    _reopening,
    _root,
    join_keys,
    settle_resume,
)
from tempergraph.store.layout import NotInRepository, ensure_state_root, lock_path, run_dir
from tempergraph.workspace import (
    LOCK_REASON,
    WorkspaceRecord,
    WorkspaceRefused,
    attach_workspace,
    flat_name,
    prepare_workspace,
    resolve_workspace,
    sibling_root,
)

EXTERNAL_KINDS = frozenset({"pull_request", "tracker_issue", "wiki_page"})


@dataclasses.dataclass(kw_only=True)
class Fork:
    values: dict[str, Any]
    config: dict[str, Any] | None  # the source checkpoint's config; None for `--from start`
    writer: str | None  # the node that wrote that checkpoint
    checkpoint_id: str | None


def external_effects(spec: WorkflowSpec, units: list[str], values: Mapping[str, Any]) -> list[str]:
    """`<unit>: <kind>` for every unit in `units` that produced an external artifact or ran an external script."""
    out: list[str] = []
    arts = values.get("artifacts") or {}
    attempts = values.get("attempts") or {}
    for unit in units:
        u = spec.units.get(unit)
        if u is None or not attempts.get(unit):
            continue
        if u.step is not None:
            for key, kind in u.step.produces.items():
                if isinstance(kind, str) and kind in EXTERNAL_KINDS and key in (arts.get(unit) or {}):
                    out.append(f"{unit}: {kind}")
            scripts = [*u.step.before, *u.step.after]
        else:
            scripts = [u.script] if u.script is not None else []
        if any(sc.side_effects == "external" for sc in scripts):
            out.append(f"{unit}: external script")
    return out


def cleared_units(spec: WorkflowSpec, unit: str, values: Mapping[str, Any]) -> list[str]:
    """`unit` and every later unit on the thread's path (RRN §2.3, §2.4)."""
    order = flow.effective_order(spec)
    path = list(((values.get("run") or {}).get("path") or {}).get("units") or [])
    later = order[order.index(unit):] if unit in order else [unit]
    return [u for u in later if u in path]


def find_fork(spec: WorkflowSpec, root: Path, source: str, start_at: str) -> Fork | None:
    """The checkpoint just before `start_at`'s step node on its last visit, read-only."""
    with open_readonly(engine_file.checkpoint_of(root, spec.name, source.partition("/")[2])) as saver:
        if saver is None:
            return None
        cw = compile_workflow(with_outcome(spec), _Inert(), saver)
        history = list(cw.graph.get_state_history(cw.config(source)))
        if start_at == "start":
            first = history[-1] if history else None
            return Fork(values=dict(first.values or {}), config=None, writer=None, checkpoint_id=None) \
                if first is not None else None
        node = flow.step_node(start_at)
        for snap in history:  # newest first: the first hit is the unit's last visit
            if node in tuple(snap.next or ()):
                writes = (snap.metadata or {}).get("writes") or {}
                writer = next(iter(writes), None) if len(writes) == 1 else None
                return Fork(values=dict(snap.values or {}), config=dict(snap.config), writer=writer,
                            checkpoint_id=str((snap.config.get("configurable") or {}).get("checkpoint_id") or ""))
    return None


def next_rerun_id(root: Path, spec: WorkflowSpec, source_task: str) -> tuple[str, int]:
    n = 1
    while classify(root, spec, f"{source_task}~r{n}") is not ThreadState.NONE:
        n += 1
    return f"{source_task}~r{n}", n


def rerun(spec: WorkflowSpec, source_task: str, target: Path, registry: Registry, *, start_at: str,
          feedback: str | None = None, settings: RunSettings | None = None, task_id: str | None = None,
          workspace_from: str = "current", same_branch: bool = False, drop_rulings: bool = False,
          accept_external: bool = False, check: bool = False) -> RunOutcome | dict[str, Any]:
    """RRN §2.4. With `check`, returns the plan document and creates nothing (contract C13)."""
    settings = dataclasses.replace(settings or RunSettings(), origin="rerun")
    out = _rerun(spec, source_task, target, registry, start_at=start_at, feedback=feedback, settings=settings,
                 task_id=task_id, workspace_from=workspace_from, same_branch=same_branch, drop_rulings=drop_rulings,
                 accept_external=accept_external, check=check)
    if isinstance(out, RunOutcome) and out.thread_id:  # BUD-B6 holds for the new thread too
        return _reopening(out, spec, out.thread_id.partition("/")[2], target, registry, settings)
    return out


def _rerun(spec: WorkflowSpec, source_task: str, target: Path, registry: Registry, *, start_at: str,
           feedback: str | None, settings: RunSettings, task_id: str | None, workspace_from: str,
           same_branch: bool, drop_rulings: bool, accept_external: bool, check: bool
           ) -> RunOutcome | dict[str, Any]:
    src = thread_id(spec.name, source_task)
    try:
        root = _root(target)
    except NotInRepository:
        return _refuse("not_git", "not inside a git repository")
    state = classify(root, spec, source_task)
    if state in (ThreadState.NONE, ThreadState.RUNNING):
        return _refuse(str(state), f"{src}: a rerun needs a source that exists and is not running", tid=src)
    if same_branch and state is not ThreadState.FINISHED:
        return _refuse("same_branch_not_finished", f"{src}: --same-branch needs a finished source", tid=src)
    if feedback and len(feedback) > gatemod.FEEDBACK_LIMIT:
        return _refuse("feedback_too_long", f"feedback is over {gatemod.FEEDBACK_LIMIT} characters", tid=src)
    if start_at != "start" and start_at not in spec.units:
        return _refuse("units_behind", f"{start_at} is not a unit of {spec.name} {spec.version}", tid=src)
    fork = find_fork(spec, root, src, start_at)
    if fork is None:
        return _refuse("fork_not_found", f"{src} never reached {start_at}", tid=src)
    latest = _latest(spec, root, src)
    path = list(((latest.get("run") or {}).get("path") or {}).get("units") or [])
    behind = [u for u in path if u not in with_outcome(spec).units]  # the compiled outcome unit is ours
    if behind:  # MIG §2.5 with `start_at` as the pending unit
        return _refuse("units_behind", f"units behind: {', '.join(behind)} are no longer in the workflow", tid=src)
    first = flow.effective_order(spec)[0]
    cleared = cleared_units(spec, first if start_at == "start" else start_at, latest)
    effects = external_effects(spec, cleared, latest)
    if effects and not accept_external:
        return _refuse("external_effects", "units after the fork point had external effects: "
                                           f"{'; '.join(effects)}; pass --accept-external", effects, tid=src)
    new_task, n = (task_id, 0) if task_id else next_rerun_id(root, spec, source_task)
    new = thread_id(spec.name, new_task)
    if classify(root, spec, new_task) is not ThreadState.NONE:
        return _refuse("thread_exists", f"{new} already exists", tid=new)
    try:
        if settings.caller:
            from tempergraph import settings as rst
            from tempergraph.run.runner import decided

            settings = decided(settings, deciding=bool(feedback or any(rst.is_widening(k)
                                                                       for k in settings.all_flags())),
                               words=("rerun",))
        settled = settle_resume(spec, settings, root, fork.values if start_at != "start" else latest)
    except SettingsRefused as exc:
        return _refuse_settings(exc, new)
    rv = settled.run
    rep = preflight(settled.spec, registry, enforce_tools=bool(rv["enforce_tools"]),
                    strict_permissions=bool(rv["strict_permissions"]))
    if not rep.ok:
        first_f = rep.refusals[0]
        return _refuse(first_f.code, f"{first_f.unit or spec.name}: {first_f.message}", tid=new)
    run_spec = with_outcome(settled.spec)
    src_ws = latest.get("workspace") or {}
    try:
        plan = _workspace_plan(run_spec, target, src_ws, new_task, n, workspace_from, root, src, start_at, rv)
        if same_branch and plan.mode == "worktree":  # the source's branch and worktree (RRN §2.4)
            plan = dataclasses.replace(plan, branch=str(src_ws.get("branch") or plan.branch),
                                       path=Path(str(src_ws.get("path") or plan.path)),
                                       base_commit=str(src_ws.get("last_head") or plan.base_commit))
    except WorkspaceRefused as exc:
        return _refuse(exc.word, str(exc), tid=new)
    started = last_record(run_dir(root, spec.name, source_task) / "run.jsonl", "run_started") or {}
    rerun_of = {"thread": src, "unit": start_at, "checkpoint_id": fork.checkpoint_id,
                "workflow_version": started.get("workflow_version")}
    if check:
        return {"schema_version": 1, "status": "ok", "thread_id": new, "rerun_of": rerun_of, "cleared": cleared,
                "external_effects": effects, "workspace": {"mode": plan.mode, "branch": plan.branch or None,
                                                          "base_commit": plan.base_commit or None},
                "settings_digest": settled.resolved.digest, "warnings": list(plan.warnings)}
    ensure_state_root(root)
    lock = RunLock(lock_path(root, spec.name, new_task))
    try:
        lock.acquire()
    except LockHeld:
        return _refuse("running", f"{new} is running", tid=new)
    try:
        try:
            if same_branch and plan.mode == "worktree":
                rec = attach_workspace(WorkspaceRecord.from_json(dict(src_ws)), new, run_spec.worktree, root)
                gitmod.git(["worktree", "lock", "--reason", LOCK_REASON + new, "--end-of-options", rec.path],
                           Path(rec.path), check=False)
                rec.state = "active"
            else:
                rec = prepare_workspace(new, plan, run_spec.worktree, root,
                                        read_include=bool(rv["worktree.read_worktreeinclude"]))
        except WorkspaceRefused as exc:
            return _refuse(exc.word, str(exc), tid=new)
        meta = {**(((fork.values.get("run") or {}).get("meta")) or {}), "origin": "rerun", "rerun_of": rerun_of}
        writes = _writes(run_spec, fork, start_at, cleared, None if settings.ruling else feedback, drop_rulings,
                         settled.snapshot_json(), rec.to_json(), meta)
        if settings.ruling and feedback:
            writes = _with_ruling(writes, run_spec, fork, start_at, feedback, drop_rulings, dict(settings.caller))
        if start_at == "start":
            first_input: Any = {"request": dict(latest.get("request") or {}), **writes}
            before = None
        else:
            first_input = None

            def before(cw: Any) -> None:
                saver = cw.graph.checkpointer
                assert fork.config is not None
                tup = saver.get_tuple(fork.config)
                cfg = {"configurable": {"thread_id": new, "checkpoint_ns": ""}}
                saver.put(cfg, tup.checkpoint, {**(tup.metadata or {}), "source": "fork"},
                          dict(tup.checkpoint.get("channel_versions") or {}))
                cw.graph.update_state(cw.config(new), writes, as_node=fork.writer)
        _lineage(root, spec, source_task, new, start_at, superseded=same_branch)
        Ledger(path=root / "ledger.jsonl").append({  # the rerun is a steer touch on its source (SUP §2.2)
            "kind": "intervention", "id": uuid.uuid4().hex, "thread_id": src, "workflow": spec.name,
            "workflow_version": spec.version, **join_keys(root, settings),
            "unit": start_at, "caller": dict(settings.caller), "touches": [{"class": "steer", "action": "rerun"}],
            "pause_kind": "finished" if state is ThreadState.FINISHED else str(state), "decision": f"rerun:{start_at}",
            "wait_s": None, "feedback": bool(feedback), "ruling": settings.ruling,
            "settings_changed": list(settled.changed), "grants": [], "cause": "rerun", "rerun": new})
        out = _drive(run_spec, new_task, root, registry, settings, rep.judges, first_input, settled, before=before,
                     executors=rep.step_executors, rerun_of=rerun_of, workspace=rec.to_json())
        out.warnings = list(plan.warnings) + out.warnings
        return out
    finally:
        lock.release()


def _with_ruling(w: dict[str, Any], spec: WorkflowSpec, fork: Fork, start_at: str, text: str, drop: bool,
                 caller: Mapping[str, Any]) -> dict[str, Any]:
    """`rerun --ruling`: the text is a ruling given at the fork unit, not its visit reason."""
    have = {} if drop else dict(fork.values.get("rulings") or {})
    at = start_at if start_at != "start" else flow.effective_order(spec)[0]
    w["rulings"] = {**w.get("rulings", {}), **gatemod.ruling_writes(
        {"rulings": have}, {"feedback": text, "ruling": {"applies_to": []}, "caller": dict(caller)}, at)}
    return w


def _latest(spec: WorkflowSpec, root: Path, src: str) -> dict[str, Any]:
    from tempergraph.durability.checkpoint import thread_values

    return thread_values(engine_file.checkpoint_of(root, spec.name, src.partition("/")[2]), with_outcome(spec), src)


def _writes(spec: WorkflowSpec, fork: Fork, start_at: str, cleared: list[str], feedback: str | None,
            drop_rulings: bool, options: Mapping[str, Any], workspace: Mapping[str, Any], meta: Mapping[str, Any]
            ) -> dict[str, Any]:
    """The new thread's state edits: a trip back from `start_at`, fresh budgets and cost, the rerun's records."""
    v = fork.values
    w: dict[str, Any] = {}
    if start_at != "start":
        w = gatemod.clear_from(spec, start_at, v)
        visits = (v.get("visits") or {}).get(start_at) or {}
        w["visits"] = {**w.get("visits", {}), start_at: {"visit": int(visits.get("visit", 1)) + 1,
                                                         "reason": feedback or "rerun by a person",
                                                         "from": None, "entered_from": "rerun"}}
        w["pause"] = {u: None for u in (v.get("pause") or {})}
        w["feedback"] = {u: None for u in (v.get("feedback") or {})}
        w["route"] = {u: None for u in cleared if u != start_at}
    w["counters"] = {u: None for u in spec.units}  # fresh retry, loop and human budgets (RRN §2.4)
    if drop_rulings:
        w["rulings"] = {rid: None for rid in (v.get("rulings") or {})}

    w["workspace"] = dict(workspace)
    w["run"] = {"cost": None, "stopped": None, "options": dict(options), "meta": dict(meta)}
    return w


def _workspace_plan(spec: WorkflowSpec, target: Path, src_ws: Mapping[str, Any], new_task: str, n: int,
                    workspace_from: str, root: Path, src: str, start_at: str, rv: Mapping[str, Any]) -> Any:
    """RRN §2.4 Workspace: a new branch `<branch>-r<n>` from the source branch's tip or its commit at the unit."""
    plan = resolve_workspace(spec, target, "worktree" if src_ws.get("mode") == "worktree" else "in_place",
                             task_id=new_task, prefix=str(rv["worktree.branch_prefix"]))
    if plan.mode != "worktree":
        return dataclasses.replace(plan, warnings=(*plan.warnings, "in_place_rerun: the rerun starts from the "
                                                                    "files as they are now"))
    branch = str(src_ws.get("branch") or "")
    if workspace_from == "at-unit":
        entered = last_record(run_dir(root, spec.name, src.split("/", 1)[1]) / "run.jsonl", "unit_entered",
                              unit=start_at)
        base = str((entered or {}).get("head_commit") or "")
        if not base:
            raise WorkspaceRefused("no_commit_at_unit", f"no commit is recorded for {start_at}; use --workspace "
                                                        "current")
    else:
        base = gitmod.git(["rev-parse", "--verify", "--end-of-options", branch], plan.main or target,
                          check=False).strip() if branch else ""
        base = base or plan.base_commit
    new_branch = f"{branch}-r{n or 1}" if branch else plan.branch
    if not is_safe_ref(new_branch):
        raise WorkspaceRefused("branch_invalid", f"derived branch {new_branch!r} is not a valid ref")
    path = sibling_root(plan.main) / flat_name(spec.name, new_task) if plan.main else plan.path
    return dataclasses.replace(plan, branch=new_branch, base_commit=base, path=path)


def _lineage(root: Path, spec: WorkflowSpec, source_task: str, new: str, start_at: str, *,
             superseded: bool = False) -> None:
    p = run_dir(root, spec.name, source_task) / "lineage.json"
    try:
        doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        doc = {}
    doc = doc if isinstance(doc, dict) else {}
    doc.setdefault("schema_version", 1)
    doc.setdefault("reruns", []).append({"thread": new, "from": start_at,
                                         "at": datetime.now(UTC).isoformat(timespec="seconds"),
                                         **({"same_branch": True} if superseded else {})})
    if superseded:
        doc["superseded_by"] = new  # the source's branch now carries the rerun's work
    write_json(p, doc)

