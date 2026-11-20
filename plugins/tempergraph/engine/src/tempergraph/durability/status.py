"""Classification, the status document and wait (DUR §2, §2.2, DUR-B4, DUR-B5).

All three are read-only and model-free: the checkpoint opens read-only, the lock is probed without
being created, and nothing is written. Fields the run has not recorded yet are left out, never zeroed
(CON §2.10).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.constants import SCHEMA, ExitCode
from tempergraph.contracts import ThreadState, WorkflowSpec, thread_id
from tempergraph.durability import alias as aliases
from tempergraph.durability.checkpoint import (
    Snapshot,
    classify_snapshot,
    observer_graph,
    open_readonly,
    snapshot,
    thread_ids,
)
from tempergraph.durability.lock import is_held
from tempergraph.model import flow
from tempergraph.store.layout import checkpoint_path, lock_path, now_iso, run_dir

RUN_FIELDS = ("attempt_in_flight", "last_verdict", "cost", "executors", "label", "origin", "rerun_of", "reruns",
              "settings_digest", "overridden_keys", "parent", "schedule", "resume_count", "engine", "engine_pin", "exit_code")


def split_thread(tid: str) -> tuple[str, str]:
    workflow, _, task = tid.partition("/")
    return workflow, task


def _read(state_root: Path, spec: WorkflowSpec, tid: str) -> tuple[Snapshot, bool]:
    _, task = split_thread(tid)
    held = is_held(lock_path(state_root, spec.name, task))
    with open_readonly(checkpoint_path(state_root, spec.name)) as saver:
        if saver is None:
            return Snapshot(exists=False), held
        return snapshot(observer_graph(spec, saver), tid), held


def classify(state_root: Path, spec: WorkflowSpec, task_id: str) -> ThreadState:
    """DUR §2 `classify`: read-only; creates nothing."""
    snap, held = _read(state_root, spec, thread_id(spec.name, task_id))
    return classify_snapshot(snap, held)


def resume_command(workflow: str, tid: str, decisions: list[str] | None = None) -> str:
    cmd = f"tempergraph resume {workflow} {split_thread(tid)[1]}"
    return cmd + (f" --decision <{'|'.join(decisions)}>" if decisions else "")


def _pending(workflow: str, tid: str, snap: Snapshot) -> list[dict[str, Any]]:
    out = []
    for node, payload in snap.interrupts:
        p = payload if isinstance(payload, dict) else {}
        unit = node.rsplit(".", 1)[0] if node.endswith(".human") else node
        out.append({"unit": unit, "item": p.get("item"), "kind": p.get("kind", "escalation"),
                    "resume": p.get("resume") or resume_command(workflow, tid, p.get("decisions"))})
    return out


def row(state_root: Path, spec: WorkflowSpec, tid: str) -> dict[str, Any]:
    snap, held = _read(state_root, spec, tid)
    state = classify_snapshot(snap, held)
    r: dict[str, Any] = {"thread_id": tid, "workflow": spec.name, "state": str(state), "alive": held,
                         "pending_gates": _pending(spec.name, tid, snap),
                         "log_path": str(run_dir(state_root, spec.name, split_thread(tid)[1]) / "run.jsonl")}
    run = snap.values.get("run") or {}
    for key in RUN_FIELDS:
        if key in run:
            r[key] = run[key]
    ws = (snap.values.get("workspace") or {})
    if ws:
        r["workspace"] = {k: ws.get(k) for k in ("mode", "path", "branch", "state") if k in ws}
    exit_path = run_dir(state_root, spec.name, split_thread(tid)[1]) / "exit.json"
    if exit_path.exists() and state is not ThreadState.RUNNING:
        try:
            ex = json.loads(exit_path.read_text(encoding="utf-8"))
            r.setdefault("exit_code", ex.get("exit_code"))
            r["exit_reason"] = ex.get("reason")
        except (OSError, ValueError):
            pass
    name = aliases.alias_of(state_root, tid)
    if name:
        r["alias"] = name
    if snap.next and state is ThreadState.UNFINISHED:
        r["next"] = [n for n in snap.next if n != flow.FINALIZER] or list(snap.next)
    return r


@dataclass(frozen=True, kw_only=True)
class Selector:
    """A thread id, an alias, a workflow name, or everything (None)."""

    value: str | None = None


def _threads(state_root: Path, spec: WorkflowSpec) -> list[str]:
    with open_readonly(checkpoint_path(state_root, spec.name)) as saver:
        return thread_ids(saver) if saver is not None else []


def select(state_root: Path, specs: Mapping[str, WorkflowSpec], sel: Selector) -> list[tuple[WorkflowSpec, str]]:
    v = sel.value
    if v is None or v in specs:
        names = [v] if v else sorted(specs)
        return [(specs[n], t) for n in names for t in _threads(state_root, specs[n])]
    if "/" in v and split_thread(v)[0] in specs:
        return [(specs[split_thread(v)[0]], v)]

    def live(t: str) -> bool:
        w = split_thread(t)[0]
        return w in specs and classify_snapshot(*_read(state_root, specs[w], t)) not in (
            ThreadState.FINISHED, ThreadState.NONE)

    tid = aliases.resolve(state_root, v, live)
    if tid and split_thread(tid)[0] in specs:
        return [(specs[split_thread(tid)[0]], tid)]
    return []


def status(state_root: Path, specs: Mapping[str, WorkflowSpec], sel: Selector | None = None) -> dict[str, Any]:
    rows = []
    for spec, tid in select(state_root, specs, sel or Selector()):
        try:
            rows.append(row(state_root, spec, tid))
        except Exception as exc:  # noqa: BLE001 - one unreadable thread marks only its row (DUR §4)
            rows.append({"thread_id": tid, "workflow": spec.name, "state": "unreadable", "error": type(exc).__name__})
    return {"schema_version": SCHEMA["status"], "generated_at": now_iso(), "threads": rows}


# ---------------------------------------------------------------------------------------------
# wait (DUR-B5)


@dataclass(kw_only=True)
class WaitOutcome:
    state: str
    exit_code: ExitCode
    row: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


EXIT_FOR = {"finished": ExitCode.FINISHED, "paused": ExitCode.PAUSED, "stopped": ExitCode.STOPPED,
            "unfinished": ExitCode.STOPPED, "none": ExitCode.USAGE}


def _signature(paths: list[Path]) -> tuple[tuple[int, int], ...]:
    sig = []
    for p in paths:
        try:
            st = p.stat()
            sig.append((st.st_size, st.st_mtime_ns))
        except OSError:
            sig.append((-1, -1))
    return tuple(sig)


def wait(state_root: Path, spec: WorkflowSpec, tid: str, timeout_s: float, *, poll_s: float = 0.5,
         clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> WaitOutcome:
    """Block until the thread pauses, ends or records a new verdict, or the timeout passes.

    Polls file sizes and times and rebuilds the row only when one moved."""
    _, task = split_thread(tid)
    db = checkpoint_path(state_root, spec.name)
    watched = [db, db.with_name(db.name + "-wal"), lock_path(state_root, spec.name, task),
               run_dir(state_root, spec.name, task) / "run.jsonl"]
    start = clock()
    sig: tuple[tuple[int, int], ...] | None = None
    first_verdict: Any = None
    while True:
        now_sig = _signature(watched)
        if now_sig != sig:
            sig = now_sig
            r = row(state_root, spec, tid)
            verdict = r.get("last_verdict")
            if first_verdict is None:
                first_verdict = verdict if verdict is not None else ""
            elif verdict is not None and verdict != first_verdict:
                return WaitOutcome(state=r["state"], exit_code=ExitCode.FINISHED, row=r, reason="verdict")
            if r["state"] != "running":
                code = r.get("exit_code")
                exit_code = ExitCode(code) if isinstance(code, int) and code in set(ExitCode) else EXIT_FOR.get(
                    r["state"], ExitCode.INTERNAL)
                return WaitOutcome(state=r["state"], exit_code=exit_code, row=r, reason="state")
        if clock() - start >= timeout_s:
            return WaitOutcome(state="running", exit_code=ExitCode.BUDGET_OR_INFRA, reason="timeout")
        sleep(poll_s)
