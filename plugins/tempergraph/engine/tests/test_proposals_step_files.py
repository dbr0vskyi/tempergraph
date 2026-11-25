"""Files a package declares its steps read at run time (`step_files`, PKG-B13): a proposal that changes one is a
producer change of class `standard` (PRP-B14, PRP-AC14), with the grading side refused `mixed_sides` (PRP-B1), its
added lines run through the literals check (PRP-B3), and an undeclared file still `no_change`; the prompt audit
reports a pattern that matches nothing and a prompt reference under a declared folder that does not resolve
(PRA-B7, PRA-AC6)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tempergraph.audit import audit
from tempergraph.improve import proposals as prp
from tempergraph.model.prompt_lint import lint
from tempergraph.package.loader import load
from tempergraph.package.manifest import read_manifest
from tempergraph.store.layout import state_root_path

from .fixtures.packages import minimal_package
from .test_audit import ctx
from .test_proposals import CLUSTER, RULE, outcome_with, patch

STANDARD = "# Notes standard\n\nEach entry names the change it describes.\n"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _declare(root: Path, patterns: list[str]) -> None:
    manifest = root / "tempergraph.json"
    doc = json.loads(manifest.read_text())
    doc["step_files"] = patterns
    manifest.write_text(json.dumps(doc, indent=2) + "\n")


@pytest.fixture
def pkg(repo: Path) -> Path:
    root = minimal_package(repo / "workflows")
    (root / "standards").mkdir()
    (root / "standards" / "notes.md").write_text(STANDARD)
    (root / "notes").mkdir()
    (root / "notes" / "undeclared.md").write_text(STANDARD)
    _declare(root, ["standards/*.md"])
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "package")
    return root


def _record(repo: Path, pkg: Path, edits: dict[str, str]) -> dict:
    return prp.record(state_root_path(repo), load(pkg), CLUSTER, patch(pkg, edits), author="proposer", rule=RULE)


def test_the_manifest_reads_step_files(pkg: Path) -> None:  # PKG-B13
    got = read_manifest(pkg)
    assert not isinstance(got, list) and got.step_files == ("standards/*.md",)


def test_a_bad_pattern_stops_the_manifest(pkg: Path) -> None:  # PKG-B13
    _declare(pkg, ["../outside.md"])
    got = read_manifest(pkg)
    assert isinstance(got, list) and any("step_files" in f.message for f in got)


def test_a_change_to_a_declared_file_is_a_producer_standard(repo: Path, pkg: Path) -> None:  # PRP-AC14, PRP-B14
    rec = _record(repo, pkg, {"standards/notes.md": STANDARD + "Each entry says what a reader can now do.\n"})
    assert rec["state"] == "drafted" and rec["classes"] == ["standard"] and rec["side"] == "producer", rec


def test_a_declared_file_and_its_grading_criterion_together_are_mixed(repo: Path, pkg: Path) -> None:
    # PRP-AC14, PRP-B1
    rec = _record(repo, pkg, {"standards/notes.md": STANDARD + "Each entry says what a reader can now do.\n",
                              "outcome.json": outcome_with(pkg, text="Every entry says what a reader can now do")})
    assert rec["state"] == "refused" and rec["refusal"] == "mixed_sides", rec


def test_a_literal_in_a_declared_file_is_refused(repo: Path, pkg: Path) -> None:  # PRP-AC14, PRP-B3
    rec = _record(repo, pkg, {"standards/notes.md": STANDARD + "Always handle the file /tmp/run-7/notes.md.\n"})
    assert rec["state"] == "refused" and rec["refusal"] == "literal", rec


def test_an_undeclared_file_is_still_no_change(repo: Path, pkg: Path) -> None:  # PRP-AC14, PRP-B14
    rec = _record(repo, pkg, {"notes/undeclared.md": STANDARD + "Each entry says what a reader can now do.\n"})
    assert rec["state"] == "refused" and rec["refusal"] == "no_change", rec


def test_a_pattern_that_matches_nothing_is_reported(pkg: Path, tmp_path: Path) -> None:  # PRA-AC6, PRA-B7
    _declare(pkg, ["standards/*.md", "rules/*.rule.md"])
    rep = audit(load(pkg), {"definition"}, ctx(tmp_path))
    hits = [f for f in rep.findings if f.rule == "step-file-missing"]
    assert len(hits) == 1 and "rules/*.rule.md" in hits[0].statement, [f.rule for f in rep.findings]


def test_a_prompt_reference_under_a_declared_folder_must_resolve(pkg: Path) -> None:  # PRA-AC6, PRA-B7
    prompt = pkg / "prompts" / "draft.md"
    prompt.write_text(prompt.read_text() + "\nFollow `standards/notes.md` and `standards/gone.md`.\n")
    missing = [f.message for f in lint(load(pkg)) if f.code == "lint-ref-missing"]
    assert any("standards/gone.md" in m for m in missing) and not any("standards/notes.md" in m for m in missing)
