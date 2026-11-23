"""What a contest does when its slots fail (CTS-AC4; CTS-B9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tempergraph.api import CheckResult
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding

from .test_contest_run import BOTH_MET, ONE_WARNING, BySlot, contest_spec, fails_all, go, recs


def fails_the_first_round(ctx: Any) -> CheckResult:
    """Every slot's check fails on its first attempt and passes on the next."""
    if ctx.attempt == 1:
        return CheckResult(result="FAIL", evidence=f"{ctx.item} is wrong", findings=[
            CheckFinding(status="fail", criterion="c-main", message=f"{ctx.item} not there")])
    return CheckResult(result="PASS", evidence="ok")


def test_every_slot_failing_on_infrastructure_ends_the_attempt_as_an_infra_failure_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B9)
    ex = BySlot(infra={"s1", "s2", "s3"})
    out = go(repo, contest_spec(then=False), ex)
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA, out.message
    assert not [k for k in ex.sessions if k.startswith("judge.")]  # no slot is graded
    (rec,) = recs(repo, "contest")
    assert rec["winner"] is None and all(s["verdict"] is None and s["keys"] is None for s in rec["slots"])
    assert [g["token"] for g in recs(repo, "gate") if g["unit"] == "pick"] == ["STOP"]
    stopped = [r for r in recs(repo, "run_exit")]
    assert stopped and stopped[-1]["exit_code"] == int(ExitCode.BUDGET_OR_INFRA)


def test_one_slot_failing_on_infrastructure_leaves_the_others_to_be_picked_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B9)
    ex = BySlot(infra={"s1"}, judges={"s2": [ONE_WARNING], "s3": [BOTH_MET]})
    out = go(repo, contest_spec(then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (rec,) = recs(repo, "contest")
    assert rec["winner"] == 3 and rec["slots"][0]["verdict"] is None  # the failed slot is out, the others are ranked


def test_every_slot_s_check_failing_makes_the_first_slot_s_fail_the_units_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B9)
    ex = BySlot()
    out = go(repo, contest_spec(check=fails_all, retry_budget=0, then=False), ex)
    assert out.exit_code is ExitCode.PAUSED, out.message  # no retry left: the gate asks a person
    assert out.payload["kind"] == "budget" and out.payload["winner"] is None
    assert [b["problem"] for b in out.payload["blockers"]] == ["s1 not there"]  # the first slot's FAIL, not the last's
    assert not [k for k in ex.sessions if k.startswith("judge.")]  # a slot whose check fails gets no judge session
    checks = sorted((c["item"], c["result"]) for c in recs(repo, "check") if c["unit"] == "pick")  # they ran at once
    assert checks == [("s1", "FAIL"), ("s2", "FAIL"), ("s3", "FAIL")]
    (rec,) = recs(repo, "contest")
    assert rec["winner"] is None and [s["check"] for s in rec["slots"]] == ["FAIL", "FAIL", "FAIL"]


def test_every_slot_s_check_failing_retries_per_the_gate_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B9)
    ex = BySlot()
    out = go(repo, contest_spec(check=fails_the_first_round, retry_budget=1, then=False), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert sorted(r.session_key for r in ex.requests if r.session_key.endswith(".retry")) == [
        "pick.s1.2.retry", "pick.s2.2.retry", "pick.s3.2.retry"]  # no winner to keep: every slot runs again
    first, second = recs(repo, "contest")
    assert first["winner"] is None and second["winner"] == 1
    assert [g["token"] for g in recs(repo, "gate") if g["unit"] == "pick"] == ["RETRY", "PROCEED"]
