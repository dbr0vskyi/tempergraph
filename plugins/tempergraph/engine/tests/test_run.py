"""The gate funnel end to end with scripted executors (JDG-AC1–4, GRD-AC3, HUM-AC2, BUD-AC3, DUR-B1,
DUR-B9 resume rows, OBS-B7, OBS-B1, OBS-B8, OBS-B9 records)."""

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
    assert row["workspace"]["mode"] == "worktree"  # the workflow writes files (WTR-B18)
    assert [c.kind for c in ex.calls] == ["step", "judge", "step", "judge"]
    draft_prompt = ex.calls[0].request.prompt
    assert "Release 1.2 notes" in draft_prompt and "## How this output will be judged" in draft_prompt
    assert "Release 1.2 notes" in ex.calls[1].request.prompt  # the judge sees the request
    assert ex.calls[0].request.workdir == Path(row["workspace"]["path"])


def test_fresh_start_on_existing_thread_is_refused(repo: Path) -> None:
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]))
    again = go(repo, standin("claude"))
    assert again.exit_code is ExitCode.USAGE and "resume" in again.message  # DUR-B1


def test_retry_carries_the_blockers(repo: Path) -> None:  # CMP-AC3 (CMP-B1)
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(verdict_block("UNMET")), judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    retry = ex.calls[2]
    assert retry.request.kind == "retry"
    assert "The previous attempt was not accepted" in retry.request.prompt and "c-file" in retry.request.prompt


def test_escalation_pauses_and_proceed_finishes(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "escalation"
    assert out.payload["resume"].startswith("tempergraph resume demo T-1")  # HUM-AC2
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
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "infra"  # BUD-AC3
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
    assert [c.kind for c in ex.calls] == ["step"]  # JDG-AC2
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
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "escalation"  # GRD-AC3


def test_same_session_discards(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge(sid="s-draft")])
    assert go(repo, ex).exit_code is ExitCode.PAUSED


def test_one_reask_then_escalate(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge("no block"), judge("still none")])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED
    assert [c.request.kind for c in ex.calls] == ["step", "judge", "judge_reask"]  # JDG-AC3


def test_back_to_an_earlier_unit(repo: Path) -> None:  # CMP-AC3 (CMP-B12)
    ex = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW],
                 judges=[judge(), judge(verdict_block("UNMET", defect_in="notes")), judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    assert [c.kind for c in ex.calls] == ["step", "judge"] * 4
    revisit = ex.calls[4].request.prompt
    assert "Why this unit runs again" in revisit and "sent back by `review`" in revisit


def test_a_run_at_its_attempt_cap_stops_cleanly_before_the_next_attempt(repo: Path) -> None:  # CMP-AC8 (CMP-B5)
    ex = standin("claude", steps=[DRAFT, DRAFT], judges=[judge(verdict_block("UNMET")), judge()])
    out = go(repo, ex, flags={"run.attempt_cap": 1})  # the draft's retry is the one counted attempt
    assert out.exit_code is ExitCode.STOPPED and out.reason == "attempt_cap", out.message
    assert [c.kind for c in ex.calls] == ["step", "judge", "step", "judge"]  # the review attempt never started
    recs = records(repo)
    assert [r["unit"] for r in recs if r["kind"] == "attempt_start" and r["session_kind"] in ("step", "retry")] == [
        "draft", "draft"]
    (exit_rec,) = [r for r in recs if r["kind"] == "run_exit"]
    assert exit_rec["reason"] == "attempt_cap"  # a clean stop, no engine error
    assert not [r for r in recs if r["kind"] == "engine_error"]
    ex.steps, ex.judges = [REVIEW], [judge()]
    assert resume(two_step(), "T-1", repo, registry(ex), settings=NO_SLEEP).exit_code is ExitCode.FINISHED  # fresh allowance


CLAIM = answer("The notes name no version\nUPSTREAM draft: notes.md names no version", session_id="s-claim")


def test_confirmed_upstream_claim_goes_back_without_a_person(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT, CLAIM, DRAFT, REVIEW], judges=[judge(), judge(), judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED  # BUD-B10: confirmed goes BACK, no pause
    assert [c.kind for c in ex.calls] == ["step", "judge"] * 4
    claim_judge = ex.calls[3].request.prompt
    assert "upstream-claim" in claim_judge and "notes.md names no version" in claim_judge
    assert "- notes: notes.md" in claim_judge  # the subject is the claimed unit's output
    revisit = ex.calls[4].request.prompt
    assert "sent back by `review`" in revisit and "notes.md names no version" in revisit
    judged = [r for r in records(repo) if r["kind"] == "judgement"]
    assert judged[1]["claim"] == "draft"


def test_refuted_upstream_claim_retries_the_step(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT, CLAIM, REVIEW], judges=[judge(), judge(verdict_block("UNMET")), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    assert [c.kind for c in ex.calls] == ["step", "judge", "step", "judge", "step", "judge"]
    assert "upstream-claim" in ex.calls[4].request.prompt  # the retry is told the claim was not confirmed


def test_undecided_upstream_claim_asks_a_person(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT, CLAIM], judges=[judge(), judge(verdict_block("UNVERIFIABLE"))])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED and out.payload["reason"] == "upstream"


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
                       ("review", 2, "proceed")]  # EVT-B10 to EVT-B16
    started = next(r for r in records(repo) if r["kind"] == "run_started")
    assert started["plan_digest"] and started["executors"]["steps"]["draft"] == "claude"


def with_outcome_spec(final_by: str = "judge") -> Any:
    from tempergraph.run.outcome import gate_criteria, parse_outcome

    from .test_outcome import MINIMAL

    data = json.loads(json.dumps(MINIMAL))
    data["final"][0]["verified_by"] = final_by
    data["deliverables"] = [{"key": "verdict", "kind": "value", "where": "review"}]  # stand-ins write no files
    if final_by == "person":
        data["final"][0]["verifier"] = {"role": "release manager", "question": "Safe to publish?"}
    data["intermediate"]["draft"]["criteria"][0]["verified_by"] = "judge"  # the fixture check names c-file only
    o = parse_outcome(data)
    spec = dataclasses.replace(two_step(), outcome=o)
    units = {n: dataclasses.replace(u, gate=dataclasses.replace(u.gate, criteria=tuple(gate_criteria(o, n))))
             for n, u in spec.units.items()}
    return dataclasses.replace(spec, units=units)


def test_outcome_gate_runs_before_the_finalizer(repo: Path) -> None:  # CMP-AC3 (CMP-B15)
    spec = with_outcome_spec()
    met2 = verdict_block("MET", "MET")
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(met2), judge(MET), judge(MET, sid="o")])
    out = go(repo, ex, spec)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [c.kind for c in ex.calls] == ["step", "judge", "step", "judge", "judge"]  # no outcome session
    outcome_prompt = ex.calls[4].request.prompt
    assert "rn-complete" in outcome_prompt and "The request and the deliverables are the truth" in outcome_prompt
    assert "MET means: all four headings" in outcome_prompt  # the scale is rendered (OUT-B11)


def test_missing_deliverable_fails_the_outcome_check(repo: Path) -> None:
    spec = with_outcome_spec()
    o = dataclasses.replace(spec.outcome, deliverables=({"key": "notes", "kind": "file", "where": "notes.md"},))
    spec = dataclasses.replace(spec, outcome=o)
    met2 = verdict_block("MET", "MET")
    ex = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW], judges=[judge(met2), judge(MET)] * 2)
    out = go(repo, ex, spec)
    checks = [r for r in records(repo) if r["kind"] == "check" and r["unit"] == "outcome"]
    assert checks[0]["result"] == "FAIL" and "0 of 1 deliverables" in checks[0]["evidence"]
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"  # loop budget 1, then ask


def test_failing_outcome_goes_back_to_the_serving_unit(repo: Path) -> None:
    spec = with_outcome_spec()
    met2 = verdict_block("MET", "MET")
    ex = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW],
                 judges=[judge(met2), judge(MET), judge(verdict_block("UNMET")), judge(met2), judge(MET),
                         judge(MET, sid="o2")])
    assert go(repo, ex, spec).exit_code is ExitCode.FINISHED
    entered = [(r["unit"], r["entered_from"]) for r in records(repo) if r["kind"] == "unit_entered"]
    assert ("draft", "back:outcome") in entered  # derived from `serves` (OUT-B3)


def test_person_criterion_pauses_for_sign_off(repo: Path) -> None:
    spec = with_outcome_spec("person")
    met2 = verdict_block("MET", "MET")
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(met2), judge(MET)])
    out = go(repo, ex, spec)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "approval"
    assert out.payload["sign_off"][0]["question"] == "Safe to publish?"  # OUT-B4


def test_cost_so_far_on_gate_pause_and_exit(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    go(repo, ex)
    recs = {r["kind"]: r for r in records(repo)}
    for kind in ("gate", "pause", "run_exit"):
        c = recs[kind]["cost_so_far"]
        assert c["reported"] == pytest.approx(0.02) and c["completeness"] in ("complete", "estimated")  # EVT-B10 to EVT-B16


def hybrid(before: tuple[Any, ...] = (), after: tuple[Any, ...] = ()) -> Any:
    spec = two_step()
    d = spec.units["draft"]
    assert d.step is not None
    step = dataclasses.replace(d.step, before=before, after=after)
    return dataclasses.replace(spec, units={**spec.units, "draft": dataclasses.replace(d, step=step)})


def test_hybrid_order_before_session_after(repo: Path) -> None:
    from tempergraph.contracts import ScriptSpec

    fetch = ScriptSpec(run=("git", "status"), name="fetch")
    publish = ScriptSpec(run=("git", "status"), name="publish")
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, hybrid((fetch,), (publish,))).exit_code is ExitCode.FINISHED
    seq = [(r["kind"], r.get("phase"), r.get("name")) for r in records(repo)
           if r["kind"] in ("script", "agent_run") and r.get("unit", "draft") == "draft"][:3]
    assert seq == [("script", "before", "fetch"), ("agent_run", None, None), ("script", "after", "publish")]  # SCR-B2


def test_failed_before_script_spends_a_retry_without_a_session(repo: Path) -> None:
    from tempergraph.contracts import ScriptSpec

    bad = ScriptSpec(run=("git", "no-such-subcommand"), name="fetch")
    ex = standin("claude", steps=[], judges=[])
    out = go(repo, ex, hybrid((bad,)))
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    assert ex.calls == []  # no session ran; three failed attempts spent the budget of 2
    assert "script_failed:fetch" in json.dumps(out.payload["blockers"])


def test_auto_reopen_retries_a_stopped_run(repo: Path) -> None:  # BUD-B6
    broken = SessionResult(ok=False, infra_cause=InfraCause.BROKEN_PIPE, usage=Usage())
    ex = standin("claude", steps=[broken] * 3 + [DRAFT, REVIEW], judges=[judge(), judge()])
    out = go(repo, ex, flags={"run.auto_reopen": 2})
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert "auto_reopen: infra" in out.warnings
    ledger = [json.loads(x) for x in (state_root_path(repo) / "ledger.jsonl").read_text().splitlines()]
    row = [r for r in ledger if r["kind"] == "intervention"]
    assert len(row) == 1 and row[0]["cause"] == "auto_reopen" and row[0]["wait_s"] is None
    assert row[0]["caller"]["kind"] == "engine" and row[0]["touches"] == [{"class": "engine", "action": "reopen"}]
    sup = [r for r in records(repo) if r["kind"] == "supervision"][-1]
    assert sup["level"] == "observer" and sup["touches"]["engine"]["engine"] == 1  # never supervision


def test_auto_reopen_stops_at_its_count(repo: Path) -> None:  # BUD-B6
    broken = SessionResult(ok=False, infra_cause=InfraCause.BROKEN_PIPE, usage=Usage())
    ex = standin("claude", steps=[broken] * 9)
    out = go(repo, ex, flags={"run.auto_reopen": 2}, task="T-2")
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "infra"
    assert out.warnings.count("auto_reopen: infra") == 2 and len(ex.calls) == 9


def test_auto_reopen_never_answers_a_pause(repo: Path) -> None:  # BUD-B6
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    out = go(repo, ex, flags={"run.auto_reopen": 3}, task="T-3")
    assert out.exit_code is ExitCode.PAUSED and not any("auto_reopen" in w for w in out.warnings)


def test_a_retry_never_changes_the_model(repo: Path) -> None:  # BUD-B7: no retry-count ladder (LAD-B18)
    fail = verdict_block("UNMET")
    broken = SessionResult(ok=False, infra_cause=InfraCause.BROKEN_PIPE, usage=Usage())
    ex = standin("claude", steps=[DRAFT, broken, DRAFT, DRAFT, DRAFT], judges=[judge(fail)] * 4)
    spec = two_step()
    units = dict(spec.units)
    units["draft"] = dataclasses.replace(units["draft"], step=dataclasses.replace(units["draft"].step, model="small"))
    spec = dataclasses.replace(spec, units=units)
    out = go(repo, ex, spec, flags={"draft.retry_budget": 3}, task="L-1")
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    aliases = [(r["session_key"], r["alias"]) for r in records(repo, "L-1") if r["kind"] == "attempt_start"]
    assert [a for k, a in aliases if "judge" not in k] == ["small"] * 5  # four attempts and one infra rerun
    assert {a for k, a in aliases if "judge" in k} == {"small"}  # the judge inherits the step's alias (CON-B3)


def test_workspace_records(repo: Path) -> None:  # EVT-B10 to EVT-B16 `workspace`, WTR-B22
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex, task="W-1").exit_code is ExitCode.PAUSED
    ex.steps, ex.judges = [REVIEW], [judge()]
    assert resume(two_step(), "W-1", repo, registry(ex), decision="proceed",
                  settings=NO_SLEEP).exit_code is ExitCode.FINISHED
    ws = [r for r in records(repo, "W-1") if r["kind"] == "workspace"]
    assert [r["action"] for r in ws] == ["prepared", "reused", "kept"]
    assert ws[0]["mode"] == "worktree" and ws[0]["branch"] == "tg/demo/W-1" and ws[0]["path"]
    ledger = (state_root_path(repo) / "ledger.jsonl").read_text()
    assert ws[0]["path"] not in ledger  # the path stays in the local run log


def _thread_values(repo: Path, task: str) -> dict[str, Any]:
    from tempergraph.durability.checkpoint import observer_graph, open_readonly, snapshot
    from tempergraph.run.outcome import with_outcome

    with open_readonly(state_root_path(repo) / "checkpoints" / "demo.sqlite") as saver:
        assert saver is not None
        return dict(snapshot(observer_graph(with_outcome(two_step()), saver), f"demo/{task}").values)


def test_a_worktree_that_appears_during_a_session_is_recorded_and_left(repo: Path, tmp_path: Path) -> None:
    # WTR-AC6 (WTR-B26, WTR-B13): a `foreign` record, an attempt warning and a `foreign_worktrees` fact; nothing removed
    import subprocess

    made = tmp_path / "agent-x"

    def subagent(req: Any) -> Any:
        subprocess.run(["git", "worktree", "add", "-q", "-b", "agent-x", str(made), "HEAD"], cwd=req.workdir,
                       check=True, capture_output=True)
        return DRAFT

    ex = standin("claude", steps=[subagent, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, task="F-1").exit_code is ExitCode.FINISHED
    foreign = [r for r in records(repo, "F-1") if r["kind"] == "workspace" and r["action"] == "foreign"]
    assert len(foreign) == 1
    assert foreign[0]["path"] == "agent-x" and foreign[0]["branch"] == "agent-x"  # relative to the repository's parent
    assert foreign[0]["session_key"].startswith("draft") and foreign[0]["unit"] == "draft"
    assert made.is_dir() and "agent-x" in subprocess.run(["git", "worktree", "list"], cwd=repo, capture_output=True,
                                                         text=True).stdout  # never removed
    values = _thread_values(repo, "F-1")
    assert values["attempts"]["draft"]["warnings"] == ["foreign_worktree: agent-x"]
    assert values["facts"]["draft"]["foreign_worktrees"] == ["agent-x"]  # the check and the judge can read it


def test_no_foreign_record_when_no_worktree_appears(repo: Path) -> None:  # WTR-AC6 (WTR-B26)
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, task="F-2").exit_code is ExitCode.FINISHED
    assert [r for r in records(repo, "F-2") if r["kind"] == "workspace" and r["action"] == "foreign"] == []
    assert "warnings" not in _thread_values(repo, "F-2")["attempts"]["draft"]
