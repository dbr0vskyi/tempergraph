"""A read of a run's recorded pull request becomes a `later[]` entry (OUT-B23, OUT-B24, OUT-B25; FBK-B15).

The run's `run_segment` ledger row holds its pull request (FIN-B11). At a final exit the loop reads, through the code
host, each pull request of the workflow that no earlier read found merged or closed, and appends to the ledger one
`outcome_later` row per changed read: the pull request's state and counts of reviews by state, review comments,
follow-up commits and the files the run wrote that those commits changed. A row holds no text and counts only a
person's work. The text of reviews and review comments goes only to the run's local evidence folder,
`evidence/pull_request.jsonl`, scrubbed. A pull request that cannot be read is skipped. This module never imports
the filing code, and the filing code never imports it.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tempergraph.improve.codehost import CodeHostError
from tempergraph.run.log import Ledger
from tempergraph.security.scrub import clip, scrub
from tempergraph.store.layout import run_dir

DONE = ("merged", "closed")
MARKER = "<!-- tg-agent:"  # CONTRIBUTING.md: the hidden first line of every agent comment
TEXT_CHARS = 8000
SKIPPED = (CodeHostError, ValueError, KeyError, TypeError, AttributeError)


def _rows(root: Path) -> list[dict[str, Any]]:
    try:
        lines = (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for ln in lines:
        with contextlib.suppress(ValueError):
            r = json.loads(ln)
            if isinstance(r, dict):
                out.append(r)
    return out


def _task(thread: str) -> str:
    return thread.split("/", 1)[1] if "/" in thread else thread


def _valid(pr: Any) -> bool:
    return isinstance(pr, Mapping) and isinstance(pr.get("repo"), str) and isinstance(pr.get("number"), int)


def _last_entries(rows: list[dict[str, Any]], workflow: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("kind") == "outcome_later" and r.get("workflow") == workflow and isinstance(r.get("entry"), dict):
            out[str(r.get("thread_id"))] = r["entry"]
    return out


def pending(root: Path, workflow: str) -> list[dict[str, Any]]:
    """The latest recorded pull request of each thread of the workflow whose last `outcome_later` row is not
    `merged` or `closed`: `{thread_id, task, pull_request}`."""
    rows = _rows(root)
    last = _last_entries(rows, workflow)
    recorded: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("kind") == "run_segment" and r.get("workflow") == workflow and _valid(r.get("pull_request")):
            recorded[str(r.get("thread_id"))] = dict(r["pull_request"])
    return [{"thread_id": t, "task": _task(t), "pull_request": pr} for t, pr in recorded.items()
            if (last.get(t) or {}).get("state") not in DONE]


def _wrote(root: Path, workflow: str, task: str) -> set[str]:
    """The paths the run's sessions changed, from the `agent_run` records of its log."""
    try:
        lines = (run_dir(root, workflow, task) / "run.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    out: set[str] = set()
    for ln in lines:
        with contextlib.suppress(ValueError):
            r = json.loads(ln)
            if isinstance(r, dict) and r.get("kind") == "agent_run":
                out.update(str(p) for p in r.get("changed_paths") or ())
    return out


def _person_text(r: Mapping[str, Any]) -> bool:
    return r.get("author_kind") == "person" and not str(r.get("text") or "").lstrip().startswith(MARKER)


def _follow_ups(commits: list[dict[str, Any]], end: str) -> list[dict[str, Any]]:
    """The commits after the run's recorded end commit; none when no end commit is recorded or it is not among them."""
    if not end:
        return []
    for i, c in enumerate(commits):
        sha = str(c.get("sha") or "")
        if sha and (sha.startswith(end) or end.startswith(sha)):
            return commits[i + 1:]
    return []


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if os.name == "posix":
        os.chmod(path, 0o600)


def _evidence(root: Path, workflow: str, task: str, reviews: list[dict[str, Any]],
              comments: list[dict[str, Any]]) -> None:
    lines = [{"kind": "review", "state": r.get("state"), "text": clip(scrub(str(r.get("text") or "")), TEXT_CHARS)}
             for r in reviews if _person_text(r)]
    lines += [{"kind": "comment", "path": c.get("path"), "text": clip(scrub(str(c.get("text") or "")), TEXT_CHARS)}
              for c in comments if _person_text(c)]
    with contextlib.suppress(OSError):
        _write_private(run_dir(root, workflow, task) / "evidence" / "pull_request.jsonl",
                       "".join(json.dumps(ln, ensure_ascii=False) + "\n" for ln in lines))


def read(root: Path, workflow: str, host: Any) -> list[dict[str, Any]]:
    """Reads each pending pull request and appends an `outcome_later` row for each whose entry differs from its
    thread's last. Returns `{thread_id, task, pull_request, entry, changed}` for each appended entry, `changed`
    being the files the run wrote that a follow-up commit changed."""
    ledger = Ledger(path=root / "ledger.jsonl")
    last = _last_entries(_rows(root), workflow)
    out: list[dict[str, Any]] = []
    for item in pending(root, workflow):
        pr, thread, task = item["pull_request"], item["thread_id"], item["task"]
        repo, number = str(pr["repo"]), int(pr["number"])
        try:
            state = str(host.pull_state(repo, number)["state"])
            if state not in ("open", "merged", "closed"):
                continue
            reviews = list(host.pull_reviews(repo, number))
            comments = list(host.pull_comments(repo, number))
            commits = list(host.pull_commits(repo, number))
        except SKIPPED:
            continue
        mine = [r for r in reviews if _person_text(r)]
        follow = [c for c in _follow_ups(commits, str(pr.get("commit") or "")) if c.get("author_kind") == "person"]
        wrote = _wrote(root, workflow, task)
        changed = sorted({str(f) for c in follow for f in c.get("files") or () if str(f) in wrote})
        kinds: dict[str, int] = {}
        for r in mine:
            kinds[str(r.get("state"))] = kinds.get(str(r.get("state")), 0) + 1
        entry = {"state": state, "reviews": dict(sorted(kinds.items())),
                 "comments": sum(1 for c in comments if _person_text(c)), "commits": len(follow),
                 "files": len(changed)}
        _evidence(root, workflow, task, reviews, comments)
        if entry == last.get(thread):
            continue
        ledger.append({"kind": "outcome_later", "thread_id": thread, "workflow": workflow, "entry": entry})
        last[thread] = entry
        out.append({"thread_id": thread, "task": task, "pull_request": pr, "entry": entry, "changed": changed})
    return out
