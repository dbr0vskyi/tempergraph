"""The loop judges the findings of a thread's earlier pauses at every final exit (SIL-B28, SIL-B37, SIL-B38)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child, filing, pause_facts, review
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
          "output": "canary-output-heron", "file": "canary-file-ibis", "ruling": "canary-ruling-lemur"}


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


def run_log(repo: Path, task: str) -> list[dict[str, Any]]:
    p = state_root_path(repo) / "runs" / "demo" / task / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def facts_by_finding(repo: Path, task: str) -> list[tuple[dict[str, Any], dict[str, str]]]:
    """Each finding of a paused segment of the thread with its facts from `pause_facts.of` (None-free: rows only)."""
    found = [f for f in read_findings(state_root_path(repo), "demo", task) if f.get("segment_exit") == 3]
    facts = pause_facts.of(state_root_path(repo), "demo", task, found)
    return [(f, facts[f["fingerprint"]]) for f in found if f["fingerprint"] in facts]


def test_a_finding_is_told_the_pause_of_its_own_segment(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC49, AC 1
    loop_on(monkeypatch)
    ex = paused_on_retries(repo, "F-20")  # segment 1 pauses at `draft`
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge(UNVERIFIABLE)]
    again = resume(two_step(), "F-20", repo, registry(ex), decision="retry", settings=NO_SLEEP)
    assert again.exit_code is ExitCode.PAUSED and again.payload["unit"] == "review", again.message  # segment 2: `review`
    starts = [r["ts"] for r in run_log(repo, "F-20") if r["kind"] == "run_started"]
    assert len(starts) == 2
    lines = [f for f in read_findings(state_root_path(repo), "demo", "F-20") if f.get("segment_exit") == 3]
    assert {f["segment_started"] for f in lines} == set(starts)
    rows = facts_by_finding(repo, "F-20")
    by_segment = {f["segment_started"]: row for f, row in rows}
    assert by_segment[starts[0]]["unit"] == "draft" and by_segment[starts[0]]["reason"] != "unresolved_gap"
    assert by_segment[starts[1]]["unit"] == "review" and by_segment[starts[1]]["reason"] == "unresolved_gap"
    # a finding of the first unit told in the second segment names the pause at `review`, not the earlier one
    stray = dict(next(f for f in lines if f["segment_started"] == starts[1]), unit="draft", fingerprint="stray")
    row = pause_facts.of(state_root_path(repo), "demo", "F-20", [stray])["stray"]
    assert row["unit"] == "review" and row["reason"] == "unresolved_gap"


def test_a_finding_with_nothing_recorded_gets_no_row(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC50, AC 1
    paused_on_gap(repo, "F-21", monkeypatch)  # one pause, no answer yet
    ((f, row),) = [x for x in facts_by_finding(repo, "F-21") if x[0]["cause"] == "gap_escalation"]
    assert row["reason"] == "unresolved_gap" and row["decision"] == pause_facts.UNKNOWN and row["unit"] == "review"
    nothing = {"kind": "finding", "thread": "demo/F-22", "segment_exit": 3, "unit": "ghost", "fingerprint": "ghost",
               "segment_started": "2000-01-01T00:00:00+00:00", "at": "2000-01-01T00:00:01+00:00"}
    answers = pause_facts.of(state_root_path(repo), "demo", "F-22", [nothing])
    assert answers == {}  # no pause, decision or gate
    assert SECTION not in child.prompt([nothing], [], answers)  # and no row means no section


def mapped_pause(repo: Path, task: str) -> tuple[Any, Any]:
    """A map whose first item spends its retry and pauses; returns the spec and the first segment's stand-in."""
    from .test_map import FAIL, THREE, item_ok, mapped, planner, run

    spec = mapped(check=None)
    out, ex = run(repo, spec, [planner(THREE[:2]), item_ok(), item_ok()], [judge(), judge(FAIL), judge(FAIL)], task=task)
    assert out.exit_code is ExitCode.PAUSED and out.payload["item"] == "p1", out.message
    return spec, ex


def test_the_next_gate_is_that_of_the_paused_item(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC51, AC 3
    from .test_map import FAIL, item_ok

    loop_on(monkeypatch)
    spec, _ = mapped_pause(repo, "F-23")
    ex = standin("claude", steps=[item_ok(), item_ok(), answer("Joined.", session_id="join")],
                 judges=[judge(FAIL), judge(), judge()])  # p2's first gate is RETRY
    done = resume(spec, "F-23", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    log = run_log(repo, "F-23")
    later = next(r for r in log[max(i for i, r in enumerate(log) if r["kind"] == "pause"):]
                 if r["kind"] == "gate" and r.get("item") == "p2")
    assert later["token"] == "RETRY"
    rows = [row for f, row in facts_by_finding(repo, "F-23") if row["unit"] == "phase"]
    assert rows and all(row["item"] == "p1" and row["next_gate"] == "none" for row in rows), rows


def test_the_next_gate_of_the_same_item_is_read(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC51, AC 3
    from .test_map import item_ok

    loop_on(monkeypatch)
    spec, _ = mapped_pause(repo, "F-24")
    ex = standin("claude", steps=[item_ok(), item_ok(), answer("Joined.", session_id="join")],
                 judges=[judge(), judge(), judge()])
    done = resume(spec, "F-24", repo, registry(ex), decision="retry", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    log = run_log(repo, "F-24")
    gate = next(r for r in log[max(i for i, r in enumerate(log) if r["kind"] == "pause"):]
                if r["kind"] == "gate" and r.get("item") == "p1")
    rows = [row for f, row in facts_by_finding(repo, "F-24") if row["unit"] == "phase"]
    assert rows and all(row["next_gate"] == gate["verdict"] != "none" for row in rows), rows


def test_the_facts_say_a_ruling_was_given_and_never_its_words(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC52, SIL-AC53, SIL-AC44, AC 4
    ex = paused_on_gap(repo, "F-25", monkeypatch)
    finish(repo, "F-25", ex, feedback=CANARY["ruling"], ruling=True, caller={"kind": "agent"})
    (prompt,) = judged_prompts()
    ledger = [json.loads(ln) for ln in (state_root_path(repo) / "ledger.jsonl").read_text().splitlines()]
    (decision,) = [r for r in ledger if r.get("kind") == "intervention" and r.get("thread_id") == "demo/F-25"
                   and r.get("ruling")]
    classes = [t.get("class") for t in decision.get("touches") or []]
    want = next((c for c in ("designed", "rescue", "steer", "engine") if c in classes), pause_facts.UNKNOWN)
    (row,) = [r for f, r in facts_by_finding(repo, "F-25") if f["cause"] == "gap_escalation"]
    assert row["ruling"] == "given" and row["feedback"] == "not given" and row["touch"] == want, row
    assert CANARY["ruling"] not in prompt
    assert CANARY["ruling"] not in child.loop_log(state_root_path(repo), "demo", "F-25").read_text()
    assert "feedback not given" in facts_of(prompt, finding_of(repo, "F-25", "gap_escalation")["fingerprint"])


def test_the_brief_tells_what_the_pauses_section_is_and_how_an_answer_bears_on_attribution(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC54, AC 5
    ex = paused_on_gap(repo, "F-30", monkeypatch)
    finish(repo, "F-30", ex)
    (prompt,) = judged_prompts()
    assert SECTION in prompt
    flat = " ".join(prompt.split())
    assert "section `What answered each pause`" in flat or "section on what answered each pause" in flat.lower()
    assert "`retry` that passes with the workspace unchanged" in flat and "points at the judge or the check" in flat
    assert "not at the step" in flat
    assert "`proceed` with a ruling" in flat and "overrode the gate" in flat
    assert "supervising caller" in flat
    assert "can file the finding by the count whatever its confidence" in flat  # FFD-B6


def test_each_paused_segment_with_a_listed_finding_has_a_section_of_its_own(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC55, AC 6
    loop_on(monkeypatch)
    ex = paused_on_retries(repo, "F-31")  # segment 1 pauses at `draft`
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge(UNVERIFIABLE)]
    again = resume(two_step(), "F-31", repo, registry(ex), decision="retry", feedback=CANARY["feedback"],
                   settings=NO_SLEEP)
    assert again.exit_code is ExitCode.PAUSED and again.payload["unit"] == "review", again.message  # segment 2
    finish(repo, "F-31", ex, feedback=CANARY["ruling"], ruling=True, caller={"kind": "agent"})  # segment 3, final
    (prompt,) = judged_prompts()
    heads = [ln for ln in prompt.splitlines() if ln.startswith("## The segment's records")]
    assert len(heads) == 3, heads
    assert [("exit code 3" in h, "exit code 0" in h) for h in heads] == [(True, False), (True, False), (False, True)]
    assert all("reason " in h for h in heads), heads
    assert "reason budget" in heads[0] and "reason escalation" in heads[1], heads  # the segment's own `run_exit` reason
    parts = prompt.split("## The segment's records")[1:]
    assert any("`draft`" in p and "gate" in p for p in parts[:1])  # the first segment's own units and records
    assert all(CANARY[k] not in prompt for k in CANARY)
    for ln in prompt.splitlines():  # `test_loop_child.py` reads a `- ` line with a backtick and `cause` as a fingerprint
        if ln.startswith("- `") and "cause" in ln:
            assert "class " in ln and "side " in ln, ln  # only finding rows
