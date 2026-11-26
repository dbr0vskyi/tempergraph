"""The loop judges the findings of a thread's earlier pauses at every final exit (SIL-B28, SIL-B37, SIL-B38)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child, filing, review
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import read_findings
from tempergraph.run.runner import resume, start
from tempergraph.store.layout import state_root_path

from .fixtures.workflows import two_step
from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, registry, verdict_block
from .test_stop_at_pause import asks, loop_on, no_retries, paused_on_retries, stop, tickets

UNVERIFIABLE = verdict_block("UNVERIFIABLE")
REPO = "acme/notes"  # the issue repository of the `two_step` fixture


def paused_on_gap(repo: Path, task: str, monkeypatch: pytest.MonkeyPatch, spec: Any = None, draft: Any = DRAFT) -> Any:
    """A first segment that pauses `review` on `gap_escalation`, with the loop's child started by the test."""
    loop_on(monkeypatch)
    ex = standin("claude", steps=[draft, REVIEW], judges=[judge(), judge(UNVERIFIABLE)])
    out = go(repo, ex, spec, task=task)
    assert out.exit_code is ExitCode.PAUSED and out.payload["unit"] == "review", out.message
    return ex


def finish(repo: Path, task: str, ex: Any, decision: str = "proceed", spec: Any = None, feedback: str | None = None,
           **kw: Any) -> Any:
    out = resume(spec or two_step(), task, repo, registry(ex), decision=decision, feedback=feedback,
                 settings=dataclasses.replace(NO_SLEEP, **kw))
    assert out.exit_code is ExitCode.FINISHED, out.message
    return out


def finding_of(repo: Path, task: str, cause: str) -> dict[str, Any]:
    return next(f for f in read_findings(state_root_path(repo), "demo", task)
                if f["cause"] == cause and f.get("segment_exit") == 3)


def held(doc: dict[str, Any]) -> set[str]:
    return {*doc.get("fingerprints", ()), *doc.get("pause_fingerprints", ())}


def started(repo: Path, task: str) -> list[dict[str, Any]]:
    log = child.loop_log(state_root_path(repo), "demo", task)
    return [r for r in map(json.loads, log.read_text().splitlines()) if r["kind"] == "loop_started"]


def test_a_final_exit_after_a_pause_judges_the_pause_findings(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC39, AC 1, AC 5
    ex = paused_on_gap(repo, "F-1", monkeypatch)
    assert tickets() == []  # a pause is no final exit
    finish(repo, "F-1", ex)
    fp = finding_of(repo, "F-1", "gap_escalation")["fingerprint"]
    (t,) = tickets()
    doc = json.loads(t.read_text())
    assert doc["lenses"]["friction"] is True and fp in held(doc)
    seen, reply = asks()
    child.drain(registry=registry(standin("claude", judges=[reply])), host=lambda: MemoryCodeHost())
    (prompt,) = seen
    assert "cause `gap_escalation`" in prompt and "unit `review`" in prompt and fp in prompt


def test_a_later_final_exit_hands_the_loop_no_finding_an_earlier_loop_was_handed(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC40, AC 2
    loop_on(monkeypatch)
    ex = paused_on_retries(repo, "F-2")
    assert stop(repo, "F-2", ex).exit_code is ExitCode.STOPPED
    first, reply1 = asks()
    child.drain(registry=registry(standin("claude", judges=[reply1])), host=lambda: MemoryCodeHost())
    assert len(first) == 1 and "cause `retries_spent`" in first[0]
    (earlier,) = started(repo, "F-2")
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge(UNVERIFIABLE)]
    again = resume(two_step(), "F-2", repo, registry(ex), decision="retry", settings=NO_SLEEP)
    assert again.exit_code is ExitCode.PAUSED and again.payload["unit"] == "review", again.message
    finish(repo, "F-2", ex)
    (t,) = tickets()
    doc = json.loads(t.read_text())
    gap = finding_of(repo, "F-2", "gap_escalation")["fingerprint"]
    assert gap in held(doc) and not held(doc) & set(earlier["fingerprints"])
    second, reply2 = asks()
    child.drain(registry=registry(standin("claude", judges=[reply2])), host=lambda: MemoryCodeHost())
    (prompt,) = second
    assert "cause `gap_escalation`" in prompt and "cause `retries_spent`" not in prompt
    assert not any(fp in prompt for fp in earlier["fingerprints"])


def drain_with_issue(repo: Path, task: str, how: str, monkeypatch: pytest.MonkeyPatch) -> tuple[MemoryCodeHost, Any]:
    """The thread of SIL-AC39 drained with a judge that attributes every finding, against a host whose one open loop
    issue holds the finding's fingerprint line (`how` is `fingerprint`) or its cause line (`cause`)."""
    monkeypatch.delenv("TEMPERGRAPH_AUTONOMY", raising=False)  # a machine setting of `record` would only record
    ex = paused_on_gap(repo, task, monkeypatch)
    finish(repo, task, ex)
    f = finding_of(repo, task, "gap_escalation")
    body = f"<!-- {filing.marker(f['fingerprint'])} -->" if how == "fingerprint" \
        else f"<!-- tempergraph:cause={filing.cause_key(f)} -->"
    host = MemoryCodeHost()
    host.issues.append({"repo": REPO, "number": 1, "title": "[loop] demo: gap_escalation", "body": body,
                        "state": "open", "url": f"https://example.test/{REPO}/issues/1"})
    (out,) = child.drain(registry=registry(standin("claude", judges=[gap_only])), host=lambda: host)
    return host, out


def gap_only(req: Any) -> Any:
    """A stand-in judge that attributes the `gap_escalation` finding at 0.9 and answers for no other."""
    fps = [ln.split("`")[1] for ln in req.prompt.splitlines() if ln.startswith("- `") and "cause `gap_escalation`" in ln]
    rows = [{"fingerprint": fp, "attributed": True, "confidence": 0.9} for fp in fps]
    return answer("```json\n" + json.dumps({"findings": rows}) + "\n```", session_id="loop")


@pytest.mark.parametrize("how", ["fingerprint", "cause"])
def test_a_pause_finding_matching_an_open_issue_comments_and_files_none(
        repo: Path, monkeypatch: pytest.MonkeyPatch, how: str) -> None:  # SIL-AC43, AC 4, AC 6
    host, out = drain_with_issue(repo, "F-3", how, monkeypatch)
    assert [r["op"] for r in out["results"] if r["op"] != "recorded"] == ["commented"]
    assert len(host.issues) == 1 and [c["number"] for c in host.comments] == [1]


def test_a_final_exit_that_is_not_a_stop_plans_no_review_from_the_pauses(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC45, AC 7
    loop_on(monkeypatch)
    monkeypatch.setattr(review, "probation", lambda *a, **k: False)
    spec = no_retries(dataclasses.replace(two_step(), improvement_mode="stable"))
    ex = paused_on_retries(repo, "F-7", spec)
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge()]
    out = resume(spec, "F-7", repo, registry(ex), decision="retry", settings=NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (t,) = tickets()
    doc = json.loads(t.read_text())
    fp = finding_of(repo, "F-7", "retries_spent")["fingerprint"]
    assert fp in doc["pause_fingerprints"] and fp not in doc["fingerprints"]
    assert review.plan_for(doc)["depth"] == "none"


SECTION = "## What answered each pause"
CANARY = {"request": "canary-request-aardvark", "feedback": "canary-feedback-zebra",
          "output": "canary-output-heron", "file": "canary-file-ibis"}


def judged_prompts() -> list[str]:
    """The prompts a recording friction judge is asked about the waiting tickets."""
    seen, reply = asks()
    child.drain(registry=registry(standin("claude", judges=[reply])), host=lambda: MemoryCodeHost())
    return seen


def facts_of(prompt: str, fp: str) -> str:
    """The line of the prompt's section on what answered each pause that names the finding."""
    assert SECTION in prompt, prompt
    return next(ln for ln in prompt.split(SECTION, 1)[1].splitlines() if fp in ln)


def test_the_judge_is_told_what_answered_the_pause(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC41, AC 3, AC 5
    ex = paused_on_gap(repo, "F-8", monkeypatch)
    finish(repo, "F-8", ex, caller={"kind": "person"})
    (prompt,) = judged_prompts()
    line = facts_of(prompt, finding_of(repo, "F-8", "gap_escalation")["fingerprint"])
    for fact in ("reason `unresolved_gap`", "decision `proceed`", "caller `person`", "feedback not given",
                 "workspace unchanged", "next gate verdict `none`"):
        assert fact in line, line


def test_the_judge_is_told_the_feedback_was_given_and_never_its_words(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC42, AC 3
    loop_on(monkeypatch)
    ex = paused_on_retries(repo, "F-9")
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge()]
    finish(repo, "F-9", ex, "retry", feedback=CANARY["feedback"], caller={"kind": "agent"})
    log = [json.loads(ln) for ln in (state_root_path(repo) / "runs" / "demo" / "F-9" / "run.jsonl").read_text().splitlines()]
    asked = max(i for i, r in enumerate(log) if r["kind"] == "pause" and r["unit"] == "draft")
    verdict = next(r["verdict"] for r in log[asked:] if r["kind"] == "gate" and r["unit"] == "draft")
    assert verdict
    (prompt,) = judged_prompts()
    line = facts_of(prompt, finding_of(repo, "F-9", "retries_spent")["fingerprint"])
    for fact in ("decision `retry`", "caller `agent`", "feedback given", f"next gate verdict `{verdict}`"):
        assert fact in line, line
    assert CANARY["feedback"] not in prompt


def committed_in_worktree(repo: Path, task: str) -> None:
    from .test_run import records
    from .test_worktree_cleanup import git

    wt = Path(next(r for r in records(repo, task) if r["kind"] == "workspace")["path"])
    (wt / "by-a-person.txt").write_text("a person's file\n")
    git(wt, "add", "-A")
    git(wt, "commit", "-m", "a person's change")


def writes_and_commits(req: Any) -> Any:
    """A step that writes a file and commits it in the worktree before the run pauses."""
    from .test_worktree_cleanup import git

    (req.workdir / "own.txt").write_text("the run's own file\n")
    git(req.workdir, "add", "-A")
    git(req.workdir, "commit", "-m", "the run's own commit")
    return DRAFT


def test_the_judge_is_told_whether_the_workspace_changed(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC46, WTR-AC15, AC 2
    ex = paused_on_gap(repo, "F-13", monkeypatch, draft=writes_and_commits)
    finish(repo, "F-13", ex)  # nothing done between the pause and the resume
    (prompt,) = judged_prompts()
    assert "workspace unchanged" in facts_of(prompt, finding_of(repo, "F-13", "gap_escalation")["fingerprint"])
    ex = paused_on_gap(repo, "F-10", monkeypatch, draft=writes_and_commits)
    committed_in_worktree(repo, "F-10")
    finish(repo, "F-10", ex)
    (prompt,) = judged_prompts()
    assert "workspace changed" in facts_of(prompt, finding_of(repo, "F-10", "gap_escalation")["fingerprint"])
    place = two_step(workspace="in_place")  # the engine compares no workspace between the segments of a run in place
    ex = paused_on_gap(repo, "F-11", monkeypatch, spec=place)
    finish(repo, "F-11", ex, spec=place)
    (prompt,) = judged_prompts()
    assert "workspace not recorded" in facts_of(prompt, finding_of(repo, "F-11", "gap_escalation")["fingerprint"])


def test_no_text_of_the_run_reaches_the_judge_or_the_loop_log(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC44, AC 8
    def writes(req: Any) -> Any:  # the step's answer holds a word and the file it writes holds another
        (req.workdir / "notes.md").write_text(CANARY["file"] + "\n")
        return answer(f"Wrote notes.md {CANARY['output']}\nARTIFACT notes: notes.md", session_id="s-draft")

    loop_on(monkeypatch)
    ex = standin("claude", steps=[writes, REVIEW], judges=[judge(), judge(UNVERIFIABLE)])
    out = start(two_step(), "F-12", {"request": CANARY["request"]}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.PAUSED, out.message
    ex.steps, ex.judges = [REVIEW], [judge()]
    finish(repo, "F-12", ex, "retry", feedback=CANARY["feedback"])
    (prompt,) = judged_prompts()
    log = child.loop_log(state_root_path(repo), "demo", "F-12").read_text()
    for word in CANARY.values():
        assert word not in prompt and word not in log, word
    paused = [f for f in read_findings(state_root_path(repo), "demo", "F-12")
              if f.get("segment_exit") == 3 and f["class"] == "fault" and f.get("lens") not in ("outcome", "review")]
    assert paused
    for f in paused:
        assert (f"- `{f['fingerprint']}` cause `{f['cause']}` class {f['class']} side `{f['side']}` "
                f"unit `{f['unit']}` count {f['count']}") in prompt
    assert "reason `unresolved_gap`" in facts_of(prompt, finding_of(repo, "F-12", "gap_escalation")["fingerprint"])
