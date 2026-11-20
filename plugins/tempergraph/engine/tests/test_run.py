"""The gate funnel end to end with scripted executors (JDG-AC-1–4, GRD-AC-3, HUM-AC-2, BUD-AC-3, DUR-B1,
DUR §2.1 resume rows, OBS §2.1 records)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.contracts import InfraCause, SessionResult, ThreadState, ToolCall, Usage
from tempergraph.durability.status import classify, status
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import ScriptedExecutor, answer, standin
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import two_step

NO_SLEEP = RunSettings(sleep=lambda s: None)


def verdict_block(*statuses: str, defect_in: str | None = None, no_change: bool = False) -> str:
    rows = [{"n": i, "status": s, "evidence": "notes.md:1 shows it" if s == "MET" else "missing",
             "defect_in": defect_in, "no_change": no_change} for i, s in enumerate(statuses, 1)]
    return "Reviewed.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.8}) + "\n```"


MET = verdict_block("MET")
DRAFT = answer("Wrote notes.md\nARTIFACT notes: notes.md", session_id="s-draft")
REVIEW = answer("Looks fine\nARTIFACT verdict: ok", session_id="s-review")


def judge(text: str = MET, tools: tuple[str, ...] = ("Read",), sid: str = "j") -> SessionResult:
    return answer(text, tools=tools, session_id=sid)


def registry(ex: ScriptedExecutor) -> Registry:
    r = Registry()
    r.register(ex)
    return r


def go(repo: Path, ex: ScriptedExecutor, spec: Any = None, task: str = "T-1", **kw: Any) -> Any:
    return start(spec or two_step(), task, {"request": "Release 1.2 notes"}, repo, registry(ex),
                 dataclasses.replace(NO_SLEEP, **kw))


def records(repo: Path, task: str = "T-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def test_happy_path(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    root = state_root_path(repo)
    assert classify(root, two_step(), "T-1") is ThreadState.FINISHED
    kinds = [r["kind"] for r in records(repo)]
    assert kinds.count("agent_run") == 4 and "run_exit" in kinds and kinds[0] == "schema"
    row = status(root, {"demo": two_step()})["threads"][0]
    assert row["state"] == "finished" and row["exit_code"] == 0
    assert row["workspace"]["mode"] == "worktree"  # the workflow writes files (WTR §2.2)
    assert [c.kind for c in ex.calls] == ["step", "judge", "step", "judge"]
    draft_prompt = ex.calls[0].request.prompt
    assert "Release 1.2 notes" in draft_prompt and "## How this output will be judged" in draft_prompt
    assert "Release 1.2 notes" in ex.calls[1].request.prompt  # the judge sees the request
    assert ex.calls[0].request.workdir == Path(row["workspace"]["path"])


def test_fresh_start_on_existing_thread_is_refused(repo: Path) -> None:
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]))
    again = go(repo, standin("claude"))
    assert again.exit_code is ExitCode.USAGE and "resume" in again.message  # DUR-B1


def test_retry_carries_the_blockers(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(verdict_block("UNMET")), judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    retry = ex.calls[2]
    assert retry.request.kind == "retry"
    assert "The previous attempt was not accepted" in retry.request.prompt and "c-file" in retry.request.prompt


def test_escalation_pauses_and_proceed_finishes(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "escalation"
    assert out.payload["resume"].startswith("tempergraph resume demo T-1")  # HUM-AC-2
    ex.steps, ex.judges = [REVIEW], [judge()]
    assert resume(two_step(), "T-1", repo, registry(ex), decision="proceed",
                  settings=NO_SLEEP).exit_code is ExitCode.FINISHED


def test_budget_spent_ask_and_stop(repo: Path) -> None:
    fail = verdict_block("UNMET")
    ex = standin("claude", steps=[DRAFT] * 3, judges=[judge(fail)] * 3)
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    spec = two_step()
    units = dict(spec.units)
    units["draft"] = dataclasses.replace(units["draft"], gate=dataclasses.replace(units["draft"].gate,
                                                                                  on_budget_spent="stop"))
    spec = dataclasses.replace(spec, units=units)
    ex2 = standin("claude", steps=[DRAFT] * 3, judges=[judge(fail)] * 3)
    out2 = go(repo, ex2, spec, task="T-2")
    assert out2.exit_code is ExitCode.BUDGET_OR_INFRA and out2.reason == "budget"
    ex2.steps, ex2.judges = [DRAFT, REVIEW], [judge(), judge()]
    back = resume(spec, "T-2", repo, registry(ex2), decision="retry", settings=NO_SLEEP)
    assert back.exit_code is ExitCode.FINISHED  # a stopped thread re-opens through the human node


def test_infra_failure_never_pauses(repo: Path) -> None:
    broken = SessionResult(ok=False, infra_cause=InfraCause.BROKEN_PIPE, usage=Usage())
    ex = standin("claude", steps=[broken] * 3)
    out = go(repo, ex)
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "infra"  # BUD-AC-3
    assert len(ex.calls) == 3 and all(c.kind == "step" for c in ex.calls)


def test_failed_check_starts_no_judge(repo: Path) -> None:
    from tempergraph.api import CheckResult

    spec = two_step()
    units = dict(spec.units)
    gate = dataclasses.replace(units["draft"].gate, check=_callable(failing_check), retry_budget=0)
    units["draft"] = dataclasses.replace(units["draft"], gate=gate)
    ex = standin("claude", steps=[DRAFT])
    out = go(repo, ex, dataclasses.replace(spec, units=units))
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    assert [c.kind for c in ex.calls] == ["step"]  # JDG-AC-2
    del CheckResult


def failing_check(ctx: Any) -> Any:
    from tempergraph.api import CheckResult
    from tempergraph.contracts import CheckFinding

    return CheckResult(result="FAIL", evidence="no file", findings=[CheckFinding(status="fail", criterion="c-file",
                                                                                 place="notes.md", fix="write it")])


def _callable(fn: Any) -> Any:
    from tempergraph.api import callable_ref

    return callable_ref(fn)


def test_outside_call_discards_the_judgement(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge(tools=("Read", "Write"))])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "escalation"  # GRD-AC-3


def test_same_session_discards(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge(sid="s-draft")])
    assert go(repo, ex).exit_code is ExitCode.PAUSED


def test_one_reask_then_escalate(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge("no block"), judge("still none")])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED
    assert [c.request.kind for c in ex.calls] == ["step", "judge", "judge_reask"]  # JDG-AC-3


def test_back_to_an_earlier_unit(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW],
                 judges=[judge(), judge(verdict_block("UNMET", defect_in="notes")), judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    assert [c.kind for c in ex.calls] == ["step", "judge"] * 4
    revisit = ex.calls[4].request.prompt
    assert "Why this unit runs again" in revisit and "sent back by `review`" in revisit


def test_cost_cap_drains_with_exit_5(repo: Path) -> None:
    spec = dataclasses.replace(two_step(), run_cost_cap_usd=0.015)
    ex = standin("claude", steps=[DRAFT], judges=[judge()])
    out = go(repo, ex, spec)
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "cost_cap"
    assert classify(state_root_path(repo), spec, "T-1") is ThreadState.UNFINISHED


def test_decision_refused_writes_nothing(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    go(repo, ex)
    bad = resume(two_step(), "T-1", repo, registry(ex), decision="back:nowhere", settings=NO_SLEEP)
    assert bad.exit_code is ExitCode.USAGE
    assert classify(state_root_path(repo), two_step(), "T-1") is ThreadState.PAUSED


def test_tool_calls_are_recorded(repo: Path) -> None:
    step = dataclasses.replace(DRAFT, tool_calls=[ToolCall(name="Write", ok=True, call_id="1")])
    ex = standin("claude", steps=[step, REVIEW], judges=[judge(), judge()])
    go(repo, ex)
    agent = [r for r in records(repo) if r["kind"] == "agent_run"]
    assert agent[0]["tools"] == ["Write"] and agent[0]["usage"]["reported_cost_usd"] == 0.01


@pytest.mark.parametrize("cause", ["auth"])
def test_auth_escalates_without_retry(repo: Path, cause: str) -> None:
    ex = standin("claude", steps=[SessionResult(ok=False, error_kind=cause, usage=Usage())])  # type: ignore[arg-type]
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["reason"] == cause
    assert len(ex.calls) == 1


def test_resume_writes_one_intervention_row(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    go(repo, ex)
    ex.steps, ex.judges = [REVIEW], [judge()]
    resume(two_step(), "T-1", repo, registry(ex), decision="proceed", feedback="fine as is",
           settings=dataclasses.replace(NO_SLEEP, caller={"kind": "person", "via": "test"}))
    ledger = [json.loads(ln) for ln in (state_root_path(repo) / "ledger.jsonl").read_text().splitlines()]
    rows = [r for r in ledger if r["kind"] == "intervention"]
    assert len(rows) == 1  # HUM-B6
    r = rows[0]
    assert r["touches"] == [{"class": "rescue", "action": "decide"}] and r["pause_kind"] == "escalation"
    assert r["decision"] == "proceed" and r["feedback"] is True and r["caller"]["kind"] == "person"
    assert isinstance(r["wait_s"], float) and len(r["id"]) == 32 and "fine as is" not in json.dumps(r)
    seqs = [rec["seq"] for rec in records(repo) if "seq" in rec]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))  # seq continues across segments (EVT-B2)


def test_touch_classes() -> None:
    from tempergraph.contracts import Decision
    from tempergraph.run.runner import touches

    assert touches("approval", "", Decision.parse("proceed")) == [{"class": "designed", "action": "approve"}]
    assert touches("budget", "", Decision.parse("rewind:draft"))[1] == {"class": "steer", "action": "rewind"}
    assert touches("stopped", "person", Decision.parse("retry")) == [{"class": "steer", "action": "decide"}]


def test_trip_back_records_new_visits(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW],
                 judges=[judge(), judge(verdict_block("UNMET", defect_in="notes")), judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    entered = [(r["unit"], r["visit"], r["entered_from"]) for r in records(repo) if r["kind"] == "unit_entered"]
    assert entered == [("draft", 1, "start"), ("review", 1, "proceed"), ("draft", 2, "back:review"),
                       ("review", 2, "proceed")]  # EVT §2.2
    started = next(r for r in records(repo) if r["kind"] == "run_started")
    assert started["plan_digest"] and started["executors"]["steps"]["draft"] == "claude"
