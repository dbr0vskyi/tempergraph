"""Which lenses fire at a final exit, and the model-free cost rules and gate scorecard (SIL-B10).

Friction and outcome need a judge in the loop child (T12.1.5); this module only decides that they fire, from
records. The cost lens is model-free here: fixed rules over a window of one workflow version.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec
from tempergraph.improve import causes as causemod
from tempergraph.improve import params
from tempergraph.model import flow
from tempergraph.store.layout import run_dir

STABLE_FRICTION = ("tool_access", "grant_missing", "retries_spent", "loop_budget_spent", "check_fail",
                   "gap_escalation", "retry_burst", "pushback", "agent_decided", "blocked_without_check")
LARGE = frozenset({"large", "opus"})


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


def _cost(row: Mapping[str, Any]) -> float:
    c = row.get("cost") or {}
    return float(c.get("reported") or 0.0) + float(c.get("estimated_only") or 0.0)


def _final_rows(root: Path, workflow: str, version: str | None) -> list[dict[str, Any]]:
    return [r for r in _jsonl(root / "ledger.jsonl") if r.get("kind") == "run_segment"
            and r.get("workflow") == workflow and r.get("workflow_version") == version
            and int(r.get("exit_code") or 0) in (0, 4, 5)]


def decide(spec: WorkflowSpec, root: Path, thread: str, findings: Sequence[Mapping[str, Any]],
           row: Mapping[str, Any], seg: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """SIL-B10 triggers for this final exit, in the workflow's improvement mode.

    `findings` are the segment's own findings and, at a person's stop of a paused thread, the unjudged findings
    of the thread's earlier pauses (SIL-B25): a fault among them turns the friction lens on.
    """
    mode = spec.improvement_mode
    faults = [f for f in findings if f.get("class") == "fault"]
    bases = {str(f["cause"]).split(":", 1)[0] for f in faults}
    finals = _final_rows(root, spec.name, row.get("workflow_version"))
    n = len(finals)
    out: dict[str, Any] = {"mode": mode}
    if mode == "dev":
        friction = bool(faults)
    else:
        costs = [_cost(r) for r in finals[:-1]]
        p90 = statistics.quantiles(costs, n=10)[-1] if len(costs) >= 10 else None
        friction = bool(bases & set(STABLE_FRICTION)) or n <= int(params.value("stable.new_version_runs")) or (
            p90 is not None and _cost(row) > p90)
    out["friction"] = friction
    orec = row.get("outcome")
    if orec is not None:
        reached = orec.get("verdict") != "not_reached"
        conf = next((float(r.get("confidence") or 0) for r in reversed(seg) if r.get("kind") == "judgement"
                     and r.get("unit") == flow.OUTCOME_UNIT), None)
        if mode == "dev":
            fire = True
        else:
            low = conf is not None and conf <= params.value("outcome.low_confidence") and orec.get("verdict") == "met"
            clean = not faults
            fire = "pushback" in bases or low or (clean and n % int(params.value("outcome.audit_every")) == 0)
        judged = any(c.get("class") == "judge" and c.get("status") not in ("not_judged",)
                     for c in orec.get("criteria", []))
        out["outcome"] = {"fire": fire, "needs_judge": fire and (not reached or not judged)}
    else:
        out["outcome"] = {"fire": False, "needs_judge": False}
    out["cost"] = n > 0 and n % int(params.value("cost.every_n_exits")) == 0
    out["quality"] = scorecard(seg)
    return out


def scorecard(seg: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per gate: visits, attempts, first-try passes and blocker counts; reported only until a binding is reliable."""
    out: dict[str, dict[str, Any]] = {}
    tries: dict[str, int] = {}
    for r in seg:
        unit = str(r.get("unit") or "")
        if r.get("kind") == "unit_entered":
            tries[unit] = 0
            out.setdefault(unit, {"visits": 0, "attempts": 0, "first_try_pass": 0, "blockers": 0})["visits"] += 1
        elif r.get("kind") == "gate" and unit in out:
            tries[unit] = tries.get(unit, 0) + 1
            out[unit]["attempts"] += 1
            if r.get("token") == "PROCEED" and tries[unit] == 1:
                out[unit]["first_try_pass"] += 1
        elif r.get("kind") == "judgement" and unit in out:
            out[unit]["blockers"] += len(r.get("blockers") or [])
    for v in out.values():
        v["filing"] = "report_only"  # FBK-B5: a gate files only while its judge binding is `reliable`
    return out


def _sessions(root: Path, workflow: str, thread: str) -> list[dict[str, Any]]:
    task = thread.split("/", 1)[1] if "/" in thread else thread
    return _jsonl(run_dir(root, workflow, task) / "run.jsonl")


def _usage_cost(r: Mapping[str, Any]) -> float | None:
    u = r.get("usage") or {}
    rep, est = u.get("reported_cost_usd"), u.get("estimated_cost_usd")
    return float(rep) if rep is not None else float(est) if est is not None else None


def cost_rules(spec: WorkflowSpec, root: Path, version: str | None, now: datetime | None = None) -> dict[str, Any]:
    """The model-free cost lens over a 30-day window of one version (SIL-B10, release 1 rule set)."""
    now = now or datetime.now(UTC)
    days = int(params.value("cost.window_days"))
    since = (now - timedelta(days=days)).isoformat()
    rows = [r for r in _final_rows(root, spec.name, version) if str(r.get("ts") or "") >= since]
    threads = list(dict.fromkeys(str(r.get("thread_id")) for r in rows))
    base = {"workflow": spec.name, "version": version, "window_days": days, "runs": len(threads),
            "params": [params.PARAMS[k].to_json() for k in ("cost.window_days", "cost.min_runs", "cost.repeat_share",
                                                             "cost.min_monthly_usd", "cost.max_lever_share")]}
    if len(threads) < int(params.value("cost.min_runs")):
        return {**base, "status": "thin", "findings": []}
    per: dict[str, dict[str, float]] = {}
    blockers: dict[str, set[str]] = {}
    unpriced: dict[str, int] = {}
    large: dict[str, bool] = {}
    blocked_units: set[str] = set()
    for t in threads:
        last_check_fail: dict[str, bool] = {}
        for r in _sessions(root, spec.name, t):
            unit = str(r.get("unit") or str(r.get("session_key") or "").split(".", 1)[0])
            if r.get("kind") == "check":
                last_check_fail[unit] = r.get("result") == "FAIL"
            elif r.get("kind") == "judgement":
                for cid in r.get("blockers") or ():
                    blockers.setdefault(f"{unit}:{cid}", set()).add(t)
                    blocked_units.add(unit)
            elif r.get("kind") == "agent_run":
                c = _usage_cost(r)
                k = str(r.get("session_kind") or "step")
                p = per.setdefault(unit, {"step": 0.0, "retry": 0.0, "judge": 0.0, "retry_after_check": 0.0})
                if c is None:
                    unpriced[unit] = unpriced.get(unit, 0) + 1
                    continue
                if k.startswith("judge"):
                    p["judge"] += c
                elif k == "retry":
                    p["retry"] += c
                    if last_check_fail.get(unit):
                        p["retry_after_check"] += c
                else:
                    p["step"] += c
                    if str(r.get("alias") or "").lower() in LARGE:
                        large[unit] = True
    scale = 30 / days
    lever = params.value("cost.max_lever_share")
    floor = params.value("cost.min_monthly_usd")
    found: list[dict[str, Any]] = []

    def add(rule: str, unit: str, usd: float, **extra: Any) -> None:
        saving = round(usd * lever * scale, 2)
        found.append({"rule": rule, "unit": unit, "monthly_saving_usd": saving, "filed": saving >= floor,
                      "basis": "reported, else estimated", **extra})

    for unit, p in per.items():
        total = p["step"] + p["retry"] + p["judge"]
        if total and p["retry"] / total >= params.value("cost.repeat_share"):
            add("repeat_share", unit, p["retry"], share=round(p["retry"] / total, 3))
        if p["retry_after_check"]:
            add("retry_after_check", unit, p["retry_after_check"])
        if p["judge"] > p["step"] + p["retry"] > 0:
            add("judge_over_step", unit, p["judge"] - p["step"] - p["retry"])
        if large.get(unit) and unit not in blocked_units:
            add("expensive_unblocked", unit, p["step"])
    for key, ts in blockers.items():
        if len(ts) >= 3:
            unit, cid = key.split(":", 1)
            p = per.get(unit) or {}
            add("recurring_blocker", unit, float(p.get("retry", 0.0)), criterion=cid, runs=len(ts))
    for unit, n_unpriced in unpriced.items():
        found.append({"rule": "unpriced_gate", "unit": unit, "sessions": n_unpriced, "monthly_saving_usd": None,
                      "filed": False, "basis": "unpriced"})
    return {**base, "status": "ok", "findings": found}


def cause_class(code: str) -> str:
    return causemod.cause_of(code).klass
