"""A kept review observation corroborates a model-free finding of its unit and run, and then the finding files with
the category named; an observation alone files nothing (SRV-B7, SIL-B16, SIL-B17, SIL-AC8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child, digest
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import append_findings, fingerprint, read_findings
from tempergraph.store.layout import run_dir

from .test_loop_child import judge_says
from .test_review_budget import NONE_FOUND
from .test_review_repeat import THRASH, write_reviews
from .test_run import registry
from .test_session_review import bash, rec, session, ticket

NOTE = "NOTE-TEXT-9c1d"


def run_with_finding(root: Path, task: str, unit: str = "code", with_finding: bool = True) -> str:
    """A run whose `unit` session repeated one failing call, and the model-free finding `tool_repeat` for it."""
    rd = run_dir(root, "demo", task)
    key = f"{unit}.1.step"
    session(root, task, key, [bash("make", ok=False, out="No such file")] * 4)
    r = rec(key)
    (rd / "run.jsonl").write_text(json.dumps(r) + "\n")
    d = digest.build(rd / "sessions" / key, r, {"tools": ["shell"]})
    (rd / "sessions" / key / "digest.json").write_text(json.dumps(d))
    fp = fingerprint("workflow", "demo", "tool_repeat", unit)
    if with_finding:
        append_findings(root, "demo", task, f"demo/{task}", [{
            "kind": "finding", "thread": f"demo/{task}", "workflow": "demo", "workflow_version": "0.0.0",
            "segment_exit": 0, "unit": unit, "cause": "tool_repeat", "class": "fault", "side": "workflow", "count": 4,
            "remedy": "The step repeated one failing call: say what to do instead", "fingerprint": fp,
            "at": "2026-11-24T00:00:00+00:00"}])
    return fp


def child_ticket(root: Path, task: str, fps: list[str]) -> dict[str, Any]:
    return {**ticket(root, task), "thread": f"demo/{task}", "issue_repository": "team/notes", "ticket_id": f"t-{task}",
            "fingerprints": fps, "lenses": {"friction": bool(fps), "outcome": False}, "dry_run": False, "units": {}}


def reviewer(category: str | None = THRASH) -> Any:
    """The session reviewer's answer: one kept-able observation citing the repeated calls, or `none_found`."""
    if category is None:
        return answer(NONE_FOUND)
    block = {"observations": [{"category": category, "turns": [2, 3, 4], "remedy_class": "prompt", "confidence": 0.8,
                               "note": NOTE}], "conformance": [], "none_found": False}
    return answer("```json\n" + json.dumps(block) + "\n```")


def kinds(root: Path, task: str) -> list[str]:
    path = child.loop_log(root, "demo", task)
    return [json.loads(ln)["kind"] for ln in path.read_text().splitlines()]


def test_a_kept_observation_corroborates_the_finding_and_the_issue_names_its_category(tmp_path: Path) -> None:
    # SRV-AC15 (SRV-B7, SIL-B16)
    fp = run_with_finding(tmp_path, "C-1")
    host = MemoryCodeHost()
    out = child.process(child_ticket(tmp_path, "C-1", [fp]),
                        registry(standin("claude", judges=[judge_says(0.9), reviewer()])), host)
    assert [r["op"] for r in out["results"]] == ["filed"]
    (f,) = [f for f in read_findings(tmp_path, "demo", "C-1") if f["cause"] == "tool_repeat"]
    assert f["review"] == f"review:{THRASH}" and f["review_weight"] == 1
    (issue,) = host.issues
    assert THRASH in issue["body"] and NOTE not in issue["body"] and NOTE not in json.dumps(issue)


def test_without_a_kept_observation_the_finding_files_as_before(tmp_path: Path) -> None:  # SRV-AC15 (SRV-B7)
    # no kept observation: the reviewer finds none
    fp = run_with_finding(tmp_path, "C-2")
    host = MemoryCodeHost()
    child.process(child_ticket(tmp_path, "C-2", [fp]), registry(standin("claude", judges=[judge_says(0.9), reviewer(None)])),
                  host)
    (f,) = read_findings(tmp_path, "demo", "C-2")
    assert "review" not in f and "review_weight" not in f
    (issue,) = host.issues
    assert "review:" not in issue["body"] and THRASH not in issue["body"]
    # a kept observation of an earlier run only
    write_reviews(tmp_path, "C-0", [("code.1.step", [(THRASH, "kept")])])
    fp = run_with_finding(tmp_path, "C-3")
    host = MemoryCodeHost()
    child.process(child_ticket(tmp_path, "C-3", [fp]), registry(standin("claude", judges=[judge_says(0.9), reviewer(None)])),
                  host)
    (f,) = read_findings(tmp_path, "demo", "C-3")
    assert "review" not in f and "review_weight" not in f
    assert "review:" not in host.issues[0]["body"]


def test_an_observation_alone_files_nothing_and_never_lifts_a_finding(tmp_path: Path) -> None:  # SRV-AC15 (SRV-B7, SIL-B16)
    run_with_finding(tmp_path, "C-4", with_finding=False)  # a kept observation and no finding
    host = MemoryCodeHost()
    out = child.process({**child_ticket(tmp_path, "C-4", []), "review": "full"},
                        registry(standin("claude", judges=[reviewer()])), host)
    assert out["results"] == [] and not host.issues and not host.comments
    assert "review_done" in kinds(tmp_path, "C-4")
    # a corroborated finding the friction judge scores below the floor stays unfiled (SIL-AC8)
    fp = run_with_finding(tmp_path, "C-5")
    host = MemoryCodeHost()
    out = child.process(child_ticket(tmp_path, "C-5", [fp]),
                        registry(standin("claude", judges=[judge_says(0.5), reviewer()])), host)
    assert [r["op"] for r in out["results"]] == ["recorded"] and not host.issues and not host.comments
    (f,) = read_findings(tmp_path, "demo", "C-5")
    assert f["review"] == f"review:{THRASH}"  # corroborated all the same


def test_the_review_runs_before_the_issue_is_filed(tmp_path: Path) -> None:  # SRV-AC15 (SRV-B7, SIL-B17)
    fp = run_with_finding(tmp_path, "C-6")
    child.process(child_ticket(tmp_path, "C-6", [fp]),
                  registry(standin("claude", judges=[judge_says(0.9), reviewer()])), MemoryCodeHost())
    got = kinds(tmp_path, "C-6")
    assert got.index("review_done") < got.index("issue_filed")
    assert got.index("loop_judged") < got.index("review_planned")
