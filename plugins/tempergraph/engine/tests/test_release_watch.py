"""The post-release comparison of a merged proposal and the regression record (PRP-B9, PRP-B29; PRP-AC7, PRP-AC12,
PRP-AC13; task i9 AC 3, AC 4). PRP-AC7 lists the post-release watch (PRP-B9) among the proposal spec's fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.executors.standins import standin
from tempergraph.improve import child, filing, measure, release
from tempergraph.improve import proposals as prp
from tempergraph.improve.codehost import MemoryCodeHost

from .conftest import DOCS
from .test_pr_state import hand, pull, ticket_of
from .test_run import registry

MERGE = datetime(2026, 11, 10, tzinfo=UTC)
MERGED_AT = "2026-11-10T00:00:00Z"
PR = "https://example.test/acme/notes/pull/1"
MINE = ["https://example.test/acme/notes/issues/12", "https://example.test/acme/notes/issues/19"]
OTHER = "https://example.test/other/repo/issues/3"
BASE, NEW = "1.0.0", "1.1.0"


def at(days: float) -> str:
    return (MERGE + timedelta(days=days)).isoformat()


class Runs:
    """Recorded runs as the ledger and the run logs hold them."""

    def __init__(self, root: Path) -> None:
        self.root, self.n = root, 0

    def add(self, days: float, version: str = BASE, cost: float = 1.0, *, origin: str = "cli", exit_code: int = 0,
            gates: tuple[str, ...] = ("PROCEED",), outcome: str | None = "met", dry_run: bool = False,
            workflow: str = "demo") -> str:
        self.n += 1
        task = f"R-{self.n}"
        tid = f"{workflow}/{task}"
        row: dict[str, Any] = {"kind": "run_segment", "ts": at(days), "workflow": workflow, "workflow_version": version,
                               "thread_id": tid, "origin": origin, "exit_code": exit_code,
                               "cost": {"reported": cost, "estimated_only": 0.0}}
        if outcome:
            row["outcome"] = {"verdict": outcome}
        with (self.root / "ledger.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        folder = self.root / "runs" / workflow / task
        folder.mkdir(parents=True)
        recs = [{"kind": "run_started", "origin": origin, **({"dry_run": True} if dry_run else {})},
                *({"kind": "gate", "token": t} for t in gates)]
        (folder / "run.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        return tid

    def window(self, days: range, version: str, cost: float, **kw: Any) -> None:
        for d in days:
            self.add(d, version, cost, **kw)


def merged(root: Path, pid: str = "p1", **extra: Any) -> dict[str, Any]:
    rec = {"schema_version": 1, "proposal_id": pid, "workflow": "demo", "base_version": BASE, "state": "merged",
           "pr_state": "merged", "merged_at": MERGED_AT, "pull_request": PR, "cluster": {"issues": [*MINE, OTHER]},
           **extra}
    prp.save(root, rec)
    return rec


def stored(root: Path, pid: str = "p1") -> dict[str, Any]:
    return prp.load_proposal(root, pid)


def ten_before(runs: Runs, cost: float = 1.0, **kw: Any) -> None:
    runs.window(range(-10, 0), BASE, cost, **kw)  # ten days, one run a day, the last a day before the merge


def issues_host(**kw: Any) -> MemoryCodeHost:
    host = MemoryCodeHost(**kw)
    for repo, n in (("acme/notes", 12), ("acme/notes", 19), ("other/repo", 3)):
        host.issues.append({"repo": repo, "number": n, "state": "closed", "body": "", "url": f"https://example.test/{repo}/issues/{n}"})
    return host


def due(root: Path, host: MemoryCodeHost | None = None) -> list[dict[str, Any]]:
    return release.compare_due(root, "demo", host or issues_host(), filing.Outbox.at(root))


# -- the figures of a window (row 3.3) -------------------------------------------------------------------------

def test_window_figures_and_figures_agree(tmp_path: Path) -> None:  # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    runs.window(range(1, 4), BASE, 2.0)
    segs = [r for r in measure._rows(tmp_path / "ledger.jsonl")]
    assert measure.window_figures(tmp_path, "demo", BASE, segs) == measure.figures(tmp_path, "demo", BASE)
    assert measure.figures(tmp_path, "demo", BASE)["cost_per_run"] == 2.0
    assert measure.figures(tmp_path, "demo", NEW)["runs"] == 0


def test_a_missing_or_unchanged_figure_never_makes_a_measure_worse(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    runs.add(-1, BASE, 0.0, gates=(), outcome=None)  # a cost of zero, no gate, no outcome before
    runs.add(1, NEW, 9.0, gates=("BLOCK",), outcome="unmet")
    rows = measure._rows(tmp_path / "ledger.jsonl")
    cmp = measure.compare_windows(tmp_path, "demo", rows[:1], rows[1:])
    assert cmp["worse"] == [] and cmp["regressed"] is False  # nothing before to compare with
    assert cmp["before"]["gate_pass_rate"] is None and cmp["after"]["gate_pass_rate"] == 0.0


# -- the comparison (row 3.4) ----------------------------------------------------------------------------------

def test_a_cost_rise_of_30_percent_over_10_exits_records_regressed_after_release(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(1, 11), NEW, 1.3)
    merged(tmp_path)
    (out,) = due(tmp_path)
    rec = stored(tmp_path)
    assert out == {"proposal_id": "p1", "result": "regressed"} and "held_after_release" not in rec
    reg = rec["regressed_after_release"]
    assert reg["before"]["cost_per_run"] == 1.0 and reg["after"]["cost_per_run"] == 1.3
    assert reg["before"]["runs"] == 10 and reg["after"]["runs"] == 10 and reg["worse"] == ["cost_per_run"]
    assert reg["at"]
    assert rec["state"] == "merged"


def test_a_gate_pass_rate_fall_of_7_points_records_regressed_after_release(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0, gates=("PROCEED",) * 10)
    for d in range(1, 11):  # 7 of the 100 gates after the merge are not first-try passes
        runs.add(d, NEW, 1.0, gates=("PROCEED",) * 10 if d > 7 else ("PROCEED",) * 9 + ("BLOCK",))
    merged(tmp_path)
    assert [o["result"] for o in due(tmp_path)] == ["regressed"]
    reg = stored(tmp_path)["regressed_after_release"]
    assert reg["before"]["gate_pass_rate"] == 1.0 and reg["after"]["gate_pass_rate"] == 0.93
    assert reg["worse"] == ["gate_pass_rate"]


def test_a_met_share_fall_records_regressed_after_release(tmp_path: Path) -> None:  # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs)
    for d in range(1, 11):
        runs.add(d, NEW, 1.0, outcome="met" if d > 2 else "unmet")  # 8 of 10 met, 20 points down
    merged(tmp_path)
    assert [o["result"] for o in due(tmp_path)] == ["regressed"]
    assert stored(tmp_path)["regressed_after_release"]["worse"] == ["outcome_met_share"]


def test_a_cost_rise_of_5_percent_with_the_rest_held_records_held_after_release(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(1, 11), NEW, 1.05)
    merged(tmp_path)
    assert due(tmp_path) == [{"proposal_id": "p1", "result": "held"}]
    rec = stored(tmp_path)
    assert "regressed_after_release" not in rec
    held = rec["held_after_release"]
    assert held["before"]["cost_per_run"] == 1.0 and held["after"]["cost_per_run"] == 1.05 and held["at"]


def test_9_exits_after_the_merge_compare_and_record_nothing(tmp_path: Path) -> None:  # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs)
    runs.window(range(1, 10), NEW, 3.0)
    merged(tmp_path)
    assert due(tmp_path) == []
    rec = stored(tmp_path)
    assert "regressed_after_release" not in rec and "held_after_release" not in rec


def test_10_exits_of_which_4_are_trial_runs_compare_nothing(tmp_path: Path) -> None:  # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs)
    runs.window(range(1, 7), NEW, 3.0)
    runs.window(range(7, 11), NEW, 3.0, origin="trial")
    merged(tmp_path)
    assert due(tmp_path) == []
    assert "regressed_after_release" not in stored(tmp_path)


def test_dry_runs_child_records_and_other_exit_codes_are_not_real_exits(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs)
    runs.window(range(1, 4), NEW, 3.0, dry_run=True)
    runs.window(range(4, 7), NEW, 3.0, origin="subworkflow:parent")
    runs.window(range(7, 10), NEW, 3.0, origin="scenario")
    runs.window(range(10, 13), NEW, 3.0, exit_code=1)  # a pause, not a final exit
    runs.add(13, NEW, 3.0, workflow="other-wf")
    assert len(release.real_exits(tmp_path, "demo")) == 10  # the ten before the merge only
    merged(tmp_path)
    assert due(tmp_path) == []


def test_exit_codes_4_and_5_are_final_exits(tmp_path: Path) -> None:  # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    for code in (0, 4, 5):
        runs.add(1, NEW, 1.0, exit_code=code)
    assert len(release.real_exits(tmp_path, "demo")) == 3


def test_a_merge_seen_late_compares_the_first_10_exits_after_it(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(1, 11), NEW, 1.05)
    runs.window(range(11, 13), NEW, 40.0)  # the 11th and 12th would make it a regression
    merged(tmp_path)
    assert [o["result"] for o in due(tmp_path)] == ["held"]
    assert stored(tmp_path)["held_after_release"]["after"]["cost_per_run"] == 1.05


def test_the_exits_before_the_merge_are_the_base_version_only(tmp_path: Path) -> None:  # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(-20, -10), "0.9.0", 50.0)  # an older version: not the base
    runs.window(range(1, 11), NEW, 1.0)
    merged(tmp_path)
    assert [o["result"] for o in due(tmp_path)] == ["held"]
    assert stored(tmp_path)["held_after_release"]["before"]["runs"] == 10


class Counting(MemoryCodeHost):
    reopened = 0

    def reopen(self, repo: str, number: int) -> None:
        type(self).reopened += 1
        super().reopen(repo, number)


def test_a_compared_proposal_is_not_compared_again_and_the_host_is_not_asked_again(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    Counting.reopened = 0
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(1, 11), NEW, 1.3)
    merged(tmp_path)
    host = Counting()
    host.issues = issues_host().issues
    assert [o["result"] for o in due(tmp_path, host)] == ["regressed"] and Counting.reopened == 2
    first = stored(tmp_path)["regressed_after_release"]
    runs.add(11, NEW, 99.0)  # the 11th final exit
    assert due(tmp_path, host) == [] and Counting.reopened == 2
    assert stored(tmp_path)["regressed_after_release"] == first
    merged(tmp_path, "p2", held_after_release={"at": "x"})
    assert due(tmp_path, host) == [] and Counting.reopened == 2  # a proposal holding either record is skipped


def test_only_merged_proposals_with_a_merge_time_are_compared(tmp_path: Path) -> None:  # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs)
    runs.window(range(1, 11), NEW, 3.0)
    merged(tmp_path, "opened", state="opened")
    merged(tmp_path, "no-time", merged_at=None)
    merged(tmp_path, "other", workflow="other-wf")
    assert due(tmp_path) == []


# -- the reopen (rows 3.4, 3.5) ----------------------------------------------------------------------------------

def test_a_regression_reopens_the_cluster_issues_of_the_pull_requests_repository(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC13 (PRP-B29), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(1, 11), NEW, 1.3)
    merged(tmp_path)
    host = issues_host()
    due(tmp_path, host)
    state = {(i["repo"], i["number"]): i["state"] for i in host.issues}
    assert state == {("acme/notes", 12): "open", ("acme/notes", 19): "open", ("other/repo", 3): "closed"}


def test_a_held_proposal_reopens_nothing(tmp_path: Path) -> None:  # PRP-AC7, PRP-AC13 (PRP-B29), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(1, 11), NEW, 1.0)
    merged(tmp_path)
    host = issues_host()
    due(tmp_path, host)
    assert {i["state"] for i in host.issues} == {"closed"}


def test_an_unreachable_host_keeps_the_record_and_queues_the_reopen(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC13 (PRP-B29), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(1, 11), NEW, 1.3)
    merged(tmp_path)
    assert [o["result"] for o in due(tmp_path, issues_host(down=True))] == ["regressed"]
    assert "regressed_after_release" in stored(tmp_path)
    queued = [json.loads(ln) for ln in (tmp_path / "filing-outbox.jsonl").read_text().splitlines()]
    assert all(q.get("queued_at") for q in queued)  # ISS-AC17: the queue time travels with the entry
    assert [{k: v for k, v in q.items() if k != "queued_at"} for q in queued] == [
        {"op": "reopen", "repo": "acme/notes", "number": 12}, {"op": "reopen", "repo": "acme/notes", "number": 19}]
    up = issues_host()  # the next filing delivers them once
    results = filing.file([], up, filing.Outbox.at(tmp_path))
    assert [r["op"] for r in results] == ["redelivered", "redelivered"]
    assert {(i["number"], i["state"]) for i in up.issues if i["repo"] == "acme/notes"} == {(12, "open"), (19, "open")}
    assert not (tmp_path / "filing-outbox.jsonl").exists()
    assert filing.file([], up, filing.Outbox.at(tmp_path)) == []


def test_a_reopen_the_host_still_cannot_take_stays_in_the_outbox(tmp_path: Path) -> None:  # PRP-AC7, PRP-AC13 (PRP-B29), task AC 3
    outbox = filing.Outbox.at(tmp_path)
    outbox.add({"op": "reopen", "repo": "acme/notes", "number": 12})
    assert filing.file([], issues_host(down=True), outbox) == []
    assert len(outbox.take()) == 1


# -- the ticket (row 3.6) ------------------------------------------------------------------------------------------

def test_a_watch_only_ticket_moves_the_proposal_and_compares_it_in_the_same_ticket(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC10 (PRP-B27), PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(1, 11), NEW, 1.3)
    prp.save(tmp_path, {"schema_version": 1, "proposal_id": "p1", "workflow": "demo", "base_version": BASE,
                        "state": "opened", "pr_state": "open", "pull_request": PR, "cluster": {"issues": [*MINE, OTHER]}})
    t = ticket_of(hand(tmp_path))
    assert t["watch_only"] is True
    host = issues_host()
    host.pulls.extend(pull(MemoryCodeHost(), 1, "merged", merged_at=MERGED_AT).pulls)
    ex = standin("claude")
    out = child.process(t, registry(ex), host)
    rec = stored(tmp_path)
    assert rec["state"] == "merged" and rec["merged_at"] == MERGED_AT and "regressed_after_release" in rec
    assert out["results"] == [] and not ex.calls
    assert {(i["number"], i["state"]) for i in host.issues if i["repo"] == "acme/notes"} == {(12, "open"), (19, "open")}


def test_a_merged_proposal_is_compared_by_a_later_watch_only_ticket(tmp_path: Path) -> None:
    # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(1, 11), NEW, 1.0)
    merged(tmp_path)
    t = ticket_of(hand(tmp_path))
    assert t["watch_only"] is True
    child.process(t, registry(standin("claude")), MemoryCodeHost(down=True))  # the host is down: still compared
    assert "held_after_release" in stored(tmp_path)
    assert hand(tmp_path) is None  # and now there is nothing left to watch


def test_at_autonomy_record_nothing_is_compared(tmp_path: Path) -> None:  # PRP-AC7, PRP-AC12 (PRP-B9), task AC 3
    runs = Runs(tmp_path)
    ten_before(runs, 1.0)
    runs.window(range(1, 11), NEW, 1.0)
    merged(tmp_path)
    t = {**ticket_of(hand(tmp_path)), "autonomy": "record"}
    child.process(t, registry(standin("claude")), MemoryCodeHost())
    assert "held_after_release" not in stored(tmp_path)


# -- the spec (row 3.2) ----------------------------------------------------------------------------------------

def test_spec_40_has_no_not_built_yet_line() -> None:  # task AC 4
    spec = (DOCS / "specs" / "improvement-proposals.spec.md").read_text(encoding="utf-8")
    assert not [ln for ln in spec.splitlines() if ln.startswith("- Not built yet")]
    assert "waits on the merge being seen" not in spec
    assert "PRP-B9" in spec and "regressed_after_release" in spec


@pytest.mark.parametrize("name", ["regressed_after_release", "held_after_release"])
def test_the_release_records_are_named_in_spec_40(name: str) -> None:  # task AC 4
    assert name in (DOCS / "specs" / "improvement-proposals.spec.md").read_text(encoding="utf-8")
