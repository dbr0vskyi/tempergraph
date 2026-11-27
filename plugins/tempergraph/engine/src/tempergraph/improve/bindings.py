"""Bindings of a cause to an issue the loop did not open (BND-B1 to BND-B10).

A loop issue closed as a duplicate may hold a comment of a person that says `duplicate of #<n>`: `<n>` is the cause's
target. The binding is learned from the host's comments, kept in `filing-bindings.json` at the state root's top level
(numbers and times only, owner-only) and reused while the host still gives the same close time and comment count.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tempergraph.docs import write_json
from tempergraph.improve.codehost import CodeHostError, NotFound

FILE = "filing-bindings.json"
PATTERN = re.compile(r"(?<![A-Za-z])duplicate\s+of\s+#(\d+)(?!\w)", re.IGNORECASE)


@dataclass
class Binding:
    """`state` is `none` (nothing bound), `bound` or `unreadable` (a read failed twice); `learned` says the target
    came from the host and not from the record."""

    state: str
    number: int | None = None
    issue: dict[str, Any] = field(default_factory=dict)
    learned: bool = False


def target_of(text: str) -> int | None:
    """BND-B1: the first number written as `duplicate of #<n>`, in any letter case."""
    m = PATTERN.search(text)
    return int(m.group(1)) if m else None


def _twice(read: Callable[[], Any]) -> tuple[bool, Any]:
    """One retry (BND-B6). `(True, answer)`, or `(False, None)` after two failures; `NotFound` is not retried."""
    for _ in range(2):
        try:
            return True, read()
        except NotFound:
            raise
        except CodeHostError:
            continue
    return False, None


def _records(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _recorded(root: Path, repo: str, key: str) -> dict[str, Any] | None:
    by_repo = _records(root).get(repo)
    rec = by_repo.get(key) if isinstance(by_repo, dict) else None
    return rec if isinstance(rec, dict) else None


def _write(root: Path, repo: str, key: str, record: dict[str, Any]) -> None:
    data = _records(root)
    by_repo = data.get(repo)
    data[repo] = {**(by_repo if isinstance(by_repo, dict) else {}), key: record}
    try:
        write_json(root / FILE, data)
    except Exception:  # noqa: BLE001 - the record is a cache; a filing never stops for it (BND-B10)
        return


def _matches(rec: dict[str, Any] | None, source: dict[str, Any]) -> bool:
    """BND-B9: the record names this source with the close time and comment count the host now gives."""
    return (rec is not None and rec.get("source") == source.get("number")
            and rec.get("source_closed_at") == source.get("closed_at")
            and rec.get("source_comments") == source.get("comments") and isinstance(rec.get("target"), int))


def _target_issue(host: Any, repo: str, number: int, source: int) -> Binding:
    """BND-B2: the target must be another issue the host holds, and not a pull request."""
    if number == source:
        return Binding("none")
    try:
        ok, issue = _twice(lambda: host.issue(repo, number))
    except NotFound:
        return Binding("none")
    if not ok:
        return Binding("unreadable")
    if issue.get("is_pull_request"):
        return Binding("none")
    return Binding("bound", number, dict(issue))


def learn(host: Any, repo: str, key: str, source: dict[str, Any], root: Path, now: datetime) -> Binding:
    """BND-B1, BND-B2, BND-B6, BND-B8 to BND-B10: the binding of the cause whose closed issue is `source` (its
    `number`, `closed_at` and `comments` as the closed read gave them)."""
    if not (hasattr(host, "issue_comments") and hasattr(host, "issue")):
        return Binding("none")
    n = source.get("number")
    if not isinstance(n, int):
        return Binding("none")
    rec = _recorded(root, repo, key)
    if rec is not None and _matches(rec, source):
        got = _target_issue(host, repo, int(rec["target"]), n)
        return got
    try:
        ok, comments = _twice(lambda: host.issue_comments(repo, n))
    except NotFound:
        return Binding("none")
    if not ok:
        return Binding("unreadable")
    ordered: Sequence[dict[str, Any]] = sorted(comments, key=lambda c: str(c.get("created_at") or ""))
    target: int | None = None
    for c in reversed(ordered):
        if c.get("author_kind") != "person":
            continue
        target = target_of(str(c.get("text") or ""))
        if target is not None:
            break
    if target is None:
        return Binding("none")
    got = _target_issue(host, repo, target, n)
    if got.state != "bound":
        return got
    got.learned = True
    _write(root, repo, key, {"source": n, "target": target, "source_closed_at": str(source.get("closed_at") or ""),
                             "source_comments": source.get("comments")})
    return got


def opening_sentence(workflow: str, cause: str, units: Sequence[str], source: int) -> str:
    """BND-B4: the one sentence that opens a comment on a target, built from ids; it holds no `duplicate of #`."""
    where = ", ".join(f"`{u}`" for u in units) or "no recorded unit"
    return (f"This comment comes from tempergraph's improvement loop: it saw the cause `{cause}` of workflow "
            f"`{workflow}` again at {where}, and sends it here because the loop issue #{source} was closed as "
            f"a duplicate of this issue; reopening #{source} ends these comments.")
