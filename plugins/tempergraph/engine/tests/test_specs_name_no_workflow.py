"""The specs this change relies on name no shipped workflow (AC 7)."""

from __future__ import annotations

import re

from .conftest import DOCS, workflow_names

SPECS = (
    "run-outcome", "feedback-and-judge-reliability", "self-improvement", "finalizer-contract",
    "improvement-proposals", "lifecycle-and-evals", "audit-rule-catalog", "session-review",
    "pull-request-read", "run-state-on-a-branch", "durability-and-resume",
)


def test_the_specs_name_no_shipped_workflow() -> None:  # AC 7 (OUT-B26 holds of the specs)
    names = workflow_names()  # found by the packages' own manifests, never typed here
    assert names
    for spec in SPECS:
        path = DOCS / "specs" / f"{spec}.spec.md"
        text = path.read_text(encoding="utf-8")
        for name in names:
            found = re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text)
            assert not found, f"{path.name} names the workflow {name!r} near {text[found.start():found.start() + 60]!r}"
