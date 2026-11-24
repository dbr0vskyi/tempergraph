"""The loop's summary, in the loop log and beside what waits in `attention` (SIL-B22, CLI-B20, SIL-AC14, CLI-AC10)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.docs import append_jsonl
from tempergraph.executors.standins import standin
from tempergraph.improve import child, loop_summary
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import append_findings
from tempergraph.store.layout import run_dir, state_root_path

from .conftest import hash_tree
from .test_cli import cli
from .test_loop_child import outcome_ticket
from .test_reports import paused_run
from .test_review_repeat import build_code_run, kept_block, write_reviews
from .test_run import DRAFT, REVIEW, go, judge, registry
from .test_session_review import ticket

NOTE = "NOTE-TEXT"  # the note the fixture reviews keep in their local evidence


def summaries(root: Path, task: str) -> list[dict[str, Any]]:
    path = run_dir(root, "demo", task) / "loop.jsonl"
    rows = [json.loads(ln) for ln in path.read_text().splitlines()] if path.exists() else []
    return [r for r in rows if r["kind"] == "loop_summary"]


def write_summary(root: Path, task: str, ts: str, recorded: int, filed: int,
                  top: list[tuple[str, str, float]], review_failed: dict[str, int] | None = None) -> None:
    append_jsonl(run_dir(root, "demo", task) / "loop.jsonl", {
        "ts": ts, "kind": "loop_summary", "thread": f"demo/{task}", "recorded": recorded, "filed": filed,
        "top": [{"category": c, "unit": u, "confidence": f} for c, u, f in top],
        **({} if review_failed is None else {"review_failed": review_failed})})


def write_loop(root: Path, task: str, rows: list[dict[str, Any]]) -> None:
    for r in rows:
        append_jsonl(run_dir(root, "demo", task) / "loop.jsonl", {"ts": "2026-11-22T10:00:00Z", **r})


def finished_run(repo: Path, task: str) -> None:
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, task=task).exit_code is ExitCode.FINISHED


def test_a_summary_counts_findings_and_keeps_three_observations_by_confidence(tmp_path: Path) -> None:  # SIL-AC14
    fake = [{"kind": "finding", "thread": "demo/S-1", "unit": "draft", "cause": f"check_fail:{n}", "class": "fault",
             "fingerprint": f"fp{n}", "side": "workflow"} for n in range(14)]
    append_findings(tmp_path, "demo", "S-1", "demo/S-1", fake)
    write_reviews(tmp_path, "S-1", [("a.1.step", [("tool_thrash", "kept")]), ("b.1.step", [("wasted_turns", "kept")]),
                                    ("c.1.step", [("prompt_misread", "kept")]), ("d.1.step", [("tool_thrash", "kept")]),
                                    ("e.1.step", [("tool_thrash", "kept"), ("judge_shallow", "unsupported")])])
    path = run_dir(tmp_path, "demo", "S-1") / "loop.jsonl"
    rows = [json.loads(ln) for ln in path.read_text().splitlines()]
    for r, conf in zip(rows, (0.7, 0.7, 0.55, 0.5, 0.45), strict=True):
        r["observations"] = [{**o, "confidence": conf if o["check"] == "kept" else 0.99} for o in r["observations"]]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    s = loop_summary.build(tmp_path, "demo", "S-1", [])
    assert s["kind"] == "loop_summary" and s["recorded"] == 14 and s["filed"] == 0
    assert s["top"] == [{"category": "tool_thrash", "unit": "a", "confidence": 0.7},
                        {"category": "wasted_turns", "unit": "b", "confidence": 0.7},
                        {"category": "prompt_misread", "unit": "c", "confidence": 0.55}]
    assert NOTE not in json.dumps(s)


def test_filed_counts_the_issues_the_child_opened_or_commented_on(tmp_path: Path) -> None:  # SIL-AC14
    results = [{"op": "filed"}, {"op": "commented"}, {"op": "recorded"}, {"op": "would_file"}]
    assert loop_summary.build(tmp_path, "demo", "S-2", results)["filed"] == 2


def test_a_loop_with_nothing_to_report_writes_zero_counts(tmp_path: Path) -> None:  # SIL-AC14
    s = loop_summary.build(tmp_path, "demo", "S-3", [])
    assert (s["recorded"], s["filed"], s["top"]) == (0, 0, [])


def failed(key: str | None, cls: str | None) -> dict[str, Any]:
    return {"kind": "review_failed", **({} if key is None else {"session_key": key}),
            **({} if cls is None else {"error_class": cls})}


def test_sil_ac16_a_summary_counts_the_failed_reviews_by_class(tmp_path: Path) -> None:  # SIL-AC16 (SIL-B24)
    write_loop(tmp_path, "F-1", [failed("a.1.step", "usage_limit"), failed("b.1.step", "usage_limit"),
                                 failed("c.1.step", "unparsed")])
    assert loop_summary.build(tmp_path, "demo", "F-1", [])["review_failed"] == {"usage_limit": 2, "unparsed": 1}


def test_sil_ac16_a_child_with_no_failed_review_has_an_empty_count(tmp_path: Path) -> None:  # SIL-AC16
    assert loop_summary.build(tmp_path, "demo", "F-2", [])["review_failed"] == {}
    write_loop(tmp_path, "F-2", [{"kind": "review_done", "session_key": "a.1.step"}])
    assert loop_summary.build(tmp_path, "demo", "F-2", [])["review_failed"] == {}


def test_sil_ac16_a_review_that_ended_done_on_its_retry_is_not_counted(tmp_path: Path) -> None:  # SIL-AC16
    write_loop(tmp_path, "F-3", [failed("a.1.step", "usage_limit"), failed("b.1.step", "usage_limit"),
                                 {"kind": "review_done", "session_key": "a.1.step", "retry": True},
                                 {**failed("b.1.step", "timed_out"), "retry": True}])  # a second failure: the latest class
    assert loop_summary.build(tmp_path, "demo", "F-3", [])["review_failed"] == {"timed_out": 1}


def test_sil_ac16_a_failed_review_naming_no_session_counts_as_one_error(tmp_path: Path) -> None:  # SIL-AC16
    write_loop(tmp_path, "F-4", [{"kind": "review_failed", "error": "RuntimeError"}, failed(None, None),
                                 failed("a.1.step", None)])
    assert loop_summary.build(tmp_path, "demo", "F-4", [])["review_failed"] == {"error": 3}


def test_cli_ac11_a_loop_that_read_nothing_is_shown_with_its_failed_reviews(repo: Path) -> None:  # CLI-AC11
    finished_run(repo, "A-6")
    root = state_root_path(repo)
    write_summary(root, "A-6", "2026-11-22T10:00:00Z", 0, 0, [], {"usage_limit": 16})
    before = hash_tree(root)
    code, doc, _ = cli(repo, None, "attention", "--json")
    assert code == 0 and doc["items"] == [] and hash_tree(root) == before
    (entry,) = doc["loop"]
    assert entry["thread"] == "demo/A-6" and entry["recorded"] == 0 and entry["top"] == []
    assert entry["review_failed"] == {"usage_limit": 16}
    text = cli(repo, None, "attention")[1]
    assert "Nothing is waiting" not in text and "usage_limit 16" in text
    assert "tempergraph improve review show demo/A-6" in text


def test_cli_ac11_a_summary_with_no_failed_review_shows_nothing(repo: Path) -> None:  # CLI-AC11, CLI-AC10
    finished_run(repo, "A-7")
    write_summary(state_root_path(repo), "A-7", "2026-11-22T10:00:00Z", 0, 0, [], {})
    assert cli(repo, None, "attention", "--json")[1]["loop"] == []
    finished_run(repo, "A-8")  # an older record has no `review_failed` key at all
    write_summary(state_root_path(repo), "A-8", "2026-11-22T11:00:00Z", 0, 0, [])
    code, doc, _ = cli(repo, None, "attention", "--json")
    assert code == 0 and doc["loop"] == [] and "Nothing is waiting" in cli(repo, None, "attention")[1]


def test_cli_ac11_the_summary_of_a_finding_carries_an_empty_failed_count(repo: Path) -> None:  # CLI-AC10
    finished_run(repo, "A-9")
    write_summary(state_root_path(repo), "A-9", "2026-11-22T10:00:00Z", 2, 0, [])
    (entry,) = cli(repo, None, "attention", "--json")[1]["loop"]
    assert entry["review_failed"] == {}


def test_the_child_writes_one_summary_per_ticket(tmp_path: Path) -> None:  # SIL-AC14
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude"))
    child.process(outcome_ticket(root, 1, calibrated=False), reg, host)
    (s,) = summaries(root, "O-1")
    assert s["thread"] == "demo/O-1" and s["recorded"] == 1 and s["filed"] == 0 and s["top"] == []
    child.process(outcome_ticket(root, 2, calibrated=True), reg, host)
    child.process(outcome_ticket(root, 3, calibrated=True), reg, host)  # the third run meets the pattern: filed
    (s3,) = summaries(root, "O-3")
    assert s3["recorded"] == 1 and s3["filed"] == 1 and len(host.issues) == 1


def test_a_review_leaves_its_finding_and_top_observations_in_the_summary(tmp_path: Path) -> None:  # SIL-AC14
    build_code_run(tmp_path, "S-4")
    t = {**ticket(tmp_path, "S-4"), "thread": "demo/S-4", "ticket_id": "t1", "fingerprints": [], "units": {},
         "lenses": {"friction": False, "outcome": False}, "dry_run": False, "issue_repository": "team/notes"}
    child.process(t, registry(standin("claude", judges=[kept_block()] * 3)), MemoryCodeHost())
    (s,) = summaries(tmp_path, "S-4")
    assert s["recorded"] == 1 and s["filed"] == 0  # the `review_repeat` finding counts as recorded
    assert [(o["category"], o["unit"]) for o in s["top"]] == [("prompt_misread", "code")] * 3
    assert all(set(o) == {"category", "unit", "confidence"} for o in s["top"])  # no note text


def test_attention_shows_the_newest_summary_of_each_workflow_beside_the_items(repo: Path) -> None:  # CLI-AC10
    finished_run(repo, "A-1")
    root = state_root_path(repo)
    write_summary(root, "A-1", "2026-11-22T10:00:00Z", 3, 0, [("tool_thrash", "draft", 0.7), ("wasted_turns", "review", 0.6)])
    before = hash_tree(root)
    code, doc, _ = cli(repo, None, "attention", "--json")
    assert code == 0 and hash_tree(root) == before  # it creates nothing
    assert doc["items"] == []  # a summary is never an item waiting on a person
    (entry,) = doc["loop"]
    assert (entry["workflow"], entry["thread"], entry["recorded"], entry["filed"]) == ("demo", "demo/A-1", 3, 0)
    assert entry["top"] == [{"category": "tool_thrash", "unit": "draft", "confidence": 0.7},
                            {"category": "wasted_turns", "unit": "review", "confidence": 0.6}]
    assert entry["command"] == "tempergraph improve review show demo/A-1"
    code, text, _ = cli(repo, None, "attention")
    assert code == 0 and "Nothing is waiting" not in text
    assert "3 recorded" in text and "0 filed" in text and "tool_thrash" in text
    assert "tempergraph improve review show demo/A-1" in text and hash_tree(root) == before


def test_attention_shows_only_the_later_thread_of_a_workflow(repo: Path) -> None:  # CLI-AC10
    finished_run(repo, "A-2")
    finished_run(repo, "A-3")
    root = state_root_path(repo)
    write_summary(root, "A-2", "2026-11-22T10:00:00Z", 1, 0, [("tool_thrash", "draft", 0.7)])
    write_summary(root, "A-3", "2026-11-22T11:00:00Z", 2, 1, [("wasted_turns", "draft", 0.6)])
    doc = cli(repo, None, "attention", "--json")[1]
    assert [e["thread"] for e in doc["loop"]] == ["demo/A-3"]


def test_a_summary_with_nothing_in_it_shows_nothing(repo: Path) -> None:  # CLI-AC10
    finished_run(repo, "A-4")
    write_summary(state_root_path(repo), "A-4", "2026-11-22T10:00:00Z", 0, 0, [])
    code, doc, _ = cli(repo, None, "attention", "--json")
    assert code == 0 and doc["loop"] == [] and doc["items"] == []
    assert "Nothing is waiting" in cli(repo, None, "attention")[1]


def test_the_items_of_paused_threads_are_unchanged_beside_a_summary(repo: Path) -> None:  # CLI-AC10
    paused_run(repo, "A-5")
    write_summary(state_root_path(repo), "A-5", "2026-11-22T10:00:00Z", 1, 0, [])
    doc = cli(repo, None, "attention", "--json")[1]
    assert [i["thread_id"] for i in doc["items"]] == ["demo/A-5"] and "recorded" not in doc["items"][0]
    assert [e["thread"] for e in doc["loop"]] == ["demo/A-5"]
    text = cli(repo, None, "attention")[1]
    assert text.index("tempergraph resume demo A-5") < text.index("tempergraph improve review show demo/A-5")
