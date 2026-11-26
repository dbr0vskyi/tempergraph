"""A finalizer url that names a pull request is recorded on the run's ledger row (FIN-B11, FIN-AC5; task AC 1)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import callable_ref
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.run.finalize import FinalizerResult
from tempergraph.store.layout import state_root_path

from .fixtures.workflows import two_step
from .test_run import DRAFT, REVIEW, go, judge

REASON = "CANARY-REASON-TEXT"
PR = "https://example.test/acme/notes/pull/12"


def opened_pr(ctx: Any) -> FinalizerResult:
    return FinalizerResult(outcome="opened", reason=REASON, url=PR)


def opened_issue(ctx: Any) -> FinalizerResult:
    return FinalizerResult(outcome="opened", reason=REASON, url="https://example.test/acme/notes/issues/12")


def opened_nothing(ctx: Any) -> FinalizerResult:
    return FinalizerResult(outcome="opened", reason=REASON)


def spec_with(fn: Any) -> Any:
    return dataclasses.replace(two_step(), finalizer=callable_ref(fn), finalizer_outcomes=("opened",))


def segments(repo: Path) -> list[dict[str, Any]]:
    p = state_root_path(repo) / "ledger.jsonl"
    rows = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    return [r for r in rows if r.get("kind") == "run_segment"]


def run(repo: Path, fn: Any) -> Any:
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    return go(repo, ex, spec_with(fn))


def test_a_pull_request_url_leaves_host_repository_number_and_commit(repo: Path) -> None:  # FIN-AC5, task AC 1
    out = run(repo, opened_pr)
    assert out.exit_code is ExitCode.FINISHED, out.message
    rows = segments(repo)
    assert len(rows) == 1
    pr = rows[0]["pull_request"]
    assert set(pr) == {"host", "repo", "number", "commit"}
    assert (pr["host"], pr["repo"], pr["number"]) == ("example.test", "acme/notes", 12)
    assert isinstance(pr["commit"], str) and len(pr["commit"]) >= 7
    assert REASON not in json.dumps(rows[0])  # no text of the finalizer's result


@pytest.mark.parametrize("fn", [opened_issue, opened_nothing])
def test_no_pull_request_url_leaves_no_field_and_exits_zero(repo: Path, fn: Any) -> None:  # FIN-AC5, task AC 1
    out = run(repo, fn)
    assert out.exit_code is ExitCode.FINISHED, out.message
    rows = segments(repo)
    assert len(rows) == 1 and "pull_request" not in rows[0]
