"""An escape is a model-free finding (SIL-B10, SIL-B33, SIL-B34; OUT-B26).

At each read of a run's pull request that shows the run to be an escape (a `met` run a person sent back; a rerun
alone does not count), the loop records, with no model call and for each unit that holds none, one `outcome_escape` finding of the workflow's side for each unit that wrote a file a follow-up commit
changed, or for the `outcome` unit when none did, and a kept review observation of the same unit and run then
corroborates it (`review.corroborate`). The finding holds the cause code, the unit and the run's keys and request
digest, never text. The unit that wrote a file is the unit of a step or retry session whose `agent_run` record lists
the file in `wrote_paths` (the files that differ from the commit the session started from, committed or not); a
judge session's `changed_paths` names no writer. It files by the pattern rule alone (`filing.decide`).
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
from tempergraph.improve.record import append_findings, fingerprint, read_evidence, read_findings
from tempergraph.model import flow
from tempergraph.run import outcome_record
from tempergraph.store.layout import run_dir

CAUSE = "outcome_escape"
KEYS = ("workflow", "workflow_version", "machine", "repo", "settings_digest", "overridden_keys")


def _task(thread: str) -> str:
    return thread.split("/", 1)[1] if "/" in thread else thread


def _shown(root: Path, workflow: str, thread: str) -> bool:
    """The pull request has shown the run to be an escape (OUT-B26): a rerun alone does not count."""
    rows = outcome_record._jsonl(root / "ledger.jsonl")
    return thread in outcome_record.escape_threads(outcome_record._latest(rows, workflow), rows, set())


def _run_row(rows: Iterable[Mapping[str, Any]], workflow: str, thread: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in rows:
        if r.get("kind") == "run_segment" and r.get("workflow") == workflow and str(r.get("thread_id")) == thread:
            out = dict(r)
    return out


def _writers(root: Path, workflow: str, task: str, changed: Sequence[str]) -> list[str]:
    """SIL-B33: the units whose step or retry sessions wrote one of the changed files: a changed path in the
    `wrote_paths` of the session's `agent_run` record in the run log."""
    want = {str(p) for p in changed}
    units: set[str] = set()
    with contextlib.suppress(OSError):
        for ln in (run_dir(root, workflow, task) / "run.jsonl").read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(ValueError):
                r = json.loads(ln)
                if (isinstance(r, dict) and r.get("kind") == "agent_run" and r.get("unit")
                        and r.get("session_kind") in ("step", "retry")
                        and want & {str(p) for p in r.get("wrote_paths") or ()}):
                    units.add(str(r["unit"]))
    return sorted(units)


def _request_digest(root: Path, workflow: str, task: str) -> str | None:
    for f in read_findings(root, workflow, task):
        if f.get("request_digest"):
            return str(f["request_digest"])
    req = str((read_evidence(root, workflow, task).get("request") or {}).get("request") or "")
    return identity.request_digest(req) if req else None


def record(root: Path, workflow: str, thread: str, changed_written: Sequence[str]) -> list[dict[str, Any]]:
    """The new `outcome_escape` finding lines for the run of `thread`, appended to its findings, one for each unit
    that wrote a changed file (or the `outcome` unit when none did) and holds none yet; none when the pull request
    has not shown the run to be an escape or each unit already holds one. Run for every read result, so the finding
    follows the state. `changed_written` is the files the run wrote that a follow-up commit changed (the `changed` of
    a `pr_later.read` result). Calls `review.corroborate` for the run."""
    if not _shown(root, workflow, thread):
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
