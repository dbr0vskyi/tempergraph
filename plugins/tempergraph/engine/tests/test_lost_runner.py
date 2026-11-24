"""A runner lost without an exit is a final exit that `status`, `stop` and `attention` hand to the loop, once
(SIL-B29 to SIL-B32)."""

from __future__ import annotations

import dataclasses
import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph import detach
from tempergraph.api import CheckResult, callable_ref
from tempergraph.catalog import Catalog
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding
from tempergraph.durability.control import stop_file
from tempergraph.durability.lock import RunLock
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import read_findings
from tempergraph.observe.detail import detail
from tempergraph.run.runner import RunSettings, ledger_rows, resume
from tempergraph.store.layout import home_path, lock_path, run_dir, state_root_path

from .conftest import hash_tree
from .fixtures.workflows import two_step
from .test_cli import cli
from .test_run import DRAFT, REVIEW, go, judge, registry, verdict_block

NO_SLEEP = RunSettings(sleep=lambda s: None)


def fail_once(ctx: Any) -> CheckResult:
    """The first attempt's check fails; the second passes and its judge is the call that kills the run."""
    if ctx.attempt == 1:
        return CheckResult(result="FAIL", evidence="no file", findings=[
            CheckFinding(status="fail", criterion="c-file", place="notes.md", fix="write it", message="missing")])
    return CheckResult(result="PASS", evidence="ok", findings=[CheckFinding(status="pass", criterion="c-file")])


def spec_of() -> Any:
    spec = two_step()
    units = dict(spec.units)
    units["draft"] = dataclasses.replace(units["draft"],
                                         gate=dataclasses.replace(units["draft"].gate, check=callable_ref(fail_once)))
    return dataclasses.replace(spec, units=units)


def catalog() -> Catalog:
    return Catalog(specs={"demo": spec_of()})


def loop_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr(detach, "start", lambda *a, **k: True)  # the child is started by drain() in the test


def kill(repo: Path, task: str = "T-1") -> None:
    """A run whose process dies after a failed check: the judge call raises, so no `run_exit` is written."""
    ex = standin("claude", steps=[DRAFT, DRAFT], judges=[])
    with pytest.raises(AssertionError):
        go(repo, ex, spec_of(), task=task)


def verb(repo: Path, *argv: str, ex: Any = None) -> tuple[int, Any, str]:
    return cli(repo, ex, *argv, catalog=catalog())


def tickets() -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(child.tickets_dir(home_path()).glob("*.json"))]


def lost_rows(repo: Path, task: str = "T-1") -> list[dict[str, Any]]:
    return [r for r in ledger_rows(state_root_path(repo)) if r.get("kind") == "run_segment"
            and r.get("thread_id") == f"demo/{task}" and r.get("reason") == "runner_lost"]


def log_of(repo: Path, task: str = "T-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def exits(repo: Path, task: str = "T-1") -> list[dict[str, Any]]:
    return [r for r in log_of(repo, task) if r["kind"] == "run_exit"]


def signature(repo: Path, task: str) -> dict[str, Any]:
    rows = lost_rows(repo, task)
    return {"rows": [(r["exit_code"], r["reason"]) for r in rows],
            "causes": sorted(f["cause"] for f in read_findings(state_root_path(repo), "demo", task)),
            "tickets": len([t for t in tickets() if t["thread"] == f"demo/{task}"]),
            "recorded": len([r for r in log_of(repo, task) if r["kind"] == "finding_recorded"])}


def drain_with_friction_judge() -> list[dict[str, Any]]:
    def reply(req: Any) -> Any:
        return answer("```json\n" + json.dumps({"findings": []}) + "\n```", session_id="loop")
    return child.drain(registry=registry(standin("claude", judges=[reply] * 4)), host=lambda: MemoryCodeHost())


def test_status_hands_a_lost_runner_to_the_loop(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC22, AC 1, AC 3
    loop_on(monkeypatch)
    kill(repo)
    assert lost_rows(repo) == [] and tickets() == []
    code, doc, err = verb(repo, "status")
    assert code == 0, err
    (row,) = lost_rows(repo)
    assert (row["exit_code"], row["reason"]) == (5, "runner_lost")
    assert "check_fail:draft" in [f["cause"] for f in read_findings(state_root_path(repo), "demo", "T-1")]
    (t,) = tickets()
    assert t["thread"] == "demo/T-1" and t["lenses"]["friction"] is True and t["trigger"] == "runner_lost"
    assert exits(repo) == []  # the engine writes no `run_exit` for a lost segment
    assert [r["kind"] for r in log_of(repo)].count("finding_recorded") == 1
    doc2 = detail(state_root_path(repo), spec_of(), "demo/T-1")
    assert doc2 is not None and doc2["health"]["orphaned"] is True
    assert doc2["run"]["state"] in ("unfinished", "stopped")  # still resumable (DUR-B2)
    assert doc["threads"][0]["thread_id"] == "demo/T-1"


def test_attention_and_stop_find_the_same_lost_runner(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC23, RCT-AC5, AC 3
    loop_on(monkeypatch)
    kill(repo, "T-1")
    assert verb(repo, "status", "demo/T-1")[0] == 0
    want = signature(repo, "T-1")
    assert want["rows"] == [(5, "runner_lost")] and want["tickets"] == 1
    kill(repo, "T-2")
    assert verb(repo, "attention")[0] == 0
    assert signature(repo, "T-2") == want
    kill(repo, "T-3")
    code, _, err = verb(repo, "stop", "demo/T-3")
    assert code == ExitCode.USAGE and "not running" in err  # RCT-B3
    assert not stop_file(state_root_path(repo), "demo", "T-3").exists()  # no request file for a killed runner
    assert signature(repo, "T-3") == want


def test_a_lost_runner_older_than_the_window_changes_nothing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC24, AC 3
    loop_on(monkeypatch)
    kill(repo)
    path = run_dir(state_root_path(repo), "demo", "T-1") / "run.jsonl"
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    path.write_text("".join(json.dumps({**json.loads(ln), "ts": old}) + "\n" for ln in path.read_text().splitlines()))
    before = (hash_tree(state_root_path(repo)), hash_tree(home_path()))
    assert verb(repo, "status")[0] == 0
    assert verb(repo, "attention")[0] == 0
    assert (hash_tree(state_root_path(repo)), hash_tree(home_path())) == before
    assert not lock_path(state_root_path(repo), "demo", "T-1").with_suffix(".holder.json").exists()
    assert lost_rows(repo) == [] and tickets() == []


def test_a_lost_runner_is_recorded_once(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC25, AC 1, AC 3
    loop_on(monkeypatch)
    kill(repo, "T-1")
    for _ in range(2):
        assert verb(repo, "status")[0] == 0
    want = signature(repo, "T-1")
    assert want["rows"] == [(5, "runner_lost")] and want["tickets"] == 1 and want["recorded"] == 1
    assert len(want["causes"]) == len(set(want["causes"]))  # one findings entry per cause
    kill(repo, "T-2")  # a status and an attention at the same moment
    barrier = threading.Barrier(2)
    done: list[int] = []

    def run(*argv: str) -> None:
        barrier.wait()
        done.append(verb(repo, *argv)[0])

    threads = [threading.Thread(target=run, args=a) for a in (("status",), ("attention",))]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert done == [0, 0]
    assert signature(repo, "T-2") == want
    kill(repo, "T-3")  # a verb that finds the run lock held writes nothing
    lock = RunLock(lock_path(state_root_path(repo), "demo", "T-3"))
    lock.acquire()
    try:
        before = hash_tree(state_root_path(repo))
        assert verb(repo, "status")[0] == 0
        assert hash_tree(state_root_path(repo)) == before
    finally:
        lock.release()
    assert lost_rows(repo, "T-3") == []


def resumed_and_lost_again(repo: Path) -> None:
    ex = standin("claude", steps=[], judges=[])  # the judge call raises again
    with pytest.raises(AssertionError):
        resume(spec_of(), "T-1", repo, registry(ex), settings=NO_SLEEP)


def test_a_second_lost_segment_starts_no_second_loop(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC26, AC 1
    loop_on(monkeypatch)
    kill(repo)
    assert verb(repo, "status")[0] == 0
    assert len(tickets()) == 1
    drain_with_friction_judge()  # the loop ran: `loop_started` of trigger `runner_lost` exists
    started = [json.loads(ln) for ln in child.loop_log(state_root_path(repo), "demo", "T-1").read_text().splitlines()]
    assert [r["trigger"] for r in started if r["kind"] == "loop_started"] == ["runner_lost"]
    resumed_and_lost_again(repo)
    assert verb(repo, "status")[0] == 0
    assert len(lost_rows(repo)) == 2 and tickets() == []  # its own row, no second ticket


def test_a_second_lost_segment_with_the_first_ticket_waiting(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC26, AC 1
    loop_on(monkeypatch)
    kill(repo)
    assert verb(repo, "status")[0] == 0
    resumed_and_lost_again(repo)
    assert verb(repo, "status")[0] == 0
    assert len(lost_rows(repo)) == 2 and len(tickets()) == 1


def test_a_later_final_exit_starts_its_own_loop(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC27, AC 1
    loop_on(monkeypatch)
    kill(repo)
    assert verb(repo, "status")[0] == 0
    first = tickets()
    assert len(first) == 1 and first[0]["trigger"] == "runner_lost"
    ex = standin("claude", steps=[REVIEW], judges=[judge(), judge()])
    done = resume(spec_of(), "T-1", repo, registry(ex), settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    got = tickets()
    assert len(got) == 2  # one for each end
    assert [t.get("trigger") for t in got].count("runner_lost") == 1


def test_attention_lists_a_pause_once_beside_a_lost_runner(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # CLI-AC5, AC 1, AC 3
    loop_on(monkeypatch)
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(), judge(verdict_block("UNVERIFIABLE"))])
    assert go(repo, ex, spec_of(), task="T-1").exit_code is ExitCode.PAUSED
    kill(repo, "T-2")
    paused_dir = run_dir(state_root_path(repo), "demo", "T-1")
    before = hash_tree(paused_dir)
    code, doc, err = verb(repo, "attention", "--json")
    assert code == 0, err
    assert [i["thread_id"] for i in doc["items"]] == ["demo/T-1"]  # the pause once; a lost runner is no pause
    assert hash_tree(paused_dir) == before  # the paused thread's run folder is unchanged
    assert [(r["exit_code"], r["reason"]) for r in lost_rows(repo, "T-2")] == [(5, "runner_lost")]
    assert lost_rows(repo, "T-1") == []


def test_the_verbs_keep_their_results_when_the_hand_off_fails(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SIL-AC28, AC 3
    loop_on(monkeypatch)
    kill(repo)
    (state_root_path(repo) / "ledger.jsonl").mkdir()  # a ledger that cannot be written
    ex = standin("claude", steps=[DRAFT], judges=[judge()])
    code, doc, err = verb(repo, "status", ex=ex)
    assert code == 0 and doc["threads"][0]["thread_id"] == "demo/T-1", err
    code, _, err = verb(repo, "stop", "demo/T-1", ex=ex)
    assert code == ExitCode.USAGE and "not running" in err
    assert tickets() == [] and exits(repo) == [] and ex.calls == []
    import tempergraph.improve.lost as lost

    def boom(*a: Any, **k: Any) -> None:
        raise RuntimeError("the hand-off failed")

    monkeypatch.setattr(lost, "settle", boom)
    code, text, err = verb(repo, "attention", ex=ex)
    assert code == 0 and "Nothing is waiting on a person" in text, err
    assert verb(repo, "status", ex=ex)[0] == 0 and verb(repo, "stop", "demo/T-1", ex=ex)[0] == ExitCode.USAGE
    assert ex.calls == [] and exits(repo) == []
