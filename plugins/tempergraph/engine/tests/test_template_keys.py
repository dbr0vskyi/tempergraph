"""Template keys and step values: the key lists of VAL-B8 and one fixture for each scenario of VAL-B5, VAL-B6, VAL-B8."""

from __future__ import annotations

import dataclasses
import re

import pytest

from tempergraph.api import Value
from tempergraph.contracts import InputDeclaration, Param, WorkflowSpec
from tempergraph.model.text import ENGINE_KEYS, ITEM_KEYS
from tempergraph.model.validate import errors, validate
from tempergraph.render.output import parse_output

from .conftest import DOCS
from .fixtures.workflows import two_step
from .test_validate import CLAUDE_ONLY, _step, codes


def _val_b8() -> str:
    text = (DOCS / "specs" / "step-values-and-template-keys.spec.md").read_text(encoding="utf-8")
    return text.split("### VAL-B8 ", 1)[1].split("\n- ", 1)[0]


def _names(row: str, opening: str) -> set[str]:
    inside = row.split(opening, 1)[1].split(")", 1)[0]
    return set(re.findall(r"`([a-z_]+)`", inside))


def test_the_key_lists_of_val_b8_equal_the_engine_constants() -> None:
    """VAL-AC4 (VAL-B8, VAL-B3, VAL-B4), AC 1, AC 2: the lists drift test; the row names VAL-B9 for a map's key."""
    row = _val_b8()
    assert _names(row, "an engine key (") == set(ENGINE_KEYS)
    assert _names(row, "an item key in map items only (") == set(ITEM_KEYS)
    assert "VAL-B9" in row


def test_val_b5_choices_and_pattern_together_are_refused() -> None:
    """VAL-AC1 (VAL-B5), AC 1, AC 2."""
    spec = _step(two_step(), "review", produces={"v": Value(choices=["a"], pattern="a")})
    assert "value-choices-and-pattern" in codes(spec)


@pytest.mark.parametrize("line,stored", [("ARTIFACT route: plan", "plan"), ("ARTIFACT route: Plan ", "plan")])
def test_val_b6_a_value_is_stored_trimmed_and_lower_cased(line: str, stored: str) -> None:
    """VAL-AC1 (VAL-B6), AC 1, AC 2."""
    out = parse_output(f"Done.\n{line}", {"route": Value(choices=["plan", "discovery"])})
    assert out.values.get("route") == stored and out.issues == []


def test_val_b6_a_value_outside_the_choices_is_not_stored() -> None:
    """VAL-AC1 (VAL-B6), AC 1, AC 2."""
    out = parse_output("Done.\nARTIFACT route: maybe", {"route": Value(choices=["plan", "discovery"])})
    assert "route" not in out.values and "value_invalid:route" in out.issues


def test_val_b6_a_required_value_with_no_line_is_missing() -> None:
    """VAL-AC1 (VAL-B6), AC 1, AC 2."""
    out = parse_output("Done.\nno line", {"route": Value(choices=["plan", "discovery"])})
    assert "route" not in out.values and "value_missing:route" in out.issues


@pytest.mark.parametrize("name", sorted(ENGINE_KEYS | ITEM_KEYS))
def test_val_b8_an_input_named_like_a_reserved_key_is_refused(name: str) -> None:
    """VAL-AC1 (VAL-B8), AC 1, AC 2: an input named `workdir` (or any engine or item key) is refused `reserved-key`."""
    spec: WorkflowSpec = dataclasses.replace(two_step(), input=InputDeclaration(parameters=(Param(name=name),)))
    found = [f for f in errors(validate(spec, CLAUDE_ONLY)) if f.code == "reserved-key"]
    assert found and name in found[0].message


def test_val_b8_an_input_with_an_ordinary_name_passes() -> None:
    """VAL-AC1 (VAL-B8), AC 1, AC 2."""
    spec = dataclasses.replace(two_step(), input=InputDeclaration(parameters=(Param(name="audience"),)))
    assert "reserved-key" not in codes(spec)


def test_val_b8_an_item_key_outside_a_map_is_refused() -> None:
    """VAL-AC1 (VAL-B8), AC 1, AC 2."""
    spec = _step(two_step(), "draft", prompt="Write {item_id}")
    assert "template-unknown-field" in codes(spec)
