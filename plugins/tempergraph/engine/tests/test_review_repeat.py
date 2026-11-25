"""A category kept in several sessions of one unit is a finding that never files alone (SRV-B26 to SRV-B28)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child, digest, params, repeat, review
from tempergraph.improve import proposals as prp
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.record import findings_path, read_findings
from tempergraph.store.layout import run_dir

from .test_loop_child import judge_says
from .test_run import registry
from .test_session_review import bash, rec, session, ticket

THRASH = "tool_thrash"
CODE3 = ("code.1.step", "code.2.retry", "code.3.retry")


def obs(category: str, check: str = "kept") -> dict[str, Any]:
    return {"category": category, "turns": [1], "remedy_class": "prompt", "confidence": 0.7, "check": check,
            "corroborated": False}


def write_reviews(root: Path, task: str, rows: Sequence[tuple[str, Sequence[tuple[str, str]]]]) -> None:
    """Fixture review records: per session its observations as (category, check); evidence files hold a note."""
    rd = run_dir(root, "demo", task)
    rd.mkdir(parents=True, exist_ok=True)
    lines = []
    for key, observations in rows:
        public = [obs(c, k) for c, k in observations]
        lines.append(json.dumps({"kind": "review_done", "session_key": key, "observations": public,
                                 "kept": sum(1 for _, k in observations if k == "kept"), "none_found": False}))
        evidence = review.review_dir(root, "demo", task)
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / f"{key}.json").write_text(json.dumps({
            "schema_version": 1, "session_key": key, "view_chars": 1, "conformance": [], "none_found": False,
            "observations": [{**o, "note": "NOTE-TEXT"} for o in public]}))
    (rd / "loop.jsonl").write_text("\n".join(lines) + "\n")


def record(root: Path, task: str) -> list[dict[str, Any]]:
    return repeat.record(root, "demo", task, f"demo/{task}")


def causes(root: Path, task: str) -> list[str]:
    return [str(f["cause"]) for f in read_findings(root, "demo", task)]


def test_three_sessions_of_one_unit_give_one_finding(tmp_path: Path) -> None:  # SRV-AC10
    write_reviews(tmp_path, "R-1", [(k, [(THRASH, "kept")]) for k in CODE3])
    new = record(tmp_path, "R-1")
    (f,) = read_findings(tmp_path, "demo", "R-1")
    assert [x["cause"] for x in new] == [f["cause"]] == [f"review_repeat:{THRASH}"]
    assert f["unit"] == "code" and f["class"] == "fault" and f["side"] == "workflow" and f["lens"] == "review"
    assert f["sessions"] == list(CODE3) and f["review_weight"] == 3 and f["thread"] == "demo/R-1"
    assert "note" not in f and "NOTE-TEXT" not in findings_path(tmp_path, "demo", "R-1").read_text()
    assert record(tmp_path, "R-1") == [] and len(read_findings(tmp_path, "demo", "R-1")) == 1  # once per run


@pytest.mark.parametrize(("rows", "want"), [
    ([("code.1.step", [(THRASH, "kept")]), ("code.2.retry", [(THRASH, "kept")])], []),  # two sessions
    ([("code.1.step", [(THRASH, "kept")]), ("code.2.retry", [(THRASH, "kept")]),
      ("code.3.retry", [(THRASH, "unsupported")])], []),  # the third was rejected by the citation check
    ([("code.1.step", [(THRASH, "kept")] * 3), ("code.2.retry", [(THRASH, "kept")])], []),  # one session thrice
    ([("code.1.step", [(THRASH, "kept")]), ("code.2.retry", [(THRASH, "kept")]),
      ("plan.1.step", [(THRASH, "kept")])], []),  # three sessions of two units
    ([("code.1.step", [(THRASH, "kept")]), ("code.2.retry", [(THRASH, "kept")]),
      ("code.3.retry", [(THRASH, "kept")]), ("plan.1.step", [(THRASH, "kept")]),
      ("plan.2.retry", [(THRASH, "kept")])], ["code"]),  # the finding is on `code` only
])
def test_only_three_distinct_sessions_of_one_unit_count(tmp_path: Path, rows: Any, want: list[str]) -> None:  # SRV-AC10
    write_reviews(tmp_path, "R-2", rows)
    record(tmp_path, "R-2")
    assert [f["unit"] for f in read_findings(tmp_path, "demo", "R-2")] == want


@pytest.mark.parametrize(("category", "klass", "side"), [
    ("environment_fault", "infra", "host"),
    ("request_ambiguous", "designed", "workflow"),
    (THRASH, "fault", "workflow"),
])
def test_the_class_follows_the_category(tmp_path: Path, category: str, klass: str, side: str) -> None:  # SRV-AC10
    write_reviews(tmp_path, "R-3", [(k, [(category, "kept")]) for k in CODE3])
    record(tmp_path, "R-3")
    (f,) = read_findings(tmp_path, "demo", "R-3")
    assert f["cause"] == f"review_repeat:{category}" and f["class"] == klass and f["side"] == side
    in_backlog = [c for c in prp.clusters(tmp_path, "demo") if c["cause"] == f["cause"]]
    assert bool(in_backlog) == (klass == "fault")  # `improve backlog` lists a fault, never an infra finding


def test_the_finding_is_listed_by_the_backlog_as_a_cluster(tmp_path: Path) -> None:  # SRV-AC10
    write_reviews(tmp_path, "R-4", [(k, [(THRASH, "kept")]) for k in CODE3])
    record(tmp_path, "R-4")
    (c,) = prp.clusters(tmp_path, "demo")
    assert c["cause"] == f"review_repeat:{THRASH}" and c["unit"] == "code" and c["side"] == "workflow"
    assert c["review_weight"] == 3  # the cluster carries the weight of the observations it corroborates (SRV-B27)
    (f,) = read_findings(tmp_path, "demo", "R-4")
    assert f["review"] == f"review:{THRASH}"  # the finding carries `review:<category>`


def test_the_threshold_is_a_parameter_with_provenance() -> None:  # SRV-AC10
    p = params.PARAMS["review.repeat_sessions"]
    assert p.value == 3 and p.provenance == "default_no_data" and p.source


def test_the_finding_corroborates_its_own_category_on_its_unit(tmp_path: Path) -> None:  # SRV-AC11
    write_reviews(tmp_path, "R-5", [(k, [(THRASH, "kept")] + ([("prompt_misread", "kept")] if n < 2 else []))
                                    for n, k in enumerate(CODE3)] + [("plan.1.step", [(THRASH, "kept")])])
    record(tmp_path, "R-5")
    shown = review.show(tmp_path, "demo", "R-5")
    by_session = {s["session_key"]: s["observations"] for s in shown["sessions"]}
    for n, key in enumerate(CODE3):
        thrash = next(o for o in by_session[key] if o["category"] == THRASH)
        assert thrash["corroborated"] is True and thrash["review_weight"] == 3
        if n < 2:  # another category on the same unit, kept in two sessions only
            assert next(o for o in by_session[key] if o["category"] == "prompt_misread")["corroborated"] is False
    assert by_session["plan.1.step"][0]["corroborated"] is False  # the same category on another unit
    s = review.summary(tmp_path, "demo")
    assert s["kept"] == 6 and s["corroborated"] == 3 and s["corroboration_rate"] == 0.5
    row = next(r for r in s["rows"] if r["unit"] == "code" and r["category"] == THRASH)
    assert row["count"] == 3 and row["corroborated"] == 3
    assert "corroborated" not in next(r for r in s["rows"] if r["unit"] == "plan")
    assert "NOTE-TEXT" not in json.dumps(s)


def test_nothing_is_corroborated_without_the_finding(tmp_path: Path) -> None:  # SRV-AC11
    write_reviews(tmp_path, "R-6", [(k, [(THRASH, "kept")]) for k in CODE3[:2]])
    record(tmp_path, "R-6")
    assert all(not o["corroborated"] for s in review.show(tmp_path, "demo", "R-6")["sessions"]
               for o in s["observations"])
    assert review.summary(tmp_path, "demo")["corroborated"] == 0


def test_the_pairs_recorded_across_a_workflows_runs(tmp_path: Path) -> None:  # SRV-AC11
    write_reviews(tmp_path, "R-7", [(k, [(THRASH, "kept")]) for k in CODE3])
    record(tmp_path, "R-7")
    write_reviews(tmp_path, "R-8", [("code.1.step", [(THRASH, "kept")])])
    assert repeat.repeated(tmp_path, "demo") == {("code", THRASH)}


def keep(root: Path, task: str, rows: Sequence[tuple[str, Sequence[tuple[str, str]]]]) -> list[dict[str, Any]]:
    """One run of the workflow: its reviews are written, then the run's reviews end (`repeat.record`)."""
    write_reviews(root, task, rows)
    return record(root, task)


ONE = [("code.1.step", [(THRASH, "kept")])]


def backlog(root: Path) -> list[dict[str, Any]]:
    """What `improve backlog demo --json` lists, from the state root of a scratch repository."""
    from tempergraph.store.layout import state_root_path

    from .test_cli import cli

    code, doc, err = cli(root, None, "improve", "backlog", "demo", "--json")
    assert code == 0, err
    assert state_root_path(root) is not None
    return list(doc["clusters"])


def test_three_runs_keeping_a_category_give_the_third_a_finding(repo: Path) -> None:  # SRV-AC17
    from tempergraph.store.layout import state_root_path

    root = state_root_path(repo)
    assert keep(root, "X-1", ONE) == [] and keep(root, "X-2", ONE) == []
    assert backlog(repo) == []  # two runs: no finding, no cluster
    (new,) = keep(root, "X-3", ONE)
    (f,) = read_findings(root, "demo", "X-3")
    assert new["cause"] == f["cause"] == f"review_repeat:{THRASH}" and f["unit"] == "code" and f["lens"] == "review"
    assert f["runs"] == ["X-1", "X-2", "X-3"] and f["count"] == 3 and f["review_weight"] == 1
    assert f["review"] == f"review:{THRASH}" and f["thread"] == "demo/X-3"
    assert "note" not in f and "NOTE-TEXT" not in findings_path(root, "demo", "X-3").read_text()
    assert read_findings(root, "demo", "X-1") == [] and read_findings(root, "demo", "X-2") == []
    (c,) = backlog(repo)
    assert c["cause"] == f["cause"] and c["unit"] == "code" and c["runs"] == 1 and c["review_weight"] == 1
    assert record(root, "X-3") == [] and len(read_findings(root, "demo", "X-3")) == 1  # once per run
    shown = review.show(root, "demo", "X-3")["sessions"][0]["observations"][0]  # SRV-B27: the third run's observation
    assert shown["corroborated"] is True
    assert review.show(root, "demo", "X-1")["sessions"][0]["observations"][0]["corroborated"] is False


def test_a_rejected_observation_and_another_unit_count_for_nothing(tmp_path: Path) -> None:  # SRV-AC17
    keep(tmp_path, "Y-1", ONE)
    keep(tmp_path, "Y-2", ONE)
    assert keep(tmp_path, "Y-3", [("code.1.step", [(THRASH, "unsupported")])]) == []  # rejected by the citation check
    assert keep(tmp_path, "Y-4", [("plan.1.step", [(THRASH, "kept")])]) == []  # another unit
    assert keep(tmp_path, "Y-5", [("code.1.step", [("prompt_misread", "kept")])]) == []  # another category
    assert [c for c in prp.clusters(tmp_path, "demo")] == []


def test_sessions_of_a_run_count_once_as_a_run(tmp_path: Path) -> None:  # SRV-AC17
    two = [("code.1.step", [(THRASH, "kept")]), ("code.2.retry", [(THRASH, "kept")])]
    assert keep(tmp_path, "S-1", two) == []  # two sessions: below SRV-B26
    assert keep(tmp_path, "S-2", two) == []  # two runs of two sessions: two runs, not four
    (new,) = keep(tmp_path, "S-3", [("code.1.step", [(THRASH, "kept")])])  # a third run
    assert new["runs"] == ["S-1", "S-2", "S-3"]


def test_three_sessions_in_the_third_run_make_one_finding(tmp_path: Path) -> None:  # SRV-AC17 (SRV-B26 and SRV-B32)
    keep(tmp_path, "T-1", ONE)
    keep(tmp_path, "T-2", ONE)
    (new,) = keep(tmp_path, "T-3", [(k, [(THRASH, "kept")]) for k in CODE3])
    assert new["sessions"] == list(CODE3)  # SRV-B26 records it first; the count of runs adds no second finding
    assert [f["cause"] for f in read_findings(tmp_path, "demo", "T-3")] == [f"review_repeat:{THRASH}"]


def test_a_fourth_run_holds_a_finding_too(tmp_path: Path) -> None:  # SRV-AC17
    for n in (1, 2):
        keep(tmp_path, f"Q-{n}", ONE)
    keep(tmp_path, "Q-3", ONE)
    (new,) = keep(tmp_path, "Q-4", ONE)
    assert new["runs"] == ["Q-1", "Q-2", "Q-3", "Q-4"] and new["count"] == 4
    (c,) = prp.clusters(tmp_path, "demo")
    assert c["runs"] == 2  # the cluster lists the two runs that hold the finding


def test_environment_faults_across_runs_are_the_hosts(tmp_path: Path) -> None:  # SRV-AC17
    rows = [("code.1.step", [("environment_fault", "kept")])]
    for n in (1, 2, 3):
        keep(tmp_path, f"E-{n}", rows)
    (f,) = read_findings(tmp_path, "demo", "E-3")
    assert f["cause"] == "review_repeat:environment_fault" and f["class"] == "infra" and f["side"] == "host"
    assert prp.clusters(tmp_path, "demo") == []


def test_the_run_count_is_a_parameter_with_provenance() -> None:  # SRV-AC17
    p = params.PARAMS["review.repeat_runs"]
    assert p.value == 3 and p.provenance == "default_no_data" and "SRV-B32" in p.source


def build_code_run(root: Path, task: str, keys: Sequence[str] = CODE3) -> None:
    rd = run_dir(root, "demo", task)
    lines = []
    for key in keys:
        session(root, task, key, [bash("make")])
        r = rec(key, model="claude-sonnet-5-5")
        lines.append(json.dumps(r))
        d = digest.build(rd / "sessions" / key, r, {"tools": ["shell"]})
        (rd / "sessions" / key / "digest.json").write_text(json.dumps(d))
    (rd / "run.jsonl").write_text("\n".join(lines) + "\n")


def kept_block() -> Any:
    block = {"observations": [{"category": "prompt_misread", "turns": [1], "remedy_class": "prompt",
                               "confidence": 0.7, "note": "misread"}], "conformance": [], "none_found": False}
    return answer("```json\n" + json.dumps(block) + "\n```", cost=0.01)


def test_a_review_alone_files_nothing_in_any_run(tmp_path: Path) -> None:  # SRV-AC11
    host = MemoryCodeHost()
    for n, task in enumerate(("F-1", "F-2")):  # two runs record the same finding
        build_code_run(tmp_path, task)
        t = {**ticket(tmp_path, task), "thread": f"demo/{task}", "issue_repository": "team/notes", "ticket_id": f"t{n}",
             "fingerprints": [], "lenses": {"friction": False, "outcome": False}, "dry_run": False, "units": {}}
        out = child.process(t, registry(standin("claude", judges=[kept_block()] * 3)), host)
        assert out["results"] == []
        assert causes(tmp_path, task) == ["review_repeat:prompt_misread"]  # recorded by the review itself
    fps = [f["fingerprint"] for f in read_findings(tmp_path, "demo", "F-2")]
    later = {**ticket(tmp_path, "F-2"), "thread": "demo/F-2", "issue_repository": "team/notes", "ticket_id": "t9",
             "fingerprints": fps, "lenses": {"friction": True, "outcome": False}, "dry_run": False, "review": "off"}
    out = child.process(later, registry(standin("claude", judges=[judge_says(0.9)])), host)  # even a hand-made ticket
    assert not host.issues and not host.comments
    assert {r["op"] for r in out["results"]} <= {"recorded"}


@pytest.mark.parametrize("runs", [1, 2, 3])
def test_a_review_repeat_across_runs_files_nothing_in_any_run(tmp_path: Path, runs: int) -> None:  # SRV-AC11
    host = MemoryCodeHost()
    for n in range(runs):
        task = f"G-{n}"
        build_code_run(tmp_path, task, keys=("code.1.step",))
        t = {**ticket(tmp_path, task), "thread": f"demo/{task}", "issue_repository": "team/notes", "ticket_id": f"g{n}",
             "fingerprints": [], "lenses": {"friction": False, "outcome": False}, "dry_run": False, "units": {}}
        out = child.process(t, registry(standin("claude", judges=[kept_block()])), host)
        assert out["results"] == []
    assert causes(tmp_path, "G-2") == (["review_repeat:prompt_misread"] if runs == 3 else [])
    assert not host.issues and not host.comments
    fps = [f["fingerprint"] for f in read_findings(tmp_path, "demo", f"G-{runs - 1}")]
    later = {**ticket(tmp_path, f"G-{runs - 1}"), "thread": f"demo/G-{runs - 1}", "issue_repository": "team/notes",
             "ticket_id": "g9", "fingerprints": fps, "lenses": {"friction": True, "outcome": False}, "dry_run": False,
             "review": "off"}
    child.process(later, registry(standin("claude", judges=[judge_says(0.9)])), host)  # even a hand-made ticket
    assert not host.issues and not host.comments
