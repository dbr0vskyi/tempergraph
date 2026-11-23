"""The contest's pick: a fixed rule over the slots' verdicts and keys, no model call in the pick code (CTS-AC2; CTS-B1,
CTS-B7)."""

from __future__ import annotations

import ast
import inspect

from tempergraph.run import contest
from tempergraph.run.contest import Candidate, ordered, pick


def cand(slot: str, order: int, verdict: str = "PROCEED", warnings: int = 0, met: int = 5, confidence: float = 0.8,
         cost: float = 0.3) -> Candidate:
    return Candidate(slot=slot, order=order, verdict=verdict, unmet_warnings=warnings, met=met, confidence=confidence,
                     cost=cost)


def test_the_scenario_of_cts_b1_picks_the_cheaper_of_two_ties() -> None:  # CTS-AC2 (CTS-B1)
    slots = [cand("s1", 0, "RETRY", 0, 5, 0.85, 0.30), cand("s2", 1, "PROCEED", 1, 6, 0.85, 0.40),
             cand("s3", 2, "PROCEED", 1, 6, 0.85, 0.55)]
    winner = pick(slots)
    assert winner is not None and winner.slot == "s2"
    assert [c.slot for c in ordered(slots)] == ["s2", "s3", "s1"]  # PROCEED first, then by cost, the RETRY last


def test_each_key_decides_in_its_turn() -> None:  # CTS-AC2 (CTS-B7)
    a, b = cand("a", 0), cand("b", 1)
    assert pick([cand("a", 0, "RETRY"), cand("b", 1, "PROCEED")]).slot == "b"  # type: ignore[union-attr]  # verdict
    assert pick([cand("a", 0, "ESCALATE"), cand("b", 1, "BACK")]).slot == "b"  # type: ignore[union-attr]
    assert pick([cand("a", 0, "BACK"), cand("b", 1, "RETRY")]).slot == "b"  # type: ignore[union-attr]
    assert pick([cand("a", 0, warnings=2), cand("b", 1, warnings=1)]).slot == "b"  # type: ignore[union-attr]  # warnings
    assert pick([cand("a", 0, met=4), cand("b", 1, met=6)]).slot == "b"  # type: ignore[union-attr]  # MET
    assert pick([cand("a", 0, confidence=0.5), cand("b", 1, confidence=0.9)]).slot == "b"  # type: ignore[union-attr]
    assert pick([cand("a", 0, cost=0.9), cand("b", 1, cost=0.2)]).slot == "b"  # type: ignore[union-attr]  # cost
    assert pick([a, b]).slot == "a"  # type: ignore[union-attr]  # all equal: the earlier slot
    assert pick([cand("a", 0, warnings=1, met=9), cand("b", 1, warnings=0, met=1)]).slot == "b"  # type: ignore[union-attr]
    assert pick([cand("a", 0, met=5, confidence=0.1), cand("b", 1, met=6, confidence=0.99, cost=9.0)]).slot == "b"  # type: ignore[union-attr]


def test_a_pick_of_no_slot_is_none() -> None:  # CTS-AC2 (CTS-B9)
    assert pick([]) is None


def test_the_keys_come_from_a_judgement() -> None:  # CTS-AC2 (CTS-B7)
    j = {"verdict": "PROCEED", "notes": ["c-style: Style (UNMET)"], "confidence": 0.85,
         "statuses": [{"n": 1, "id": "c1", "status": "MET"}, {"n": 2, "id": "c2", "status": "MET"},
                      {"n": 3, "id": "w1", "status": "UNMET"}, {"n": 4, "id": "c4", "status": "N/A"}]}
    assert contest.keys_of(j) == {"unmet_warnings": 1, "met": 2, "confidence": 0.85}
    assert contest.keys_of({"verdict": "ESCALATE"}) == {"unmet_warnings": 0, "met": 0, "confidence": 0.0}


def test_the_pick_code_calls_no_model() -> None:  # CTS-AC2 (CTS-B7): a source scan
    tree = ast.parse(inspect.getsource(contest))
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not [m for m in imported if any(w in m for w in ("executor", "nodes", "registry", "judging", "launcher"))]
    called = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "") for n in ast.walk(tree)
              if isinstance(n, ast.Call)}
    assert not called & {"run_step", "run_judge", "_session", "judge_executor", "probe", "invoke"}
    assert not any(w in inspect.getsource(contest.pick) + inspect.getsource(contest.ordered) + inspect.getsource(
        contest.rank_key) for w in ("run_step", "run_judge", "Session", "registry"))
