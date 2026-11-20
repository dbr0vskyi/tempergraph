"""Workflow packages (PKG-AC-1 to AC-7, PKG-B2 to B7, B9): loading, rules, digests and the docs check."""

from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.registry import default_registry
from tempergraph.model.validate import Finding, validate
from tempergraph.package import importer
from tempergraph.package.inventory import package_files
from tempergraph.package.loader import LoadedPackage, PackageNotLoaded, load, load_package
from tempergraph.package.manifest import read_manifest
from tempergraph.run import checks as checkmod
from tempergraph.run.check_worker import run_in_worker

from .fixtures.packages import CHECKS, DECLARATION, minimal_package, write

try:
    import tempergraph.run.outcome as _outcome  # noqa: F401  # plan T5.8.1

    OUTCOME_READER = hasattr(_outcome, "read_outcome")
except ImportError:
    OUTCOME_READER = False


def caps() -> dict[str, Any]:
    reg = default_registry()
    return {n: reg.get(n).capabilities() for n in reg.available()}


def codes(fs: list[Finding], severity: str | None = None) -> set[str]:
    return {f.code for f in fs if severity is None or f.severity == severity}


def not_loaded(path: Path, **kw: Any) -> PackageNotLoaded:
    with pytest.raises(PackageNotLoaded) as info:
        load_package(path, **kw)
    return info.value


@pytest.fixture
def pkg(tmp_path: Path) -> Path:
    return minimal_package(tmp_path / "p", inline_criteria=True)


# -- PKG-AC-1 the minimal package --------------------------------------------------------------------


def test_minimal_package_loads_validates_compiles_and_runs(pkg: Path, repo: Path) -> None:
    from tempergraph.executors.standins import standin

    from .test_run import DRAFT, NO_SLEEP, judge, registry, verdict_block

    lp = load_package(pkg)
    spec = lp.spec
    assert (spec.name, spec.version, spec.package_root) == ("release-notes", "0.1.0", pkg.resolve())
    assert spec.units["draft"].gate.check is not None
    assert spec.units["draft"].gate.check.module == "tgwf_release_notes.checks"
    assert codes(validate(spec, caps()), "error") == set()
    from tempergraph.run.runner import start

    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("MET", "MET"))])
    out = start(spec, "R-1", {"request": "v1.2"}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    step = next(c for c in ex.calls if c.kind == "step")
    assert step.request.plugin_dir == pkg.resolve()  # PKG §2.6: step sessions get the plugin
    assert "Write release notes for v1.2" in step.request.prompt  # text("prompts/draft.md")


@pytest.mark.xfail(not OUTCOME_READER, strict=True, reason="PKG §2.3 step 5 waits on OUT's reader (plan T5.8.1)")
def test_minimal_package_gates_take_criteria_from_outcome(tmp_path: Path) -> None:
    spec = load(minimal_package(tmp_path))
    assert {c.id for c in spec.units["draft"].gate.criteria} == {"rn-sections", "rn-faithful"}
    assert codes(validate(spec, caps()), "error") == set()


def test_minimal_package_without_outcome_reader_is_pending(tmp_path: Path) -> None:
    lp = load_package(minimal_package(tmp_path))
    assert lp.outcome_pending is not OUTCOME_READER


@pytest.mark.skipif(shutil.which("claude") is None, reason="needs the claude CLI (model-free validate)")
def test_minimal_package_passes_claude_plugin_validate(pkg: Path) -> None:
    got = subprocess.run(["claude", "plugin", "validate", "--strict", str(pkg)], capture_output=True, text=True, timeout=120)
    assert got.returncode == 0, got.stdout + got.stderr


# -- PKG-AC-2 every refusal has its own code ----------------------------------------------------------


@pytest.mark.parametrize(("part", "code"), [
    ("hooks/hooks.json", "plugin-hooks"), (".mcp.json", "plugin-mcp"), ("bin/run.sh", "plugin-bin"),
    (".lsp.json", "plugin-session-settings"), ("CLAUDE.md", "plugin-instruction-file"),
    ("AGENTS.md", "plugin-instruction-file"),
])
def test_refused_plugin_parts(pkg: Path, part: str, code: str) -> None:
    write(pkg, part, "{}")
    found = validate(load(pkg), caps())
    assert code in codes(found, "error")
    if code == "plugin-hooks":
        assert "tempergraph hooks add" in next(f.message for f in found if f.code == code)  # PKG-B5


@pytest.mark.parametrize("key", ["hooks", "mcpServers", "lspServers"])
def test_refused_manifest_keys(pkg: Path, key: str) -> None:
    plugin = json.loads((pkg / ".claude-plugin/plugin.json").read_text())
    write(pkg, ".claude-plugin/plugin.json", {**plugin, key: {}})
    assert codes(validate(load(pkg), caps()), "error") & {"plugin-hooks", "plugin-mcp", "plugin-session-settings"}


def test_settings_with_agent_refused(pkg: Path) -> None:
    write(pkg, "settings.json", {"agent": "x"})
    assert "plugin-session-settings" in codes(validate(load(pkg), caps()), "error")


@pytest.mark.parametrize(("mutate", "reason"), [
    (lambda p: (p / "tempergraph.json").unlink(), "manifest"),
    (lambda p: write(p, ".claude-plugin/plugin.json", {"name": "other", "version": "0.1.0"}), "manifest"),
    (lambda p: write(p, "tempergraph.json", {"schema_version": 2, "name": "release-notes",
                                             "entry": "release_notes:workflow", "workflow_api": 1}), "manifest"),
    (lambda p: write(p, "tempergraph.json", {"schema_version": 1, "name": "release-notes",
                                             "entry": "release_notes", "workflow_api": 1}), "manifest"),
    (lambda p: write(p, "workflow/release_notes/__init__.py", "import nonexistent_module_xyz\n"), "import"),
    (lambda p: write(p, "workflow/release_notes/__init__.py", "def workflow():\n    raise ValueError('x')\n"),
     "build"),
    (lambda p: write(p, "workflow/release_notes/__init__.py", "def workflow():\n    return 42\n"), "build"),
    (lambda p: write(p, "workflow/release_notes/__init__.py", "def other():\n    pass\n"), "build"),
    (lambda p: shutil.rmtree(p / "workflow/release_notes"), "build"),
    (lambda p: write(p, "workflow/pyproject.toml",
                     '[project]\nname = "tgwf-release-notes"\ndependencies = ["evil @ https://x.invalid/e.whl"]\n'),
     "dependency_refused"),
    (lambda p: write(p, "workflow/pyproject.toml",
                     '[project]\nname = "tgwf-release-notes"\ndependencies = ["tempergraph>=1"]\n'),
     "dependency_refused"),
])
def test_load_failures(pkg: Path, mutate: Any, reason: str) -> None:
    mutate(pkg)
    assert not_loaded(pkg).reason == reason


def test_private_engine_import_is_refused_before_import(pkg: Path, tmp_path: Path) -> None:
    """PKG-B4: the scan names file and line, and the module never ran."""
    marker = tmp_path / "ran"
    write(pkg, "workflow/release_notes/checks.py", textwrap.dedent(f'''
        import pathlib
        pathlib.Path({str(marker)!r}).write_text("ran")
        from tempergraph.compiler import compile_workflow
    ''') + textwrap.dedent(CHECKS))
    exc = not_loaded(pkg)
    assert exc.reason == "private-engine-import"
    assert "workflow/release_notes/checks.py:4" in exc.detail
    assert not marker.exists()


def test_own_module_absolute_import_refused(pkg: Path) -> None:
    write(pkg, "workflow/release_notes/__init__.py",
          textwrap.dedent(DECLARATION).replace("from .checks", "from release_notes.checks"))
    assert not_loaded(pkg).reason == "own-module-absolute-import"


def test_undeclared_import_warns(pkg: Path) -> None:
    write(pkg, "workflow/release_notes/extra.py", "import yaml_not_declared_pkg\n")
    found = validate(load(pkg), caps())
    assert "undeclared-import" in codes(found, "warning")


def test_text_ref_outside_or_missing(pkg: Path) -> None:
    (pkg / "prompts/draft.md").unlink()
    assert "text-ref" in codes(validate(load(pkg), caps()), "error")
    decl = (pkg / "workflow/release_notes/__init__.py").read_text().replace('"prompts/draft.md"', '"../x.md"')
    write(pkg, "workflow/release_notes/__init__.py", decl)
    found = [f for f in validate(load(pkg), caps()) if f.code == "text-ref"]
    assert any("outside the package" in f.message for f in found)


def test_pyproject_name_and_missing_files(pkg: Path) -> None:
    write(pkg, "workflow/pyproject.toml", '[project]\nname = "notes"\ndependencies = []\n')
    (pkg / "README.md").unlink()
    (pkg / "outcome.json").unlink()
    found = validate(load(pkg), caps())
    assert {"pyproject-name", "outcome-missing"} <= codes(found, "error")
    assert "package-file-missing" in codes(found, "warning")
    (pkg / "workflow/pyproject.toml").unlink()
    assert "pyproject-missing" in codes(validate(load(pkg), caps()), "error")


def test_callable_not_module_level(pkg: Path) -> None:
    decl = textwrap.dedent(DECLARATION).replace("check=draft_check", "check=lambda ctx: None")
    write(pkg, "workflow/release_notes/__init__.py", decl)
    exc = not_loaded(pkg)
    assert exc.reason == "build" and "callable-not-importable" in exc.detail


def test_skill_not_in_package(pkg: Path) -> None:
    decl = (pkg / "workflow/release_notes/__init__.py").read_text().replace(
        'tools=["read", "write"]', 'tools=["read", "write", "skill:release-notes:style"]')
    write(pkg, "workflow/release_notes/__init__.py", decl)
    assert "skill-not-installed" in codes(validate(load(pkg), caps()), "error")
    write(pkg, "skills/style/SKILL.md", "---\nname: style\ndescription: House style\n---\nWrite plainly.\n")
    assert "skill-not-installed" not in codes(validate(load(pkg), caps()))


# -- PKG-B6 interface levels ---------------------------------------------------------------------------


@pytest.mark.parametrize(("level", "reason"), [(3, None), (2, None), (1, "workflow_api_retired"),
                                                (4, "workflow_api_newer")])
def test_interface_levels(pkg: Path, level: int, reason: str | None) -> None:
    m = json.loads((pkg / "tempergraph.json").read_text())
    write(pkg, "tempergraph.json", {**m, "workflow_api": level})
    if reason is None:
        assert load_package(pkg, engine_api=3, loads_from=2).spec.name == "release-notes"
    else:
        exc = not_loaded(pkg, engine_api=3, loads_from=2)
        assert exc.reason == reason
        assert ("update" if level == 4 else "upgrade") in exc.remedy


# -- PKG-AC-3 / PKG-B3 two packages with the same module names ----------------------------------------


def _other_checks(word: str) -> str:
    return textwrap.dedent(f'''
        from tempergraph.api import CheckResult

        WORD = "{word}"


        def draft_check(ctx):
            return CheckResult(result="PASS", evidence=WORD)
    ''')


def test_two_packages_same_module_names(tmp_path: Path, repo: Path) -> None:
    a = load_package(minimal_package(tmp_path / "a", "notes-a", checks=_other_checks("from-a"), inline_criteria=True))
    b = load_package(minimal_package(tmp_path / "b", "notes-b", checks=_other_checks("from-b"), inline_criteria=True))
    ga, gb = a.spec.units["draft"].gate, b.spec.units["draft"].gate
    assert ga.check is not None and gb.check is not None
    assert (ga.check.module, gb.check.module) == ("tgwf_notes_a.checks", "tgwf_notes_b.checks")
    ctx = checkmod.CheckContext(unit="draft", workdir=repo, request={})
    in_process = [dataclasses.replace(g.check, func=None).resolve()(ctx).evidence for g in (ga, gb)]
    assert in_process == ["from-a", "from-b"]
    # the same in one check worker process each, importing by reference through the private-name map
    assert [run_in_worker(g, ctx)[0].evidence for g in (ga, gb)] == ["from-a", "from-b"]


def test_reload_after_new_version_drops_old_modules(tmp_path: Path) -> None:
    a = load_package(minimal_package(tmp_path / "v1", checks=_other_checks("v1"), inline_criteria=True))
    b = load_package(minimal_package(tmp_path / "v2", checks=_other_checks("v2"), inline_criteria=True))
    assert importer.mapping()["tgwf_release_notes"].startswith(str((tmp_path / "v2").resolve()))
    ctx = checkmod.CheckContext(unit="draft", workdir=tmp_path, request={})
    for lp, want in ((b, "v2"),):
        g = lp.spec.units["draft"].gate
        assert g.check is not None
        assert dataclasses.replace(g.check, func=None).resolve()(ctx).evidence == want
    assert a.root != b.root


# -- PKG-AC-4 / PKG-B2 builders -------------------------------------------------------------------------


@pytest.mark.parametrize(("arg", "word"), [('version="0.3.0"', "version"), ('name="x"', "name"),
                                            ("colour=1", "colour")])
def test_builder_refuses_unknown_name_and_version(pkg: Path, arg: str, word: str) -> None:
    decl = (pkg / "workflow/release_notes/__init__.py").read_text().replace(
        'issue_repository="acme/release-notes",', f'issue_repository="acme/release-notes", {arg},')
    write(pkg, "workflow/release_notes/__init__.py", decl)
    exc = not_loaded(pkg)
    assert exc.reason == "build" and "TypeError" in exc.detail and word in exc.detail


def test_name_and_version_come_from_manifests(tmp_path: Path) -> None:
    spec = load(minimal_package(tmp_path, "notes-x", "2.4.1", inline_criteria=True))
    assert (spec.name, spec.version) == ("notes-x", "2.4.1")
    m = read_manifest(tmp_path / "notes-x")
    assert not isinstance(m, list) and m.name == "notes-x" and m.entry == "notes_x:workflow"


# -- PKG-AC-5 judges never load the plugin ----------------------------------------------------------------


def test_judge_sessions_never_get_the_plugin(pkg: Path, repo: Path) -> None:
    from tempergraph.executors.claude import judge_argv
    from tempergraph.executors.standins import standin
    from tempergraph.run.runner import start

    from .test_run import DRAFT, NO_SLEEP, judge, registry, verdict_block

    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("MET", "MET"))])
    start(load(pkg), "R-2", {"request": "v1.2"}, repo, registry(ex), NO_SLEEP)
    judges = [c for c in ex.calls if c.kind != "step"]
    assert judges and all(c.request.plugin_dir is None for c in judges)
    from tempergraph.contracts import ViewSet

    for isolated in (True, False):
        argv = judge_argv(ViewSet(), None, isolated=isolated)
        assert "--plugin-dir" not in argv and ("--bare" in argv or "--setting-sources" in argv)


# -- PKG-AC-6 / PKG-B9 the docs check ------------------------------------------------------------------------


def drift(pkg: Path, mode: str = "dev") -> list[Finding]:
    from tempergraph.package.docs_check import docs_check

    return [f for f in docs_check(load(pkg), pkg, mode) if f.code == "docs-drift"]  # type: ignore[arg-type]


def test_docs_check_passes_on_the_minimal_package(pkg: Path) -> None:
    assert drift(pkg) == []


@pytest.mark.parametrize("case", ["unit-without-spec", "missing-id", "unknown-id", "changed-text", "bad-link"])
def test_docs_check_fails(pkg: Path, case: str) -> None:
    spec_file = pkg / "docs/specs/01-draft.spec.md"
    text = spec_file.read_text()
    if case == "unit-without-spec":
        spec_file.unlink()
    elif case == "missing-id":
        spec_file.write_text(text.replace("- [ ] rn-faithful Every entry matches what its merged change did\n", ""))
    elif case == "unknown-id":
        spec_file.write_text(text + "- [ ] rn-ghost Something nobody declared\n")
    elif case == "changed-text":
        outcome = json.loads((pkg / "outcome.json").read_text())
        outcome["intermediate"]["draft"]["criteria"][1]["text"] = "Every entry is faithful"
        write(pkg, "outcome.json", outcome)
    else:
        spec_file.write_text(text.replace("(00-overview.spec.md)", "(99-gone.spec.md)"))
    found = drift(pkg)
    assert found and all(f.severity == "warning" for f in found)
    assert all(f.severity == "error" for f in drift(pkg, "stable"))


def test_docs_drift_is_a_validation_warning(pkg: Path) -> None:
    (pkg / "docs/specs/01-draft.spec.md").unlink()
    found = validate(load(pkg), caps())
    assert "docs-drift" in codes(found, "warning") and "docs-drift" not in codes(found, "error")


# -- PKG-AC-7 the content digest ---------------------------------------------------------------------------------


def _digest(pkg: Path) -> str:
    lp: LoadedPackage = load_package(pkg)
    return lp.content_digest


@pytest.mark.parametrize(("rel", "content", "changes"), [
    ("outcome.json", None, True), ("prompts/draft.md", "Other prompt {request}\n", True),
    ("judges/draft.md", "# Stance\n\nStrict.\n\n# Brief\n\nRead.\n", True),
    ("skills/style/SKILL.md", "---\nname: style\ndescription: s\n---\nx\n", True),
    ("agents/helper.md", "---\nname: helper\ndescription: h\n---\nHelp.\n", True),
    ("lessons/draft.json", {"schema_version": 1, "lessons": []}, True),
    ("workflow/release_notes/util.py", "X = 1\n", True),
    ("workflow/pyproject.toml", '[project]\nname = "tgwf-release-notes"\ndependencies = ["rich>=13"]\n', True),
    ("docs/specs/01-draft.spec.md", "changed\n", False), ("diagram/workflow.md", "changed\n", False),
    ("evals/cases.json", {"schema_version": 1, "cases": []}, False), ("authoring.json", {"x": 1}, False),
    ("README.md", "changed\n", False), ("tests/test_more.py", "X = 2\n", False),
])
def test_content_digest(pkg: Path, rel: str, content: Any, changes: bool) -> None:
    before = _digest(pkg)
    if content is None:
        doc = json.loads((pkg / rel).read_text())
        doc["statement"] = "A different statement."
        content = doc
    write(pkg, rel, content)
    assert (_digest(pkg) != before) is changes


def test_pyproject_metadata_outside_dependencies_does_not_change_digest(pkg: Path) -> None:
    before = _digest(pkg)
    write(pkg, "workflow/pyproject.toml", '[project]\nname = "tgwf-release-notes"\ndescription = "d"\n'
          'requires-python = ">=3.12"\ndependencies = []\n')
    assert _digest(pkg) == before


def test_workflow_version_and_inventory(pkg: Path) -> None:
    lp = load_package(pkg)
    assert lp.workflow_version == f"0.1.0+{lp.content_digest[:12]}"
    inv = package_files(pkg)
    assert "prompts/draft.md" in inv.content and "workflow/release_notes/checks.py" in inv.python
    assert "docs/specs/01-draft.spec.md" in inv.docs and "README.md" in inv.other
    docs_before = lp.docs_digest
    write(pkg, "docs/specs/01-draft.spec.md", "changed\n")
    assert load_package(pkg).docs_digest != docs_before
