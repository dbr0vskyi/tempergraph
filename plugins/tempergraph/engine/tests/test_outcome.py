"""The outcome file and gate criteria (OUT §2.1, §4, OUT-B1, OUT-AC-1, OUT-AC-2)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.contracts import OutcomeSpec
from tempergraph.run.outcome import check_against, gate_criteria, parse_outcome, read_outcome

from .fixtures.workflows import two_step

SCALE = {"met": "all four headings", "partial": "no partial: any gap is UNMET", "unmet": "a heading missing",
         "evidence": "the heading lines"}
MINIMAL: dict[str, Any] = {
    "schema_version": 1, "revision": 1, "statement": "Release notes a reader can trust.",
    "deliverables": [{"key": "notes", "kind": "file", "where": "notes.md"}],
    "final": [{"id": "rn-complete", "text": "Every merged change is in the notes", "verified_by": "judge",
               "check_method": "Compare with the merge log", "verifier": {"references": ["notes"], "scale": SCALE}}],
    "intermediate": {
        "draft": {"statement": "A faithful draft", "criteria": [
            {"id": "rn-sections", "text": "The four headings in order", "verified_by": "check",
             "verifier": {"check": "x:y"}, "serves": ["rn-complete"]},
            {"id": "rn-faithful", "text": "Every entry matches its change", "verified_by": "judge",
             "check_method": "Read each change", "verifier": {"references": ["notes"], "scale": SCALE},
             "serves": ["rn-complete"]}]},
        "review": {"statement": "A review", "criteria": [
            {"id": "rv-ok", "text": "The review names a verdict", "verified_by": "judge"}]},
    },
}


def test_minimal_outcome_gives_each_gate_its_criteria() -> None:
    out = parse_outcome(MINIMAL)
    assert isinstance(out, OutcomeSpec)
    draft = gate_criteria(out, "draft")
    assert [(c.id, c.mechanical) for c in draft] == [("rn-sections", True), ("rn-faithful", False)]  # OUT-B1
    assert [c.id for c in out.final] == ["rn-complete"] and gate_criteria(out, "nowhere") == []
    assert check_against(out, two_step()) == []


def broken(path: str, value: Any) -> dict[str, Any]:
    data = copy.deepcopy(MINIMAL)
    target: Any = data
    *head, last = path.split(".")
    for k in head:
        target = target[int(k)] if k.isdigit() else target[k]
    if value is None:
        del target[last]
    else:
        target[int(last) if last.isdigit() else last] = value
    return data


@pytest.mark.parametrize("data, code", [
    (broken("final", []), "outcome-missing"),
    (broken("schema_version", 2), "outcome-missing"),
    (broken("intermediate.draft.criteria.0.serves", ["nope"]), "outcome-serves-unknown"),
    (broken("intermediate.review.criteria.0.id", "rn-faithful"), "criterion-id-duplicate"),
    (broken("intermediate.review.criteria.0.verified_by", "none"), "outcome-none-unexplained"),
])
def test_file_errors_have_their_own_code(data: dict[str, Any], code: str) -> None:
    out = parse_outcome(data)
    assert isinstance(out, list) and code in {f.code for f in out}  # OUT-AC-1


def test_unit_errors_have_their_own_code() -> None:
    extra = parse_outcome(broken("intermediate.ghost", {"criteria": []}))
    assert isinstance(extra, OutcomeSpec)
    assert "outcome-unit-unknown" in {f.code for f in check_against(extra, two_step())}
    missing = parse_outcome(broken("intermediate.review", None))
    assert isinstance(missing, OutcomeSpec)
    assert "outcome-unit-missing" in {f.code for f in check_against(missing, two_step())}
    checkless = parse_outcome(broken("intermediate.review.criteria.0.verified_by", "check"))
    assert isinstance(checkless, OutcomeSpec)
    assert "mechanical-without-check" in {f.code for f in check_against(checkless, two_step())}


def test_read_outcome_from_a_package(tmp_path: Path) -> None:
    assert [f.code for f in read_outcome(tmp_path)] == ["outcome-missing"]  # type: ignore[union-attr]
    (tmp_path / "outcome.json").write_text(json.dumps(MINIMAL))
    assert isinstance(read_outcome(tmp_path), OutcomeSpec)
