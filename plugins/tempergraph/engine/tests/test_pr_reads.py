"""PRP-AC11, AC 2: the code host clients read a pull request's reviews, comments and commits, read-only."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tempergraph.improve import codehost
from tempergraph.improve.codehost import CodeHostError, GhCodeHost, MemoryCodeHost

SHA = "a" * 40


def _lines(items: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(i) for i in items) + "\n"


def _gh_with(answers: dict[str, str], seen: list[list[str]]) -> GhCodeHost:
    host = GhCodeHost()

    def run(args: list[str], payload: dict[str, Any] | None = None) -> str:
        seen.append(args)
        assert payload is None
        for key, text in answers.items():
            if any(a.endswith(key) for a in args):
                return text
        raise AssertionError(f"unexpected argv {args}")

    host._run = run  # type: ignore[method-assign]
    return host


def test_prp_ac11_reviews_are_one_constant_get_with_state_and_author_kind() -> None:
    seen: list[list[str]] = []
    raw = [
        {"state": "CHANGES_REQUESTED", "body": "fix it", "user": {"login": "ann", "type": "User"}},
        {"state": "APPROVED", "body": "", "user": {"login": "ci[bot]", "type": "Bot"}},
        {"state": "COMMENTED", "body": "hm", "user": {"login": "dependabot[bot]", "type": "User"}},
        {"state": "DISMISSED", "body": "x", "user": {"login": "bob", "type": "User"}},
        {"state": "PENDING", "body": "draft", "user": {"login": "cy", "type": "User"}},
    ]
    host = _gh_with({"/pulls/7/reviews": _lines(raw)}, seen)
    got = host.pull_reviews("acme/notes", 7)
    assert [(r["state"], r["author_kind"]) for r in got] == [
        ("changes_requested", "person"), ("approved", "bot"), ("commented", "bot"), ("dismissed", "person")]
    assert got[0]["text"] == "fix it"
    assert len(seen) == 1
    assert seen[0][:3] == ["api", "--method", "GET"]
    assert "repos/acme/notes/pulls/7/reviews" in seen[0]
    assert not any(a in ("POST", "PATCH", "PUT", "DELETE", "--input") for a in seen[0])


def test_prp_ac11_review_comments_are_one_constant_get() -> None:
    seen: list[list[str]] = []
    raw = [{"body": "nit", "path": "a.py", "user": {"login": "ann", "type": "User"}},
           {"body": "bot says", "path": "b.py", "user": {"login": "x[bot]", "type": "Bot"}}]
    host = _gh_with({"/pulls/7/comments": _lines(raw)}, seen)
    got = host.pull_comments("acme/notes", 7)
    assert [(c["author_kind"], c["text"]) for c in got] == [("person", "nit"), ("bot", "bot says")]
    assert len(seen) == 1 and seen[0][:3] == ["api", "--method", "GET"]
    assert "repos/acme/notes/pulls/7/comments" in seen[0]


def test_prp_ac11_commits_hold_author_kind_and_changed_files() -> None:
    seen: list[list[str]] = []
    other = "b" * 40
    listing = [{"sha": SHA, "author": {"login": "ann", "type": "User"}},
               {"sha": other, "author": {"login": "x[bot]", "type": "Bot"}}]
    host = _gh_with({
        "/pulls/7/commits": _lines(listing),
        f"/commits/{SHA}": json.dumps({"files": [{"filename": "a.py"}, {"filename": "b/c.py"}]}),
        f"/commits/{other}": json.dumps({"files": [{"filename": "z.py"}]}),
    }, seen)
    got = host.pull_commits("acme/notes", 7)
    assert [(c["sha"], c["author_kind"], c["files"]) for c in got] == [
        (SHA, "person", ["a.py", "b/c.py"]), (other, "bot", ["z.py"])]
    assert all(a[:3] == ["api", "--method", "GET"] for a in seen)
    assert len(seen) == 3


def test_prp_ac11_the_repository_and_the_sha_are_checked() -> None:
    seen: list[list[str]] = []
    host = _gh_with({"/commits": _lines([{"sha": "x; rm -rf", "author": None}])}, seen)
    for call in (lambda: host.pull_reviews("not a repo", 1), lambda: host.pull_comments("a/b/c", 1),
                 lambda: host.pull_commits("acme", 1)):
        with pytest.raises(CodeHostError):
            call()
    assert seen == []
    host2 = _gh_with({"/pulls/1/commits": _lines([{"sha": "x; rm -rf", "author": None}])}, seen)
    with pytest.raises(CodeHostError):
        host2.pull_commits("acme/notes", 1)


def test_prp_ac11_a_missing_gh_and_an_unknown_shape_raise_code_host_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codehost.shutil, "which", lambda _name: None)
    for call in (GhCodeHost().pull_reviews, GhCodeHost().pull_comments, GhCodeHost().pull_commits):
        with pytest.raises(CodeHostError):
            call("acme/notes", 1)
    seen: list[list[str]] = []
    host = _gh_with({"/pulls/1/reviews": "[1, 2]\n", "/pulls/1/comments": "not json\n"}, seen)
    with pytest.raises(CodeHostError):
        host.pull_reviews("acme/notes", 1)
    with pytest.raises(CodeHostError):
        host.pull_comments("acme/notes", 1)


def test_prp_ac11_the_memory_client_answers_from_its_lists_and_fails_when_down() -> None:
    review = {"state": "changes_requested", "author_kind": "person", "text": "t"}
    comment = {"author_kind": "person", "text": "c"}
    commit = {"sha": SHA, "author_kind": "person", "files": ["a.py"]}
    host = MemoryCodeHost(reviews={("acme/notes", 3): [review]}, review_comments={("acme/notes", 3): [comment]},
                          commits={("acme/notes", 3): [commit]})
    assert host.pull_reviews("acme/notes", 3) == [review]
    assert host.pull_comments("acme/notes", 3) == [comment]
    assert host.pull_commits("acme/notes", 3) == [commit]
    assert host.pull_reviews("acme/notes", 4) == []
    host.down = True
    for call in (host.pull_reviews, host.pull_comments, host.pull_commits):
        with pytest.raises(CodeHostError):
            call("acme/notes", 3)
