"""Filing by the count alone: the causes of an answered pause file by the pattern rule on their fingerprint with no
judge answer (FFD-AC7), `resume_no_progress` files on a thread count of 2 (FFD-AC8), none is handed again for want of a
judge answer (SIL-AC46) and `loop_result` holds the reason and the counted numbers (FFD-AC9)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child, filing, record
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import unjudged_pause_findings

from .test_loop_child import judge_says, loop_rows
from .test_run import registry

COUNTED = ("answer_overrode:check", "upstream_confirmed:draft", "retry_passed_unchanged:budget", "retry_same_failure")


def seed(root: Path, n: int, cause: str, *, count: int = 1, rows: int = 1, side: str = "workflow",
         segment_exit: int | None = None) -> dict[str, Any]:
    """The ticket of run `demo/F-<n>` with `rows` segment findings of `cause` at unit `draft`, each of `count`."""
    fp = record.fingerprint(side, "demo", cause, "draft")
    lines = [{"kind": "finding", "thread": f"demo/F-{n}", "workflow": "demo", "unit": "draft", "cause": cause,
              "class": "fault", "side": side, "count": count, "remedy": "r", "fingerprint": fp,
              "at": datetime.now(UTC).isoformat(timespec="seconds"), "request_digest": f"r{n}", "machine": "m",
              **({"segment_exit": segment_exit} if segment_exit is not None else {})} for _ in range(rows)]
    path = record.findings_path(root, "demo", f"F-{n}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "thread": f"demo/F-{n}", "findings": lines}))
    return {"ticket_id": f"f{n}", "thread": f"demo/F-{n}", "workflow": "demo", "task_id": f"F-{n}",
            "state_root": str(root), "issue_repository": "team/notes", "dry_run": False, "executor": "claude",
            "fingerprints": [fp], "lenses": {"friction": True, "outcome": False}}


def silent_judge() -> Any:
    def reply(req: Any) -> Any:
        return answer("no answer", session_id="loop")
    return reply


@pytest.mark.parametrize("cause", COUNTED)
def test_ffd_ac7_three_runs_file_one_issue_and_two_file_none(tmp_path: Path, cause: str) -> None:  # FFD-AC7
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude", judges=[silent_judge()] * 3))  # the judge gives no answer for the finding
    for n in (1, 2):
        out = child.process(seed(root, n, cause), reg, host)
        assert [r["reason"] for r in out["results"]] == ["below_count"] and not host.issues
    out = child.process(seed(root, 3, cause), reg, host)
    assert [r["op"] for r in out["results"]] == ["filed"] and len(host.issues) == 1


def test_ffd_ac7_a_judge_that_denies_the_finding_does_not_stop_it_filing(tmp_path: Path) -> None:  # FFD-AC7
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    prompts: list[str] = []
    says = judge_says(0.1, attributed=False)

    def spy(req: Any) -> Any:
        prompts.append(req.prompt)
        return says(req)

    reg = registry(standin("claude", judges=[spy] * 3))
    for n in (1, 2, 3):
        out = child.process(seed(root, n, "answer_overrode:check"), reg, host)
    fp = record.fingerprint("workflow", "demo", "answer_overrode:check", "draft")
    assert all(fp in p for p in prompts)  # the prompt lists the finding
    assert [r["op"] for r in out["results"]] == ["filed"] and len(host.issues) == 1


def test_ffd_ac8_resume_no_progress_files_on_a_thread_count_of_two(tmp_path: Path) -> None:  # FFD-AC8
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude", judges=[silent_judge()] * 3))
    out = child.process(seed(root, 1, "resume_no_progress", side="engine"), reg, host)
    (below,) = out["results"]
    assert below["reason"] == "below_count" and not host.issues
    rows = [r for r in loop_rows(root, "F-1") if r["kind"] == "loop_result"]
    assert rows[0]["count"] == 1 and all(k not in rows[0] for k in ("runs", "requests", "machines"))
    out = child.process(seed(root, 2, "resume_no_progress", side="engine", rows=2), reg, host)  # two segments
    assert [r["op"] for r in out["results"]] == ["filed"] and len(host.issues) == 1
    filed = [r for r in loop_rows(root, "F-2") if r["kind"] == "issue_filed"]
    assert filed and filed[0]["reason"] == "fault"


def test_ffd_ac8_decide_counts_one_finding_of_count_two(tmp_path: Path) -> None:  # FFD-AC8
    t = seed(tmp_path, 1, "resume_no_progress", count=2, side="engine")
    (f,) = record.read_findings(tmp_path, "demo", "F-1")
    d = filing.decide(filing.Candidate(finding=f), [], "team/notes")
    assert (d.action, d.reason, d.counted) == ("file", "fault", {"count": 2}) and t["thread"] == f["thread"]
    f1 = {**f, "count": 1}
    d = filing.decide(filing.Candidate(finding=f1), [], "team/notes")
    assert (d.action, d.reason, d.counted) == ("record", "below_count", {"count": 1})


def test_sil_ac46_a_pause_finding_of_these_causes_needs_no_judge_answer(tmp_path: Path) -> None:  # SIL-AC46
    root = tmp_path / ".tempergraph"
    thread = "demo/F-1"
    seed(root, 1, "answer_overrode:check", segment_exit=3)
    other = record.read_findings(root, "demo", "F-1")
    fp_other = record.fingerprint("workflow", "demo", "slow_step", "draft")
    extra = {**other[0], "cause": "slow_step", "fingerprint": fp_other}
    record.append_findings(root, "demo", "F-1", thread, [extra])
    fp = other[0]["fingerprint"]
    log = child.loop_log(root, "demo", "F-1")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"ts": "2999-01-01T00:00:00+00:00", "kind": "loop_started",
                               "fingerprints": [fp, fp_other], "held": False}) + "\n")
    left = {str(f["fingerprint"]) for f in unjudged_pause_findings(root, "demo", "F-1", thread, home=tmp_path)}
    assert fp not in left  # covered with no loop_judged answer
    assert fp_other in left  # a friction fault of another cause with no answer is handed again


def test_ffd_ac9_loop_results_hold_the_reason_and_the_counted_numbers(tmp_path: Path) -> None:  # FFD-AC9
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude", judges=[silent_judge()] * 3))
    cause = "retry_same_failure"
    for n in (1, 2):
        child.process(seed(root, n, cause), reg, host)
    first = [r for r in loop_rows(root, "F-1") if r["kind"] == "loop_result"][0]
    assert first["reason"] == "below_count"
    assert all(isinstance(first[k], int) for k in ("runs", "requests", "machines")) and first["runs"] == 1
    dry = {**seed(root, 3, cause), "dry_run": True}
    child.process(dry, reg, host)
    (would,) = [r for r in loop_rows(root, "F-3") if r["kind"] == "loop_result" and r["op"] == "would_file"]
    assert would["reason"] == "pattern_met"
    assert (would["runs"], would["requests"], would["machines"]) == (3, 3, 1)
