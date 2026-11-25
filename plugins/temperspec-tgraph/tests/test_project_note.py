"""Task i67: prepare writes the project note from the repository's real layout (PNR-B1 to PNR-B6), and the documents
that say where prepare puts the rule files and where a step writes its notes say so (README, setup skill, prompts)."""

from __future__ import annotations

import importlib
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tempergraph.package.loader import load_package

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
routing = importlib.import_module("tgwf_temperspec.routing")
fmt = importlib.import_module("tgwf_temperspec.specfmt")
checks = importlib.import_module("tgwf_temperspec.checks")
RULES = sorted(p.name for p in (ROOT / "rules").glob("*.rule.md"))
OVERVIEW = "overview.spec.md"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch git repository with one commit; the machine holds no rule files."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "commit", "-q", "--allow-empty", "-m", "start")
    return root


def _put(repo: Path, *paths: str, text: str = "# x\n") -> None:
    for path in paths:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text, encoding="utf-8")


def _rules_in(base: Path, folder: str, names: list[str] | None = None) -> None:
    for name in names if names is not None else RULES:
        _put(base, f"{folder}/{name}", text=(ROOT / "rules" / name).read_text(encoding="utf-8"))


def _block(repo: Path) -> str:
    """What `write_context` leaves in the project-context file."""
    routing.write_context(repo)
    return next((repo / n).read_text(encoding="utf-8") for n in routing.CONTEXT_FILES if (repo / n).is_file())


def _prepare(repo: Path) -> str:
    ctx = SimpleNamespace(workdir=repo, unit="prepare", request={"task_id": "T"})
    routing.prepare(ctx)
    return next((repo / n).read_text(encoding="utf-8") for n in routing.CONTEXT_FILES if (repo / n).is_file())


def _named(text: str, *paths: str) -> bool:
    """Whether the text names each folder as a unit of its own (between backticks)."""
    return all(f"`{p}`" in text for p in paths)


# -- the specs folders and the folders beside them (PNR-B1, PNR-B2) -------------------------------------------


def test_the_block_names_the_folders_of_the_overview_specs(repo: Path) -> None:  # PNR-AC1, AC 1
    _put(repo, f"plugins/a/docs/specs/{OVERVIEW}", f"plugins/b/docs/specs/{OVERVIEW}", f"evals/c/docs/specs/{OVERVIEW}")
    block = _block(repo)
    assert _named(block, "plugins/a/docs/specs/", "plugins/b/docs/specs/")
    assert "evals/" not in block and not _named(block, "docs/specs/")


def test_without_an_overview_the_block_names_the_other_specs_and_else_the_default(repo: Path) -> None:  # PNR-AC2, AC 1
    _put(repo, "design/specs/x.spec.md")
    block = _block(repo)
    assert _named(block, "design/specs/") and not _named(block, "docs/specs/")
    empty = repo.parent / "empty"
    empty.mkdir()
    _git(empty, "init", "-q", "-b", "main")
    assert _named(_block(empty), "docs/specs/")


def test_the_block_names_the_four_folders_beside_each_specs_folder(repo: Path, tmp_path: Path) -> None:  # PNR-AC3, AC 1
    _put(repo, f"plugins/a/docs/specs/{OVERVIEW}", f"plugins/b/docs/specs/{OVERVIEW}")
    block = _block(repo)
    for part in ("a", "b"):
        assert _named(block, *(f"plugins/{part}/docs/{d}/" for d in ("adr", "research", "plans", "tasks")))
    assert not any((repo / "plugins" / p / "docs" / d).exists() for p in "ab" for d in ("adr", "plans"))
    bare = tmp_path / "bare"
    bare.mkdir()
    assert _named(_block(bare), "docs/adr/", "docs/research/", "docs/plans/", "docs/tasks/")


def test_the_specs_folders_come_in_path_order_with_no_cap(repo: Path) -> None:  # PNR-AC1, AC 1
    names = [f"plugins/p{n}/docs/specs/{OVERVIEW}" for n in (6, 3, 1, 5, 2, 4)]
    _put(repo, *names)
    block = _block(repo)
    folders = [f"plugins/p{n}/docs/specs/" for n in range(1, 7)]
    assert _named(block, *folders)
    assert [block.index(f"`{f}`") for f in folders] == sorted(block.index(f"`{f}`") for f in folders)
    assert routing.specs_folders(repo) == folders


# -- the rule files are copied only when nobody holds them (PNR-B3 to PNR-B5) ----------------------------------


def _installed(repo: Path) -> bool:
    return (repo / ".claude" / "rules" / "temperspec").exists() or (repo / fmt.TEMPLATE_DIR).exists()


def test_rule_files_held_in_a_folder_of_the_repository_are_not_copied(repo: Path) -> None:  # PNR-AC4, PNR-AC6, PNR-AC7, AC 2
    _rules_in(repo, "plugins/a/rules")
    block = _prepare(repo)
    assert not _installed(repo)
    assert _named(block, "plugins/a/rules/") and "docs/templates" not in block and ".claude/rules" not in block


def test_rule_files_only_the_machine_holds_are_copied_into_the_repository(repo: Path, tmp_path: Path) -> None:  # PNR-AC10, PNR-AC6, AC 1
    _rules_in(tmp_path / "home", ".claude/rules/temperspec")
    block = _prepare(repo)
    assert sorted(p.name for p in (repo / ".claude" / "rules" / "temperspec").iterdir()) == RULES
    assert (repo / fmt.TEMPLATE_DIR / "spec.template.md").is_file()
    assert _named(block, ".claude/rules/temperspec/", "docs/templates/")
    assert "~/.claude" not in block and "whole machine" not in block


def test_rule_files_the_repository_holds_are_not_copied_though_the_machine_holds_them(
        repo: Path, tmp_path: Path) -> None:  # PNR-AC4, PNR-AC6, AC 1
    _rules_in(tmp_path / "home", ".claude/rules/temperspec")
    _rules_in(repo, ".claude/rules/temperspec", ["spec.rule.md"])
    own = _prepare(repo)
    assert sorted(p.name for p in (repo / ".claude" / "rules" / "temperspec").iterdir()) == ["spec.rule.md"]
    assert not (repo / fmt.TEMPLATE_DIR).exists()
    assert _named(own, ".claude/rules/temperspec/") and "~/.claude" not in own and "whole machine" not in own
    folder = repo.parent / "folder"
    folder.mkdir()
    _git(folder, "init", "-q", "-b", "main")
    _git(folder, "commit", "-q", "--allow-empty", "-m", "start")
    _rules_in(folder, "plugins/a/rules")
    block = _prepare(folder)
    assert not _installed(folder)
    assert _named(block, "plugins/a/rules/") and "~/.claude" not in block and "whole machine" not in block


def test_the_repositorys_own_rule_folder_wins_over_another_folder(repo: Path) -> None:  # PNR-AC4, PNR-AC6, AC 2
    _rules_in(repo, "plugins/a/rules")
    _rules_in(repo, ".claude/rules/temperspec", ["spec.rule.md"])
    block = _prepare(repo)
    assert sorted(p.name for p in (repo / ".claude" / "rules" / "temperspec").iterdir()) == ["spec.rule.md"]
    assert not (repo / fmt.TEMPLATE_DIR).exists()
    assert _named(block, ".claude/rules/temperspec/") and not _named(block, "plugins/a/rules/")


@pytest.mark.parametrize("folder", ["fixtures/rules", "evals/rules"])
def test_a_copy_of_the_rule_files_in_a_skipped_folder_does_not_count(repo: Path, folder: str) -> None:  # PNR-AC5, AC 2
    _rules_in(repo, folder)
    block = _prepare(repo)
    assert sorted(p.name for p in (repo / ".claude" / "rules" / "temperspec").iterdir()) == RULES
    assert _named(block, ".claude/rules/temperspec/") and not _named(block, f"{folder}/")


def test_only_some_of_the_rule_files_installs_every_rule_file(repo: Path) -> None:  # PNR-AC5, PNR-AC6, PNR-AC7, AC 2
    _rules_in(repo, "plugins/a/rules", ["spec.rule.md"])
    block = _prepare(repo)
    assert sorted(p.name for p in (repo / ".claude" / "rules" / "temperspec").iterdir()) == RULES
    assert (repo / fmt.TEMPLATE_DIR / "spec.template.md").is_file()
    assert _named(block, ".claude/rules/temperspec/", "docs/templates/") and not _named(block, "plugins/a/rules/")


def test_no_rule_file_anywhere_installs_every_rule_file_and_the_templates(repo: Path) -> None:  # PNR-AC5, PNR-AC6, PNR-AC7, AC 2
    block = _prepare(repo)
    assert sorted(p.name for p in (repo / ".claude" / "rules" / "temperspec").iterdir()) == RULES
    assert sorted(p.name for p in (repo / fmt.TEMPLATE_DIR).iterdir()) == sorted(
        n for r in RULES for n in fmt.rule_templates(r.split(".")[0], (ROOT / "rules" / r).read_text(encoding="utf-8")))
    assert _named(block, ".claude/rules/temperspec/", "docs/templates/")


def test_install_rules_alone_writes_the_same_files(repo: Path) -> None:  # PNR-AC5, AC 2
    routing.install_rules(SimpleNamespace(workdir=repo, unit="prepare", request={}))
    assert sorted(p.name for p in (repo / ".claude" / "rules" / "temperspec").iterdir()) == RULES
    assert (repo / fmt.TEMPLATE_DIR).is_dir()
    held = repo.parent / "held"
    held.mkdir()
    _rules_in(held, "docs/rules")
    routing.install_rules(SimpleNamespace(workdir=held, unit="prepare", request={}))
    assert not (held / ".claude").exists()
    _rules_in(repo.parent / "home", ".claude/rules/temperspec")  # the machine holds them too: still nothing copied
    routing.install_rules(SimpleNamespace(workdir=held, unit="prepare", request={}))
    assert not (held / ".claude").exists() and not (held / fmt.TEMPLATE_DIR).exists()


# -- a file that already says where specs live is left alone (PNR-B6) ------------------------------------------


def _commit_file(repo: Path, name: str, text: str) -> None:
    _put(repo, name, text=text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"add {name}")


def test_a_file_that_names_the_specs_folder_is_left_alone_and_uncommitted(repo: Path) -> None:  # PNR-AC8, AC 3
    text = "# Project\n\nDocs live in `plugins/a/docs/{specs,adr,research}/`.\n"
    _put(repo, f"plugins/a/docs/specs/{OVERVIEW}")
    _commit_file(repo, "CLAUDE.md", text)
    _prepare(repo)
    assert (repo / "CLAUDE.md").read_bytes() == text.encode()
    assert fmt.CONTEXT_START not in (repo / "CLAUDE.md").read_text()
    assert _git(repo, "log", "--format=%s", "--", "CLAUDE.md").split("\n")[:-1] == ["add CLAUDE.md"]


@pytest.mark.parametrize("said", ["Specs: `plugins/a/docs/specs/`.", "Everything is under `plugins/a/docs/`."])
def test_the_whole_path_of_the_folder_or_the_folder_that_holds_it_counts(repo: Path, said: str) -> None:  # PNR-AC8, AC 3
    text = f"# Project\n\n{said}\n"
    _put(repo, f"plugins/a/docs/specs/{OVERVIEW}", "CLAUDE.md", text=text)
    _prepare(repo)
    assert (repo / "CLAUDE.md").read_text() == text


def test_a_path_that_only_contains_the_folder_name_does_not_count(repo: Path) -> None:  # PNR-AC9, AC 3
    text = "# Project\n\nGuides are in `plugins/b/docs/guides/`.\n"
    _put(repo, f"docs/specs/{OVERVIEW}", "CLAUDE.md", text=text)
    got = _prepare(repo)
    assert got.startswith(text) and got.count(fmt.CONTEXT_START) == 1 and _named(got, "docs/specs/")


def test_a_file_that_names_only_the_repository_root_does_not_count(repo: Path) -> None:  # PNR-AC9, AC 3
    text = "# Project\n\nSee the repository root `./` and `.` for everything.\n"
    _put(repo, f"docs/specs/{OVERVIEW}", "CLAUDE.md", text=text)
    assert _prepare(repo).startswith(text + "\n") and fmt.CONTEXT_START in (repo / "CLAUDE.md").read_text()


def test_a_file_that_says_only_how_to_run_the_tests_gets_the_block_after_its_text(repo: Path) -> None:  # PNR-AC9, AC 3
    text = "# Project\n\nRun the tests with `pytest`.\n"
    _put(repo, "CLAUDE.md", text=text)
    got = _prepare(repo)
    assert got.startswith(text + "\n") and got.count(fmt.CONTEXT_START) == 1


def test_a_specs_folder_named_only_inside_an_earlier_block_is_replaced_in_place(repo: Path) -> None:  # PNR-AC9, AC 3
    old = f"{fmt.CONTEXT_START}\nSpecs are in `docs/specs/`. old text\n{fmt.CONTEXT_END}"
    text = f"# Project\n\n{old}\n\n## After\n"
    _put(repo, "design/specs/x.spec.md", "CLAUDE.md", text=text)
    got = _prepare(repo)
    assert "old text" not in got and got.startswith("# Project\n\n" + fmt.CONTEXT_START)
    assert got.endswith(f"{fmt.CONTEXT_END}\n\n## After\n") and got.count(fmt.CONTEXT_START) == 1
    assert _named(got, "design/specs/")


def test_agents_md_is_read_the_same_when_it_is_the_file_the_repository_has(repo: Path) -> None:  # PNR-AC8, AC 3
    text = "# Agents\n\nSpecs: `plugins/a/docs/specs/`.\n"
    _put(repo, f"plugins/a/docs/specs/{OVERVIEW}", "AGENTS.md", text=text)
    routing.write_context(repo)
    assert (repo / "AGENTS.md").read_text() == text and not (repo / "CLAUDE.md").exists()
    _put(repo, "AGENTS.md", text="# Agents\n\nnothing\n")
    routing.write_context(repo)
    assert fmt.CONTEXT_START in (repo / "AGENTS.md").read_text() and not (repo / "CLAUDE.md").exists()


def test_the_block_keeps_the_rules_of_the_method(repo: Path) -> None:  # PNR-AC9, AC 3
    block = _block(repo)
    for kept in ("the task's acceptance criteria, then specs and decision records, then the plan",
                 "carries the criterion's id", 'tempergraph run temperspec "<the task and its acceptance criteria>"',
                 "belongs to its own part"):
        assert " ".join(kept.split()) in " ".join(block.split()), kept
    assert re.search(rf"^{re.escape(fmt.CONTEXT_START)}\n## temperspec\n", block)


# -- the documents that say where prepare puts the rule files and where a step writes its notes ----------------

PROMPTS = ("triage", "discovery", "discovery_short", "plan", "setup", "expand", "code")
NOTES = ("triage", "discovery", "discovery_short", "plan", "setup", "code")


def _words(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


@pytest.mark.parametrize("name", PROMPTS)
def test_each_prompt_says_where_the_rule_files_are(name: str) -> None:  # SRC-AC4, AC 1, AC 2, AC 3
    text = _words(ROOT / "prompts" / f"{name}.md")
    assert "`.claude/rules/temperspec/` of this repository" in text
    assert "project note in `claude.md` or `agents.md` names" in text
    assert "whole machine" not in text and "already in your instructions" not in text


@pytest.mark.parametrize("name", NOTES)
def test_a_prompt_that_names_a_notes_folder_defers_to_the_project_note(name: str) -> None:  # AC 1, AC 2, AC 3
    text = _words(ROOT / "prompts" / f"{name}.md")
    assert "beside the repository's specs, as the project note names it" in text, name
    assert "docs/" in text, name  # the folder written stays as the default


def test_the_phrases_the_prompt_checks_read_are_still_in_their_prompts() -> None:  # AC 1, AC 2, AC 3
    for key in checks.PROMPT_SAYS:
        assert all(f.status == "pass" for f in checks._prompt_says(key)), key


@pytest.mark.parametrize("path", [ROOT / "README.md", ROOT / "skills" / "setup" / "SKILL.md"])
def test_the_readme_and_the_setup_skill_state_what_prepare_does(path: Path) -> None:  # AC 1, AC 2, AC 3
    text = _words(path)
    assert "holds all seven rule files" in text
    assert "already names" in text and "unchanged" in text
    assert "tempergraph.commands.json" in text  # AC 4: prepare also writes the commands file of a Python repository


def test_the_documents_say_where_the_verification_commands_come_from() -> None:  # AC 4
    readme = _words(ROOT / "README.md")
    assert "`verify`" not in readme and "one fixed list" not in readme
    limits =readme.split("limits of this version", 1)[1].split(" - no release step", 1)[0]
    for said in ("`tempergraph.commands.json`", "read-only `git`", "`cd <folder> && <command>`"):
        assert said in limits, said
    assert "fixed list" not in _words(ROOT / "docs" / "specs" / OVERVIEW)
    for path in (ROOT / "prompts" / "code.md", ROOT / "prompts" / "plan.md", ROOT / "prompts" / "expand.md",
                 ROOT / "judges" / "code.md"):
        assert "tempergraph.commands.json" in _words(path), path.name
