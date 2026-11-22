"""A finding about a sub-workflow child's unit is filed to the child workflow, the parent named (SWF-B9, SWF-AC1;
task AC 2; SIL-B18)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph import detach
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import read_findings

from .fixtures.subworkflows import home_dir, register_workflow
from .test_loop_child import tickets
from .test_run import DRAFT, REVIEW, judge, registry, verdict_block
from .test_subworkflow_run import WORK, go, parent


def child_attributed(req: Any) -> Any:
    """The loop's friction judge: it attributes to the workflow, at 0.8, only the finding about the child's unit."""
    rows = [{"fingerprint": ln.split("`")[1], "attributed": "a child of" in ln, "confidence": 0.8}
            for ln in req.prompt.splitlines() if ln.startswith("- `") and "cause" in ln]
    return answer("```json\n" + json.dumps({"findings": rows}) + "\n```", session_id="loop")


def test_a_friction_finding_on_a_child_unit_files_to_the_child_and_names_the_parent(
        tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SWF-AC1, AC 2
    register_workflow(home_dir(), tmp_path / "pkgs", "repo-setup", produces=["overview"], version="0.3.1",
                      issue_repository="acme/repo-setup")
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr(detach, "start", lambda *a, **k: True)  # the loop's child is started by drain() below
    spec = dataclasses.replace(parent(workflow="repo-setup"), issue_repository="acme/deliver")
    # the child's `work` gate blocks once, then passes: a `judge_blocked` fault on the child's unit
    ex = standin("claude", steps=[DRAFT, WORK, WORK, REVIEW],
                 judges=[judge(), judge(verdict_block("UNMET")), judge(), judge(), judge()])
    assert go(repo, ex, spec).exit_code is ExitCode.FINISHED
    root = repo / ".tempergraph"
    found = [f for f in read_findings(root, "deliver", "T-1") if f.get("child")]
    assert found, "the child's blocked attempt left no finding of its own"
    f = next(x for x in found if x["cause"] == "judge_blocked:c-work")
    assert (f["unit"], f["child"], f["workflow"], f["workflow_version"], f["parent"]) == (
        "work", "setup", "repo-setup", "0.3.1", "deliver")
    assert f["side"] == "workflow" and f["class"] == "fault" and f["issue_repository"] == "acme/repo-setup"
    assert not [x for x in read_findings(root, "deliver", "T-1") if x["unit"] == "work" and not x.get("child")]
    (t,) = tickets()
    host = MemoryCodeHost()
    (out,) = child.drain(registry=registry(standin("claude", judges=[child_attributed])), host=lambda: host)
    assert [r["op"] for r in out["results"] if r["op"] != "recorded"] == ["filed"]
    assert [i["repo"] for i in host.issues] == ["acme/repo-setup"]  # none in the parent's repository
    issue = host.issues[0]
    assert "repo-setup" in issue["title"] and "side:workflow" in issue["labels"]
    assert "**Parent** `deliver`" in issue["body"] and "version `0.3.1`" in issue["body"]
    assert not t.exists()
