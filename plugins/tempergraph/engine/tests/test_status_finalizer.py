"""`status --json` rows carry the finalizer's result when a person still has steps to take (DUR-B11, DUR-AC7; task AC 8).
Every thread here is a real fixture run through `go`; the rows are read with `status` and nothing is written by hand."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.durability.status import status
from tempergraph.run.finalize import FinalizerResult
from tempergraph.store.layout import state_root_path

from .conftest import hash_tree
from .test_finalizer_outcomes import PR, finalize_record, happy, raises, skips, skips_quietly, spec_with
from .test_run import go, records


def opens(ctx: Any) -> FinalizerResult:
    return FinalizerResult(outcome="opened", reason="published", url=PR)


FIELDS = ("thread_id", "workflow", "state", "alive", "pending_gates", "log_path", "exit_code")


def test_dur_ac7_status_rows_carry_the_finalizer_only_when_steps_remain(repo: Path) -> None:
    # DUR-AC7, DUR-B11, task AC 8
    fns = {"M-1": skips, "E-1": raises, "P-1": opens, "Q-1": skips_quietly}
    specs = {}
    for task, fn in fns.items():
        specs[task] = spec_with(fn)
        out = go(repo, happy(), specs[task], task=task)
        assert out.exit_code is ExitCode.FINISHED, out.message

    root = state_root_path(repo)
    before = hash_tree(root)
    rows = {r["thread_id"]: r for r in status(root, {"demo": specs["M-1"]})["threads"]}
    assert hash_tree(root) == before  # status read the state root and left it unchanged
    assert set(rows) == {f"demo/{t}" for t in fns}

    def fin(task: str) -> dict[str, Any]:
        got = [r for r in records(repo, task) if r["kind"] == "finalize"]
        assert len(got) == 1
        return got[0]

    manual = rows["demo/M-1"]["finalizer"]
    rec = fin("M-1")
    assert manual == {"outcome": rec["outcome"], "reason": rec["reason"], "manual_steps": rec["manual_steps"]}
    assert manual["manual_steps"] == ["add a remote", "push the branch"]

    raised = rows["demo/E-1"]["finalizer"]
    assert raised["outcome"] == "error" and raised["manual_steps"] == []

    assert "finalizer" not in rows["demo/P-1"] and "finalizer" not in rows["demo/Q-1"]
    assert fin("P-1")["outcome"] == "opened" and fin("Q-1")["outcome"] == "skipped"

    for row in rows.values():
        for key in FIELDS:
            assert key in row, (row["thread_id"], key)
        assert row["workflow"] == "demo" and row["exit_code"] == 0
