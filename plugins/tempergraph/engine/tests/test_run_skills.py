"""The run driver and project bootstrap skills (SHL-B5, SHL-AC1; T9.1).

The bootstrap helper is run in throwaway repositories and its status and the exact ignore-file bytes are
checked; the run driver's verbs and options are checked against the built CLI.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tempergraph.cli.main import COMMANDS, _parser

from .test_source_rules import SHIPPED_WORKFLOW_NAMES

SKILLS = Path(__file__).resolve().parents[2] / "skills"
HELPER = SKILLS / "bootstrap" / "scripts" / "ignore_rule.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q")
    return r


def helper(repo: Path) -> tuple[int, dict]:
    p = subprocess.run([sys.executable, "-I", str(HELPER), str(repo)], capture_output=True, text=True, check=False)
    return p.returncode, json.loads(p.stdout)


def test_adds_once_and_keeps_bytes(repo: Path) -> None:
    (repo / ".gitignore").write_bytes(b"node_modules/\r\ndist")  # CRLF, no final newline
    rc, out = helper(repo)
    assert rc == 0 and out["status"] == "added"
    assert (repo / ".gitignore").read_bytes() == (b"node_modules/\r\ndist\r\n# tempergraph run state (local only)\r\n"
                                                  b"/.tempergraph/\r\n")
    (repo / ".tempergraph").mkdir()
    (repo / ".tempergraph" / ".gitignore").write_text("*\n")
    before = (repo / ".gitignore").read_bytes()
    assert helper(repo)[1]["status"] == "already_ignored" and (repo / ".gitignore").read_bytes() == before


def test_inner_ignore_file_does_not_count(repo: Path) -> None:
    (repo / ".tempergraph").mkdir()
    (repo / ".tempergraph" / ".gitignore").write_text("*\n")
    rc, out = helper(repo)
    assert out["status"] == "added" and (repo / ".gitignore").read_text().endswith("/.tempergraph/\n")


def test_negation_stands_and_tracked_files_reported(repo: Path) -> None:
    (repo / ".tempergraph").mkdir()
    (repo / ".tempergraph" / "run.jsonl").write_text("{}\n")
    git(repo, "add", ".tempergraph/run.jsonl")
    (repo / ".gitignore").write_text("/.tempergraph/\n!/.tempergraph/\n")
    before = (repo / ".gitignore").read_bytes()
    rc, out = helper(repo)
    assert rc == 1 and out["status"] == "negated" and "/.tempergraph/" in out["paste"]
    assert (repo / ".gitignore").read_bytes() == before
    assert out["tracked"] == [".tempergraph/run.jsonl"] and out["untrack"].startswith("git rm -r --cached")
    assert git(repo, "diff", "--cached", "--name-only").strip() == ".tempergraph/run.jsonl"  # nothing staged


def test_not_a_repository(tmp_path: Path) -> None:
    rc, out = helper(tmp_path)
    assert rc == 1 and out["status"] == "not_a_repository" and not (tmp_path / ".gitignore").exists()


def skill_text(name: str) -> str:
    folder = SKILLS / name
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(folder.rglob("*.md")))


@pytest.mark.parametrize("name", ["run", "bootstrap"])
def test_skill_shape(name: str) -> None:  # SHL-B7, SHL-B8, SHL-B11: a core plus references read on demand
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    head = re.match(r"^---\nname: (\S+)\ndescription: (.+)\n---\n", text)
    assert head and head.group(1) == name and len(head.group(2)) <= 1024
    for ref in re.findall(r"\]\((references/[^)]+)\)", text):
        assert (SKILLS / name / ref).exists(), ref


def test_run_driver_names_built_verbs_and_options_only() -> None:  # SHL-AC1, SHL-B2
    text = skill_text("run")
    parser = _parser()
    sub = next(a for a in parser._actions if isinstance(getattr(a, "choices", None), dict))
    for verb, rest in re.findall(r"`tempergraph ([a-z-]+)([^`]*)`", text):
        assert verb in COMMANDS, verb
        opts = {o for a in sub.choices[verb]._actions for o in a.option_strings}  # type: ignore[attr-defined]
        for sub_name in sub.choices[verb]._actions:  # nested verbs (`outcome show`)
            if getattr(sub_name, "choices", None) and isinstance(sub_name.choices, dict):
                for p in sub_name.choices.values():
                    opts |= {o for a in p._actions for o in a.option_strings}
        for opt in re.findall(r"(--[a-z-]+)", rest):
            assert opt in opts, f"{verb} {opt}"
    assert "--relayed" in text and "never resume on your" in text.lower().replace("\n", " ")
    assert not [w for w in SHIPPED_WORKFLOW_NAMES if w in text]  # names no workflow of the repository
