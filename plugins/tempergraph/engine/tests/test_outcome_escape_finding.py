"""A read that shows an escape records an `outcome_escape` finding, fires the outcome lens in stable mode, files by
the pattern rule and is corroborated by kept review observations (SIL-B10, SIL-B16, SIL-B33, SIL-B34; task AC 3, AC 4)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph import identity
from tempergraph.executors.standins import standin
from tempergraph.improve import child, review
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import evidence_path, findings_path, read_findings, write_findings
from tempergraph.model import flow
from tempergraph.run.log import Ledger
from tempergraph.store.layout import run_dir

from .test_pr_later import END, QUIET, REPO, commit, pr_host, ticket_of
from .test_pr_later import review as pr_review
from .test_run import registry

CLEAN = {"lenses": {"friction": False}, "fault_fingerprints": [], "outcome_fingerprints": [], "fingerprints": []}


def make_run(root: Path, task: str, units: dict[str, list[str]], *, number: int = 1, request: str | None = None,
             verdict: str = "met") -> None:
    """A finished run of the fixture workflow that opened pull request `number`: its ledger row, the paths each unit
    wrote (run log and digest) and its request in the local evidence."""
    thread = f"demo/{task}"
    Ledger(path=root / "ledger.jsonl").append(
        {"kind": "run_segment", "thread_id": thread, "workflow": "demo", "workflow_version": "v1", "machine": "m1",
         "exit_code": 0, "outcome": {"verdict": verdict, "criteria": []},
         "pull_request": {"host": "example.test", "repo": REPO, "number": number, "commit": END}})
    rd = run_dir(root, "demo", task)
    rd.mkdir(parents=True, exist_ok=True)
    lines = []
    for unit, paths in units.items():
        key = f"{unit}.1.step"
        lines.append({"kind": "agent_run", "unit": unit, "session_key": key, "changed_paths": list(paths)})
        sdir = rd / "sessions" / key
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "digest.json").write_text(json.dumps({
            "session_key": key, "kind": "step", "unit": unit,
            "_wrote": sorted(identity.request_digest(p) for p in paths)}))
    (rd / "run.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines))
    if request is not None:
        path = evidence_path(root, "demo", task)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"request": {"request": request}}))


def hand(root: Path, spec: Any = QUIET) -> dict[str, Any]:
    path = child.hand_off(root, spec, "T-0", "demo/T-0", CLEAN, judge_executor="claude", home=root / "home",
                          dry_run=False)
    return ticket_of(path)


def process(root: Path, host: MemoryCodeHost, spec: Any = QUIET) -> dict[str, Any]:
    return child.process(hand(root, spec), registry(standin("claude")), host)


def escapes(root: Path, task: str) -> list[dict[str, Any]]:
    return [f for f in read_findings(root, "demo", task) if f.get("cause") == "outcome_escape"]


def loop_kinds(root: Path) -> list[dict[str, Any]]:
    p = child.loop_log(root, "demo", "T-0")
    return [json.loads(ln) for ln in p.read_text().splitlines()] if p.exists() else []


# -- SIL-AC29: an escape is a finding and fires the lens in stable mode --------------------------------------------

@pytest.mark.parametrize("mode", ["dev", "stable"])
def test_a_changes_requested_review_is_one_outcome_finding_with_no_session(tmp_path: Path, mode: str) -> None:
    # SIL-AC29, task AC 3
    spec = dataclasses.replace(QUIET, improvement_mode=mode)
    make_run(tmp_path, "T-1", {"draft": ["a.py"]}, request="R1")
    host = pr_host()
    host.reviews[(REPO, 1)] = [pr_review()]
    process(tmp_path, host, spec)
    (f,) = escapes(tmp_path, "T-1")
    assert (f["unit"], f["lens"], f["side"], f["class"]) == (flow.OUTCOME_UNIT, "outcome", "workflow", "fault")
    assert f["thread"] == "demo/T-1" and f["request_digest"] == identity.request_digest("R1")
    kinds = loop_kinds(tmp_path)
    assert not [r for r in kinds if r["kind"] in ("loop_judged", "review_planned")]  # no model call
    lens = [r for r in kinds if r["kind"] == "loop_lens"]
    assert [r["thread"] for r in lens] == (["demo/T-1"] if mode == "stable" else [])


def test_a_follow_up_commit_on_files_of_two_units_is_a_finding_for_each(tmp_path: Path) -> None:
    # SIL-AC29, task AC 3
    make_run(tmp_path, "T-1", {"draft": ["a.py"], "review": ["b.py"], "other": ["c.py"]}, request="R1")
    host = pr_host()
    host.commits[(REPO, 1)] = [commit(END, ["old.py"]), commit("bbbbbbb2", ["a.py", "b.py"])]
    process(tmp_path, host)
    assert sorted(f["unit"] for f in escapes(tmp_path, "T-1")) == ["draft", "review"]
    process(tmp_path, host)  # a second read adds no second finding
    assert len(escapes(tmp_path, "T-1")) == 2


def test_a_run_that_is_no_escape_gets_no_finding(tmp_path: Path) -> None:  # SIL-AC29, task AC 3
    make_run(tmp_path, "T-1", {"draft": ["a.py"]})
    make_run(tmp_path, "T-2", {"draft": ["a.py"]}, number=2, verdict="unmet")
    host = pr_host()
    host.reviews[(REPO, 1)] = [pr_review("approved")]
    host.reviews[(REPO, 2)] = [pr_review()]
    process(tmp_path, host)
    assert escapes(tmp_path, "T-1") == [] and escapes(tmp_path, "T-2") == []


# -- SIL-AC31: the pattern rule alone -----------------------------------------------------------------------------

def three_runs(root: Path, n: int) -> MemoryCodeHost:
    host = pr_host()
    for i in range(1, n + 1):
        make_run(root, f"T-{i}", {"draft": ["a.py"]}, number=i, request=f"request {i}")
        host.pulls.append({"repo": REPO, "number": i, "state": "open", "draft": True})
        host.reviews[(REPO, i)] = [pr_review()]
    return host


def test_escapes_of_three_runs_and_three_requests_file_one_issue(tmp_path: Path) -> None:  # SIL-AC31, task AC 3
    host = three_runs(tmp_path, 3)
    out = process(tmp_path, host)  # the outcome judge has no calibration score
    assert len(host.issues) == 1 and "outcome_escape" in host.issues[0]["title"]
    assert "filed" in {r["op"] for r in out["results"]}


def test_escapes_of_two_runs_are_recorded_and_file_none(tmp_path: Path) -> None:  # SIL-AC31, task AC 3
    host = three_runs(tmp_path, 2)
    out = process(tmp_path, host)
    assert host.issues == []
    assert out["results"] and {r["op"] for r in out["results"]} == {"recorded"}
    assert len(escapes(tmp_path, "T-1")) == 1 and len(escapes(tmp_path, "T-2")) == 1


# -- SIL-AC30: a kept review observation corroborates the escape finding -------------------------------------------

def observe(root: Path, task: str, unit: str, category: str = "tool_thrash") -> None:
    p = child.loop_log(root, "demo", task)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "review_done", "session_key": f"{unit}.1.step", "kept": 1,
                             "observations": [{"category": category, "check": "kept", "turns": [2]}]}) + "\n")


def with_unmet_finding(root: Path, task: str, unit: str) -> None:
    write_findings(root, "demo", task, f"demo/{task}", [
        {"kind": "finding", "thread": f"demo/{task}", "workflow": "demo", "unit": unit, "cause": "outcome_unmet:c1",
         "class": "fault", "side": "workflow", "lens": "outcome", "count": 1, "fingerprint": "u" * 16}])


def test_an_observation_recorded_before_the_escape_corroborates_it(tmp_path: Path) -> None:  # SIL-AC30, task AC 4
    make_run(tmp_path, "T-1", {"draft": ["a.py"], "review": ["b.py"]})
    with_unmet_finding(tmp_path, "T-1", "draft")
    observe(tmp_path, "T-1", "draft")
    host = pr_host()
    host.commits[(REPO, 1)] = [commit(END, []), commit("bbbbbbb2", ["a.py"])]
    process(tmp_path, host)
    (f,) = escapes(tmp_path, "T-1")
    assert f["unit"] == "draft" and f["review"] == "review:tool_thrash" and f["review_weight"] == 1
    (unmet,) = [x for x in read_findings(tmp_path, "demo", "T-1") if x["cause"].startswith("outcome_unmet")]
    assert "review" not in unmet  # SRV-B7: the `outcome_unmet` finding of lens `outcome` is still skipped


def test_an_observation_recorded_after_the_escape_corroborates_it(tmp_path: Path) -> None:  # SIL-AC30, task AC 4
    make_run(tmp_path, "T-1", {"draft": ["a.py"]})
    host = pr_host()
    host.commits[(REPO, 1)] = [commit(END, []), commit("bbbbbbb2", ["a.py"])]
    process(tmp_path, host)
    (f,) = escapes(tmp_path, "T-1")
    assert "review" not in f
    observe(tmp_path, "T-1", "draft")
    assert review.corroborate(tmp_path, "demo", "T-1", "demo/T-1") == 1
    (f,) = escapes(tmp_path, "T-1")
    assert f["review"] == "review:tool_thrash" and f["review_weight"] == 1


def test_an_observation_on_a_unit_with_no_escape_finding_changes_none(tmp_path: Path) -> None:
    # SIL-AC30, task AC 4
    make_run(tmp_path, "T-1", {"draft": ["a.py"], "review": ["b.py"]})
    host = pr_host()
    host.commits[(REPO, 1)] = [commit(END, []), commit("bbbbbbb2", ["a.py"])]
    observe(tmp_path, "T-1", "review")
    process(tmp_path, host)
    (f,) = escapes(tmp_path, "T-1")
    assert f["unit"] == "draft" and "review" not in f and "review_weight" not in f
    assert findings_path(tmp_path, "demo", "T-1").exists()
