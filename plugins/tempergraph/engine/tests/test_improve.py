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
from tempergraph.improve.record import evidence_path, findings_path, read_findings

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


def test_a_final_exit_decides_the_lenses(repo: Path) -> None:  # SIL-B10 dev mode
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


def test_stable_mode_fires_friction_on_its_triggers(repo: Path) -> None:  # SIL-B10 stable mode
    spec = dataclasses.replace(with_outcome_spec(), improvement_mode="stable")
    met2 = verdict_block("MET", "MET")
    for n in range(7):
        ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(met2), judge(), judge(sid="o")])
        assert go(repo, ex, spec, task=f"S-{n}").exit_code is ExitCode.FINISHED
    lens = [[r for r in records(repo, f"S-{n}") if r["kind"] == "finding_recorded"][-1]["lenses"] for n in range(7)]
    assert [x["friction"] for x in lens] == [True] * 5 + [False] * 2  # a new version's first five runs
    assert not any(x["outcome"]["fire"] for x in lens)  # no pushback, no low confidence, not the 20th


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


def test_publish_boundary() -> None:  # SIL-B8, SIL-B19, SIL-B20: only the recorder names the evidence file
    for f in (SRC / "improve").glob("*.py"):
        if f.name != "record.py":
            text = f.read_text()
            assert "evidence_path" not in text and "evidence.json" not in text, f.name
