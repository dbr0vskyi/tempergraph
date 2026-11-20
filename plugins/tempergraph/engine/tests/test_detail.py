"""The run detail document (RDD-B1–B6, RDD-AC-1–AC-4) and `status --detail`."""

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
    """A retry on draft, a trip back from review, then an escalation pause on review (RDD-AC-1 without a map)."""
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


def test_fixture_reproduces_the_expected_document(repo: Path) -> None:  # RDD-AC-1, B2, B3
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


def test_orphaned_thread(repo: Path) -> None:  # RDD-B5
    ex = standin("claude", steps=[DRAFT], judges=[])  # the judge call raises: the process dies mid-run
    with pytest.raises(AssertionError):
        go(repo, ex)
    doc = detail(state_root_path(repo), two_step(), "demo/T-1")
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


def test_text_is_scrubbed_and_clipped(repo: Path) -> None:  # RDD-AC-3
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


def test_cut_drops_blocks_in_order(repo: Path) -> None:  # RDD-AC-4
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
