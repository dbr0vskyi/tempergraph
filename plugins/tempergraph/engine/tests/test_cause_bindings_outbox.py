"""A waiting create of a bound cause is delivered as a comment on its target (BND-AC10, BND-B11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.improve import filing
from tempergraph.improve.codehost import LOOP_LABEL, MemoryCodeHost
from tempergraph.improve.filing import Outbox, decide

from .test_filing import friction

REPO = "team/notes"


def decision() -> filing.Decision:
    return decide(friction(), [], REPO)


def iso(then: datetime, days_ago: float) -> str:
    return (then - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def waiting(tmp_path: Path, closing: list[tuple[str, str]], target_closed: tuple[str, float] | None = None,
            source_days: float = 31, strip: bool = False) -> tuple[MemoryCodeHost, Outbox, datetime, filing.Decision]:
    """A create queued by `filing.file` while the host is down; the cause's loop issue (closed as a duplicate
    `source_days` before the delivery) and a person's issue #1 exist on the host."""
    d = decision()
    key = filing.cause_key(d.candidate.finding)
    then = datetime.now(UTC) + timedelta(hours=1)
    host = MemoryCodeHost()
    host.create(REPO, "person's issue", "body", ["bug"])
    host.create(REPO, "[loop] demo: retry_burst", f"{filing._cause_line(key)}\nbody", [LOOP_LABEL])
    for i, (kind, text) in enumerate(closing):
        host.add_comment(REPO, 2, text, kind, iso(then, 40 - i))
    host.close(REPO, 2, "duplicate", iso(then, source_days))
    if target_closed:
        host.close(REPO, 1, target_closed[0], iso(then, target_closed[1]))
    box = Outbox.at(tmp_path)
    host.down = True
    assert [r["op"] for r in filing.file([d], host, box, now=then)] == ["queued"]
    host.down = False
    if strip:  # an entry of an earlier version: no workflow, cause or units
        (entry,) = box.take()
        for k in ("workflow", "cause", "units"):
            entry.pop(k, None)
        box.add(entry)
    return host, box, then, d


def ops(results: list[dict[str, Any]]) -> list[str]:
    return [r["op"] for r in results if r["op"] != "bound"]


def test_a_waiting_create_of_a_bound_cause_is_a_comment_on_the_target(tmp_path: Path) -> None:  # BND-AC10
    host, box, then, _ = waiting(tmp_path, [("person", "Duplicate of #1")], source_days=31)
    (entry,) = box.entries()
    assert entry["workflow"] == "demo" and entry["cause"] == "retry_burst" and entry["units"] == ["draft"]
    res = filing.file([], host, box, now=then)
    assert ops(res) == ["commented"] and res[-1]["number"] == 1
    assert len(host.issues) == 2 and [c["number"] for c in host.comments] == [1] and not box.take()
    text = host.comments[0]["body"]
    assert text.startswith("This comment comes from tempergraph's improvement loop")
    assert "`retry_burst`" in text and "`demo`" in text and "`draft`" in text and "#2" in text
    assert "duplicate of #" not in text.lower().replace("a duplicate of this issue", "")
    assert "**Seen again**" in text


def test_a_waiting_create_over_the_target_bound_leaves_a_capped_result(tmp_path: Path) -> None:  # BND-AC10
    host, box, then, _ = waiting(tmp_path, [("person", "Duplicate of #1")])
    res = filing.file([], host, box, now=then, comments_today={(REPO, 1): 1})
    assert ops(res) == ["comment_capped"] and res[-1]["number"] == 1
    assert not {"body", "text", "comment"} & set(res[-1])
    assert not host.comments and len(host.issues) == 2 and not box.take()


def test_an_entry_without_the_new_fields_takes_them_from_its_title_and_line(tmp_path: Path) -> None:  # BND-AC10
    host, box, then, _ = waiting(tmp_path, [("person", "Duplicate of #1")], strip=True)
    (entry,) = box.entries()
    assert not {"workflow", "cause", "units"} & set(entry)
    res = filing.file([], host, box, now=then)
    assert ops(res) == ["commented"]
    text = host.comments[0]["body"]
    assert "`retry_burst`" in text and "`demo`" in text and "`draft`" in text and "#2" in text


def test_a_bound_entry_whose_binding_cannot_be_read_goes_back(tmp_path: Path) -> None:  # BND-AC10
    host, box, then, _ = waiting(tmp_path, [("person", "Duplicate of #1")])
    (before,) = box.entries()
    host.fail_comments = 2
    res = filing.file([], host, box, now=then)
    assert ops(res) == [] and not host.comments and len(host.issues) == 2
    (after,) = box.entries()
    assert after["queued_at"] == before["queued_at"] and after["fingerprint"] == before["fingerprint"]


def test_a_target_closed_as_completed_sends_the_entry_as_queued(tmp_path: Path) -> None:  # BND-AC10
    host, box, then, _ = waiting(tmp_path, [("person", "Duplicate of #1")], ("completed", 10))
    res = filing.file([], host, box, now=then)
    assert ops(res) == ["redelivered"] and not host.comments and len(host.issues) == 3
    assert "Possible regression" not in host.issues[-1]["body"] and not box.take()


def test_a_target_closed_not_planned_or_duplicate_inside_mute_days_drops_the_entry(tmp_path: Path) -> None:  # BND-AC10
    for reason in ("not_planned", "duplicate"):
        host, box, then, _ = waiting(tmp_path / reason, [("person", "Duplicate of #1")], (reason, 10))
        res = filing.file([], host, box, now=then)
        assert ops(res) == ["outbox_dropped"] and res[-1]["reason"] == "muted"
        assert not host.comments and len(host.issues) == 2 and not box.take()
    host, box, then, _ = waiting(tmp_path / "old", [("person", "Duplicate of #1")], ("not_planned", 31))
    assert ops(filing.file([], host, box, now=then)) == ["redelivered"]  # after `mute.days` it is sent as queued
