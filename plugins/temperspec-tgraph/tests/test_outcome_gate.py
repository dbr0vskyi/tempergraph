"""What the final gate requires of the documents a run leaves, what its judge is shown, and what it reports about the
push (spec outcome-gate, OGT-*). The gate's check is built the way the engine builds it at run time: the package's
deliverables, the units that produce each, the units the run's path took, and the package's own outcome check."""

from __future__ import annotations

import dataclasses
import importlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, git_facts, run_check
from tempergraph.run.judging import JudgeInputs, render_judge
from tempergraph.run.outcome import deliverable_producers, derived_back, outcome_unit

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
OWNER = {key: unit for unit in SPEC.order for key in (SPEC.units[unit].step.produces if SPEC.units[unit].step else {})}
GATE = outcome_unit(SPEC).gate  # type: ignore[union-attr]
FIXTURE = ROOT / "evals" / "checks" / "outcome" / "must-pass" / "1-code-run"

ALL_STEPS = ["triage", "discovery", "plan", "expand", "code"]
# the hand-off and the plan are the files of the fixture run (with its spec and its test beside them)
DOCUMENTS = {"triage_note": "docs/tasks/T.triage.md", "handoff": "handoff.md", "plan": "plan.md",
             "code_report": "docs/tasks/T.report.md"}


def _settings(path_units: list[str]) -> dict[str, Any]:
    """The settings the engine gives the outcome gate's check (`nodes.py`), with the units the path took."""
    return {"deliverables": [dict(d) for d in SPEC.outcome.deliverables],  # type: ignore[union-attr]
            "deliverable_producers": deliverable_producers(SPEC),
            "outcome_check": SPEC.outcome.check.ref,  # type: ignore[union-attr]
            "path_units": path_units}


def _run(work: Path, path_units: list[str], present: list[str], values: dict[str, Any] | None = None,
         git: GitFacts | None = None) -> Any:
    """Run the outcome gate's check with the listed documents written and registered as artifacts."""
    artifacts: dict[str, dict[str, str]] = {}
    for source in sorted(p for p in FIXTURE.rglob("*") if p.is_file()):
        rel = source.relative_to(FIXTURE).as_posix()
        if rel in (DOCUMENTS["handoff"], DOCUMENTS["plan"]) and not any(DOCUMENTS[k] == rel for k in present):
            continue  # a document the run did not leave
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_bytes(source.read_bytes())
    for key in present:
        target = work / DOCUMENTS[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        artifacts.setdefault(OWNER[key], {})[key] = DOCUMENTS[key]
    ctx = CheckContext(unit="outcome", workdir=work, request={}, artifacts=artifacts, values=values or {},
                       git=git or GitFacts(), allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                       deadline_at=time.monotonic() + 60)
    ctx.settings = _settings(path_units)
    res, _ = run_check(GATE, ctx)
    return res


def _missing(res: Any) -> set[str]:
    """The keys of the deliverables the check found missing."""
    return {f.message.split()[1] for f in res.findings if f.message.startswith("deliverable ")
            and f.message.endswith(" is missing")}


# -- a document is required on the path that writes it (OGT-B1) ------------------------------------------------


def test_ogt_ac1_the_full_discovery_requires_its_handoff(tmp_path: Path) -> None:  # OGT-AC1
    res = _run(tmp_path, ["triage", "discovery"], ["triage_note"])
    assert res.result == "FAIL" and "handoff" in _missing(res), res.evidence


def test_ogt_ac2_the_short_visit_requires_its_handoff(tmp_path: Path) -> None:  # OGT-AC2
    res = _run(tmp_path, ["triage", "discovery_short"], ["triage_note"])
    assert res.result == "FAIL" and "handoff" in _missing(res), res.evidence


def test_ogt_ac3_the_plan_step_requires_its_plan(tmp_path: Path) -> None:  # OGT-AC3
    res = _run(tmp_path, ["triage", "plan"], ["triage_note"])
    assert res.result == "FAIL" and "plan" in _missing(res), res.evidence


def test_ogt_ac4_the_code_step_requires_its_code_report(tmp_path: Path) -> None:  # OGT-AC4
    res = _run(tmp_path, ["triage", "code"], ["triage_note"])
    assert res.result == "FAIL" and "code_report" in _missing(res), res.evidence


def test_ogt_ac5_a_run_of_every_step_with_every_document_is_missing_none(tmp_path: Path) -> None:  # OGT-AC5, AC 4
    res = _run(tmp_path, ALL_STEPS, ["triage_note", "handoff", "plan", "code_report"])
    assert _missing(res) == set(), res.evidence
    assert "deliverables present" in res.evidence and "4 of 4" in res.evidence, res.evidence


# -- a document of a step the run did not take is not required (OGT-B2) ----------------------------------------


def test_ogt_ac6_the_quick_lane_needs_no_handoff_and_no_plan(tmp_path: Path) -> None:  # OGT-AC6
    res = _run(tmp_path, ["triage", "code"], ["triage_note", "code_report"])
    assert not _missing(res) & {"handoff", "plan"}, res.evidence
    assert "2 not produced on this path" in res.evidence, res.evidence


def test_ogt_ac7_a_run_with_no_gap_needs_no_handoff(tmp_path: Path) -> None:  # OGT-AC7
    res = _run(tmp_path, ["triage", "plan", "code"], ["triage_note", "plan", "code_report"])
    assert "handoff" not in _missing(res), res.evidence
    assert "1 not produced on this path" in res.evidence, res.evidence


def test_ogt_ac8_a_docs_only_run_needs_no_plan_and_no_code_report(tmp_path: Path) -> None:  # OGT-AC8
    res = _run(tmp_path, ["triage", "discovery"], ["triage_note", "handoff"],
               values={"triage": {"route": "discovery-only"}})
    assert not _missing(res) & {"plan", "code_report"}, res.evidence
    assert "2 not produced on this path" in res.evidence, res.evidence


def test_the_deliverables_are_produced_by_the_units_of_their_path() -> None:  # AC 1, AC 4
    producers = {key: sorted(units) for key, units in deliverable_producers(SPEC).items()}
    keys = {str(d["key"]) for d in SPEC.outcome.deliverables}  # type: ignore[union-attr]
    assert set(producers) == keys == {"triage_note", "handoff", "plan", "code_report"}, producers
    assert producers == {"triage_note": ["triage"], "handoff": ["discovery", "discovery_short"],
                         "plan": ["plan"], "code_report": ["code"]}


# -- the outcome judge is shown the documents the run wrote (OGT-B3) -------------------------------------------


def _brief(state: dict[str, dict[str, str]]) -> str:
    """The prompt the engine renders for the outcome judge: each reference the run recorded, by its path
    (`nodes.py`, `_judge_session`)."""
    judge = GATE.judge
    assert judge is not None
    refs = {ref: str(vs[ref]) for ref in judge.references for vs in state.values() if ref in vs}
    return render_judge(JudgeInputs(gate=GATE, stance="", brief="", request="the task", references=refs))


def test_ogt_ac9_the_brief_of_a_run_that_wrote_every_document_names_all_four() -> None:  # OGT-AC9
    judge = GATE.judge
    assert judge is not None
    assert "triage_note" in judge.references
    for key in ("handoff", "plan", "code_report"):
        assert judge.references[key] == "optional", judge.references
    state = {OWNER[key]: {} for key in DOCUMENTS}
    for key, path in DOCUMENTS.items():
        state[OWNER[key]][key] = path
    prompt = _brief(state)
    for key, path in DOCUMENTS.items():
        assert f"### {key}" in prompt and path in prompt, key


def test_ogt_ac10_the_brief_of_a_docs_only_run_names_the_triage_note_and_the_handoff_only() -> None:  # OGT-AC10
    state = {OWNER["triage_note"]: {"triage_note": DOCUMENTS["triage_note"]},
             OWNER["handoff"]: {"handoff": DOCUMENTS["handoff"]}}
    prompt = _brief(state)
    assert DOCUMENTS["triage_note"] in prompt and DOCUMENTS["handoff"] in prompt
    for key in ("plan", "code_report"):
        assert DOCUMENTS[key] not in prompt and f"### {key}" not in prompt, key


# -- the revision, the assumptions and the overview (AC 1, AC 3) -----------------------------------------------


def test_the_outcome_record_lists_the_three_documents_and_the_overview_closes_its_questions() -> None:  # AC 1, AC 3
    outcome = json.loads((ROOT / "outcome.json").read_text())
    assert [d["key"] for d in outcome["deliverables"]] == ["triage_note", "handoff", "plan", "code_report"]
    assert all(d["kind"] == "file" and d["where"] for d in outcome["deliverables"])
    entry = next(r for r in outcome["revisions"] if "issue 53" in r.get("note", ""))
    assert entry["revision"] >= 11 and entry["origin"] == "authored"
    assert outcome["revision"] == outcome["revisions"][-1]["revision"] >= entry["revision"]
    assumptions = outcome["assumptions"]
    assert not any("not listed as deliverables" in a or "absent from every remote" in a for a in assumptions)
    assert any("reports whether the run's branch is pushed" in a and "never grades it" in a for a in assumptions)
    commit = next(c for c in outcome["intermediate"]["code"]["criteria"] if c["id"] == "ts-code-commit")
    assert commit["text"] == "Every file the code step changed is committed"
    code_spec = (ROOT / "docs" / "specs" / "code.spec.md").read_text(encoding="utf-8")
    assert any(commit["text"] in line for line in code_spec.splitlines())
    overview = (ROOT / "docs" / "specs" / "overview.spec.md").read_text(encoding="utf-8")
    assert "outcome-gate.spec.md" in overview
    for line in overview.splitlines():
        low = line.lower()
        assert not ("not deliverables" in low or "absent from every remote" in low), line


# -- the check reports whether the branch is pushed (OGT-B4) ---------------------------------------------------

PUSHED = "The run's branch is pushed."
NOT_PUSHED = "The run's branch is not pushed."
CHANGED_LINE = "Changed paths since the run's base"


def _push_run(tmp_path: Path, pushed: bool) -> str:
    git = GitFacts(pushed=pushed, changed_paths=(DOCUMENTS["handoff"],))
    res = _run(tmp_path, ALL_STEPS, ["triage_note", "handoff", "plan", "code_report"], git=git)
    assert _missing(res) == set(), res.evidence
    return str(res.evidence)


def _assert_placed(evidence: str, push: str) -> None:
    """The push line follows the check's first line and comes before the changed paths."""
    lines = evidence.splitlines()
    at = lines.index(push)
    assert "deliverables present" in lines[at - 2], evidence  # the engine's line, then the check's first line
    assert at < next(i for i, ln in enumerate(lines) if ln.startswith(CHANGED_LINE)), evidence


def test_ogt_ac11_the_evidence_says_the_branch_is_pushed(tmp_path: Path) -> None:  # OGT-AC11, AC 2
    evidence = _push_run(tmp_path, True)
    assert "is pushed" in evidence and "not pushed" not in evidence, evidence
    _assert_placed(evidence, PUSHED)


def test_ogt_ac12_the_evidence_says_the_branch_is_not_pushed(tmp_path: Path) -> None:  # OGT-AC12, AC 2
    evidence = _push_run(tmp_path, False)
    assert NOT_PUSHED in evidence and PUSHED not in evidence, evidence
    _assert_placed(evidence, NOT_PUSHED)


# -- a push never decides the check's result (OGT-B5) ----------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


def test_ogt_ac13_the_result_is_the_same_with_the_branch_pushed_or_not(tmp_path: Path) -> None:  # OGT-AC13, AC 2
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "README.txt").write_text("start\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "start")
    base = _git(tmp_path, "rev-parse", "HEAD").strip()
    artifacts: dict[str, dict[str, str]] = {}
    for f in sorted(p for p in FIXTURE.rglob("*") if p.is_file()):
        rel = f.relative_to(FIXTURE)
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(f.read_bytes())
        if len(rel.parts) == 1 and f.stem in OWNER:
            artifacts.setdefault(OWNER[f.stem], {})[f.stem] = rel.as_posix()
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "the change")
    facts = git_facts(tmp_path, base)
    assert facts is not None and facts.clean

    def grade(pushed: bool) -> Any:
        ctx = CheckContext(unit="outcome", workdir=tmp_path, request={}, artifacts=artifacts, values={},
                           git=dataclasses.replace(facts, pushed=pushed), allow=SPEC.allow_commands,
                           out_dir=tmp_path.parent / f"{tmp_path.name}.out", deadline_at=time.monotonic() + 60)
        ctx.settings = {"deliverables": [], "outcome_check": SPEC.outcome.check.ref}  # type: ignore[union-attr]
        res, _ = run_check(GATE, ctx)
        return res

    pushed, not_pushed = grade(True), grade(False)
    assert pushed.result == "PASS" and not_pushed.result == "PASS", (pushed.evidence, not_pushed.evidence)
    assert pushed.findings == not_pushed.findings
    assert PUSHED in pushed.evidence and NOT_PUSHED in not_pushed.evidence

    # the shared result builder adds the line to no other check: the code check's evidence has none
    code = CheckContext(unit="code", workdir=tmp_path, request={}, artifacts=artifacts, values={},
                        git=dataclasses.replace(facts, pushed=True), allow=SPEC.allow_commands,
                        out_dir=tmp_path.parent / f"{tmp_path.name}.code", deadline_at=time.monotonic() + 60)
    for evidence in (str(checks._result(code, []).evidence), str(checks.code_check(code).evidence)):
        assert "branch is pushed" not in evidence and "branch is not pushed" not in evidence, evidence


# -- where a failing judged criterion goes back to (OGT-B6 to OGT-B10) ------------------------------------------

FULL_DISCOVERY_PATH = ["triage", "owner_questions", "ask_route", "read_gap", "discovery", "plan", "code"]


def _serving(final: str) -> set[str]:
    """The units that hold a criterion serving the final criterion, read from the loaded outcome record."""
    return {unit for unit, io in SPEC.outcome.intermediate.items()  # type: ignore[union-attr]
            if any(final in c.serves for c in io.criteria)}


def _back(failing: list[str], path: list[str]) -> str | None:
    """The engine's own routing on the loaded package (`derived_back`), with the units in the order of the package."""
    assert set(path) <= set(SPEC.order), set(path) - set(SPEC.order)
    taken = [unit for unit in SPEC.order if unit in path]
    back = derived_back(SPEC, failing, taken)
    assert back is None or back in GATE.back_targets, (back, GATE.back_targets)
    return back


def test_ogt_ac14_a_failing_spec_sync_goes_back_to_the_full_discovery() -> None:  # OGT-AC14, AC 1
    assert _back(["ts-spec-sync"], FULL_DISCOVERY_PATH) == "discovery"
    assert not _serving("ts-spec-sync") & {"setup", "triage", "list_components", "read_component", "read_gap"}


def test_ogt_ac15_a_failing_spec_sync_goes_back_to_the_full_discovery_not_the_setup_step() -> None:  # OGT-AC15, AC 1
    setup_path = ["list_components", "read_component", "setup", "triage", "discovery", "plan", "code"]
    assert _back(["ts-spec-sync"], setup_path) == "discovery"
    short_then_full = ["triage", "discovery_short", "read_gap", "discovery", "plan"]
    assert _back(["ts-spec-sync"], short_then_full) == "discovery"


def test_ogt_ac16_a_failing_spec_sync_goes_back_to_the_plan_step_after_the_short_visit() -> None:  # OGT-AC16, AC 2
    assert _back(["ts-spec-sync"], ["triage", "discovery_short", "plan", "code"]) == "plan"


def test_ogt_ac17_a_failing_spec_sync_goes_back_to_the_plan_step_from_triage() -> None:  # OGT-AC17, AC 2
    assert _back(["ts-spec-sync"], ["triage", "plan", "code"]) == "plan"


def test_ogt_ac18_a_failing_spec_sync_on_the_quick_lane_goes_back_to_the_code_step() -> None:  # OGT-AC18, AC 2
    assert _back(["ts-spec-sync"], ["triage", "code"]) == "code"


def test_ogt_ac19_a_failing_accepted_criterion_goes_back_to_the_triage_step() -> None:  # OGT-AC19, AC 5
    assert _back(["ts-accepted"], FULL_DISCOVERY_PATH) == "triage"


def test_ogt_ac20_several_failing_criteria_go_back_to_the_earliest_step() -> None:  # OGT-AC20, AC 5
    assert _back(["ts-spec-sync", "ts-accepted"], FULL_DISCOVERY_PATH) == "triage"


# -- the outcome judge is told to state the place and the fix (OGT-B12) -----------------------------------------


def _folded(text: str) -> str:
    return " ".join(text.lower().split())


def test_ogt_ac22_the_brief_asks_for_the_place_and_the_fix_of_a_failing_criterion() -> None:  # OGT-AC22, AC 3
    judge = GATE.judge
    assert judge is not None
    prompt = render_judge(JudgeInputs(gate=GATE, stance=judge.stance, brief="", request="the task", references={}))
    sentence = ("For each criterion you grade PARTIAL or UNMET, state in its evidence the place of the defect and "
                "the fix, in one line.")
    assert _folded(sentence) in _folded(prompt), prompt
    for phrase in ("quote the line you relied on", "grade a criterion partial, not met"):
        assert phrase in _folded(prompt), phrase


# -- the decision record, the spec and the authoring record agree (AC 5) ----------------------------------------


def test_the_decision_record_agrees_with_the_serving_and_the_spec_states_each_judged_criterion() -> None:  # AC 5
    assert _serving("ts-spec-sync") == {"discovery", "plan", "code"}
    outcome = json.loads((ROOT / "outcome.json").read_text())
    serving = {c["id"] for unit in outcome["intermediate"].values() for c in unit["criteria"]
               if "ts-spec-sync" in c.get("serves", [])}
    assert serving == {"ts-dis-links", "ts-plan-spec", "ts-code-related"}, serving
    record = (ROOT / "docs" / "adr" / "ts-spec-sync.adr.md").read_text(encoding="utf-8")
    for name in sorted(serving) + ["OGT-B6", "OGT-B7", "OGT-B8", "OGT-B11", "OGT-B12"]:
        assert name in record, name
    spec = (ROOT / "docs" / "specs" / "outcome-gate.spec.md").read_text(encoding="utf-8")
    for criterion in outcome["final"]:
        if criterion.get("verified_by") == "judge":
            assert f"`{criterion['id']}`" in spec, criterion["id"]
    authoring = json.loads((ROOT / "authoring.json").read_text())
    d1 = next(d for d in authoring["decisions"] if d["id"] == "d1")
    assert d1["subject"] == "ts-spec-sync"
    assert "step that owns the specs" in d1["choice"], d1["choice"]
    assert "ts-plan-spec" in d1["consequence"], d1["consequence"]
