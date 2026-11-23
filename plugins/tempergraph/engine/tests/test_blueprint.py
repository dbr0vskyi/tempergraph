"""Blueprint check, draw and compare, and the literal check (SCF-B9, SCF-B11, SCF-B13; plan T8.6)."""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.author import blueprint as bpm
from tempergraph.author.compare import compare
from tempergraph.author.draw import draw
from tempergraph.author.literals import scan
from tempergraph.cli.main import main
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import standin
from tempergraph.package.loader import load_package
from tempergraph.run.outcome import parse_outcome

from .conftest import hash_tree
from .fixtures.packages import OUTCOME, blueprint, minimal_package, write

CAPS = {"claude": DECLARED["claude"]}


def reg() -> Registry:
    r = Registry()
    r.register(standin("claude"))
    return r


def cli(cwd: Path, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = main(list(argv), registry=reg(), cwd=cwd, out=out, err=io.StringIO())
    return code, out.getvalue()


def two_units() -> dict[str, Any]:
    return {"schema_version": 1, "name": "plan-then-code", "units": [
        {"name": "plan", "kind": "step", "summary": "Write the plan", "produces": ["plan"],
         "gate": {"check": False, "judge": True, "signoff": False}, "sizing": dict(SIZING), "judge_sizing": dict(SIZING)},
        {"name": "code", "kind": "step", "summary": "Write the code", "produces": ["patch"], "reads": ["plan"],
         "gate": {"check": False, "judge": True, "signoff": False}, "back_targets": ["plan"],
         "sizing": dict(SIZING), "judge_sizing": dict(SIZING)}]}


SIZING = {"model": "medium", "effort": "high", "why": "Design work that reads several files"}


def codes(found: list[Any]) -> list[str]:
    return [f.code for f in found]


# -- blueprint check (SCF-B9, SCF-B11, SCF-B10, SCF-B14, SCF-B20, SCF-B21, SCF-AC1) -------------------------------------------------------------------


def test_minimal_blueprint_checks_clean() -> None:
    bp = bpm.parse(blueprint())
    assert isinstance(bp, bpm.Blueprint)
    outcome = parse_outcome(OUTCOME)
    assert not isinstance(outcome, list)
    assert bpm.check(bp, CAPS, outcome, OUTCOME) == []


def test_misspelt_field_is_unknown_key() -> None:
    """SCF-B1."""
    doc = two_units()
    doc["units"][0]["prodcues"] = doc["units"][0].pop("produces")
    got = bpm.parse(doc)
    assert isinstance(got, list) and codes(got) == ["unknown_key"] and got[0].unit == "plan"
    assert "$.units[0].prodcues" in got[0].message


def test_reference_nobody_produces() -> None:
    """SCF-B2: a read no earlier unit produces fails with WFM's reference finding."""
    doc = two_units()
    doc["units"][0]["reads"] = ["patch"]
    bp = bpm.parse(doc)
    assert isinstance(bp, bpm.Blueprint)
    found = bpm.check(bp, CAPS)
    assert "template-unknown-field" in codes(found) and all(f.severity == "error" for f in found)


@pytest.mark.parametrize(("mutate", "code"), [
    (lambda d: d["units"].extend(copy.deepcopy(d["units"][0]) | {"name": f"u{i}"} for i in range(20)),
     "blueprint-invalid"),
    (lambda d: d.update(name="release-notes-tgraph"), "blueprint-invalid"),  # ADR-0120: suffix is the plugin's
    (lambda d: d["units"][0].update(summary="x" * 61), "summary-too-long"),
    (lambda d: d["units"][0].pop("sizing"), "sizing-missing"),  # SCF-B10: stated for every step
    (lambda d: d["units"][0].pop("judge_sizing"), "sizing-missing"),  # and for every judge
    (lambda d: d["units"][0]["sizing"].update(model="inherit"), "sizing-invalid"),
    (lambda d: d["units"][0]["sizing"].update(model="huge"), "sizing-invalid"),
    (lambda d: d["units"][0]["sizing"].update(effort="extreme"), "sizing-invalid"),
    (lambda d: d["units"][0]["sizing"].update(why="because"), "sizing-invalid"),
    (lambda d: d["units"][0]["sizing"].pop("why"), "sizing-invalid"),
    (lambda d: d["units"][0]["gate"].update(judge=False), "sizing-invalid"),  # a judge's sizing with no judge
    (lambda d: d.update(colour="blue"), "unknown_key"),
    (lambda d: d["units"][0].update(kind="council"), "not_in_release"),
    (lambda d: d["units"][0].update(kind="subworkflow"), "not_in_release"),  # SCF-B9: the blueprint states no sub-workflow (AC 1)
    (lambda d: d["units"][0].update(kind="contest"), "not_in_release"),  # SCF-B9: it cannot state slots, so it refuses a contest (CTS-AC1)
    (lambda d: d.update(flow={"plan": {"parallel": ["a", "b"]}}), "blueprint-invalid"),  # a shape on a step
    (lambda d: d["units"][1].update(kind="map"), "blueprint-invalid"),  # a map states what it runs over
    (lambda d: d["units"][0].update(kind="ask", produces=["plan"]), "blueprint-invalid"),
    (lambda d: d["units"][0]["gate"].update(review=True), "unknown_key"),
])
def test_error_rows(mutate: Any, code: str) -> None:
    doc = two_units()
    mutate(doc)
    got = bpm.parse(doc)
    assert isinstance(got, list) and code in codes(got)


def test_outcome_cross_check() -> None:
    bp = bpm.parse(blueprint())
    assert isinstance(bp, bpm.Blueprint)
    changed = copy.deepcopy(OUTCOME)
    changed["statement"] = "Something else entirely, said differently."
    outcome = parse_outcome(changed)
    assert not isinstance(outcome, list)
    assert "blueprint_outcome_mismatch" in codes(bpm.check(bp, CAPS, outcome, changed))
    doc = blueprint()
    doc["units"][0]["gate"]["check"] = False
    bp = bpm.parse(doc)
    assert isinstance(bp, bpm.Blueprint)
    outcome = parse_outcome(OUTCOME)
    assert "blueprint-criterion-without-check" in codes(bpm.check(bp, CAPS, outcome, OUTCOME))  # type: ignore[arg-type]
    doc["units"][0]["gate"].update(check=True, signoff=True)
    bp = bpm.parse(doc)
    assert "blueprint-signoff-mismatch" in codes(bpm.check(bp, CAPS, outcome, OUTCOME))  # type: ignore[arg-type]


def test_cli_check_and_draw(tmp_path: Path) -> None:
    write(tmp_path, "blueprint.json", blueprint())
    write(tmp_path, "outcome.json", OUTCOME)
    before = hash_tree(tmp_path)
    code, out = cli(tmp_path, "blueprint", "check", "blueprint.json")
    assert code == 0 and json.loads(out)["ok"] is True
    code, out = cli(tmp_path, "blueprint", "draw", "blueprint.json")
    assert code == 0 and "```mermaid" in out and "## Verification" in out and "## Unverified" in out
    assert "| outcome | rn-complete |" in out and "uncalibrated" in out
    assert "- draft.on_fail: retry" in out  # defaults shown
    code, out = cli(tmp_path, "blueprint", "draw", "blueprint.json", "--format", "svg")
    assert code == 0 and out.startswith("<svg") and "draft" in out
    code, out = cli(tmp_path, "blueprint", "draw", "blueprint.json", "--format", "mermaid")
    assert code == 0 and out.startswith("flowchart TD") and "outcome" in out
    assert hash_tree(tmp_path) == before
    write(tmp_path, "bad.json", {**blueprint(), "colour": "blue"})
    code, out = cli(tmp_path, "blueprint", "draw", "bad.json")
    assert code == 2 and json.loads(out)["findings"][0]["code"] == "unknown_key"  # nothing drawn


def test_draw_lists_unverified_or_none() -> None:
    bp = bpm.parse(two_units())
    assert isinstance(bp, bpm.Blueprint)
    assert "## Unverified\n\nnone" not in draw(bp, None, "md")  # no outcome: no tables
    o = copy.deepcopy(OUTCOME)
    o["final"].append({"id": "rn-tone", "severity": "warning", "verified_by": "none", "text": "The tone fits",
                       "verifier": {"reason": "taste", "risk": "low"}})
    outcome = parse_outcome(o)
    bp = bpm.parse(blueprint(outcome=o))
    assert isinstance(bp, bpm.Blueprint) and not isinstance(outcome, list)
    text = draw(bp, outcome, "md")
    assert "- rn-tone on outcome: taste (risk: low)" in text


# -- compare (SCF-B18, SCF-B19, SCF-B20, SCF-B21, SCF-B22 rung 2, SCF-AC3) -------------------------------------------------------------------------


def test_compare_clean_then_drift(tmp_path: Path) -> None:
    root = minimal_package(tmp_path)
    spec = load_package(root).spec
    bp = bpm.parse(json.loads((root / "blueprint.json").read_text()))
    assert isinstance(bp, bpm.Blueprint)
    assert compare(bp, spec, OUTCOME) == []
    decl = root / "workflow/release_notes/__init__.py"
    decl.write_text(decl.read_text().replace("references=[\"notes\"]))", "references=[\"notes\"]), approval=True)"))
    diffs = compare(bp, load_package(root).spec, OUTCOME)
    assert [d.field for d in diffs] == ["approval"]
    assert diffs[0].statement == "draft now pauses for approval after a pass; the blueprint does not"  # SCF-B4
    assert "change the blueprint with the person's yes" in diffs[0].to_json()["fixes"]
    code, out = cli(tmp_path, "blueprint", "compare", str(root))
    assert code == 2 and json.loads(out)["differences"][0]["field"] == "approval"


def test_compare_ignores_summaries_models_criteria_and_prompts(tmp_path: Path) -> None:
    root = minimal_package(tmp_path)
    decl = root / "workflow/release_notes/__init__.py"
    decl.write_text(decl.read_text().replace('tools=["read", "write"]', 'tools=["read", "write"], model="large", '
                                             'summary="Another summary"'))
    (root / "prompts" / "draft.md").write_text("A different prompt for {request}.\n")
    o = copy.deepcopy(OUTCOME)
    o["intermediate"]["draft"]["criteria"][1]["text"] = "Reworded criterion text"
    write(root, "outcome.json", o)
    bp = bpm.parse(json.loads((root / "blueprint.json").read_text()))
    assert isinstance(bp, bpm.Blueprint)
    diffs = compare(bp, load_package(root).spec, o)
    assert [d.field for d in diffs] == ["outcome_ref.digest"]  # the outcome changed; nothing else is compared


@pytest.mark.parametrize(("edit", "fld"), [
    ('produces={"notes": "file"}', 'produces={"notes": "file", "extra": "file"}'),
    ("gate=Gate(check=draft_check, ", "gate=Gate(check=None, "),
    ('references=["notes"]))', 'references=["notes"]), on_budget_spent="stop")'),
])
def test_compare_reports_each_field(tmp_path: Path, edit: str, fld: str) -> None:
    root = minimal_package(tmp_path)
    decl = root / "workflow/release_notes/__init__.py"
    decl.write_text(decl.read_text().replace(edit, fld))
    bp = bpm.parse(json.loads((root / "blueprint.json").read_text()))
    assert isinstance(bp, bpm.Blueprint)
    got = {d.field for d in compare(bp, load_package(root).spec, OUTCOME)}
    assert got & {"produces", "gate.check", "on_budget_spent"}


# -- literals (SCF-B13, SCF-B5) ---------------------------------------------------------------------------------


def test_literal_in_a_brief_then_recorded(tmp_path: Path) -> None:
    root = minimal_package(tmp_path)
    write(root, "judges/draft.md", "# Stance\n\nVerify the notes.\n\n# Brief\n\nCompare with RN-1423 first.\n")
    write(root, "evals/cases.json", {"schema_version": 1, "cases": [{"id": "c1", "request": "notes for RN-1423"}]})
    hits = scan(load_package(root).spec)
    hit = next(h for h in hits if h.kind == "ticket")
    assert (hit.file, hit.line, hit.text) == ("judges/draft.md", 7, "RN-1423")
    doc = json.loads((root / "authoring.json").read_text())
    doc["decisions"] = [{"id": "d1", "subject": "literal", "choice": "keep: the brief's worked example",
                         "literal_digest": hit.digest}]
    write(root, "authoring.json", doc)
    assert not [h for h in scan(load_package(root).spec) if h.kind == "ticket"]


def test_other_literal_kinds(tmp_path: Path) -> None:
    root = minimal_package(tmp_path)
    write(root, "prompts/draft.md", "Write notes for {request}. See https://wiki.example.com/page, ask "
          "owner@example.com, read /home/alice/notes.txt and include the changes merged into the release branch.\n")
    write(root, "evals/cases.json", {"schema_version": 1, "cases": [
        {"id": "c1", "request": "include the changes merged into the release branch since v1.2"}]})
    spec = load_package(root).spec
    kinds = {h.kind for h in scan(spec)}
    assert {"url", "email", "path", "case_text"} <= kinds
    assert "case_text" not in {h.kind for h in scan(spec, cases=False)}
    code, out = cli(tmp_path, "literals", str(root), "--cases")
    assert code == 6 and json.loads(out)["ok"] is False


def test_clean_package_has_no_literals(tmp_path: Path) -> None:
    root = minimal_package(tmp_path)
    assert scan(load_package(root).spec) == []
    assert cli(tmp_path, "literals", str(root), "--cases")[0] == 0


def shapes() -> dict[str, Any]:
    judged = {"check": False, "judge": True, "signoff": False}
    plain = {"check": False, "judge": False, "signoff": False}

    def step(name: str, produces: list[str], reads: list[str] = (), kind: str = "step") -> dict[str, Any]:  # type: ignore[assignment]
        return {"name": name, "kind": kind, "summary": name, "produces": produces, "reads": list(reads),
                "gate": judged, "sizing": dict(SIZING), "judge_sizing": dict(SIZING)}

    return {"schema_version": 1, "name": "shapes", "units": [
        step("look-a", ["a"]), step("look-b", ["b"]),
        {"name": "both", "kind": "parallel", "summary": "Both reads", "gate": plain},
        step("plan", ["phases"], ["a", "b"]),
        {"name": "go", "kind": "ask", "summary": "Go ahead?", "reads": ["phases"], "gate": plain},
        step("code", ["patch"], kind="map"),
        {"name": "merged", "kind": "wait", "summary": "Wait for the merge", "gate": plain}],
        "flow": {"both": {"parallel": ["look-a", "look-b"]}, "code": {"map": {"over": "plan.phases"}},
                 "merged": {"wait": {"event": "merged"}}}}


def test_release_two_shapes_check_clean() -> None:  # SCF-B9, SCF-B11: parallel, map, ask and wait
    bp = bpm.parse(shapes())
    assert isinstance(bp, bpm.Blueprint)
    assert bpm.check(bp, CAPS) == []  # `b` of the second branch is produced on every path into `plan`
    spec = bpm.to_spec(bp)
    assert spec.units["look-a"].step.tools == ("read",)  # type: ignore[union-attr]  # a branch reads only
    assert spec.units["code"].map.items_from == ("plan", "phases")  # type: ignore[union-attr]
    assert compare(bp, spec) == []
    moved = shapes()
    moved["flow"]["code"]["map"]["over"] = "plan.other"
    other = bpm.parse(moved)
    assert isinstance(other, bpm.Blueprint)
    assert [d.field for d in compare(other, spec)] == ["map.over"]
