"""Fixture runs of the loop child for the bindings of a cause (BND-AC1 to BND-AC12), through `child.process`."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.executors.standins import standin
from tempergraph.improve import bindings, child, filing
from tempergraph.improve.codehost import LOOP_LABEL, MemoryCodeHost

from .test_loop_child import friction_ticket, judge_says, loop_rows
from .test_run import registry

REPO = "team/notes"
DAY = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
CANARY = "CANARY-bnd-5e1f"


def key_of(cause: str = "slow_step") -> str:
    return filing.cause_key({"side": "workflow", "workflow": "demo", "cause": cause})


def set_day(monkeypatch: pytest.MonkeyPatch, day: datetime) -> None:
    """The loop child's UTC day: its filing time and the time of its records move together."""
    monkeypatch.setattr(child, "filing_clock", lambda: day)
    monkeypatch.setattr(child, "now_iso", lambda: day.isoformat(timespec="milliseconds").replace("+00:00", "Z"))


def test_the_filing_clock_makes_two_utc_days(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # BND-AC6
    day1 = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    day2 = day1 + timedelta(days=1)
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude", judges=[judge_says(0.5) for _ in range(8)]))
    set_day(monkeypatch, day1)
    for n in (1, 2, 3):  # the third exit files the one issue
        child.process(friction_ticket(root, n), reg, host)
    assert len(host.issues) == 1
    ops = [[r["op"] for r in child.process(friction_ticket(root, n), reg, host)["results"]] for n in (4, 5)]
    assert ops == [["commented"], ["comment_capped"]]  # the bound of the day follows the set clock
    commented = [r for n in (4, 5) for r in loop_rows(root, f"F-{n}") if r["kind"] == "issue_commented"]
    assert [r["ts"][:10] for r in commented] == [day1.date().isoformat()]
    assert filing.comments_by_day(root, "demo", day1) == {("team/notes", 1): 1}
    set_day(monkeypatch, day2)  # the next UTC day starts at none
    out = child.process(friction_ticket(root, 6), reg, host)
    assert [r["op"] for r in out["results"]] == ["commented"]
    rows = [r for r in loop_rows(root, "F-6") if r["kind"] == "issue_commented"]
    assert rows[0]["ts"][:10] == day2.date().isoformat()
    assert filing.comments_by_day(root, "demo", day2) == {("team/notes", 1): 1}


def test_the_clock_of_the_retry_wait_keeps_its_meaning() -> None:
    assert isinstance(child.clock(), float)
    assert isinstance(child.filing_clock(), datetime) and child.filing_clock().tzinfo is not None


def iso(days_ago: float) -> str:
    return (DAY - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def seed(host: MemoryCodeHost, comments: list[tuple[str, str]], closed_days_ago: float | None = 10,
         reason: str = "duplicate", cause: str = "slow_step", people: int = 1) -> int:
    """People's issues with no loop label (numbers 1..people when the host is new) and the cause's loop issue, closed
    after `comments` (author kind, text) as a person or the host would. Returns the loop issue's number."""
    for k in range(people if not host.issues else 0):
        host.create(REPO, f"person's issue {k}", "body", ["bug"])
    host.create(REPO, f"[loop] demo: {cause}", f"{filing._cause_line(key_of(cause))}\nbody", [LOOP_LABEL])
    n = len(host.issues)
    for i, (kind, text) in enumerate(comments):
        host.add_comment(REPO, n, text, kind, iso(40 - i))
    if closed_days_ago is not None:
        host.close(REPO, n, reason, iso(closed_days_ago))
    return n


def run_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: Any, n: int = 1, *, root: Path | None = None,
            causes: tuple[str, ...] = ("slow_step",), day: datetime = DAY, ticket: dict[str, Any] | None = None
            ) -> tuple[list[dict[str, Any]], Path]:
    root = root or tmp_path / ".tempergraph"
    set_day(monkeypatch, day)
    reg = registry(standin("claude", judges=[judge_says(0.9) for _ in range(4)]))
    t = {**friction_ticket(root, n, causes), **(ticket or {})}
    results = child.process(t, reg, host)["results"]
    return [r for r in results if r["op"] != "bound"], root  # the `bound` records are read from the loop log


def rows_of(root: Path, n: int, op: str | None = None, kind: str = "loop_result") -> list[dict[str, Any]]:
    return [r for r in loop_rows(root, f"F-{n}") if r["kind"] == kind and (op is None or r.get("op") == op)]


@pytest.mark.parametrize("ago", [10, 31])
def test_a_duplicate_close_with_a_target_comments_there_and_opens_nothing(  # BND-AC1, BND-AC2, BND-AC8
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ago: int) -> None:
    host = MemoryCodeHost()
    src = seed(host, [("person", "Duplicate of #1")], closed_days_ago=ago)
    results, root = run_one(tmp_path, monkeypatch, host)
    assert [r["op"] for r in results] == ["commented"] and results[0]["number"] == 1
    assert len(host.issues) == 2 and [c["number"] for c in host.comments] == [1]
    (commented,) = rows_of(root, 1, kind="issue_commented")
    assert commented["number"] == 1 and commented["repo"] == REPO
    (bound,) = rows_of(root, 1, "bound")
    assert bound["cause_key"] == key_of() and bound["source"] == src and bound["target"] == 1
    assert not {"body", "text", "comment"} & set(bound)


def test_a_reopened_loop_issue_takes_the_comment_itself(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # BND-AC1
    host = MemoryCodeHost()
    src = seed(host, [("person", "duplicate of #1")], closed_days_ago=31)
    host.reopen(REPO, src)
    results, root = run_one(tmp_path, monkeypatch, host)
    assert [r["op"] for r in results] == ["commented"] and results[0]["number"] == src
    assert [c["number"] for c in host.comments] == [src] and not rows_of(root, 1, "bound")


def test_two_numbers_give_the_first_and_a_newer_person_comment_replaces_it(  # BND-AC2
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = MemoryCodeHost()
    seed(host, [("person", "duplicate of #1, and duplicate of #3")], people=3)
    results, _ = run_one(tmp_path, monkeypatch, host)
    assert results[0]["number"] == 1
    host.add_comment(REPO, 4, "it is duplicate of #3 after all", "person", iso(5))
    results, _ = run_one(tmp_path, monkeypatch, host, 2)
    assert [r["op"] for r in results] == ["commented"] and results[0]["number"] == 3


@pytest.mark.parametrize("kind", ["bot", "other"])
def test_a_comment_by_a_bot_or_an_other_binds_nothing(  # BND-AC2
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    host = MemoryCodeHost()
    seed(host, [(kind, "duplicate of #1")], closed_days_ago=10)
    results, root = run_one(tmp_path, monkeypatch, host)
    assert [r["op"] for r in results] == ["muted"] and not host.comments and not rows_of(root, 1, "bound")


@pytest.mark.parametrize("comment", ["duplicate of #2", "duplicate of #3", "duplicate of #99", "see the other one"])
def test_a_target_that_cannot_bind_leaves_iss_b3_unchanged(  # BND-AC3
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, comment: str) -> None:
    for ago, op in ((10, "muted"), (31, "filed")):
        host = MemoryCodeHost()
        seed(host, [("person", comment)], closed_days_ago=ago)  # issue 3 is a pull request
        host.create(REPO, "a pull request", "b", ["bug"])
        host.issues[-1]["pull_request"] = True
        results, root = run_one(tmp_path / f"{ago}", monkeypatch, host)
        assert [r["op"] for r in results] == [op] and not host.comments, (comment, ago)
        assert not rows_of(root, 1, "bound") and not rows_of(root, 1, "binding_unreadable")
        assert len(host.issues) == (4 if op == "filed" else 3)


def test_a_read_that_fails_twice_opens_nothing_and_leaves_binding_unreadable(  # BND-AC4
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, kw in (("comments", {"fail_comments": 2}), ("target", {"fail_issue": 2})):
        host = MemoryCodeHost(**kw)
        seed(host, [("person", f"duplicate of #1 {CANARY}")], closed_days_ago=31)
        before = len(host.issues)
        results, root = run_one(tmp_path / name, monkeypatch, host)
        assert [r["op"] for r in results] == ["binding_unreadable"], name
        assert len(host.issues) == before and not host.comments, name
        (row,) = rows_of(root, 1, "binding_unreadable")
        assert row["cause_key"] == key_of() and CANARY not in json.dumps(row)
        assert not rows_of(root, 1, "bound")


def test_a_read_that_fails_once_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # BND-AC4
    host = MemoryCodeHost(fail_comments=1, fail_issue=1)
    seed(host, [("person", "duplicate of #1")], closed_days_ago=31)
    results, _ = run_one(tmp_path, monkeypatch, host)
    assert [r["op"] for r in results] == ["commented"] and [c["number"] for c in host.comments] == [1]


def test_a_failed_closed_read_still_opens_an_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # BND-AC4
    host = MemoryCodeHost(fail_closed=2)
    seed(host, [("person", "duplicate of #1")], closed_days_ago=10)
    results, _ = run_one(tmp_path, monkeypatch, host)
    assert [r["op"] for r in results] == ["filed"] and results[0]["note"] == "closed_search_failed"


class NoBindingReads(MemoryCodeHost):
    def issue_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        raise AssertionError("the comments were read")

    def issue(self, repo: str, number: int) -> dict[str, Any]:
        raise AssertionError("the target was read")


def test_a_dry_run_and_the_hold_at_record_read_nothing(  # BND-AC4
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = NoBindingReads()
    seed(host, [("person", "duplicate of #1")], closed_days_ago=31)
    for sub, extra in (("dry", {"dry_run": True}), ("record", {"autonomy": "record"})):
        results, _ = run_one(tmp_path / sub, monkeypatch, host, ticket=extra)
        assert [r["op"] for r in results] in (["would_file"], ["recorded"])
    assert not host.comments


def test_the_comment_on_a_target_begins_with_the_sentence(  # BND-AC5
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = MemoryCodeHost()
    src = seed(host, [("person", f"duplicate of #1 {CANARY}")], closed_days_ago=31)
    results, _ = run_one(tmp_path, monkeypatch, host, 1, causes=("slow_step",))
    assert [r["op"] for r in results] == ["commented"]
    (c,) = host.comments
    first, rest = c["body"].split("\n", 1)
    assert first == bindings.opening_sentence("demo", "slow_step", ["draft"], src)
    assert "improvement loop" in first and "`slow_step`" in first and "`demo`" in first and f"#{src}" in first
    assert "reopening" in first
    assert "**Seen again**" in rest and "## Environment" in rest and "## Evidence" in rest
    assert "duplicate of #" not in c["body"].lower() and CANARY not in c["body"]


def test_two_causes_bound_to_one_target_share_the_comment_of_the_day(  # BND-AC6
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = MemoryCodeHost()
    seed(host, [("person", "duplicate of #1")], closed_days_ago=31)
    seed(host, [("person", "duplicate of #1")], closed_days_ago=31, cause="other_step")
    first, root = run_one(tmp_path, monkeypatch, host, 1)
    second, _ = run_one(tmp_path, monkeypatch, host, 2, causes=("other_step",))
    assert [r["op"] for r in first] == ["commented"] and [r["op"] for r in second] == ["comment_capped"]
    assert len(host.comments) == 1
    (capped,) = rows_of(root, 2, "comment_capped")
    assert capped["number"] == 1 and not {"body", "text"} & set(capped)
    third, _ = run_one(tmp_path, monkeypatch, host, 3, causes=("other_step",), day=DAY + timedelta(days=1))
    assert [r["op"] for r in third] == ["commented"] and [c["number"] for c in host.comments] == [1, 1]


def test_two_causes_of_two_workflows_bound_to_one_target_share_the_comment_of_the_day(  # BND-AC6
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tempergraph.improve import record

    host = MemoryCodeHost()
    seed(host, [("person", "duplicate of #1")], closed_days_ago=31)  # the cause of workflow `demo`
    host.create(REPO, "[loop] other: slow_step", "x", [LOOP_LABEL])  # the cause of workflow `other`
    other_key = filing.cause_key({"side": "workflow", "workflow": "other", "cause": "slow_step"})
    host.issues[-1]["body"] = f"{filing._cause_line(other_key)}\nbody"
    host.add_comment(REPO, len(host.issues), "duplicate of #1", "person", iso(40))
    host.close(REPO, len(host.issues), "duplicate", iso(31))
    first, root = run_one(tmp_path, monkeypatch, host, 1)
    fp = record.fingerprint("workflow", "other", "slow_step", "draft")
    row = {"kind": "finding", "thread": "other/F-2", "workflow": "other", "unit": "draft", "cause": "slow_step",
           "class": "fault", "side": "workflow", "count": 1, "remedy": "r", "fingerprint": fp,
           "at": datetime.now(UTC).isoformat(timespec="seconds"), "request_digest": "r2", "machine": "m"}
    path = record.findings_path(root, "other", "F-2")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "thread": "other/F-2", "findings": [row]}))
    t = {**friction_ticket(root, 2), "thread": "other/F-2", "workflow": "other", "task_id": "F-2",
         "fingerprints": [fp]}
    reg = registry(standin("claude", judges=[judge_says(0.9) for _ in range(4)]))
    second = child.process(t, reg, host)["results"]
    assert [r["op"] for r in first] == ["commented"]
    assert [r["op"] for r in second if r["op"] != "bound"] == ["comment_capped"]
    assert [c["number"] for c in host.comments] == [1]  # one comment on the target in the UTC day, over both workflows


def test_a_target_closed_as_completed_opens_a_regression_issue(  # BND-AC7
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = MemoryCodeHost()
    seed(host, [("person", "duplicate of #1")], closed_days_ago=31)
    host.close(REPO, 1, "completed", iso(100))
    results, _ = run_one(tmp_path, monkeypatch, host)
    assert [r["op"] for r in results] == ["filed"] and not host.comments
    summary = host.issues[-1]["body"].split("## Summary\n", 1)[1].split("\n## ", 1)[0]
    assert "Possible regression of #1" in summary
    results, _ = run_one(tmp_path, monkeypatch, host, 2)
    assert [r["op"] for r in results] == ["commented"] and host.comments[0]["number"] == len(host.issues)


@pytest.mark.parametrize("reason", ["not_planned", "duplicate"])
def test_a_target_closed_not_planned_or_duplicate_mutes_from_its_close(  # BND-AC7
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    host = MemoryCodeHost()
    seed(host, [("person", "duplicate of #1")], closed_days_ago=60)
    host.create(REPO, "third", "b", ["bug"])
    host.add_comment(REPO, 1, "duplicate of #3", "person", iso(11))
    host.close(REPO, 1, reason, iso(10))
    host.fail_issue = 0
    results, root = run_one(tmp_path, monkeypatch, host)
    assert [r["op"] for r in results] == ["muted"] and results[0]["url"] == host.issues[0]["url"]
    assert not host.comments and len(host.issues) == 3
    host.close(REPO, 1, reason, iso(31))
    results, _ = run_one(tmp_path, monkeypatch, host, 2)
    assert [r["op"] for r in results] == ["filed"]
    assert "regression" not in host.issues[-1]["body"].lower()


@pytest.mark.parametrize("reason", ["", "stale"])
def test_a_target_closed_with_no_or_another_reason_opens_a_plain_issue(  # BND-AC7
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    host = MemoryCodeHost()
    seed(host, [("person", "duplicate of #1")], closed_days_ago=60)
    host.close(REPO, 1, reason, iso(5))
    results, _ = run_one(tmp_path, monkeypatch, host)
    assert [r["op"] for r in results] == ["filed"] and not host.comments
    assert "regression" not in host.issues[-1]["body"].lower()


def test_a_reopened_target_takes_the_comments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # BND-AC7
    host = MemoryCodeHost()
    seed(host, [("person", "duplicate of #1")], closed_days_ago=31)
    host.close(REPO, 1, "completed", iso(5))
    host.reopen(REPO, 1)
    results, _ = run_one(tmp_path, monkeypatch, host)
    assert [r["op"] for r in results] == ["commented"] and host.comments[0]["number"] == 1


def test_the_first_filing_writes_one_bound_record_and_the_record_file(  # BND-AC8
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = MemoryCodeHost()
    src = seed(host, [("person", f"duplicate of #1 {CANARY}")], closed_days_ago=31)
    _, root = run_one(tmp_path, monkeypatch, host)
    data = json.loads((root / "filing-bindings.json").read_text())
    assert list(data) == [REPO] and list(data[REPO]) == [key_of()]
    rec = data[REPO][key_of()]
    assert rec["source"] == src and rec["target"] == 1 and CANARY not in json.dumps(data)
    if os.name == "posix":
        assert (root / "filing-bindings.json").stat().st_mode & 0o777 == 0o600
    assert len(rows_of(root, 1, "bound")) == 1


class CountingHost(MemoryCodeHost):
    reads: int = 0

    def issue_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        self.reads += 1
        return super().issue_comments(repo, number)


def test_a_matching_record_saves_the_read_and_writes_no_second_bound_record(  # BND-AC8, BND-AC9
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = CountingHost()
    seed(host, [("person", "duplicate of #1")], closed_days_ago=31)
    run_one(tmp_path, monkeypatch, host, 1)
    assert host.reads == 1
    results, root = run_one(tmp_path, monkeypatch, host, 2, day=DAY + timedelta(days=1))
    assert [r["op"] for r in results] == ["commented"] and host.reads == 1
    assert not rows_of(root, 2, "bound")


def test_a_second_state_root_writes_the_same_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # BND-AC9
    host = MemoryCodeHost()
    seed(host, [("person", "duplicate of #1")], closed_days_ago=31)
    _, a = run_one(tmp_path / "a", monkeypatch, host, 1)
    results, b = run_one(tmp_path / "b", monkeypatch, host, 1, day=DAY + timedelta(days=1))
    assert results[0]["number"] == 1
    assert json.loads((a / "filing-bindings.json").read_text()) == json.loads((b / "filing-bindings.json").read_text())
    assert len(rows_of(b, 1, "bound")) == 1


def test_a_reclosed_source_or_a_newer_comment_replaces_the_target(  # BND-AC9
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = MemoryCodeHost()
    src = seed(host, [("person", "duplicate of #1")], closed_days_ago=31, people=2)
    day = DAY
    _, root = run_one(tmp_path, monkeypatch, host, 1, day=day)
    host.reopen(REPO, src)
    host.add_comment(REPO, src, "duplicate of #2", "person", iso(3))
    host.close(REPO, src, "duplicate", iso(2))
    results, _ = run_one(tmp_path, monkeypatch, host, 2, day=day + timedelta(days=1))
    assert results[0]["number"] == 2 and rows_of(root, 2, "bound")[0]["target"] == 2
    assert json.loads((root / "filing-bindings.json").read_text())[REPO][key_of()]["target"] == 2
    host.add_comment(REPO, src, "no, duplicate of #1", "person", iso(1))  # a new comment, same close
    results, _ = run_one(tmp_path, monkeypatch, host, 3, day=day + timedelta(days=2))
    assert results[0]["number"] == 1
    assert json.loads((root / "filing-bindings.json").read_text())[REPO][key_of()]["target"] == 1


def test_an_unreadable_record_file_never_stops_the_filing(  # BND-AC9
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = MemoryCodeHost()
    seed(host, [("person", "duplicate of #1")], closed_days_ago=31)
    root = tmp_path / ".tempergraph"
    root.mkdir()
    (root / "filing-bindings.json").write_text("{not json")
    results, _ = run_one(tmp_path, monkeypatch, host, 1)
    assert [r["op"] for r in results] == ["commented"]
    assert json.loads((root / "filing-bindings.json").read_text())[REPO][key_of()]["target"] == 1


def test_the_replay_of_five_causes_over_five_exits_on_two_utc_days(  # BND-AC12, BND-AC1, BND-AC6
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    day1 = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)  # the findings are stamped now
    monkeypatch.setitem(globals(), "DAY", day1)  # the closes of `seed` are relative to this day
    host = MemoryCodeHost()
    causes = ("c_one", "c_two", "c_three", "c_four", "c_five")
    seed(host, [("person", "Duplicate of #1")], 31, cause=causes[0], people=3)  # one number
    seed(host, [("person", "a duplicate of #2, and also duplicate of #3")], 31, cause=causes[1])  # two numbers
    seed(host, [("person", "duplicate of #1 and duplicate of #3")], 31, cause=causes[2])  # first is c_one's target
    seed(host, [], 10, cause=causes[3])  # closed as a duplicate with no comment
    before = len(host.issues)
    assert before == 7
    reg = registry(standin("claude", judges=[judge_says(0.5) for _ in range(8)]))  # the count of three decides
    root = tmp_path / ".tempergraph"
    outcomes: list[list[str]] = []
    for n in range(1, 6):
        set_day(monkeypatch, day1 if n <= 3 else day1 + timedelta(days=1))
        out = child.process(friction_ticket(root, n, causes), reg, host)
        outcomes.append(sorted(r["op"] for r in out["results"] if r["op"] != "bound"))
    early = outcomes[0] + outcomes[1]
    assert "filed" not in early and "commented" not in early
    assert outcomes[2].count("filed") == 1  # the pattern rule is met at the third exit, for the fifth cause only
    assert outcomes[2].count("muted") == 1 and outcomes[2].count("commented") == 2
    assert len(host.issues) == before + 1  # one issue opens over the five exits
    assert "c_five" in host.issues[-1]["title"]
    for exits in ((1, 2, 3), (4, 5)):  # one UTC day each: at most one comment a day for each target
        sent = [r["number"] for n in exits for r in rows_of(root, n, kind="issue_commented")]
        assert len(sent) == len(set(sent)), exits
    assert {c["number"] for c in host.comments} <= {1, 2, before + 1}
    assert "muted" in outcomes[3] and "muted" in outcomes[4]
