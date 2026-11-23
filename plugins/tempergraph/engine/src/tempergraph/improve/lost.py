"""A lost runner is a final exit (SIL-B26 to SIL-B29).

A thread whose lock is free and whose newest segment started and wrote no `run_exit` lost its runner (killed,
crashed or cut off by its caller's timeout: the engine cannot tell them apart, RDD-B14). `status`, `stop` and
`attention` call `settle` to write that segment as an exit with code 5 and reason `runner_lost`, with the records of
SIL-B8, and to hand it to the loop once per thread. The readers themselves (`durability.status`, `observe.attention`,
`observe.detail`) stay pure. The thread's run lock, taken without waiting, is the claim (DUR-B10): a verb that finds
it held skips the thread. Nothing here prints, starts a session or writes a `run_exit`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec
from tempergraph.durability.lock import LockHeld, RunLock, is_held
from tempergraph.durability.status import Selector, _read, select, split_thread
from tempergraph.executors.registry import Registry, default_registry
from tempergraph.improve import child, params
from tempergraph.run.log import CostTotals, Ledger, RunLog
from tempergraph.store.layout import lock_path, run_dir

REASON = "runner_lost"
EXIT_CODE = 5


def _when(ts: Any) -> datetime | None:
    try:
        got = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return got if got.tzinfo else got.replace(tzinfo=UTC)


def _lost(records: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    """The `run_started` record of the newest segment when it has no `run_exit` and the log is inside the window."""
    start = max((i for i, r in enumerate(records) if r.get("kind") == "run_started"), default=None)
    if start is None or any(r.get("kind") == "run_exit" for r in records[start:]):
        return None
    newest = _when(records[-1].get("ts"))
    days = float(params.value("lost_runner.window_days"))
    if newest is None or now - newest > timedelta(days=days):
        return None
    return records[start]


def _recorded(rows: list[dict[str, Any]], tid: str, started: Mapping[str, Any]) -> bool:
    """SIL-B27: the segment already has its `runner_lost` row: one at or after the segment's `run_started`."""
    at = _when(started.get("ts"))
    return any(r.get("kind") == "run_segment" and r.get("thread_id") == tid and r.get("reason") == REASON
               and (at is None or (_when(r.get("ts")) or at) >= at) for r in rows)


def _settle_thread(root: Path, spec: WorkflowSpec, tid: str, registry: Registry) -> None:
    from tempergraph.improve.record import record_exit
    from tempergraph.run import runner

    task = split_thread(tid)[1]
    path = lock_path(root, spec.name, task)
    log_path = run_dir(root, spec.name, task) / "run.jsonl"
    now = datetime.now(UTC)
    if is_held(path) or _lost(runner._log_records(log_path), now) is None:
        return  # a probe creates nothing: a thread with a live runner or no lost segment is left as it is
    lock = RunLock(path)
    try:
        lock.acquire()  # DUR-B10: without waiting; a verb that finds it held skips the thread
    except LockHeld:
        return
    try:
        records = runner._log_records(log_path)  # read again under the lock
        started = _lost(records, now)
        rows = runner.ledger_rows(root)
        if started is None or _recorded(rows, tid, started):
            return
        snap, _ = _read(root, spec, tid)  # the thread's last checkpoint: its request, outputs and spend
        values = snap.values or {}
        cost = CostTotals.from_json((values.get("run") or {}).get("cost"))
        settings = runner.RunSettings()
        ledger = Ledger(path=root / "ledger.jsonl")
        row = {"kind": "run_segment", "thread_id": tid, "workflow": spec.name, "workflow_version": spec.version,
               **runner.join_keys(root, settings), "exit_code": EXIT_CODE, "reason": REASON, "cost": cost.to_json(),
               "origin": started.get("origin") or settings.origin, "stage": runner._stage(spec, settings)[0],
               "settings_digest": started.get("settings_digest"), "overridden_keys": started.get("overridden_keys"),
               "grants": []}
        ledger.append(row)
        if ledger.failures:
            return  # nothing is recorded without its ledger row, so a later look tries again
        written = next((r for r in reversed(runner.ledger_rows(root)) if r.get("kind") == "run_segment"
                        and r.get("thread_id") == tid), row)
        log = RunLog(log_path)
        summary = record_exit(root, spec, task, log_path, values, written)
        from tempergraph.improve.reliability import after_exit

        summary["labels"] = after_exit(root, spec.name, task, written)
        log.write("finding_recorded", **summary)
        if child.started_for(root, spec.name, task, tid, REASON):  # SIL-B28: once per thread
            return
        judges = (started.get("executors") or {}).get("judges") or {}
        runner.hand_to_loop(root, spec, task, tid, summary, None, registry, judges,
                            run_cost_usd=cost.reported + cost.estimated_only, trigger=REASON)
    finally:
        lock.release()


def settle(root: Path, specs: Mapping[str, WorkflowSpec], selector: str | None = None,
           registry: Registry | None = None) -> None:
    """Hands every lost runner of the selected threads to the loop; every failure is caught, per thread (SIL-B29)."""
    with contextlib.suppress(Exception):
        found = select(root, specs, Selector(value=selector))
        for spec, tid in found:
            with contextlib.suppress(Exception):
                _settle_thread(root, spec, tid, registry or default_registry())
