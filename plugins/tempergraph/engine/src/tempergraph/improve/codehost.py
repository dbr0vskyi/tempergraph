"""The code host client for filing (ADR `first-release-is-simple-trusted-workflows-on-one-machine` S5): GitHub through the person's own `gh` sign-in.

A sanctioned launch site (SEC-B7): constant subcommands as list argv, the repository checked as
`owner/name`, the issue number an int, and every user-derived text (title, body, comment) on stdin as JSON
through `gh api --input -`. Never imports or opens the evidence file.
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote

REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
LOOP_LABEL = "tempergraph-loop"  # the label every loop issue carries (ISS-B1); its list read (ISS-B9) filters on it


class CodeHostError(Exception):
    pass


class NotFound(CodeHostError):
    """The host answered `HTTP 404`."""


class CodeHost(Protocol):
    def loop_issues(self, repo: str, state: str) -> list[dict[str, Any]]: ...
    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str: ...
    def comment(self, repo: str, number: int, body: str) -> str: ...
    def reopen(self, repo: str, number: int) -> None: ...


class IssueReadHost(Protocol):
    """Read-only questions about one issue, whatever labels it carries (BND-B12, BND-B13). A comment holds its
    text, its author kind (`person`, `bot` or `other`) and its time; an issue holds `number`, `state`, `state_reason`
    (lower case), `closed_at`, `url`, `comments` (a count) and `is_pull_request`. An issue the host does not hold
    raises `NotFound`."""

    def issue_comments(self, repo: str, number: int) -> list[dict[str, Any]]: ...
    def issue(self, repo: str, number: int) -> dict[str, Any]: ...


class PullRequestHost(Protocol):
    """Draft pull requests for proposals (PRP-B8). There is no merge method, by design (PRP-AC2)."""

    def default_branch(self, repo: str) -> str: ...
    def create_draft_pr(self, repo: str, head: str, base: str, title: str, body: str, labels: list[str]) -> str: ...
    def pull_state(self, repo: str, number: int) -> dict[str, Any]: ...


class PullReviewHost(Protocol):
    """Read-only questions about a pull request's reviews, review comments and commits. Each answer holds an
    author kind (`person`, `bot` or `other`); the text of a review or comment is for local use only. Only the
    commits after `after` hold their changed files."""

    def pull_reviews(self, repo: str, number: int) -> list[dict[str, Any]]: ...
    def pull_comments(self, repo: str, number: int) -> list[dict[str, Any]]: ...
    def pull_commits(self, repo: str, number: int, after: str = "") -> list[dict[str, Any]]: ...


REVIEW_STATES = ("approved", "changes_requested", "commented", "dismissed")
SHA = re.compile(r"^[0-9a-f]{7,64}$")
STANDING = ("OWNER", "MEMBER", "COLLABORATOR")


def _kind(user: Any, association: Any = None) -> str:
    """`bot` for a `Bot` account or a `[bot]` login; `person` only for a `User` whose standing the host gives
    (`association` of `OWNER`, `MEMBER` or `COLLABORATOR`); `other` for anything else, a missing user included."""
    if not isinstance(user, dict):
        return "other"
    login = str(user.get("login") or "")
    if user.get("type") == "Bot" or login.endswith("[bot]"):
        return "bot"
    return "person" if user.get("type") == "User" and association in STANDING else "other"


def _records(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln in text.splitlines():
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except ValueError:
            raise CodeHostError("the pull request answer is not JSON") from None
        if not isinstance(r, dict):
            raise CodeHostError("the pull request answer has no known shape")
        out.append(r)
    return out


BRANCH = re.compile(r"^(improve/[A-Za-z0-9_.-]{1,80}|tempergraph/upgrade/[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,40})$")


def _check_branch(head: str) -> str:
    if not BRANCH.match(head):
        raise CodeHostError(f"branch {head!r} is not an improve/<proposal> or upgrade branch")
    return head


def _check(repo: str) -> str:
    if not REPO.match(repo):
        raise CodeHostError(f"repository {repo!r} is not owner/name")
    return repo


def _number(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodeHostError("the issue number is not a whole number")
    return value


@dataclass(kw_only=True)
class GhCodeHost:
    timeout_s: float = 60.0

    def _gh(self, args: list[str], payload: dict[str, Any] | None = None) -> Any:
        out = self._run(args, payload)
        return json.loads(out) if out.strip() else None

    def _run(self, args: list[str], payload: dict[str, Any] | None = None) -> str:
        exe = shutil.which("gh")
        if exe is None:
            raise CodeHostError("gh is not installed")
        try:
            proc = subprocess.run(  # noqa: S603 - constant subcommands, text on stdin (SEC-B7)
                [exe, *args], input=json.dumps(payload) if payload is not None else None, capture_output=True,
                text=True, timeout=self.timeout_s)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CodeHostError(type(exc).__name__) from None
        if proc.returncode != 0:
            if "HTTP 404" in (proc.stderr or ""):
                raise NotFound("HTTP 404")
            raise CodeHostError(f"gh exited {proc.returncode}")
        return proc.stdout

    def loop_issues(self, repo: str, state: str) -> list[dict[str, Any]]:
        """ISS-B9: every issue of the repository in `state` (`open` or `closed`) that carries the loop's label, read
        page by page through the REST list endpoint, not the search index: an issue is listed the moment it exists,
        and the call needs no GraphQL. Pull requests are left out."""
        if state not in ("open", "closed"):
            raise CodeHostError("state is not open or closed")
        text = self._run(["api", "--method", "GET", f"repos/{_check(repo)}/issues", "-f", f"state={state}",
                          "-f", f"labels={LOOP_LABEL}", "-f", "per_page=100", "--paginate", "--jq", ".[]"])
        out: list[dict[str, Any]] = []
        for ln in text.splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("pull_request"):
                continue
            out.append({"number": r.get("number"), "url": r.get("html_url"), "body": r.get("body") or "",
                        "state_reason": str(r.get("state_reason") or "").lower(), "closed_at": r.get("closed_at") or "",
                        "created_at": r.get("created_at") or "",
                        "comments": r.get("comments") if isinstance(r.get("comments"), int) else 0})
        return out

    def issue_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        """BND-B12: every page of one issue's comments through one paged REST GET, each with its author kind."""
        n = _number(number)
        text = self._run(["api", "--method", "GET", f"repos/{_check(repo)}/issues/{n}/comments",
                          "-f", "per_page=100", "--paginate", "--jq", ".[]"])
        return [{"text": str(r.get("body") or ""), "author_kind": _kind(r.get("user"), r.get("author_association")),
                 "created_at": str(r.get("created_at") or "")} for r in _records(text)]

    def issue(self, repo: str, number: int) -> dict[str, Any]:
        """BND-B13: one REST GET of an issue by number, whatever labels it carries."""
        n = _number(number)
        try:
            got = self._gh(["api", "--method", "GET", f"repos/{_check(repo)}/issues/{n}"])
        except ValueError:
            raise CodeHostError("the issue answer is not JSON") from None
        if not isinstance(got, dict):
            raise CodeHostError("the issue answer has no known shape")
        count = got.get("comments")
        return {"number": got.get("number"), "state": str(got.get("state") or ""),
                "state_reason": str(got.get("state_reason") or "").lower(), "closed_at": got.get("closed_at") or "",
                "url": got.get("html_url") or "", "comments": count if isinstance(count, int) else 0,
                "is_pull_request": bool(got.get("pull_request"))}

    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str:
        got = self._gh(["api", f"repos/{_check(repo)}/issues", "--method", "POST", "--input", "-"],
                       {"title": title, "body": body, "labels": labels})
        return str((got or {}).get("html_url") or "")

    def comment(self, repo: str, number: int, body: str) -> str:
        got = self._gh(["api", f"repos/{_check(repo)}/issues/{int(number)}/comments", "--method", "POST",
                        "--input", "-"], {"body": body})
        return str((got or {}).get("html_url") or "")

    def issue_state(self, repo: str, number: int) -> str | None:
        """DRV-B2: `open` or `closed`, None when the issue cannot be read."""
        try:
            got = self._gh(["api", f"repos/{_check(repo)}/issues/{int(number)}"])
        except CodeHostError:
            return None
        state = str((got or {}).get("state") or "")
        return state if state in ("open", "closed") else None

    def reopen(self, repo: str, number: int) -> None:
        self._gh(["api", f"repos/{_check(repo)}/issues/{int(number)}", "--method", "PATCH", "--input", "-"],
                 {"state": "open"})

    def default_branch(self, repo: str) -> str:
        got = self._gh(["api", f"repos/{_check(repo)}"])
        return str((got or {}).get("default_branch") or "main")

    def create_draft_pr(self, repo: str, head: str, base: str, title: str, body: str, labels: list[str]) -> str:
        """Always a draft; labels go on through the issues endpoint, best effort."""
        got = self._gh(["api", f"repos/{_check(repo)}/pulls", "--method", "POST", "--input", "-"],
                       {"title": title, "body": body, "head": _check_branch(head), "base": base, "draft": True})
        number = (got or {}).get("number")
        if labels and isinstance(number, int):
            with contextlib.suppress(CodeHostError):
                self._gh(["api", f"repos/{_check(repo)}/issues/{number}/labels", "--method", "POST", "--input", "-"],
                         {"labels": labels})
        return str((got or {}).get("html_url") or "")

    def pull_state(self, repo: str, number: int) -> dict[str, Any]:
        """PRP-B26: one read-only GET of the pull request: `open`, `merged` or `closed` (without a merge), and the
        merge time the host reports."""
        got = self._read_pull(repo, number)
        if not isinstance(got, dict):
            raise CodeHostError("the pull request answer has no known shape")
        merged_at = got.get("merged_at")
        if got.get("merged") is True or (merged_at and got.get("state") == "closed"):
            return {"state": "merged", "merged_at": str(merged_at) if merged_at else None}
        state = got.get("state")
        if state not in ("open", "closed"):
            raise CodeHostError("the pull request answer has no known state")
        return {"state": str(state), "merged_at": None}

    def _paged(self, repo: str, number: int, part: str) -> list[dict[str, Any]]:
        text = self._run(["api", "--method", "GET", f"repos/{_check(repo)}/pulls/{int(number)}/{part}",
                          "-f", "per_page=100", "--paginate", "--jq", ".[]"])
        return _records(text)

    def pull_reviews(self, repo: str, number: int) -> list[dict[str, Any]]:
        """One read-only GET: each review with its lower-case state and author kind; a pending review is left out."""
        out: list[dict[str, Any]] = []
        for r in self._paged(repo, number, "reviews"):
            state = str(r.get("state") or "").lower()
            if state == "pending":
                continue
            if state not in REVIEW_STATES:
                raise CodeHostError("the review answer has no known state")
            out.append({"state": state, "author_kind": _kind(r.get("user"), r.get("author_association")),
                        "text": str(r.get("body") or ""),
                        "submitted_at": str(r.get("submitted_at") or "")})
        return out

    def pull_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        """One read-only GET: each review comment with its author kind."""
        return [{"author_kind": _kind(r.get("user"), r.get("author_association")), "text": str(r.get("body") or ""),
                 "path": str(r.get("path") or ""), "created_at": str(r.get("created_at") or "")}
                for r in self._paged(repo, number, "comments")]

    def _collaborator(self, repo: str, login: str) -> bool:
        """One read-only GET of the repository's collaborator check: no answer body is a yes, `HTTP 404` a no."""
        try:
            self._run(["api", "--method", "GET", f"repos/{_check(repo)}/collaborators/{quote(login, safe='')}"])
        except NotFound:
            return False
        return True

    def pull_commits(self, repo: str, number: int, after: str = "") -> list[dict[str, Any]]:
        """Each commit of the pull request with its author kind. One GET for the list, and one for each commit after
        the commit `after` (a sha or its prefix) for its changed files; none when `after` is empty or not in the
        list, and a commit up to `after` holds kind `other` and no files. A commit after `after` is a `person` only
        with an account of type `User`, exactly one parent and a yes from the collaborator check (one GET for each
        distinct login)."""
        listed = self._paged(repo, number, "commits")
        for r in listed:
            sha = r.get("sha")
            if not isinstance(sha, str) or not SHA.match(sha):
                raise CodeHostError("the commit answer has no known sha")
        cut = -1
        if after:
            for i, r in enumerate(listed):
                sha = str(r["sha"])
                if sha.startswith(after) or after.startswith(sha):
                    cut = i
                    break
        standing: dict[str, bool] = {}
        out: list[dict[str, Any]] = []
        for i, r in enumerate(listed):
            sha = str(r["sha"])
            commit = r.get("commit") if isinstance(r.get("commit"), dict) else {}
            when = (commit.get("committer") or {}).get("date") if isinstance(commit, dict) else None
            kind, files = "other", []
            if cut >= 0 and i > cut:
                try:
                    one = self._gh(["api", "--method", "GET", f"repos/{_check(repo)}/commits/{sha}"])
                except ValueError:
                    raise CodeHostError("the commit answer is not JSON") from None
                if not isinstance(one, dict):
                    raise CodeHostError("the commit answer has no known shape")
                files = [str(f.get("filename")) for f in one.get("files") or []
                         if isinstance(f, dict) and f.get("filename")]
                author = r.get("author")
                login = str(author.get("login") or "") if isinstance(author, dict) else ""
                if not isinstance(author, dict) or not login:
                    kind = "other"
                elif author.get("type") == "Bot" or login.endswith("[bot]"):
                    kind = "bot"
                elif author.get("type") == "User" and len(r.get("parents") or []) == 1:
                    if login not in standing:
                        standing[login] = self._collaborator(repo, login)
                    kind = "person" if standing[login] else "other"
            out.append({"sha": sha, "author_kind": kind, "files": files, "committed_at": str(when or "")})
        return out

    def _read_pull(self, repo: str, number: int) -> Any:
        try:
            return self._gh(["api", f"repos/{_check(repo)}/pulls/{int(number)}"])
        except ValueError:
            raise CodeHostError("the pull request answer is not JSON") from None


@dataclass(kw_only=True)
class MemoryCodeHost:
    """A code host in memory, for tests and dry runs."""

    issues: list[dict[str, Any]] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)
    pulls: list[dict[str, Any]] = field(default_factory=list)
    reviews: dict[tuple[str, int], list[dict[str, Any]]] = field(default_factory=dict)
    review_comments: dict[tuple[str, int], list[dict[str, Any]]] = field(default_factory=dict)
    commits: dict[tuple[str, int], list[dict[str, Any]]] = field(default_factory=dict)
    files_asked: list[str] = field(default_factory=list)
    fail_search: int = 0
    fail_closed: int = 0
    fail_issue: int = 0
    fail_comments: int = 0
    thread: list[dict[str, Any]] = field(default_factory=list)
    down: bool = False

    def add_comment(self, repo: str, number: int, body: str, author_kind: str, at: str) -> None:
        """Seeds a comment of a given author kind (`person`, `bot` or `other`) at an ISO time."""
        self.thread.append({"repo": repo, "number": number, "text": body, "author_kind": author_kind, "created_at": at})

    def _count(self, repo: str, number: int) -> int:
        return sum(1 for c in self.thread if c["repo"] == repo and c["number"] == number)

    def _find(self, repo: str, number: int) -> dict[str, Any]:
        for i in self.issues:
            if i["repo"] == repo and i["number"] == number:
                return i
        raise NotFound("HTTP 404")

    def issue_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        if self.down:
            raise CodeHostError("unreachable")
        if self.fail_comments:
            self.fail_comments -= 1
            raise CodeHostError("comments read failed")
        self._find(repo, number)
        return [{"text": c["text"], "author_kind": c["author_kind"], "created_at": c["created_at"]}
                for c in self.thread if c["repo"] == repo and c["number"] == number]

    def issue(self, repo: str, number: int) -> dict[str, Any]:
        if self.down:
            raise CodeHostError("unreachable")
        if self.fail_issue:
            self.fail_issue -= 1
            raise CodeHostError("issue read failed")
        i = self._find(repo, number)
        return {"number": i["number"], "state": i["state"], "state_reason": str(i.get("state_reason") or "").lower(),
                "closed_at": i.get("closed_at") or "", "url": i["url"], "comments": self._count(repo, number),
                "is_pull_request": bool(i.get("pull_request"))}

    def pull_reviews(self, repo: str, number: int) -> list[dict[str, Any]]:
        if self.down:
            raise CodeHostError("unreachable")
        return list(self.reviews.get((repo, number), []))

    def pull_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        if self.down:
            raise CodeHostError("unreachable")
        return list(self.review_comments.get((repo, number), []))

    def pull_commits(self, repo: str, number: int, after: str = "") -> list[dict[str, Any]]:
        """The commits given, with `files` emptied for each commit up to and including `after` (for all when `after`
        is empty or not among them); the sha of each commit after it is added to `files_asked`."""
        if self.down:
            raise CodeHostError("unreachable")
        given = [dict(c) for c in self.commits.get((repo, number), [])]
        cut = -1
        if after:
            for i, c in enumerate(given):
                sha = str(c.get("sha") or "")
                if sha and (sha.startswith(after) or after.startswith(sha)):
                    cut = i
                    break
        for i, c in enumerate(given):
            if cut >= 0 and i > cut:
                self.files_asked.append(str(c.get("sha") or ""))
            else:
                c["files"] = []
        return given

    def loop_issues(self, repo: str, state: str) -> list[dict[str, Any]]:
        """Issues in `state` with the loop's label; `fail_search` fails open reads, `fail_closed` closed ones."""
        if self.down:
            raise CodeHostError("unreachable")
        if state == "open" and self.fail_search:
            self.fail_search -= 1
            raise CodeHostError("search failed")
        if state == "closed" and self.fail_closed:
            self.fail_closed -= 1
            raise CodeHostError("closed search failed")
        return [{"number": i["number"], "url": i["url"], "body": i["body"], "state_reason": i.get("state_reason") or "",
                 "closed_at": i.get("closed_at") or "", "comments": self._count(repo, i["number"])}
                for i in self.issues if i["repo"] == repo and i["state"] == state
                and LOOP_LABEL in (i.get("labels") or [LOOP_LABEL])]

    def close(self, repo: str, number: int, reason: str, at: str) -> None:
        """Closes an issue with a reason (`not_planned`, `completed`, `duplicate` or empty) at an ISO time."""
        for i in self.issues:
            if i["repo"] == repo and i["number"] == number:
                i.update(state="closed", state_reason=reason, closed_at=at)

    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str:
        if self.down:
            raise CodeHostError("unreachable")
        n = len(self.issues) + 1
        self.issues.append({"repo": _check(repo), "number": n, "title": title, "body": body, "labels": labels,
                            "state": "open", "url": f"https://example.test/{repo}/issues/{n}"})
        return self.issues[-1]["url"]

    def comment(self, repo: str, number: int, body: str) -> str:
        if self.down:
            raise CodeHostError("unreachable")
        self.comments.append({"repo": repo, "number": number, "body": body})
        self.add_comment(repo, number, body, "other", "")
        return f"https://example.test/{repo}/issues/{number}#c{len(self.comments)}"

    def reopen(self, repo: str, number: int) -> None:
        if self.down:
            raise CodeHostError("unreachable")
        for i in self.issues:
            if i["repo"] == repo and i["number"] == number:
                i.update(state="open", state_reason=None, closed_at=None)

    def default_branch(self, repo: str) -> str:
        if self.down:
            raise CodeHostError("unreachable")
        return "main"

    def create_draft_pr(self, repo: str, head: str, base: str, title: str, body: str, labels: list[str]) -> str:
        if self.down:
            raise CodeHostError("unreachable")
        n = len(self.pulls) + 1
        self.pulls.append({"repo": _check(repo), "number": n, "head": _check_branch(head), "base": base,
                           "title": title, "body": body, "labels": labels, "draft": True, "state": "open"})
        return f"https://example.test/{repo}/pull/{n}"

    def pull_state(self, repo: str, number: int) -> dict[str, Any]:
        if self.down:
            raise CodeHostError("unreachable")
        for p in self.pulls:
            if p["repo"] == repo and p["number"] == number:
                return {"state": p["state"], "merged_at": p.get("merged_at")}
        raise CodeHostError("no such pull request")
