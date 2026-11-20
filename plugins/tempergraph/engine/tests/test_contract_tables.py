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
