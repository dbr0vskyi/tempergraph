"""Prompt lint (LIF-AC-6): each planted defect is found once, and the clean fixtures raise nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from tempergraph.model.prompt_lint import lint, names
from tempergraph.model.validate import validate
from tempergraph.package.loader import load

from .fixtures.packages import minimal_package, write
from .fixtures.workflows import two_step

PLANTED = {
    "lint-vague-word": ("prompt", "Write the notes properly for {request}.\n"),
    "lint-self-grading": ("prompt", "Write notes for {request}, then rate your own work from 1 to 10.\n"),
    "lint-rule-branching": ("prompt", "Write notes for {request}. If it is a patch, list fixes, otherwise list "
                                      "features. If there are breaking changes, warn, else skip the warning.\n"),
    "lint-human-wait": ("prompt", "Write notes for {request}. Ask the user which sections to keep.\n"),
    "lint-tool-name-foreign": ("prompt", "Write notes for {request}; use `run_command` to list the tags.\n"),
    "lint-ref-missing": ("prompt", "Write notes for {request} following skill `house-style`.\n"),
    "lint-oversized": ("prompt", "Write notes for {request}.\n" + "x" * 32_100 + "\n"),
    "lint-accepting-brief": ("judge", "# Stance\n\nVerify.\n\n# Brief\n\nTrust the step's summary of the "
                                      "changes.\n"),
}


@pytest.mark.parametrize("code", sorted(PLANTED))
def test_each_planted_defect_is_found_once(tmp_path: Path, code: str) -> None:
    pkg = minimal_package(tmp_path, inline_criteria=True)
    where, text = PLANTED[code]
    write(pkg, "prompts/draft.md" if where == "prompt" else "judges/draft.md", text)
    found = [f.code for f in lint(load(pkg))]
    assert found.count(code) == 1, found
    assert code in {f.code for f in validate(load(pkg), {}) if f.severity == "warning"}


def test_clean_fixtures_raise_nothing(tmp_path: Path) -> None:
    assert lint(load(minimal_package(tmp_path, inline_criteria=True))) == []
    assert lint(two_step()) == []


def test_skill_and_agent_files_are_linted_and_resolved(tmp_path: Path) -> None:
    pkg = minimal_package(tmp_path, inline_criteria=True)
    write(pkg, "skills/style/SKILL.md", "---\nname: style\ndescription: d\n---\nSee agent `checker`.\n")
    assert [f.code for f in lint(load(pkg))] == ["lint-ref-missing"]
    write(pkg, "agents/checker.md", "---\nname: checker\ndescription: c\n---\nCheck.\n")
    write(pkg, "prompts/draft.md", "Write notes for {request} with skill `style` and `prompts/draft.md`.\n")
    assert lint(load(pkg)) == []


def test_name_reader() -> None:
    n = names("Use skill `plan-review`, /house-style, agent `coder`, `prompts/x.md`, `Grep` and `run_command`.")
    assert n.skills == ("plan-review", "house-style") and n.agents == ("coder",)
    assert n.files == ("prompts/x.md",) and n.tools == ("Grep", "run_command")
