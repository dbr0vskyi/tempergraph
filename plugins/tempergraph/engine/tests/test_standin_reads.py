"""A scripted stand-in session opens a named path and reports it as a `read` call (SRV-AC47; task AC 6).

Fixtures are engine runs on a scratch repository with stand-in sessions. Nothing here writes a journal by hand.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import answer, standin
from tempergraph.store.layout import run_dir, state_root_path

from .test_judge_changed_paths import judge_digest, judge_run, one_unit, writes
from .test_run import MET, go, judge


def journal(repo: Path, task: str, key: str) -> list[dict[str, Any]]:
    path = run_dir(state_root_path(repo), "demo", task) / "sessions" / key / "activity.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_a_scripted_judge_that_opens_a_path_reports_a_read_call(repo: Path) -> None:  # SRV-AC47, AC 6
    opened = answer(MET, tools=("Read",), session_id="j", reads=("notes.md",))
    ex = standin("claude", steps=[writes("notes.md", "b.md")], judges=[opened])
    assert go(repo, ex, one_unit(), task="R-1").exit_code is ExitCode.FINISHED
    started = [r for r in journal(repo, "R-1", "build.1.judge") if r.get("ev") == "tool_started"]
    reads = [r for r in started if r.get("capability") == "read" and r.get("input_summary") == "notes.md"]
    assert len(reads) == 1 and reads[0]["name"] == "Read"
    d = judge_digest(repo, "R-1", "build.1.judge")
    assert d["changed_total"] == 2 and d["changed_read"] == 1
    assert judge_run(repo, "R-1", "build.1.judge")["session_key"] == "build.1.judge"


def test_a_stand_in_reply_with_no_reads_pushes_the_same_events_as_before(repo: Path) -> None:  # SRV-AC47, AC 6
    ex = standin("claude", steps=[writes("a.md")], judges=[judge()])
    assert go(repo, ex, one_unit(), task="R-2").exit_code is ExitCode.FINISHED
    started = [r for r in journal(repo, "R-2", "build.1.judge") if r.get("ev") == "tool_started"]
    assert [(r["name"], r["call_id"], r["subagent"]) for r in started] == [("Read", "t0", False)]
    assert all(r.get("capability") is None and r.get("input_summary") is None for r in started)
    assert judge_digest(repo, "R-2", "build.1.judge")["changed_read"] == 0
