"""Generated-table drift tests: CON §2.9 exit codes equal the engine constants (CON-AC-6, CLI-AC-4)."""

from __future__ import annotations

import re

from tempergraph.constants import ExitCode

from .conftest import DOCS


def test_exit_codes_match_contracts_spec() -> None:
    text = (DOCS / "specs" / "01-contracts.spec.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| `ExitCode` |"))
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


def _cli_spec() -> str:
    return (DOCS / "specs" / "17-engine-cli.spec.md").read_text(encoding="utf-8")


def _verb_rows(text: str) -> list[str]:
    body = text.split("## 2. Contract", 1)[1].split("### 2.1", 1)[0]
    return [ln.split(" | ")[0] for ln in body.splitlines() if ln.startswith("| `")]


def test_reserved_verbs_match_the_verb_table() -> None:  # CLI-AC-3, CLI §5
    from tempergraph.cli.main import VERBS

    documented = {re.match(r"[a-z-]+", span).group(0) for cell in _verb_rows(_cli_spec())  # type: ignore[union-attr]
                  for span in re.findall(r"`([a-z][^`]*)`", cell) if re.match(r"[a-z-]+", span)}
    assert documented == set(VERBS) - {"help"}


def test_every_built_option_is_documented() -> None:  # CLI §5: options drift
    import argparse

    from tempergraph.cli.main import _parser

    text = _cli_spec()
    rst = (DOCS / "specs" / "80-run-settings-and-overrides.spec.md").read_text(encoding="utf-8")
    prv = (DOCS / "specs" / "85-caller-provenance.spec.md").read_text(encoding="utf-8")
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
                    if opt not in text + rst + prv:
                        missing.append(f"{name} {opt}")

    walk(_parser(), "")
    assert seen > 50 and missing == []
