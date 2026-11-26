"""Feedback and lasting rulings on resume (RRN-B14, RRN-B15, RRN-B1, B2, B4, B11, AC-2, AC-6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.executors.standins import ScriptedExecutor, standin

from .test_cli import cli
from .test_run import DRAFT, REVIEW, judge, verdict_block

RULE = "Keep the public API unchanged CANARY-RULE"


class Seen:
    """Stand-in replies that remember every prompt they were given."""

    def __init__(self) -> None:
        self.prompts: list[tuple[str, str]] = []

    def __call__(self, reply: Any) -> Any:
        def give(req: Any) -> Any:
            self.prompts.append((req.session_key, req.prompt))
            return reply
        return give

    def with_text(self, text: str) -> list[str]:
        return [k for k, p in self.prompts if text in p]


def paused(repo: Path, task: str, seen: Seen) -> ScriptedExecutor:
    ex = standin("claude", steps=[seen(DRAFT)], judges=[seen(judge(verdict_block("UNVERIFIABLE")))])
    code, _, err = cli(repo, ex, "run", "demo", "notes", "--task-id", task)
    assert code == 3, err
    return ex


def records(repo: Path, task: str, kind: str) -> list[dict[str, Any]]:
    log = repo / ".tempergraph" / "runs" / "demo" / task / "run.jsonl"
    return [r for r in (json.loads(x) for x in log.read_text().splitlines()) if r.get("kind") == kind]


def test_a_ruling_reaches_every_later_attempt_and_judge(repo: Path) -> None:  # RRN-B1, AC-2
    seen = Seen()
    ex = paused(repo, "F-1", seen)
    ex.steps = [seen(DRAFT), seen(REVIEW)]
    ex.judges = [seen(judge()), seen(judge())]
    code, _, err = cli(repo, ex, "resume", "demo", "F-1", "--decision", "retry", "--ruling", "--feedback", RULE)
    assert code == 0, err
    hit = seen.with_text(RULE)
    assert any(k.startswith("draft") and "judge" not in k for k in hit)  # the retried step
    assert any(k.startswith("draft") and "judge" in k for k in hit)  # its judge
    assert any(k.startswith("review") and "judge" not in k for k in hit)  # a later unit
    assert any(k.startswith("review") and "judge" in k for k in hit)
    assert all("`ruling`" in p for k, p in seen.prompts if k in hit and "judge" in k)
    given = records(repo, "F-1", "ruling")
    assert given == [{**given[0], "id": "r1", "action": "given", "given_at": "draft", "chars": len(RULE)}]
    # AC-6: the text stays out of the run log and the ledger
    for f in (repo / ".tempergraph" / "runs" / "demo" / "F-1" / "run.jsonl", repo / ".tempergraph" / "ledger.jsonl"):
        assert "CANARY-RULE" not in f.read_text()
    row = [json.loads(x) for x in (repo / ".tempergraph" / "ledger.jsonl").read_text().splitlines()
           if '"intervention"' in x][0]
    assert row["ruling"] is True and row["feedback"] is False


def test_one_time_feedback_stays_one_time(repo: Path) -> None:  # RRN-B2
    seen = Seen()
    ex = paused(repo, "F-2", seen)
    ex.steps = [seen(DRAFT), seen(REVIEW)]
    ex.judges = [seen(judge()), seen(judge())]
    code, _, err = cli(repo, ex, "resume", "demo", "F-2", "--decision", "retry", "--feedback", "rename the flag")
    assert code == 0, err
    hit = seen.with_text("rename the flag")
    assert sorted(k.split("-")[0].split(".")[0] for k in hit) and all(k.startswith("draft") for k in hit)
    assert any("judge" in k for k in hit)  # the retried step's judge sees it too


def test_revoke_a_ruling(repo: Path) -> None:  # RRN-B11
    seen = Seen()
    ex = paused(repo, "F-3", seen)
    ex.steps = [seen(DRAFT), seen(REVIEW)]
    ex.judges = [seen(judge()), seen(judge(verdict_block("UNVERIFIABLE")))]
    code, _, _ = cli(repo, ex, "resume", "demo", "F-3", "--decision", "retry", "--ruling", "--feedback", RULE)
    assert code == 3  # paused again, at review
    seen.prompts.clear()
    ex.steps, ex.judges = [seen(REVIEW)], [seen(judge())]
    code, _, err = cli(repo, ex, "resume", "demo", "F-3", "--decision", "retry", "--revoke-ruling", "r1")
    assert code == 0, err
    assert seen.prompts and not seen.with_text(RULE)
    revoked = records(repo, "F-3", "ruling")[-1]
    assert revoked["action"] == "revoked" and revoked["id"] == "r1" and revoked["by"]["kind"] == "person"


def test_refusals_write_nothing(repo: Path) -> None:  # RRN-B16, RRN-B17, RRN-B18, RRN-B14, RRN-B15
    from .conftest import hash_tree

    seen = Seen()
    ex = paused(repo, "F-4", seen)
    before = hash_tree(repo / ".tempergraph")
    for argv in (["--revoke-ruling", "r9"], ["--feedback", "x" * 8001], ["--ruling"],
                 ["--ruling", "--feedback", "y", "--ruling-for", "nope"]):
        code, _, err = cli(repo, ex, "resume", "demo", "F-4", "--decision", "retry", *argv)
        assert code == 2 and err, argv
    assert hash_tree(repo / ".tempergraph") == before


def test_feedback_on_an_unfinished_thread(repo: Path) -> None:  # RRN-B4
    seen = Seen()
    ex = standin("claude", steps=[seen(DRAFT), seen(DRAFT)], judges=[seen(judge(verdict_block("UNMET"))), seen(judge())])
    code, _, _ = cli(repo, ex, "run", "demo", "notes", "--task-id", "F-5", "--set", "run.attempt_cap=1")  # the retry counts
    assert code != 0  # drained before review started
    ex.steps, ex.judges = [seen(REVIEW)], [seen(judge())]
    code, _, err = cli(repo, ex, "resume", "demo", "F-5", "--decision", "proceed", "--feedback", "z")
    assert code == 2 and err
    code, _, err = cli(repo, ex, "resume", "demo", "F-5", "--feedback", "use the existing retry helper")
    assert code == 0, err
    hit = seen.with_text("use the existing retry helper")
    assert any(k.startswith("review") and "judge" not in k for k in hit)
    assert any(k.startswith("review") and "judge" in k for k in hit)
