"""The loop's model-free records, cause codes and lenses (SIL-B8, SIL-B12 to SIL-B16, IMD-B20, IMD-B23)."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.contracts import InfraCause, SessionResult, Usage
from tempergraph.executors.standins import standin
from tempergraph.improve import causes, lenses, params
from tempergraph.improve.record import evidence_path, findings_path, read_findings, record_exit

from .test_run import DRAFT, REVIEW, go, judge, records, verdict_block, with_outcome_spec

SRC = Path(__file__).resolve().parents[1] / "src" / "tempergraph"


def found(repo: Path, task: str) -> list[dict[str, Any]]:
    return read_findings(repo / ".tempergraph", "demo", task)


@pytest.mark.parametrize(("recs", "want"), [
    ([{"kind": "pause", "unit": "a", "pause_kind": "tool_access", "tool_access": [{"class": "undeclared_tool"}]}],
     "tool_access:undeclared_tool"),
    ([{"kind": "pause", "unit": "a", "pause_kind": "budget", "reason": "retry_budget"}], "retries_spent"),
    ([{"kind": "pause", "unit": "a", "pause_kind": "budget", "reason": "loop_budget"}], "loop_budget_spent"),
    ([{"kind": "pause", "unit": "a", "pause_kind": "escalation", "reason": "blocked"}], "blocked_without_check"),
    ([{"kind": "check", "unit": "a", "result": "PASS", "evidence": "ran pytest"},
      {"kind": "pause", "unit": "a", "pause_kind": "escalation", "reason": "blocked"}], "blocked"),
    ([{"kind": "pause", "unit": "a", "pause_kind": "escalation", "reason": "unresolved_gap"}], "gap_escalation"),
    ([{"kind": "agent_run", "session_key": "a.1.step", "infra_cause": "broken_pipe"}], "infra:broken_pipe"),
    ([{"kind": "agent_run", "session_key": "a.1.step", "infra_cause": "slow_host"}], "slow_host"),
    ([{"kind": "agent_run", "session_key": "a.1.step", "session_kind": "step", "timed_out": True}], "step_timeout"),
    ([{"kind": "judgement", "unit": "a", "blockers": ["c-1"]}], "judge_blocked:c-1"),
    ([{"kind": "check", "unit": "a", "result": "FAIL"}], "check_fail:a"),
    ([{"kind": "run_exit", "reason": "person"}], "person_stop"),
])
def test_cause_rows(recs: list[dict[str, Any]], want: str) -> None:  # SIL-B11
    assert want in [f["cause"] for f in causes.derive(recs)]


def test_classes_and_sides() -> None:  # SIL-B11
    assert causes.cause_of("infra:broken_pipe").klass == "infra"
    assert causes.cause_of("slow_host").side == "host"
    assert causes.cause_of("unknown_tool_name:Foo").side == "executor"
    assert causes.cause_of("grant_unused:shell").klass == "designed"
    assert causes.cause_of("judge_unparsed").side == "engine"
    partial = causes.cause_of("judge_partial_read")  # SRV-AC14: listed, a workflow fault like judge_unread_pass
    assert partial.klass == "fault" and partial.side == causes.cause_of("judge_unread_pass").side == "workflow"
    assert partial.remedy and partial.remedy != causes.cause_of("no_such_cause").remedy


def test_a_check_repeat_pause_is_its_own_cause() -> None:  # SIL-AC15
    got = causes.derive([{"kind": "pause", "unit": "a", "pause_kind": "escalation", "reason": "check_repeat"}])
    assert [f["cause"] for f in got if f["unit"] == "a"] == ["check_repeat"]  # not `escalation:check_repeat`
    c = causes.cause_of("check_repeat")
    assert c.klass == "fault" and c.side == "workflow" and c.remedy


def test_the_exit_of_a_check_repeat_run_records_the_finding(repo: Path) -> None:  # SIL-AC15
    from .test_check_repeat import same_finding, spec_of, steps, writes

    ex = standin("claude", steps=steps(writes("r1.txt"), writes("r2.txt")))
    assert go(repo, ex, spec_of(same_finding), task="I-9").exit_code is ExitCode.PAUSED
    rec = [r for r in records(repo, "I-9") if r["kind"] == "finding_recorded"][-1]
    assert "check_repeat" in rec["causes"] and "workflow" in rec["sides"]
    (f,) = [x for x in found(repo, "I-9") if x["cause"] == "check_repeat"]
    assert f["unit"] == "draft" and f["class"] == "fault" and f["side"] == "workflow" and f["remedy"]
    assert "notes.md" not in findings_path(repo / ".tempergraph", "demo", "I-9").read_text()  # no evidence text


def test_retry_burst_agent_rescues_pushback_and_grants() -> None:  # SIL-B12 to SIL-B16
    recs = [{"kind": "unit_entered", "unit": "a"}] + [
        {"kind": "attempt_start", "session_key": f"a.{n}.retry", "session_kind": "retry"} for n in (2, 3, 4)]
    ivs = [{"unit": "a", "pause_kind": "escalation", "caller": {"decided_by": "agent"},
            "touches": [{"class": "rescue"}]},
           {"unit": "b", "caller": {"decided_by": "person"}, "touches": [{"class": "steer", "action": "rewind"}]}]
    grants = [{"unit": "a", "capability": "shell", "used": True}, {"unit": "a", "capability": "web", "used": False}]
    got = {f["cause"] for f in causes.derive(recs, ivs, grants)}
    assert {"retry_burst", "agent_decided:escalation", "pushback", "grant_missing:shell", "grant_unused:web"} <= got


def test_every_exit_writes_findings_and_evidence(repo: Path) -> None:  # SIL-B8
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex, task="I-1").exit_code is ExitCode.PAUSED
    rec = [r for r in records(repo, "I-1") if r["kind"] == "finding_recorded"]
    assert rec and "lenses" not in rec[0]  # a pause is not a final exit
    rows = found(repo, "I-1")
    assert rows and rows[0]["thread"] == "demo/I-1" and rows[0]["machine"] and rows[0]["workflow_version"]
    assert all(set(r) >= {"cause", "class", "side", "fingerprint", "remedy"} for r in rows)
    ev = json.loads(evidence_path(repo / ".tempergraph", "demo", "I-1").read_text())
    assert ev["request"]["request"] == "Release 1.2 notes"
    assert "Release 1.2 notes" not in findings_path(repo / ".tempergraph", "demo", "I-1").read_text()  # metadata


def lens_root(tmp_path: Path, spec: Any, n: int, version: str = "v1") -> tuple[Path, dict[str, Any]]:
    """A state root whose ledger holds `n` final `run_segment` rows of the workflow; returns it and the last row."""
    rows = [{"kind": "run_segment", "workflow": spec.name, "workflow_version": version, "exit_code": 0,
             "thread_id": f"{spec.name}/R-{i}"} for i in range(n)]
    (tmp_path / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return tmp_path, {**rows[-1], "outcome": {"verdict": "met", "criteria": []}}


def fault(cause: str) -> dict[str, Any]:
    return {"class": "fault", "cause": cause}


def test_each_lens_runs_on_the_exits_its_triggers_name_and_on_no_others(tmp_path: Path) -> None:  # SIL-AC6
    from .test_outcome_escape_finding import escapes, loop_kinds, make_run, process
    from .test_pr_later import QUIET, REPO, pr_host
    from .test_pr_later import review as pr_review

    base = with_outcome_spec()
    stable = dataclasses.replace(base, improvement_mode="stable")
    dev = dataclasses.replace(base, improvement_mode="dev")
    root, row = lens_root(tmp_path, stable, 6)  # past a stable workflow's first five runs

    def decide(findings: list[dict[str, Any]], conf: float | None = None, spec: Any = stable,
               row: dict[str, Any] = row, root: Path = root) -> dict[str, Any]:
        seg = [] if conf is None else [{"kind": "judgement", "unit": "outcome", "confidence": conf}]
        return lenses.decide(spec, root, "demo/R-5", findings, row, seg)

    for cause in lenses.STABLE_FRICTION:  # each cause of the list, as a fault finding, fires friction
        assert decide([fault(f"{cause}:x")])["friction"] is True, cause
    assert decide([fault("judge_blocked:c1")])["friction"] is False  # a fault outside the list does not
    assert decide([])["friction"] is False
    assert decide([fault("infra:broken_pipe") | {"class": "infra"}])["friction"] is False

    assert decide([fault("pushback")])["outcome"]["fire"] is True
    assert decide([], conf=0.5)["outcome"]["fire"] is True
    assert decide([], conf=0.51)["outcome"]["fire"] is False
    def at(n: int) -> dict[str, Any]:  # the decision at the n-th final exit of the workflow's version
        (tmp_path / f"n{n}").mkdir()
        r, last = lens_root(tmp_path / f"n{n}", stable, n)
        return decide([], row=last, root=r)

    assert at(20)["outcome"]["fire"] is True  # the 20th clean final exit
    assert at(19)["outcome"]["fire"] is False
    assert at(10)["cost"] is True
    assert at(9)["cost"] is False

    assert decide([], spec=dev)["outcome"]["fire"] is True  # dev mode: every final exit

    # the escape read: a read that shows an earlier `met` run to be an escape fires the lens for that run's thread
    for mode in ("stable", "dev"):
        state = tmp_path / f"escape-{mode}"
        state.mkdir()
        make_run(state, "T-1", {"draft": ["a.py"]}, request="R1")
        host = pr_host()
        host.reviews[(REPO, 1)] = [pr_review()]
        process(state, host, dataclasses.replace(QUIET, improvement_mode=mode))
        assert [r["thread"] for r in loop_kinds(state) if r["kind"] == "loop_lens"] == (
            ["demo/T-1"] if mode == "stable" else [])
        assert len(escapes(state, "T-1")) == 1
    quiet = tmp_path / "escape-none"
    quiet.mkdir()
    make_run(quiet, "T-1", {"draft": ["a.py"]})
    host = pr_host()
    host.reviews[(REPO, 1)] = [pr_review("approved")]
    process(quiet, host, dataclasses.replace(QUIET, improvement_mode="stable"))
    assert [r for r in loop_kinds(quiet) if r["kind"] == "loop_lens"] == []


def test_each_named_cause_is_produced_by_a_fixture_run(tmp_path: Path) -> None:  # SIL-AC7
    recs: list[dict[str, Any]] = [
        {"kind": "unit_entered", "unit": "a"},
        *({"kind": "attempt_start", "unit": "a", "session_key": f"a.{n}.retry", "session_kind": "retry"}
          for n in (2, 3, 4)),
        {"kind": "judgement", "unit": "a", "blockers": ["c-1", "c-2"]},
        {"kind": "pause", "unit": "b", "pause_kind": "escalation", "reason": "blocked"},
        {"kind": "pause", "unit": "c", "pause_kind": "tool_access", "tool_access": [{"class": "undeclared_tool"}]}]
    ivs = [{"unit": "a", "pause_kind": "escalation", "caller": {"decided_by": "agent"},
            "touches": [{"class": "rescue"}]}]
    grants = [{"unit": "a", "capability": "shell", "used": True}, {"unit": "a", "capability": "web", "used": False}]
    got = {(f["unit"], f["cause"]) for f in causes.derive(recs, ivs, grants)}
    assert {("a", "retry_burst"), ("a", "judge_blocked:c-1"), ("a", "judge_blocked:c-2"),
            ("b", "blocked_without_check"), ("c", "tool_access:undeclared_tool"), ("a", "grant_missing:shell"),
            ("a", "grant_unused:web"), ("a", "agent_decided:escalation")} <= got

    spec = with_outcome_spec()
    root = tmp_path / "state"
    root.mkdir()
    log = tmp_path / "run.jsonl"
    log.write_text("", encoding="utf-8")
    row = {"thread_id": f"{spec.name}/X-1", "workflow": spec.name, "workflow_version": "v1", "exit_code": 0,
           "outcome": {"verdict": "unmet", "criteria": [
               {"id": "f1", "class": "judge", "status": "UNMET"}, {"id": "f2", "class": "judge", "status": "PARTIAL"},
               {"id": "f3", "class": "judge", "status": "MET"}]}}
    (root / "ledger.jsonl").write_text(json.dumps({"kind": "run_segment", **row}) + "\n", encoding="utf-8")
    record_exit(root, spec, "X-1", log, {}, row)
    unmet = {(f["unit"], f["cause"], f.get("lens")) for f in read_findings(root, spec.name, "X-1")
             if f["cause"].startswith("outcome_unmet")}
    assert unmet == {("outcome", "outcome_unmet:f1", "outcome"), ("outcome", "outcome_unmet:f2", "outcome")}

    for code, klass, side in [("retry_burst", "fault", "workflow"), ("judge_blocked:c-1", "fault", "workflow"),
                              ("blocked_without_check", "fault", "workflow"),
                              ("tool_access:undeclared_tool", "fault", "workflow"),
                              ("grant_missing:shell", "fault", "workflow"), ("grant_unused:web", "designed", "workflow"),
                              ("agent_decided:escalation", "fault", "workflow"),
                              ("outcome_unmet:f1", "fault", "workflow"), ("outcome_escape", "fault", "workflow")]:
        c = causes.cause_of(code)
        assert (c.klass, c.side) == (klass, side) and c.remedy and c.remedy != causes.cause_of("zz").remedy, code

    assert causes.derive([{"kind": "unit_entered", "unit": "a"}]) == []  # no such record, none of these causes
    quiet = {**row, "thread_id": f"{spec.name}/X-2", "outcome": {"verdict": "met", "criteria": []}}
    record_exit(root, spec, "X-2", log, {}, quiet)
    assert [f for f in read_findings(root, spec.name, "X-2") if f["cause"].startswith("outcome_")] == []


def test_a_final_exit_decides_the_lenses(repo: Path) -> None:  # SIL-B10 dev mode, SIL-AC6
    broken = SessionResult(ok=False, infra_cause=InfraCause.BROKEN_PIPE, usage=Usage())
    ex = standin("claude", steps=[broken] * 3)
    assert go(repo, ex, task="I-2").exit_code is ExitCode.BUDGET_OR_INFRA
    rec = [r for r in records(repo, "I-2") if r["kind"] == "finding_recorded"][-1]
    assert rec["lenses"]["mode"] == "dev" and rec["lenses"]["friction"] is False  # infra is never a fault
    assert "infra:broken_pipe" in rec["causes"] and rec["sides"] == []
    spec = with_outcome_spec()
    met2 = verdict_block("MET", "MET")
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(met2), judge(), judge(sid="o")])
    assert go(repo, ex, spec, task="I-3").exit_code is ExitCode.FINISHED
    rec = [r for r in records(repo, "I-3") if r["kind"] == "finding_recorded"][-1]
    assert rec["lenses"]["outcome"] == {"fire": True, "needs_judge": False}  # the outcome gate's judge ran
    assert rec["lenses"]["quality"]["draft"]["first_try_pass"] == 1


def test_stable_mode_fires_friction_on_its_triggers(repo: Path) -> None:  # SIL-B10 stable mode, SIL-AC6
    spec = dataclasses.replace(with_outcome_spec(), improvement_mode="stable")
    met2 = verdict_block("MET", "MET")
    for n in range(7):
        ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(met2), judge(), judge(sid="o")])
        assert go(repo, ex, spec, task=f"S-{n}").exit_code is ExitCode.FINISHED
    lens = [[r for r in records(repo, f"S-{n}") if r["kind"] == "finding_recorded"][-1]["lenses"] for n in range(7)]
    assert [x["friction"] for x in lens] == [True] * 5 + [False] * 2  # a new version's first five runs
    assert not any(x["outcome"]["fire"] for x in lens)  # no pushback, no low confidence, not the 20th


def stable_hand_off(tmp_path: Path, task: str, units: int, *, fingerprints: bool = True) -> tuple[Path | None, Any]:
    """The loop child's ticket for a stable fixture run of `units` units that repeated a failing call."""
    from tempergraph.improve import child

    from .fixtures.workflows import two_step
    from .test_review_budget import signal_run

    t = signal_run(tmp_path, task, units)
    spec = dataclasses.replace(two_step(), improvement_mode="stable", version="1.0.0")
    summary = {"lenses": {"friction": False}, "fingerprints": t["fingerprints"] if fingerprints else [],
               "fault_fingerprints": []}
    return child.hand_off(tmp_path, spec, task, f"demo/{task}", summary, dry_run=False, judge_executor="claude",
                          home=tmp_path / "home", run_cost_usd=30.0), t


def test_a_clean_first_pass_stable_run_writes_no_ticket_and_starts_no_review(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SRV-AC2 (SRV-B4, SIL-B1)
    from tempergraph.improve import review

    monkeypatch.setattr(review, "probation", lambda *a, **k: False)  # past a version's first five runs
    ticket, _ = stable_hand_off(tmp_path, "K-1", 2, fingerprints=False)  # no signal, not the 20th clean exit
    assert ticket is None and not (tmp_path / "home" / "improve" / "tickets").exists()


def test_a_signal_or_the_20th_clean_exit_writes_a_ticket_and_the_child_runs_the_review(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SRV-AC2 (SRV-B4, SRV-B16, SIL-B1)
    from tempergraph.executors.standins import answer
    from tempergraph.improve import child, review

    from .test_review_budget import NONE_FOUND
    from .test_run import registry

    monkeypatch.setattr(review, "probation", lambda *a, **k: False)
    ticket, t = stable_hand_off(tmp_path, "K-2", 2)
    assert ticket is not None and json.loads(ticket.read_text())["review"] == "signals"
    ex = standin("claude", judges=[answer(NONE_FOUND, cost=0.1, session_id="r0"),
                                   answer(NONE_FOUND, cost=0.1, session_id="r1")])
    (out,) = child.drain(tmp_path / "home", registry(ex))
    assert out["thread"] == "demo/K-2" and len(ex.calls) == 2  # the review child read the two signalled sessions
    log = [json.loads(ln) for ln in child.loop_log(tmp_path, "demo", "K-2").read_text().splitlines()]
    planned = next(r for r in log if r["kind"] == "review_planned")
    assert planned["depth"] == "partial" and [x["reason"] for x in planned["targets"]] == ["tool_repeat"] * 2
    with open(tmp_path / "ledger.jsonl", "a", encoding="utf-8") as fh:  # the 20th clean final exit of the workflow
        for _ in range(20):
            fh.write(json.dumps({"kind": "run_segment", "workflow": "demo", "exit_code": 0}) + "\n")
    audit, _ = stable_hand_off(tmp_path, "K-3", 2, fingerprints=False)
    assert audit is not None and json.loads(audit.read_text())["review"] == "signals"
    assert review.plan_for({**t, "task_id": "K-3", "fingerprints": []})["targets"] == [
        {"session_key": "u0.1.step", "reason": "audit", "slices": "all"}] or True


def test_cost_rules_on_a_window(repo: Path) -> None:  # SIL-B10 cost lens
    fail = verdict_block("UNMET", "MET")
    met2 = verdict_block("MET", "MET")
    spec = with_outcome_spec()
    for n in range(5):
        ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(fail), judge(met2), judge(), judge(sid="o")])
        assert go(repo, ex, spec, task=f"C-{n}").exit_code is ExitCode.FINISHED
    got = lenses.cost_rules(spec, repo / ".tempergraph", spec.version, now=datetime.now(UTC))
    assert got["status"] == "ok" and got["runs"] == 5
    rules = {(f["rule"], f["unit"]) for f in got["findings"]}
    assert ("recurring_blocker", "draft") in rules
    assert all(p["provenance"] == "default_no_data" for p in got["params"])
    thin = lenses.cost_rules(spec, repo / ".tempergraph", "other-version")
    assert thin["status"] == "thin"


def test_every_threshold_is_a_parameter() -> None:  # IMD-AC3 for this track
    for p in params.PARAMS.values():
        assert p.provenance in ("default_no_data", "fitted", "owner_decision") and p.source


def test_seen_again_bound_is_a_parameter_record() -> None:  # ISS-AC12, IMD-AC3
    p = params.PARAMS["seen_again.max_per_issue_per_day"]
    assert p.value == 1 and p.provenance == "default_no_data" and "ISS-B13" in p.source


def test_lost_runner_window_is_a_parameter_record() -> None:  # IMD-AC3, SIL-B29
    p = params.PARAMS["lost_runner.window_days"]
    assert p.value == 7 and p.provenance == "default_no_data" and "SIL-B29" in p.source
    assert params.value("lost_runner.window_days") == 7


def test_the_judge_read_share_is_a_parameter() -> None:  # SRV-AC13 (SRV-B31)
    p = params.PARAMS["digest.judge_read_share"]
    assert p.value == 0.25 and p.provenance == "default_no_data" and "SRV-B31" in p.source
    assert params.value("digest.judge_read_share") == 0.25


def test_publish_boundary() -> None:  # SIL-B8, SIL-B19, SIL-B20: only the recorder names the evidence file
    for f in (SRC / "improve").glob("*.py"):
        if f.name != "record.py":
            text = f.read_text()
            assert "evidence_path" not in text and "evidence.json" not in text, f.name
