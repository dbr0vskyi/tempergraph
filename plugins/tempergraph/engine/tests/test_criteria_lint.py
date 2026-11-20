"""Criteria lint and the sufficiency check (AUT §2.4.1, §2.8; AUT-AC-7 first half, AUT-B9)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from tempergraph.author.criteria_lint import lint, sufficiency

from .fixtures.packages import OUTCOME

SCALE = {"met": "each entry names the user-visible effect", "partial": "no partial: any gap is UNMET",
         "unmet": "an entry quotes the commit subject", "evidence": "the entry", "seeds": ["s-met", "s-unmet"]}


def doc(text: str, **c: Any) -> dict[str, Any]:
    crit = {"id": "c1", "severity": "blocker", "verified_by": "judge", "text": text,
            "check_method": "Read the notes", "verifier": {"references": ["notes"], "scale": dict(SCALE)}}
    crit.update(c)
    return {"statement": "Release notes that list every merged change", "deliverables": [{"key": "notes"}],
            "final": [crit], "intermediate": {}}


def codes(d: dict[str, Any]) -> list[str]:
    return [f.code for f in lint(d)]


GOOD = "Every entry names the user-visible effect of its change"

CASES = [  # (code, must fire, must not fire)
    ("criterion-vague", doc("The notes are good and clear to read"), doc(GOOD)),
    ("criterion-compound", doc("Every entry links its change and the notes have a summary section"),
     doc("Every change is in the notes or listed as excluded with a reason")),
    ("criterion-unobservable", doc("Readers trust the release", verifier={"scale": dict(SCALE)}), doc(GOOD)),
    ("criterion-self-graded", doc("The step confirms that every entry was checked"), doc(GOOD)),
    ("criterion-unanchored", doc(GOOD, verifier={"references": ["notes"], "scale": {"met": "x"}}), doc(GOOD)),
    ("criterion-no-seed", doc(GOOD, verifier={"references": ["notes"], "scale": {**SCALE, "seeds": ["one"]}}),
     doc(GOOD)),
]


@pytest.mark.parametrize(("code", "fires", "clean"), CASES, ids=[c[0] for c in CASES])
def test_each_code_fires_and_does_not(code: str, fires: dict[str, Any], clean: dict[str, Any]) -> None:
    assert code in codes(fires)
    assert code not in codes(clean)


def test_overlap_within_a_unit_and_against_the_final() -> None:
    d = doc(GOOD)
    d["final"].append({**d["final"][0], "id": "c2", "text": "Each entry names the user-visible effect of its change"})
    assert "criterion-overlap" in codes(d)
    d = doc(GOOD)
    d["intermediate"] = {"draft": {"criteria": [{"id": "i1", "verified_by": "check", "verifier": {"check": "x"},
                                                 "serves": ["c1"], "text": "Every entry names the user-visible effect"}]}}
    assert "criterion-overlap" in codes(d)
    d["intermediate"]["draft"]["criteria"][0]["text"] = "The notes file has the template's four headings"
    assert "criterion-overlap" not in codes(d)


def test_the_package_fixture_is_clean() -> None:
    """The outcome the scaffold tests use passes, so SCF-B3 still holds with the lint in rung 1."""
    found = lint(OUTCOME)
    assert [f.code for f in found if f.severity() == "error"] == []
    assert sufficiency(OUTCOME, found) == []


def test_vague_statement_twice_and_insufficient() -> None:
    """AUT-B9: "good, complete release notes" reports criterion-vague twice; phase 2 cannot end."""
    d = copy.deepcopy(OUTCOME)
    d["statement"] = "good, complete release notes"
    vague = [f for f in lint(d) if f.code == "criterion-vague" and f.criterion is None]
    assert sorted(m.message.split("'")[1] for m in vague) == ["complete", "good"]
    gaps = [f.message for f in sufficiency(d)]
    assert "the statement is not observable" in gaps
    assert all(f.severity("validate") == "warning" for f in lint(d))


def test_sufficiency_needs_a_deliverable_and_a_blocker() -> None:
    d = doc(GOOD, severity="warning")
    d["deliverables"] = []
    gaps = {f.message for f in sufficiency(d)}
    assert {"no deliverable", "no blocker final criterion"} <= gaps
