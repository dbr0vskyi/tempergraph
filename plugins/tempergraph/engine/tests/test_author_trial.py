"""`author verify` rungs 8 and 9, `author trial` and `author grade` (SCF §2.5, §2.7; SCF-B6, B8, AC-5 to AC-7).

Stand-in executors only: the judge stand-in answers each seed and trial judgement from a script."""

from __future__ import annotations

import copy
import io
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph.author.scaffold import read_session, scaffold
from tempergraph.cli.main import main
from tempergraph.executors.registry import Registry
from tempergraph.executors.scripted import answer
from tempergraph.executors.standins import standin

from .fixtures.packages import write
from .test_scaffold import GOOD_NOTES, outcome, session

SIGNALS = ({}, True)  # a person at a terminal (PRV §2.3)


def seeded() -> dict[str, Any]:
    o = outcome()
    o["final"][0]["verifier"]["scale"]["seeds"] = ["out-good", "out-bad"]
    o["intermediate"]["draft"]["criteria"][1]["verifier"]["scale"]["seeds"] = ["draft-good", "draft-bad"]
    return o


def seed_case(pkg: Path, gate: str, case_id: str, labels: dict[str, str]) -> None:
    folder = pkg / "evals" / "calibration" / gate / case_id
    write(folder, "fixture/workspace/notes.md", GOOD_NOTES)
    write(folder, "fixture/request.md", "v1.2")
    write(folder, "case.json", {"schema_version": 1, "case_id": case_id, "gate": gate, "state": "reviewed",
                                "labels": [{"criterion_id": k, "expected": v, "reason": "seed", "reviewer": "owner",
                                            "by_person": True} for k, v in labels.items()]})


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "--allow-empty",
                    "-m", "start"], cwd=r, check=True)
    return r


@pytest.fixture
def pkg(tmp_path: Path) -> Path:
    o = seeded()
    scaffold(read_session(session(tmp_path, o=copy.deepcopy(o))), tmp_path / "out" / "release-notes")
    p = tmp_path / "out" / "release-notes"
    seed_case(p, "draft", "draft-good", {"rn-faithful": "MET"})
    seed_case(p, "draft", "draft-bad", {"rn-faithful": "UNMET"})
    seed_case(p, "outcome", "out-good", {"rn-complete": "MET"})
    seed_case(p, "outcome", "out-bad", {"rn-complete": "UNMET"})
    return p


def verdict(*statuses: str, sid: str = "j") -> Any:
    rows = [{"n": i, "status": s, "evidence": "notes.md:3 lists every change", "defect_in": None, "no_change": False}
            for i, s in enumerate(statuses, 1)]
    return answer("Graded.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.9}) + "\n```",
                  tools=("Read",), session_id=sid)


def draft_judge(status: str) -> Any:
    return verdict("MET", status, sid="j-draft")  # rn-sections is the check's; the judge rows every criterion


def seed_answers(draft_bad: tuple[str, str] = ("UNMET", "UNMET")) -> list[Any]:
    """Seeds in order: draft gate (draft-bad, draft-good) twice each, then the outcome gate (out-bad, out-good)."""
    return [draft_judge(draft_bad[0]), draft_judge(draft_bad[1]), draft_judge("MET"), draft_judge("MET"),
            verdict("UNMET"), verdict("UNMET"), verdict("MET"), verdict("MET")]


def step(req: Any) -> Any:
    (Path(req.workdir) / "notes.md").write_text(GOOD_NOTES, encoding="utf-8")
    return answer("Wrote the notes.\nARTIFACT notes: notes.md", session_id="s-draft")


def cli(repo: Path, reg: Registry, *argv: str) -> tuple[int, Any, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), registry=reg, cwd=repo, out=out, err=err, signals=SIGNALS)
    text = out.getvalue()
    try:
        doc = json.loads(text) if text.strip() else None
    except ValueError:
        doc = text
    return code, doc, err.getvalue()


def registry(steps: list[Any], judges: list[Any]) -> Registry:
    reg = Registry()
    reg.register(standin("claude", steps=steps, judges=judges))  # type: ignore[arg-type]
    return reg


def states(doc: dict[str, Any]) -> dict[str, str]:
    return {r["name"]: r["state"] for r in doc["rungs"]}


def test_seeds_graded_as_expected_pass_with_judge_sessions_only(pkg: Path, repo: Path) -> None:
    """Rung 8 passes; only judge sessions start (SCF-AC-5); the ladder goes on to stamp."""
    reg = registry([], seed_answers())
    code, doc, _ = cli(repo, reg, "author", "verify", str(pkg), "--judge-seeds", "--json")
    assert code == 0, json.dumps([r for r in doc["rungs"] if r["state"] != "passed"], indent=1)
    s = states(doc)
    assert s["judge_seeds"] == "passed" and s["trial"] == "skipped" and s["stamp"] == "passed"
    calls = reg.get("claude").calls  # type: ignore[attr-defined]
    assert len(calls) == 8 and {c.kind for c in calls} == {"judge"}
    assert doc["usage"]["judge_sessions"] == 8
    assert {(g["criterion"], g["seed"]) for g in doc["seeds"]} == {
        ("rn-faithful", "draft-good"), ("rn-faithful", "draft-bad"), ("rn-complete", "out-good"),
        ("rn-complete", "out-bad")}
    assert not (pkg / "evals" / "calibration" / "draft" / "scores.jsonl").exists()  # never counts as a score


def test_a_seed_states_its_own_expectation_without_a_label(pkg: Path, repo: Path) -> None:
    """A synthetic seed with no label is graded against its `seed` block; a block for another criterion is not
    an expectation, so the seed stays `seed-unlabelled` (SCF §2.5)."""
    for gate, sid, cid, exp in (("draft", "draft-good", "rn-faithful", "MET"), ("draft", "draft-bad", "rn-faithful", "UNMET"),
                                ("outcome", "out-good", "rn-complete", "MET"), ("outcome", "out-bad", "rn-complete", "UNMET")):
        write(pkg / "evals" / "calibration" / gate / sid, "case.json", {
            "schema_version": 1, "case_id": sid, "gate": gate, "labels": [], "provenance": "synthetic",
            "state": "candidate", "split": "holdout", "seed": {"criterion_id": cid, "expected": exp, "reason": "seed"}})
    reg = registry([], seed_answers())
    code, doc, _ = cli(repo, reg, "author", "verify", str(pkg), "--judge-seeds", "--json")
    assert code == 0 and states(doc)["judge_seeds"] == "passed"
    assert {(g["seed"], g["expected"]) for g in doc["seeds"]} == {
        ("draft-good", "MET"), ("draft-bad", "UNMET"), ("out-good", "MET"), ("out-bad", "UNMET")}
    assert not (pkg / "evals" / "calibration" / "draft" / "scores.jsonl").exists()
    write(pkg / "evals" / "calibration" / "outcome" / "out-bad", "case.json", {
        "schema_version": 1, "case_id": "out-bad", "gate": "outcome", "labels": [],
        "seed": {"criterion_id": "another", "expected": "UNMET"}})
    code, doc, _ = cli(repo, registry([], seed_answers()), "author", "verify", str(pkg), "--judge-seeds", "--json")
    rung = next(r for r in doc["rungs"] if r["name"] == "judge_seeds")
    assert code != 0 and "seed-unlabelled" in {f["code"] for f in rung["findings"]}


def test_an_unclear_scale_flips_and_fails_rung_8(pkg: Path, repo: Path) -> None:
    """SCF-B8 / SCF-AC-7: the unmet seed graded PARTIAL once and UNMET once names rn-faithful; no stamp."""
    reg = registry([], seed_answers(("PARTIAL", "UNMET")))
    code, doc, _ = cli(repo, reg, "author", "verify", str(pkg), "--judge-seeds", "--json")
    assert code == 2
    s = states(doc)
    assert s["judge_seeds"] == "failed" and s["stamp"] == "skipped"
    rows = doc["rungs"][7]["findings"]
    assert [r["code"] for r in rows] == ["seed-unstable"] and "rn-faithful" in rows[0]["message"]
    assert "guidance ladder" in rows[0]["remedy"]


def test_a_rerun_regrades_only_the_seeds_that_failed(pkg: Path, repo: Path) -> None:
    """SCF §2.5: a stray grading fails rung 8; the rerun starts sessions for that seed only, because the other
    seeds' passes still hold (same gate, judge binding, files and expectation). An edit to a seed regrades it."""
    code, doc, _ = cli(repo, registry([], seed_answers(("PARTIAL", "UNMET"))), "author", "verify", str(pkg),
                       "--judge-seeds", "--json")
    assert code == 2 and states(doc)["judge_seeds"] == "failed"
    passed = json.loads((pkg / "authoring.json").read_text())["seeds_passed"]
    assert sorted(passed["draft"]) == ["draft-good"] and sorted(passed["outcome"]) == ["out-bad", "out-good"]
    reg = registry([], [draft_judge("UNMET"), draft_judge("UNMET")])
    code, doc, _ = cli(repo, reg, "author", "verify", str(pkg), "--judge-seeds", "--json")
    assert code == 0, json.dumps(doc["rungs"][7], indent=1)
    assert len(reg.get("claude").calls) == 2  # type: ignore[attr-defined]
    assert sorted(doc["carried"]) == ["draft/draft-good", "outcome/out-bad", "outcome/out-good"]
    assert "3 seeds kept an earlier pass" in doc["rungs"][7]["note"]
    write(pkg / "evals" / "calibration" / "outcome" / "out-good", "fixture/workspace/notes.md", GOOD_NOTES + "\n")
    reg = registry([], [verdict("MET"), verdict("MET")])
    code, doc, _ = cli(repo, reg, "author", "verify", str(pkg), "--judge-seeds", "--json")
    assert code == 0 and len(reg.get("claude").calls) == 2  # type: ignore[attr-defined]
    assert "outcome/out-good" not in doc["carried"]


def test_a_seed_graded_wrong_both_times_fails(pkg: Path, repo: Path) -> None:
    reg = registry([], seed_answers(("MET", "MET")))
    code, doc, _ = cli(repo, reg, "author", "verify", str(pkg), "--judge-seeds", "--json")
    assert code == 2
    assert [r["code"] for r in doc["rungs"][7]["findings"]] == ["seed-misgraded"]


def test_missing_seeds_and_the_cap(tmp_path: Path, repo: Path) -> None:
    """A judged criterion with fewer than two seeds fails rung 8 with no session; a spent cap stops grading."""
    scaffold(read_session(session(tmp_path)), tmp_path / "out" / "release-notes")
    p = tmp_path / "out" / "release-notes"
    reg = registry([], [])
    code, doc, _ = cli(repo, reg, "author", "verify", str(p), "--judge-seeds", "--json")
    assert code == 2 and {r["code"] for r in doc["rungs"][7]["findings"]} == {"criterion-no-seed"}
    assert reg.get("claude").calls == []  # type: ignore[attr-defined]


def test_the_cap_stops_seed_grading(pkg: Path, repo: Path) -> None:
    reg = registry([], seed_answers())
    code, doc, _ = cli(repo, reg, "author", "verify", str(pkg), "--judge-seeds", "--cap", "0.02", "--json")
    assert code == 2 and "seeds-cap-reached" in [r["code"] for r in doc["rungs"][7]["findings"]]
    assert len(reg.get("claude").calls) == 2  # type: ignore[attr-defined]  # $0.01 a session


def test_trial_needs_a_known_case(pkg: Path, repo: Path) -> None:
    code, doc, _ = cli(repo, registry([], []), "author", "verify", str(pkg), "--trial", "--json")
    assert code == 2 and doc["refused"] == "trial-needs-case"
    code, doc, _ = cli(repo, registry([], seed_answers()), "author", "verify", str(pkg), "--trial", "--case", "nope",
                       "--json")
    assert code == 2 and doc["rungs"][8]["findings"][0]["code"] == "trial-case-unknown"


def test_trial_report_and_grades(pkg: Path, repo: Path) -> None:
    """Rung 9 runs the case to the outcome gate in a worktree; the person's grades become labels with
    origin authoring_trial and calibration candidates; a disagreement is listed first (SCF-B6, AC-6)."""
    reg = registry([step], seed_answers() + [draft_judge("MET"), verdict("MET", sid="j-outcome")])
    code, doc, err = cli(repo, reg, "author", "verify", str(pkg), "--trial", "--case", "case-1", "--json")
    assert code == 0, err + json.dumps(doc["rungs"], indent=1)
    s = states(doc)
    assert s["judge_seeds"] == s["trial"] == s["stamp"] == "passed"
    trial = doc["trial"]
    assert trial["state"] == "ended" and trial["verdict"] == "met" and trial["task"].startswith("trial-case-1-")
    rec = json.loads((pkg / "authoring.json").read_text())
    assert rec["trial"]["thread"] == trial["thread"]
    mode_before = json.loads((pkg / "tempergraph.json").read_text()).get("improvement_mode")

    code, rep, _ = cli(repo, reg, "author", "trial", str(pkg), "--json")
    assert code == 0 and rep["verdict"] == "met"
    assert {(r["unit"], r["criterion"], r["status"]) for r in rep["criteria"]} == {
        ("outcome", "rn-complete", "MET"), ("draft", "rn-sections", "MET"), ("draft", "rn-faithful", "MET")}
    assert len(rep["ungraded"]) == 3

    code, g, _ = cli(repo, reg, "author", "grade", str(pkg), "--unit", "draft", "--criterion", "rn-faithful",
                     "--status", "UNMET", "--reason", "Entry two misstates its change.", "--json")
    assert code == 0, g
    assert g["by_person"] is True and g["label"]["value"] == "disagree" and g["label"]["origin"] == "authoring_trial"
    assert g["label"]["source"] == "person" and g["case"] == f"draft/trial-{trial['task']}"
    ledger = [json.loads(ln) for ln in (repo / ".tempergraph" / "ledger.jsonl").read_text().splitlines()]
    labels = [r for r in ledger if r.get("kind") == "label"]
    assert len(labels) == 1 and labels[0]["origin"] == "authoring_trial" and labels[0]["criterion_id"] == "rn-faithful"
    case = json.loads((pkg / "evals" / "calibration" / "draft" / f"trial-{trial['task']}" / "case.json").read_text())
    assert case["state"] == "candidate" and case["provenance"] == "harvested"
    assert case["labels"][0]["expected"] == "UNMET" and case["labels"][0]["origin"] == "authoring_trial"
    assert (pkg / "evals" / "calibration" / "draft" / f"trial-{trial['task']}" / "fixture" / "workspace"
            / "notes.md").read_text() == GOOD_NOTES

    code, g2, _ = cli(repo, reg, "author", "grade", str(pkg), "--criterion", "rn-complete", "--status", "MET",
                      "--reason", "Every change is listed.", "--json")
    assert code == 0 and g2["label"]["value"] == "agree"
    code, rep, _ = cli(repo, reg, "author", "trial", str(pkg), "--json")
    first = rep["criteria"][0]
    assert first["criterion"] == "rn-faithful" and first["disagrees"] and first["text"]
    assert rep["ungraded"] == ["draft/rn-sections"]
    code, bad, err = cli(repo, reg, "author", "grade", str(pkg), "--criterion", "nope", "--status", "MET",
                         "--reason", "x")
    assert code == 2 and "not a criterion" in err
    assert json.loads((pkg / "tempergraph.json").read_text()).get("improvement_mode") == mode_before


def test_trial_verbs_need_a_trial(pkg: Path, repo: Path) -> None:
    code, _, err = cli(repo, registry([], []), "author", "trial", str(pkg))
    assert code == 2 and "has no trial" in err


def test_seeds_move_to_tune_only_after_an_edit(pkg: Path, repo: Path) -> None:
    """JCL §2.1.1: a seed a failing rung 8 showed stays `holdout` until the gate's criteria or brief change;
    the next rung 8 then moves it to `tune` for good."""
    case = pkg / "evals" / "calibration" / "draft" / "draft-bad" / "case.json"
    cli(repo, registry([], seed_answers(("PARTIAL", "UNMET"))), "author", "verify", str(pkg), "--judge-seeds")
    rec = json.loads((pkg / "authoring.json").read_text())
    assert list(rec["seeds_shown"]["draft"]) == ["draft-bad"]
    assert json.loads(case.read_text()).get("split", "holdout") == "holdout"
    code, doc, _ = cli(repo, registry([], seed_answers()), "author", "verify", str(pkg), "--judge-seeds", "--json")
    assert doc["tuned"] == [] and json.loads(case.read_text()).get("split", "holdout") == "holdout"  # no edit
    judge = pkg / "judges" / "draft.md"
    judge.write_text(judge.read_text() + "\nAn entry that names the wrong change is UNMET.\n")
    code, doc, _ = cli(repo, registry([], seed_answers()), "author", "verify", str(pkg), "--judge-seeds", "--json")
    assert doc["tuned"] == ["draft/draft-bad"]
    assert json.loads(case.read_text())["split"] == "tune"
