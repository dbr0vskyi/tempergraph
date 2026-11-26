"""The files a run wrote are those that differ between its branch start and its end commit, and the unit whose session
changed each one is on its `agent_run` record (OUT-B28, OUT-AC12, SIL-B33, SIL-AC32; task AC 1, AC 9). Every run here
is a real fixture run through `go`: its steps write a file and commit it, its finalizer returns a pull request url,
and no log or ledger record of it is written by hand."""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import callable_ref
from tempergraph.catalog import Catalog
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.standins import answer, standin
from tempergraph.store.layout import state_root_path

from .test_cli import cli
from .test_outcome_escape_finding import escapes, process
from .test_pr_later import REPO, commit, head, opened_pr, pr_host, read_one, rows, segment, state
from .test_run import REVIEW, go, judge, records, verdict_block, with_outcome_spec

MET2 = verdict_block("MET", "MET")
MET = verdict_block("MET")
FILE = "notes.md"


def writes_and_commits(*, tool: bool) -> Any:
    """A scripted step reply that writes `notes.md` in the session's own folder and commits it, with a `Write` tool
    call in its result (`tool`) or through a shell command alone."""
    def reply(req: SessionRequest) -> SessionResult:
        (req.workdir / FILE).write_text("written by the step\n")
        subprocess.run(["git", "add", "--", FILE], cwd=req.workdir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "--no-verify", "-m", "step writes"], cwd=req.workdir, check=True,
                       capture_output=True)
        return answer("Wrote notes.md\nARTIFACT notes: notes.md", tools=("Write",) if tool else (),
                      session_id="s-draft")
    return reply


def spec_with_pull_request() -> Any:
    spec = dataclasses.replace(with_outcome_spec(), finalizer=callable_ref(opened_pr), finalizer_outcomes=("opened",),
                               session_review="off")
    return spec


def run_that_commits(repo: Path, task: str, *, tool: bool) -> Any:
    spec = spec_with_pull_request()
    ex = standin("claude", steps=[writes_and_commits(tool=tool), REVIEW],
                 judges=[judge(MET2), judge(MET), judge(MET, sid="o")])
    out = go(repo, ex, spec=spec, task=task)
    assert out.exit_code is ExitCode.FINISHED, out.message
    return spec


@pytest.mark.parametrize("tool", [True, False], ids=["write-tool", "shell-command"])
def test_a_follow_up_commit_on_a_file_a_step_committed_is_an_escape_for_that_unit(repo: Path, tool: bool) -> None:
    # OUT-AC12, SIL-AC32, task AC 1, AC 9: the files come from git, whichever tool or command wrote them
    task = "W-1" if tool else "S-1"
    spec = run_that_commits(repo, task, tool=tool)
    root = state_root_path(repo)

    (step,) = [r for r in records(repo, task) if r["kind"] == "agent_run" and r.get("session_kind") == "step"
               and r["unit"] == "draft"]
    assert FILE in step["wrote_paths"]
    (review,) = [r for r in records(repo, task) if r["kind"] == "agent_run" and r.get("session_kind") == "step"
                 and r["unit"] == "review"]
    assert review["wrote_paths"] == []

    (seg,) = rows(root, "run_segment")
    end = seg["pull_request"]["commit"]
    assert end
    host = pr_host()
    host.pulls.append({"repo": REPO, "number": 7, "state": "open", "draft": True})
    host.commits[(REPO, 7)] = [commit(end, []), commit("bbbbbbb2", [FILE])]  # a person's commit after the end commit
    process(root, host)

    (later,) = rows(root)
    assert later["thread_id"] == f"demo/{task}" and later["entry"]["files"] == 1 and later["entry"]["commits"] == 1

    cat = Catalog(specs={"demo": spec})
    code, doc, err = cli(repo, None, "outcome", "show", "demo", "--runs", catalog=cat)
    assert code == 0, err
    assert doc["runs"][0]["escapes"] == 1
    code, doc, err = cli(repo, None, "outcome", "candidates", "demo", "--window", "30", catalog=cat)
    assert code == 0, err
    (esc,) = [c for c in doc["candidates"] if c["signal"] == "escape"]
    assert esc["threads"] == [f"demo/{task}"]

    (found,) = escapes(root, task)
    assert found["unit"] == "draft"


def test_a_run_whose_workspace_has_no_base_commit_has_no_files(tmp_path: Path) -> None:
    # OUT-AC12, task AC 1: no base commit is known, so no file is a file the run wrote
    root = state(tmp_path)
    segment(root, "T-1", 1)  # a recorded pull request and no run log, so no `workspace` record
    host = pr_host()
    host.commits[(REPO, 1)] = [commit(head(root), []), commit("bbbbbbb2", ["a.py"])]
    read_one(root, host)
    (later,) = rows(root)
    assert later["entry"]["commits"] == 1 and later["entry"]["files"] == 0
