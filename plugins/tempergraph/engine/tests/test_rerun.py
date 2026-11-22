"""`rerun` as a linked fork (RRN-B17, RRN-B18, RRN-B6, B7, B8, AC-3, AC-4)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tempergraph.catalog import Catalog
from tempergraph.executors.standins import answer, standin

from .conftest import hash_tree
from .fixtures.workflows import two_step
from .test_cli import cli, happy
from .test_feedback import Seen, records
from .test_run import DRAFT, REVIEW, judge


def history(repo: Path, tid: str) -> list[Any]:
    from tempergraph.compiler import compile_workflow
    from tempergraph.durability.checkpoint import open_readonly
    from tempergraph.run.outcome import with_outcome
    from tempergraph.run.runner import _Inert

    with open_readonly(repo / ".tempergraph" / "checkpoints" / "demo.sqlite") as saver:
        cw = compile_workflow(with_outcome(two_step()), _Inert(), saver)
        return [(s.config["configurable"]["checkpoint_id"], json.dumps(s.values, sort_keys=True, default=str))
                for s in cw.graph.get_state_history(cw.config(tid))]


def finished(repo: Path, task: str) -> None:
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", task)
    assert code == 0, err


def test_rerun_keeps_earlier_verdicts(repo: Path) -> None:  # RRN-B7, AC-3
    finished(repo, "R-1")
    assert (repo / ".tempergraph" / "checkpoints" / "demo.sqlite").exists()
    before = history(repo, "demo/R-1")
    seen = Seen()
    ex = standin("claude", steps=[seen(REVIEW)], judges=[seen(judge())])
    code, _, err = cli(repo, ex, "rerun", "demo", "R-1", "--from", "review", "--set", "review.model=large",
                       "--feedback", "handle the empty list")
    assert code == 0, err
    assert [k.split(".")[0].split("-")[0] for k, _ in seen.prompts] and all(k.startswith("review")
                                                                            for k, _ in seen.prompts)
    assert seen.with_text("handle the empty list")  # the visit reason
    assert history(repo, "demo/R-1") == before  # the source's history is untouched
    started = records(repo, "R-1~r1", "run_started")[0]
    assert started["origin"] == "rerun" and started["rerun_of"]["thread"] == "demo/R-1"
    assert started["rerun_of"]["unit"] == "review" and started["rerun_of"]["checkpoint_id"]
    starts = [r for r in records(repo, "R-1~r1", "attempt_start") if r["kind"] == "attempt_start"]
    assert any(r["alias"] == "large" for r in starts if "judge" not in r["session_key"])
    lineage = json.loads((repo / ".tempergraph" / "runs" / "demo" / "R-1" / "lineage.json").read_text())
    assert lineage["reruns"][0]["thread"] == "demo/R-1~r1"
    code, _, _ = cli(repo, ex, "rerun", "demo", "R-1", "--from", "review", "--check")
    assert code == 0  # the next rerun id is r2


def test_rerun_from_start_reuses_the_input(repo: Path) -> None:  # RRN-B8
    finished(repo, "R-2")
    seen = Seen()
    ex = standin("claude", steps=[seen(DRAFT), seen(REVIEW)], judges=[seen(judge()), seen(judge())])
    code, _, err = cli(repo, ex, "rerun", "demo", "R-2", "--from", "start")
    assert code == 0, err
    assert [k for k, _ in seen.prompts if "judge" not in k][0].startswith("draft")
    a = records(repo, "R-2", "task")[0]
    assert a["request"] and seen.with_text("notes")


def test_rerun_check_creates_nothing_and_refuses_alike(repo: Path) -> None:  # RRN-AC4, C13
    finished(repo, "R-3")
    root = repo / ".tempergraph"
    before = hash_tree(root)
    code, doc, _ = cli(repo, happy(), "rerun", "demo", "R-3", "--from", "review", "--check")
    assert code == 0 and doc["thread_id"] == "demo/R-3~r1" and doc["cleared"] == ["review"]
    assert hash_tree(root) == before
    for argv in (["R-3", "--from", "nope"], ["R-9", "--from", "review"]):
        code, doc, _ = cli(repo, happy(), "rerun", "demo", *argv, "--check")
        code2, _, err = cli(repo, happy(), "rerun", "demo", *argv)
        assert code == code2 == 2 and doc["status"] == "error" and err, argv
    assert hash_tree(root) == before


def with_pr() -> Any:
    s = two_step()
    units = dict(s.units)
    rv = units["review"]
    gate = dataclasses.replace(rv.gate, judge=dataclasses.replace(rv.gate.judge, subject=("verdict",)))
    units["review"] = dataclasses.replace(rv, gate=gate, step=dataclasses.replace(
        rv.step, produces={**rv.step.produces, "pr": "pull_request"}))
    return dataclasses.replace(s, units=units)


def test_external_effects_need_consent(repo: Path) -> None:  # RRN-B6, AC-5
    cat = Catalog(specs={"demo": with_pr()})
    pr = answer("Opened it\nARTIFACT verdict: ok\nARTIFACT pr: https://example.test/pr/1", session_id="s-r")
    ex = standin("claude", steps=[DRAFT, pr], judges=[judge(), judge()])
    code, _, err = cli(repo, ex, "run", "demo", "notes", "--task-id", "R-4", catalog=cat)
    assert code == 0, err
    code, doc, _ = cli(repo, None, "rerun", "demo", "R-4", "--from", "draft", "--check", catalog=cat)
    assert code == 2 and "review: pull_request" in json.dumps(doc)
    ex = standin("claude", steps=[DRAFT, pr], judges=[judge(), judge()])
    code, _, err = cli(repo, ex, "rerun", "demo", "R-4", "--from", "draft", "--accept-external", catalog=cat)
    assert code == 0, err


def test_same_branch_supersedes_a_finished_source(repo: Path) -> None:  # RRN-B17, RRN-B18 Workspace
    finished(repo, "R-5")
    ex = standin("claude", steps=[REVIEW], judges=[judge()])
    code, doc, _ = cli(repo, ex, "rerun", "demo", "R-5", "--from", "review", "--same-branch", "--check")
    assert code == 0 and doc["workspace"]["branch"] == "tg/demo/R-5"
    code, _, err = cli(repo, ex, "rerun", "demo", "R-5", "--from", "review", "--same-branch")
    assert code == 0, err
    ws = [r for r in records(repo, "R-5~r1", "workspace")]
    assert ws[0]["action"] == "reused" and ws[0]["branch"] == "tg/demo/R-5"
    lineage = json.loads((repo / ".tempergraph" / "runs" / "demo" / "R-5" / "lineage.json").read_text())
    assert lineage["superseded_by"] == "demo/R-5~r1" and lineage["reruns"][0]["same_branch"] is True
    from .test_feedback import paused

    paused(repo, "R-6", Seen())
    for extra in (["--check"], []):
        code, _, err = cli(repo, happy(), "rerun", "demo", "R-6", "--from", "review", "--same-branch", *extra)
        assert code == 2
    assert not (repo / ".tempergraph" / "runs" / "demo" / "R-6~r1").exists()
