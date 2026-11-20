"""The intake inventory (AUT §2.3, §2.8; AUT-AC-2, AUT-B1)."""

from __future__ import annotations

import json
from pathlib import Path

from tempergraph.author.inventory import files, inventory

REPO = {
    "pyproject.toml": "[project]\nname = 'x'\n\n[tool.pytest.ini_options]\naddopts = '-q'\n\n[tool.ruff]\n"
                      "line-length = 100\n\n[tool.mypy]\nstrict = true\n",
    "package.json": json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}, "devDependencies": {"eslint": "9"}}),
    "Makefile": "test:\n\tpytest\nlint:\n\truff check .\n",
    ".github/workflows/ci.yml": "jobs:\n  t:\n    steps:\n      - run: pytest -q\n",
    "README.md": "# Tool\n\n## Commands\n\nRun `make test` before a pull request.\n",
    ".markdownlint.json": "{}",
    ".pre-commit-config.yaml": "repos:\n  - hooks:\n      - id: ruff\n      - id: mypy\n",
    "schemas/release.schema.json": json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema"}),
    "docs/openapi.yaml": "openapi: 3.1.0\ninfo:\n  title: x\n",
    "docs/checklist.md": "# Release checklist\n\n- [ ] Tag pushed\n- [ ] Notes published\n\n1. Notes must link "
                         "every change\n",
    ".github/pull_request_template.md": "## Summary\n\n- [ ] Tests added\n",
    "docs/dod.md": "# Definition of Done\n\nWork is done when reviewed.\n\n## Acceptance criteria\n\nGiven a tag\n"
                   "When notes run\nThen every change is listed\n",
    "CODEOWNERS": "* @owner-team\n",
    "docs/review.md": "# Code review guide\n\nReviewers check the changelog.\n",
    "templates/release-notes-template.md": "# Added\n\n# Changed\n\n# Fixed\n",
}

WANT = {"existing:test", "existing:linter", "existing:type_check", "existing:schema", "existing:checklist",
        "existing:acceptance_criteria", "existing:definition_of_done", "existing:review_rule", "existing:template"}


def _repo(root: Path) -> None:
    for rel, text in REPO.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def test_every_row_is_detected_and_no_text_is_recorded(tmp_path: Path) -> None:
    _repo(tmp_path)
    sources = [inventory(p, p.relative_to(tmp_path).as_posix(), f"s{i}", kind="reference", saved=False)
               for i, p in enumerate(files(tmp_path), 1)]
    kinds = {c.kind for s in sources for c in s.candidates}
    assert kinds >= WANT, WANT - kinds
    commands = {c.detail.get("command") for s in sources for c in s.candidates}
    assert {"pytest", "ruff", "mypy", "eslint", "markdownlint", "npm run test", "make test"} <= commands
    record = json.dumps({"sources": [s.to_json() for s in sources],
                         "candidates": [c.to_json() for s in sources for c in s.candidates]})
    for text in REPO.values():  # AUT-AC-2: no source line of any length worth a name is in the record
        for line in text.splitlines():
            line = line.strip(" -#*[]0123456789.")
            if len(line) > 12:
                assert line not in record, line


def test_examples_binaries_and_large_files(tmp_path: Path) -> None:
    good = tmp_path / "good.md"
    good.write_text("# Added\n")
    s = inventory(good, "good.md", "s1", kind="example_good", saved=True, artifact="notes")
    assert [c.kind for c in s.candidates] == ["fixture:must_pass"]
    assert s.locator == "saved:good.md" and s.private and s.to_json()["artifact"] == "notes"
    binary = tmp_path / "x.bin"
    binary.write_bytes(b"\0\1\2" * 10)
    assert inventory(binary, "x.bin", "s2", kind="reference", saved=False).kind == "other"
    big = tmp_path / "big.md"
    big.write_bytes(b"- [ ] x\n" * (5 * 1024 * 1024 // 8 + 1))
    b = inventory(big, "big.md", "s3", kind="reference", saved=False)
    assert b.kind == "other" and b.candidates == []


def test_from_a_solution(tmp_path: Path) -> None:
    """AUT-B1: a test command and a heading candidate from the script's test; the prompt's self-check is a
    claim, never a verification."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts/notes.sh").write_text("#!/bin/sh\nclaude -p \"$(cat prompts/notes.md)\" > notes.md\n")
    (tmp_path / "prompts/notes.md").write_text("Write release notes.\nCheck that you covered everything.\n")
    (tmp_path / "tests/test_notes.sh").write_text("#!/bin/sh\ngrep -q \"## Fixes\" notes.md\n")
    got = [inventory(tmp_path / r, r, f"s{i}", kind="solution", saved=False)
           for i, r in enumerate(("scripts/notes.sh", "prompts/notes.md", "tests/test_notes.sh"), 1)]
    kinds = [c.kind for s in got for c in s.candidates]
    assert "existing:test" in kinds and "existing:template" in kinds
    claim = [c for c in got[1].candidates if c.kind == "claim:self_check"]
    assert claim and claim[0].detail["lines"] == [2]
