"""`outcome show` and `outcome candidates` (CLI §2, OUT §2.5, §2.6); read-only, model-free (contract C13)."""

from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime, timedelta
from typing import Any

WINDOW = re.compile(r"^(\d{1,4})d$")


def add_parser(sub: Any, parser_class: type[argparse.ArgumentParser]) -> None:
    o = sub.add_parser("outcome", help="the good outcome, its measures and revision candidates")
    osub = o.add_subparsers(dest="action", parser_class=parser_class)
    sh = osub.add_parser("show")
    sh.add_argument("workflow")
    sh.add_argument("--runs", nargs="?", const="all", default=None, metavar="WINDOW", help="all, or <days>d")
    sh.add_argument("--json", action="store_true")
    ca = osub.add_parser("candidates")
    ca.add_argument("workflow")
    ca.add_argument("--window", type=int, default=None, metavar="DAYS")


def _since(window: str | int | None) -> str | None:
    if window in (None, "all"):
        return None
    if isinstance(window, int):
        days = window
    else:
        m = WINDOW.match(str(window))
        if not m:
            from tempergraph.cli.main import UsageError

            raise UsageError(f"--runs {window!r}: expected all or <days>d")
        days = int(m.group(1))
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def _definition(spec: Any) -> dict[str, Any]:
    from tempergraph.run.outcome_trust import coverage, profile, trust

    o = spec.outcome
    root = spec.package_root
    final = [{"id": c.id, "severity": c.severity, "verified_by": c.verified_by or "none",
              "trust": trust(c, "outcome", root)} for c in o.final]
    inter = [{"unit": u, "id": c.id, "verified_by": c.verified_by or "none", "serves": list(c.serves),
              "trust": trust(c, u, root)} for u, io in o.intermediate.items() for c in io.criteria]
    cov = [{"criterion": c.criterion, "trust": c.trust, "covered": c.covered, "serving": c.serving,
            "missing_units": c.missing_units} for c in coverage(o, spec)]
    return {"revision": o.revision, "statement": o.statement, "deliverables": [dict(d) for d in o.deliverables],
            "final": final, "intermediate": inter, "trust_profile": profile(o, spec), "coverage": cov}


def cmd_outcome(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import UsageError, _emit, _root_or_none, _spec
    from tempergraph.run import outcome_record

    if a.action not in ("show", "candidates"):
        raise UsageError("outcome needs show or candidates")
    spec = _spec(env, a.workflow)
    if spec.outcome is None:
        raise UsageError(f"{spec.name} has no outcome.json; the authoring skill writes one (AUT)")
    root = _root_or_none(env)
    ledger = root / "ledger.jsonl" if root is not None else None
    if a.action == "candidates":
        doc = outcome_record.candidates(spec, ledger, _since(a.window)) if ledger else \
            {"schema_version": 1, "workflow": spec.name, "candidates": []}
        _emit(env, doc)
        return 0
    doc = {"schema_version": 1, "workflow": spec.name, "outcome": _definition(spec)}
    if a.runs is not None:
        doc["runs"] = outcome_record.measures(spec, ledger, _since(a.runs))["revisions"] if ledger else []
    _emit(env, doc)
    return 0
