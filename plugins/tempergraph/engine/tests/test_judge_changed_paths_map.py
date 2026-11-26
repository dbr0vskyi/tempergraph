"""The judge of one item of a map counts what that item changed since the commit its first attempt of the map's
visit started from, committed or not (SRV-B35; SRV-AC27 to SRV-AC29; task AC 2).

Built from the helpers of `test_map.py`; the map's step carries an `after` script that commits the item's files, as a
workflow's own script does. Nothing here names a workflow package.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tempergraph.api import Script
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult, WorkflowSpec
from tempergraph.executors.standins import answer
from tempergraph.improve import digest
from tempergraph.store.layout import state_root_path

from .test_judge_changed_paths import commit_in, commit_script
from .test_map import THREE, item_ok, mapped, recs, run
from .test_run import judge, verdict_block


def committing_map() -> WorkflowSpec:
    """The map fixture whose item step commits what the item wrote."""
    spec = mapped()
    phase = spec.units["phase"]
    assert phase.step is not None
    step = dataclasses.replace(phase.step, after=(Script(call=commit_script),))
    return dataclasses.replace(spec, units={**spec.units, "phase": dataclasses.replace(phase, step=step)},
                               session_review="off")


def plan_commits(items: Any) -> Any:
    """A scripted plan step that writes the list and commits it, so no item's count holds the list file."""

    def reply(req: SessionRequest) -> SessionResult:
        (req.workdir / "phases.json").write_text(json.dumps(items))
        commit_in(req.workdir)
        return answer("Planned.\nARTIFACT phases: phases.json", session_id="plan")

    return reply


def item_writes(req: SessionRequest) -> SessionResult:
    """An item's step: it writes one file named for the item and the attempt (the same content on every visit)."""
    _, iid, attempt, _ = req.session_key.split(".")
    (req.workdir / f"done-{iid}-{attempt}.md").write_text(f"{iid}\n")
    return item_ok()


def item_judges(repo: Path, task: str, item: str) -> list[dict[str, Any]]:
    """The judge sessions of one item, in the order they ran."""
    return [r for r in recs(repo, "agent_run", task)
            if r["session_key"].startswith(f"phase.{item}.") and r["session_key"].endswith(".judge")]


def judge_total(repo: Path, task: str, key: str) -> int:
    doc = digest.read(state_root_path(repo), "demo", task, key)
    assert doc is not None, key
    return int(doc["changed_total"])


def test_an_items_judge_counts_what_that_item_changed(repo: Path) -> None:  # SRV-AC27, AC 2
    steps = [plan_commits(THREE[:2]), item_writes, item_writes, answer("Joined.", session_id="join")]
    out, _ = run(repo, committing_map(), steps, [judge() for _ in range(4)], task="MJ-1")
    assert out.exit_code is ExitCode.FINISHED, out.message
    (first,) = item_judges(repo, "MJ-1", "p1")
    (second,) = item_judges(repo, "MJ-1", "p2")
    assert first["changed_paths"] == ["done-p1-1.md"]
    assert second["changed_paths"] == ["done-p2-1.md"]  # p1's committed file is not p2's change (MAP-B9)
    assert judge_total(repo, "MJ-1", second["session_key"]) == 1


def test_a_retry_of_an_item_counts_from_the_commit_its_first_attempt_started_from(repo: Path) -> None:  # SRV-AC28, AC 2
    steps = [plan_commits(THREE[:1]), item_writes, item_writes, answer("Joined.", session_id="join")]
    judges = [judge(), judge(verdict_block("UNMET")), judge(), judge()]
    out, _ = run(repo, committing_map(), steps, judges, task="MJ-2")
    assert out.exit_code is ExitCode.FINISHED, out.message
    first, retry = item_judges(repo, "MJ-2", "p1")
    assert judge_total(repo, "MJ-2", first["session_key"]) == 1
    assert sorted(retry["changed_paths"]) == ["done-p1-1.md", "done-p1-2.md"]  # the first attempt's commit counts
    assert judge_total(repo, "MJ-2", retry["session_key"]) == 2


def test_an_item_of_a_visit_begun_by_a_trip_back_counts_that_visit_only(repo: Path) -> None:  # SRV-AC29, AC 2

    def same(req: SessionRequest) -> SessionResult:
        (req.workdir / "done-p1.md").write_text("p1\n")  # the second visit writes the same content again
        return item_ok()

    steps = [plan_commits(THREE[:2]), same, item_writes, answer("Joined.", session_id="join"),
             plan_commits([THREE[0], THREE[2]]), same, item_writes, answer("Joined.", session_id="join")]
    judges = [judge(), judge(), judge(), judge(verdict_block("UNMET", defect_in="phases")),
              judge(), judge(), judge(), judge()]
    out, _ = run(repo, committing_map(), steps, judges, task="MJ-3")
    assert out.exit_code is ExitCode.FINISHED, out.message
    first, again = item_judges(repo, "MJ-3", "p1")
    assert first["changed_paths"] == ["done-p1.md"]
    assert again["changed_paths"] == []  # nothing the new visit changed
    assert judge_total(repo, "MJ-3", again["session_key"]) == 0
