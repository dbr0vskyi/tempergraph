"""A pause finding is handed on at every final exit until a loop has dealt with it (SIL-B28, SIL-B47 to SIL-B49)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import read_findings, unjudged_pause_findings
from tempergraph.run.runner import resume
from tempergraph.store.layout import home_path, state_root_path

from .fixtures.workflows import two_step
from .test_pause_findings_at_final_exit import UNVERIFIABLE, finding_of, finish, held, paused_on_gap
from .test_run import DRAFT, NO_SLEEP, REVIEW, judge, registry
from .test_stop_at_pause import asks, loop_on, paused_on_retries, stop, tickets

THREAD = "demo/{}"


def attribute_all(seen: list[str]) -> Any:
    """A stand-in friction judge that attributes every finding row of its prompt at 0.9 and keeps the prompts."""
    def reply(req: Any) -> Any:
        seen.append(req.prompt)
        rows = [{"fingerprint": ln.split("`")[1], "attributed": True, "confidence": 0.9}
                for ln in req.prompt.splitlines() if ln.startswith("- `") and "cause `" in ln]
        return answer("```json\n" + json.dumps({"findings": rows}) + "\n```", session_id="loop")
    return reply


def loop_records(repo: Path, task: str, kind: str) -> list[dict[str, Any]]:
    log = child.loop_log(state_root_path(repo), "demo", task)
    return [r for r in map(json.loads, log.read_text().splitlines()) if r["kind"] == kind]


def answers_for(repo: Path, task: str, fp: str) -> list[dict[str, Any]]:
    return [a for r in loop_records(repo, task, "loop_judged") for a in r.get("answers") or [] if a["fingerprint"] == fp]


def drain(judge_reply: Any) -> list[dict[str, Any]]:
    return child.drain(registry=registry(standin("claude", judges=[judge_reply])), host=lambda: MemoryCodeHost())


def stopped_then_finished(repo: Path, task: str, monkeypatch: pytest.MonkeyPatch, hold: str) -> tuple[Any, list[str]]:
    """A thread stopped at a pause under a hold (`record` or a dry run), drained, re-opened and finished without it."""
    loop_on(monkeypatch)
    if hold == "record":
        monkeypatch.setenv("TEMPERGRAPH_AUTONOMY", "record")
    ex = paused_on_retries(repo, task)
    dry = hold == "dry_run"
    from dataclasses import replace
    out = resume(two_step(), task, repo, registry(ex), decision="stop", settings=replace(NO_SLEEP, dry_run=dry))
    assert out.exit_code is ExitCode.STOPPED, out.message
    seen: list[str] = []
    drain(attribute_all(seen))
    assert len(seen) == 1
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge(UNVERIFIABLE)]
    again = resume(two_step(), task, repo, registry(ex), decision="retry", settings=replace(NO_SLEEP, dry_run=dry))
    assert again.exit_code is ExitCode.PAUSED, again.message
    return ex, seen


@pytest.mark.parametrize("hold", ["record", "dry_run"])
def test_a_finding_a_held_loop_only_recorded_is_handed_again_and_judged_once(
        repo: Path, monkeypatch: pytest.MonkeyPatch, hold: str) -> None:  # SIL-AC57, AC 3
    task = f"H-{hold}"
    ex, first = stopped_then_finished(repo, task, monkeypatch, hold)
    fp = next(f for f in read_findings(state_root_path(repo), "demo", task)
              if f["cause"] == "retries_spent")["fingerprint"]
    assert len(answers_for(repo, task, fp)) == 1
    assert [r["held"] for r in loop_records(repo, task, "loop_started")] == [True]
    from dataclasses import replace
    out = resume(two_step(), task, repo, registry(ex), decision="proceed",
                 settings=replace(NO_SLEEP, dry_run=hold == "dry_run"))
    assert out.exit_code is ExitCode.FINISHED, out.message
    (t,) = tickets()
    assert fp in held(json.loads(t.read_text()))  # handed again
    second: list[str] = []
    drain(attribute_all(second))
    assert not any(fp in p for p in second)  # its recorded answer is used, the judge is not asked again
    assert len(answers_for(repo, task, fp)) == 1


def test_a_finding_a_judge_left_out_is_handed_again(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC57, AC 3
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    loop_on(monkeypatch)
    ex = paused_on_retries(repo, "H-left")
    assert stop(repo, "H-left", ex).exit_code is ExitCode.STOPPED
    seen, reply = asks()  # answers no finding
    drain(reply)
    root = state_root_path(repo)
    left = unjudged_pause_findings(root, "demo", "H-left", THREAD.format("H-left"))
    assert "retries_spent" in [f["cause"] for f in left]
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge(UNVERIFIABLE)]
    assert resume(two_step(), "H-left", repo, registry(ex), decision="retry", settings=NO_SLEEP).exit_code \
        is ExitCode.PAUSED
    finish(repo, "H-left", ex)
    (t,) = tickets()
    fp = finding_of(repo, "H-left", "retries_spent")["fingerprint"]
    assert fp in held(json.loads(t.read_text()))


def test_a_thread_whose_last_exit_was_held_keeps_its_pause_findings_recorded_only(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC57, AC 3
    monkeypatch.setenv("TEMPERGRAPH_AUTONOMY", "record")
    ex = paused_on_gap(repo, "H-last", monkeypatch)
    finish(repo, "H-last", ex)
    seen: list[str] = []
    drain(attribute_all(seen))
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    root = state_root_path(repo)
    left = unjudged_pause_findings(root, "demo", "H-last", THREAD.format("H-last"))
    assert "gap_escalation" in [f["cause"] for f in left]  # recorded only, there is no later exit to hand it on
    assert tickets() == []


@pytest.mark.parametrize("claimed", [False, True])
def test_a_waiting_or_claimed_ticket_holds_its_findings_against_a_second_exit(
        repo: Path, monkeypatch: pytest.MonkeyPatch, claimed: bool) -> None:  # SIL-AC58, AC 3
    task = f"H-wait-{claimed}"
    loop_on(monkeypatch)
    ex = paused_on_retries(repo, task)
    assert stop(repo, task, ex).exit_code is ExitCode.STOPPED
    (first,) = tickets()
    fp = finding_of(repo, task, "retries_spent")["fingerprint"]
    assert fp in held(json.loads(first.read_text()))
    if claimed:
        first.rename(first.with_suffix(".claimed"))
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge(UNVERIFIABLE)]
    assert resume(two_step(), task, repo, registry(ex), decision="retry", settings=NO_SLEEP).exit_code \
        is ExitCode.PAUSED
    finish(repo, task, ex)
    folder = child.tickets_dir(home_path())
    (t2,) = [p for p in folder.glob("*.json") if p != first]
    assert fp not in held(json.loads(t2.read_text()))
    first.unlink(missing_ok=True)  # the first ticket's child is the one that judges its findings
    first.with_suffix(".claimed").unlink(missing_ok=True)
    seen: list[str] = []
    drain(attribute_all(seen))
    assert len(seen) == 1 and fp not in seen[0]  # the judge is asked once, and not about the first ticket's finding


def process_ticket(repo: Path, task: str, judge_reply: Any) -> None:
    """Hand the loop child the pause finding of `task` through a ticket made by hand."""
    root = state_root_path(repo)
    fp = finding_of(repo, task, "gap_escalation")["fingerprint"]
    t = {"schema_version": 1, "ticket_id": "t-hand", "thread": THREAD.format(task), "workflow": "demo",
         "task_id": task, "state_root": str(root), "issue_repository": "acme/notes", "mode": "dev",
         "dry_run": False, "executor": "claude", "fingerprints": [], "pause_fingerprints": [fp],
         "lenses": {"friction": True, "outcome": False}, "review": "off", "autonomy": "pr"}
    child.process(t, registry(standin("claude", judges=[judge_reply])), MemoryCodeHost())


@pytest.mark.parametrize("attributed", [True, False])
def test_a_recorded_answer_is_used_without_a_second_judgement(
        repo: Path, monkeypatch: pytest.MonkeyPatch, attributed: bool) -> None:  # SIL-AC59, AC 3
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    task = f"H-ans-{attributed}"
    ex = paused_on_gap(repo, task, monkeypatch)
    finish(repo, task, ex)
    for p in tickets():
        p.unlink()
    fp = finding_of(repo, task, "gap_escalation")["fingerprint"]
    log = child.loop_log(state_root_path(repo), "demo", task)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        fh.write(json.dumps({"ts": "2000-01-01T00:00:00+00:00", "kind": "loop_judged", "lens": "friction", "ok": True,
                             "parsed": True, "answers": [{"fingerprint": fp, "confidence": 0.9,
                                                          "attributed": attributed}]}) + "\n")
    seen: list[str] = []
    process_ticket(repo, task, attribute_all(seen))
    assert not any(fp in p for p in seen)  # no row for it in the judge's prompt, and no session when none is left
    assert len(answers_for(repo, task, fp)) == 1
    results = [r for r in loop_records(repo, task, "loop_result")] + loop_records(repo, task, "issue_filed")
    if attributed:
        assert loop_records(repo, task, "issue_filed") or results
    else:
        assert any(r.get("reason") == "not_attributed" for r in results)
        assert not loop_records(repo, task, "issue_filed")


def test_a_finding_with_no_recorded_answer_is_put_to_the_judge(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC59, AC 3
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    ex = paused_on_gap(repo, "H-new", monkeypatch)
    finish(repo, "H-new", ex)
    (t,) = tickets()
    fp = finding_of(repo, "H-new", "gap_escalation")["fingerprint"]
    assert fp in held(json.loads(t.read_text()))
    seen: list[str] = []
    drain(attribute_all(seen))
    (prompt,) = seen
    assert fp in prompt
    assert len(answers_for(repo, "H-new", fp)) == 1
