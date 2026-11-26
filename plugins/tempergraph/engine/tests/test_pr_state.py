"""A proposal's pull request state is read from the code host, and the loop reaches the read at every final exit
(PRP-B26, PRP-B27, PRP-B28; PRP-AC10, PRP-AC11; task i9 AC 1, AC 2)."""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.improve import child, loop_report
from tempergraph.improve import proposals as prp
from tempergraph.improve.codehost import CodeHostError, GhCodeHost, MemoryCodeHost
from tempergraph.package.loader import load
from tempergraph.store.layout import state_root_path

from .conftest import _git
from .fixtures.packages import minimal_package
from .fixtures.workflows import two_step
from .test_proposals import CLUSTER, PROMPT, proposer_ex
from .test_run import DRAFT, REVIEW, go, judge, registry

PR = "https://example.test/acme/notes/pull/1"
MERGED_AT = "2026-11-20T10:00:00Z"


def pull(host: MemoryCodeHost, number: int = 1, state: str = "open", **extra: Any) -> MemoryCodeHost:
    host.pulls.append({"repo": "acme/notes", "number": number, "state": state, "draft": True, **extra})
    return host


def opened(root: Path, pid: str = "p1", number: int = 1, workflow: str = "demo", **extra: Any) -> dict[str, Any]:
    rec = {"schema_version": 1, "proposal_id": pid, "workflow": workflow, "base_version": "1.0.0",
           "state": "opened", "pr_state": "unknown", "cluster": {"issues": []},
           "pull_request": f"https://example.test/acme/notes/pull/{number}", **extra}
    prp.save(root, rec)
    return rec


def stored(root: Path, pid: str = "p1") -> dict[str, Any]:
    return prp.load_proposal(root, pid)


# -- the code host clients (row 1.2) ---------------------------------------------------------------------------

def test_memory_host_answers_open_merged_and_closed() -> None:  # PRP-AC10 (PRP-B26), task AC 1
    host = MemoryCodeHost()
    pull(host, 1, "open")
    pull(host, 2, "merged", merged_at=MERGED_AT)
    pull(host, 3, "closed")
    assert host.pull_state("acme/notes", 1) == {"state": "open", "merged_at": None}
    assert host.pull_state("acme/notes", 2) == {"state": "merged", "merged_at": MERGED_AT}
    assert host.pull_state("acme/notes", 3) == {"state": "closed", "merged_at": None}


def test_memory_host_cannot_be_read_when_down_or_unknown() -> None:  # PRP-AC11 (PRP-B28), task AC 1
    host = pull(MemoryCodeHost(), 1, "open")
    with pytest.raises(CodeHostError):
        host.pull_state("acme/notes", 9)
    host.down = True
    with pytest.raises(CodeHostError):
        host.pull_state("acme/notes", 1)
    with pytest.raises(CodeHostError):
        host.reopen("acme/notes", 1)


def test_gh_host_raises_when_gh_is_missing_or_the_answer_has_no_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC11 (PRP-B28), task AC 1
    monkeypatch.setattr("tempergraph.improve.codehost.shutil.which", lambda name: None)
    with pytest.raises(CodeHostError):
        GhCodeHost().pull_state("acme/notes", 1)
    monkeypatch.undo()
    monkeypatch.setattr(GhCodeHost, "_gh", lambda self, args, payload=None: ["not", "a", "mapping"])
    with pytest.raises(CodeHostError):
        GhCodeHost().pull_state("acme/notes", 1)
    with pytest.raises(CodeHostError):
        GhCodeHost().pull_state("not a repo", 1)


def test_gh_host_reads_one_pull_request_and_maps_its_state(monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC10 (PRP-B26, PRP-B27), task AC 1
    seen: list[list[str]] = []
    answers = iter([{"state": "open", "merged": False, "merged_at": None},
                    {"state": "closed", "merged": True, "merged_at": MERGED_AT},
                    {"state": "closed", "merged": False, "merged_at": None}])

    def fake(self: GhCodeHost, args: list[str], payload: dict[str, Any] | None = None) -> Any:
        seen.append(args)
        assert payload is None
        return next(answers)

    monkeypatch.setattr(GhCodeHost, "_gh", fake)
    host = GhCodeHost()
    assert host.pull_state("acme/notes", 4) == {"state": "open", "merged_at": None}
    assert host.pull_state("acme/notes", 4) == {"state": "merged", "merged_at": MERGED_AT}
    assert host.pull_state("acme/notes", 4) == {"state": "closed", "merged_at": None}
    assert seen == [["api", "repos/acme/notes/pulls/4"]] * 3  # one GET each, never a write


# -- the proposal record (row 1.3) -----------------------------------------------------------------------------

def test_a_proposal_just_opened_shows_pr_state_unknown(repo: Path) -> None:  # PRP-AC10 (PRP-B26), task AC 1
    git_pkg = minimal_package(repo / "workflows")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "package")
    root = state_root_path(repo)
    spec = load(git_pkg)
    rec = prp.propose(root, spec, CLUSTER, proposer_ex({"prompts/draft.md": PROMPT}))
    out = prp.open_pr(root, spec, rec["proposal_id"], MemoryCodeHost(), push=False)
    assert out["state"] == "opened" and out["pr_state"] == "unknown"
    assert prp.load_proposal(root, rec["proposal_id"])["pr_state"] == "unknown"


def test_pull_ref_reads_the_loops_own_pull_request_urls() -> None:  # PRP-B26, task AC 1
    # PRP-AC15: the code host comes with the repository and the number
    assert prp.pull_ref(PR) == ("example.test", "acme/notes", 1)
    assert prp.pull_ref("http://example.test/acme/notes/pull/7") == ("example.test", "acme/notes", 7)
    assert prp.pull_ref("https://example.test/acme/notes/issues/1") is None
    assert prp.pull_ref("https://example.test/acme/notes/pull/1/files") is None
    assert prp.pull_ref("nonsense") is None
    assert prp.pull_ref(None) is None


def test_an_open_pull_request_keeps_the_proposal_opened_with_pr_state_open(tmp_path: Path) -> None:
    # PRP-AC10 (PRP-B26), task AC 2
    opened(tmp_path)
    host = pull(MemoryCodeHost(), 1, "open")
    assert prp.sync_pr_state(tmp_path, "demo", host) == [("p1", "open")]
    rec = stored(tmp_path)
    assert rec["state"] == "opened" and rec["pr_state"] == "open" and "merged_at" not in rec


def test_a_pull_request_closed_without_a_merge_leaves_the_proposal_opened(tmp_path: Path) -> None:
    # PRP-AC10 (PRP-B26), task AC 2
    opened(tmp_path)
    prp.sync_pr_state(tmp_path, "demo", pull(MemoryCodeHost(), 1, "closed"))
    rec = stored(tmp_path)
    assert rec["state"] == "opened" and rec["pr_state"] == "closed" and "merged_at" not in rec


def test_a_merged_pull_request_moves_the_proposal_to_merged_with_the_hosts_time(tmp_path: Path) -> None:
    # PRP-AC10 (PRP-B27), task AC 2
    opened(tmp_path)
    host = pull(MemoryCodeHost(), 1, "open")
    prp.sync_pr_state(tmp_path, "demo", host)
    host.pulls[0].update(state="merged", merged_at=MERGED_AT)  # a person merged it; the loop has no merge call
    assert prp.sync_pr_state(tmp_path, "demo", host) == [("p1", "merged")]
    rec = stored(tmp_path)
    assert rec["state"] == "merged" and rec["pr_state"] == "merged" and rec["merged_at"] == MERGED_AT


def test_an_unreachable_host_leaves_the_proposal_as_it_was(tmp_path: Path) -> None:  # PRP-AC11 (PRP-B28), task AC 2
    opened(tmp_path, "never", 1)
    opened(tmp_path, "read", 2, pr_state="open")
    host = pull(pull(MemoryCodeHost(), 1, "merged", merged_at=MERGED_AT), 2, "merged", merged_at=MERGED_AT)
    host.down = True
    assert prp.sync_pr_state(tmp_path, "demo", host) == []  # raises nothing
    never, read = stored(tmp_path, "never"), stored(tmp_path, "read")
    assert never["state"] == "opened" and never["pr_state"] == "unknown" and "merged_at" not in never
    assert read["state"] == "opened" and read["pr_state"] == "open" and "merged_at" not in read
    host.down = False  # the host back up: the next final exit moves both
    assert sorted(prp.sync_pr_state(tmp_path, "demo", host)) == [("never", "merged"), ("read", "merged")]
    assert stored(tmp_path, "never")["state"] == "merged" and stored(tmp_path, "read")["merged_at"] == MERGED_AT


def test_a_missing_gh_leaves_the_proposal_as_it_was(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC11 (PRP-B28), task AC 1
    opened(tmp_path)
    monkeypatch.setattr("tempergraph.improve.codehost.shutil.which", lambda name: None)
    assert prp.sync_pr_state(tmp_path, "demo", GhCodeHost()) == []
    rec = stored(tmp_path)
    assert rec["state"] == "opened" and rec["pr_state"] == "unknown" and "merged_at" not in rec


def test_only_opened_proposals_of_the_workflow_are_read(tmp_path: Path) -> None:  # PRP-B26, task AC 2
    opened(tmp_path, "other", 1, workflow="other-wf")
    for state in ("drafted", "shown_better", "merged", "closed", "refused"):
        opened(tmp_path, f"s-{state}", 1, state=state)
    host = pull(MemoryCodeHost(), 1, "merged", merged_at=MERGED_AT)
    assert prp.sync_pr_state(tmp_path, "demo", host) == []
    assert stored(tmp_path, "other")["state"] == "opened" and stored(tmp_path, "s-drafted")["state"] == "drafted"
    assert stored(tmp_path, "s-closed")["state"] == "closed"


def test_watching_is_true_for_opened_and_for_merged_without_a_release_record(tmp_path: Path) -> None:
    # PRP-B26, task AC 2
    assert prp.watching(tmp_path, "demo") is False
    opened(tmp_path, "a", state="drafted")
    assert prp.watching(tmp_path, "demo") is False
    opened(tmp_path, "b", state="merged")
    assert prp.watching(tmp_path, "demo") is True
    opened(tmp_path, "b", state="merged", held_after_release={"at": "x"})
    assert prp.watching(tmp_path, "demo") is False
    opened(tmp_path, "c", state="merged", regressed_after_release={"at": "x"})
    assert prp.watching(tmp_path, "demo") is False
    opened(tmp_path, "d")
    assert prp.watching(tmp_path, "demo") is True
    assert prp.watching(tmp_path, "other-wf") is False


# -- the loop reaches the read at every final exit (rows 2.2, 2.3) ----------------------------------------------

CLEAN = {"lenses": {"friction": False}, "fault_fingerprints": [], "outcome_fingerprints": [], "fingerprints": []}
QUIET = dataclasses.replace(two_step(), session_review="off")


@dataclasses.dataclass(kw_only=True)
class CountingHost(MemoryCodeHost):
    asked: int = 0

    def pull_state(self, repo: str, number: int) -> dict[str, Any]:
        self.asked += 1
        return super().pull_state(repo, number)


def hand(root: Path, summary: dict[str, Any] = CLEAN, **kw: Any) -> Path | None:
    kw.setdefault("dry_run", False)
    return child.hand_off(root, QUIET, "T-1", "demo/T-1", summary, judge_executor="claude", home=root / "home", **kw)


def ticket_of(path: Path | None) -> dict[str, Any]:
    assert path is not None
    return json.loads(path.read_text())


def test_a_clean_final_exit_with_an_opened_proposal_writes_a_watch_only_ticket(tmp_path: Path) -> None:
    # PRP-AC10 (PRP-B26), task AC 2
    opened(tmp_path)
    t = ticket_of(hand(tmp_path))
    assert t["watch_only"] is True and t["fingerprints"] == [] and t["autonomy"] == "file"


def test_a_ticket_with_a_fault_to_judge_is_not_watch_only(tmp_path: Path) -> None:  # PRP-B26, task AC 2
    opened(tmp_path)
    faulty = {"lenses": {"friction": True}, "fault_fingerprints": ["fp"], "outcome_fingerprints": [],
              "fingerprints": ["fp"]}
    assert ticket_of(hand(tmp_path, faulty))["watch_only"] is False


def test_no_ticket_for_a_clean_exit_with_nothing_to_watch_or_a_loop_that_must_not_read(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # PRP-AC10 (PRP-B26), task AC 2
    assert hand(tmp_path) is None  # no proposal at all
    opened(tmp_path, "m", state="merged", held_after_release={"at": "x"})
    assert hand(tmp_path) is None  # a merged proposal that holds a release record is no longer watched
    opened(tmp_path)
    assert hand(tmp_path, dry_run=True) is None
    assert hand(tmp_path, trial=True) is None
    assert hand(tmp_path, {k: v for k, v in CLEAN.items() if k != "lenses"}) is None  # not a final exit
    monkeypatch.setenv("TEMPERGRAPH_AUTONOMY", "record")
    assert hand(tmp_path) is None
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY")
    assert hand(tmp_path) is not None


def test_a_watch_only_ticket_moves_a_merged_proposal_and_spends_nothing(tmp_path: Path) -> None:
    # PRP-AC10 (PRP-B27), task AC 2
    opened(tmp_path)
    t = ticket_of(hand(tmp_path))
    ex = standin("claude")  # no scripted session: any session would fail the test
    out = child.process(t, registry(ex), pull(MemoryCodeHost(), 1, "merged", merged_at=MERGED_AT))
    rec = stored(tmp_path)
    assert rec["state"] == "merged" and rec["pr_state"] == "merged" and rec["merged_at"] == MERGED_AT
    assert out["results"] == [] and out["cost"] == {"reported": 0.0, "estimated_only": 0.0} and not ex.calls
    kinds = [json.loads(ln)["kind"] for ln in child.loop_log(tmp_path, "demo", "T-1").read_text().splitlines()]
    assert kinds == ["loop_started"]
    assert not (tmp_path / "ledger.jsonl").exists()  # no `loop` ledger row for a read


def test_a_watch_only_ticket_with_an_unreachable_host_leaves_the_proposal_opened(tmp_path: Path) -> None:
    # PRP-AC11 (PRP-B28), task AC 2
    opened(tmp_path)
    t = ticket_of(hand(tmp_path))
    out = child.process(t, registry(standin("claude")), pull(MemoryCodeHost(down=True), 1, "merged"))
    rec = stored(tmp_path)
    assert rec["state"] == "opened" and rec["pr_state"] == "unknown" and "merged_at" not in rec
    assert out["results"] == []


@pytest.mark.parametrize("change", [{"autonomy": "record"}, {"dry_run": True}])
def test_at_autonomy_record_and_in_a_dry_run_the_host_is_not_asked(tmp_path: Path, change: dict[str, Any]) -> None:
    # PRP-AC10 (PRP-B26), task AC 2
    opened(tmp_path)
    t = {**ticket_of(hand(tmp_path)), **change}
    host = pull(CountingHost(), 1, "merged", merged_at=MERGED_AT)
    child.process(t, registry(standin("claude")), host)
    assert host.asked == 0 and stored(tmp_path)["state"] == "opened"


def test_a_failing_read_is_noted_and_never_stops_the_ticket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC11 (PRP-B28), task AC 2
    opened(tmp_path)
    t = ticket_of(hand(tmp_path))

    def boom(*a: Any, **k: Any) -> None:
        raise RuntimeError("no")

    monkeypatch.setattr(prp, "sync_pr_state", boom)
    child.process(t, registry(standin("claude")), MemoryCodeHost())
    notes = [json.loads(ln) for ln in child.loop_log(tmp_path, "demo", "T-1").read_text().splitlines()]
    assert {"kind": "loop_skipped", "step": "pr_state", "reason": "error"}.items() <= notes[-1].items()


def no_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    real = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None if name == "gh" else real(name, *a, **k))


def test_a_run_ends_the_same_with_no_gh_signed_in(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PRP-AC11 (PRP-B28), task AC 1
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "inline")
    no_gh(monkeypatch)
    root = state_root_path(repo)
    opened(root, "p-merged")
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, spec=QUIET, task="G-1").exit_code is ExitCode.FINISHED
    rec = stored(root, "p-merged")
    assert rec["state"] == "opened" and rec["pr_state"] == "unknown" and "merged_at" not in rec
    kinds = [json.loads(ln)["kind"] for ln in child.loop_log(root, "demo", "G-1").read_text().splitlines()]
    assert kinds == ["loop_started"]  # the read was tried; nothing else of the loop's work changed


def test_the_funnel_counts_a_proposal_as_opened_once_it_is_merged_or_closed(tmp_path: Path) -> None:
    # IMD-B22, task AC 2
    for pid, state in (("a", "opened"), ("b", "merged"), ("c", "closed"), ("d", "drafted"), ("e", "refused")):
        opened(tmp_path, pid, state=state)
    (w,) = loop_report.report(tmp_path, ["demo"], None)["workflows"]
    assert w["funnel"]["proposals"] == 5 and w["funnel"]["opened"] == 3
    assert w["funnel"]["merged"] is None and w["funnel"]["held_after_release"] is None

