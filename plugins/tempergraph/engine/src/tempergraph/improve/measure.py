"""Measurement of a shipped fix: two workflow versions compared, model-free (SIL-B5, OVR-B16).

It writes no file, ledger row or code and launches nothing; its only writes go through the code host given to
it: one comment, and before it one reopen when quality fell (more than `measure.quality_drop` points).
It reads the ledger and run logs as plain text and imports no writer (a source test enforces it).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tempergraph.improve import params
from tempergraph.improve.codehost import CodeHost

QUALITY_DROP = params.value("measure.quality_drop")  # provenance default_no_data (5 points, from earlier runs)


def _rows(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def _cost(row: Mapping[str, Any]) -> float:
    c = row.get("cost") or {}
    return float(c.get("reported") or 0.0) + float(c.get("estimated_only") or 0.0)


def figures(root: Path, workflow: str, version: str) -> dict[str, Any]:
    segs = [r for r in _rows(root / "ledger.jsonl") if r.get("kind") == "run_segment"
            and r.get("workflow") == workflow and r.get("workflow_version") == version]
    threads: dict[str, list[dict[str, Any]]] = {}
    for r in segs:
        threads.setdefault(str(r.get("thread_id")), []).append(r)
    n = len(threads)
    cost = sum(_cost(r) for r in segs)
    gates = passes = retries = sessions = 0
    for tid in threads:
        task = tid.split("/", 1)[1]
        for r in _rows(root / "runs" / workflow / task / "run.jsonl"):
            if r.get("kind") == "gate":
                gates += 1
                passes += r.get("token") == "PROCEED"
            elif r.get("kind") == "agent_run":
                sessions += 1
                retries += r.get("session_kind") == "retry"
    outcomes: dict[str, int] = {}
    for rows in threads.values():
        o = (rows[-1].get("outcome") or {}).get("verdict")
        if o:
            outcomes[o] = outcomes.get(o, 0) + 1
    graded = sum(v for k, v in outcomes.items() if k != "not_reached")
    met = outcomes.get("met", 0) + outcomes.get("met_with_open", 0)
    return {"version": version, "runs": n, "cost_per_run": round(cost / n, 4) if n else None,
            "repeat_share": round(retries / sessions, 3) if sessions else None,
            "gate_pass_rate": round(passes / gates, 3) if gates else None,
            "outcome_met_share": round(met / graded, 3) if graded else None, "outcomes": outcomes}


def compare(root: Path, workflow: str, before: str, after: str) -> dict[str, Any]:
    a, b = figures(root, workflow, before), figures(root, workflow, after)
    drops = [k for k in ("gate_pass_rate", "outcome_met_share")
             if a[k] is not None and b[k] is not None and a[k] - b[k] > QUALITY_DROP]
    saved = (a["cost_per_run"] - b["cost_per_run"]) if a["cost_per_run"] is not None and b["cost_per_run"] is not None \
        else None
    return {"workflow": workflow, "before": a, "after": b, "saved_per_run": round(saved, 4) if saved is not None
            else None, "regressed": bool(drops), "dropped": drops,
            "param": {"name": "measure.quality_drop", "value": QUALITY_DROP, "provenance": "default_no_data"}}


def report(cmp: Mapping[str, Any], host: CodeHost, repo: str, issue: int) -> dict[str, Any]:
    """The only writes: a reopen first when quality fell, then one comment (SIL-B5)."""
    a, b = cmp["before"], cmp["after"]
    if cmp["regressed"]:
        host.reopen(repo, issue)
    saved = cmp["saved_per_run"]
    lines = [f"Measured `{cmp['workflow']}` {a['version']} ({a['runs']} runs) against {b['version']} ({b['runs']} runs).",
             f"Cost per run {a['cost_per_run']} -> {b['cost_per_run']}" + (f" (saved {saved})." if saved else "."),
             f"Gate pass rate {a['gate_pass_rate']} -> {b['gate_pass_rate']}; outcome met share "
             f"{a['outcome_met_share']} -> {b['outcome_met_share']}.",
             "Quality fell on " + ", ".join(cmp["dropped"]) + "; reopened." if cmp["regressed"] else "Quality held."]
    url = host.comment(repo, issue, "\n".join(lines))
    return {"comment": url, "reopened": bool(cmp["regressed"])}
