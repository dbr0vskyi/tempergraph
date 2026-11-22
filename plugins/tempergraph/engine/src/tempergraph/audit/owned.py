"""Owned history rules, rendered (ARC-B1, ARC-AC4, ADR-0054): `cost-lens-rules`, `engine-fault-open` and
`prompt-change-moved-gate`.

Each calls the owning component and renders what it returns under `<owner>:<code>` with the owner's wording and
numbers: the cost lens of SIL (`improve.lenses.cost_rules`), the engine-side findings of the runs (`improve.record`,
`improve.causes`) and the post-release watch of SIL. No logic of those components is copied here. A function returns
None when its owner is not present (ARC-B7: skipped with `owner not present`, never passed).
"""

from __future__ import annotations

import datetime as dt
import importlib
from collections.abc import Callable
from typing import Any

from tempergraph.audit.history import HistoryFacts
from tempergraph.audit.report import AuditFinding
from tempergraph.contracts import WorkflowSpec

OWNER = "SIL"


def _version(spec: WorkflowSpec, facts: HistoryFacts) -> str:
    """The workflow version the owners filter on: `current` and `all` read the audited spec's version."""
    return spec.version if facts.version in ("current", "all") else facts.version


def _now(facts: HistoryFacts) -> dt.datetime:
    return dt.datetime.combine(facts.today or dt.date.today(), dt.time(23, 59, 59), tzinfo=dt.UTC)


def cost_lens_findings(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding] | None:
    """ARC-B1: the cost lens's findings over the same window, carried with its code and numbers."""
    from tempergraph.improve import lenses

    if facts.root is None:
        return []
    got = lenses.cost_rules(spec, facts.root, _version(spec, facts), _now(facts))
    out = []
    for f in got.get("findings") or []:
        out.append(AuditFinding(
            rule=f"cost-lens:{f['rule']}", layer="history", severity="warning" if f.get("filed") else "info",
            confidence="medium", unit=f.get("unit"), owner=OWNER,
            statement=f"cost lens {f['rule']} on {f.get('unit') or 'the workflow'}",
            evidence={k: v for k, v in f.items() if k not in ("rule", "unit")},
            remedy="See the cost lens (SIL-B10)"))
    return out


def engine_fault_findings(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding] | None:
    """ARC-B14: open engine- or executor-side findings that name this workflow's units, so the author does not
    chase them in the workflow. The side is the finding's own, else its cause's (`improve.causes`)."""
    from tempergraph.improve import causes as causemod

    seen: dict[tuple[str, str, str], set[str]] = {}
    for f in facts.findings:
        cause, unit = str(f.get("cause") or ""), f.get("unit")
        if not cause or unit not in spec.units:
            continue
        side = str(f.get("side") or causemod.cause_of(cause).side)
        if side == "engine" or side.startswith("executor"):
            seen.setdefault((cause, str(unit), side), set()).add(str(f.get("run")))
    return [AuditFinding(rule=f"{OWNER}:{cause}", layer="history", severity="info", confidence="high", unit=unit,
                         owner=OWNER, statement=f"{cause} on {unit} is an open {side} finding, not a workflow defect",
                         evidence={"runs": len(runs), "side": side}, remedy="See SIL: the fix is on the engine side")
            for (cause, unit, side), runs in sorted(seen.items())]


def _watch() -> Callable[[WorkflowSpec, Any, str], list[dict[str, Any]]] | None:
    """The post-release watch of SIL and PRP, or None when the engine does not hold it yet."""
    try:
        mod = importlib.import_module("tempergraph.improve.watch")
    except ImportError:
        return None
    return getattr(mod, "prompt_moved_gates", None)


def prompt_change_findings(spec: WorkflowSpec, facts: HistoryFacts) -> list[AuditFinding] | None:
    """PRA-B10: a prompt change that moved a gate, from the watch, with its digest and dates."""
    watch = _watch()
    if watch is None:
        return None
    out = []
    for row in watch(spec, facts.root, _version(spec, facts)):
        code = str(row["code"])
        out.append(AuditFinding(
            rule=f"{OWNER}:{code}", layer="history", severity=str(row.get("severity") or "warning"),
            confidence="high", unit=row.get("unit"), owner=OWNER, statement=str(row.get("message") or code),
            evidence={k: v for k, v in row.items() if k not in ("code", "unit", "message", "severity")},
            remedy="See the post-release watch (SIL, PRP)"))
    return out


HISTORY_OWNED = {"cost-lens-rules": cost_lens_findings, "engine-fault-open": engine_fault_findings,
                 "prompt-change-moved-gate": prompt_change_findings}
