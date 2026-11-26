"""How a proposal's text growth is weighed (PTG-B1 to PTG-B3, PKG-B26; GitHub issue #229): the proposer may replace
or delete text, its judge weighs growth, the record and the pull request text carry each changed file's measures,
and a package's declared character budget refuses a change that takes a file above it."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tempergraph.executors.capabilities import DECLARED
from tempergraph.improve import proposals as prp
from tempergraph.model.validate import errors, validate
from tempergraph.package.loader import load
from tempergraph.package.manifest import read_manifest
from tempergraph.store.layout import state_root_path

from .fixtures.packages import minimal_package
from .test_proposals import CLUSTER, RULE, patch

PROMPT = ("Write release notes for {request} into notes.md.\n\nNever list a change twice.\n\n"
          "Never list a merge commit.\n")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _budget(root: Path, budgets: dict[str, int]) -> None:
    doc = json.loads((root / "tempergraph.json").read_text())
    doc["text_budgets"] = budgets
    (root / "tempergraph.json").write_text(json.dumps(doc, indent=2) + "\n")


@pytest.fixture
def pkg(repo: Path) -> Path:
    root = minimal_package(repo / "workflows")
    (root / "prompts" / "draft.md").write_text(PROMPT)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "package")
    return root


def _record(repo: Path, pkg: Path, edits: dict[str, str]) -> dict:
    return prp.record(state_root_path(repo), load(pkg), CLUSTER, patch(pkg, edits), author="proposer", rule=RULE)


def test_ptg_ac1_the_brief_allows_replacing_and_the_judge_weighs_growth() -> None:  # PTG-AC1 (PTG-B1)
    assert "replace, merge or delete sentences" in prp.PROPOSER_BRIEF
    assert "reason in half a" in prp.PROPOSER_BRIEF
    assert "replaces-before-adding" in {c.id for c in prp.JUDGE_CRITERIA}


def test_ptg_ac2_a_deletion_only_patch_is_drafted_classed_and_measured(repo: Path, pkg: Path) -> None:
    # PTG-AC2 (PTG-B2)
    rec = _record(repo, pkg, {"prompts/draft.md": PROMPT.replace("\n\nNever list a merge commit.\n", "\n")})
    assert rec["state"] == "drafted" and rec["classes"] == ["prompt"], rec
    m = rec["measures"]["prompts/draft.md"]
    assert m["before"]["prohibitions"] == 2 and m["after"]["prohibitions"] == 1
    assert m["after"]["chars"] < m["before"]["chars"]
    body = prp.report_body(rec, None)
    assert "`prompts/draft.md`" in body and "characters" in body and "per reason" in body


def test_pkg_ac9_a_file_over_its_budget_fails_validate(pkg: Path) -> None:  # PKG-AC9 (PKG-B26)
    _budget(pkg, {"prompts/*.md": 40})
    assert not isinstance(read_manifest(pkg), list)
    codes = {f.code for f in errors(validate(load(pkg), DECLARED))}
    assert "text-over-budget" in codes
    _budget(pkg, {"prompts/*.md": 4000})
    assert "text-over-budget" not in {f.code for f in errors(validate(load(pkg), DECLARED))}


def test_pkg_ac9_a_bad_budget_stops_the_manifest(pkg: Path) -> None:  # PKG-AC9 (PKG-B26)
    _budget(pkg, {"prompts/*.md": -1})
    got = read_manifest(pkg)
    assert isinstance(got, list) and any("text_budgets" in f.message for f in got)


def test_ptg_ac3_a_patch_that_takes_a_file_over_its_budget_is_refused_growth(repo: Path, pkg: Path) -> None:
    # PTG-AC3 (PTG-B3)
    _budget(pkg, {"prompts/draft.md": len(PROMPT) + 20})
    git(repo, "commit", "-qam", "budget")
    rec = _record(repo, pkg, {"prompts/draft.md": PROMPT + "Never name a person who reviewed the change.\n"})
    assert rec["state"] == "refused" and rec["refusal"] == "growth", rec
    assert rec["over_budget"][0]["file"] == "prompts/draft.md"
    rec = _record(repo, pkg, {"prompts/draft.md": PROMPT.replace("twice", "two times")})
    assert rec["state"] == "drafted", rec  # within the budget: today's behaviour


def test_ptg_ac3_without_a_budget_a_growing_patch_is_drafted(repo: Path, pkg: Path) -> None:  # PTG-AC3 (PTG-B3)
    rec = _record(repo, pkg, {"prompts/draft.md": PROMPT + "Never name a person who reviewed the change.\n" * 3})
    assert rec["state"] == "drafted", rec
