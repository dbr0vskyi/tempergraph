"""The contest's pick and the records it writes (CTS-B1, CTS-B7, CTS-B9; EVT-B15). Model-free and pure.

Every slot that was graded and not put out is a `Candidate`. The slots are ordered by derived verdict (PROCEED first),
then fewer unmet warnings, more criteria MET, higher judge confidence, lower cost and earlier place in the declared
order; the first is the winner. This module reads numbers and words only: it starts nothing and reads no file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

VERDICT_RANK = {"PROCEED": 0, "RETRY": 1, "BACK": 2, "ESCALATE": 3, "STOP": 4}  # the order of CTS-B7: PROCEED first


@dataclass(frozen=True)
class Candidate:
    """One slot that was graded and not put out: its derived verdict and the keys the pick compares."""

    slot: str
    order: int  # the slot's place in the declared order, counted from 0
    verdict: str
    unmet_warnings: int = 0
    met: int = 0
    confidence: float = 0.0
    cost: float = 0.0


def rank_key(c: Candidate) -> tuple[int, int, int, float, float, int]:
    """Smaller sorts first: verdict, unmet warnings, more MET, higher confidence, lower cost, earlier slot."""
    return (VERDICT_RANK.get(c.verdict, len(VERDICT_RANK)), c.unmet_warnings, -c.met, -c.confidence, c.cost, c.order)


def ordered(candidates: Sequence[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=rank_key)


def pick(candidates: Sequence[Candidate]) -> Candidate | None:
    """The winner, or None when no slot is left to pick from."""
    got = ordered(candidates)
    return got[0] if got else None


def keys_of(judgement: Mapping[str, Any]) -> dict[str, Any]:
    """The three keys the pick compares after the verdict, from a slot's judgement: the criteria of severity warning it
    did not meet (`notes`), the criteria it met, and the judge's confidence."""
    met = sum(1 for s in judgement.get("statuses") or [] if isinstance(s, Mapping) and s.get("status") == "MET")
    conf = judgement.get("confidence")
    return {"unmet_warnings": len(judgement.get("notes") or []), "met": met,
            "confidence": float(conf) if isinstance(conf, int | float) and not isinstance(conf, bool) else 0.0}


def retry_write(unit: str, scope: str, winner: str | None) -> dict[str, Any]:
    """The `maps` write of a RETRY of the contest `unit` (CTS-B8, CTS-B4): under `best` with a winner the contest becomes
    one step, the winner's slot (`single`), for the rest of the visit; under `all`, or with no winner (every slot put out
    by its check), every slot runs again with its own notes."""
    if scope == "best" and winner:
        return {"maps": {unit: {"single": winner}}}
    return {"maps": {unit: {"single": None}}}


def retry_slots(names: Sequence[str], single: str | None) -> list[str]:
    """The slots a retry runs: the one slot a `best` retry kept, else every slot (CTS-B8)."""
    return [single] if single is not None and single in names else list(names)


def slot_row(place: int, name: str, *, attempt: int | None = None, check: str | None = None,
             verdict: str | None = None, keys: Mapping[str, Any] | None = None, cost: float = 0.0,
             skipped: bool = False) -> dict[str, Any]:
    """One slot of the `contest` run record (EVT-B15): its place in the declared order from 1, its name, the check result,
    the derived verdict, the rank keys and the cost, or `skipped` for a slot the attempt's cost cap kept from starting."""
    if skipped:
        return {"slot": place, "name": name, "skipped": True}
    return {"slot": place, "name": name, "attempt": attempt, "check": check, "verdict": verdict,
            "keys": dict(keys) if keys is not None else None, "cost": round(cost, 6)}
