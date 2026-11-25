"""Generated-table drift tests: CON-B13 exit codes equal the engine constants (CON-AC6, CLI-AC4)."""

from __future__ import annotations

import re

from tempergraph.constants import ExitCode

from .conftest import DOCS


def test_exit_codes_match_contracts_spec() -> None:
    text = (DOCS / "specs" / "contracts.spec.md").read_text(encoding="utf-8")
    row = text.split("### CON-B13 ", 1)[1].split("\n- ", 1)[0]
    documented = {int(n) for n in re.findall(r"`(\d+)`", row)}
    assert documented == {int(c) for c in ExitCode}


def test_docs_artifacts_carry_type_suffix() -> None:
    """The file-naming rule of the docs README (ADR-0017)."""
    suffix = {"specs": ".spec.md", "adr": ".adr.md", "research": ".rsrch.md", "plans": ".plan.md"}
    bad = []
    for folder, sfx in suffix.items():
        for p in (DOCS / folder).glob("*.md"):
            if p.name != "README.md" and not p.name.endswith(sfx):
                bad.append(str(p))
    assert bad == []


def test_docs_artifacts_are_named_by_a_slug() -> None:
    """The file-naming rule of the docs README: lower-case words joined by `-`, at most 80 characters, and no spec
    carries a number; a decision record or research note numbered before the rule keeps its number as its id."""
    bad = []
    for folder in ("specs", "adr", "research"):
        for p in (DOCS / folder).glob("*.md"):
            stem = p.name.split(".", 1)[0]
            if p.name == "README.md":
                continue
            if len(p.name) > 80 or not re.fullmatch(r"[A-Za-z0-9]+(-[a-z0-9]+)*", stem):
                bad.append(p.name)
            elif folder == "specs" and re.match(r"\d", stem):
                bad.append(p.name)
    assert bad == []


def _cli_spec() -> str:
    return (DOCS / "specs" / "engine-cli.spec.md").read_text(encoding="utf-8")


def _verb_words(text: str) -> set[str]:
    """The verb words of CLI-B7's statement."""
    body = text.split("### CLI-B7 ", 1)[1].split("\n- ", 1)[0]
    return set(re.findall(r"`([a-z][a-z-]*)`", body))


def test_reserved_verbs_match_the_verb_list() -> None:  # CLI-AC3
    from tempergraph.cli.main import VERBS

    assert _verb_words(_cli_spec()) == set(VERBS)


def test_every_built_option_is_documented() -> None:  # CLI-AC7: options drift
    import argparse

    from tempergraph.cli.main import _parser

    text = "".join(p.read_text(encoding="utf-8") for p in sorted((DOCS / "specs").glob("*.spec.md")))
    missing: list[str] = []
    seen = 0

    def walk(parser: argparse.ArgumentParser, name: str) -> None:
        nonlocal seen
        for act in parser._actions:
            if isinstance(act, argparse._SubParsersAction):
                for verb, child in act.choices.items():
                    walk(child, f"{name} {verb}".strip())
            for opt in act.option_strings:
                if opt.startswith("--") and opt != "--help":
                    seen += 1
                    if opt not in text:
                        missing.append(f"{name} {opt}")

    walk(_parser(), "")
    assert seen > 50 and missing == []
