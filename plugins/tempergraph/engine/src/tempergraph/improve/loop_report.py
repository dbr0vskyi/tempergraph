"""`report --loop`: the loop's own figures over a window, per workflow (IMD-B22; plan T12.8).

Read-only and model-free, from this state root: findings, the `loop.jsonl` records of each thread, the ledger's
`loop` rows, and the proposal and trial records. Release 1 reads no issue or pull request state from the code
host, so issue precision, time to fix, held after release and estimated saving print as not derived, with the
reason, never as zero (IMD-B22). Every parameter that decides a figure is printed with its provenance (IMD-B23).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from tempergraph.improve import params

NOT_DERIVED = "issue and pull request states are not read from the code host in release 1"
FIGURE_PARAMS = ("cost.window_days", "proposals.label_value", "stable.daily_cap_usd", "trial.cap_usd",
                 "trial.monthly_cap_usd", "reliability.min_labels")


def _jsonl(path: Path) -> list[dict[str, Any]]:
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


def _docs(folder: Path) -> list[dict[str, Any]]:
    out = []
    for p in sorted(folder.glob("*.json")) if folder.is_dir() else ():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def _in(ts: Any, since: datetime | None) -> bool:
    return since is None or str(ts or "") >= since.isoformat()


def _spend(doc: Mapping[str, Any]) -> tuple[float, float]:
    s = doc.get("spend") or {}
    if "total" in s:
        return 0.0, float(s.get("total") or 0)  # a trial's total mixes both; shown as estimated
    return float(s.get("reported") or 0), float(s.get("estimated") or 0)


def workflow_figures(root: Path, workflow: str, since: datetime | None) -> dict[str, Any]:
    from tempergraph.improve import proposals as prp
    from tempergraph.improve.record import read_findings

    base = root / "runs" / workflow
    findings: list[dict[str, Any]] = []
    loop: list[dict[str, Any]] = []
    for d in sorted(base.iterdir()) if base.is_dir() else ():
        findings += [f for f in read_findings(root, workflow, d.name) if _in(f.get("at"), since)]
        loop += [r for r in _jsonl(d / "loop.jsonl") if _in(r.get("ts"), since)]
    props = [p for p in _docs(root / "improve" / "proposals") if p.get("workflow") == workflow and _in(p.get("at"), since)]
    trials = [t for t in _docs(root / "improve" / "trials") if t.get("workflow") == workflow and _in(t.get("at"), since)]
    rows = [r for r in _jsonl(root / "ledger.jsonl") if r.get("kind") == "loop" and r.get("workflow") == workflow
            and _in(r.get("ts"), since)]
    spend = {"children": {"reported": 0.0, "estimated": 0.0}, "proposer": {"reported": 0.0, "estimated": 0.0},
             "trials": {"reported": 0.0, "estimated": 0.0}}
    for r in rows:
        c = r.get("cost") or {}
        spend["children"]["reported"] += float(c.get("reported") or 0)
        spend["children"]["estimated"] += float(c.get("estimated_only") or 0)
    for key, docs in (("proposer", props), ("trials", trials)):
        for doc in docs:
            rep, est = _spend(doc)
            spend[key]["reported"] += rep
            spend[key]["estimated"] += est
    for v in spend.values():
        v["reported"], v["estimated"] = round(v["reported"], 4), round(v["estimated"], 4)
    funnel = {"findings": len(findings), "clusters": len(prp.clusters(root, workflow)),
              "issues_filed": sum(1 for r in loop if r.get("kind") == "issue_filed"),
              "issues_commented": sum(1 for r in loop if r.get("kind") == "issue_commented"),
              "proposals": len(props), "by_loop": sum(1 for p in props if p.get("author") == "loop"),
              "trials": len(trials), "shown_better": sum(1 for t in trials if t.get("decision") == "shown_better"),
              "opened": sum(1 for p in props if p.get("state") in ("opened", "merged", "closed")), "merged": None,
              "held_after_release": None}
    return {"workflow": workflow, "funnel": funnel,
            "issue_precision": {"value": None, "not_derived": NOT_DERIVED},
            "time_to_fix_days": {"value": None, "not_derived": NOT_DERIVED},
            "held_after_release": {"value": None, "not_derived": NOT_DERIVED},
            "estimated_saving": {"value": None, "not_derived": NOT_DERIVED},
            "loop_spend": spend,
            "reviews": sum(1 for r in loop if r.get("kind") == "review_done"),
            "skipped_daily_cap": sum(1 for r in loop if r.get("kind") == "loop_skipped"
                                     and r.get("reason") == "daily_cap")}


def report(root: Path, workflows: Sequence[str], since: datetime | None,
           coverage: Callable[[str], Sequence[str]] | None = None) -> dict[str, Any]:
    """Every figure of IMD-B22 per workflow; `coverage(workflow)` gives each judged gate's reliability grade."""
    out = []
    for w in workflows:
        fig = workflow_figures(root, w, since)
        grades = list(coverage(w)) if coverage is not None else []
        fig["label_coverage"] = {g: round(grades.count(g) / len(grades), 3) for g in
                                 ("reliable", "unmeasured", "unreliable")} if grades else None
        out.append(fig)
    return {"schema_version": 1, "since": since.isoformat() if since else None, "workflows": out,
            "params": [params.PARAMS[k].to_json() for k in FIGURE_PARAMS if k in params.PARAMS]}


def text(doc: Mapping[str, Any]) -> str:
    lines = [f"loop report since {doc.get('since') or 'the start'}"]
    for w in doc["workflows"]:
        f = w["funnel"]
        lines.append(f"{w['workflow']}: findings {f['findings']} → clusters {f['clusters']} → issues {f['issues_filed']} "
                     f"(+{f['issues_commented']} comments) → proposals {f['proposals']} ({f['by_loop']} by the loop) → "
                     f"trials {f['trials']} → shown better {f['shown_better']} → opened {f['opened']} → merged n/a")
        s = w["loop_spend"]
        lines.append("  spend: " + ", ".join(f"{k} ${v['reported']:.2f} reported, ${v['estimated']:.2f} estimated"
                                             for k, v in s.items()))
        cov = w.get("label_coverage")
        lines.append("  label coverage: " + (", ".join(f"{k} {v:.0%}" for k, v in cov.items()) if cov else "no gates"))
        lines.append(f"  reviews {w['reviews']}, days capped {w['skipped_daily_cap']}; precision, time to fix, held "
                     f"after release, saving: not derived ({NOT_DERIVED})")
    for p in doc["params"]:
        lines.append(f"  param {p['name']} = {p['value']} ({p['provenance']}, {p['source']})")
    return "\n".join(lines) + "\n"
