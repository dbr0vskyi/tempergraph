"""A waiting outbox entry is checked at delivery (ISS-B16 to ISS-B18; task AC 1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.executors.standins import standin
from tempergraph.improve import child, filing
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.filing import Outbox, decide

from .test_filing import NOW, friction
from .test_loop_child import friction_ticket, judge_says, loop_rows
from .test_run import registry

REPO = "team/notes"


def decision() -> filing.Decision:
    return decide(friction(), [], REPO)


def ago(days: float, now: datetime = NOW) -> str:
    return (now - timedelta(days=days)).isoformat()


def create_entry(d: filing.Decision, queued_at: str | None = None) -> dict[str, Any]:
    f = d.candidate.finding
    p: dict[str, Any] = {"op": "create", "repo": REPO, "title": filing.title(f), "body": filing.body(d),
                         "labels": ["tempergraph-loop"], "fingerprint": str(f["fingerprint"])}
    if queued_at:
        p["queued_at"] = queued_at
    return p


def open_issue(host: MemoryCodeHost, body: str, number: int | None = None) -> int:
    n = number or len(host.issues) + 1
    host.issues.append({"repo": REPO, "number": n, "title": "t", "body": body, "labels": ["tempergraph-loop"],
                        "state": "open", "url": f"https://example.test/{REPO}/issues/{n}"})
    return n


def closed_issue(host: MemoryCodeHost, body: str, reason: str, days: float) -> None:
    n = open_issue(host, body)
    host.close(REPO, n, reason, ago(days))


def test_a_queued_create_becomes_a_comment_on_the_open_issue(tmp_path: Path) -> None:  # ISS-AC15, AC 1
    d = decision()
    f = d.candidate.finding
    cause_only = f"<!-- tempergraph:cause={filing.cause_key(f)} -->\n"
    for held in (filing.body(d), cause_only):  # its fingerprint line, or only its cause line
        host = MemoryCodeHost()
        number = open_issue(host, held)
        box = Outbox.at(tmp_path / str(len(held)))
        box.add(create_entry(d))
        res = filing.file([], host, box, now=NOW)
        assert [r["op"] for r in res] == ["commented"] and res[0]["number"] == number
        assert len(host.issues) == 1 and len(host.comments) == 1 and not box.take()


def test_a_queued_create_over_the_comment_bound_leaves_a_capped_result(tmp_path: Path) -> None:  # ISS-AC15, AC 1
    d = decision()
    host = MemoryCodeHost()
    number = open_issue(host, filing.body(d))
    box = Outbox.at(tmp_path)
    box.add(create_entry(d))
    res = filing.file([], host, box, now=NOW, comments_today={(REPO, number): 1})
    assert [r["op"] for r in res] == ["comment_capped"] and res[0]["number"] == number
    assert "body" not in res[0] and not host.comments and len(host.issues) == 1 and not box.take()


def test_a_queued_create_with_a_muted_cause_is_dropped(tmp_path: Path) -> None:  # ISS-AC16, AC 1
    d = decision()
    fp = str(d.candidate.finding["fingerprint"])
    for reason in ("not_planned", "duplicate"):
        host = MemoryCodeHost()
        closed_issue(host, filing.body(d), reason, 10)
        box = Outbox.at(tmp_path / reason)
        box.add(create_entry(d))
        res = filing.file([], host, box, now=NOW)
        assert res == [{"op": "outbox_dropped", "reason": "muted", "fingerprint": fp}]
        assert len(host.issues) == 1 and not host.comments and not box.take()


def test_a_queued_create_is_sent_when_the_mute_is_old_or_unread(tmp_path: Path) -> None:  # ISS-AC16, AC 1
    d = decision()
    old = MemoryCodeHost()
    closed_issue(old, filing.body(d), "not_planned", 31)
    box = Outbox.at(tmp_path / "old")
    box.add(create_entry(d))
    assert [r["op"] for r in filing.file([], old, box, now=NOW)] == ["redelivered"] and len(old.issues) == 2
    unread = MemoryCodeHost(fail_closed=2)
    closed_issue(unread, filing.body(d), "not_planned", 10)
    box = Outbox.at(tmp_path / "unread")
    box.add(create_entry(d))
    assert [r["op"] for r in filing.file([], unread, box, now=NOW)] == ["redelivered"] and len(unread.issues) == 2


def other_finding(**kw: Any) -> filing.Decision:
    """A second finding of the same cause (same workflow and cause code) with a fingerprint of its own."""
    return decide(friction(fingerprint="ff00ff00ff00ff00", unit="verify", **kw), [], REPO)


def test_an_issue_a_redelivery_opens_is_found_by_the_findings_of_its_cause(tmp_path: Path) -> None:  # ISS-AC15, AC 1
    d, later = decision(), other_finding()
    assert filing.cause_key(d.candidate.finding) == filing.cause_key(later.candidate.finding)
    host = MemoryCodeHost()
    box = Outbox.at(tmp_path)
    box.add(create_entry(d))
    res = filing.file([later], host, box, now=NOW)
    assert [r["op"] for r in res] == ["redelivered", "commented"]  # one issue, then a comment on it
    assert len(host.issues) == 1 and len(host.comments) == 1 and res[1]["number"] == host.issues[0]["number"]


def test_a_second_waiting_create_of_a_cause_comments_on_the_issue_the_first_opened(tmp_path: Path) -> None:  # ISS-AC15, AC 1
    d, second = decision(), other_finding()
    host = MemoryCodeHost()
    box = Outbox.at(tmp_path)
    box.add(create_entry(d))
    box.add(create_entry(second))
    res = filing.file([], host, box, now=NOW)
    assert [r["op"] for r in res] == ["redelivered", "commented"]
    assert len(host.issues) == 1 and len(host.comments) == 1


def test_an_entry_past_the_age_bound_is_dropped_of_any_kind(tmp_path: Path) -> None:  # ISS-AC17, AC 1
    d = decision()
    fp = str(d.candidate.finding["fingerprint"])
    host = MemoryCodeHost()
    open_issue(host, filing.body(d))  # an open issue holds the cause: the entry is still dropped, not commented
    box = Outbox.at(tmp_path)
    box.add(create_entry(d, ago(31)))
    box.add({"op": "comment", "repo": REPO, "number": 1, "body": "b", "queued_at": ago(31)})
    box.add({"op": "reopen", "repo": REPO, "number": 1, "queued_at": ago(31)})
    res = filing.file([], host, box, now=NOW)
    drop = {"op": "outbox_dropped", "reason": "expired", "repo": REPO}
    assert res[0] == {**drop, "entry_kind": "create", "fingerprint": fp}
    assert res[1] == {**drop, "entry_kind": "comment", "number": 1}
    assert res[2] == {**drop, "entry_kind": "reopen", "number": 1}
    assert not host.comments and len(host.issues) == 1 and not box.take()


def test_an_entry_within_the_bound_or_with_no_queue_time_is_delivered(tmp_path: Path) -> None:  # ISS-AC17, AC 1
    host = MemoryCodeHost()
    open_issue(host, "x")
    box = Outbox.at(tmp_path)
    box.add({"op": "comment", "repo": REPO, "number": 1, "body": "b", "queued_at": ago(29)})
    box.path.write_text(box.path.read_text() + '{"op": "comment", "repo": "team/notes", "number": 1, "body": "c"}\n')
    res = filing.file([], host, box, now=NOW)
    assert [r["op"] for r in res] == ["redelivered", "redelivered"] and len(host.comments) == 2


def test_a_refused_delivery_keeps_the_first_queue_time(tmp_path: Path) -> None:  # ISS-AC17, AC 1
    d = decision()
    box = Outbox.at(tmp_path)
    queued = ago(5)
    box.add(create_entry(d, queued))
    box.add({"op": "reopen", "repo": REPO, "number": 3})  # stamped when added
    assert filing.file([], MemoryCodeHost(down=True), box, now=NOW) == []
    kept = box.take()
    assert [e["queued_at"] for e in kept][0] == queued and kept[1]["queued_at"]


def test_the_loop_child_writes_a_dropped_entry_as_a_loop_result(tmp_path: Path) -> None:  # ISS-AC17, AC 1
    root = tmp_path / ".tempergraph"
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    Outbox.at(root).add({"op": "reopen", "repo": REPO, "number": 4, "queued_at": old})
    reg = registry(standin("claude", judges=[judge_says(0.5)]))
    out = child.process(friction_ticket(root, 1), reg, MemoryCodeHost())
    assert any(r.get("op") == "outbox_dropped" for r in out["results"])
    rows = [r for r in loop_rows(root, "F-1") if r["kind"] == "loop_result" and r["op"] == "outbox_dropped"]
    assert len(rows) == 1 and rows[0]["reason"] == "expired" and rows[0]["number"] == 4
    assert "body" not in rows[0] and "text" not in rows[0]
