"""The guide's section "Hold filing" held against the built CLI and catalog, and the twelfth criterion of i171b."""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

import pytest

from tempergraph import settings
from tempergraph.cli.main import VERBS, main
from tempergraph.improve import params

PLUGINS = Path(__file__).resolve().parents[2].parent  # plugins/
GUIDE = PLUGINS / "tempergraph" / "docs" / "guides" / "improving-workflows.guide.md"
SPECS = PLUGINS / "tempergraph" / "docs" / "specs"
PLAN_SPECS = ("friction-filing-decisions", "self-improvement", "loop-issues", "improvement-proposals",
              "run-settings-and-overrides", "run-options")


def section() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    body = text.split("\n## Hold filing\n", 1)[1]
    return body.split("\n## ", 1)[0]


def help_of(verb: str, capsys: pytest.CaptureFixture[str]) -> str:
    with contextlib.suppress(SystemExit):
        main([verb, "--help"])
    return capsys.readouterr().out


def test_the_guide_names_the_three_holds_with_what_they_still_run() -> None:  # PRP-AC16, ROP-AC12
    text = section()
    assert "loop_autonomy" in settings.CATALOG and "`loop_autonomy`" in text
    for level in ("record", "file", "propose", "trial"):
        assert level in text
    assert "`TEMPERGRAPH_AUTONOMY=record`" in text
    assert "`tempergraph config paths`" in text and "config" in VERBS
    assert "`--dry-run`" in text
    for words in ("still runs", "still spends", "autonomy_record", "would_file", "loop_judged"):
        assert words in text or words.replace("still spends", "it still spends") in text, words


def test_dry_run_is_on_run_and_on_resume_as_the_guide_says(capsys: pytest.CaptureFixture[str]) -> None:  # ROP-AC12
    text = section()
    assert "tempergraph run <workflow>" in text and "tempergraph resume <workflow> <thread> --dry-run" in text
    for verb in ("run", "resume"):
        assert "--dry-run" in help_of(verb, capsys), verb


def test_config_paths_is_a_command_of_the_cli(capsys: pytest.CaptureFixture[str]) -> None:  # PRP-AC16
    assert "paths" in help_of("config", capsys)


def test_every_command_of_the_section_is_a_verb_of_the_cli() -> None:  # ROP-AC12
    spans = re.findall(r"`([^`]+)`", section())
    commands = [s for s in spans if s.startswith("tempergraph ")]
    assert commands
    for command in commands:
        assert command.split()[1] in VERBS, command


def test_the_guide_names_the_mute_by_a_duplicate_close_for_mute_days() -> None:  # ISS-AC3
    text = section()
    assert "not planned or as a duplicate" in text and "`mute.days`" in text
    assert params.value("mute.days") == 30 and "30 days" in text
    assert "muted" in text


def test_the_specs_of_the_run_name_no_workflow_package() -> None:  # FFD-AC1, ISS-AC12, PRP-AC16, ROP-AC12
    names = set()
    for manifest in PLUGINS.glob("*/tempergraph.json"):
        names.add(json.loads(manifest.read_text(encoding="utf-8")).get("name"))
        names.add(manifest.parent.name)
    names -= {None, "tempergraph", "tempergraph-monitor"}
    assert names
    for slug in PLAN_SPECS:
        text = (SPECS / f"{slug}.spec.md").read_text(encoding="utf-8").lower()
        text = text.replace("temperspec's format", "")  # the spec format's name in a purpose line, not a package
        for name in names:
            assert not re.search(rf"(?<![\w-]){re.escape(str(name).lower())}(?![\w-])", text), (slug, name)


def test_every_parameter_record_has_a_source_and_the_new_one_is_there() -> None:  # ISS-AC12
    assert all(p.source for p in params.PARAMS.values())
    assert params.PARAMS["seen_again.max_per_issue_per_day"].source == "ISS-B13"
