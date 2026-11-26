"""A pause finding is handed on until a loop has dealt with it (SIL-B28, SIL-B47, SIL-B48, SIL-B49)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import unjudged_pause_findings
from tempergraph.run.runner import resume
from tempergraph.store.layout import home_path, state_root_path

from .fixtures.workflows import two_step
from .test_pause_findings_at_final_exit import finding_of, finish, gap_only, held, paused_on_gap
from .test_run import NO_SLEEP, REVIEW, judge, registry
from .test_stop_at_pause import stop, tickets


def counting(reply: Any = gap_only) -> tuple[list[str], Any]:
    """A friction judge that keeps the prompts it is asked and answers as `reply` does."""
    seen: list[str] = []

    def ask(req: Any) -> Any:
        seen.append(req.prompt)
        return reply(req)
    return seen, ask


def drain(judge: Any, host: MemoryCodeHost | None = None) -> MemoryCodeHost:
    host = host or MemoryCodeHost()
    child.drain(registry=registry(standin("claude", judges=[judge])), host=lambda: host)
    return host


def answers(repo: Path, task: str, fp: str) -> int:
    log = child.loop_log(state_root_path(repo), "demo", task)
    return sum(1 for r in map(json.loads, log.read_text().splitlines()) if r["kind"] == "loop_judged"
               for a in r.get("answers") or () if a["fingerprint"] == fp)


def asked_about(seen: list[str], fp: str) -> int:
    """How many prompts hold a finding row (a line that starts with the fingerprint) for `fp`."""
    return sum(1 for p in seen if any(ln.startswith(f"- `{fp}`") for ln in p.splitlines()))


def handed(repo: Path, task: str) -> set[str]:
    """The fingerprints of the thread's pause findings that the next final exit hands on."""
    return {str(f["fingerprint"]) for f in unjudged_pause_findings(state_root_path(repo), "demo", task, f"demo/{task}")}


def nothing(req: Any) -> Any:
    return answer("no block here", session_id="loop")


def silent_gap(req: Any) -> Any:
    return answer("```json\n" + json.dumps({"findings": []}) + "\n```", session_id="loop")


def held_then_lifted(repo: Path, task: str, monkeypatch: pytest.MonkeyPatch, how: str) -> tuple[str, list[str], MemoryCodeHost]:
    """A thread stopped at its gap pause under a hold (`how` is `record` or `dry_run`), drained, re-opened with
    `proceed` and finished without it, then drained again; returns the fingerprint, the judge's prompts and the host."""
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    ex = paused_on_gap(repo, task, monkeypatch)  # the dry run is a setting of the run, so the first segment is redone
    if how == "record":
        monkeypatch.setenv("TEMPERGRAPH_AUTONOMY", "record")
        assert stop(repo, task, ex).exit_code is ExitCode.STOPPED
    else:
        assert resume(two_step(), task, repo, registry(ex), decision="stop",
                      settings=__import__("dataclasses").replace(NO_SLEEP, dry_run=True)).exit_code is ExitCode.STOPPED
    fp = finding_of(repo, task, "gap_escalation")["fingerprint"]
    seen, ask = counting()
    drain(ask)
    assert asked_about(seen, fp) == 1
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    ex.steps, ex.judges = [REVIEW], [judge()]
    back = resume(two_step(), task, repo, registry(ex), decision="retry", settings=NO_SLEEP)
    assert back.exit_code is ExitCode.FINISHED, back.message
    (t,) = tickets()
    assert fp in held(json.loads(t.read_text()))  # the held loop did not cover it: it is handed again
    return fp, seen, drain(ask)


@pytest.mark.parametrize("how", ["record", "dry_run"])
def test_a_finding_a_held_child_only_recorded_is_handed_again_and_judged_once(
        repo: Path, monkeypatch: pytest.MonkeyPatch, how: str) -> None:  # SIL-AC57, AC 3
    fp, seen, host = held_then_lifted(repo, f"H-{how}", monkeypatch, how)
    assert asked_about(seen, fp) == 1  # the recorded answer is used by the second child, which asks nothing of it
    assert answers(repo, f"H-{how}", fp) == 1
    assert len(host.issues) <= 1


def test_a_first_child_whose_judge_left_the_finding_out_hands_it_again(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC57, AC 3
    ex = paused_on_gap(repo, "H-left", monkeypatch)
    fp = finding_of(repo, "H-left", "gap_escalation")["fingerprint"]
    finish(repo, "H-left", ex)
    (t,) = tickets()
    assert fp in held(json.loads(t.read_text()))
    drain(silent_gap)  # the judge answers for no finding
    assert fp in handed(repo, "H-left")


def test_a_first_child_whose_judge_session_fails_hands_the_finding_again(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC57, AC 3
    ex = paused_on_gap(repo, "H-fail", monkeypatch)
    fp = finding_of(repo, "H-fail", "gap_escalation")["fingerprint"]
    finish(repo, "H-fail", ex)
    drain(nothing)
    assert fp in handed(repo, "H-fail")


def test_a_judged_finding_is_not_handed_again(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC57, AC 3
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    ex = paused_on_gap(repo, "H-done", monkeypatch)
    finish(repo, "H-done", ex)
    fp = finding_of(repo, "H-done", "gap_escalation")["fingerprint"]
    seen, ask = counting()
    drain(ask)
    assert fp not in handed(repo, "H-done")
    assert asked_about(seen, fp) == 1


def test_a_waiting_or_claimed_ticket_holds_its_fingerprints(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC58, AC 3
    ex = paused_on_gap(repo, "H-wait", monkeypatch)
    fp = finding_of(repo, "H-wait", "gap_escalation")["fingerprint"]
    finish(repo, "H-wait", ex)
    root, thread = state_root_path(repo), "demo/H-wait"
    (t,) = tickets()
    assert fp in held(json.loads(t.read_text()))
    assert fp not in handed(repo, "H-wait")  # waiting
    claimed = t.with_suffix(".claimed")
    t.rename(claimed)
    assert fp not in handed(repo, "H-wait")  # claimed
    assert fp in child.held_by_tickets(root, thread, home_path())
    claimed.unlink()
    assert fp in handed(repo, "H-wait")


def test_two_exits_before_the_first_child_starts_hand_the_finding_once(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC58, AC 3
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    ex = paused_on_gap(repo, "H-two", monkeypatch)
    fp = finding_of(repo, "H-two", "gap_escalation")["fingerprint"]
    assert stop(repo, "H-two", ex).exit_code is ExitCode.STOPPED
    (first,) = tickets()
    assert fp in held(json.loads(first.read_text()))
    ex.steps, ex.judges = [REVIEW], [judge()]
    again = resume(two_step(), "H-two", repo, registry(ex), decision="retry", settings=NO_SLEEP)
    assert again.exit_code is ExitCode.FINISHED, again.message
    second = [p for p in tickets() if p != first]
    assert len(second) == 1 and fp not in held(json.loads(second[0].read_text()))
    seen, ask = counting()
    drain(ask)
    assert asked_about(seen, fp) == 1


def test_a_recorded_answer_is_used_without_a_second_judgement(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC59, AC 3
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    ex = paused_on_gap(repo, "H-rec", monkeypatch)
    finish(repo, "H-rec", ex)
    fp = finding_of(repo, "H-rec", "gap_escalation")["fingerprint"]
    log = child.loop_log(state_root_path(repo), "demo", "H-rec")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"kind": "loop_judged", "answers": [
        {"fingerprint": fp, "attributed": True, "confidence": 0.9}]}) + "\n")
    seen, ask = counting()
    host = drain(ask)
    assert asked_about(seen, fp) == 0  # no row in the judge's prompt
    assert answers(repo, "H-rec", fp) == 1
    assert len(host.issues) == 1  # filed on the recorded answer


def test_a_recorded_answer_not_attributed_files_nothing_and_asks_nothing(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC59, AC 3
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    ex = paused_on_gap(repo, "H-no", monkeypatch)
    finish(repo, "H-no", ex)
    fp = finding_of(repo, "H-no", "gap_escalation")["fingerprint"]
    log = child.loop_log(state_root_path(repo), "demo", "H-no")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"kind": "loop_judged", "answers": [
        {"fingerprint": fp, "attributed": False, "confidence": 0.9}]}) + "\n")
    seen, ask = counting()
    host = drain(ask)
    assert asked_about(seen, fp) == 0 and host.issues == []
    lines = [json.loads(ln) for ln in log.read_text().splitlines()]
    assert any(r.get("reason") == "not_attributed" for r in lines)
    assert answers(repo, "H-no", fp) == 1


def test_a_finding_with_no_recorded_answer_is_put_to_the_judge(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC59, AC 3
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)
    ex = paused_on_gap(repo, "H-new", monkeypatch)
    finish(repo, "H-new", ex)
    fp = finding_of(repo, "H-new", "gap_escalation")["fingerprint"]
    seen, ask = counting()
    drain(ask)
    assert asked_about(seen, fp) == 1 and answers(repo, "H-new", fp) == 1
