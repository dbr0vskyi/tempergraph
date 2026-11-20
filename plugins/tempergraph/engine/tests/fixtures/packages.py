"""Fixture workflow packages written to disk (PKG §2.1, §2.7), one builder per shape the tests need."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

OUTCOME: dict[str, Any] = {
    "schema_version": 1, "revision": 1,
    "statement": "Release notes that cover every merged change since the last tag, faithfully.",
    "deliverables": [{"key": "notes", "kind": "file", "where": "the run's branch"}],
    "final": [{"id": "rn-complete", "severity": "blocker", "verified_by": "judge",
               "text": "Every merged change since the last tag is in the notes or listed as excluded with a reason",
               "check_method": "Compare the notes with the merged changes",
               "verifier": {"references": ["notes"], "scale": {
                   "met": "every change is listed or excluded with a reason", "partial": "no partial: any gap is UNMET",
                   "unmet": "a merged change is missing", "evidence": "the list of changes and where each is"}}}],
    "intermediate": {"draft": {
        "statement": "A draft with the template's headings whose entries match the changes",
        "criteria": [
            {"id": "rn-sections", "severity": "blocker", "verified_by": "check", "serves": ["rn-complete"],
             "text": "The notes have the template's four headings in order", "verifier": {"check": "draft_check"}},
            {"id": "rn-faithful", "severity": "blocker", "verified_by": "judge", "serves": ["rn-complete"],
             "text": "Every entry matches what its merged change did", "check_method": "Read each entry and its change",
             "verifier": {"references": ["notes"], "scale": {
                 "met": "each entry matches its change", "partial": "no partial: any gap is UNMET",
                 "unmet": "an entry misstates its change", "evidence": "entry and change pairs"}}}]}},
    "assumptions": [], "revisions": [],
}

DECLARATION = '''
from tempergraph.api import Gate, Judge, Routing, Step, Workflow, text

from .checks import draft_check


def workflow():
    return Workflow(
        order=["draft"],
        routing=Routing(description="Write release notes for the changes since the last tag"),
        issue_repository="acme/release-notes",
        units={"draft": Step(prompt=text("prompts/draft.md"), tools=["read", "write"], produces={"notes": "file"},
                             gate=Gate(check=draft_check, judge=Judge(file="judges/draft.md", references=["notes"])))},
    )
'''

INLINE_CRITERIA = '''

INLINE = [Criterion(id="rn-sections", text="The notes have the template's four headings in order", mechanical=True),
          Criterion(id="rn-faithful", text="Every entry matches what its merged change did",
                    check_method="Read each entry and its change")]
'''

CHECKS = '''
from tempergraph.api import CheckFinding, CheckResult


def draft_check(ctx):
    return CheckResult(result="PASS", evidence="four headings",
                       findings=[CheckFinding(status="pass", criterion="rn-sections")])
'''

OVERVIEW = """# Release notes

## 1. Overview

{statement}

## 6. Acceptance criteria

- [ ] rn-complete Every merged change since the last tag is in the notes or listed as excluded with a reason
"""

UNIT_SPEC = """# draft

## 1. Overview

Writes the notes. See the [overview](00-overview.spec.md).

## 6. Acceptance criteria

- [ ] rn-sections The notes have the template's four headings in order
- [ ] rn-faithful Every entry matches what its merged change did
"""


def write(root: Path, rel: str, content: str | dict[str, Any] | list[Any]) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content, indent=2), encoding="utf-8")
    return path


def minimal_package(parent: Path, name: str = "release-notes", version: str = "0.1.0", *,
                    declaration: str = DECLARATION, checks: str = CHECKS, inline_criteria: bool = False) -> Path:
    """The minimal package of PKG §2.7. `inline_criteria` adds the draft gate's criteria in the declaration
    (the older form, WFM-B5) for tests that run before OUT's reader fills gates from `outcome.json`."""
    root = parent / name
    mod = name.replace("-", "_")
    write(root, ".claude-plugin/plugin.json", {"name": name, "version": version, "description": "Release notes", "author": {"name": "Example Owner"}, "license": "MIT",
                                               "dependencies": ["tempergraph"]})
    write(root, "tempergraph.json", {"schema_version": 1, "name": name, "entry": f"{mod}:workflow",
                                     "workflow_api": 1, "docs": "provisional"})
    write(root, "outcome.json", OUTCOME)
    write(root, "workflow/pyproject.toml", textwrap.dedent(f'''
        [project]
        name = "tgwf-{name}"
        requires-python = ">=3.11"
        dependencies = []
    '''))
    decl = declaration
    if inline_criteria:
        decl = decl.replace("from tempergraph.api import Gate,", "from tempergraph.api import Criterion, Gate,")
        decl = decl.replace('references=["notes"]))', 'references=["notes"]), criteria=INLINE)')
        decl += INLINE_CRITERIA
    write(root, f"workflow/{mod}/__init__.py", textwrap.dedent(decl))
    write(root, f"workflow/{mod}/checks.py", textwrap.dedent(checks))
    write(root, "prompts/draft.md", "Write release notes for {request} into notes.md.\n")
    write(root, "judges/draft.md", "# Stance\n\nVerify the notes against the changes.\n\n# Brief\n\nRead notes.md.\n")
    write(root, "evals/cases.json", {"schema_version": 1, "cases": [{"id": "case-1", "request": "v1.2"}]})
    write(root, "evals/checks/draft/must-pass/notes.md", "# Added\n# Changed\n# Fixed\n# Removed\n")
    write(root, "evals/checks/draft/must-fail/notes.md", "# Added\n")
    write(root, "blueprint.json", {"schema_version": 1, "units": ["draft"]})
    write(root, "authoring.json", {"schema_version": 1, "entry_path": "scratch"})
    write(root, "diagram/workflow.md", "draft -> outcome -> finalizer\n")
    write(root, "tests/test_release_notes.py", "def test_placeholder():\n    assert True\n")
    write(root, "docs/README.md", "# Docs\n\nRules: provisional (the engine's docs README).\n")
    write(root, "docs/specs/00-overview.spec.md", OVERVIEW.format(statement=OUTCOME["statement"]))
    write(root, "docs/specs/01-draft.spec.md", UNIT_SPEC)
    write(root, "README.md", f"# {name}\n\nWrites release notes. Start: `tempergraph run {name} v1.2`.\n")
    return root


def package_parts(root: Path, name: str, outcome: dict[str, Any] | None = None) -> Path:
    """The non-declaration parts every package carries (PKG §2.1), for a test that writes its own declaration."""
    write(root, "workflow/pyproject.toml", f'[project]\nname = "tgwf-{name}"\ndependencies = []\n')
    write(root, "outcome.json", outcome or {"schema_version": 1, "revision": 1, "statement": "Done well.",
                                            "deliverables": [], "final": [], "intermediate": {}})
    write(root, "evals/cases.json", {"schema_version": 1, "cases": [{"id": "case-1", "request": "x"}]})
    write(root, "diagram/workflow.md", "generated\n")
    write(root, "tests/test_placeholder.py", "def test_placeholder():\n    assert True\n")
    write(root, "README.md", f"# {name}\n")
    write(root, "docs/README.md", "# Docs\n")
    return root
