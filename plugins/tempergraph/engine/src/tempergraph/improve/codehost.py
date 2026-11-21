"""The code host client for filing (ADR-0090 S5): GitHub through the person's own `gh` sign-in.

A sanctioned launch site (SEC §2.2): constant subcommands as list argv, the repository checked as
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


class CodeHostError(Exception):
    pass


class CodeHost(Protocol):
    def search(self, repo: str, marker: str) -> list[dict[str, Any]]: ...
    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str: ...
    def comment(self, repo: str, number: int, body: str) -> str: ...
    def reopen(self, repo: str, number: int) -> None: ...


class PullRequestHost(Protocol):
    """Draft pull requests for proposals (PRP-B8). There is no merge method, by design (PRP-AC-2)."""

    def default_branch(self, repo: str) -> str: ...
    def create_draft_pr(self, repo: str, head: str, base: str, title: str, body: str, labels: list[str]) -> str: ...


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
        exe = shutil.which("gh")
        if exe is None:
            raise CodeHostError("gh is not installed")
        try:
            proc = subprocess.run(  # noqa: S603 - constant subcommands, text on stdin (SEC §2.2)
                [exe, *args], input=json.dumps(payload) if payload is not None else None, capture_output=True,
                text=True, timeout=self.timeout_s)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CodeHostError(type(exc).__name__) from None
        if proc.returncode != 0:
            raise CodeHostError(f"gh exited {proc.returncode}")
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def search(self, repo: str, marker: str) -> list[dict[str, Any]]:
        if not re.match(r"^[a-z0-9:=<>!\- ]{1,80}$", marker):
            raise CodeHostError("marker is not a constant shape")
        got = self._gh(["issue", "list", "--repo", _check(repo), "--state", "open", "--limit", "50",
                        "--json", "number,body,url", "--search", f"\"{marker}\" in:body"])
        return list(got or [])

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


@dataclass(kw_only=True)
class MemoryCodeHost:
    """A code host in memory, for tests and dry runs."""

    issues: list[dict[str, Any]] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)
    pulls: list[dict[str, Any]] = field(default_factory=list)
    fail_search: int = 0
    down: bool = False

    def search(self, repo: str, marker: str) -> list[dict[str, Any]]:
        if self.down:
            raise CodeHostError("unreachable")
        if self.fail_search:
            self.fail_search -= 1
            raise CodeHostError("search failed")
        return [i for i in self.issues if i["repo"] == repo and i["state"] == "open" and marker in i["body"]]

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
        for i in self.issues:
            if i["repo"] == repo and i["number"] == number:
                i["state"] = "open"

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
