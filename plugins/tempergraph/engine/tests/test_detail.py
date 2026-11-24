"""The run detail document (RDD-B1–B6, RDD-AC1–AC-4) and `status --detail`."""

from __future__ import annotations

import dataclasses
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.durability.lock import RunLock
from tempergraph.executors.standins import standin
from tempergraph.observe.detail import cut, detail
from tempergraph.run.log import RunLog
from tempergraph.store.layout import lock_path, run_dir, session_dir, state_root_path

from .conftest import hash_tree
from .fixtures.workflows import two_step
from .test_cli import cli
from .test_run import DRAFT, REVIEW, go, judge, verdict_block

CANARY = "sk-ant-CANARY0123456789abcdef"


def fixture_run(repo: Path) -> dict[str, Any]:
    """A retry on draft, a trip back from review, then an escalation pause on review (RDD-AC1 without a map)."""
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW, DRAFT, REVIEW],
                 judges=[judge(verdict_block("UNMET")), judge(), judge(verdict_block("UNMET", defect_in="notes")),
                         judge(), judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    doc = detail(state_root_path(repo), two_step(), "demo/T-1")
    assert doc is not None
    return doc


def shape(doc: dict[str, Any]) -> dict[str, Any]:
    """The parts of the document a person reads, without times, paths and digests."""
    def att(a: dict[str, Any]) -> list[Any]:
        j = a.get("judge") or {}
        return [a["attempt"], [s["session_key"] for s in (a.get("step") or {}).get("sessions", [])],
                (a.get("check") or {}).get("result"), f"{j.get('met')}/{j.get('total')}",
                [b["id"] for b in j.get("blockers", [])], (a.get("gate") or {}).get("verdict"),
                (a.get("gate") or {}).get("route_target"), a.get("repeat_cause")]

    return {
        "plan": [[p["name"], p["kind"], p["gated"], sorted({(e["on"], e["target"]) for e in p["edges"]})]
                 for p in doc["plan"]],
        "units": {u["name"]: [u["state"], [[v["visit"], v["entered_from"], [att(a) for a in v["attempts"]]]
                                           for v in u["visits"]]] for u in doc["units"]},
        "pause": {k: doc["pause"][k] for k in ("unit", "kind", "decisions")} if doc["pause"] else None,
        "health": {k: doc["health"][k] for k in ("alive", "orphaned", "suspect_stall")},
        "tail": [line.split(" ", 2)[2] for line in doc["events_tail"]],
    }


EXPECTED = {
    "plan": [
        ["draft", "step", True, [("ESCALATE", "human"), ("PROCEED", "review"), ("STOP", "end")]],
        ["review", "step", True, [("BACK", "draft"), ("ESCALATE", "human"), ("PROCEED", "finalizer"),
                                  ("STOP", "end")]],
        ["finalizer", "finalizer", False, []],
    ],
    "units": {
        "draft": ["passed", [
            [1, "start", [
                [1, ["draft.1.step"], "PASS", "0/1", ["c-file"], "RETRY", "draft", "blocker:c-file"],
                [2, ["draft.2.retry"], "PASS", "1/1", [], "PROCEED", "review", None]]],
            [2, "back:review", [
                [3, ["draft.3.step"], "PASS", "1/1", [], "PROCEED", "review", None]]]]],
        "review": ["paused", [
            [1, "proceed", [[1, ["review.1.step"], "PASS", "0/1", ["c-review"], "BACK", "draft", None]]],
            [2, "proceed", [[2, ["review.2.step"], "PASS", "0/1", ["c-review"], "ESCALATE", "human", None]]]]],
    },
    "pause": {"unit": "review", "kind": "escalation", "decisions": ["proceed", "retry", "back:draft", "stop"]},
    "health": {"alive": False, "orphaned": False, "suspect_stall": False},
    "tail": [
        "entered draft (visit 1, from start)", "check draft: PASS", "gate draft: RETRY -> draft",
        "budget retries: 1/2 (blockers)", "check draft: PASS", "gate draft: PROCEED -> review", "entered review (visit 1, from proceed)",
        "check review: PASS", "gate review: BACK -> draft", "budget loops:draft: 1/1 (defect_in)",
        "entered draft (visit 2, from back:review)",
        "check draft: PASS", "gate draft: PROCEED -> review", "entered review (visit 2, from proceed)",
        "check review: PASS",
        "gate review: ESCALATE -> human", "paused at review (escalation): "
        "tempergraph resume demo T-1 --decision <proceed|retry|back:draft|stop>"],
}


def test_fixture_reproduces_the_expected_document(repo: Path) -> None:  # RDD-AC1, B2, B3
    doc = fixture_run(repo)
    assert doc["schema_version"] == 1 and doc["truncated"] == []
    got = shape(doc)
    got["plan"] = [[n, k, g, [tuple(e) for e in es]] for n, k, g, es in got["plan"]]
    assert got == EXPECTED
    run = doc["run"]
    assert run["thread_id"] == "demo/T-1" and run["segment"] == 0 and run["last_seq"] > 40
    assert run["state"] == "paused" and run["plan_digest"] and not doc["plan_stale"]
    draft = next(u for u in doc["units"] if u["name"] == "draft")
    assert draft["cost"]["completeness"] == "complete" and 0 < draft["share"] < 1
    s = draft["visits"][0]["attempts"][0]["step"]["sessions"][0]
    assert s["session_id"] == "s-draft" and s["transcript"]["engine"].endswith("draft.1.step/raw.jsonl")
    assert s["activity_path"].endswith("draft.1.step/activity.jsonl") and s["outcome"]["ok"] is True
    assert "live" not in s
    review = next(u for u in doc["units"] if u["name"] == "review")
    last = review["visits"][-1]["attempts"][-1]
    assert last["judge"]["blockers"][0]["evidence"]  # evidence from the checkpoint's local judgement
    first = draft["visits"][0]["attempts"][0]["judge"]["blockers"][0]  # an earlier attempt: its evidence file
    assert first["id"] == "c-file" and "missing" in first["evidence"]
    kept = run_dir(state_root_path(repo), "demo", "T-1") / "evidence" / "judgements" / "draft" / "1.1.json"
    assert kept.stat().st_mode & 0o777 == 0o600
    assert doc["pause"]["resume"] == ["tempergraph resume demo T-1 --decision <proceed|retry|back:draft|stop>"]
    assert doc["pause"]["artifacts"] == [{"key": "verdict", "path": None}]  # a value, not a file
    assert doc["budgets"]["counters"]["draft.retries"]["limit"] == 2
    assert doc["health"]["waiting_for_person_s"] is not None


def contest_thread(repo: Path, write: Any, task: str = "T-1") -> dict[str, Any]:
    """The detail of a contest thread whose run log is written by hand: a real run makes the thread, `write(log)` its records."""
    from .test_contest_run import BySlot, contest_spec
    from .test_contest_run import go as go_contest

    spec = contest_spec(slots=3, then=False)
    assert go_contest(repo, spec, BySlot(), task=task).exit_code is ExitCode.FINISHED
    root = state_root_path(repo)
    path = run_dir(root, "demo", task) / "run.jsonl"
    path.unlink()
    log = RunLog(path)
    log.write("unit_entered", unit="pick", visit=1, entered_from="start")
    write(log)
    doc = detail(root, spec, f"demo/{task}")
    assert doc is not None
    return doc


def session(log: RunLog, slot: str, kind: str, cost: float, n: int = 1, start: bool = True) -> None:
    key = f"pick.{slot}.{n}.{kind}"
    if start:
        log.write("attempt_start", session_key=key, kind=kind, executor="claude", alias="small", timeout_s=600)
    else:
        log.write("agent_run", session_key=key, kind=kind, executor="claude", usage={"reported_cost_usd": cost}, ok=True,
                  tools=["Read"])


def graded(log: RunLog, slot: str, n: int = 1, check: str = "PASS", met: int = 1, conf: float = 0.85) -> None:
    log.write("check", unit="pick", item=slot, attempt=n, result=check, environmental=False, evidence=f"{slot} {check}")
    if check == "PASS":
        log.write("judgement", unit="pick", item=slot, attempt=n, statuses=[{"n": i, "id": f"c{i}", "status": "MET"}
                                                                            for i in range(1, met + 1)],
                  blockers=[], confidence=conf, confidence_source="judge", guard="ok")


def the_slots(doc: dict[str, Any]) -> list[dict[str, Any]]:
    (unit,) = [u for u in doc["units"] if u["name"] == "pick"]
    return [a for v in unit["visits"] for a in v["attempts"]]


def interleaved(log: RunLog) -> None:
    """The scenario of CTS-B1: three slots at once, their records written interleaved (`s2` and `s1` end before `s3`)."""
    for slot in ("s1", "s2", "s3"):
        session(log, slot, "step", 0)
    session(log, "s2", "step", 0.20, start=False)
    graded(log, "s2", met=6)
    session(log, "s1", "step", 0.15, start=False)
    session(log, "s3", "step", 0.30, start=False)
    for slot in ("s3", "s1", "s2"):
        session(log, slot, "judge", 0)
    graded(log, "s3", met=6)
    graded(log, "s1", met=5)
    session(log, "s2", "judge", 0.20, start=False)
    session(log, "s3", "judge", 0.25, start=False)
    session(log, "s1", "judge", 0.15, start=False)
    log.write("contest", unit="pick", visit=1, attempt=1, winner=2, slots=[
        {"slot": 1, "name": "s1", "attempt": 1, "check": "PASS", "verdict": "RETRY", "cost": 0.30,
         "keys": {"unmet_warnings": 0, "met": 5, "confidence": 0.85}},
        {"slot": 2, "name": "s2", "attempt": 1, "check": "PASS", "verdict": "PROCEED", "cost": 0.40,
         "keys": {"unmet_warnings": 1, "met": 6, "confidence": 0.85}},
        {"slot": 3, "name": "s3", "attempt": 1, "check": "PASS", "verdict": "PROCEED", "cost": 0.55,
         "keys": {"unmet_warnings": 1, "met": 6, "confidence": 0.85}}])
    log.write("gate", unit="pick", item=None, verdict="PROCEED", token="PROCEED", route_target="finalizer")


def test_interleaved_slots_each_hold_only_their_own_records_RDD_AC9(repo: Path) -> None:  # RDD-AC9 (RDD-B19, RDD-B10)
    slots = the_slots(contest_thread(repo, interleaved))
    assert [(a["item"], a["attempt"]) for a in slots] == [("s1", 1), ("s2", 1), ("s3", 1)]  # in the declared order
    s1, s2, s3 = slots
    assert [x["session_key"] for x in s2["step"]["sessions"]] == ["pick.s2.1.step"]  # its own sessions only
    assert [x["session_key"] for x in s2["judge"]["sessions"]] == ["pick.s2.1.judge"]
    assert s2["check"]["result"] == "PASS" and s2["check"]["evidence"] == "s2 PASS"  # its own check
    assert (s2["judge"]["met"], s1["judge"]["met"], s3["judge"]["met"]) == (6, 5, 6)  # and its own judgement
    assert s2["verdict"] == "PROCEED" and s2["keys"] == {"unmet_warnings": 1, "met": 6, "confidence": 0.85}
    assert s1["verdict"] == "RETRY" and s1["keys"]["met"] == 5
    assert s2["cost"]["figure"] == 0.40 and s1["cost"]["figure"] == 0.30 and s3["cost"]["figure"] == 0.55  # as a unit's
    assert s2["cost"]["completeness"] == "complete" and not any(a["skipped"] for a in slots)
    assert s2["gate"]["verdict"] == "PROCEED"  # the unit's gate record, which names no item, is on the winner's entry
    assert s1["gate"] is None and s3["gate"] is None


def test_a_slot_put_out_by_its_check_has_no_verdict_and_no_judge_RDD_AC9(repo: Path) -> None:  # RDD-AC9 (RDD-B19)
    def write(log: RunLog) -> None:
        for slot in ("s1", "s2", "s3"):
            session(log, slot, "step", 0)
            session(log, slot, "step", 0.1, start=False)
        graded(log, "s2", check="FAIL")
        graded(log, "s1")
        graded(log, "s3")
        for slot in ("s1", "s3"):
            session(log, slot, "judge", 0)
            session(log, slot, "judge", 0.1, start=False)
        log.write("contest", unit="pick", visit=1, attempt=1, winner=1, slots=[
            {"slot": 1, "name": "s1", "attempt": 1, "check": "PASS", "verdict": "PROCEED", "cost": 0.2,
             "keys": {"unmet_warnings": 0, "met": 1, "confidence": 0.85}},
            {"slot": 2, "name": "s2", "attempt": 1, "check": "FAIL", "verdict": None, "keys": None, "cost": 0.1},
            {"slot": 3, "name": "s3", "attempt": 1, "check": "PASS", "verdict": "PROCEED", "cost": 0.2,
             "keys": {"unmet_warnings": 0, "met": 1, "confidence": 0.85}}])

    s1, s2, s3 = the_slots(contest_thread(repo, write))
    assert (s2["check"]["result"], s2["judge"], s2["verdict"], s2["keys"]) == ("FAIL", None, None, None)
    assert s2["cost"]["figure"] == 0.1 and s1["judge"]["met"] == 1 and s3["judge"]["met"] == 1
    assert (s1["winner"], s2["winner"], s3["winner"]) == (True, False, False)


def test_a_slot_the_cost_cap_kept_from_starting_is_shown_skipped_RDD_AC9(repo: Path) -> None:  # RDD-AC9 (RDD-B19)
    def write(log: RunLog) -> None:
        for slot in ("s1", "s2"):
            session(log, slot, "step", 0)
            session(log, slot, "step", 0.30, start=False)
            graded(log, slot)
            session(log, slot, "judge", 0)
            session(log, slot, "judge", 0.01, start=False)
        log.write("contest", unit="pick", visit=1, attempt=1, winner=1, slots=[
            {"slot": 1, "name": "s1", "attempt": 1, "check": "PASS", "verdict": "PROCEED", "cost": 0.31,
             "keys": {"unmet_warnings": 0, "met": 1, "confidence": 0.85}},
            {"slot": 2, "name": "s2", "attempt": 1, "check": "PASS", "verdict": "PROCEED", "cost": 0.31,
             "keys": {"unmet_warnings": 0, "met": 1, "confidence": 0.85}},
            {"slot": 3, "name": "s3", "skipped": True}])

    s1, s2, s3 = the_slots(contest_thread(repo, write))
    assert s3["item"] == "s3" and s3["skipped"] is True and s3["step"] is None and s3["judge"] is None
    assert s3["verdict"] is None and s3["keys"] is None and s3["cost"]["figure"] == 0.0  # no session, no cost
    assert not s1["skipped"] and not s2["skipped"] and s3["winner"] is False


def test_the_winner_is_marked_true_on_the_kept_slot_and_false_on_the_others_RDD_AC10(repo: Path) -> None:  # RDD-AC10 (RDD-B20)
    s1, s2, s3 = the_slots(contest_thread(repo, interleaved))
    assert (s1["winner"], s2["winner"], s3["winner"]) == (False, True, False)


def test_the_winner_is_null_while_the_pick_has_not_run_and_when_it_kept_none_RDD_AC10(repo: Path) -> None:  # RDD-AC10 (RDD-B20)
    def running(log: RunLog) -> None:  # three slots still running: no pick yet
        for slot in ("s1", "s2", "s3"):
            session(log, slot, "step", 0)

    slots = the_slots(contest_thread(repo, running))
    assert [a["winner"] for a in slots] == [None, None, None] and [a["verdict"] for a in slots] == [None] * 3

    def none_kept(log: RunLog) -> None:  # every check failed: the pick kept none
        for slot in ("s1", "s2", "s3"):
            session(log, slot, "step", 0)
            session(log, slot, "step", 0.1, start=False)
            graded(log, slot, check="FAIL")
        log.write("contest", unit="pick", visit=1, attempt=1, winner=None, slots=[
            {"slot": i, "name": f"s{i}", "attempt": 1, "check": "FAIL", "verdict": None, "keys": None, "cost": 0.1}
            for i in (1, 2, 3)])

    slots = the_slots(contest_thread(repo, none_kept, "T-2"))
    assert [a["winner"] for a in slots] == [None, None, None] and [a["check"]["result"] for a in slots] == ["FAIL"] * 3


def test_each_attempt_of_a_contest_under_all_carries_a_winner_of_its_own_RDD_AC10(repo: Path) -> None:  # RDD-AC10 (RDD-B20)
    def write(log: RunLog) -> None:
        for n, winner in ((1, 2), (2, 1)):
            for slot in ("s1", "s2"):
                session(log, slot, "step" if n == 1 else "retry", 0, n=n)
                session(log, slot, "step" if n == 1 else "retry", 0.1, n=n, start=False)
                graded(log, slot, n=n)
            log.write("contest", unit="pick", visit=1, attempt=n, winner=winner, slots=[
                {"slot": i, "name": f"s{i}", "attempt": n, "check": "PASS", "verdict": "PROCEED", "cost": 0.1,
                 "keys": {"unmet_warnings": 0, "met": 1, "confidence": 0.85}} for i in (1, 2)])

    slots = the_slots(contest_thread(repo, write))
    assert [(a["item"], a["attempt"], a["winner"]) for a in slots] == [
        ("s1", 1, False), ("s2", 1, True), ("s1", 2, True), ("s2", 2, False)]  # round by round, slots in declared order


def test_a_real_contest_run_shows_every_slot_the_skipped_one_and_the_winner_RDD_AC9(repo: Path) -> None:  # RDD-AC9, RDD-AC10
    from .test_contest_run import BOTH_MET, ONE_WARNING, BySlot, contest_spec
    from .test_contest_run import go as go_contest

    spec = contest_spec(slots=3, concurrency=1, cost_cap_usd=0.4, then=False)
    ex = BySlot(step_cost=0.30, judges={"s1": [ONE_WARNING], "s2": [BOTH_MET]})
    assert go_contest(repo, spec, ex).exit_code is ExitCode.FINISHED
    doc = detail(state_root_path(repo), spec, "demo/C-1")
    assert doc is not None
    slots = the_slots(doc)
    assert [(a["item"], a["skipped"]) for a in slots] == [("s1", False), ("s2", False), ("s3", True)]
    assert [a["winner"] for a in slots] == [False, True, False]  # `s2` has no unmet warning
    assert [a["verdict"] for a in slots] == ["PROCEED", "PROCEED", None]
    assert slots[0]["keys"] == {"unmet_warnings": 1, "met": 1, "confidence": 0.8}
    assert slots[1]["cost"]["figure"] == 0.31 and slots[2]["cost"]["figure"] == 0.0 and slots[2]["step"] is None
    assert slots[1]["gate"]["verdict"] == "PROCEED" and next(u for u in doc["units"] if u["name"] == "pick")["state"] == "passed"


def test_plan_before_units_are_reached(repo: Path) -> None:  # RDD-B1
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex).exit_code is ExitCode.PAUSED
    doc = detail(state_root_path(repo), two_step(), "demo/T-1")
    assert doc is not None
    assert [p["name"] for p in doc["plan"]] == ["draft", "review", "finalizer"]
    assert {u["name"]: u["state"] for u in doc["units"]} == {"draft": "paused", "review": "not_reached"}


def test_finished_run(repo: Path) -> None:
    assert go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])).exit_code == 0
    doc = detail(state_root_path(repo), two_step(), "demo/T-1")
    assert doc is not None and doc["pause"] is None
    assert {u["name"]: u["state"] for u in doc["units"]} == {"draft": "passed", "review": "passed"}
    assert doc["health"]["burn_usd_per_h"] is not None and doc["health"]["orphaned"] is False


def _running_thread(repo: Path) -> tuple[Path, Path]:
    """A thread whose judge session is open: the run log stops after its attempt start."""
    root = state_root_path(repo)
    assert go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])).exit_code == 0
    log = run_dir(root, "demo", "T-1") / "run.jsonl"
    lines = log.read_text().splitlines()
    cut_at = next(i for i, ln in enumerate(lines) if json.loads(ln).get("session_key") == "review.1.judge")
    log.write_text("\n".join(lines[: cut_at + 2]) + "\n")  # attempt_start and session_opened of the judge
    return root, session_dir(root, "demo", "T-1", "review.1.judge")


def test_live_session_block(repo: Path) -> None:  # RDD-B4
    root, sdir = _running_thread(repo)
    now = datetime.now(UTC)
    started = (now - timedelta(seconds=12)).isoformat().replace("+00:00", "Z")
    recent = [{"name": "Read", "input_summary": f"f{i}.py", "ok": True, "duration_s": 0.1} for i in range(10)]
    (sdir / "live.json").write_text(json.dumps({
        "open_tool": {"name": "Grep", "capability": "search", "input_summary": f"TODO {CANARY}",
                      "started_at": started},
        "recent": recent, "last_text": "Checking", "tokens_so_far": None, "turns_so_far": None, "pgid": 4242,
        "last_event_at": started}))
    lock = RunLock(lock_path(root, "demo", "T-1"))
    lock.acquire()
    try:
        doc = detail(root, two_step(), "demo/T-1", now=now)
    finally:
        lock.release()
    assert doc is not None
    review = next(u for u in doc["units"] if u["name"] == "review")
    assert review["state"] == "running"
    sess = review["visits"][0]["attempts"][0]["judge"]["sessions"][0]
    live = sess["live"]
    assert live["open_tool"]["name"] == "Grep" and live["open_tool"]["capability"] == "search"
    assert live["open_tool"]["elapsed"] == pytest.approx(12, abs=1)
    assert CANARY not in json.dumps(doc) and len(live["recent"]) == 10 and live["pgid"] == 4242
    assert doc["health"]["alive"] is True and doc["health"]["suspect_stall"] is False
    no_live = detail(root, two_step(), "demo/T-1", with_live=False, now=now)
    assert no_live is not None
    rv = next(u for u in no_live["units"] if u["name"] == "review")
    assert "live" not in rv["visits"][0]["attempts"][0]["judge"]["sessions"][0]


def test_stall_hint(repo: Path) -> None:
    spec = two_step()
    units = dict(spec.units)
    units["review"] = dataclasses.replace(units["review"], step=dataclasses.replace(units["review"].step, idle_s=10))
    spec = dataclasses.replace(spec, units=units)
    root, sdir = _running_thread(repo)
    now = datetime.now(UTC)
    old = (now - timedelta(seconds=9)).isoformat().replace("+00:00", "Z")
    (sdir / "live.json").write_text(json.dumps({"open_tool": None, "recent": [], "last_event_at": old}))
    lock = RunLock(lock_path(root, "demo", "T-1"))
    lock.acquire()
    try:
        doc = detail(root, spec, "demo/T-1", now=now)
    finally:
        lock.release()
    assert doc is not None and doc["health"]["suspect_stall"] is True  # 9 s >= 80 % of 10 s


def test_orphaned_thread(repo: Path) -> None:  # RDD-B5, RDD-B6, SIL-AC22
    ex = standin("claude", steps=[DRAFT], judges=[])  # the judge call raises: the process dies mid-run
    with pytest.raises(AssertionError):
        go(repo, ex)
    before = hash_tree(state_root_path(repo))
    doc = detail(state_root_path(repo), two_step(), "demo/T-1")
    assert hash_tree(state_root_path(repo)) == before  # `detail()` hands nothing to the loop: only the verbs do
    assert doc is not None
    assert doc["health"]["orphaned"] is True and doc["pause"] is None
    assert doc["run"]["state"] in ("unfinished", "stopped")


def test_read_only_and_fast(repo: Path) -> None:  # RDD-B6, AC-2
    fixture_run(repo)
    root = state_root_path(repo)
    log = RunLog(run_dir(root, "demo", "T-1") / "run.jsonl")
    for i in range(5_000):
        log.write("check", unit="review", result="PASS", evidence=f"line {i}")
    before = hash_tree(root)
    t0 = time.perf_counter()
    for _ in range(5):
        doc = detail(root, two_step(), "demo/T-1")
    per_doc = (time.perf_counter() - t0) / 5
    assert hash_tree(root) == before
    assert doc is not None and per_doc < 0.3, per_doc


def leaky(ctx: Any) -> Any:
    from tempergraph.api import CheckResult
    from tempergraph.contracts import CheckFinding

    return CheckResult(result="PASS", evidence=f"token {CANARY} " + "e" * 900,
                       findings=[CheckFinding(status="pass", criterion="c-file")])


def test_text_is_scrubbed_and_clipped(repo: Path) -> None:  # RDD-AC3
    spec = two_step()
    units = dict(spec.units)
    from tempergraph.api import callable_ref

    gate = dataclasses.replace(units["draft"].gate, check=callable_ref(leaky))
    units["draft"] = dataclasses.replace(units["draft"], gate=gate)
    spec = dataclasses.replace(spec, units=units)
    blocker = "Reviewed.\n```json\n" + json.dumps({"criteria": [
        {"n": 1, "status": "UNVERIFIABLE", "evidence": f"saw {CANARY} " + "x" * 900, "fix": "y" * 900}],
        "gap": False, "confidence": 0.5}) + "\n```"
    ex = standin("claude", steps=[DRAFT], judges=[judge(blocker)])
    assert go(repo, ex, spec).exit_code is ExitCode.PAUSED
    doc = detail(state_root_path(repo), spec, "demo/T-1")
    text = json.dumps(doc)
    assert CANARY not in text
    att = doc["units"][0]["visits"][0]["attempts"][0]  # type: ignore[index]
    assert len(att["check"]["evidence"]) <= 400
    b = att["judge"]["blockers"][0]
    assert b["evidence"] and len(b["evidence"]) <= 400 and (b["fix"] is None or len(b["fix"]) <= 400)
    for line in doc["events_tail"]:  # type: ignore[index]
        assert CANARY not in line


def test_cut_drops_blocks_in_order(repo: Path) -> None:  # RDD-AC4
    doc = fixture_run(repo)
    small = cut(json.loads(json.dumps(doc)), limit=len(json.dumps(doc)) - 10)
    assert small["truncated"] == ["events_tail"] and small["events_tail"] == []
    smaller = cut(json.loads(json.dumps(doc)), limit=2_000)
    assert smaller["truncated"] == ["events_tail", "passed_attempts"]
    draft = next(u for u in smaller["units"] if u["name"] == "draft")
    assert draft["visits"][0]["attempts"] == [] and draft["visits"][0]["attempts_count"] == 2
    review = next(u for u in smaller["units"] if u["name"] == "review")
    assert review["visits"][0]["attempts"]  # a unit that did not pass keeps its detail


def test_unreadable_run_log(repo: Path) -> None:
    fixture_run(repo)
    root = state_root_path(repo)
    (run_dir(root, "demo", "T-1") / "run.jsonl").unlink()
    doc = detail(root, two_step(), "demo/T-1")
    assert doc is not None and doc["truncated"] == ["run_log_unreadable"]
    assert doc["run"]["state"] == "paused" and all(not u["visits"] for u in doc["units"])


def test_stale_plan(repo: Path) -> None:
    fixture_run(repo)
    root = state_root_path(repo)
    RunLog(run_dir(root, "demo", "T-1") / "run.jsonl").write("run_started", plan_digest="0" * 64)
    doc = detail(root, two_step(), "demo/T-1")
    assert doc is not None and doc["plan_stale"] is True


def test_status_detail_verb(repo: Path) -> None:
    fixture_run(repo)
    root = state_root_path(repo)
    before = hash_tree(root)
    code, doc, err = cli(repo, None, "status", "demo/T-1", "--detail", "--json")
    assert code == 0, err
    assert doc["run"]["thread_id"] == "demo/T-1" and doc["pause"]["unit"] == "review"
    code, one, _ = cli(repo, None, "status", "demo/T-1", "--detail", "--unit", "review")
    assert code == 0 and [u["name"] for u in one["units"]] == ["review"]
    assert cli(repo, None, "status", "demo/T-1", "--detail", "--unit", "nope")[0] == ExitCode.USAGE
    assert cli(repo, None, "status", "--detail")[0] == ExitCode.USAGE
    assert cli(repo, None, "status", "demo/T-404", "--detail")[0] == ExitCode.USAGE  # unknown thread
    assert hash_tree(root) == before


def test_the_detail_carries_the_loop_summary_of_the_thread(repo: Path) -> None:  # RDD-AC6
    from tempergraph.docs import append_jsonl

    fixture_run(repo)
    root = state_root_path(repo)
    log = run_dir(root, "demo", "T-1") / "loop.jsonl"
    assert detail(root, two_step(), "demo/T-1")["loop"] is None  # type: ignore[index]  # no loop child has ended
    top = [{"category": "tool_thrash", "unit": "draft", "confidence": 0.7},
           {"category": "wasted_turns", "unit": "review", "confidence": 0.6}]
    append_jsonl(log, {"ts": "2026-11-22T10:00:00Z", "kind": "loop_summary", "thread": "demo/T-1", "recorded": 1,
                       "filed": 0, "top": top[:1]})
    append_jsonl(log, {"ts": "2026-11-22T11:00:00Z", "kind": "loop_summary", "thread": "demo/T-1", "recorded": 3,
                       "filed": 1, "top": top})
    doc = detail(root, two_step(), "demo/T-1")
    assert doc is not None and doc["loop"]["recorded"] == 3 and doc["loop"]["filed"] == 1  # the newest summary
    assert doc["loop"]["top"] == top and all(set(o) == {"category", "unit", "confidence"} for o in doc["loop"]["top"])
    assert cut(dict(doc), limit=1)["loop"] == doc["loop"]  # the size cut leaves it in place
    code, one, _ = cli(repo, None, "status", "demo/T-1", "--detail", "--json")
    assert code == 0 and one["loop"]["recorded"] == 3
    other = detail(root, two_step(), "demo/T-1", unit="review")
    assert other is not None and "loop" in other


def _shape(value: object) -> object:
    """Keys and value types, not values: what a reader of the document relies on."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_shape(v) for v in value[:1]]
    if isinstance(value, bool) or value is None:
        return type(value).__name__
    return "number" if isinstance(value, (int, float)) else type(value).__name__


def test_monitor_fixtures_match_the_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The monitor mod is tested on fixtures of this engine's documents (MOV §5); they must not drift."""
    import importlib.util

    script = Path(__file__).resolve().parents[3] / "tempergraph-monitor" / "tests" / "fixtures" / "make_fixtures.py"
    if not script.exists():
        pytest.skip("the monitor plugin is not beside the engine")
    spec = importlib.util.spec_from_file_location("make_fixtures", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "OUT", tmp_path)
    mod.main()
    for name in ("status.json", "detail-paused.json"):
        fresh = json.loads((tmp_path / name).read_text())
        held = json.loads((script.parent / name).read_text())
        assert _shape(fresh) == _shape(held), f"{name}: run make_fixtures.py and commit the result"
    fresh_kinds = [json.loads(line)["kind"] for line in (tmp_path / "run-paused.jsonl").read_text().splitlines()[1:]]
    held_kinds = [json.loads(line)["kind"] for line in (script.parent / "run-paused.jsonl").read_text().splitlines()[1:]]
    assert fresh_kinds == held_kinds
