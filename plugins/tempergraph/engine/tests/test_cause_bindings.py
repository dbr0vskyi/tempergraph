"""Learning a cause's binding and keeping its record (BND-B1, BND-B2, BND-B4 to BND-B6, BND-B8 to BND-B10)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tempergraph.improve import bindings
from tempergraph.improve.codehost import LOOP_LABEL, MemoryCodeHost

REPO = "team/notes"
KEY = "abcd1234abcd1234"
NOW = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
CLOSED = "2026-01-10T00:00:00Z"


class CountingHost(MemoryCodeHost):
    """The memory host that counts the reads of comments."""

    reads: int = 0

    def issue_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        self.reads += 1
        return super().issue_comments(repo, number)


def seeded(comments: list[tuple[str, str, str]], host: MemoryCodeHost | None = None) -> tuple[MemoryCodeHost, dict[str, Any]]:
    """Issue 1 is a person's (no loop label); issue 2 is the cause's loop issue, closed as a duplicate after
    `comments` (author kind, text, time)."""
    host = host or MemoryCodeHost()
    host.create(REPO, "person's issue", "body", ["bug"])
    host.create(REPO, "loop issue", "body", [LOOP_LABEL])
    for kind, text, at in comments:
        host.add_comment(REPO, 2, text, kind, at)
    host.close(REPO, 2, "duplicate", CLOSED)
    return host, source_of(host)


def source_of(host: MemoryCodeHost) -> dict[str, Any]:
    (src,) = [i for i in host.loop_issues(REPO, "closed") if i["number"] == 2]
    return src


def person(text: str, at: str = "2026-01-09T00:00:00Z") -> tuple[str, str, str]:
    return ("person", text, at)


def test_target_of_takes_the_first_number_in_any_case() -> None:  # BND-AC2
    assert bindings.target_of("Duplicate of #12, and also duplicate of #13") == 12
    assert bindings.target_of("closing: DUPLICATE   OF\t#7.") == 7
    assert bindings.target_of("duplicate of #5") == 5


def test_target_of_refuses_a_url_a_letter_before_and_a_word_after() -> None:  # BND-AC2
    assert bindings.target_of("duplicate of https://github.com/a/b/issues/5") is None
    assert bindings.target_of("notduplicate of #5") is None
    assert bindings.target_of("xduplicate of #5") is None
    assert bindings.target_of("duplicate of #5x") is None
    assert bindings.target_of("duplicate of #") is None
    assert bindings.target_of("see #5") is None


def test_the_newest_comment_of_a_person_with_a_number_wins(tmp_path: Path) -> None:  # BND-AC2
    host, src = seeded([person("duplicate of #1", "2026-01-08T00:00:00Z"),
                        person("Duplicate of #3, duplicate of #4", "2026-01-09T00:00:00Z")])
    host.create(REPO, "another", "b", ["bug"])  # number 3
    host.create(REPO, "yet another", "b", ["bug"])  # number 4
    got = bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    assert got.state == "bound" and got.number == 3 and got.learned


def test_a_newer_person_comment_with_no_number_changes_nothing(tmp_path: Path) -> None:  # BND-AC2
    host, src = seeded([person("duplicate of #1", "2026-01-08T00:00:00Z"), person("thanks", "2026-01-09T00:00:00Z")])
    got = bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    assert got.state == "bound" and got.number == 1 and got.issue["number"] == 1


def test_a_bot_or_an_other_binds_nothing(tmp_path: Path) -> None:  # BND-AC2
    host, src = seeded([("bot", "duplicate of #1", "2026-01-08T00:00:00Z"),
                        ("other", "duplicate of #1", "2026-01-09T00:00:00Z")])
    got = bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    assert got.state == "none" and got.number is None
    assert not (tmp_path / "filing-bindings.json").exists()  # a learning that finds no target writes nothing


def test_a_target_that_is_the_source_binds_nothing_and_no_second_number_is_tried(tmp_path: Path) -> None:  # BND-AC3
    host, src = seeded([person("duplicate of #2, duplicate of #1")])
    assert bindings.learn(host, REPO, KEY, src, tmp_path, NOW).state == "none"


def test_a_pull_request_binds_nothing(tmp_path: Path) -> None:  # BND-AC3
    host, src = seeded([person("duplicate of #3 and duplicate of #1")])
    host.create(REPO, "a pull request", "b", ["bug"])  # number 3
    host.issues[-1]["pull_request"] = True
    assert bindings.learn(host, REPO, KEY, src, tmp_path, NOW).state == "none"


def test_a_number_the_host_does_not_hold_binds_nothing(tmp_path: Path) -> None:  # BND-AC3
    host, src = seeded([person("duplicate of #99")])
    got = bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    assert got.state == "none" and got.number is None


def test_two_failed_reads_of_the_comments_are_unreadable_and_one_is_retried(tmp_path: Path) -> None:  # BND-AC4
    host, src = seeded([person("duplicate of #1")])
    host.fail_comments = 2
    assert bindings.learn(host, REPO, KEY, src, tmp_path, NOW).state == "unreadable"
    host.fail_comments = 1
    got = bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    assert got.state == "bound" and got.number == 1


def test_two_failed_reads_of_the_target_are_unreadable_and_one_is_retried(tmp_path: Path) -> None:  # BND-AC4
    host, src = seeded([person("duplicate of #1")])
    host.fail_issue = 2
    assert bindings.learn(host, REPO, KEY, src, tmp_path, NOW).state == "unreadable"
    host.fail_issue = 1
    assert bindings.learn(host, REPO, KEY, src, tmp_path / "second", NOW).state == "bound"


def test_the_record_is_owner_only_keyed_by_repository_and_cause_with_no_text(tmp_path: Path) -> None:  # BND-AC8
    host, src = seeded([person("duplicate of #1 please see the secret-canary")])
    bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    path = tmp_path / "filing-bindings.json"
    raw = path.read_text(encoding="utf-8")
    assert "canary" not in raw and "duplicate" not in raw
    record = json.loads(raw)[REPO][KEY]
    assert 1 in record.values() and 2 in record.values() and CLOSED in record.values()
    assert all(isinstance(v, int | str) for v in record.values())
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


def test_two_repositories_give_two_records(tmp_path: Path) -> None:  # BND-AC8
    for repo in (REPO, "team/other"):
        host = MemoryCodeHost()
        host.create(repo, "person's issue", "b", ["bug"])
        host.create(repo, "loop issue", "b", [LOOP_LABEL])
        host.add_comment(repo, 2, "duplicate of #1", "person", "2026-01-09T00:00:00Z")
        host.close(repo, 2, "duplicate", CLOSED)
        (src,) = host.loop_issues(repo, "closed")
        assert bindings.learn(host, repo, KEY, src, tmp_path, NOW).state == "bound"
    assert set(json.loads((tmp_path / "filing-bindings.json").read_text())) == {REPO, "team/other"}


def test_a_record_that_matches_the_host_saves_the_read_of_comments(tmp_path: Path) -> None:  # BND-AC9
    host, src = seeded([person("duplicate of #1")], CountingHost())
    first = bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    assert first.learned and host.reads == 1  # type: ignore[attr-defined]
    again = bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    assert again.state == "bound" and again.number == 1 and not again.learned
    assert host.reads == 1  # type: ignore[attr-defined]


def test_a_reopened_and_closed_again_source_rebuilds_the_record(tmp_path: Path) -> None:  # BND-AC9
    host, src = seeded([person("duplicate of #1")], CountingHost())
    bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    host.reopen(REPO, 2)
    host.close(REPO, 2, "duplicate", "2026-01-20T00:00:00Z")
    got = bindings.learn(host, REPO, KEY, source_of(host), tmp_path, NOW)
    assert got.learned and host.reads == 2  # type: ignore[attr-defined]


def test_a_new_comment_naming_another_number_replaces_the_target(tmp_path: Path) -> None:  # BND-AC9
    host, src = seeded([person("duplicate of #1")], CountingHost())
    host.create(REPO, "another", "b", ["bug"])  # number 3
    bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    host.add_comment(REPO, 2, "actually duplicate of #3", "person", "2026-01-11T00:00:00Z")
    got = bindings.learn(host, REPO, KEY, source_of(host), tmp_path, NOW)
    assert got.number == 3 and got.learned
    assert json.loads((tmp_path / "filing-bindings.json").read_text())[REPO][KEY]["target"] == 3


def test_an_unreadable_record_file_is_rebuilt_from_the_host(tmp_path: Path) -> None:  # BND-AC9
    host, src = seeded([person("duplicate of #1")])
    (tmp_path / "filing-bindings.json").write_text("{not json", encoding="utf-8")
    got = bindings.learn(host, REPO, KEY, src, tmp_path, NOW)
    assert got.state == "bound" and got.number == 1
    assert json.loads((tmp_path / "filing-bindings.json").read_text())[REPO][KEY]["target"] == 1


def test_a_second_root_with_no_record_writes_the_same_record(tmp_path: Path) -> None:  # BND-AC9
    host, src = seeded([person("duplicate of #1")])
    bindings.learn(host, REPO, KEY, src, tmp_path / "a", NOW)
    bindings.learn(host, REPO, KEY, src, tmp_path / "b", NOW)
    one = (tmp_path / "a" / "filing-bindings.json").read_text()
    assert one == (tmp_path / "b" / "filing-bindings.json").read_text()


def test_an_unwritable_record_never_stops_the_learning(tmp_path: Path) -> None:  # BND-AC9
    host, src = seeded([person("duplicate of #1")])
    blocker = tmp_path / "root"
    blocker.write_text("a file where the state root should be", encoding="utf-8")
    assert bindings.learn(host, REPO, KEY, src, blocker, NOW).state == "bound"


def test_the_opening_sentence_names_the_loop_the_cause_the_workflow_the_units_and_the_source() -> None:  # BND-AC5
    text = bindings.opening_sentence("demo", "slow_step", ["draft", "review"], 2)
    assert "\n" not in text
    for word in ("improvement loop", "slow_step", "demo", "draft", "review", "#2", "reopening"):
        assert word in text
    assert "duplicate of #" not in text.lower()


@pytest.mark.parametrize("units", [[], ["a"]])
def test_the_opening_sentence_holds_no_duplicate_of_pattern(units: list[str]) -> None:  # BND-AC5
    assert bindings.target_of(bindings.opening_sentence("w", "c", units, 9)) is None
