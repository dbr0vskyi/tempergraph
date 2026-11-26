"""A person's stop of a paused thread is an exit the loop reads with the pauses before it (SIL-B27, SIL-B28)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph import detach
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child, review
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import read_findings
from tempergraph.run.runner import RunSettings, ledger_rows, resume
from tempergraph.store.layout import home_path, run_dir, state_root_path

from .fixtures.workflows import two_step
from .test_run import DRAFT, REVIEW, go, judge, registry, verdict_block

NO_SLEEP = RunSettings(sleep=lambda s: None)
FAIL = verdict_block("UNMET")


def loop_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr(detach, "start", lambda *a, **k: True)  # the child is started by drain() in the test


def tickets() -> list[Path]:
    return sorted(child.tickets_dir(home_path()).glob("*.json"))


def no_retries(spec: Any) -> Any:
    """`draft` gets no retry, so one attempt and its judge are the whole first segment."""
    units = dict(spec.units)
    units["draft"] = dataclasses.replace(units["draft"], gate=dataclasses.replace(units["draft"].gate, retry_budget=0))
    return dataclasses.replace(spec, units=units)


def paused_on_retries(repo: Path, task: str, spec: Any = None) -> Any:
    """A first segment that pauses at `draft` with its retries spent."""
    work = answer("Wrote notes.md\nARTIFACT notes: notes.md", tools=("Read",), session_id="s-draft")  # a turn to read
    n = 1 if spec is not None and spec.units["draft"].gate.retry_budget == 0 else 3
    ex = standin("claude", steps=[work] * n, judges=[judge(FAIL)] * n)
    out = go(repo, ex, spec, task=task)
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget", out.message
    return ex


def stop(repo: Path, task: str, ex: Any, spec: Any = None) -> Any:
    return resume(spec or two_step(), task, repo, registry(ex), decision="stop", settings=NO_SLEEP)


def asks() -> tuple[list[str], Any]:
    """A stand-in friction judge that keeps the prompts it is asked."""
    seen: list[str] = []

    def reply(req: Any) -> Any:
        seen.append(req.prompt)
        return answer("```json\n" + json.dumps({"findings": []}) + "\n```", session_id="loop")
    return seen, reply


def segment_rows(repo: Path, task: str) -> list[dict[str, Any]]:
    return [r for r in ledger_rows(state_root_path(repo)) if r.get("kind") == "run_segment"
            and r.get("thread_id") == f"demo/{task}"]


def recorded(repo: Path, task: str) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == "finding_recorded"]


def test_a_stop_at_a_gate_after_retries_spent_tickets_the_friction_lens(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC19, SIL-AC18, AC 2
    loop_on(monkeypatch)
    ex = paused_on_retries(repo, "P-1")
    assert tickets() == [] and [r["exit_code"] for r in segment_rows(repo, "P-1")] == [3]
    out = stop(repo, "P-1", ex)
    assert out.exit_code is ExitCode.STOPPED and out.reason == "person"
    rows = segment_rows(repo, "P-1")
    assert [r["exit_code"] for r in rows] == [3, 4] and rows[-1]["reason"] == "person"
    assert len(recorded(repo, "P-1")) == 2
    (t,) = tickets()
    doc = json.loads(t.read_text())
    assert doc["lenses"]["friction"] is True
    seen, reply = asks()
    child.drain(registry=registry(standin("claude", judges=[reply])), host=lambda: MemoryCodeHost())
    (prompt,) = seen
    assert "cause `retries_spent`" in prompt and "unit `draft`" in prompt


def test_a_stop_keeps_the_earlier_pause_findings_in_the_tickets_fingerprints(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC19, SIL-AC20, AC 7
    loop_on(monkeypatch)
    ex = paused_on_retries(repo, "P-4")
    assert stop(repo, "P-4", ex).exit_code is ExitCode.STOPPED
    (t,) = tickets()
    doc = json.loads(t.read_text())
    paused = {f["fingerprint"] for f in read_findings(state_root_path(repo), "demo", "P-4")
              if f["cause"] == "retries_spent" and f.get("segment_exit") == 3}
    assert paused and paused <= set(doc["fingerprints"])  # the review plan reads its signals from here
    assert not doc.get("pause_fingerprints")


def test_stable_mode_stop_plans_a_partial_review_of_the_paused_unit(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC20, AC 2
    loop_on(monkeypatch)
    monkeypatch.setattr(review, "probation", lambda *a, **k: False)  # past a version's first five runs
    spec = no_retries(dataclasses.replace(two_step(), improvement_mode="stable"))
    ex = paused_on_retries(repo, "P-2", spec)
    assert stop(repo, "P-2", ex, spec).exit_code is ExitCode.STOPPED
    (t,) = tickets()
    doc = json.loads(t.read_text())
    plan = review.plan_for(doc)
    assert plan["depth"] == "partial", plan
    runs = [r for r in map(json.loads, (run_dir(state_root_path(repo), "demo", "P-2") / "run.jsonl")
                           .read_text().splitlines()) if r["kind"] == "agent_run"
            and str(r["session_key"]).startswith("draft.")]
    last_attempt = [r["session_key"] for r in runs if r["session_kind"] in ("step", "retry")][-1]
    last_judge = [r["session_key"] for r in runs if str(r["session_kind"]).startswith("judge")][-1]
    assert {x["session_key"] for x in plan["targets"]} == {last_attempt, last_judge}
    assert "retries_spent" in {x["reason"] for x in plan["targets"]}  # the pause's finding is a signal of the stop


def test_a_second_stop_judges_the_second_pause_only(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC21, AC 1
    loop_on(monkeypatch)
    ex = paused_on_retries(repo, "P-3")
    assert stop(repo, "P-3", ex).exit_code is ExitCode.STOPPED
    first, reply1 = asks()
    child.drain(registry=registry(standin("claude", judges=[reply1])), host=lambda: MemoryCodeHost())
    assert len(first) == 1 and "cause `retries_spent`" in first[0]
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge(verdict_block("UNVERIFIABLE"))]
    again = resume(two_step(), "P-3", repo, registry(ex), decision="retry", settings=NO_SLEEP)
    assert again.exit_code is ExitCode.PAUSED and again.payload["unit"] == "review", again.message
    assert stop(repo, "P-3", ex).exit_code is ExitCode.STOPPED
    second, reply2 = asks()
    child.drain(registry=registry(standin("claude", judges=[reply2])), host=lambda: MemoryCodeHost())
    (prompt,) = second
    assert "cause `gap_escalation`" in prompt and "unit `review`" in prompt
    assert "cause `retries_spent`" not in prompt
    assert any(f["cause"] == "retries_spent" for f in read_findings(state_root_path(repo), "demo", "P-3"))
