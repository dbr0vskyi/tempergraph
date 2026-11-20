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
    front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert front
    fields = dict(line.split(": ", 1) for line in front.group(1).splitlines())
    assert set(fields) <= {"name", "description", "allowed-tools"}
    assert fields["name"] == skill.parent.name and 20 < len(fields["description"]) <= 1024
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


READ_ONLY = re.compile(r"^(Read|Grep|Glob|Bash\((git (status|log|diff)|ls|cat|grep|ps|tempergraph (status|facts|list|graph|"
                       r"validate|audit|workflows list|executors|worktree list|outcome show|upgrade-check|"
                       r"install --check|author show)):\*\))$")


def test_troubleshooter_grant_is_read_only() -> None:
    """SHL §2.3: the troubleshooter's `allowed-tools` holds read rules only, and its text forbids the one flag a
    prefix cannot exclude."""
    text = (PLUGIN / "skills" / "troubleshoot" / "SKILL.md").read_text(encoding="utf-8")
    grant = re.search(r"^allowed-tools: (.+)$", text, re.M)
    assert grant
    rules = [r.strip() for r in grant.group(1).split(", ")]
    assert rules and all(READ_ONLY.match(r) for r in rules), [r for r in rules if not READ_ONLY.match(r)]
    assert "--stamp" in text


def test_install_skill_runs_only_its_fixed_commands() -> None:
    """LSK-AC-3, structurally: every command the install skill names is the launcher's or the shim's."""
    text = (PLUGIN / "skills" / "install" / "SKILL.md").read_text(encoding="utf-8")
    commands = re.findall(r"`(<plugin>/bin/tempergraph [^`]+|<shim> [^`]+|tempergraph [^`]+)`", text)
    allowed = ("<plugin>/bin/tempergraph install", "<shim> workflows list", "<shim> executors --probe",
               "<shim> workflows register", "tempergraph executors")
    assert commands and all(c.startswith(allowed) for c in commands), commands
    for c in commands:
        if c.startswith("<plugin>/bin/tempergraph install"):
            from tempergraph.install.bootstrap import parser

            known = {o for a in parser()._actions for o in a.option_strings}
            assert set(re.findall(r"--[a-z-]+", c)) <= known, c
