"""The package's records show the regeneration unit (AC 10)."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from tempergraph.author import blueprint as bpm
from tempergraph.author.compare import compare
from tempergraph.package.loader import load_package

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
OUTCOME = json.loads((ROOT / "outcome.json").read_text(encoding="utf-8"))
CHECK = "tgwf_temperspec.regeneration:regeneration_check"


def test_the_outcome_record_holds_revision_25_and_the_criteria_of_the_unit() -> None:  # AC 10
    assert OUTCOME["revision"] == 25
    assert any(r["revision"] == 25 and r.get("note") for r in OUTCOME["revisions"])
    criteria = OUTCOME["intermediate"]["regeneration"]["criteria"]
    assert criteria
    for c in criteria:
        assert c["verified_by"] == "check" and c["verifier"]["check"] == CHECK, c


def test_the_readme_shows_the_unit_in_its_table_and_lanes() -> None:  # AC 10
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert re.search(r"^\| regeneration \|", text, re.M)
    lanes = [ln for ln in text.splitlines() if re.match(r"^\| (quick|standard|full) \|", ln)]
    assert len(lanes) == 3
    for ln in lanes:
        assert re.search(r"code → regeneration", ln) or re.search(r"code \(no review\) → regeneration", ln), ln


def test_the_blueprint_and_the_built_workflow_agree_on_the_unit() -> None:  # AC 10
    bp = bpm.read(ROOT / "blueprint.json")
    assert not isinstance(bp, list), bp
    assert compare(bp, SPEC, OUTCOME) == []
    assert "regeneration" in SPEC.order


def test_the_two_new_specs_stay_within_the_budget() -> None:  # AC 10
    for name in ("regeneration.spec.md", "regeneration-failures.spec.md"):
        path = ROOT / "docs" / "specs" / name
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 400, name
        assert path.stat().st_size <= 30720, name


def test_every_regeneration_test_names_a_criterion() -> None:  # AC 10
    ids = re.compile(r"(RGN|RGF|HUM|SCF)[_-]AC[_-]?\d+|\bAC[ _]\d+", re.I)
    missing: list[str] = []
    for path in sorted((ROOT / "tests").glob("test_regeneration*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        tree = ast.parse("\n".join(lines))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                body = node.body[0].lineno - 1 if node.body else node.lineno
                # name, decorators, a comment above, or any text of the function
                start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
                chunk = "\n".join(lines[max(0, start - 2):node.end_lineno])
                if not ids.search(chunk) and body >= 0:
                    missing.append(f"{path.name}::{node.name}")
    assert missing == []
