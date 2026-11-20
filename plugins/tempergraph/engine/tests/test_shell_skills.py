"""Structure of the plugin's shell skills (SHL §6, T9.2.6): frontmatter, links, no shipped workflow named
(SHL-AC-1), and every engine verb and option a skill tells the model to run exists in the CLI."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from tempergraph.cli.main import VERBS, _parser

from .test_source_rules import SHIPPED_WORKFLOW_NAMES

PLUGIN = Path(__file__).resolve().parents[2]
SKILLS = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
CALL = re.compile(r"`tempergraph ([^`]+)`")


def _files(skill: Path) -> list[Path]:
    return [skill, *sorted((skill.parent / "references").rglob("*.md"))]


def _options(parser: argparse.ArgumentParser, words: list[str]) -> set[str]:
    """The options valid after `words` (verb, then sub-verbs) in the built parser."""
    found: set[str] = set()
    for act in parser._actions:
        found |= {o for o in act.option_strings if o.startswith("--")}
        if isinstance(act, argparse._SubParsersAction) and words and words[0] in act.choices:
            found |= _options(act.choices[words[0]], words[1:])
    return found


def test_there_are_skills() -> None:
    assert any(p.parent.name == "author" for p in SKILLS)


@pytest.mark.parametrize("skill", SKILLS, ids=[p.parent.name for p in SKILLS])
def test_frontmatter_links_and_size(skill: Path) -> None:
    text = skill.read_text(encoding="utf-8")
    m = re.match(r"^---\nname: ([a-z0-9-]+)\ndescription: (.+)\n---\n", text)
    assert m and m.group(1) == skill.parent.name and 20 < len(m.group(2)) <= 1024
    assert len(text.splitlines()) < 500  # a core under 500 lines, references read on demand (SHL §5)
    for f in _files(skill):
        for target in re.findall(r"\]\(([^)#:]+)\)", f.read_text(encoding="utf-8")):
            assert (f.parent / target).exists(), f"{f.relative_to(PLUGIN)} links {target}"


@pytest.mark.parametrize("skill", SKILLS, ids=[p.parent.name for p in SKILLS])
def test_no_shipped_workflow_is_named(skill: Path) -> None:  # SHL-AC-1
    for f in _files(skill):
        text = f.read_text(encoding="utf-8")
        assert not [w for w in SHIPPED_WORKFLOW_NAMES if w in text], f


@pytest.mark.parametrize("skill", SKILLS, ids=[p.parent.name for p in SKILLS])
def test_every_engine_call_exists(skill: Path) -> None:
    parser = _parser()
    calls = 0
    for f in _files(skill):
        for call in CALL.findall(f.read_text(encoding="utf-8")):
            words = [w for w in call.split() if not w.startswith(("<", "[", "--", "-")) and "|" not in w]
            verb = call.split()[0]
            assert verb in VERBS, f"{f.name}: {call}"
            valid = _options(parser, words)
            for opt in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", call):
                assert opt in valid, f"{f.name}: `tempergraph {call}` passes {opt}, which is not built"
            calls += 1
    assert calls > 0
