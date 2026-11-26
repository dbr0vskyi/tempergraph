"""The code host client asks for little and counts only people (OUT-AC11, OUT-AC9; task AC 4, AC 5)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tempergraph.improve.codehost import CodeHostError, GhCodeHost, NotFound

END = "a" * 40
LATER = "b" * 40
LATER2 = "c" * 40
EARLIER = "9" * 40
PARENT = [{"sha": "1" * 40}]


def _lines(items: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(i) for i in items) + "\n"


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


def _commit(sha: str, login: str = "ann", kind: str = "User", parents: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {"sha": sha, "author": {"login": login, "type": kind} if login else None,
            "parents": PARENT if parents is None else parents}


def _answers(listing: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"/pulls/7/commits": _lines(listing)}
    for c in listing:
        out[f"/commits/{c['sha']}"] = json.dumps({"files": [{"filename": f"{c['sha'][0]}.py"}]})
    out.update(extra)
    return out


def _gets(seen: list[list[str]], part: str) -> list[list[str]]:
    return [a for a in seen if any(part in x for x in a)]


def test_out_ac11_files_are_asked_for_only_the_commits_after_the_end_commit() -> None:
    seen: list[list[str]] = []
    listing = [_commit(EARLIER), _commit(END), _commit(LATER), _commit(LATER2, login="bob")]
    host = _gh_with(_answers(listing, **{"/collaborators/ann": "", "/collaborators/bob": ""}), seen)
    got = host.pull_commits("acme/notes", 7, after=END)
    assert [c["sha"] for c in got] == [EARLIER, END, LATER, LATER2]
    assert [c["files"] for c in got] == [[], [], ["b.py"], ["c.py"]]
    asked = [a for a in seen if any("/commits/" in x and "/pulls/" not in x for x in a)]
    assert [a[-1].rsplit("/", 1)[1] for a in asked if a[-1].rsplit("/", 1)[0].endswith("/commits")] == [LATER, LATER2]
    assert len(_gets(seen, "/pulls/7/commits")) == 1
    assert not _gets(seen, f"/commits/{END}") and not _gets(seen, f"/commits/{EARLIER}")
    assert all(a[:3] == ["api", "--method", "GET"] for a in seen)


@pytest.mark.parametrize("after", ["", "d" * 40])
def test_out_ac11_no_end_commit_or_one_not_in_the_list_asks_for_no_commit(after: str) -> None:
    seen: list[list[str]] = []
    listing = [_commit(END), _commit(LATER)]
    host = _gh_with(_answers(listing), seen)
    got = host.pull_commits("acme/notes", 7, after=after)
    assert [c["files"] for c in got] == [[], []]
    assert not [a for a in seen if any("/commits/" in x and "/pulls/" not in x for x in a)]
    assert not _gets(seen, "/collaborators/")
    assert all(c["author_kind"] != "person" for c in got)


def test_out_ac9_a_review_and_a_review_comment_count_only_for_an_owner_member_or_collaborator() -> None:
    seen: list[list[str]] = []
    cases = [("OWNER", "User", "ann", "person"), ("MEMBER", "User", "ann", "person"),
             ("COLLABORATOR", "User", "ann", "person"), ("NONE", "User", "ann", "other"),
             ("CONTRIBUTOR", "User", "ann", "other"), ("FIRST_TIMER", "User", "ann", "other"),
             ("OWNER", "Bot", "ci", "bot"), ("MEMBER", "User", "dependabot[bot]", "bot")]
    reviews = [{"state": "COMMENTED", "body": "t", "author_association": a, "user": {"login": lg, "type": ty}}
               for a, ty, lg, _ in cases]
    comments = [{"body": "t", "path": "a.py", "author_association": a, "user": {"login": lg, "type": ty}}
                for a, ty, lg, _ in cases]
    host = _gh_with({"/pulls/7/reviews": _lines(reviews), "/pulls/7/comments": _lines(comments)}, seen)
    want = [k for *_, k in cases]
    assert [r["author_kind"] for r in host.pull_reviews("acme/notes", 7)] == want
    assert [c["author_kind"] for c in host.pull_comments("acme/notes", 7)] == want


def test_out_ac9_a_review_with_no_user_is_not_a_person() -> None:
    seen: list[list[str]] = []
    host = _gh_with({"/pulls/7/reviews": _lines([{"state": "APPROVED", "body": "", "user": None}])}, seen)
    assert host.pull_reviews("acme/notes", 7)[0]["author_kind"] == "other"


def test_out_ac9_a_commit_after_the_end_is_a_person_only_with_an_account_one_parent_and_a_collaborator() -> None:
    seen: list[list[str]] = []
    shas = ["1a" * 20, "2a" * 20, "3a" * 20, "4a" * 20, "5a" * 20, "6a" * 20]
    listing = [_commit(END),
               _commit(shas[0], login="ann"),                      # a collaborator: person
               _commit(shas[1], login=""),                         # no account
               _commit(shas[2], login="ann", parents=PARENT * 2),  # a merge
               _commit(shas[3], login="ann", parents=[]),          # no parent
               _commit(shas[4], login="eve"),                      # not a collaborator
               _commit(shas[5], login="robo[bot]", kind="Bot")]
    host = _gh_with(_answers(listing, **{"/collaborators/ann": "", "/collaborators/eve": NotFound("HTTP 404")}), seen)
    got = host.pull_commits("acme/notes", 7, after=END)
    assert [c["author_kind"] for c in got] == ["other", "person", "other", "other", "other", "other", "bot"]
    # one check for each distinct login, not repeated for a second commit of the same author
    assert len(_gets(seen, "repos/acme/notes/collaborators/ann")) == 1
    assert len(_gets(seen, "repos/acme/notes/collaborators/eve")) == 1
    assert not _gets(seen, "/collaborators/robo")


def test_out_ac9_a_failed_collaborator_check_raises_code_host_error() -> None:
    seen: list[list[str]] = []
    host = _gh_with(_answers([_commit(END), _commit(LATER)], **{"/collaborators/ann": CodeHostError("gh exited 1")}),
                    seen)
    with pytest.raises(CodeHostError) as exc:
        host.pull_commits("acme/notes", 7, after=END)
    assert not isinstance(exc.value, NotFound)
