"""Eval suites: check, step and workflow suites, the grader order, figures, the cap, a person's grade and the
report (EVS-AC1, AC-3 to AC-6, EVS-B1 to B4, B6)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.catalog import Catalog
from tempergraph.contracts import CheckFinding, CheckResult, SessionRequest, SessionResult
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import suites
from tempergraph.package import rules
from tempergraph.store.layout import state_root_path

from .fixtures.workflows import crit as make_crit
from .fixtures.workflows import two_step
from .test_cli import cli
from .test_run import judge, verdict_block

CANARY = "CANARY-51c0de"
MET, UNMET = verdict_block("MET", "MET"), verdict_block("MET", "UNMET")


def lf_only(ctx: Any) -> CheckResult:
    """Passes a notes file with a heading; fails on CRLF line endings (a check that is not line-ending safe)."""
    data = (ctx.workdir / ctx.artifacts["draft"]["notes"]).read_bytes()
    bad = b"\r\n" in data or not data.startswith(b"# ")
    return CheckResult(result="FAIL" if bad else "PASS", evidence="notes", findings=[
        CheckFinding(status="fail" if bad else "pass", criterion="c-file", message="heading")])


def robust(ctx: Any) -> CheckResult:
    data = (ctx.workdir / ctx.artifacts["draft"]["notes"]).read_bytes()
    bad = not data.startswith(b"# ")
    return CheckResult(result="FAIL" if bad else "PASS", evidence="notes", findings=[
        CheckFinding(status="fail" if bad else "pass", criterion="c-file", message="heading")])


def package(root: Path, check: Any = robust, **spec_fields: Any) -> Any:
    from tempergraph.api import callable_ref

    spec = two_step()
    u = spec.units["draft"]
    crit = dataclasses.replace(u.gate.criteria[0], verified_by="check")
    units = {**spec.units, "draft": dataclasses.replace(u, gate=dataclasses.replace(
        u.gate, check=callable_ref(check), criteria=(crit, make_crit("c-judged"))))}
    return dataclasses.replace(spec, units=units, package_root=root, **spec_fields)


def fixtures(root: Path, fail: bool = True) -> None:
    base = root / "evals" / "checks" / "draft"
    (base / "must-pass").mkdir(parents=True)
    (base / "must-pass" / "notes.md").write_text("# Notes\n- one\n")
    if fail:
        (base / "must-fail").mkdir()
        (base / "must-fail" / "notes.md").write_text("no heading\n")


def step_case(root: Path, case_id: str = "basic", unit: str = "draft", **doc: Any) -> None:
    folder = root / "evals" / "steps" / unit / case_id
    (folder / "workspace").mkdir(parents=True)
    (folder / "workspace" / "README.md").write_text("base\n")
    (folder / "case.json").write_text(json.dumps({"case_id": case_id, "inputs": {"request": f"notes {CANARY}"},
                                                  **doc}))


def drafts(req: SessionRequest) -> SessionResult:
    (req.workdir / "notes.md").write_text(f"# Notes\n- {CANARY}\n")
    return answer(f"Wrote notes.md {CANARY}\nARTIFACT notes: notes.md", session_id="s")


def bad_draft(req: SessionRequest) -> SessionResult:
    (req.workdir / "notes.md").write_text("no heading\n")
    return answer("Wrote notes.md\nARTIFACT notes: notes.md", session_id="s")


def reg(steps: list[Any], judges: list[Any]) -> tuple[Registry, Any]:
    ex = standin("claude", steps=steps, judges=judges)
    r = Registry()
    r.register(ex)
    return r, ex


def state(name: str) -> Any:
    return lambda unit: name


def test_figures_reproduce_the_table() -> None:  # EVS-AC1, EVS-B3
    passed = {"a": 3, "b": 2, "c": 3, "d": 0, "e": 3, "f": 1}
    rows = [{"case": c, "trial": t, "status": "passed" if t <= n else "failed", "attempts": 1, "first_attempt": t <= n}
            for c, n in passed.items() for t in (1, 2, 3)]
    fig = suites.figures(rows)
    assert (fig["pass_at_1"], fig["pass_hat_k"], fig["trials"], fig["cases"]) == (0.6667, 0.5, 18, 6)
    assert fig["first_attempt_pass"] == 0.6667 and fig["mean_attempts"] == 1.0


def test_a_needs_person_trial_counts_in_no_rate(tmp_path: Path) -> None:  # EVS-AC4
    rows = [{"case": "a", "status": "passed"}, {"case": "b", "status": "needs_person", "result_id": "r1"}]
    fig = suites.figures(rows)
    assert (fig["pass_at_1"], fig["pass_hat_k"], fig["needs_person"], fig["counted"]) == (1.0, 1.0, 1, 1)
    assert suites.suite_status("regression", rows) == "incomplete"
    assert suites.suite_status("regression", rows[:1]) == "passed"
    assert suites.suite_status("regression", [*rows, {"case": "c", "status": "failed"}]) == "failed"
    assert suites.suite_status("capability", [{"case": "c", "status": "failed"}]) == "tracked"


@pytest.mark.parametrize(("finished", "failures", "covered", "by_code", "judge_state", "want"), [
    (True, ["0:pattern"], False, False, "accepted", ("failed", "code")),
    (False, [], False, True, "accepted", ("failed", "code")),
    (True, [], True, False, "unscored", ("passed", "code")),
    (True, [], False, False, "accepted", ("passed", "judge")),
    (False, [], False, False, "accepted", ("failed", "judge")),
    (True, [], False, False, "below_bar", ("needs_person", "person")),
    (False, [], False, False, "provisional", ("needs_person", "person")),
])
def test_grader_order(finished: bool, failures: list[str], covered: bool, by_code: bool, judge_state: str,
                      want: tuple[str, str]) -> None:  # EVS-B16
    assert suites.grade(finished=finished, failures=failures, covered=covered, failed_by_code=by_code,
                        judge_state=judge_state) == want


def test_check_suite_runs_both_line_endings(tmp_path: Path) -> None:  # EVS-B2
    fixtures(tmp_path)
    doc = suites.run(package(tmp_path), "check", tmp_path / "state")
    assert [(r["case"], r["status"]) for r in doc["results"]] == [("must-fail/notes.md", "passed"),
                                                                   ("must-pass/notes.md", "passed")]
    doc = suites.run(package(tmp_path, check=lf_only), "check", tmp_path / "state")
    row = next(r for r in doc["results"] if r["case"] == "must-pass/notes.md")
    assert row["status"] == "failed" and row["line_endings_differ"] and row["results"] == ["PASS", "FAIL"]
    assert suites.green_model_free(package(tmp_path, check=lf_only)) and not suites.green_model_free(package(tmp_path))


def test_a_check_without_a_fail_case_warns(tmp_path: Path) -> None:  # EVS-B1
    fixtures(tmp_path, fail=False)
    found = rules.check_cases(package(tmp_path), tmp_path)
    assert [(f.code, f.unit, f.severity) for f in found] == [("check_without_fail_case", "draft", "warning")]
    doc = suites.run(package(tmp_path), "check", tmp_path / "state", write=False)
    assert doc["results"][0]["status"] == "invalid" and doc["results"][0]["reason"] == "check_without_fail_case"


def test_step_suite_grades_in_order_and_keeps_no_text(tmp_path: Path) -> None:  # EVS-B4, EVS-AC5
    root = tmp_path / "state"
    step_case(tmp_path, "judged", trials=2)
    step_case(tmp_path, "covered", trials=1, covered=True, expect=[{"path": "notes.md", "heading": "Notes"}])
    step_case(tmp_path, "asserted", trials=1, expect=[{"path": "notes.md", "pattern": "^## Missing"}])
    spec = package(tmp_path)
    r, ex = reg([drafts] * 4, [judge(MET)] * 4)
    doc = suites.run(spec, "step", root, registry=r, executor=ex, judge_state=state("below_bar"))
    got = {(x["case"], x["trial"]): (x["status"], x["graded_by"]) for x in doc["results"]}
    assert got == {("asserted", 1): ("failed", "code"), ("covered", 1): ("passed", "code"),
                   ("judged", 1): ("needs_person", "person"), ("judged", 2): ("needs_person", "person")}
    assert all(x["attempts"] == 1 and x["binding"] for x in doc["results"])
    assert CANARY not in suites.results_path(root).read_text()
    rep = suites.report(spec, root)
    (suite,) = rep["suites"]
    assert suite["status"] == "failed" and suite["figures"]["needs_person"] == 2
    assert len(rep["needs_person"]) == 2 and "evals grade" in rep["needs_person"][0]["command"]


def test_an_accepted_judge_decides_and_a_retry_counts(tmp_path: Path) -> None:  # EVS-B9, EVS-B2, EVS-B10, EVS-B17, EVS-B18
    root = tmp_path / "state"
    step_case(tmp_path, "one", trials=2)
    spec = package(tmp_path)
    r, ex = reg([drafts, drafts, drafts], [judge(UNMET), judge(MET), judge(MET)])
    doc = suites.run(spec, "step", root, registry=r, executor=ex, judge_state=state("accepted"))
    rows = doc["results"]
    assert [(x["status"], x["graded_by"], x["attempts"], x["first_attempt"]) for x in rows] == [
        ("passed", "judge", 2, False), ("passed", "judge", 1, True)]
    fig = suites.figures(rows)
    assert (fig["pass_at_1"], fig["pass_hat_k"], fig["first_attempt_pass"], fig["mean_attempts"]) == (1.0, 1.0, 0.5, 1.5)
    assert fig["cost_per_pass"] == pytest.approx(0.03)
    shown = suites.report(spec, root)["suites"][0]["figures"]["judge_graded"]  # EVS-B15: the judge's state rides along
    assert shown == {"raw": 1.0, "label": "uncorrected (unscored)", "state": "unscored"}


def test_a_failing_check_is_decided_by_code(tmp_path: Path) -> None:  # EVS-B16 order 1
    step_case(tmp_path, "one", trials=1)
    spec = package(tmp_path)
    r, ex = reg([bad_draft] * 3, [])
    doc = suites.run(spec, "step", tmp_path / "state", registry=r, executor=ex, judge_state=state("unscored"))
    assert [(x["status"], x["graded_by"], x["attempts"]) for x in doc["results"]] == [("failed", "code", 3)]


def test_the_cap_stops_cleanly(tmp_path: Path) -> None:  # EVS-B6
    step_case(tmp_path, "one", trials=5)
    r, ex = reg([drafts] * 5, [judge(MET)] * 5)
    doc = suites.run(package(tmp_path), "step", tmp_path / "state", registry=r, executor=ex, cap_usd=0.03,
                     judge_state=state("accepted"))
    assert doc["partial"] and len(doc["results"]) == 2 and all(x["partial"] for x in doc["results"])
    assert suites.suite_status("regression", doc["results"]) == "incomplete"


class LiveExecutor:
    name = "claude"


def test_no_live_suite_starts_under_the_test_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # EVS-AC3
    fixtures(tmp_path)
    for kind in suites.LIVE_KINDS:
        with pytest.raises(suites.SuiteRefused, match="live"):
            suites.run(package(tmp_path), kind, tmp_path / "state", executor=LiveExecutor())
    assert suites.run(package(tmp_path), "check", tmp_path / "state", executor=LiveExecutor())["results"]
    monkeypatch.setenv("TEMPERGRAPH_LIVE", "1")
    suites.refuse_live("step", LiveExecutor())  # a marked live check may start one
    assert not (tmp_path / "state" / "evals" / "results.jsonl").read_text().count('"kind": "step"')


def test_a_person_grades_what_no_grader_could(tmp_path: Path) -> None:  # EVS-AC4, EVS-AC6
    root = tmp_path / "state"
    step_case(tmp_path, "one", trials=1)
    spec = package(tmp_path)
    r, ex = reg([drafts], [judge(MET)])
    (row,) = suites.run(spec, "step", root, registry=r, executor=ex, judge_state=state("stale"))["results"]
    assert row["status"] == "needs_person" and suites.report(spec, root)["suites"][0]["status"] == "incomplete"
    calls = len(ex.calls)
    suites.person_grade(root, row["result_id"], True, "Read the notes: they cover the request.", "dana")
    rep = suites.report(spec, root)
    assert rep["suites"][0]["status"] == "passed" and rep["suites"][0]["cases"][0]["graded_by"] == "person"
    assert rep["needs_person"] == [] and len(ex.calls) == calls
    with pytest.raises(suites.SuiteRefused, match="only a `needs_person`"):
        suites.person_grade(root, row["result_id"], False, "again", "dana")
    with pytest.raises(suites.SuiteRefused, match="no eval result"):
        suites.person_grade(root, "nope", True, "x", "dana")


def test_a_changed_prompt_makes_results_stale(tmp_path: Path) -> None:  # EVS-B13, EVS-B14
    root = tmp_path / "state"
    step_case(tmp_path, "one", trials=1)
    spec = package(tmp_path)
    r, ex = reg([drafts], [judge(MET)])
    suites.run(spec, "step", root, registry=r, executor=ex, judge_state=state("accepted"))
    assert suites.report(spec, root)["suites"][0]["status"] == "passed"
    u = spec.units["draft"]
    changed = dataclasses.replace(spec, units={**spec.units, "draft": dataclasses.replace(
        u, step=dataclasses.replace(u.step, prompt="Write better notes for {request} into notes.md"))})
    assert suites.report(changed, root)["suites"][0]["status"] == "stale"


def test_graduation_and_never_passed(tmp_path: Path) -> None:  # EVS-B8, EVS-B17, EVS-B18
    root = tmp_path / "state"
    step_case(tmp_path, "soon", trials=1, role="capability")
    step_case(tmp_path, "broken", trials=2, role="capability", expect=[{"path": "missing.md"}])
    spec = package(tmp_path)
    for _ in range(3):
        r, ex = reg([drafts] * 3, [judge(MET)] * 3)
        doc = suites.run(spec, "step", root, registry=r, executor=ex, judge_state=state("accepted"))
        assert suites.suite_status("capability", doc["results"]) == "tracked"
    rep = suites.report(spec, root)
    assert rep["graduation"] == [{"kind": "step", "subject": "draft", "case": "soon"}]
    assert [(n["case"], n["trials"]) for n in rep["never_passed"]] == [("broken", 6)]


def test_invalid_step_cases_are_listed(tmp_path: Path) -> None:  # EVS-B13, EVS-B12, EVS-B14
    step_case(tmp_path, "one", unit="nope")
    step_case(tmp_path, "two", role="sometimes")
    cases, bad = suites.step_cases(package(tmp_path))
    assert cases == [] and sorted(b["case"] for b in bad) == ["one", "two"]


def workflow_cases(root: Path, **more: Any) -> None:
    (root / "evals").mkdir(parents=True, exist_ok=True)
    (root / "evals" / "cases.json").write_text(json.dumps({"cases": [
        {"case_id": "notes", "base": "HEAD", "request": f"Release notes {CANARY}", **more}]}))


def reviews(req: SessionRequest) -> SessionResult:
    return answer("Looks fine\nARTIFACT verdict: ok", session_id="s-review")


def test_workflow_suite_runs_a_case_as_a_dry_run(tmp_path: Path, repo: Path) -> None:  # EVS-B12
    pkg = tmp_path / "pkg"
    workflow_cases(pkg, end_state=[{"path": "notes.md", "heading": "Notes"}, {"changed_within": ["notes.md"]}])
    spec = package(pkg)
    r, ex = reg([drafts, reviews], [judge(MET), judge(MET)])
    root = state_root_path(repo)
    doc = suites.run(spec, "workflow", root, registry=r, repo=repo, executor=ex, judge_state=state("accepted"))
    (row,) = doc["results"]
    assert (row["status"], row["graded_by"], row["failures"]) == ("passed", "judge", [])
    assert CANARY not in suites.results_path(root).read_text()
    workflow_cases(pkg, end_state=[{"changed_within": ["docs/**"]}])
    r, ex = reg([drafts, reviews], [judge(MET), judge(MET)])
    (row,) = suites.run(spec, "workflow", root, registry=r, repo=repo, executor=ex,
                        judge_state=state("accepted"))["results"]
    assert (row["status"], row["graded_by"], row["failures"]) == ("failed", "code", ["0:changed_within"])
    workflow_cases(pkg, base="0000000000000000000000000000000000000001")
    (row,) = suites.run(spec, "workflow", root, registry=reg([], [])[0], repo=repo, executor=ex)["results"]
    assert (row["status"], row["reason"]) == ("invalid", "base_missing")


def test_a_pause_takes_a_recorded_answer_or_ends_paused(tmp_path: Path, repo: Path) -> None:  # EVS-B12 answers
    pkg = tmp_path / "pkg"
    workflow_cases(pkg)
    spec = package(pkg)
    u = spec.units["draft"]
    spec = dataclasses.replace(spec, units={**spec.units, "draft": dataclasses.replace(
        u, gate=dataclasses.replace(u.gate, approval=True))})
    root = state_root_path(repo)
    r, ex = reg([drafts], [judge(MET)])
    (row,) = suites.run(spec, "workflow", root, registry=r, repo=repo, executor=ex,
                        judge_state=state("accepted"))["results"]
    assert row["status"] == "paused" and suites.suite_status("regression", [row]) == "incomplete"
    workflow_cases(pkg, answers=[{"decision": "proceed"}])
    r, ex = reg([drafts, reviews], [judge(MET), judge(MET)])
    (row,) = suites.run(spec, "workflow", root, registry=r, repo=repo, executor=ex,
                        judge_state=state("accepted"))["results"]
    assert (row["status"], row["graded_by"]) == ("passed", "judge")


def test_evals_run_report_and_grade_in_the_cli(tmp_path: Path, repo: Path) -> None:  # EVS-B17, EVS-B18, EVS-AC6
    pkg = tmp_path / "pkg"
    fixtures(pkg)
    step_case(pkg, "one", trials=1)
    spec = package(pkg)
    cat = Catalog(specs={"demo": spec})
    code, doc, _ = cli(repo, None, "evals", "run", "demo", "--kind", "check", "--json", catalog=cat)
    assert code == 0 and [r["status"] for r in doc["results"]] == ["passed", "passed"]
    ex = standin("claude", steps=[drafts], judges=[judge(MET)])
    code, doc, _ = cli(repo, ex, "evals", "run", "demo", "--kind", "step", "--json", catalog=cat)
    assert code == 0 and doc["results"][0]["status"] == "needs_person"  # the judge is unscored
    rid = doc["results"][0]["result_id"]
    idle = standin("claude")  # no scripted reply: a model call would fail
    code, rep, _ = cli(repo, idle, "evals", "report", "demo", "--json", catalog=cat)
    assert code == 0 and {s["kind"]: s["status"] for s in rep["suites"]} == {"check": "passed", "step": "incomplete"}
    code, text, _ = cli(repo, idle, "evals", "report", "demo", catalog=cat)
    assert code == 0 and "needs a person" in text
    assert cli(repo, idle, "evals", "grade", rid, "--pass", "--reason", "Read it.", catalog=cat)[0] == 0
    code, rep, _ = cli(repo, idle, "evals", "report", "demo", "--json", catalog=cat)
    assert {s["kind"]: s["status"] for s in rep["suites"]}["step"] == "passed" and idle.calls == []
    assert cli(repo, idle, "evals", "grade", rid, "--fail", "--reason", "x", catalog=cat)[0] != 0
    lf = Catalog(specs={"demo": package(pkg, check=lf_only)})
    assert cli(repo, None, "evals", "run", "demo", "--kind", "check", catalog=lf)[0] == 1
