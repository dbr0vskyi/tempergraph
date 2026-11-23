"""A contest's retry: both scopes, the no-winner outcome and a winner's other verdicts (CTS-AC4; CTS-B8, CTS-B4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode

from .test_contest_run import BLOCKED, BOTH_MET, BySlot, block, contest_spec, go, recs


def keys(ex: BySlot, slot: str | None = None, kind: str | None = None) -> list[str]:
    return [r.session_key for r in ex.requests if r.session_key.startswith("pick.")
            and (slot is None or r.session_key.split(".")[1] == slot)
            and (kind is None or r.session_key.endswith(kind))]


def test_a_retry_under_best_runs_the_winner_s_slot_alone_with_its_notes_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B8)
    ex = BySlot(judges={"s1": [BLOCKED], "s2": [BLOCKED, BOTH_MET], "s3": [BLOCKED]},
                costs={"s1": 0.3, "s2": 0.1, "s3": 0.2})  # every slot RETRY: the cheapest, `s2`, is best-ranked
    out = go(repo, contest_spec(retry_scope="best", then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert keys(ex, "s2", ".step") == ["pick.s2.1.step"] and keys(ex, "s2", ".retry") == ["pick.s2.2.retry"]
    assert keys(ex, "s1", ".step") == ["pick.s1.1.step"] and keys(ex, "s1", ".retry") == []  # the others are not run again
    assert keys(ex, "s3", ".step") == ["pick.s3.1.step"] and keys(ex, "s3", ".retry") == []
    retry = next(r for r in ex.requests if r.session_key == "pick.s2.2.retry")
    assert "missing" in retry.prompt and "Did s2." in retry.prompt  # its own judge's notes and its own previous report
    assert "Did s1." not in retry.prompt and "Did s3." not in retry.prompt
    first, second = recs(repo, "contest")
    assert (first["winner"], [s["name"] for s in first["slots"]]) == (2, ["s1", "s2", "s3"])
    assert (second["winner"], [s["name"] for s in second["slots"]]) == (2, ["s2"])  # the contest is one step now
    assert [g["token"] for g in recs(repo, "gate") if g["unit"] == "pick"] == ["RETRY", "PROCEED"]


def test_every_slot_retry_under_best_charges_the_retry_budget_once_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B4)
    ex = BySlot(judges={"s1": [BLOCKED], "s2": [BLOCKED, BOTH_MET], "s3": [BLOCKED]},
                costs={"s1": 0.3, "s2": 0.05, "s3": 0.2})
    out = go(repo, contest_spec(retry_scope="best", then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert keys(ex, "s2", ".retry") == ["pick.s2.2.retry"]  # the best-ranked slot, alone
    charged = [b for b in recs(repo, "budget") if b["unit"] == "pick" and b["counter"] == "retries"]
    assert [(b["used"], b["limit"]) for b in charged] == [(1, 2)]  # once, though three slots were RETRY
    assert sum(1 for k in keys(ex) if k.endswith((".step", ".retry"))) == 4  # three slots, then the best-ranked alone


def test_a_second_retry_under_best_still_runs_the_one_slot_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B8)
    ex = BySlot(judges={"s1": [BLOCKED], "s2": [BLOCKED, BLOCKED, BOTH_MET], "s3": [BLOCKED]},
                costs={"s1": 0.3, "s2": 0.05, "s3": 0.2})
    out = go(repo, contest_spec(retry_scope="best", retry_budget=2, then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert keys(ex, "s2", ".retry") == ["pick.s2.2.retry", "pick.s2.3.retry"]
    assert keys(ex, "s1", ".retry") == [] and keys(ex, "s3", ".retry") == []  # a single step for the rest of the visit


def test_a_retry_under_all_runs_every_slot_with_its_own_notes_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B8)
    ex = BySlot(judges={"s1": [BLOCKED, BOTH_MET], "s2": [BLOCKED, BOTH_MET], "s3": [BLOCKED, BOTH_MET]},
                costs={"s1": 0.3, "s2": 0.2, "s3": 0.1})
    out = go(repo, contest_spec(retry_scope="all", then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert sorted(keys(ex, kind=".retry")) == ["pick.s1.2.retry", "pick.s2.2.retry", "pick.s3.2.retry"]  # every slot again
    for mine in ("s1", "s2", "s3"):
        prompt = next(r.prompt for r in ex.requests if r.session_key == f"pick.{mine}.2.retry")
        assert f"Did {mine}." in prompt and "missing" in prompt  # its own previous report and notes
        assert all(f"Did {other}." not in prompt for other in {"s1", "s2", "s3"} - {mine})
    first, second = recs(repo, "contest")
    assert first["winner"] == 3 and second["winner"] == 3  # each attempt carries a pick of its own
    assert [len(first["slots"]), len(second["slots"])] == [3, 3]


def test_a_winner_that_escalates_applies_to_the_unit_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B8)
    gap = block("UNVERIFIABLE", "MET")  # a blocker the judge could not verify: ESCALATE
    ex = BySlot(judges={"s1": [gap], "s2": [gap], "s3": [gap]})
    out = go(repo, contest_spec(then=False), ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert out.payload["kind"] == "escalation" and out.payload["unit"] == "pick"
    assert out.payload["winner"] == "s1"  # the winner's verdict is the unit's; the pause says whose it is
    assert [g["token"] for g in recs(repo, "gate") if g["unit"] == "pick"] == ["ESCALATE"]


def test_a_winner_that_goes_back_applies_to_the_unit_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B8)
    rows = [{"n": 1, "status": "UNMET", "evidence": "the plan is wrong", "defect_in": "doc", "no_change": False},
            {"n": 2, "status": "MET", "evidence": "x:1", "defect_in": None, "no_change": False}]
    back = "R.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.8}) + "\n```"
    ex = BySlot(judges={"s1": [back], "s2": [back], "s3": [back]})
    spec = contest_spec(then=False, plan=True, gate={"back_targets": ["plan"]})
    out = go(repo, spec, ex, flags={"plan.retry_budget": 2})
    gates = [(g["unit"], g["token"], g["route_target"]) for g in recs(repo, "gate") if g["unit"] == "pick"]
    assert gates[0] == ("pick", "BACK", "plan.step"), (gates, out.message)  # the winner's BACK sends the unit back to `plan`


def test_a_winner_that_stops_applies_to_the_unit_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B8)
    ex = BySlot(judges={"s1": [BLOCKED], "s2": [BLOCKED], "s3": [BLOCKED]})
    out = go(repo, contest_spec(then=False, gate={"on_fail": "stop"}), ex)
    assert [g["token"] for g in recs(repo, "gate") if g["unit"] == "pick"] == ["STOP"]
    assert out.exit_code is not ExitCode.FINISHED, out.message
    assert len(keys(ex, kind=".step")) == 3  # the one pick, no retry
    stopped: Any = out.reason
    assert stopped is not None
