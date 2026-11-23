"""Checkpoints, thread states, the lock, aliases, status and wait (DUR-B9, DUR-B11, DUR-B3–B5, B8;
DUR-AC1, AC-2, AC-3)."""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path
from typing import Any

import pytest
from langgraph.types import Command

from tempergraph.compiler import compile_workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import ThreadState
from tempergraph.durability import alias as aliases
from tempergraph.durability.checkpoint import open_readonly, open_saver, thread_ids
from tempergraph.durability.lock import LockHeld, RunLock, is_held
from tempergraph.durability.status import Selector, classify, status, wait
from tempergraph.store.layout import checkpoint_path, ensure_state_root, lock_path

from .conftest import hash_tree
from .fixtures.workflows import two_step
from .test_compiler import Scripted


class Crashing(Scripted):
    def judge(self, unit: str, state: Any) -> dict[str, Any]:
        if unit == "review":
            raise KeyboardInterrupt  # the process dies mid-unit
        return {}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return ensure_state_root(tmp_path / ".tempergraph")


def drive(root: Path, task: str, script: dict[str, list[str]], nodes_cls: type = Scripted,
          resume: str | None = None) -> None:
    spec = two_step()
    saver = open_saver(checkpoint_path(root, spec.name))
    cw = compile_workflow(spec, nodes_cls(spec, script), saver)
    cfg = cw.config(f"{spec.name}/{task}")
    try:
        cw.graph.invoke({"request": {"text": "x"}}, cfg)
        if resume:
            cw.graph.invoke(Command(resume=resume), cfg)
    except KeyboardInterrupt:
        pass
    finally:
        saver.conn.close()


def test_every_thread_state(root: Path) -> None:
    spec = two_step()
    drive(root, "fin", {})
    drive(root, "pause", {"draft": ["ESCALATE"]})
    drive(root, "stop", {"draft": ["STOP"]})
    drive(root, "cut", {}, Crashing)
    got = {t: classify(root, spec, t) for t in ("none", "fin", "pause", "stop", "cut")}
    assert got == {"none": ThreadState.NONE, "fin": ThreadState.FINISHED, "pause": ThreadState.PAUSED,
                   "stop": ThreadState.STOPPED, "cut": ThreadState.UNFINISHED}
    with RunLock(lock_path(root, spec.name, "pause")):
        assert classify(root, spec, "pause") is ThreadState.RUNNING  # a held lock reads running


def test_paused_resume_continues(root: Path) -> None:
    drive(root, "p", {"draft": ["ESCALATE"]}, resume="proceed")
    assert classify(root, two_step(), "p") is ThreadState.FINISHED


def test_status_function_writes_nothing_for_a_lost_runner(repo: Path) -> None:  # DUR-AC3, SIL-AC20
    from tempergraph.observe.attention import items
    from tempergraph.store.layout import state_root_path

    from .test_lost_runner import kill, spec_of

    kill(repo)  # no `run_exit`, lock free: a lost runner that only the verbs hand to the loop
    state = state_root_path(repo)
    before = hash_tree(state)
    doc = status(state, {"demo": spec_of()})
    items(state, {"demo": spec_of()})
    assert hash_tree(state) == before
    assert [r["state"] for r in doc["threads"]] == ["unfinished"]


def test_observers_create_nothing(root: Path) -> None:
    spec = two_step()
    assert classify(root, spec, "nothing") is ThreadState.NONE
    assert not checkpoint_path(root, spec.name).exists()
    drive(root, "pause", {"draft": ["ESCALATE"]})
    drive(root, "fin", {})
    before = hash_tree(root)
    doc = status(root, {spec.name: spec})
    wait(root, spec, f"{spec.name}/fin", 1)
    assert hash_tree(root) == before  # DUR-AC3
    states = {r["thread_id"].split("/")[1]: r["state"] for r in doc["threads"]}
    assert states == {"fin": "finished", "pause": "paused"}
    paused = next(r for r in doc["threads"] if r["state"] == "paused")
    assert paused["pending_gates"][0]["unit"] == "draft"
    assert paused["pending_gates"][0]["resume"].startswith("tempergraph resume demo pause")
    assert paused["alive"] is False and doc["schema_version"] == 1


def test_lock_probe_and_exclusion(root: Path) -> None:
    p = lock_path(root, "demo", "t")
    assert not is_held(p) and not p.exists()  # probing creates nothing
    with RunLock(p):
        assert is_held(p)
        with pytest.raises(LockHeld):
            RunLock(p).acquire()
    assert not is_held(p)


def _writer(path: str, n: int) -> None:
    spec = two_step()
    saver = open_saver(Path(path))
    cw = compile_workflow(spec, Scripted(spec, {}), saver)
    cw.graph.invoke({"request": {"text": "x"}}, cw.config(f"demo/w{n}"))
    saver.conn.close()


def test_sixteen_writers_lose_nothing(root: Path) -> None:
    path = checkpoint_path(root, "demo")
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_writer, args=(str(path), n)) for n in range(16)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
        assert p.exitcode == 0
    with open_readonly(path) as saver:
        assert saver is not None
        assert len(thread_ids(saver)) == 16  # DUR-AC2
    assert all(classify(root, two_step(), f"w{n}") is ThreadState.FINISHED for n in range(16))


def test_alias_unique_among_live(root: Path) -> None:
    live = {"demo/a": True, "demo/b": True}
    aliases.claim(root, "auth-fix", "demo/a", lambda t: live.get(t, False))
    with pytest.raises(aliases.AliasTaken):
        aliases.claim(root, "auth-fix", "demo/b", lambda t: live.get(t, False))
    live["demo/a"] = False  # finished
    aliases.claim(root, "auth-fix", "demo/b", lambda t: live.get(t, False))
    live["demo/b"] = False
    assert aliases.resolve(root, "auth-fix", lambda t: live.get(t, False)) == "demo/b"  # latest one
    with pytest.raises(aliases.AliasInvalid):
        aliases.claim(root, "bad name!", "demo/c", lambda t: False)


def test_status_by_alias(root: Path) -> None:
    spec = two_step()
    drive(root, "pause", {"draft": ["ESCALATE"]})
    aliases.claim(root, "notes", "demo/pause", lambda t: True)
    doc = status(root, {spec.name: spec}, Selector(value="notes"))
    assert [r["thread_id"] for r in doc["threads"]] == ["demo/pause"]
    assert doc["threads"][0]["alias"] == "notes"


def test_wait_outcomes(root: Path) -> None:
    spec = two_step()
    drive(root, "pause", {"draft": ["ESCALATE"]})
    assert wait(root, spec, "demo/pause", 5).exit_code is ExitCode.PAUSED
    drive(root, "fin", {})
    assert wait(root, spec, "demo/fin", 5).exit_code is ExitCode.FINISHED
    ticks = iter(range(100))
    with RunLock(lock_path(root, spec.name, "pause")):
        out = wait(root, spec, "demo/pause", 3, clock=lambda: float(next(ticks)), sleep=lambda s: None)
    assert out.reason == "timeout" and out.state == "running"
