"""A carried parent run paused inside its child resumes on a second state root and finishes, the child continuing where
it paused (SWF-B8, SWF-AC3; task AC 5; CAR-B1, CAR-AC1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tempergraph.catalog import Catalog
from tempergraph.constants import ExitCode
from tempergraph.durability import carry
from tempergraph.durability import engine_file as enginefile
from tempergraph.durability.checkpoint import open_readonly
from tempergraph.executors.standins import standin
from tempergraph.run.events import records
from tempergraph.run.runner import ledger_rows
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.subworkflows import register_workflow
from .test_carry import World, git
from .test_cli import cli
from .test_run import DRAFT, REVIEW, judge
from .test_subworkflow_run import WORK, parent

BRANCH = "tempergraph/state/deliver/t1"
CATALOG = Catalog(specs={"deliver": parent()})


@pytest.fixture
def world(tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    w = World(tmp_path, repo, monkeypatch)
    for name in ("a", "b"):  # the child is registered on both machines, as a shared plugin would be
        register_workflow(tmp_path / f"home-{name}" / ".tempergraph", tmp_path / "pkgs", "child",
                          produces=["overview"], approval=True)
    return w


def log(repo: Path) -> list[dict[str, Any]]:
    return list(records(run_dir(state_root_path(repo), "deliver", "t1") / "run.jsonl"))


def test_a_carried_parent_paused_in_its_child_resumes_on_another_state_root_and_finishes(
        world: World) -> None:  # SWF-AC3, CAR-AC1, AC 5
    a = world.on("a")
    ex = standin("claude", steps=[DRAFT, WORK], judges=[judge(), judge()])
    code, _, err = cli(a, ex, "run", "deliver", "notes", "--task-id", "t1", "--carry", catalog=CATALOG)
    assert code == ExitCode.PAUSED, err
    pause = [r for r in log(a) if r["kind"] == "pause"][-1]
    assert pause["child"] == "setup" and pause["unit"] == "work" and pause["pause_kind"] == "approval"
    work = [r for r in log(a) if r["kind"] == "workspace"][-1]["branch"]
    git(a, "push", "-q", "origin", str(work))  # the person's own push of the work branch
    assert BRANCH in world.remote_heads()

    b = world.on("b")
    code, doc, err = cli(b, None, "carry", "pull", "deliver", "t1", "--json", catalog=CATALOG)
    assert code == 0 and doc["imported"] > 3, err
    code, st, _ = cli(b, None, "status", catalog=CATALOG)
    assert [(t["thread_id"], t["state"]) for t in st["threads"]] == [("deliver/t1", "paused")]
    assert [g["unit"] for g in st["threads"][0]["pending_gates"]] == ["setup/work"]  # paused at the child's unit
    second = standin("claude", steps=[REVIEW], judges=[judge(), judge()])  # the child's outcome gate, then review
    code, doc, err = cli(b, second, "resume", "deliver", "t1", "--decision", "proceed", "--json", catalog=CATALOG)
    assert code == 0, (err, doc)
    # the child continued where it paused: its `work` did not run again, its outcome gate and the parent's `review` did
    assert [c.request.session_key for c in second.calls] == ["setup/outcome.1.judge", "review.1.step", "review.1.judge"]
    rows = log(b)
    steps = [(r.get("child"), r["unit"]) for r in rows if r["kind"] == "agent_run" and r.get("session_kind") == "step"]
    assert steps == [(None, "draft"), ("setup", "work"), (None, "review")]  # A's segment travelled, each unit ran once
    exits = [r for r in rows if r["kind"] == "run_exit"]
    assert [r["kind"] for r in rows].count("run_started") == 2 and [e["exit_code"] for e in exits] == [3, 0]
    # the child's state is intact: its version in both segments, and its outcome record (graded on B, from A's `work`)
    started = [r for r in rows if r["kind"] == "run_started"]
    assert all(s["children"]["setup"]["workflow"] == "child" for s in started)
    (kid,) = [r for r in ledger_rows(state_root_path(b)) if r.get("kind") == "child_outcome"]
    assert kid["workflow"] == "child" and kid["thread_id"] == "deliver/t1" and kid["outcome"]["verdict"] == "met"
    with open_readonly(enginefile.checkpoint_of(state_root_path(b), "deliver", "t1")) as saver:
        assert saver is not None
        held: dict[str, dict[str, Any]] = {}
        for tup in saver.list({"configurable": {"thread_id": "deliver/t1"}}):  # newest first
            ns = str(tup.config["configurable"].get("checkpoint_ns") or "")
            if ns and ns not in held:
                held[ns] = dict(tup.checkpoint.get("channel_values") or {})
    state = held["setup.1.1"]  # the child's own namespace: the unit's visit and attempt (SWF-B8)
    assert state["attempts"]["work"]["ok"] is True and state["judgements"]["work"]["verdict"] == "PROCEED"
    assert "outcome" in state["attempts"]  # the child's outcome gate ran on B, in the same namespace
    # CAR-B3: no trace after the finish
    assert BRANCH not in world.remote_heads()
    assert carry.marker(state_root_path(b), "deliver", "t1")["state"] == "finished"
