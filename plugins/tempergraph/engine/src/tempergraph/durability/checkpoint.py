"""The per-workflow SQLite checkpoint and thread classification (DUR §2, §2.1, DUR-B3, DUR-B4).

Writers open the store with a 60 s busy wait and retry creating an empty store for 30 s. Observers open
it read-only and create nothing: with no write-ahead log present (no writer has it open) the file is
opened ``immutable``, else ``mode=ro``, which touches only the live writer's shared-memory index.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from tempergraph.compiler.graph import CompiledWorkflow, compile_workflow
from tempergraph.compiler.state import RunState
from tempergraph.contracts import ThreadState, WorkflowSpec

BUSY_TIMEOUT_S = 60.0
CREATE_RETRY_S = 30.0


def open_saver(path: Path) -> SqliteSaver:
    """A writer's saver; the folder is owner-only and the file 0600."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    deadline = time.monotonic() + CREATE_RETRY_S
    while True:
        try:
            conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_S, check_same_thread=False)
            saver = SqliteSaver(conn)
            saver.setup()
            path.chmod(0o600)
            return saver
        except sqlite3.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


@contextmanager
def open_readonly(path: Path) -> Iterator[SqliteSaver | None]:
    """An observer's saver, or None when no store exists. Creates no file (DUR-B4)."""
    if not path.exists():
        yield None
        return
    wal = path.with_name(path.name + "-wal")
    mode = "mode=ro" if wal.exists() else "mode=ro&immutable=1"
    conn = sqlite3.connect(f"file:{path}?{mode}", uri=True, timeout=BUSY_TIMEOUT_S, check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.is_setup = True  # never run the writer's setup script on a read-only store
        yield saver
    finally:
        conn.close()


def thread_ids(saver: SqliteSaver) -> list[str]:
    try:
        rows = saver.conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id").fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]


class _NoNodes:
    """Node bodies for an observer's graph: reading state never runs a node."""

    def _never(self, *_: Any) -> dict[str, Any]:
        raise RuntimeError("an observer's graph runs no node")

    step = judge = gate = human = _never

    def finalizer(self, state: RunState) -> dict[str, Any]:
        return self._never(state)


def observer_graph(spec: WorkflowSpec, saver: SqliteSaver) -> CompiledWorkflow:
    return compile_workflow(spec, _NoNodes(), saver)


@dataclass(frozen=True, kw_only=True)
class Snapshot:
    """What classification needs from one thread's latest checkpoint."""

    exists: bool
    next: tuple[str, ...] = ()
    interrupts: tuple[tuple[str, Any], ...] = ()  # (node, payload)
    values: dict[str, Any] = field(default_factory=dict)


def snapshot(cw: CompiledWorkflow, thread_id: str) -> Snapshot:
    try:
        st = cw.graph.get_state(cw.config(thread_id))
    except sqlite3.OperationalError:
        return Snapshot(exists=False)
    if not st.values:
        return Snapshot(exists=False)
    ints = tuple((t.name, i.value) for t in st.tasks for i in t.interrupts)
    return Snapshot(exists=True, next=tuple(st.next), interrupts=ints, values=dict(st.values))


def classify_snapshot(snap: Snapshot, lock_held: bool) -> ThreadState:
    """DUR §2.1: a held lock reads `running` over any checkpoint state (DUR §5)."""
    if lock_held:
        return ThreadState.RUNNING
    if not snap.exists:
        return ThreadState.NONE
    if snap.interrupts:
        return ThreadState.PAUSED
    if snap.next:
        return ThreadState.UNFINISHED
    if snap.values.get("finalized"):
        return ThreadState.FINISHED
    return ThreadState.STOPPED


def resume_input(value: Any) -> Any:
    """The graph input that answers a pending interrupt; keeps LangGraph inside durability (ADR-0115)."""
    from langgraph.types import Command

    return Command(resume=value)
