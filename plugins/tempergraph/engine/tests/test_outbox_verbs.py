"""`improve outbox list` and `improve outbox clear` on a fixture filing outbox (CLI-B21 to CLI-B23, CLI-B26; task AC 2)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tempergraph.constants import ExitCode
from tempergraph.store.layout import state_root_path

from .conftest import hash_tree
from .test_cli import cli


def _ago(days: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")


def write_outbox(repo: Path, entries: list[dict]) -> Path:
    path = state_root_path(repo) / "filing-outbox.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path


def fixture(repo: Path) -> Path:
    return write_outbox(repo, [
        {"op": "create", "repo": "acme/notes", "title": "loop: a cause", "body": "SECRET BODY",
         "fingerprint": "f1", "queued_at": _ago(2)},
        {"op": "comment", "repo": "acme/notes", "number": 7, "body": "SECRET COMMENT", "fingerprint": "f1",
         "queued_at": _ago(3)},
        {"op": "reopen", "repo": "acme/notes", "number": 12, "queued_at": _ago(1)},
        {"op": "comment", "repo": "acme/other", "number": 3, "body": "SECRET"},
    ])


def entries_of(repo: Path) -> list[dict]:
    code, doc, err = cli(repo, None, "improve", "outbox", "list")
    assert code == 0, err
    return doc["entries"]


def test_cli_ac12_list_prints_entries_oldest_first_without_a_body_and_writes_nothing(repo: Path) -> None:  # CLI-AC12, AC 2
    path = fixture(repo)
    before = hash_tree(state_root_path(repo))
    code, doc, _ = cli(repo, None, "improve", "outbox", "list")
    assert code == 0 and doc["schema_version"] == 1
    got = doc["entries"]
    assert [e["age_days"] for e in got] == [3.0, 2.0, 1.0, None]  # oldest first, one decimal, no queue time last
    assert [e["op"] for e in got[:3]] == ["comment", "create", "reopen"]
    create = next(e for e in got if e["op"] == "create")
    assert create["title"] == "loop: a cause" and create["repo"] == "acme/notes" and create["fingerprint"] == "f1"
    assert "number" not in create
    comment = next(e for e in got if e["op"] == "comment" and e["repo"] == "acme/notes")
    assert comment["number"] == 7 and "title" not in comment
    bare = next(e for e in got if e["repo"] == "acme/other")
    assert bare["age_days"] is None and bare["fingerprint"] is None
    assert "SECRET" not in json.dumps(doc) and all("body" not in e for e in got)
    assert hash_tree(state_root_path(repo)) == before and path.exists()


def test_cli_ac12_an_absent_outbox_lists_no_entry_and_writes_nothing(repo: Path) -> None:  # CLI-AC12, AC 2
    root = state_root_path(repo)
    before = hash_tree(root)
    code, doc, _ = cli(repo, None, "improve", "outbox", "list")
    assert code == 0 and doc["entries"] == []
    assert hash_tree(root) == before


def test_cli_ac13_clear_by_fingerprint_removes_those_and_keeps_the_others(repo: Path) -> None:  # CLI-AC13, AC 2
    fixture(repo)
    code, doc, err = cli(repo, None, "improve", "outbox", "clear", "--fingerprint", "f1")
    assert code == 0, err
    assert doc["removed"] == 2 and "caller" in doc
    assert sorted(e["op"] for e in entries_of(repo)) == ["comment", "reopen"]


def test_cli_ac13_clear_all_empties_the_outbox_and_prints_the_caller_block(repo: Path) -> None:  # CLI-AC13, AC 2
    fixture(repo)
    code, doc, err = cli(repo, None, "improve", "outbox", "clear", "--all")
    assert code == 0, err
    assert doc["removed"] == 4 and doc["caller"]
    assert entries_of(repo) == []


def test_cli_ac13_an_outbox_of_entries_with_no_fingerprint_is_untouched_by_a_fingerprint(repo: Path) -> None:  # CLI-AC13, AC 2
    write_outbox(repo, [{"op": "reopen", "repo": "acme/notes", "number": 12}, {"op": "comment", "repo": "a/b", "number": 1}])
    code, doc, _ = cli(repo, None, "improve", "outbox", "clear", "--fingerprint", "f1")
    assert code == 0 and doc["removed"] == 0
    assert len(entries_of(repo)) == 2


@pytest.mark.parametrize("argv", [(), ("--all", "--fingerprint", "f1")])
def test_cli_ac13_clear_without_one_scope_is_refused_and_leaves_the_outbox(repo: Path, argv: tuple[str, ...]) -> None:  # CLI-AC13, AC 2
    path = fixture(repo)
    raw = path.read_bytes()
    code, _, err = cli(repo, None, "improve", "outbox", "clear", *argv)
    assert code == ExitCode.USAGE
    assert "--all" in err and "--fingerprint" in err
    assert path.read_bytes() == raw


def test_cli_ac15_the_help_names_list_and_clear(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:  # CLI-AC15, AC 2
    capsys.readouterr()
    cli(repo, None, "improve", "outbox", "--help")
    text = capsys.readouterr().out
    assert "list" in text and "clear" in text
