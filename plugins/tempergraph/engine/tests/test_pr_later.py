"""The loop reads a recorded pull request and appends a `later[]` entry of counts and kinds (OUT-B23 to OUT-B25; task AC 2)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import callable_ref
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.improve import child
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.run.finalize import FinalizerResult
from tempergraph.run.log import Ledger
from tempergraph.store.layout import state_root_path

from .fixtures.workflows import two_step
from .test_run import DRAFT, REVIEW, go, judge, registry

CLEAN = {"lenses": {"friction": False}, "fault_fingerprints": [], "outcome_fingerprints": [], "fingerprints": []}
QUIET = dataclasses.replace(two_step(), session_review="off")
REPO = "acme/notes"
END = "aaaaaaa1"
MARKER = "<!-- tg-agent: kind=report agent=loop -->"


def opened_pr(ctx: Any) -> FinalizerResult:
    return FinalizerResult(outcome="opened", url="https://example.test/acme/notes/pull/7")


@dataclasses.dataclass(kw_only=True)
class CountingHost(MemoryCodeHost):
    asked: list[int] = dataclasses.field(default_factory=list)

    def pull_state(self, repo: str, number: int) -> dict[str, Any]:
        self.asked.append(number)
        return super().pull_state(repo, number)


def pr_host(**kw: Any) -> CountingHost:
    host = CountingHost(**kw)
    for n in (1, 2):
        host.pulls.append({"repo": REPO, "number": n, "state": "open", "draft": True})
    return host


def segment(root: Path, task: str, number: int, commit: str = END) -> None:
    Ledger(path=root / "ledger.jsonl").append(
        {"kind": "run_segment", "thread_id": f"demo/{task}", "workflow": "demo", "exit_code": 0,
         "pull_request": {"host": "example.test", "repo": REPO, "number": number, "commit": commit}})


def later_row(root: Path, task: str, state: str) -> None:
    Ledger(path=root / "ledger.jsonl").append(
        {"kind": "outcome_later", "thread_id": f"demo/{task}", "workflow": "demo",
         "entry": {"state": state, "reviews": {}, "comments": 0, "commits": 0, "files": 0}})


def wrote(root: Path, task: str, unit: str, *paths: str) -> None:
    p = root / "runs" / "demo" / task / "run.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "agent_run", "unit": unit, "changed_paths": list(paths)}) + "\n")


def rows(root: Path, kind: str = "outcome_later") -> list[dict[str, Any]]:
    p = root / "ledger.jsonl"
    out = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()] if p.exists() else []
    return [r for r in out if r.get("kind") == kind]


def hand(root: Path, summary: dict[str, Any] = CLEAN, **kw: Any) -> Path | None:
    kw.setdefault("dry_run", False)
    return child.hand_off(root, QUIET, "T-1", "demo/T-1", summary, judge_executor="claude", home=root / "home", **kw)


def ticket_of(path: Path | None) -> dict[str, Any]:
    assert path is not None
    return json.loads(path.read_text())


def review(state: str = "changes_requested", kind: str = "person", text: str = "REVIEW-TEXT") -> dict[str, Any]:
    return {"state": state, "author_kind": kind, "text": text}


def comment(kind: str = "person", text: str = "COMMENT-TEXT") -> dict[str, Any]:
    return {"author_kind": kind, "text": text, "path": "a.py"}


def commit(sha: str, files: list[str], kind: str = "person") -> dict[str, Any]:
    return {"sha": sha, "author_kind": kind, "files": files}


# -- OUT-AC7: which pull requests are read ------------------------------------------------------------------------

def test_a_ticket_is_written_for_a_workflow_with_only_a_recorded_pull_request(tmp_path: Path) -> None:
    # OUT-AC7, task AC 2
    assert hand(tmp_path) is None  # nothing recorded, nothing to watch
    segment(tmp_path, "T-1", 1)
    t = ticket_of(hand(tmp_path))
    assert t["watch_only"] is True and t["autonomy"] == "file"
    later_row(tmp_path, "T-1", "merged")
    assert hand(tmp_path) is None  # found merged: nothing left to read


def test_only_the_pull_request_not_found_merged_or_closed_is_read(tmp_path: Path) -> None:  # OUT-AC7, task AC 2
    segment(tmp_path, "T-1", 1)
    segment(tmp_path, "T-2", 2)
    later_row(tmp_path, "T-2", "merged")
    host = pr_host()
    child.process(ticket_of(hand(tmp_path)), registry(standin("claude")), host)
    assert host.asked == [1]


@pytest.mark.parametrize("change", [{"autonomy": "record"}, {"dry_run": True}])
def test_at_autonomy_record_and_in_a_dry_run_the_host_is_not_asked(tmp_path: Path, change: dict[str, Any]) -> None:
    # OUT-AC7, task AC 2
    segment(tmp_path, "T-1", 1)
    t = {**ticket_of(hand(tmp_path)), **change}
    host = pr_host()
    child.process(t, registry(standin("claude")), host)
    assert host.asked == [] and rows(tmp_path) == []


def test_a_host_that_is_down_appends_nothing(tmp_path: Path) -> None:  # OUT-AC7, task AC 2
    segment(tmp_path, "T-1", 1)
    out = child.process(ticket_of(hand(tmp_path)), registry(standin("claude")), pr_host(down=True))
    assert rows(tmp_path) == [] and out["results"] == []


def test_a_missing_gh_appends_nothing_and_the_run_keeps_its_exit_code(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # OUT-AC7, task AC 2
    import shutil

    monkeypatch.setenv("TEMPERGRAPH_LOOP", "inline")
    real = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None if name == "gh" else real(name, *a, **k))

    spec = dataclasses.replace(QUIET, finalizer=callable_ref(opened_pr), finalizer_outcomes=("opened",))
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, spec=spec, task="G-1").exit_code is ExitCode.FINISHED
    root = state_root_path(repo)
    assert len(rows(root, "run_segment")) == 1 and rows(root) == []
    assert (child.loop_log(root, "demo", "G-1")).exists()  # the ticket was processed, the read tried


# -- OUT-AC8: the entry and where the text goes -------------------------------------------------------------------

def read_one(root: Path, host: MemoryCodeHost) -> dict[str, Any]:
    return child.process(ticket_of(hand(root)), registry(standin("claude")), host)


def test_a_read_appends_one_entry_of_counts_and_no_text(tmp_path: Path) -> None:  # OUT-AC8, task AC 2
    segment(tmp_path, "T-1", 1)
    wrote(tmp_path, "T-1", "draft", "a.py")
    host = pr_host()
    host.reviews[(REPO, 1)] = [review()]
    host.review_comments[(REPO, 1)] = [comment(), comment(text="SECOND")]
    host.commits[(REPO, 1)] = [commit(END, ["old.py"]), commit("bbbbbbb2", ["a.py", "other.py"])]
    read_one(tmp_path, host)
    got = rows(tmp_path)
    assert len(got) == 1
    row = got[0]
    assert (row["thread_id"], row["workflow"]) == ("demo/T-1", "demo")
    assert row["entry"] == {"state": "open", "reviews": {"changes_requested": 1}, "comments": 2, "commits": 1,
                            "files": 1}
    assert "REVIEW-TEXT" not in json.dumps(row) and "COMMENT-TEXT" not in json.dumps(row)
    assert "REVIEW-TEXT" not in (tmp_path / "ledger.jsonl").read_text()
    evidence = (tmp_path / "runs" / "demo" / "T-1" / "evidence" / "pull_request.jsonl").read_text()
    assert "REVIEW-TEXT" in evidence and "COMMENT-TEXT" in evidence
    read_one(tmp_path, host)  # a second read of an unchanged pull request
    assert len(rows(tmp_path)) == 1


def test_a_changed_pull_request_appends_a_new_entry(tmp_path: Path) -> None:  # OUT-AC8, task AC 2
    segment(tmp_path, "T-1", 1)
    host = pr_host()
    read_one(tmp_path, host)
    host.reviews[(REPO, 1)] = [review("approved")]
    read_one(tmp_path, host)
    assert [r["entry"]["reviews"] for r in rows(tmp_path)] == [{}, {"approved": 1}]


# -- OUT-AC9: only a person's work counts -------------------------------------------------------------------------

def test_bots_the_agent_marker_and_earlier_commits_are_not_counted(tmp_path: Path) -> None:  # OUT-AC9, task AC 2
    segment(tmp_path, "T-1", 1)
    wrote(tmp_path, "T-1", "draft", "a.py")
    host = pr_host()
    host.reviews[(REPO, 1)] = [review(kind="bot"), review("approved")]
    host.review_comments[(REPO, 1)] = [comment(kind="bot"), comment(text=f"{MARKER}\n**Report:** done"),
                                       comment(text="a person's")]
    host.commits[(REPO, 1)] = [commit("0000000", ["a.py"]), commit(END, ["a.py"]),
                               commit("bbbbbbb2", ["a.py"], kind="bot"), commit("ccccccc3", ["a.py"])]
    read_one(tmp_path, host)
    assert rows(tmp_path)[0]["entry"] == {"state": "open", "reviews": {"approved": 1}, "comments": 1, "commits": 1,
                                          "files": 1}
