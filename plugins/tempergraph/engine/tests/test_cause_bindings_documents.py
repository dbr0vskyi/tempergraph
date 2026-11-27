"""The documents of the bindings of a cause: the decision record, the spec's structure, the overview's Purpose and
LOS-B7 (task AC 9, AC 10, AC 12)."""

from __future__ import annotations

import re

from tempergraph.improve import params

from .conftest import DOCS, workflow_names

SPECS = DOCS / "specs"
SPEC = SPECS / "cause-bindings.spec.md"
RECORD = DOCS / "adr" / "a-duplicate-close-binds-a-cause-to-the-issue-its-comment-names.adr.md"
EARLIER = "a-close-as-a-duplicate-mutes-a-loop-issues-cause.adr.md"
TEN = ["Context", "Current state", "Forces", "Options considered", "Decision", "Decision rationale",
       "Consequences", "Risks", "Assumptions", "Revisit when"]
CHANGED = ("cause-bindings", "loop-issues", "local-observability-store", "overview", "security", "pull-request-read")


def read(path) -> str:  # type: ignore[no-untyped-def]
    return path.read_text(encoding="utf-8")


def test_the_decision_record_has_the_ten_sections_in_order() -> None:  # AC 9
    text = read(RECORD)
    assert re.findall(r"^## (.+)$", text, re.M) == TEN


def test_the_decision_record_links_the_earlier_record_and_compares_the_options() -> None:  # AC 9
    text = read(RECORD)
    context = text.split("## Context", 1)[1].split("\n## ", 1)[0]
    assert f"({EARLIER})" in context
    options = text.split("## Options considered", 1)[1].split("\n## ", 1)[0]
    heads = re.findall(r"^### (.+)$", options, re.M)
    assert len(heads) >= 4
    low = [h.lower() for h in heads]
    assert "chosen" in low[0] and "comment" in low[0]
    assert any("marker" in h for h in low)
    assert any("graphql" in h and "duplicate-of" in h for h in low)
    assert any("no record" in h for h in low)


def test_the_decision_record_names_the_negation_risk_and_the_unchecked_event() -> None:  # AC 9
    text = read(RECORD)
    risks = text.split("## Risks", 1)[1].split("\n## ", 1)[0]
    assert "not a duplicate of #5" in risks
    assumptions = text.split("## Assumptions", 1)[1].split("\n## ", 1)[0]
    assert "REST event" in assumptions and "not checked" in assumptions


def test_the_earlier_record_names_no_part_of_this_change() -> None:  # AC 9
    earlier = read(DOCS / "adr" / EARLIER).lower()
    for word in ("filing-bindings", "cause-bindings", "bnd-", "binding_unreadable", "comment_capped"):
        assert word not in earlier, word


def test_the_spec_has_its_prefix_and_depends_on_rows_for_every_spec_it_links() -> None:  # AC 10
    text = read(SPEC)
    ids = re.findall(r"^### ([A-Z0-9]+)-B\d+ ", text, re.M)
    assert ids and set(ids) == {"BND"}
    assert re.findall(r"^- (BND)-AC\d+ \(", text, re.M)
    depends = text.split("## Depends on", 1)[1].split("\n## ", 1)[0]
    rows = set(re.findall(r"^- `([\w.-]+\.spec\.md)`", depends, re.M))
    body = text.split("## Behaviours", 1)[1]
    linked = set(re.findall(r"\(([\w-]+\.spec\.md)\)", body))
    owner = {}
    for path in SPECS.glob("*.spec.md"):
        for ident in re.findall(r"^### ([A-Z0-9]+-B\d+) ", read(path), re.M):  # a split spec keeps its ids
            owner[ident] = path.name
    for ident in set(re.findall(r"\b([A-Z][A-Z0-9]{1,7}-B\d+)\b", body)):
        if not ident.startswith("BND-") and ident in owner:
            linked.add(owner[ident])
    assert linked <= rows, linked - rows
    assert "cause-bindings.spec.md" not in rows


def test_the_overview_purpose_names_the_spec_and_los_b7_names_the_record() -> None:  # AC 10
    overview = read(SPECS / "overview.spec.md")
    purpose = overview.split("## Purpose", 1)[1].split("\n## ", 1)[0]
    assert "cause-bindings.spec.md" in purpose
    store = read(SPECS / "local-observability-store.spec.md")
    b7 = store.split("### LOS-B7", 1)[1].split("\n### ", 1)[0]
    assert "filing-bindings.json" in b7


def test_the_specs_of_the_change_stay_in_budget_and_name_no_workflow() -> None:  # AC 10
    names = workflow_names()
    assert names
    for spec in CHANGED:
        raw = (SPECS / f"{spec}.spec.md").read_bytes()
        assert len(raw.splitlines()) <= 400 and len(raw) <= 30_720, spec
        text = raw.decode("utf-8").replace("temperspec's format", "")
        for name in names:
            assert not re.search(rf"(?<![\w-]){re.escape(name)}(?![\w])", text), (spec, name)


def test_no_parameter_is_added_for_bindings_and_each_has_a_source() -> None:  # AC 12
    assert params.PARAMS
    for name, param in params.PARAMS.items():
        assert param.source, name
        assert "bind" not in name.lower(), name
