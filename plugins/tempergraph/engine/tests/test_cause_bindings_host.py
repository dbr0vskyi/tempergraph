"""The code host reads the comments of one issue and one issue by number (BND-AC11: BND-B12, BND-B13, BND-B14)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tempergraph.improve.codehost import CodeHostError, GhCodeHost, MemoryCodeHost, NotFound

REPO = "acme/widgets"


def _gh_with(answers: dict[str, Any], seen: list[list[str]]) -> GhCodeHost:
    host = GhCodeHost()

    def run(args: list[str], payload: dict[str, Any] | None = None) -> str:
        seen.append(args)
        for key, text in answers.items():
            if any(a.endswith(key) for a in args):
                if isinstance(text, Exception):
                    raise text
                return str(text)
        raise AssertionError(f"unexpected argv {args}")

    host._run = run  # type: ignore[method-assign]
    return host


def _lines(items: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(i) for i in items) + "\n"


def _comment(text: str, login: str | None, kind: str, assoc: str, at: str = "2026-01-01T00:00:00Z") -> dict[str, Any]:
    return {"body": text, "created_at": at, "author_association": assoc,
            "user": {"login": login, "type": kind} if login else None}


def test_bnd_ac11_the_comments_are_read_by_list_argv_with_author_kinds_and_no_search() -> None:
    seen: list[list[str]] = []
    rows = [_comment("a", "ann", "User", "COLLABORATOR"), _comment("b", "bob", "User", "OWNER"),
            _comment("c", "ci", "Bot", "NONE"), _comment("d", "dep[bot]", "User", "NONE"),
            _comment("e", "eve", "User", "CONTRIBUTOR"), _comment("f", None, "User", "NONE"),
            _comment("g", "mem", "User", "MEMBER")]
    host = _gh_with({"/issues/5/comments": _lines(rows)}, seen)
    got = host.issue_comments(REPO, 5)
    assert [c["text"] for c in got] == list("abcdefg")
    assert [c["author_kind"] for c in got] == ["person", "person", "bot", "bot", "other", "other", "person"]
    assert got[0]["created_at"] == "2026-01-01T00:00:00Z"
    assert len(seen) == 1
    argv = seen[0]
    assert argv[:3] == ["api", "--method", "GET"]
    assert "repos/acme/widgets/issues/5/comments" in argv
    assert "--paginate" in argv
    assert all("search" not in a and "graphql" not in a for a in argv)


def test_bnd_ac11_an_issue_is_read_by_number_whatever_its_labels() -> None:
    seen: list[list[str]] = []
    answer = {"number": 9, "state": "closed", "state_reason": "COMPLETED", "closed_at": "2026-02-02T00:00:00Z",
              "html_url": "https://example.test/acme/widgets/issues/9", "comments": 3, "labels": [{"name": "bug"}]}
    host = _gh_with({"/issues/9": json.dumps(answer)}, seen)
    got = host.issue(REPO, 9)
    assert got == {"number": 9, "state": "closed", "state_reason": "completed", "closed_at": "2026-02-02T00:00:00Z",
                   "url": "https://example.test/acme/widgets/issues/9", "comments": 3, "is_pull_request": False}
    assert len(seen) == 1
    assert all("search" not in a and "graphql" not in a for a in seen[0])
    pr = _gh_with({"/issues/9": json.dumps({**answer, "pull_request": {"url": "x"}})}, [])
    assert pr.issue(REPO, 9)["is_pull_request"] is True


@pytest.mark.parametrize("repo,number", [("not a repo", 5), ("acme", 5), ("acme/widgets", "5; rm"), ("acme/widgets", None)])
def test_bnd_ac11_a_bad_repository_or_number_is_refused_before_any_request(repo: str, number: Any) -> None:
    seen: list[list[str]] = []
    host = _gh_with({}, seen)
    with pytest.raises(CodeHostError):
        host.issue_comments(repo, number)
    with pytest.raises(CodeHostError):
        host.issue(repo, number)
    assert seen == []


def test_bnd_ac11_a_404_is_told_from_another_failure() -> None:
    host = _gh_with({"/issues/4": NotFound("HTTP 404"), "/issues/4/comments": NotFound("HTTP 404")}, [])
    with pytest.raises(NotFound):
        host.issue(REPO, 4)
    with pytest.raises(NotFound):
        host.issue_comments(REPO, 4)
    other = _gh_with({"/issues/4": CodeHostError("gh exited 1")}, [])
    with pytest.raises(CodeHostError) as err:
        other.issue(REPO, 4)
    assert not isinstance(err.value, NotFound)
    odd = _gh_with({"/issues/4": json.dumps([1, 2])}, [])
    with pytest.raises(CodeHostError):
        odd.issue(REPO, 4)


def test_bnd_ac11_the_closed_list_gives_the_comment_count() -> None:
    row = {"number": 2, "html_url": "u", "body": "", "state_reason": "duplicate", "closed_at": "t", "comments": 4}
    host = _gh_with({"/issues": _lines([row])}, [])
    assert host.loop_issues(REPO, "closed")[0]["comments"] == 4


def _person_issue(host: MemoryCodeHost) -> int:
    host.create(REPO, "a person's report", "text", ["bug"])
    return host.issues[-1]["number"]


def test_bnd_ac11_the_memory_host_reads_a_persons_issue_and_its_comments() -> None:
    host = MemoryCodeHost()
    n = _person_issue(host)
    assert host.loop_issues(REPO, "open") == []
    got = host.issue(REPO, n)
    assert got["number"] == n and got["state"] == "open" and got["is_pull_request"] is False
    assert got["comments"] == 0
    host.add_comment(REPO, n, "Duplicate of #3", "person", "2026-03-01T00:00:00Z")
    host.add_comment(REPO, n, "beep", "bot", "2026-03-02T00:00:00Z")
    host.comment(REPO, n, "from the loop")
    got_comments = host.issue_comments(REPO, n)
    assert [(c["text"], c["author_kind"]) for c in got_comments] == [
        ("Duplicate of #3", "person"), ("beep", "bot"), ("from the loop", "other")]
    assert got_comments[0]["created_at"] == "2026-03-01T00:00:00Z"
    assert host.issue(REPO, n)["comments"] == 3
    host.close(REPO, n, "not_planned", "2026-04-01T00:00:00Z")
    closed = host.issue(REPO, n)
    assert (closed["state"], closed["state_reason"], closed["closed_at"]) == ("closed", "not_planned", "2026-04-01T00:00:00Z")


def test_bnd_ac11_the_memory_host_reports_a_pull_request_and_a_missing_number() -> None:
    host = MemoryCodeHost()
    n = _person_issue(host)
    host.issues[-1]["pull_request"] = True
    assert host.issue(REPO, n)["is_pull_request"] is True
    with pytest.raises(NotFound):
        host.issue(REPO, 99)
    with pytest.raises(NotFound):
        host.issue_comments(REPO, 99)


def test_bnd_ac11_the_memory_host_fails_reads_on_demand() -> None:
    host = MemoryCodeHost(fail_issue=1, fail_comments=2)
    n = _person_issue(host)
    with pytest.raises(CodeHostError):
        host.issue(REPO, n)
    assert host.issue(REPO, n)["number"] == n
    for _ in range(2):
        with pytest.raises(CodeHostError):
            host.issue_comments(REPO, n)
    assert host.issue_comments(REPO, n) == []
    host.down = True
    with pytest.raises(CodeHostError):
        host.issue(REPO, n)
    with pytest.raises(CodeHostError):
        host.issue_comments(REPO, n)


def test_bnd_ac11_each_closed_row_holds_its_comment_count() -> None:
    host = MemoryCodeHost()
    host.create(REPO, "loop issue", "body", ["tempergraph-loop"])
    host.add_comment(REPO, 1, "Duplicate of #2", "person", "2026-03-01T00:00:00Z")
    host.close(REPO, 1, "duplicate", "2026-03-02T00:00:00Z")
    rows = host.loop_issues(REPO, "closed")
    assert rows[0]["comments"] == 1
