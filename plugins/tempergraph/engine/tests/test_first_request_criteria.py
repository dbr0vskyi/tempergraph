"""Criteria 1 to 5 of the first request, each proved on a real fixture run (task AC 9): the steps write a file and commit
it, the finalizer returns a pull request url, the pull request is read through a fake host, and no ledger or log record
is written by hand. Criterion 1: a run records its pull request (FIN-AC5); 2: the loop reads it into a `later[]` entry
of counts (OUT-AC8); 3: a `met` run with a change request or a follow-up commit on a file it wrote is an escape that
fires the outcome lens in stable mode (OUT-AC10, SIL-AC29); 4: an escape is a harvest candidate and corroborates review
observations on the writing units (SIL-AC30, LIF-AC12); 5: a canary reaches no filed issue and no ledger row (FBK-AC7)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tempergraph.catalog import Catalog
from tempergraph.improve import review
from tempergraph.store.layout import state_root_path

from .test_cli import cli
from .test_outcome_escape_finding import escapes, loop_kinds, observe, process
from .test_pr_later import QUIET, REPO, comment, commit, pr_host, rows
from .test_pr_later import review as pr_review
from .test_pr_run_files import FILE, run_that_commits

CANARY = "CANARY-5d2c-first-request-do-not-leak"
STABLE = dataclasses.replace(QUIET, improvement_mode="stable")


def read_run(repo: Path, task: str, *, review_state: str = "", follow_up: bool = False, canary: str = "") -> Any:
    """One real run that commits `notes.md` and opens pull request 7, then one read of it: returns the state root, the
    host and the spec."""
    spec = run_that_commits(repo, task, tool=True)
    root = state_root_path(repo)
    (seg,) = rows(root, "run_segment")
    end = seg["pull_request"]["commit"]
    host = pr_host()
    host.pulls.append({"repo": REPO, "number": 7, "state": "open", "draft": True})
    if review_state:
        host.reviews[(REPO, 7)] = [pr_review(review_state, text=canary or "please change")]
    if canary:
        host.review_comments[(REPO, 7)] = [comment(text=canary)]
    host.commits[(REPO, 7)] = [commit(end, [])] + ([commit("bbbbbbb2", [FILE])] if follow_up else [])
    process(root, host, STABLE)
    return root, host, spec


def test_fin_ac5_criterion_1_a_run_records_its_pull_request(repo: Path) -> None:  # FIN-AC5, task AC 9
    run_that_commits(repo, "C-1", tool=True)
    (seg,) = rows(state_root_path(repo), "run_segment")
    pr = seg["pull_request"]
    assert (pr["host"], pr["repo"], pr["number"]) == ("example.test", REPO, 7)
    assert len(pr["commit"]) == 40


def test_out_ac8_criterion_2_the_read_appends_one_entry_of_counts_and_no_text(repo: Path) -> None:
    # OUT-AC8, task AC 9
    root, _, _ = read_run(repo, "C-2", review_state="changes_requested", follow_up=True, canary=CANARY)
    (later,) = rows(root)
    entry = later["entry"]
    assert entry["reviews"] == {"changes_requested": 1} and entry["comments"] == 1
    assert entry["commits"] == 1 and entry["files"] == 1
    assert CANARY not in json.dumps(later)


def test_out_ac10_sil_ac29_criterion_3_a_change_request_is_an_escape_and_fires_the_lens(repo: Path) -> None:
    # OUT-AC10, SIL-AC29, task AC 9
    root, _, spec = read_run(repo, "C-3", review_state="changes_requested")
    code, doc, err = cli(repo, None, "outcome", "show", "demo", "--runs", catalog=Catalog(specs={"demo": spec}))
    assert code == 0, err
    assert doc["runs"][0]["escapes"] == 1
    assert [r["thread"] for r in loop_kinds(root) if r["kind"] == "loop_lens"] == ["demo/C-3"]
    (found,) = escapes(root, "C-3")
    assert found["lens"] == "outcome"


def test_sil_ac30_lif_ac12_criterion_4_an_escape_is_a_candidate_and_corroborates_observations(repo: Path) -> None:
    # SIL-AC30, LIF-AC12, task AC 9
    root, _, spec = read_run(repo, "C-4", review_state="changes_requested", follow_up=True)
    code, doc, err = cli(repo, None, "outcome", "candidates", "demo", "--window", "30",
                         catalog=Catalog(specs={"demo": spec}))
    assert code == 0, err
    (esc,) = [c for c in doc["candidates"] if c["signal"] == "escape"]
    assert esc["threads"] == ["demo/C-4"]
    assert "draft" in [f["unit"] for f in escapes(root, "C-4")]
    observe(root, "C-4", "draft")  # a review observation kept on the unit that wrote the file
    assert review.corroborate(root, "demo", "C-4", "demo/C-4") >= 1
    (draft,) = [f for f in escapes(root, "C-4") if f["unit"] == "draft"]
    assert draft["review"] == "review:tool_thrash" and draft["review_weight"] == 1


def test_fbk_ac7_criterion_5_a_canary_reaches_no_issue_and_no_ledger_row(repo: Path) -> None:
    # FBK-AC7, task AC 9
    root, host, _ = read_run(repo, "C-5", review_state="changes_requested", follow_up=True, canary=CANARY)
    assert CANARY not in json.dumps(host.issues, default=str)
    assert CANARY not in (root / "ledger.jsonl").read_text(encoding="utf-8")
    hits = [p for p in root.rglob("*") if p.is_file() and CANARY in p.read_text(encoding="utf-8", errors="ignore")]
    assert [p.name for p in hits] == ["pull_request.jsonl"]  # only the run's local evidence holds the text
