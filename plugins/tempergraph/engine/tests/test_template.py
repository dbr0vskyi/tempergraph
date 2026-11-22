"""Template grammar (CON-B8, CON-AC2)."""

from __future__ import annotations

import pytest

from tempergraph.render.template import TemplateError, fields, render


def test_fields_and_literal_braces() -> None:
    assert fields("Do {task_id} with {{braces}} and {settings.depth}") == ["task_id", "settings.depth"]
    assert render("{{x}} {a}", {"a": "1"})[0] == "{x} 1"


@pytest.mark.parametrize("bad", ["{", "}", "{a b}", "{a.b}", "{1x}", "{}", "x {a"])
def test_outside_grammar_refused(bad: str) -> None:
    with pytest.raises(TemplateError):
        fields(bad)


def test_missing_value_renders_marker_and_is_recorded() -> None:
    text, missing = render("Fix {ticket} on {branch}", {"branch": "main"})
    assert text == "Fix ⟨missing:ticket⟩ on main" and missing == ["ticket"]
