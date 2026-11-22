"""The same check failure twice, the step having changed files, escalates at once (BUD-B16, BUD-AC8)."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tempergraph.api import CheckResult, callable_ref
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding, SessionResult
from tempergraph.executors.standins import standin

from .fixtures.workflows import two_step
from .test_run import DRAFT, go, records


def same_finding(ctx: Any) -> CheckResult:
    return CheckResult(result="FAIL", evidence="no file", findings=[
        CheckFinding(status="fail", criterion="c-file", place="notes.md", fix="write it", message="missing")])


def moving_finding(ctx: Any) -> CheckResult:  # the failure changes with every attempt
    return CheckResult(result="FAIL", evidence="no file", findings=[
        CheckFinding(status="fail", criterion="c-file", place=f"notes{ctx.attempt}.md", fix="write it",
                     message="missing")])


def same_text(ctx: Any) -> CheckResult:  # no findings: the scrubbed evidence text is the failure
    return CheckResult(result="FAIL", evidence="the build output was empty", findings=[])


def moving_text(ctx: Any) -> CheckResult:
    return CheckResult(result="FAIL", evidence=f"the build output of attempt {ctx.attempt} was empty", findings=[])


def spec_of(check: Callable[[Any], CheckResult], retry_budget: int = 3) -> Any:
    spec = two_step()
    units = dict(spec.units)
    gate = dataclasses.replace(units["draft"].gate, check=callable_ref(check), retry_budget=retry_budget)
    units["draft"] = dataclasses.replace(units["draft"], gate=gate)
    return dataclasses.replace(spec, units=units)


def writes(name: str) -> Callable[[Any], SessionResult]:
    """A step session that leaves a new file in the workspace, so its attempt `changed` files."""
    def reply(req: Any) -> SessionResult:
        (Path(req.workdir) / name).write_text("x\n")
        return DRAFT
    return reply


def idle(_req: Any) -> SessionResult:
    return DRAFT


def steps(*replies: Any, n: int = 4) -> list[Any]:
    return [*replies] + [idle] * (n - len(replies))


def budgets(repo: Path, task: str) -> list[dict[str, Any]]:
    return [r for r in records(repo, task) if r["kind"] == "budget"]


def test_the_same_failure_twice_with_changed_files_escalates_at_once(repo: Path) -> None:  # BUD-AC8
    ex = standin("claude", steps=steps(writes("a1.txt"), writes("a2.txt")))
    out = go(repo, ex, spec_of(same_finding), task="K-1")
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "escalation"
    assert out.payload["reason"] == "check_repeat" and out.payload["unit"] == "draft"
    assert [(f["criterion"], f["place"], f["message"]) for f in out.payload["repeated"]] \
        == [("c-file", "notes.md", "missing")]
    assert [c.kind for c in ex.calls] == ["step", "step"]  # no third attempt although 3 retries were allowed
    assert [b["used"] for b in budgets(repo, "K-1")] == [1]  # the one retry before the repeat; none after it
    assert not [r for r in records(repo, "K-1") if r["kind"] == "ladder_decision"]


def test_a_failure_that_changes_between_attempts_keeps_the_retries(repo: Path) -> None:  # BUD-AC8
    ex = standin("claude", steps=steps(writes("b1.txt"), writes("b2.txt")))
    out = go(repo, ex, spec_of(moving_finding, retry_budget=1), task="K-2")
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"  # BUD-B8: the retry ran out
    assert "repeated" not in out.payload and [c.kind for c in ex.calls] == ["step", "step"]


def test_a_later_step_that_changed_no_file_keeps_the_retries(repo: Path) -> None:  # BUD-AC8
    ex = standin("claude", steps=steps(writes("c1.txt"), idle))
    out = go(repo, ex, spec_of(same_finding, retry_budget=2), task="K-3")
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    assert out.payload["reason"] != "check_repeat" and [c.kind for c in ex.calls] == ["step"] * 3


def test_a_failure_with_no_findings_repeats_on_the_same_evidence_text(repo: Path) -> None:  # BUD-AC8
    ex = standin("claude", steps=steps(writes("d1.txt"), writes("d2.txt")))
    out = go(repo, ex, spec_of(same_text), task="K-4")
    assert out.payload["kind"] == "escalation" and out.payload["reason"] == "check_repeat"
    assert out.payload["repeated"] == [] and [c.kind for c in ex.calls] == ["step", "step"]
    ex = standin("claude", steps=steps(writes("e1.txt"), writes("e2.txt")))
    out = go(repo, ex, spec_of(moving_text, retry_budget=1), task="K-5")
    assert out.payload["kind"] == "budget"  # the evidence text changed: the normal retries


def test_the_first_attempt_never_repeats(repo: Path) -> None:  # BUD-AC8
    ex = standin("claude", steps=steps(writes("f1.txt")))
    out = go(repo, ex, spec_of(same_finding, retry_budget=0), task="K-6")
    assert out.payload["kind"] == "budget" and [c.kind for c in ex.calls] == ["step"]
