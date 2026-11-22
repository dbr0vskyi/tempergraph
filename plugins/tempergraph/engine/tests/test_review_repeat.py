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


def build_code_run(root: Path, task: str) -> None:
    rd = run_dir(root, "demo", task)
    lines = []
    for key in CODE3:
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
