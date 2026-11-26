"""The regeneration unit's declaration, its due rule, its call and its check (RGN-B3 and RGN-B4, RGN-B6 to RGN-B12,
RGN-B16), on scratch git repositories whose declared commands are small `python3` scripts. The file builds its own
repositories, so it passes alone."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext

ROOT = Path(__file__).resolve().parents[1]
load_package(ROOT)  # makes the package's module importable as `tgwf_temperspec`
regeneration = importlib.import_module("tgwf_temperspec.regeneration")
FILE = "tempergraph.regenerations.json"
TASK = "T"
GEN = ("import os, pathlib, sys\n"
       "pathlib.Path('out.txt').write_text(' '.join(sys.argv[1:]) + '|' + os.getcwd() + '\\n')\n")
SAME = "import pathlib\npathlib.Path('out.txt').write_text('same\\n')\n"
FAIL = ("import pathlib, sys\n"
        "pathlib.Path('made.txt').write_text('made\\n')\n"
        "sys.stderr.write('boom\\n')\nsys.exit(3)\n")
OTHER = "import pathlib\npathlib.Path('other-ran.txt').write_text('x')\n"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")


def _commit(repo: Path, subject: str, files: dict[str, str]) -> None:
    _write(repo, files)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", subject)


def _entry(name: str, command: str, inputs: list[str] | None = None, outputs: list[str] | None = None) -> dict[str, Any]:
    return {"name": name, "command": command, "inputs": inputs if inputs is not None else ["src"],
            "outputs": outputs if outputs is not None else ["out.txt"]}


def _declaration(*entries: dict[str, Any]) -> str:
    return json.dumps({"schema_version": 1, "regenerations": list(entries)})


def _repo(tmp_path: Path, declaration: str | None, extra: dict[str, str] | None = None, code: bool = True) -> Path:
    """A repository whose base commit holds the tools, whose prepare commit holds the declaration and whose code commit
    changes `src/a.py` (the run's change) unless `code` is false."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "start", {"tools/gen.py": GEN, "tools/same.py": SAME, "tools/fail.py": FAIL, "tools/other.py": OTHER,
                            "src/a.py": "a = 1\n", "out.txt": "old\n", **(extra or {})})
    _commit(repo, f"docs(temperspec): prepare for {TASK}", {FILE: declaration} if declaration is not None else {"n": "1"})
    if code:
        _commit(repo, f"feat(temperspec): code for {TASK}", {"src/a.py": "a = 2\n"})
    return repo


def _ctx(repo: Path) -> Any:
    return CheckContext(unit="regeneration", workdir=repo, request={"task_id": TASK})  # what a script's call is given


def _count(repo: Path) -> int:
    return int(_git(repo, "rev-list", "--count", "HEAD").strip())


def _status(repo: Path) -> str:
    return _git(repo, "status", "--porcelain")


# -- the declaration (RGN-B3, RGN-B4) -------------------------------------------------------------------------------


def test_rgn_ac3_a_declaration_of_two_regenerations_is_read_in_file_order(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _declaration(_entry("one", "python3 tools/gen.py", ["src"], ["out.txt"]),
                                        _entry("two", "make docs --quiet", ["docs", "x.json"], ["d/site.md"])))
    got = regeneration.load_declaration(repo)
    assert [r.name for r in got] == ["one", "two"]
    assert got[0].command == "python3 tools/gen.py" and list(got[0].inputs) == ["src"]
    assert list(got[0].outputs) == ["out.txt"]
    assert got[1].command == "make docs --quiet" and list(got[1].inputs) == ["docs", "x.json"]
    assert list(got[1].outputs) == ["d/site.md"]


@pytest.mark.parametrize("text", [
    "{not json",
    json.dumps({"schema_version": 2, "regenerations": []}),
    json.dumps({"schema_version": 1, "regenerations": [{"name": "a", "inputs": [], "outputs": []}]}),
])
def test_rgn_ac4_an_unusable_declaration_fails_the_check_environmentally_and_names_the_file(
        tmp_path: Path, text: str) -> None:
    repo = _repo(tmp_path, text)
    ctx = _ctx(repo)
    regeneration.regenerate(ctx)
    result = regeneration.regeneration_check(ctx)
    assert result.result == "FAIL" and result.environmental and FILE in result.evidence
    assert _status(repo) == ""


def test_rgn_ac4_a_repository_with_no_declaration_does_not_fail(tmp_path: Path) -> None:
    repo = _repo(tmp_path, None)
    ctx = _ctx(repo)
    regeneration.regenerate(ctx)
    assert regeneration.regeneration_check(ctx).result == "PASS"


# -- when a regeneration is due (RGN-B6, RGN-B7) --------------------------------------------------------------------


def _regs(*entries: dict[str, Any]) -> list[Any]:
    return [regeneration.Regeneration(name=e["name"], command=e["command"], inputs=tuple(e["inputs"]),
                                      outputs=tuple(e["outputs"])) for e in entries]


def test_rgn_ac6_a_regeneration_is_due_for_a_changed_input_and_not_for_another_path() -> None:
    folder = _regs(_entry("a", "x", ["plugins/a"], ["plugins/a/stamp.json"]))
    assert regeneration.due(folder, ["plugins/a/blueprint.json"]) == folder
    assert regeneration.due(folder, ["plugins/b/blueprint.json"]) == []
    assert regeneration.due(folder, ["plugins/ab/blueprint.json"]) == []
    file = _regs(_entry("f", "x", ["plugins/a/outcome.json"], ["o"]))
    assert regeneration.due(file, ["plugins/a/outcome.json"]) == file
    assert regeneration.due(file, ["plugins/a/outcome.json.bak"]) == []


def test_rgn_ac7_a_changed_output_alone_makes_nothing_due_and_an_input_beside_it_does() -> None:
    regs = _regs(_entry("a", "x", ["plugins/a"], ["plugins/a/stamp.json"]))
    assert regeneration.due(regs, ["plugins/a/stamp.json"]) == []
    assert regeneration.due(regs, ["plugins/a/stamp.json", "plugins/a/blueprint.json"]) == regs


# -- the call (RGN-B8 to RGN-B12, RGN-B16) --------------------------------------------------------------------------


@pytest.mark.parametrize("declaration, code", [
    (None, True),
    (_declaration(), True),
    (_declaration(_entry("a", "python3 tools/gen.py")), False),
])
def test_rgn_ac8_nothing_due_starts_nothing_changes_nothing_and_adds_no_commit(
        tmp_path: Path, declaration: str | None, code: bool) -> None:
    repo = _repo(tmp_path, declaration, code=code)
    before = _count(repo)
    regeneration.regenerate(_ctx(repo))
    assert (repo / "out.txt").read_text() == "old\n" and _count(repo) == before and _status(repo) == ""
    assert regeneration.regeneration_check(_ctx(repo)).result == "PASS"


def test_rgn_ac9_a_command_starts_with_its_words_as_a_list_and_no_shell_in_the_workspace(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _declaration(_entry("a", "python3 tools/gen.py --quiet docs")))
    regeneration.regenerate(_ctx(repo))
    words, _, where = (repo / "out.txt").read_text().strip().partition("|")
    assert Path(where).resolve() == repo.resolve()
    assert words == "--quiet docs"  # the arguments arrive as separate words


@pytest.mark.parametrize("command", ["python3 tools/gen.py && python3 tools/other.py", "/usr/bin/python3 tools/gen.py",
                                     "python3 ../gen.py"])
def test_rgn_ac10_a_command_with_a_shell_an_absolute_path_or_a_parent_path_is_refused(
        tmp_path: Path, command: str) -> None:
    repo = _repo(tmp_path, _declaration(_entry("a", command)))
    before = _count(repo)
    regeneration.regenerate(_ctx(repo))
    assert not (repo / "other-ran.txt").exists() and (repo / "out.txt").read_text() == "old\n"
    assert _count(repo) == before and _status(repo) == ""
    result = regeneration.regeneration_check(_ctx(repo))
    assert result.result == "FAIL" and result.environmental and command in result.evidence


def test_rgn_ac16_the_declaration_alone_names_the_commands(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _declaration(_entry("a", "python3 tools/gen.py")),
                 extra={"tempergraph.commands.json": json.dumps({"schema_version": 1,
                                                                  "commands": ["python3 tools/other.py"]})})
    regeneration.regenerate(_ctx(repo))
    assert (repo / "out.txt").read_text().startswith("|") and not (repo / "other-ran.txt").exists()
    bare = tmp_path / "bare"
    bare.mkdir()
    sub = _repo(bare, None, extra={"tempergraph.commands.json": json.dumps(
        {"schema_version": 1, "commands": ["python3 tools/gen.py"]})})
    regeneration.regenerate(_ctx(sub))
    assert (sub / "out.txt").read_text() == "old\n"


def test_rgn_ac11_a_passing_regeneration_leaves_one_commit_of_the_step_and_a_clean_tree(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _declaration(_entry("a", "python3 tools/gen.py")))
    before = _count(repo)
    got = regeneration.regenerate(_ctx(repo))
    assert _count(repo) == before + 1 and _status(repo) == ""
    assert _git(repo, "log", "-1", "--format=%s").strip() == f"docs(temperspec): regeneration for {TASK}"
    assert "out.txt" in _git(repo, "show", "--name-only", "--format=", "HEAD")
    assert "regeneration_report" in got
    assert regeneration.regeneration_check(_ctx(repo)).result == "PASS"


def test_rgn_ac11_a_regeneration_that_writes_the_same_bytes_adds_no_commit(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _declaration(_entry("a", "python3 tools/same.py")), extra={"out.txt": "same\n"})
    before = _count(repo)
    regeneration.regenerate(_ctx(repo))
    assert _count(repo) == before and _status(repo) == ""


def test_rgn_ac12_a_failed_pass_puts_every_written_file_back_and_commits_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _declaration(_entry("one", "python3 tools/gen.py"),
                                        _entry("two", "python3 tools/fail.py", ["src"], ["made.txt"])))
    before = _count(repo)
    regeneration.regenerate(_ctx(repo))
    assert (repo / "out.txt").read_text() == "old\n" and not (repo / "made.txt").exists()
    assert _count(repo) == before and _status(repo) == ""
    result = regeneration.regeneration_check(_ctx(repo))
    assert result.result == "FAIL" and not result.environmental
    assert len(result.findings) == 1 and "python3 tools/fail.py" in (result.findings[0].criterion or "")
    assert "3" in result.findings[0].message and "boom" in result.findings[0].message
