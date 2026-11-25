"""An escape is a model-free finding (SIL-B10, SIL-B33, SIL-B34; OUT-B26).

When a read of a run's pull request makes the run an escape (a `met` run a person sent back), the loop records, with
no model call, one `outcome_escape` finding of the workflow's side for each unit that wrote a file a follow-up commit
changed, or for the `outcome` unit when none did, and a kept review observation of the same unit and run then
corroborates it (`review.corroborate`). The finding holds the cause code, the unit and the run's keys and request
digest, never text. It files by the pattern rule alone (`filing.decide`).
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph import identity
from tempergraph.improve import causes as causemod
from tempergraph.improve import digest as digestmod
from tempergraph.improve.record import append_findings, fingerprint, read_evidence, read_findings
from tempergraph.model import flow
from tempergraph.run import outcome_record
from tempergraph.store.layout import run_dir

CAUSE = "outcome_escape"
KEYS = ("workflow", "workflow_version", "machine", "repo", "settings_digest", "overridden_keys")


def _task(thread: str) -> str:
    return thread.split("/", 1)[1] if "/" in thread else thread


def _escaped(rows: Sequence[Mapping[str, Any]], workflow: str, thread: str) -> bool:
    latest = outcome_record._latest(rows, workflow)
    reruns = {str(r.get("thread_id")) for r in rows if r.get("kind") == "intervention" and r.get("cause") == "rerun"}
    return thread in outcome_record.escape_threads(latest, rows, reruns)


def _is_new(root: Path, workflow: str, thread: str) -> bool:
    """The run is an escape now and was none before the read: dropping the thread's last `outcome_later` row
    leaves it out of the escape set."""
    rows = outcome_record._jsonl(root / "ledger.jsonl")
    if not _escaped(rows, workflow, thread):
        return False
    at = max((i for i, r in enumerate(rows) if r.get("kind") == "outcome_later" and r.get("workflow") == workflow
              and str(r.get("thread_id")) == thread), default=None)
    if at is None:
        return False
    return not _escaped([r for i, r in enumerate(rows) if i != at], workflow, thread)


def _run_row(rows: Iterable[Mapping[str, Any]], workflow: str, thread: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in rows:
        if r.get("kind") == "run_segment" and r.get("workflow") == workflow and str(r.get("thread_id")) == thread:
            out = dict(r)
    return out


def _writers(root: Path, workflow: str, task: str, changed: Sequence[str]) -> list[str]:
    """The units whose sessions wrote one of the changed files: a changed file's digest in a session digest's `_wrote`."""
    want = {identity.request_digest(p) or "" for p in changed} - {""}
    keys: list[str] = []
    with contextlib.suppress(OSError):
        for ln in (run_dir(root, workflow, task) / "run.jsonl").read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(ValueError):
                r = json.loads(ln)
                if isinstance(r, dict) and r.get("kind") == "agent_run" and r.get("session_key"):
                    keys.append(str(r["session_key"]))
    units: set[str] = set()
    for key in dict.fromkeys(keys):
        d = digestmod.read(root, workflow, task, key)
        if d is not None and d.get("kind") in digestmod.STEP_KINDS and want & set(d.get("_wrote") or ()):
            units.add(str(d.get("unit") or digestmod.parse_key(key)[0]))
    return sorted(units)


def _request_digest(root: Path, workflow: str, task: str) -> str | None:
    for f in read_findings(root, workflow, task):
        if f.get("request_digest"):
            return str(f["request_digest"])
    req = str((read_evidence(root, workflow, task).get("request") or {}).get("request") or "")
    return identity.request_digest(req) if req else None


def record(root: Path, workflow: str, thread: str, changed_written: Sequence[str]) -> list[dict[str, Any]]:
    """The new `outcome_escape` finding lines for the run of `thread`, appended to its findings; none when the read
    did not make the run an escape or each unit already holds one. `changed_written` is the files the run wrote that
    a follow-up commit changed (the `changed` of a `pr_later.read` result). Calls `review.corroborate` for the run."""
    if not _is_new(root, workflow, thread):
        return []
    task = _task(thread)
    row = _run_row(outcome_record._jsonl(root / "ledger.jsonl"), workflow, thread)
    units = _writers(root, workflow, task, changed_written) or [flow.OUTCOME_UNIT]
    held = {str(f.get("unit")) for f in read_findings(root, workflow, task) if f.get("cause") == CAUSE}
    c = causemod.cause_of(CAUSE)
    digest = _request_digest(root, workflow, task)
    at = datetime.now(UTC).isoformat(timespec="seconds")
    lines = [{"kind": "finding", "thread": thread, **{k: row.get(k) for k in KEYS}, "segment_exit": row.get("exit_code"),
              "unit": u, "cause": CAUSE, "class": c.klass, "side": c.side, "count": 1, "remedy": c.remedy,
              "fingerprint": fingerprint(c.side, workflow, CAUSE, u), "at": at, "request_digest": digest,
              "lens": "outcome"} for u in units if u not in held]
    if not lines:
        return []
    append_findings(root, workflow, task, thread, lines)
    from tempergraph.improve import review

    review.corroborate(root, workflow, task, thread)
    return [f for f in read_findings(root, workflow, task) if f.get("cause") == CAUSE
            and f.get("fingerprint") in {x["fingerprint"] for x in lines}]
