"""The guide's section "Hold filing" held against the built CLI and catalog, and the checks of the twelfth
criterion of the friction-pattern task: no workflow in the specs, a source on every parameter."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tempergraph import settings
from tempergraph.cli.main import VERBS, main
from tempergraph.improve import params

from .conftest import DOCS, workflow_names

GUIDE = DOCS / "guides" / "improving-workflows.guide.md"
SPECS = (
    "friction-filing-decisions", "self-improvement", "loop-issues", "improvement-proposals",
    "run-settings-and-overrides", "run-options",
)


def section() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    match = re.search(r"^## Hold filing\n(.*?)(?=^## )", text, re.S | re.M)
    assert match, 'the guide has no section "Hold filing"'
    return match.group(1)


def help_of(verb: str, capsys: pytest.CaptureFixture[str]) -> str:
    capsys.readouterr()
    main([verb, "--help"])
    return capsys.readouterr().out


def test_the_guide_names_the_three_holds_the_cli_and_the_catalog_have(
        capsys: pytest.CaptureFixture[str]) -> None:  # PRP-AC16, ROP-AC12 (task AC 10)
    text = section()
    assert "loop_autonomy" in text and "loop_autonomy" in settings.CATALOG  # the setting
    assert "`--dry-run`" in text
    assert "--dry-run" in help_of("run", capsys) and "--dry-run" in help_of("resume", capsys)
    assert "tempergraph run <workflow>" in text and "tempergraph resume <workflow> <thread> --dry-run" in text
    assert "TEMPERGRAPH_AUTONOMY=record" in text
    assert "tempergraph config paths" in text
    main(["config", "paths", "--help"])  # `paths` is an action of `config`
    capsys.readouterr()
    for level in ("record", "file", "propose", "trial"):
        assert f"`{level}`" in text
    for what in ("autonomy_record", "would_file", "loop_judged", "loop.jsonl"):  # what each still records
        assert what in text
    assert "still run" in text and "still spends" in text


def test_every_command_of_the_section_is_a_verb_of_the_cli() -> None:  # PRP-AC16 (task AC 10)
    spans = re.findall(r"`([^`]*)`", section())
    commands = [s for s in spans if s.startswith("tempergraph ")]
    assert commands
    for command in commands:
        assert command.split()[1] in VERBS, command


def test_the_guide_says_a_duplicate_close_mutes_for_mute_days() -> None:  # ISS-AC3 (task AC 10)
    text = section()
    assert "not planned" in text and "duplicate" in text and "`mute.days`" in text
    assert f"{params.value('mute.days'):g} days" in text
    assert "muted" in text


def test_the_specs_of_the_change_name_no_workflow() -> None:  # FFD-AC1, ISS-AC12, PRP-AC16, ROP-AC12 (task AC 12)
    names = workflow_names()
    assert names
    for spec in SPECS:
        text = (DOCS / "specs" / f"{spec}.spec.md").read_text(encoding="utf-8")
        text = text.replace("temperspec's format", "")  # the spec method's own name, not a workflow of this change
        for name in names:
            assert not re.search(rf"(?<![\w-]){re.escape(name)}(?![\w])", text), (spec, name)


def test_every_parameter_has_a_source_and_the_comment_bound_is_one() -> None:  # ISS-AC12, FFD-AC1 (task AC 12)
    assert params.PARAMS
    for name, param in params.PARAMS.items():
        assert param.source, name
    bound = params.PARAMS["seen_again.max_per_issue_per_day"]
    assert bound.value == 1 and "ISS-B13" in bound.source
