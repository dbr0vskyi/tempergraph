"""The code host client for filing (ADR-0090 S5): GitHub through the person's own `gh` sign-in.

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

REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
LOOP_LABEL = "tempergraph-loop"  # the label every loop issue carries (ISS-B1); its list read (ISS-B9) filters on it


class CodeHostError(Exception):
    pass


class CodeHost(Protocol):
    def loop_issues(self, repo: str, state: str) -> list[dict[str, Any]]: ...
    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str: ...
    def comment(self, repo: str, number: int, body: str) -> str: ...
    def reopen(self, repo: str, number: int) -> None: ...


class PullRequestHost(Protocol):
    """Draft pull requests for proposals (PRP-B8). There is no merge method, by design (PRP-AC2)."""

    def default_branch(self, repo: str) -> str: ...
    def create_draft_pr(self, repo: str, head: str, base: str, title: str, body: str, labels: list[str]) -> str: ...
    def pull_state(self, repo: str, number: int) -> dict[str, Any]: ...


BRANCH = re.compile(r"^(improve/[A-Za-z0-9_.-]{1,80}|tempergraph/upgrade/[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,40})$")


def _check_branch(head: str) -> str:
    if not BRANCH.match(head):
        raise CodeHostError(f"branch {head!r} is not an improve/<proposal> or upgrade branch")
    return head


def _check(repo: str) -> str:
    if not REPO.match(repo):
        raise CodeHostError(f"repository {repo!r} is not owner/name")
    return repo


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
                        "created_at": r.get("created_at") or ""})
        return out

    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str:
        got = self._gh(["api", f"repos/{_check(repo)}/issues", "--method", "POST", "--input", "-"],
                       {"title": title, "body": body, "labels": labels})
        return str((got or {}).get("html_url") or "")

    def comment(self, repo: str, number: int, body: str) -> str:
        got = self._gh(["api", f"repos/{_check(repo)}/issues/{int(number)}/comments", "--method", "POST",
                        "--input", "-"], {"body": body})
        return str((got or {}).get("html_url") or "")

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
    fail_search: int = 0
    fail_closed: int = 0
    down: bool = False

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
                 "closed_at": i.get("closed_at") or ""}
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
