"""The post-release comparison of a merged proposal and the regression record (PRP-B9, PRP-B29).

When the first `trial.after_release_runs` real final exits after a proposal's merge exist, the exits of the
proposal's `base_version` before the merge are compared with them (`measure.compare_windows`) and the proposal
holds `regressed_after_release` or `held_after_release`, once. A regression reopens the cluster's issues that are
in the pull request's repository; a host that cannot be reached leaves the reopen in the outbox (SIL-B19).
`measure.py` imports no writer (a source test enforces it), so the writes live here. Model-free.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph.improve import filing, measure, params, promotion
from tempergraph.improve import proposals as prp
from tempergraph.improve.codehost import CodeHost, CodeHostError
from tempergraph.store.layout import now_iso


def _dry(root: Path, workflow: str, thread: str) -> bool:
    task = thread.split("/", 1)[-1]
    return any(r.get("kind") == "run_started" and r.get("dry_run")
               for r in prp._jsonl(root / "runs" / workflow / task / "run.jsonl"))


def real_exits(root: Path, workflow: str) -> list[dict[str, Any]]:
    """The workflow's final `run_segment` rows (exit 0, 4 or 5), oldest first, leaving out the runs PRO-B8 leaves
    out: trial, scenario and eval origins, a child's records from inside a parent and dry runs."""
    out = []
    for r in prp._jsonl(root / "ledger.jsonl"):
        origin = str(r.get("origin") or "")
        if r.get("kind") != "run_segment" or r.get("workflow") != workflow \
                or r.get("exit_code") not in promotion.FINAL_EXITS or prp._ts(r.get("ts")) is None \
                or origin in promotion.EXCLUDED_ORIGINS or origin.startswith(promotion.CHILD_ORIGIN) \
                or _dry(root, workflow, str(r.get("thread_id") or "")):
            continue
        out.append(r)
    return sorted(out, key=lambda r: prp._ts(r.get("ts")) or datetime.min.replace(tzinfo=UTC))


def _reopen(rec: Mapping[str, Any], host: CodeHost, outbox: filing.Outbox) -> None:
    """PRP-B29: the cluster's issues of the pull request's repository, open again; the ones the host cannot take
    wait in the outbox."""
    ref = prp.pull_ref(rec.get("pull_request"))
    if ref is None:
        return
    done: set[int] = set()
    for url in (rec.get("cluster") or {}).get("issues") or []:
        issue = prp.issue_ref(url)
        if issue is None or issue[0] != ref[1] or issue[1] in done:
            continue
        done.add(issue[1])
        try:
            host.reopen(issue[0], issue[1])
        except CodeHostError:
            outbox.add({"op": "reopen", "repo": issue[0], "number": issue[1]})


def compare_due(root: Path, workflow: str, host: CodeHost, outbox: filing.Outbox) -> list[dict[str, Any]]:
    """PRP-B9: compares each merged proposal of the workflow that holds no release record and has its first
    `trial.after_release_runs` real exits after the merge; returns one outcome per proposal compared."""
    need = int(params.value("trial.after_release_runs"))
    exits: list[dict[str, Any]] | None = None
    out: list[dict[str, Any]] = []
    for rec in prp._saved(root, workflow):
        merged_at = prp._ts(rec.get("merged_at"))
        if rec.get("state") != "merged" or merged_at is None \
                or rec.get("regressed_after_release") or rec.get("held_after_release"):
            continue
        exits = real_exits(root, workflow) if exits is None else exits
        after = [r for r in exits if (prp._ts(r["ts"]) or merged_at) > merged_at][:need]
        if len(after) < need:
            continue
        before = [r for r in exits if r.get("workflow_version") == rec.get("base_version")
                  and (prp._ts(r["ts"]) or merged_at) <= merged_at]
        cmp = measure.compare_windows(root, workflow, before, after)
        entry = {"before": cmp["before"], "after": cmp["after"], "at": now_iso()}
        if cmp["regressed"]:
            rec["regressed_after_release"] = {**entry, "worse": cmp["worse"]}
        else:
            rec["held_after_release"] = entry
        prp.save(root, rec)
        if cmp["regressed"]:
            _reopen(rec, host, outbox)
        out.append({"proposal_id": str(rec["proposal_id"]), "result": "regressed" if cmp["regressed"] else "held"})
    return out
