"""T7.4: `report` (OBS §2.4), stats rows and `stats` (OBS §2.4, CST §2.2, §2.5), the machine index and
`--all-roots` (CST §2.1), and `attention` (CLI-B6, AC-5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.executors.standins import standin
from tempergraph.observe import report as rep
from tempergraph.observe import rows
from tempergraph.run.log import RunLog
from tempergraph.store.layout import home_path, run_dir, state_root_path

from .conftest import hash_tree
from .test_cli import cli
from .test_run import DRAFT, REVIEW, go, judge, verdict_block


def paused_run(repo: Path, task: str = "T-1") -> None:
    """The monitor fixture's run: draft retried, review sent back once, then escalated (exit 3)."""
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW, DRAFT, REVIEW],
                 judges=[judge(verdict_block("UNMET")), judge(), judge(verdict_block("UNMET", defect_in="notes")),
                         judge(), judge(verdict_block("UNVERIFIABLE"))])
    go(repo, ex, task=task)


def write_log(root: Path, task: str, recs: list[dict[str, Any]]) -> Path:
    log = RunLog(run_dir(root, "demo", task) / "run.jsonl")
    for r in recs:
        log.write(r.pop("kind"), **r)
    return log.path


def usage(rep_usd: float | None, est_usd: float | None) -> dict[str, Any]:
    return {"input_tokens": 10, "output_tokens": 5, "reported_cost_usd": rep_usd, "estimated_cost_usd": est_usd}


def test_units_first_visit_and_repeats(repo: Path) -> None:  # OBS-AC-5
    paused_run(repo)
    doc = rep.report(state_root_path(repo), None)
    units = {u["unit"]: u for u in doc["units"]}
    assert units["draft"]["first_visit"]["sessions"] == 2  # step and its judge
    assert set(units["draft"]["repeats"]) == {"retry: judge", "back:review"}
    assert set(units["review"]["repeats"]) == {"proceed"}
    assert doc["steps_and_judges"]["steps"]["sessions"] == 5 and doc["steps_and_judges"]["judges"]["sessions"] == 5
    crit = {c["criterion"]: c for c in doc["criteria"]}
    assert crit["c-file"]["statuses"] == {"MET": 2, "UNMET": 1}
    assert crit["c-review"]["statuses"] == {"UNMET": 1, "UNVERIFIABLE": 1}
    assert {(a["unit"], a["arm"]) for a in doc["arms"]} >= {("review", "gate:ESCALATE"), ("draft", "gate:RETRY")}


def test_mixed_executors_never_summed(repo: Path) -> None:  # OBS-B2, OBS-AC-3
    root = state_root_path(repo)
    write_log(root, "T-9", [
        {"kind": "run_started", "workflow_version": "1"},
        {"kind": "unit_entered", "unit": "a", "visit": 1, "entered_from": "start"},
        {"kind": "agent_run", "unit": "a", "attempt": 1, "executor": "antigravity", "session_kind": "step",
         "usage": usage(None, 0.31)},
        {"kind": "agent_run", "unit": "a", "attempt": 1, "executor": "claude", "session_kind": "judge",
         "usage": usage(0.22, 0.20)},
        {"kind": "agent_run", "unit": "a", "attempt": 2, "executor": "antigravity", "session_kind": "retry",
         "usage": usage(None, 0.44)},
        {"kind": "agent_run", "unit": "a", "attempt": 2, "executor": "claude", "session_kind": "judge",
         "usage": usage(None, None)},
    ])
    doc = rep.report(root, None)
    t = doc["total"]
    assert (t["reported_usd"], t["reported_sessions"], t["sessions"]) == (0.22, 1, 4)
    assert t["estimated_usd"] == 0.95 and t["completeness"] == "incomplete" and t["unmeasured"] == 1
    assert doc["by_executor"]["antigravity"]["reported_usd"] is None
    code, text, _ = cli(repo, None, "report", "all")
    assert code == 0 and "≥ $0.22 rep (1 of 4) · $0.95 est · incomplete" in text


def test_gate_escape_and_timeouts(repo: Path) -> None:  # OBS §2.4, OBS-B6
    root = state_root_path(repo)
    write_log(root, "T-8", [
        {"kind": "judgement", "unit": "a", "statuses": [{"n": 1, "id": "tests", "status": "MET"}]},
        {"kind": "gate", "unit": "a", "verdict": "PROCEED"},
        {"kind": "agent_run", "unit": "b", "attempt": 1, "session_kind": "step", "usage": usage(None, None),
         "timed_out": True, "stalled": True},
        {"kind": "agent_run", "unit": "b", "attempt": 1, "session_kind": "judge", "usage": usage(None, None),
         "stalled": True},
        {"kind": "judgement", "unit": "b", "statuses": [{"n": 1, "id": "tests", "status": "UNMET"}]},
        {"kind": "gate", "unit": "b", "verdict": "RETRY"},
    ])
    doc = rep.report(root, None)
    assert [c["escapes"] for c in doc["criteria"] if c["criterion"] == "tests"] == [1]
    assert [t["class"] for t in doc["timeouts"]] == ["hung", "stalled"]


def test_time_profile_and_loop_signal(repo: Path) -> None:  # OBS-B5
    root = state_root_path(repo)
    log = write_log(root, "T-7", [
        {"kind": "agent_run", "unit": "a", "attempt": 1, "session_kind": "step", "session_key": "a.1.step",
         "usage": usage(None, None)}])
    journal = log.parent / "sessions" / "a.1.step" / "activity.jsonl"
    journal.parent.mkdir(parents=True)
    lines = []
    for i in range(5):
        lines += [{"ev": "tool_started", "call_id": str(i), "name": "Bash", "capability": "shell",
                   "input_summary": "/usr/bin/make test"},
                  {"ev": "tool_finished", "call_id": str(i), "ok": True, "duration_s": 1.5}]
    journal.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    doc = rep.report(root, None)
    assert doc["time_profile"] == {"sessions": 1, "tool_s": {"Bash": 7.5}, "program_s": {"make": 7.5}}
    assert doc["loops"] == [{"thread_id": "demo/T-7", "session_key": "a.1.step", "tool": "Bash", "repeats": 5}]
    assert "make test" not in json.dumps(doc)


def test_report_is_read_only_and_windowed(repo: Path) -> None:
    paused_run(repo)
    root = state_root_path(repo)
    before = hash_tree(root)
    for argv in (("report",), ("report", "7d", "--by", "executor"), ("report", "all", "--by", "version", "--json")):
        assert cli(repo, None, *argv)[0] == 0
    assert hash_tree(root) == before
    assert cli(repo, None, "report", "soon")[0] == 2
    assert rep.report(root, rep.window("1h"))["threads"] == 1


def test_stats_row_at_each_exit(repo: Path) -> None:  # OBS §2.4, CST §2.2
    paused_run(repo)
    files = sorted((home_path() / "stats").glob("*.jsonl"))
    assert len(files) == 1
    [row] = [json.loads(x) for x in files[0].read_text().splitlines()]
    assert row["thread_id"] == "demo/T-1" and row["exit_code"] == 3 and row["segment"] == 0
    assert row["sessions"] == 10 and row["reported_cost_usd"] == 0.1 and row["completeness"] == "complete"
    assert row["repeats"] == {"retry": 1, "back": 1, "proceed": 1} and row["gate_verdicts"]["ESCALATE"] == 1
    assert "Release 1.2 notes" not in files[0].read_text()
    code, doc, _ = cli(repo, None, "stats", "--by", "workflow", "--projection")
    assert code == 0 and doc["totals"]["runs"] == 1 and doc["by"]["groups"]["demo"]["reported_usd"] == 0.1
    assert doc["projection"] == []  # no finished run yet


def test_projection_marks_thin_samples() -> None:  # CST §2.5
    found = [{"row_id": str(i), "thread_id": f"w/T-{i}", "workflow": "w", "exit_code": 0, "estimated_cost_usd": c}
             for i, c in enumerate([1.0, 2.0, 3.0, 10.0])]
    assert rows.projection(found) == [{"workflow": "w", "runs": 4, "median_usd": 2.5, "p90_usd": 10.0, "thin": True}]


def test_rows_deduplicated(tmp_path: Path) -> None:  # CST-AC-3
    p = tmp_path / "a.jsonl"
    p.write_text("\n".join(json.dumps({"row_id": "r1", "n": i}) for i in range(2)) + "\n"
                 + json.dumps({"row_id": "r2", "schema_version": 2}) + "\nnot json\n")
    found, unknown = rows.read_rows([p, p])
    assert [r["row_id"] for r in found] == ["r1"] and unknown == 2


def test_machine_index_and_all_roots(repo: Path, tmp_path: Path) -> None:  # CST §2.1
    paused_run(repo)
    index = rows.read_index()
    assert [r["path"] for r in index] == [str(state_root_path(repo).resolve())]
    gone = tmp_path / "gone" / ".tempergraph"
    rows.touch_index(gone)
    code, doc, _ = cli(repo, None, "status", "--all-roots")
    assert code == 0 and {r["path"]: r["missing"] for r in doc["roots"]}[str(gone.resolve())] is True
    assert [t["thread_id"] for t in doc["threads"]] == ["demo/T-1"]
    assert rows.read_index()[1]["path"] == str(gone.resolve())  # a reader never removes an entry


def test_attention_lists_each_pause_once_oldest_first(repo: Path) -> None:  # CLI-B6, AC-5
    paused_run(repo, "T-1")
    paused_run(repo, "T-2")
    root = state_root_path(repo)
    before = hash_tree(root)
    code, doc, _ = cli(repo, None, "attention", "--json")
    assert code == 0 and hash_tree(root) == before
    assert [i["thread_id"] for i in doc["items"]] == ["demo/T-1", "demo/T-2"]
    first = doc["items"][0]
    assert first["unit"] == "review" and first["kind"] == "escalation"
    assert first["command"] == "tempergraph resume demo T-1 --decision <proceed|retry|back:draft|stop>"
    assert first["age_s"] is not None and first["decisions"] == ["proceed", "retry", "back:draft", "stop"]
    code, text, _ = cli(repo, None, "attention")
    assert code == 0 and "tempergraph resume demo T-2" in str(text)


def test_status_row_settings_and_stale(repo: Path) -> None:  # RST §2.7
    paused_run(repo)
    code, doc, _ = cli(repo, None, "status", "demo/T-1")
    [row] = doc["threads"]
    assert code == 0 and len(row["settings_digest"]) == 64 and row["overridden_keys"] == []
    assert row["settings_stale"] is False
    (state_root_path(repo) / "config").mkdir(exist_ok=True)
    (state_root_path(repo) / "config" / "settings.json").write_text(
        json.dumps({"schema_version": 1, "defaults": {"run.attempt_cap": 9}}))
    [row] = cli(repo, None, "status", "demo/T-1")[1]["threads"]
    assert row["settings_stale"] is True


def test_status_row_rerun_lineage(repo: Path) -> None:  # RRN §2.4, DUR §2.2
    from .test_cli import happy
    from .test_rerun import finished

    finished(repo, "R-1")
    code, _, err = cli(repo, standin("claude", steps=[REVIEW], judges=[judge()]), "rerun", "demo", "R-1",
                       "--from", "review")
    assert code == 0, err
    rows_ = {r["thread_id"]: r for r in cli(repo, happy(), "status")[1]["threads"]}
    assert [x["thread"] for x in rows_["demo/R-1"]["reruns"]] == ["demo/R-1~r1"] and "rerun_of" not in rows_["demo/R-1"]
    src = rows_["demo/R-1~r1"]["rerun_of"]
    assert src["thread"] == "demo/R-1" and src["unit"] == "review" and src["checkpoint_id"]
    assert "superseded_by" not in rows_["demo/R-1"]
    code, _, err = cli(repo, standin("claude", steps=[REVIEW], judges=[judge()]), "rerun", "demo", "R-1",
                       "--from", "review", "--same-branch")
    assert code == 0, err
    rows_ = {r["thread_id"]: r for r in cli(repo, happy(), "status")[1]["threads"]}
    assert rows_["demo/R-1"]["superseded_by"] == "demo/R-1~r2"
    assert rows_["demo/R-1"]["reruns"][-1] == {**rows_["demo/R-1"]["reruns"][-1], "same_branch": True}
