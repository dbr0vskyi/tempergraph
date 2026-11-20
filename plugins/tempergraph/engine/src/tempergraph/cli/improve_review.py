"""`tempergraph improve review <selector>`, `improve review show <selector>`, `improve review summary` (SRV §2.9).

`improve review <selector>` plans and runs a review of one run now, `reason: person`, under the per-run cap; in
release 1 a person's review reads `full` (the `signals` plans are release 2, X2-26), and `--full` is accepted for
the release 2 shape. `--dry-run` prints the plan and its estimate and spends nothing. `show` and `summary` are
read-only. Exit 0, or 2 for a bad selector or option. Results stay on the machine (SRV §2.8).
"""

from __future__ import annotations

import argparse
from typing import Any

from tempergraph.constants import ExitCode


def add_review_parser(isub: Any) -> None:
    rv = isub.add_parser("review", help="the session review of a run (SRV): run, show, summary")
    rv.add_argument("first", metavar="selector", help="a thread selector, or `show` / `summary`")
    rv.add_argument("second", nargs="?", default=None, help=argparse.SUPPRESS)
    rv.add_argument("--session", action="append", default=[], metavar="KEY", help="review only these sessions")
    rv.add_argument("--full", action="store_true", help="read every session (release 1 always does)")
    rv.add_argument("--dry-run", action="store_true", help="print the plan and the estimate; spend nothing")
    rv.add_argument("--version", default=None, help="summary: one workflow version")
    rv.add_argument("--json", action="store_true")


def _ledger_cost(root: Any, thread: str) -> float:
    from tempergraph.improve.review import _jsonl

    total = 0.0
    for r in _jsonl(root / "ledger.jsonl"):
        if r.get("kind") == "run_segment" and r.get("thread_id") == thread:
            c = r.get("cost") or {}
            total += float(c.get("reported") or 0.0) + float(c.get("estimated_only") or 0.0)
    return total


def _text(doc: dict[str, Any]) -> str:
    lines = []
    plan = doc.get("plan") or {}
    lines.append(f"plan: depth {plan.get('depth')}, {len(plan.get('targets') or [])} sessions, "
                 f"cap {plan.get('cap_usd')} USD, about {plan.get('estimate_tokens')} tokens")
    for s in plan.get("skipped") or []:
        lines.append(f"  skipped {s.get('session_key')}: {s.get('reason')}")
    for s in doc.get("sessions") or []:
        lines.append(f"{s.get('session_key')}: {len(s.get('observations') or [])} kept, "
                     f"{s.get('unsupported')} unsupported")
        for o in s.get("observations") or []:
            lines.append(f"  {o.get('category')} turns {o.get('turns')} remedy {o.get('remedy_class')}: "
                         f"{o.get('note') or ''}")
    for r in doc.get("rows") or []:
        lines.append(f"{r['workflow']} {r['unit']} {r['category']} {r['check']}: {r['count']}")
    return "\n".join(lines) + "\n"


def cmd_review(env: Any, a: argparse.Namespace) -> int:
    from tempergraph.cli.main import UsageError, _emit, _one, _root
    from tempergraph.improve import review
    from tempergraph.improve.record import unit_decls

    def out(doc: dict[str, Any]) -> int:
        if a.json:
            _emit(env, doc)
        else:
            env.out.write(_text(doc))
        return int(ExitCode.FINISHED)

    root = _root(env)
    if a.first == "summary":
        return out(review.summary(root, a.second, a.version))
    if a.first == "show":
        if a.second is None:
            raise UsageError("improve review show takes a selector")
        spec, tid = _one(env, a.second)
        return out(review.show(root, spec.name, tid.split("/", 1)[-1]))
    if a.second is not None:
        raise UsageError("improve review takes one selector, or show <selector>, or summary [workflow]")
    spec, tid = _one(env, a.first)
    task = tid.split("/", 1)[-1]
    t = {"state_root": str(root), "workflow": spec.name, "task_id": task, "thread": tid, "review": "full",
         "mode": spec.improvement_mode, "executor": spec.default_executor, "units": unit_decls(spec),
         "run_cost_usd": _ledger_cost(root, tid)}
    got = review.run(t, env.registry, reason="person", keys=tuple(a.session), force_full=True, dry_run=a.dry_run)
    doc = {"schema_version": 1, "thread": tid, "plan": got["plan"], "done": got["done"], "failed": got["failed"],
           "cost": got["cost"], **({} if a.dry_run else {"sessions": review.show(root, spec.name, task)["sessions"]})}
    return out(doc)

