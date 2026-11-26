"""The loop reads a recorded pull request and appends a `later[]` entry of counts and kinds (OUT-B23 to OUT-B25; task AC 2)."""

from __future__ import annotations

import dataclasses
import json
import subprocess
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


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def ensure_repo(repo: Path) -> None:
    """A real repository with one base commit in `repo`, made once."""
    if (repo / ".git").exists():
        return
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "base")


def state(tmp_path: Path) -> Path:
    """A real repository with one base commit in `tmp_path`; returns its state root."""
    ensure_repo(tmp_path)
    root = tmp_path / ".tempergraph"
    root.mkdir(exist_ok=True)
    return root


def head(root: Path) -> str:
    """The commit the repository of the state root is at: the end commit a run's pull request records."""
    return _git(root.parent, "rev-parse", "HEAD")


def segment(root: Path, task: str, number: int, commit: str = "") -> None:
    Ledger(path=root / "ledger.jsonl").append(
        {"kind": "run_segment", "thread_id": f"demo/{task}", "workflow": "demo", "exit_code": 0,
         "pull_request": {"host": "example.test", "repo": REPO, "number": number, "commit": commit or head(root)}})


def later_row(root: Path, task: str, state: str) -> None:
    Ledger(path=root / "ledger.jsonl").append(
        {"kind": "outcome_later", "thread_id": f"demo/{task}", "workflow": "demo",
         "entry": {"state": state, "reviews": {}, "comments": 0, "commits": 0, "files": 0}})


def wrote(root: Path, task: str, unit: str, *paths: str) -> None:
    """The unit's session wrote `paths` and committed them on top of the base: the commit is real, and the run log
    holds the run's `workspace` record (`base_commit`) and the session's `agent_run` record (`wrote_paths`)."""
    repo = root.parent
    ensure_repo(repo)
    base = _git(repo, "rev-list", "--max-parents=0", "HEAD").splitlines()[0]
    for rel in paths:
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text((f.read_text() if f.exists() else "") + f"{task} {unit}\n")
    if paths:
        _git(repo, "add", "--", *paths)
        _git(repo, "commit", "-q", "-m", f"{unit} writes", "--no-verify")
    p = root / "runs" / "demo" / task / "run.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists() or '"kind": "workspace"' not in p.read_text()
    with p.open("a", encoding="utf-8") as fh:
        if fresh:
            fh.write(json.dumps({"kind": "workspace", "action": "prepared", "base_commit": base}) + "\n")
        fh.write(json.dumps({"kind": "agent_run", "session_kind": "step", "unit": unit,
                             "session_key": f"{unit}.1.step", "wrote_paths": list(paths)}) + "\n")


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
    root = state(tmp_path)
    assert hand(root) is None  # nothing recorded, nothing to watch
    segment(root, "T-1", 1)
    t = ticket_of(hand(root))
    assert t["watch_only"] is True and t["autonomy"] == "file"
    later_row(root, "T-1", "merged")
    assert hand(root) is None  # found merged: nothing left to read


def test_only_the_pull_request_not_found_merged_or_closed_is_read(tmp_path: Path) -> None:  # OUT-AC7, task AC 2
    root = state(tmp_path)
    segment(root, "T-1", 1)
    segment(root, "T-2", 2)
    later_row(root, "T-2", "merged")
    host = pr_host()
    child.process(ticket_of(hand(root)), registry(standin("claude")), host)
    assert host.asked == [1]


@pytest.mark.parametrize("change", [{"autonomy": "record"}, {"dry_run": True}])
def test_at_autonomy_record_and_in_a_dry_run_the_host_is_not_asked(tmp_path: Path, change: dict[str, Any]) -> None:
    # OUT-AC7, task AC 2
    root = state(tmp_path)
    segment(root, "T-1", 1)
    t = {**ticket_of(hand(root)), **change}
    host = pr_host()
    child.process(t, registry(standin("claude")), host)
    assert host.asked == [] and rows(root) == []


def test_a_host_that_is_down_appends_nothing(tmp_path: Path) -> None:  # OUT-AC7, task AC 2
    root = state(tmp_path)
    segment(root, "T-1", 1)
    out = child.process(ticket_of(hand(root)), registry(standin("claude")), pr_host(down=True))
    assert rows(root) == [] and out["results"] == []


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


def test_a_read_appends_one_entry_of_counts_and_no_text(tmp_path: Path) -> None:  # OUT-AC8, OUT-AC12, task AC 2
    root = state(tmp_path)
    wrote(root, "T-1", "draft", "a.py")
    segment(root, "T-1", 1)
    host = pr_host()
    host.reviews[(REPO, 1)] = [review()]
    host.review_comments[(REPO, 1)] = [comment(), comment(text="SECOND")]
    host.commits[(REPO, 1)] = [commit(head(root), ["old.py"]), commit("bbbbbbb2", ["a.py", "other.py"])]
    read_one(root, host)
    got = rows(root)
    assert len(got) == 1
    row = got[0]
    assert (row["thread_id"], row["workflow"]) == ("demo/T-1", "demo")
    assert row["entry"] == {"state": "open", "reviews": {"changes_requested": 1}, "comments": 2, "commits": 1,
                            "files": 1}
    assert "REVIEW-TEXT" not in json.dumps(row) and "COMMENT-TEXT" not in json.dumps(row)
    assert "REVIEW-TEXT" not in (root / "ledger.jsonl").read_text()
    evidence = (root / "runs" / "demo" / "T-1" / "evidence" / "pull_request.jsonl").read_text()
    assert "REVIEW-TEXT" in evidence and "COMMENT-TEXT" in evidence
    read_one(root, host)  # a second read of an unchanged pull request
    assert len(rows(root)) == 1


def test_a_changed_pull_request_appends_a_new_entry(tmp_path: Path) -> None:  # OUT-AC8, task AC 2
    root = state(tmp_path)
    segment(root, "T-1", 1)
    host = pr_host()
    read_one(root, host)
    host.reviews[(REPO, 1)] = [review("approved")]
    read_one(root, host)
    assert [r["entry"]["reviews"] for r in rows(root)] == [{}, {"approved": 1}]


# -- OUT-AC9: only a person's work counts -------------------------------------------------------------------------

def test_bots_the_agent_marker_and_earlier_commits_are_not_counted(tmp_path: Path) -> None:  # OUT-AC9, OUT-AC12, task AC 2
    root = state(tmp_path)
    wrote(root, "T-1", "draft", "a.py")
    segment(root, "T-1", 1)
    host = pr_host()
    host.reviews[(REPO, 1)] = [review(kind="bot"), review("approved"),
                               review("changes_requested", kind="other", text="OTHER-REVIEW")]
    host.review_comments[(REPO, 1)] = [comment(kind="bot"), comment(text=f"{MARKER}\n**Report:** done"),
                                       comment(text="a person's"), comment(kind="other", text="OTHER-COMMENT")]
    host.commits[(REPO, 1)] = [commit("0000000", ["a.py"]), commit(head(root), ["a.py"]),
                               commit("bbbbbbb2", ["a.py"], kind="bot"), commit("ccccccc3", ["a.py"]),
                               commit("ddddddd4", ["a.py"], kind="other")]
    read_one(root, host)
    assert rows(root)[0]["entry"] == {"state": "open", "reviews": {"approved": 1}, "comments": 1, "commits": 1,
                                      "files": 1}
    evidence = (root / "runs" / "demo" / "T-1" / "evidence" / "pull_request.jsonl").read_text()
    assert "OTHER-REVIEW" not in evidence and "OTHER-COMMENT" not in evidence


def test_the_read_asks_for_the_files_of_the_commits_after_the_end_commit_only(tmp_path: Path) -> None:
    # OUT-AC11, task AC 4
    root = state(tmp_path)
    wrote(root, "T-1", "draft", "a.py")
    segment(root, "T-1", 1)
    end = head(root)
    host = pr_host()
    host.commits[(REPO, 1)] = [commit("0000000", ["a.py"]), commit(end, ["a.py"]), commit("bbbbbbb2", ["a.py"]),
                               commit("ccccccc3", ["x.py"])]
    read_one(root, host)
    assert host.files_asked == ["bbbbbbb2", "ccccccc3"]


def test_read_returns_a_result_for_each_pull_request_it_read_appended_or_not(tmp_path: Path) -> None:
    # OUT-AC13, task AC 3
    from tempergraph.improve import pr_later

    root = state(tmp_path)
    wrote(root, "T-1", "draft", "a.py")
    segment(root, "T-1", 1)
    host = pr_host()
    host.reviews[(REPO, 1)] = [review()]
    host.commits[(REPO, 1)] = [commit(head(root), []), commit("bbbbbbb2", ["a.py"])]
    (first,) = pr_later.read(root, "demo", host)
    assert first["appended"] is True and first["thread_id"] == "demo/T-1" and first["changed"] == ["a.py"]
    (second,) = pr_later.read(root, "demo", host)
    assert second["appended"] is False
    assert second["entry"] == first["entry"] and second["changed"] == first["changed"]
    assert len(rows(root)) == 1  # no row when the entries are equal
    host.reviews[(REPO, 1)] = [review(), review("approved")]
    (third,) = pr_later.read(root, "demo", host)
    assert third["appended"] is True and len(rows(root)) == 2


def test_no_files_are_asked_for_without_a_recorded_end_commit_or_one_the_pull_request_lacks(tmp_path: Path) -> None:
    # OUT-AC11, task AC 4
    root = state(tmp_path)
    segment(root, "T-1", 1, commit="f" * 40)  # not among the commits of the pull request
    ledger = Ledger(path=root / "ledger.jsonl")
    ledger.append({"kind": "run_segment", "thread_id": "demo/T-2", "workflow": "demo", "exit_code": 0,
                   "pull_request": {"host": "example.test", "repo": REPO, "number": 2}})  # no end commit
    host = pr_host()
    for n in (1, 2):
        host.commits[(REPO, n)] = [commit("aaaaaaa1", ["a.py"]), commit("bbbbbbb2", ["a.py"])]
    read_one(root, host)
    assert host.files_asked == []
    assert all(r["entry"]["files"] == 0 and r["entry"]["commits"] == 0 for r in rows(root))
