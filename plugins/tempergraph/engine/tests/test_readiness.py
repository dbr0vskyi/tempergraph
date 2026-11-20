"""The structural judge readiness report and the stable-mode rule (LIF §2, LIF-B6)."""

from __future__ import annotations

import json
from pathlib import Path

from tempergraph.model.validate import validate
from tempergraph.package.loader import load
from tempergraph.package.readiness import readiness

from .fixtures.packages import minimal_package, write


def grades(pkg: Path) -> dict[str, str]:
    return {g.gate: g.grade for g in readiness(load(pkg))}


def test_minimal_package_needs_cases_until_a_judge_is_accepted(tmp_path: Path) -> None:
    pkg = minimal_package(tmp_path)
    assert grades(pkg) == {"draft": "needs cases", "outcome": "needs cases"}
    spec = load(pkg)
    assert {g.gate: g.grade for g in readiness(spec, accepted=lambda g: True)} == {"draft": "ready",
                                                                                   "outcome": "ready"}
    write(pkg, "evals/calibration/draft/case-1.json", {"expected": "met"})
    assert next(g for g in readiness(load(pkg)) if g.gate == "draft").calibration_cases == 1


def test_structural_findings_need_work(tmp_path: Path) -> None:
    pkg = minimal_package(tmp_path)
    outcome = json.loads((pkg / "outcome.json").read_text())
    faithful = outcome["intermediate"]["draft"]["criteria"][1]
    faithful["check_method"] = ""
    del faithful["verifier"]["scale"]["partial"]
    faithful["text"] = "Every entry is properly written"
    write(pkg, "outcome.json", outcome)
    [draft] = [g for g in readiness(load(pkg)) if g.gate == "draft"]
    assert draft.grade == "needs work"
    text = " ".join(draft.findings)
    assert "no check method" in text and "partial" in text and "properly" in text


def test_stable_mode_refuses_gates_that_are_not_ready(tmp_path: Path) -> None:
    pkg = minimal_package(tmp_path)
    decl = (pkg / "workflow/release_notes/__init__.py").read_text().replace(
        'issue_repository="acme/release-notes",', 'issue_repository="acme/release-notes", improvement_mode="stable",')
    write(pkg, "workflow/release_notes/__init__.py", decl)
    found = [f for f in validate(load(pkg), {}) if f.code == "gate-not-ready"]
    assert {f.unit for f in found} == {"draft", "outcome"} and all(f.severity == "error" for f in found)
