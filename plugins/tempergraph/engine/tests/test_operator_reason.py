"""A decision's operator reason: `resume --reason` reaches the ledger, the judge's facts and an issue (CLI-B24, CLI-B25,
SIL-B37, SIL-B50)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tempergraph.executors.standins import standin
from tempergraph.improve import child
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.run.runner import ledger_rows
from tempergraph.store.layout import state_root_path

from .conftest import hash_tree
from .test_cli import cli
from .test_pause_findings_at_final_exit import (
    facts_of,
    finding_of,
    gap_only,
    judged_prompts,
    paused_on_gap,
)
from .test_run import REVIEW, judge, registry

WORDS = ("engine_defect", "judge_error", "environment", "plan", "request", "other")


def resumed(repo: Path, task: str, monkeypatch: pytest.MonkeyPatch, *extra: str) -> tuple[int, str]:
    ex = paused_on_gap(repo, task, monkeypatch)
    ex.steps, ex.judges = [REVIEW], [judge()]
    code, _, err = cli(repo, ex, "resume", "demo", task, "--decision", "proceed", *extra)
    return code, err


def own_rows(repo: Path, task: str) -> list[dict[str, object]]:
    return [r for r in ledger_rows(state_root_path(repo)) if r.get("kind") == "intervention"
            and r.get("thread_id") == f"demo/{task}"]


@pytest.mark.parametrize("word", WORDS)
def test_a_reason_is_on_the_ledger_row_of_the_decision(
        repo: Path, monkeypatch: pytest.MonkeyPatch, word: str) -> None:  # CLI-AC14, AC 4
    code, err = resumed(repo, "O-1", monkeypatch, "--reason", word)
    assert code == 0, err
    (row,) = own_rows(repo, "O-1")
    assert row["operator_reason"] == word


def test_no_reason_leaves_the_key_out(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # CLI-AC14, AC 4
    code, err = resumed(repo, "O-2", monkeypatch)
    assert code == 0, err
    (row,) = own_rows(repo, "O-2")
    assert "operator_reason" not in row


@pytest.mark.parametrize("value", ["the check was wrong", "flaky"])
def test_any_other_reason_is_refused_before_a_write(
        repo: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:  # CLI-AC14, AC 4
    ex = paused_on_gap(repo, "O-3", monkeypatch)
    before = hash_tree(state_root_path(repo))
    code, _, err = cli(repo, ex, "resume", "demo", "O-3", "--decision", "proceed", "--reason", value)
    assert code == 2
    assert all(w in err for w in WORDS), err
    assert hash_tree(state_root_path(repo)) == before
    assert own_rows(repo, "O-3") == []


def test_resume_help_names_the_option_and_the_words(
        repo: Path, capsys: pytest.CaptureFixture[str]) -> None:  # CLI-AC15, AC 4
    cli(repo, None, "resume", "--help")
    out = capsys.readouterr().out
    assert "--reason" in out and all(w in out for w in WORDS)


def test_the_judge_is_told_the_reason_or_that_none_was_given(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC60, AC 4
    code, err = resumed(repo, "O-4", monkeypatch, "--reason", "judge_error")
    assert code == 0, err
    (prompt,) = judged_prompts()
    line = facts_of(prompt, finding_of(repo, "O-4", "gap_escalation")["fingerprint"])
    assert "operator reason `judge_error`" in line, line
    code, err = resumed(repo, "O-5", monkeypatch)
    assert code == 0, err
    (prompt,) = judged_prompts()
    line = facts_of(prompt, finding_of(repo, "O-5", "gap_escalation")["fingerprint"])
    assert "operator reason not given" in line, line


def test_the_brief_says_a_reason_other_than_plan_or_request_points_away_from_the_step(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC61, AC 4
    code, err = resumed(repo, "O-6", monkeypatch, "--reason", "environment")
    assert code == 0, err
    (prompt,) = judged_prompts()
    flat = " ".join(prompt.split())
    assert "operator reason other than `plan` or `request` points away from the workflow's step" in flat


def test_an_issue_shows_the_reason_in_its_facts_line(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC60, ISS-B15, AC 4
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    ex = paused_on_gap(repo, "O-7", monkeypatch)
    ex.steps, ex.judges = [REVIEW], [judge()]
    code, _, err = cli(repo, ex, "resume", "demo", "O-7", "--decision", "proceed", "--reason", "judge_error")
    assert code == 0, err
    host = MemoryCodeHost()
    child.drain(registry=registry(standin("claude", judges=[gap_only])), host=lambda: host)
    (issue,) = host.issues
    run = issue["body"].split("## Run\n")[1].split("\n## ")[0]
    assert "operator_reason=judge_error" in run, run
