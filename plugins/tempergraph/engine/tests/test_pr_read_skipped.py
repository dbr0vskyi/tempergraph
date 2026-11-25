"""A pull request that cannot be read leaves one `loop_skipped` record and the others are read (OUT-B31; task AC 4)."""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import callable_ref
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.improve import child
from tempergraph.improve.codehost import CodeHostError
from tempergraph.store.layout import state_root_path

from .test_pr_later import QUIET, CountingHost, hand, opened_pr, pr_host, rows, segment, state, ticket_of
from .test_run import DRAFT, REVIEW, go, judge, registry


@dataclasses.dataclass(kw_only=True)
class FailsFirst(CountingHost):
    def pull_state(self, repo: str, number: int) -> dict[str, Any]:
        if number == 1:
            raise CodeHostError("secret text of the failure")
        return super().pull_state(repo, number)


def skipped(root: Path, task: str) -> list[dict[str, Any]]:
    p = child.loop_log(root, "demo", task)
    out = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()] if p.exists() else []
    return [r for r in out if r.get("kind") == "loop_skipped" and r.get("step") == "pull_request_read"]


def test_out_ac14_an_unreadable_pull_request_leaves_one_record_and_the_other_is_read(tmp_path: Path) -> None:
    # OUT-AC14, task AC 4
    root = state(tmp_path)
    segment(root, "T-1", 1)
    segment(root, "T-2", 2)
    host = FailsFirst()
    for n in (1, 2):
        host.pulls.append({"repo": "acme/notes", "number": n, "state": "open", "draft": True})
    t = ticket_of(hand(root))
    out = child.process(t, registry(standin("claude")), host)
    got = skipped(root, "T-1")
    assert len(got) == 1
    rec = got[0]
    assert (rec["reason"], rec["thread"], rec["number"], rec["error"]) == ("error", "demo/T-1", 1, "CodeHostError")
    assert "secret text" not in json.dumps(rec)
    assert all(isinstance(v, (int, str)) for v in rec.values())
    assert set(rec) == {"ts", "kind", "step", "reason", "thread", "number", "error"}
    assert [r["thread_id"] for r in rows(root)] == ["demo/T-2"]  # pull request 2 was read
    assert host.asked == [2]
    assert out["results"] == [] and out.get("exit_code") in (None, 0)


def test_out_ac7_a_run_whose_host_is_down_still_finishes_and_leaves_one_record(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # OUT-AC14, OUT-AC7, task AC 4
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "inline")
    real = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None if name == "gh" else real(name, *a, **k))
    spec = dataclasses.replace(QUIET, finalizer=callable_ref(opened_pr), finalizer_outcomes=("opened",))
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, spec=spec, task="G-1").exit_code is ExitCode.FINISHED
    root = state_root_path(repo)
    assert rows(root) == []
    assert len(skipped(root, "G-1")) == 1


def test_out_ac14_a_host_that_answers_is_not_skipped(tmp_path: Path) -> None:
    # OUT-AC14, task AC 4
    root = state(tmp_path)
    segment(root, "T-1", 1)
    child.process(ticket_of(hand(root)), registry(standin("claude")), pr_host())
    assert skipped(root, "T-1") == []
