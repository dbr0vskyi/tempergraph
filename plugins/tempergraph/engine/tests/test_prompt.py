"""Prompt rendering (PRM §2; PRM-B1..B5, PRM-AC-1..4) and the output contract (PRM §2.3, VAL §2.1)."""

from __future__ import annotations

import itertools

import pytest

from tempergraph.api import Value
from tempergraph.executors.capabilities import DECLARED
from tempergraph.render.output import parse_output
from tempergraph.render.prompt import AttemptContext, Blocker, render_step

from .fixtures.workflows import two_step

SPEC = two_step()
DRAFT = SPEC.units["draft"]


def ctx(**kw: object) -> AttemptContext:
    base = {"template": "Write the notes for {request} into notes.md", "fields": {"request": "v1.2"}}
    base.update(kw)
    return AttemptContext(**base)  # type: ignore[arg-type]


def tools_block(text: str) -> str:
    start = text.index("## Tools for this step")
    end = text.index("\n\n", start)
    return text[start:end]


def test_same_prompt_on_every_executor_but_the_tools_block() -> None:
    renders = {ex: render_step("draft", DRAFT, ctx(), caps).text for ex, caps in DECLARED.items()}
    for a, b in itertools.combinations(renders, 2):
        ta, tb = renders[a], renders[b]
        assert ta.replace(tools_block(ta), "") == tb.replace(tools_block(tb), "")
    assert "`Read`" in renders["claude"] and "`Bash`" in renders["claude"]
    assert "`read_file`" in renders["messages-api"] and "`run_command`" in renders["messages-api"]
    assert "`view_file`" in renders["antigravity"]


def test_no_self_assessment() -> None:
    text = render_step("draft", DRAFT, ctx(), DECLARED["claude"]).text
    crit = DRAFT.gate.criteria[0]
    assert crit.text in text
    assert crit.check_method not in text and "blocker" not in text.lower()
    for word in ("confidence", "verdict", "grade yourself", "status of each"):
        assert word not in text.lower()


def test_absent_when_unused() -> None:
    bare = DRAFT.__class__(kind="step", gate=DRAFT.gate.__class__(), step=DRAFT.step.__class__(prompt="x"))  # type: ignore[union-attr]
    r = render_step("draft", bare, ctx(template="Just do {request}"), DECLARED["claude"])
    assert r.sections == ["template", "blocked"]


def test_braces_in_appended_text_stay_literal() -> None:
    r = render_step("draft", DRAFT, ctx(feedback="use {not_a_field} please"), DECLARED["claude"])
    assert "use {not_a_field} please" in r.text


def test_retry_told_not_resumed() -> None:
    r = render_step("draft", DRAFT, ctx(retry=True, attempt=2,
                    blockers=(Blocker(criterion="c-file", place="notes.md:3", problem="empty", fix="fill it"),),
                    previous_report="I wrote it all" * 400, changed_paths=tuple(f"p{i}" for i in range(30))),
                    DECLARED["claude"])
    assert "c-file" in r.text and "fill it" in r.text and "a claim, not a fact" in r.text
    assert "p19" in r.text and "p20" not in r.text  # ≤ 20 paths (PRM-AC-4)
    section = r.text[r.text.index("What the previous attempt reported"):]
    assert len(section.split("Paths changed")[0]) < 3200  # ≤ 3000 chars of report


def test_missing_field_recorded() -> None:
    r = render_step("draft", DRAFT, ctx(fields={}), DECLARED["claude"])
    assert r.missing_fields == ["request"] and "⟨missing:request⟩" in r.text


@pytest.mark.parametrize("line,stored,issue", [
    ("ARTIFACT route: plan", "plan", None),
    ("ARTIFACT route: Plan ", "plan", None),
    ("ARTIFACT route: maybe", None, "value_invalid:route"),
    ("done", None, "value_missing:route"),
])
def test_value_table(line: str, stored: str | None, issue: str | None) -> None:
    out = parse_output(f"Work done.\n{line}", {"route": Value(choices=["plan", "discovery"])})
    assert out.values.get("route") == stored
    assert (issue in out.issues) if issue else out.issues == []


def test_blocked_and_upstream() -> None:
    assert parse_output("x\nBLOCKED: need the ticket", {}).blocked == "need the ticket"
    ok = parse_output("x\nUPSTREAM draft: wrong file", {}, upstream_allowed=("draft",))
    assert ok.upstream == ("draft", "wrong file")
    other = parse_output("x\nUPSTREAM plan: wrong", {}, upstream_allowed=("draft",))
    assert other.upstream is None and other.blocked is not None


def test_artifact_lines_only_at_the_end() -> None:
    out = parse_output("ARTIFACT notes: early.md\nthen more text", {"notes": "file"})
    assert out.artifacts == {}
