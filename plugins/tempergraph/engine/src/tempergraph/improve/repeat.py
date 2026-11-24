"""A review category kept in several sessions of one unit, or in several runs, is a finding (SRV-B26, SRV-B27,
SRV-B28, SRV-B32).

Read from the runs' `review_done` records (category codes, session keys and check results only, never a note), so
the finding carries no note text. It is a candidate for nothing: the loop child never files it (SRV-B28), it goes
to the proposer alone, and the review readers use it only to mark the kept observations of its own category on its
own unit as corroborated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph.improve import causes as causemod
from tempergraph.improve import digest as digestmod
from tempergraph.improve import params
from tempergraph.improve.record import _jsonl, append_findings, fingerprint, read_findings
from tempergraph.store.layout import run_dir

PREFIX = "review_repeat:"
CARRIED = ("workflow", "workflow_version", "machine", "repo", "settings_digest", "overridden_keys", "request_digest")


def kept_sessions(root: Path, workflow: str, task_id: str) -> dict[tuple[str, str], list[str]]:
    """The distinct sessions, in review order, that kept each (unit, category) in the run."""
    out: dict[tuple[str, str], list[str]] = {}
    for r in _jsonl(run_dir(root, workflow, task_id) / "loop.jsonl"):
        if r.get("kind") != "review_done":
            continue
        key = str(r.get("session_key"))
        unit = digestmod.parse_key(key)[0]
        for o in r.get("observations") or []:
            if o.get("check") == "kept":
                sessions = out.setdefault((unit, str(o.get("category"))), [])
                if key not in sessions:
                    sessions.append(key)
    return out


def _weights(root: Path, workflow: str, task_id: str) -> dict[tuple[str, str], int]:
    """How many kept observations each (unit, category) has in the run."""
    out: dict[tuple[str, str], int] = {}
    for r in _jsonl(run_dir(root, workflow, task_id) / "loop.jsonl"):
        if r.get("kind") == "review_done":
            unit = digestmod.parse_key(str(r.get("session_key")))[0]
            for o in r.get("observations") or []:
                if o.get("check") == "kept":
                    k = (unit, str(o.get("category")))
                    out[k] = out.get(k, 0) + 1
    return out


def kept_runs(root: Path, workflow: str) -> dict[tuple[str, str], list[str]]:
    """The runs of the workflow, in directory order, whose reviews kept each (unit, category): a run counts once
    however many of its sessions kept the pair, and a rejected observation counts for nothing (SRV-B32)."""
    base = root / "runs" / workflow
    out: dict[tuple[str, str], list[str]] = {}
    for d in sorted(base.iterdir()) if base.is_dir() else ():
        for pair in kept_sessions(root, workflow, d.name):
            out.setdefault(pair, []).append(d.name)
    return out


def record(root: Path, workflow: str, task_id: str, thread: str) -> list[dict[str, Any]]:
    """Appends one `review_repeat:<category>` finding per unit and category kept in at least
    `review.repeat_sessions` distinct sessions of the run (SRV-B26) or in at least `review.repeat_runs` runs of the
    workflow, this run included (SRV-B32), and not yet recorded in the run; returns the new findings."""
    need = int(params.value("review.repeat_sessions"))
    need_runs = int(params.value("review.repeat_runs"))
    existing = read_findings(root, workflow, task_id)
    done = {(str(f.get("unit")), str(f.get("cause"))) for f in existing}
    weights = _weights(root, workflow, task_id)
    carried = {k: existing[0][k] for k in CARRIED if existing and k in existing[0]}
    at = datetime.now(UTC).isoformat(timespec="seconds")
    lines: list[dict[str, Any]] = []

    def add(unit: str, category: str, count: int, held: dict[str, Any], weight: int) -> None:
        cause = PREFIX + category
        c = causemod.cause_of(cause)
        done.add((unit, cause))
        lines.append({"kind": "finding", "thread": thread, "workflow": workflow, **carried, "segment_exit": None,
                      "unit": unit, "cause": cause, "class": c.klass, "side": c.side, "count": count,
                      "remedy": c.remedy, "fingerprint": fingerprint(c.side, workflow, cause, unit), "at": at,
                      "lens": "review", **held, "review": f"review:{category}", "review_weight": weight})

    mine = kept_sessions(root, workflow, task_id)
    for (unit, category), sessions in mine.items():
        if len(sessions) >= need and (unit, PREFIX + category) not in done:
            add(unit, category, len(sessions), {"sessions": list(sessions)},
                weights.get((unit, category), len(sessions)))
    across = kept_runs(root, workflow)
    for (unit, category) in mine:  # SRV-B32: only a pair this run's reviews kept can be recorded by this run
        runs = across.get((unit, category), [])
        if task_id in runs and len(runs) >= need_runs and (unit, PREFIX + category) not in done:
            add(unit, category, len(runs), {"runs": list(runs)}, weights.get((unit, category), 1))
    append_findings(root, workflow, task_id, thread, lines)
    return lines


def recorded(root: Path, workflow: str, task_id: str) -> dict[tuple[str, str], int]:
    """The (unit, category) pairs the run's findings hold as `review_repeat`, with their `review_weight`."""
    return {(str(f.get("unit")), str(f["review"]).removeprefix("review:")): int(f.get("review_weight") or 0)
            for f in read_findings(root, workflow, task_id)
            if str(f.get("cause") or "").startswith(PREFIX) and f.get("review")}


def repeated(root: Path, workflow: str) -> set[tuple[str, str]]:
    """The (unit, category) pairs recorded as `review_repeat` in any run of the workflow."""
    base = root / "runs" / workflow
    out: set[tuple[str, str]] = set()
    for d in sorted(base.iterdir()) if base.is_dir() else ():
        out |= set(recorded(root, workflow, d.name))
    return out
