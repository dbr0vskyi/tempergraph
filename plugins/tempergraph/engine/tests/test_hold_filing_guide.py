"""The guide's section "Hold filing" held against the built CLI and catalog, and the checks of the twelfth
criterion of the friction-pattern task: no workflow in the specs, a source on every parameter."""

from __future__ import annotations

import re

import pytest

from tempergraph import settings
from tempergraph.cli.main import VERBS, main
from tempergraph.improve import params

from .conftest import DOCS, workflow_names

GUIDE = DOCS / "guides" / "improving-workflows.guide.md"
SPECS = (
    "friction-filing-decisions", "self-improvement", "loop-issues", "improvement-proposals",
    "run-settings-and-overrides", "run-options", "loop-filing-state", "contracts", "run-events",
    "loop-summary-and-review-retries", "runs-without-a-final-exit", "promotion-check",
    "durability-and-resume",
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


def test_the_guide_names_the_holds_the_cli_and_the_catalog_have(
        capsys: pytest.CaptureFixture[str]) -> None:  # PRP-AC16, ROP-AC13 (task AC 14)
    text = section()
    assert "loop_autonomy" in text and "loop_autonomy" in settings.CATALOG  # the setting
    assert "loop_dry_run" in text and "loop_dry_run" in settings.CATALOG
    for option in ("--dry-run", "--no-dry-run"):
        assert f"`{option}`" in text
        assert option in help_of("run", capsys) and option in help_of("resume", capsys)
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


def test_the_guide_states_the_whole_filing_rule_in_one_section() -> None:  # LFS-AC2, ROP-AC12 (task AC 14)
    text = " ".join(section().split())
    assert "The loop files by default" in text
    assert "a workflow declares `loop_dry_run`" in text and "a settings file or a profile" in text
    assert "`--dry-run` and `--no-dry-run` on `run` and `resume`" in text
    assert "the one given last wins" in text and "`--unset run.loop_dry_run`" in text
    assert "`--no-dry-run` files for one thread of a workflow that declares `record`" in text
    assert "The hold wins over the argument" in text
    assert "The order is: the hold, then the declared level and the argument, then the dry run." in text
    assert "The improvement mode has no part in any of it." in text


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


def test_the_guide_says_what_a_duplicate_close_with_a_target_does() -> None:  # AC 11 (BND-B1, BND-B3, BND-B5, BND-B11)
    text = " ".join(section().split())
    assert "`Duplicate of #<n>`" in text
    assert "later sightings to that issue as comments, at most one a day" in text
    assert "a duplicate with no such comment mutes" in text and "`mute.days`" in text
    assert "reopening the loop issue ends the binding" in text
    assert "a closed target decides by its close reason" in text
    assert "waiting create of a bound cause is delivered as a comment" in text


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
