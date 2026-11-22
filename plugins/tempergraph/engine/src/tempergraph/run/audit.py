"""The sampled audit judge (JDG-B7, JDG-AC7).

After a gate's judgement, with probability `audit_rate` a second judge grades the same subject on the audit
executor when one is set. Its per-criterion agreement is recorded as an `audit_judge` record and its sessions are
logged like any judge's; it never changes the verdict, the route, a counter or a budget. A session that failed,
timed out, could not be read or was discarded by the guard writes nothing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from tempergraph.contracts import CheckResult, GateSpec, SessionRequest, SessionResult, Usage
from tempergraph.run.judging import Unparsed, derive, parse_judgement


def sampled(rate: float, *, seed: int | None, thread: str, unit: str, item: str | None, attempt: int) -> bool:
    """The draw: a hash of the seed, the thread, the unit, the item and the attempt against the rate, so a second
    call, a resume and a rerun of the same attempt draw the same. At 1.0 every judged gate is audited, at 0 none."""
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    key = "\0".join([str(seed if seed is not None else ""), thread, unit, item or "", str(attempt)])
    point = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big") / 2**64
    return point < rate


@dataclass(frozen=True, kw_only=True)
class Audit:
    """What an `audit_judge` record carries."""

    executor: str
    alias: str
    session_key: str
    statuses: list[dict[str, str]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    def fields(self) -> dict[str, Any]:
        return {"executor": self.executor, "alias": self.alias, "session_key": self.session_key,
                "statuses": self.statuses, "usage": self.usage}


def run(session: Callable[[SessionRequest], tuple[SessionResult, list[SessionResult]]], req: SessionRequest, *,
        gate: GateSpec, check: CheckResult | None, executor: str, discarded: Callable[[SessionResult], bool]
        ) -> Audit | None:
    """One audit session on the gate's own prompt and views; its status per criterion, or nothing when the session
    failed, timed out, could not be parsed or was discarded by the guard."""
    res, _ = session(req)
    if res.infra_cause is not None or res.timed_out:
        return None
    try:
        judgement = parse_judgement(res.text, gate)
    except Unparsed:
        return None
    if discarded(res):
        return None
    outcome = derive(judgement, gate, check, {})
    return Audit(executor=executor, alias=req.alias, session_key=req.session_key, usage=res.usage,
                 statuses=[{"id": str(s["id"]), "status": str(s["status"])} for s in outcome.statuses])
