"""A finding with no `segment_started` is bound to the segment of the latest `run_exit` at or before its time, and the
facts row and the prompt's sections both use that binding (SIL-B51, SIL-AC62)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.improve import pause_facts
from tempergraph.improve.record import _when, findings_path, read_findings
from tempergraph.store.layout import state_root_path

from .fixtures.workflows import two_step
from .test_pause_findings_at_final_exit import (
    CANARY,
    DRAFT,
    NO_SLEEP,
    REVIEW,
    UNVERIFIABLE,
    finish,
    judge,
    judged_prompts,
    loop_on,
    paused_on_retries,
    registry,
    resume,
    run_log,
)


def test_findings_without_a_segment_start_are_bound_by_their_time(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # SIL-AC62, AC 7
    loop_on(monkeypatch)
    ex = paused_on_retries(repo, "B-1")  # segment 1 pauses at `draft`
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge(UNVERIFIABLE)]
    again = resume(two_step(), "B-1", repo, registry(ex), decision="retry", feedback=CANARY["feedback"],
                   settings=NO_SLEEP)
    assert again.payload["unit"] == "review", again.message  # segment 2 pauses at `review`
    finish(repo, "B-1", ex, feedback=CANARY["ruling"], ruling=True, caller={"kind": "agent"})  # segment 3, final
    root = state_root_path(repo)
    log = run_log(repo, "B-1")
    starts = [r for r in log if r["kind"] == "run_started"]
    exits = [r for r in log if r["kind"] == "run_exit"]
    assert len(starts) == 3 and len(exits) == 3
    doc = json.loads(findings_path(root, "demo", "B-1").read_text())
    # the stand-in run is fast: move the later segments an hour on so no two exits share a second
    path = state_root_path(repo) / "runs" / "demo" / "B-1" / "run.jsonl"
    cut = log.index(starts[1])
    renamed: dict[str, str] = {}
    for n, r in enumerate(log[cut:], cut):
        moved_ts = (_when(r["ts"]) + timedelta(hours=1)).isoformat()  # type: ignore[operator]
        if r["kind"] == "run_started":
            renamed[r["ts"]] = moved_ts
        log[n] = {**r, "ts": moved_ts}
    path.write_text("\n".join(json.dumps(r) for r in log) + "\n")
    for f in doc["findings"]:
        if f.get("segment_started") in renamed:
            f["segment_started"] = renamed[f["segment_started"]]
            f["at"] = (_when(f["at"]) + timedelta(hours=1)).isoformat()  # type: ignore[operator]
    first_exit = _when(exits[0]["ts"])
    late = timedelta(seconds=4)
    moved = False
    for f in doc["findings"]:
        if f.get("segment_exit") == 3 and f["segment_started"] == starts[0]["ts"]:
            f["at"] = (first_exit + (late if not moved else timedelta())).isoformat()  # type: ignore[operator]
            moved = True
        if f.get("segment_exit") == 3 and f["segment_started"] == starts[0]["ts"]:
            del f["segment_started"]
    assert moved
    findings_path(root, "demo", "B-1").write_text(json.dumps(doc))
    paused = [f for f in read_findings(root, "demo", "B-1") if f.get("segment_exit") == 3 and f.get("fingerprint")]
    bare = [f for f in paused if "segment_started" not in f]
    assert bare and len(bare) < len(paused)
    rows = pause_facts.of(root, "demo", "B-1", paused)
    assert all(str(f["fingerprint"]) in rows for f in paused)
    assert all(rows[str(f["fingerprint"])]["unit"] == "draft" for f in bare)  # the first segment's own pause
    (prompt,) = judged_prompts()
    heads = [ln for ln in prompt.splitlines() if ln.startswith("## The segment's records")]
    assert len(heads) == 3, heads
    assert [("exit code 3" in h, "exit code 0" in h) for h in heads] == [(True, False), (True, False), (False, True)]


def records(*specs: tuple[str, str, str | None]) -> list[dict[str, Any]]:
    """Segments written by hand: (run_started ts, run_exit ts, unit of the pause)."""
    out: list[dict[str, Any]] = []
    for start, end, unit in specs:
        out.append({"kind": "run_started", "ts": start})
        if unit:
            out.append({"kind": "pause", "ts": end, "unit": unit, "reason": f"r_{unit}"})
        out.append({"kind": "run_exit", "ts": end, "exit_code": 3})
    return out


def rows_of(tmp_path: Path, recs: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    path = tmp_path / "runs" / "demo" / "T-1" / "run.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    return pause_facts.of(tmp_path, "demo", "T-1", findings)


def test_a_finding_made_in_the_second_of_a_segments_exit_binds_to_that_segment(
        tmp_path: Path) -> None:  # SIL-AC62, AC 7
    recs = records(("2026-11-26T01:00:00+00:00", "2026-11-26T01:00:10.200000+00:00", "a"),
                   ("2026-11-26T01:05:00+00:00", "2026-11-26T01:05:10.900000+00:00", "b"))
    f = {"kind": "finding", "thread": "demo/T-1", "segment_exit": 3, "unit": "x", "fingerprint": "fp1",
         "at": "2026-11-26T01:00:10+00:00"}  # whole second of the first exit, though the record is 0.2 s into it
    g = {**f, "fingerprint": "fp2", "at": "2026-11-26T01:05:10.700000+00:00"}  # 0.7 s into the second's second
    rows = rows_of(tmp_path, recs, [f, g])
    assert rows["fp1"]["unit"] == "a" and rows["fp2"]["unit"] == "b"
    later = {**f, "fingerprint": "fp3", "at": "2026-11-26T01:03:00+00:00"}  # between the exits: the first's
    assert pause_facts.segment_of(later, recs) == (0, 3)


def test_a_finding_with_no_start_and_an_unreadable_time_gets_no_row(tmp_path: Path) -> None:  # SIL-AC62, AC 7
    recs = records(("2026-11-26T01:00:00+00:00", "2026-11-26T01:00:10+00:00", "a"))
    f = {"kind": "finding", "thread": "demo/T-1", "segment_exit": 3, "unit": "a", "fingerprint": "fp1", "at": "soon"}
    assert pause_facts.segment_of(f, recs) is None
    assert rows_of(tmp_path, recs, [f]) == {}
