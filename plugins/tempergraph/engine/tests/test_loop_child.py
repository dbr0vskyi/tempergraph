"""The loop child: hand-off ticket, detached start, friction judge, filing (SIL-B1, B2, B6; T12.1.5)."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tempergraph import detach
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionResult, Usage
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child, filing
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import read_findings
from tempergraph.store.layout import home_path

from .fixtures.workflows import two_step
from .test_review_budget import NONE_FOUND, build_run, run_ticket
from .test_run import DRAFT, REVIEW, go, judge, registry, verdict_block


def blocked_run(repo: Path, task: str, monkeypatch: pytest.MonkeyPatch, **kw: Any) -> None:
    """A run that finishes after one blocked attempt: a `judge_blocked` workflow fault at a final exit."""
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr(detach, "start", lambda *a, **k: True)  # the child is started by drain() below
    fail = verdict_block("UNMET")
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(fail), judge(), judge()])
    assert go(repo, ex, task=task, **kw).exit_code is ExitCode.FINISHED


def judge_says(fp_conf: float, attributed: bool = True) -> Any:
    def reply(req: Any) -> Any:
        fps = [ln.split("`")[1] for ln in req.prompt.splitlines() if ln.startswith("- `") and "cause" in ln]
        rows = [{"fingerprint": fp, "attributed": attributed, "confidence": fp_conf} for fp in fps]
        assert "Release 1.2 notes" not in req.prompt  # metadata only: no request text reaches the judge
        assert "can file the finding by the count whatever its confidence" in req.prompt  # FFD-AC6
        assert req.alias == child.ALIAS and req.timeout_s == child.TIMEOUT_S
        return answer("```json\n" + json.dumps({"findings": rows}) + "\n```", session_id="loop")
    return reply


def tickets() -> list[Path]:
    return sorted(child.tickets_dir(home_path()).glob("*.json"))


def test_ticket_then_judged_filing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-B1, B2
    blocked_run(repo, "L-1", monkeypatch)
    (t,) = tickets()
    doc = json.loads(t.read_text())
    assert doc["thread"] == "demo/L-1" and doc["fingerprints"] and doc["lenses"]["friction"]
    assert "Release 1.2 notes" not in t.read_text()
    host = MemoryCodeHost()
    ex = standin("claude", judges=[judge_says(0.9)])
    root = repo / ".tempergraph"
    spec_repo = "team/notes"
    doc["issue_repository"] = spec_repo
    t.write_text(json.dumps(doc))
    (out,) = child.drain(registry=registry(ex), host=lambda: host)
    assert [r["op"] for r in out["results"] if r["op"] != "recorded"] == ["filed"]
    assert host.issues[0]["repo"] == spec_repo and filing.marker(doc["fingerprints"][0]) in host.issues[0]["body"]
    assert not tickets()  # claimed and removed
    log = [json.loads(ln) for ln in child.loop_log(root, "demo", "L-1").read_text().splitlines()]
    assert [r["kind"] for r in log][:2] == ["loop_started", "loop_judged"] and "issue_filed" in [r["kind"] for r in log]
    assert any(r.get("kind") == "loop" for r in map(json.loads, (root / "ledger.jsonl").read_text().splitlines()))
    summary = [r for r in log if r["kind"] == "loop_summary"]  # SIL-AC14: one, written when the child ends
    assert len(summary) == 1 and log[-1] is summary[0]
    assert summary[0]["recorded"] == len(read_findings(root, "demo", "L-1"))
    assert summary[0]["filed"] == len([r for r in out["results"] if r["op"] in ("filed", "commented")]) == 1
    assert summary[0]["top"] == [] and summary[0]["thread"] == "demo/L-1"
    blocked_run(repo, "L-2", monkeypatch)  # the same cause again: a comment, never a second issue
    d2 = json.loads(tickets()[0].read_text())
    d2["issue_repository"] = spec_repo
    tickets()[0].write_text(json.dumps(d2))
    (out2,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
    assert len(host.issues) == 1 and [r["op"] for r in out2["results"] if r["op"] != "recorded"] == ["commented"]


def test_sil_ac5_the_review_runs_first_and_the_child_still_records_and_never_fails_the_parent(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC5 (SIL-B17): the session review comes before deciding and filing; records and ledger row survive the order
    blocked_run(repo, "L-9", monkeypatch)
    (t,) = tickets()
    doc = json.loads(t.read_text())
    root = repo / ".tempergraph"
    build_run(root, "L-9", 1)  # a captured session for the review to plan
    doc.update({"issue_repository": "team/notes", "review": "full", "mode": "dev", "run_cost_usd": 4.0, "units": {}})
    t.write_text(json.dumps(doc))
    host = MemoryCodeHost()
    ex = standin("claude", judges=[judge_says(0.9), answer(NONE_FOUND, session_id="review")])
    (out,) = child.drain(registry=registry(ex), host=lambda: host)
    kinds = [json.loads(ln)["kind"] for ln in child.loop_log(root, "demo", "L-9").read_text().splitlines()]
    assert kinds[:2] == ["loop_started", "loop_judged"] and kinds.count("loop_summary") == 1 and kinds[-1] == "loop_summary"
    assert "issue_filed" in kinds
    assert kinds.index("review_done") < kinds.index("issue_filed")
    assert [r for r in out["results"] if r["op"] == "filed"] and len(host.issues) == 1
    ledger = [r for r in map(json.loads, (root / "ledger.jsonl").read_text().splitlines()) if r.get("kind") == "loop"]
    assert len([r for r in ledger if r["thread_id"] == "demo/L-9"]) == 1
    # (b) a child that fails leaves the parent's exit code as the parent ended it
    blocked_run(repo, "L-10", monkeypatch)  # asserts FINISHED before the child runs
    (t2,) = tickets()
    doc2 = json.loads(t2.read_text())
    doc2["issue_repository"] = "team/notes"
    t2.write_text(json.dumps(doc2))

    def boom(req: Any) -> Any:
        raise RuntimeError("judge down")

    outs = child.drain(registry=registry(standin("claude", judges=[boom])), host=lambda: MemoryCodeHost(down=True))
    assert len(outs) == 1 and not tickets()  # drain returned without raising


def test_loop_started_names_the_fingerprints_it_covered(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC21, AC 1
    blocked_run(repo, "L-6", monkeypatch)
    (t,) = tickets()
    fps = sorted(json.loads(t.read_text())["fingerprints"])
    assert fps
    child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: MemoryCodeHost())
    log = [json.loads(ln) for ln in child.loop_log(repo / ".tempergraph", "demo", "L-6").read_text().splitlines()]
    (started,) = [r for r in log if r["kind"] == "loop_started"]
    assert started["fingerprints"] == fps


def test_low_confidence_or_unparsed_is_recorded(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocked_run(repo, "L-3", monkeypatch)
    host = MemoryCodeHost()
    (out,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.4)])), host=lambda: host)
    assert {r["reason"] for r in out["results"]} <= {"below_count", "no_repository", "designed"} and not host.issues  # FFD-AC3
    blocked_run(repo, "L-4", monkeypatch)
    (out,) = child.drain(registry=registry(standin("claude", judges=[answer("no block")])), host=lambda: host)
    assert all(r["op"] == "recorded" for r in out["results"]) and not host.issues


def test_dry_run_files_nothing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-B6
    blocked_run(repo, "L-5", monkeypatch, dry_run=True)
    d = json.loads(tickets()[0].read_text())
    assert d["dry_run"] is True
    d["issue_repository"] = "team/notes"
    tickets()[0].write_text(json.dumps(d))
    host = MemoryCodeHost(down=True)  # any call would raise
    (out,) = child.drain(registry=registry(standin("claude", judges=[judge_says(0.9)])), host=lambda: host)
    assert "would_file" in {r["op"] for r in out["results"]} and not host.issues


def test_no_ticket_without_a_fault_and_off_switch(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    started: list[tuple[str, ...]] = []
    monkeypatch.setattr(detach, "start", lambda m, w, h: started.append((m, *w)) or True)
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    quiet = dataclasses.replace(two_step(), session_review="off")  # a dev run's session review is a ticket too
    assert go(repo, ex, spec=quiet, task="L-6").exit_code is ExitCode.FINISHED
    assert not tickets() and not started
    blocked_run(repo, "L-7", monkeypatch)
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "off")
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(verdict_block("UNMET")), judge(), judge()])
    n = len(tickets())
    assert go(repo, ex, task="L-8").exit_code is ExitCode.FINISHED and len(tickets()) == n


def test_detached_site_is_constant() -> None:  # SEC-B7
    assert detach.DETACHED["tempergraph.improve.child"] == (("drain",),)
    assert child.main(["other"]) == 2


def test_a_failing_ticket_never_stops_the_next(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = child.tickets_dir(home_path())
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bad.json").write_text("{nope")
    out = child.drain(registry=registry(standin("claude")), host=MemoryCodeHost)
    assert out == [{"ticket": "bad", "error": "JSONDecodeError"}] and not list(folder.iterdir())


def outcome_ticket(root: Path, n: int, calibrated: bool) -> dict[str, Any]:
    from tempergraph.improve import record

    fp = record.fingerprint("workflow", "demo", "outcome_unmet:c-1", "outcome")
    f = {"kind": "finding", "thread": f"demo/O-{n}", "workflow": "demo", "unit": "outcome", "lens": "outcome",
         "cause": "outcome_unmet:c-1", "class": "fault", "side": "workflow", "count": 1, "remedy": "r",
         "fingerprint": fp, "at": datetime.now(UTC).isoformat(timespec="seconds"), "request_digest": f"r{n}", "machine": "m"}
    path = record.findings_path(root, "demo", f"O-{n}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "thread": f"demo/O-{n}", "findings": [f]}))
    return {"ticket_id": f"t{n}", "thread": f"demo/O-{n}", "workflow": "demo", "task_id": f"O-{n}",
            "state_root": str(root), "issue_repository": "team/notes", "dry_run": False, "executor": "claude",
            "fingerprints": [fp], "lenses": {"friction": False, "outcome": True}, "outcome_calibrated": calibrated}


def test_outcome_lens_files_only_when_calibrated_and_patterned(tmp_path: Path) -> None:  # SIL-B3, B7
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude"))  # no session is scripted: the outcome gate's judge already graded it
    out = child.process(outcome_ticket(root, 1, calibrated=False), reg, host)
    assert [r["reason"] for r in out["results"]] == ["uncalibrated"] and not host.issues
    out = child.process(outcome_ticket(root, 2, calibrated=True), reg, host)
    assert [r["reason"] for r in out["results"]] == ["pattern_not_met"] and not host.issues  # two runs so far
    out = child.process(outcome_ticket(root, 3, calibrated=True), reg, host)
    assert [r["op"] for r in out["results"]] == ["filed"] and host.issues[0]["repo"] == "team/notes"
    out = child.process(outcome_ticket(root, 4, calibrated=True), reg, host)
    assert [r["op"] for r in out["results"]] == ["commented"] and len(host.issues) == 1


def friction_ticket(root: Path, n: int, causes: tuple[str, ...] = ("slow_step",)) -> dict[str, Any]:
    """The ticket of run `demo/F-<n>`: one friction fault for each cause, the same fingerprint in every run."""
    from tempergraph.improve import record

    rows = []
    for cause in causes:
        fp = record.fingerprint("workflow", "demo", cause, "draft")
        rows.append({"kind": "finding", "thread": f"demo/F-{n}", "workflow": "demo", "unit": "draft", "cause": cause,
                     "class": "fault", "side": "workflow", "count": 1, "remedy": "r", "fingerprint": fp,
                     "at": datetime.now(UTC).isoformat(timespec="seconds"), "request_digest": f"r{n}", "machine": "m"})
    path = record.findings_path(root, "demo", f"F-{n}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "thread": f"demo/F-{n}", "findings": rows}))
    return {"ticket_id": f"f{n}", "thread": f"demo/F-{n}", "workflow": "demo", "task_id": f"F-{n}",
            "state_root": str(root), "issue_repository": "team/notes", "dry_run": False, "executor": "claude",
            "fingerprints": [r["fingerprint"] for r in rows], "lenses": {"friction": True, "outcome": False}}


def judged_row(root: Path, n: int) -> dict[str, Any]:
    (row,) = [r for r in loop_rows(root, f"F-{n}") if r["kind"] == "loop_judged"]
    return row


def test_a_friction_finding_files_by_the_pattern_count(tmp_path: Path) -> None:  # SIL-AC34, AC 7
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude", judges=[judge_says(0.5) for _ in range(4)]))
    for n in (1, 2):  # two runs, each judged at 0.5: the count is not met, recorded, nothing filed (FFD-AC3)
        out = child.process(friction_ticket(root, n), reg, host)
        assert [r["reason"] for r in out["results"]] == ["below_count"] and not host.issues
    # the third run: three attributed answers (FFD-AC1), a third request: one issue
    out = child.process(friction_ticket(root, 3), reg, host)
    assert [r["op"] for r in out["results"]] == ["filed"] and len(host.issues) == 1
    evidence = host.issues[0]["body"].split("## Evidence\n", 1)[1].split("\n## ", 1)[0]
    assert "runs 3" in evidence and "requests 3" in evidence
    out = child.process(friction_ticket(root, 4), reg, host)  # a fourth run: a comment, no second issue
    assert [r["op"] for r in out["results"]] == ["commented"]
    assert len(host.issues) == 1 and len(host.comments) == 1


def test_a_count_met_finding_files_nothing_without_an_attribution(tmp_path: Path) -> None:  # SIL-AC35, AC 3
    def reply_for_another(req: Any) -> Any:
        rows = [{"fingerprint": "0000111122223333", "attributed": True, "confidence": 0.9}]
        return answer("```json\n" + json.dumps({"findings": rows}) + "\n```", session_id="loop")

    cases = {
        "not_attributed": (judge_says(0.9, attributed=False), "not_attributed"),
        "session_failed": (SessionResult(ok=False, usage=Usage(reported_cost_usd=0.01)), "not_judged"),
        "no_block": (answer("no block here"), "not_judged"),
        "left_out": (reply_for_another, "not_judged"),
    }
    for name, (reply, reason) in cases.items():
        root = tmp_path / name / ".tempergraph"
        host = MemoryCodeHost()
        for n in (1, 2):  # the same fingerprint recorded in two other runs, each with its own request
            friction_ticket(root, n)
        out = child.process(friction_ticket(root, 3), registry(standin("claude", judges=[reply])), host)
        assert [r["op"] for r in out["results"]] == ["recorded"], name
        assert [r["reason"] for r in out["results"]] == [reason], name
        assert not host.issues and not host.comments, name


def earlier_judged(root: Path, n: int, attributed: bool, confidence: float = 0.5) -> None:
    """The `loop_judged` record an earlier exit of run `demo/F-<n>` left for the fixture fingerprint."""
    from tempergraph.improve import record

    fp = record.fingerprint("workflow", "demo", "slow_step", "draft")
    path = child.loop_log(root, "demo", f"F-{n}")
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "kind": "loop_judged", "lens": "friction",
           "answers": [{"fingerprint": fp, "confidence": confidence, "attributed": attributed}]}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def exit_three(root: Path, flags: dict[int, bool], confidence: float, reply: Any = None) -> tuple[dict[str, Any], MemoryCodeHost]:
    """Runs F-1 and F-2 hold the fingerprint (and the answers of `flags`); the exit of F-3 is processed."""
    host = MemoryCodeHost()
    for n in (1, 2):
        friction_ticket(root, n)
    for n, flag in flags.items():
        earlier_judged(root, n, flag)
    reg = registry(standin("claude", judges=[reply or judge_says(confidence)]))
    return child.process(friction_ticket(root, 3), reg, host), host


def test_the_pattern_files_on_a_majority_of_recorded_answers(tmp_path: Path) -> None:  # FFD-AC1, SIL-AC36
    out, host = exit_three(tmp_path / "a" / ".tempergraph", {1: True, 2: False}, 0.5)  # (true, false) + true
    assert [r["op"] for r in out["results"]] == ["filed"] and len(host.issues) == 1
    out, host = exit_three(tmp_path / "b" / ".tempergraph", {1: False}, 0.5)  # (false) + true: a tie
    assert [r["reason"] for r in out["results"]] == ["not_attributed"] and not host.issues
    out, host = exit_three(tmp_path / "c" / ".tempergraph", {}, 0.8)  # one answer at the floor or above
    assert [r["op"] for r in out["results"]] == ["filed"] and len(host.issues) == 1


def test_seen_again_comments_are_bounded_by_the_records_of_the_day(tmp_path: Path) -> None:  # ISS-AC12
    from datetime import timedelta

    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude", judges=[judge_says(0.5) for _ in range(6)]))
    for n in (1, 2, 3):  # the third exit files the one issue
        child.process(friction_ticket(root, n), reg, host)
    assert len(host.issues) == 1
    outs = [child.process(friction_ticket(root, n), reg, host) for n in (4, 5, 6)]  # three more exits on the day
    assert [[r["op"] for r in o["results"]] for o in outs] == [["commented"], ["comment_capped"], ["comment_capped"]]
    assert len(host.issues) == 1 and len(host.comments) == 1
    rows = [r for n in range(1, 7) for r in loop_rows(root, f"F-{n}")]
    assert len([r for r in rows if r["kind"] == "issue_commented"]) == 1
    capped = [r for r in rows if r["kind"] == "loop_result" and r["op"] == "comment_capped"]
    assert len(capped) == 2 and all(r["number"] == 1 and "body" not in r and "text" not in r for r in capped)
    today = datetime.now(UTC)
    assert filing.comments_by_day(root, "demo", today) == {("team/notes", 1): 1}  # read by the record's UTC day
    assert filing.comments_by_day(root, "demo", today + timedelta(days=1)) == {}  # the next day starts at none


def test_each_reason_of_a_finding_that_does_not_file_is_named_once(tmp_path: Path) -> None:  # FFD-AC2, FFD-AC3, SIL-AC35
    failed = SessionResult(ok=False, usage=Usage(reported_cost_usd=0.01))
    cases = {
        "not_judged": ({}, 0.5, failed),
        "not_attributed": ({}, 0.9, judge_says(0.9, attributed=False)),
        "few_answers": ({}, 0.5, None),  # the count is met, one answer, below the floor
        "below_count": (None, 0.5, None),  # the count is not met
    }
    for name, (flags, conf, reply) in cases.items():
        root = tmp_path / name / ".tempergraph"
        if flags is None:
            out = child.process(friction_ticket(root, 1), registry(standin("claude", judges=[judge_says(conf)])),
                                MemoryCodeHost())
        else:
            out, host = exit_three(root, flags, conf, reply)
            assert not host.issues and not host.comments, name
        assert [r["reason"] for r in out["results"]] == [name], name
        assert "below_floor" not in child.loop_log(root, "demo", "F-3" if flags is not None else "F-1").read_text()


def test_loop_result_holds_the_counts_and_filed_records_the_reason(tmp_path: Path) -> None:  # FFD-AC4, FFD-AC5
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude", judges=[judge_says(0.5) for _ in range(4)]))
    for n in (1, 2, 3, 4):
        child.process(friction_ticket(root, n), reg, host)

    def rows(n: int, kind: str) -> list[dict[str, Any]]:
        return [r for r in loop_rows(root, f"F-{n}") if r["kind"] == kind]

    (low,) = rows(2, "loop_result")
    assert low["reason"] == "below_count" and (low["runs"], low["requests"], low["machines"]) == (2, 2, 1)
    (filed,) = rows(3, "issue_filed")
    assert filed["reason"] == "pattern_met" and "body" not in filed
    (again,) = rows(4, "issue_commented")
    assert again["reason"] == "pattern_met" and isinstance(again["number"], int) and again["repo"] == "team/notes"
    assert "Release" not in child.loop_log(root, "demo", "F-4").read_text()
    out, _ = exit_three(tmp_path / "nj" / ".tempergraph", {}, 0.5, SessionResult(ok=False, usage=Usage()))
    (nj,) = [r for r in loop_rows(tmp_path / "nj" / ".tempergraph", "F-3") if r["kind"] == "loop_result"]
    assert nj["reason"] == "not_judged" and not {"runs", "requests", "machines"} & set(nj)


def test_loop_judged_holds_what_the_judge_answered_and_none_of_its_text(tmp_path: Path) -> None:  # SIL-AC38, AC 5
    from tempergraph.improve import record

    causes = ("slow_step", "retry_burst", "empty_output")
    fps = [record.fingerprint("workflow", "demo", c, "draft") for c in causes]
    words = "zebra-explanation-91"

    def two_of_three(req: Any) -> Any:
        rows = [{"fingerprint": fps[0], "attributed": True, "confidence": 0.5, "why": f"{words} first"},
                {"fingerprint": fps[1], "attributed": False, "confidence": 0.7, "why": f"{words} second"}]
        return answer("```json\n" + json.dumps({"findings": rows}) + "\n```", session_id="loop")

    root = tmp_path / ".tempergraph"
    child.process(friction_ticket(root, 1, causes), registry(standin("claude", judges=[two_of_three])),
                  MemoryCodeHost())
    row = judged_row(root, 1)
    assert row["answers"] == [{"fingerprint": fps[0], "confidence": 0.5, "attributed": True},
                              {"fingerprint": fps[1], "confidence": 0.7, "attributed": False}]
    assert words not in child.loop_log(root, "demo", "F-1").read_text()
    root2 = tmp_path / "failed" / ".tempergraph"  # a failed session leaves an empty list
    failed = SessionResult(ok=False, usage=Usage(reported_cost_usd=0.01))
    child.process(friction_ticket(root2, 1, causes), registry(standin("claude", judges=[failed])), MemoryCodeHost())
    assert judged_row(root2, 1)["answers"] == [] and judged_row(root2, 1)["ok"] is False


# -- a review that fails is counted; a usage-limit failure is run again once (SIL-B24 to SIL-B26) --------------------


class FakeClock:
    """The child's clock and sleep: a sleep moves the clock and is kept; `forbid` makes any sleep fail the test."""

    def __init__(self, forbid: bool = False) -> None:
        self.now = 1_000_000.0
        self.sleeps: list[float] = []
        self.forbid = forbid

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        assert not self.forbid, "the child must start no wait"
        self.now += seconds


def fake_clock(monkeypatch: pytest.MonkeyPatch, forbid: bool = False) -> FakeClock:
    c = FakeClock(forbid)
    monkeypatch.setattr(child, "clock", c.time)
    monkeypatch.setattr(child, "sleep", c.sleep)
    return c


def retry_ticket(root: Path, task: str, run_cost: float = 4.0) -> dict[str, Any]:
    t = run_ticket(root, task, run_cost)
    return {**t, "thread": f"demo/{task}", "ticket_id": "t1", "fingerprints": [], "dry_run": False,
            "lenses": {"friction": False, "outcome": False}, "issue_repository": "team/notes"}


def spent(at: float | None, cost: float = 0.01) -> SessionResult:
    return SessionResult(ok=False, usage=Usage(reported_cost_usd=cost), usage_limit=True, usage_limit_resets_at=at)


def loop_rows(root: Path, task: str) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in child.loop_log(root, "demo", task).read_text().splitlines()]


def summary_of(root: Path, task: str) -> dict[str, Any]:
    rows = loop_rows(root, task)
    assert rows[-1]["kind"] == "loop_summary"  # written after the last retry
    return rows[-1]


def test_sil_ac16_a_review_that_raises_counts_as_one_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC16 (SIL-B24)
    from tempergraph.improve import review

    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(review, "run", boom)
    build_run(tmp_path, "E-1", 1)
    child.process(retry_ticket(tmp_path, "E-1"), registry(standin("claude")), MemoryCodeHost())
    rows = loop_rows(tmp_path, "E-1")
    (failed,) = [r for r in rows if r["kind"] == "review_failed"]
    assert "session_key" not in failed and failed["error_class"] == "error"
    assert rows[-1]["kind"] == "loop_summary" and rows[-1]["review_failed"] == {"error": 1}


def test_sil_ac17_a_usage_limit_is_waited_for_and_each_review_runs_once_more(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC17 (SIL-B25)
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    c = fake_clock(monkeypatch)
    build_run(tmp_path, "W-1", 2)
    started: list[float] = []

    def retried(req: Any) -> SessionResult:
        started.append(c.now)
        return answer(NONE_FOUND, session_id="again")

    ex = standin("claude", judges=[spent(c.now + 3600), spent(c.now + 7200), retried, retried])
    out = child.process(retry_ticket(tmp_path, "W-1"), registry(ex), MemoryCodeHost())
    assert c.sleeps == [7200.0] and started == [c.now, c.now] and c.now == 1_000_000.0 + 7200  # the later reset
    rows = loop_rows(tmp_path, "W-1")
    planned = [i for i, r in enumerate(rows) if r["kind"] == "review_planned"]
    assert len(planned) == 2 and "retry" not in rows[planned[0]] and rows[planned[1]]["retry"] is True
    order = [t["session_key"] for t in rows[planned[0]]["targets"]]
    assert [r["session_key"] for r in rows if r["kind"] == "review_done"] == order  # plan order again
    assert not any("retry" in r for r in rows[:planned[1]])  # the first attempt's records carry no mark
    assert all(r.get("retry") is True for r in rows[planned[1]:-1])  # every record of the retry carries it
    assert summary_of(tmp_path, "W-1")["review_failed"] == {}
    (ledger,) = [r for r in map(json.loads, (tmp_path / "ledger.jsonl").read_text().splitlines())
                 if r.get("kind") == "loop"]
    assert round(ledger["cost"]["reported"], 6) == round(out["cost"]["reported"], 6) == 0.04  # the retry is in it


def test_sil_ac17_a_retry_that_fails_again_is_not_run_a_third_time(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC17 (SIL-B25)
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    c = fake_clock(monkeypatch)
    build_run(tmp_path, "W-2", 2)
    ex = standin("claude", judges=[spent(c.now + 3600)] * 2 + [spent(c.now + 7200)] * 2)
    child.process(retry_ticket(tmp_path, "W-2"), registry(ex), MemoryCodeHost())
    assert len(ex.calls) == 4 and c.sleeps == [3600.0]  # one wait, one retry of each review
    rows = loop_rows(tmp_path, "W-2")
    again = [r for r in rows if r["kind"] == "review_failed" and r.get("retry") is True]
    assert [r["error_class"] for r in again] == ["usage_limit"] * 2
    assert summary_of(tmp_path, "W-2")["review_failed"] == {"usage_limit": 2}


def test_sil_ac17_only_the_usage_limit_failure_within_the_bound_is_retried(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC17 (SIL-B25)
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    c = fake_clock(monkeypatch)
    build_run(tmp_path, "W-3", 2)
    ex = standin("claude", judges=[spent(c.now + 3600), answer("no block"), answer("no block"),
                                   answer(NONE_FOUND, session_id="again")])
    child.process(retry_ticket(tmp_path, "W-3"), registry(ex), MemoryCodeHost())
    rows = loop_rows(tmp_path, "W-3")
    first = [t["session_key"] for t in next(r for r in rows if r["kind"] == "review_planned")["targets"]][0]
    assert len(ex.calls) == 4  # one session, two asks, one retry
    assert [r["session_key"] for r in rows if r["kind"] == "review_done"] == [first]
    assert summary_of(tmp_path, "W-3")["review_failed"] == {"unparsed": 1}


def test_sil_ac17_a_retry_past_the_money_cap_is_skipped_and_stays_failed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC17 (SIL-B25, SRV-B25)
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    c = fake_clock(monkeypatch)
    build_run(tmp_path, "W-4", 2)  # a run cost of 4.0 gives a cap of 1.00 USD: two failed reviews spend all of it
    ex = standin("claude", judges=[spent(c.now + 3600, 0.5), spent(c.now + 3600, 0.5)])
    child.process(retry_ticket(tmp_path, "W-4"), registry(ex), MemoryCodeHost())
    assert len(ex.calls) == 2
    rows = loop_rows(tmp_path, "W-4")
    skipped = [r for r in rows if r["kind"] == "review_skipped"]
    assert [(r["reason"], r.get("retry")) for r in skipped] == [("budget", True)] * 2
    assert summary_of(tmp_path, "W-4")["review_failed"] == {"usage_limit": 2}


@pytest.mark.parametrize(("mode", "ahead"), [("detached", None), ("detached", 6 * 3600 + 60), ("inline", 2 * 3600)])
def test_sil_ac17_a_limit_that_will_not_pass_soon_or_a_foreground_run_starts_no_wait(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, ahead: int | None) -> None:
    # SIL-AC17 (SIL-B26)
    monkeypatch.setenv("TEMPERGRAPH_LOOP", mode)
    c = fake_clock(monkeypatch, forbid=True)
    build_run(tmp_path, "N-1", 2)
    at = None if ahead is None else c.now + ahead
    ex = standin("claude", judges=[spent(at), spent(at)])
    child.process(retry_ticket(tmp_path, "N-1"), registry(ex), MemoryCodeHost())
    assert c.sleeps == [] and len(ex.calls) == 2
    rows = loop_rows(tmp_path, "N-1")
    assert not any(r.get("retry") for r in rows)
    assert summary_of(tmp_path, "N-1")["review_failed"] == {"usage_limit": 2}


def test_sil_ac17_a_reset_exactly_six_hours_ahead_is_waited_for(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC17 (SIL-B25)
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    c = fake_clock(monkeypatch)
    build_run(tmp_path, "N-2", 1)
    ex = standin("claude", judges=[spent(c.now + 6 * 3600), answer(NONE_FOUND, session_id="again")])
    child.process(retry_ticket(tmp_path, "N-2"), registry(ex), MemoryCodeHost())
    assert c.sleeps == [21600.0] and len(ex.calls) == 2
    assert summary_of(tmp_path, "N-2")["review_failed"] == {}


def test_sil_ac17_a_persons_review_waits_for_nothing(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC17 (SIL-B26)
    from .test_cli import cli

    c = fake_clock(monkeypatch, forbid=True)
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, spec=dataclasses.replace(two_step(), session_review="off"), task="P-1").exit_code \
        is ExitCode.FINISHED
    reviewer = standin("claude", judges=[spent(c.now + 3600)] * 8)
    code, doc, _ = cli(repo, reviewer, "improve", "review", "demo/P-1", "--json")
    keys = [t["session_key"] for t in doc["plan"]["targets"]]
    assert code == 0 and keys and doc["failed"] == keys and len(reviewer.calls) == len(keys)  # once each, no re-ask
    assert c.sleeps == []
    rows = loop_rows(repo / ".tempergraph", "P-1")
    assert {r["error_class"] for r in rows if r["kind"] == "review_failed"} == {"usage_limit"}
    assert not any(r.get("retry") for r in rows)


def test_hand_off_carries_calibration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tempergraph.improve import calibration

    from .fixtures.workflows import two_step

    monkeypatch.setattr(calibration, "has_score", lambda spec, gate, root=None: gate == "outcome")
    summary = {"lenses": {"friction": False}, "fault_fingerprints": [], "outcome_fingerprints": ["abc"],
               "fingerprints": ["abc"]}
    p = child.hand_off(tmp_path, two_step(), "T-1", "demo/T-1", summary, dry_run=False, judge_executor="claude",
                       home=tmp_path / "home")
    assert p is not None and json.loads(p.read_text())["outcome_calibrated"] is True
    none = {"lenses": {"friction": True}, "fault_fingerprints": [], "outcome_fingerprints": [], "fingerprints": []}
    quiet = dataclasses.replace(two_step(), session_review="off")  # else a dev run's review writes a ticket
    assert child.hand_off(tmp_path, quiet, "T-2", "demo/T-2", none, dry_run=False, judge_executor="claude",
                          home=tmp_path / "home") is None
