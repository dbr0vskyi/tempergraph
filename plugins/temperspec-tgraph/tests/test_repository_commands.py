"""Task i58, RCM-B1 to RCM-B5: the checks and the code step take their verification commands from the repository's
`tempergraph.commands.json`. The file builds its own scratch repository, so it passes alone."""

from __future__ import annotations

import importlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, git_facts, run_check
from tempergraph.run.commands import expand
from tempergraph.run.outcome import outcome_unit

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
checks = importlib.import_module("tgwf_temperspec.checks")
fmt = importlib.import_module("tgwf_temperspec.specfmt")
OWNER = {key: unit for unit in SPEC.order for key in (SPEC.units[unit].step.produces if SPEC.units[unit].step else {})}
EVALS = ROOT / "evals" / "checks"
GIT_COMMANDS = ("git --version", "git status", "git diff", "git log", "git show")


def _copy(src: Path, dst: Path) -> list[Path]:
    out = []
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())
        out.append(target)
    return out


def _declare(root: Path, *commands: str) -> None:
    (root / "tempergraph.commands.json").write_text(json.dumps({"schema_version": 1, "commands": list(commands)}))


@pytest.fixture
def non_python(tmp_path: Path) -> Path:
    """A repository with a `package.json`, no Python project file and its own commands file."""
    root = tmp_path / "web-repo"
    root.mkdir()
    (root / "package.json").write_text('{"scripts": {"test": "vitest", "lint": "eslint ."}}\n')
    _declare(root, "npm test", "npm run lint")
    return root


def _context(unit: str, work: Path, artifacts: dict[str, dict[str, str]], values: dict[str, Any] | None = None,
             git: GitFacts | None = None) -> CheckContext:
    return CheckContext(unit=unit, workdir=work, request={}, artifacts=artifacts, values=values or {},
                        git=git or GitFacts(), allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                        deadline_at=time.monotonic() + 60)


def _artifacts(files: list[Path], work: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for f in files:
        if f.stem in OWNER:
            out.setdefault(OWNER[f.stem], {})[f.stem] = f.relative_to(work).as_posix()
    return out


def _plan_with(work: Path, command: str, fixture: str = "plan/must-pass/2-simple", name: str = "plan.md") -> list[Path]:
    files = _copy(EVALS / fixture, work)
    plan = work / name
    plan.write_text(plan.read_text().replace("`git --version`", f"`{command}`"))
    return files


def _plan_gate(work: Path, command: str) -> Any:
    files = _plan_with(work, command)
    res, _ = run_check(SPEC.units["plan"].gate, _context("plan", work, _artifacts(files, work)))
    return res


def _expand_gate(work: Path, command: str) -> Any:
    files = _plan_with(work, command, "expand/must-pass/1-expanded", "phases.md")
    res, _ = run_check(SPEC.units["expand"].gate, _context("expand", work, _artifacts(files, work)))
    return res


def _triage_gate(work: Path, command: str) -> Any:
    _copy(EVALS / "triage" / "must-pass" / "4-quick", work)
    note = work / "triage_note.md"
    note.write_text(note.read_text().replace("`git --version`", f"`{command}`"))
    ctx = _context("triage", work, {"triage": {"triage_note": "triage_note.md"}},
                   {"triage": {"route": "quick", "gaps": "none"}})
    res, _ = run_check(SPEC.units["triage"].gate, ctx)
    return res


def _statuses(res: Any, criterion: str) -> list[str]:
    return [f.status for f in res.findings if f.criterion == criterion]


def _told(res: Any, criterion: str) -> str:
    return " ".join(f"{f.message} {f.fix}" for f in res.findings if f.criterion == criterion and f.status == "fail")


def test_rcm_ac1_a_declared_command_is_accepted(non_python: Path, tmp_path: Path) -> None:
    """RCM-AC1 (RCM-B1)."""
    (non_python / "web").mkdir()
    for command in ("npm test -- --run", "cd web && npm run lint"):
        res = _plan_gate(non_python, command)
        assert _statuses(res, "ts-plan-form") == ["pass"], (command, res.evidence)
    res = _expand_gate(non_python, "npm test")
    assert _statuses(res, "ts-exp-commands") == ["pass"], res.evidence
    res = _triage_gate(non_python, "npm test")
    assert _statuses(res, "ts-tri-route") == ["pass"], res.evidence


def test_rcm_ac2_a_command_no_declaration_covers_is_refused(non_python: Path) -> None:
    """RCM-AC2 (RCM-B2)."""
    res = _plan_gate(non_python, "pytest")
    assert _statuses(res, "ts-plan-form") == ["fail"] and "tempergraph.commands.json" in _told(res, "ts-plan-form")
    res = _expand_gate(non_python, "pytest")
    assert _statuses(res, "ts-exp-commands") == ["fail"] and "tempergraph.commands.json" in _told(res, "ts-exp-commands")
    res = _triage_gate(non_python, "pytest")
    assert _statuses(res, "ts-tri-route") == ["fail"] and "tempergraph.commands.json" in _told(res, "ts-tri-route")
    root, base = _gate_repo(non_python.parent / "gate", "pytest", "exit 0\n")
    res, _ = run_check(SPEC.units["code"].gate, _gate_ctx(root, base))
    assert "fail" in _statuses(res, "ts-code-verify") and "tempergraph.commands.json" in _told(res, "ts-code-verify")


def test_rcm_ac2_without_a_file_or_with_an_invalid_one_the_refusal_names_the_file(tmp_path: Path) -> None:
    """RCM-AC2 (RCM-B2)."""
    bare = tmp_path / "bare"
    bare.mkdir()
    res = _plan_gate(bare, "make test")
    assert _statuses(res, "ts-plan-form") == ["fail"] and "tempergraph.commands.json" in _told(res, "ts-plan-form")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "tempergraph.commands.json").write_text("{not json")
    res = _plan_gate(broken, "make test")
    assert _statuses(res, "ts-plan-form") == ["fail"] and "tempergraph.commands.json" in _told(res, "ts-plan-form")


def test_rcm_ac3_read_only_git_is_accepted_in_every_repository(tmp_path: Path, non_python: Path) -> None:
    """RCM-AC3 (RCM-B3)."""
    bare = tmp_path / "bare"
    bare.mkdir()
    narrow = tmp_path / "narrow"
    narrow.mkdir()
    _declare(narrow, "npm test")
    for work in (bare, narrow):
        ctx = _context("plan", work, {})
        for command in ("git status", "git diff --stat", "git log -1"):
            assert checks._commands(ctx, fmt.Plan(commands=[command]), "ts-plan-form") == [], (work.name, command)
    root, base = _gate_repo(tmp_path / "gate", "git --version", "exit 0\n", declare=False)
    res, _ = run_check(SPEC.units["code"].gate, _gate_ctx(root, base))
    assert _statuses(res, "ts-code-verify") == ["pass"], res.evidence


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


DONE = EVALS / "code" / "must-pass" / "1-done"


def _gate_repo(root: Path, command: str, script: str, *, declare: bool = True, folder: str = "") -> tuple[Path, str]:
    """A repository with no Python project file whose base commit holds `check.sh` (in `folder`) as an exit 0 and
    whose head is the finished plan of the `1-done` fixture with `command`, and `script` as `check.sh`."""
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "package.json").write_text("{}\n")
    where = root / folder if folder else root
    where.mkdir(parents=True, exist_ok=True)
    (where / "check.sh").write_text("exit 0\n")
    if declare:
        _declare(root, "sh check.sh")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD").strip()
    for f in sorted(p for p in DONE.rglob("*") if p.is_file()):
        target = root / f.relative_to(DONE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.read_text().replace("`git --version`", f"`{command}`"))
    (where / "check.sh").write_text(script)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the code step")
    return root, base


def _gate_ctx(root: Path, base: str, unit: str = "code") -> CheckContext:
    artifacts: dict[str, dict[str, str]] = {}
    for f in sorted(p for p in DONE.rglob("*") if p.is_file()):
        if f.stem in OWNER:
            artifacts.setdefault(OWNER[f.stem], {})[f.stem] = f.relative_to(DONE).as_posix()
    ctx = CheckContext(unit=unit, workdir=root, request={}, artifacts=artifacts, git=git_facts(root, base),
                       allow=SPEC.allow_commands, values={"triage": {"route": "plan"}},
                       out_dir=root.parent / f"{root.name}.out", deadline_at=time.monotonic() + 120)
    return ctx


def test_rcm_ac4_the_code_gate_runs_a_declared_command(tmp_path: Path) -> None:
    """RCM-AC4 (RCM-B4): the exit code of the declared command decides `ts-code-verify`."""
    root, base = _gate_repo(tmp_path / "ok", "sh check.sh", "exit 0\n")
    res, _ = run_check(SPEC.units["code"].gate, _gate_ctx(root, base))
    assert _statuses(res, "ts-code-verify") == ["pass"], res.evidence
    assert "`sh check.sh`: run" in res.evidence
    root, base = _gate_repo(tmp_path / "bad", "sh check.sh", "exit 1\n")
    res, _ = run_check(SPEC.units["code"].gate, _gate_ctx(root, base))
    failed = [f for f in res.findings if f.criterion == "ts-code-verify" and f.status == "fail"]
    assert len(failed) == 1 and "sh check.sh" in failed[0].message and "exit 1" in failed[0].message, res.evidence


def test_rcm_ac4_a_command_in_a_folder_runs_there(tmp_path: Path) -> None:
    """RCM-AC4 (RCM-B4): `cd tools && sh check.sh` runs in `tools`."""
    script = 'case "$PWD" in */tools) exit 0;; *) exit 1;; esac\n'
    root, base = _gate_repo(tmp_path / "tools", "cd tools && sh check.sh", script, folder="tools")
    res, _ = run_check(SPEC.units["code"].gate, _gate_ctx(root, base))
    assert _statuses(res, "ts-code-verify") == ["pass"], res.evidence


def test_rcm_ac4_the_outcome_check_runs_a_declared_command(tmp_path: Path) -> None:
    """RCM-AC4 (RCM-B4): `ts-verify` passes for the passing script."""
    root, base = _gate_repo(tmp_path / "ok", "sh check.sh", "exit 0\n")
    ctx = _gate_ctx(root, base, "outcome")
    ctx.settings = {"deliverables": [], "outcome_check": SPEC.outcome.check.ref}  # type: ignore[union-attr]
    res, _ = run_check(outcome_unit(SPEC).gate, ctx)  # type: ignore[union-attr]
    assert _statuses(res, "ts-verify") == ["pass"], res.evidence


def test_rcm_ac5_the_code_step_commands_come_from_the_repository(tmp_path: Path, non_python: Path) -> None:
    """RCM-AC5 (RCM-B5)."""
    step = SPEC.units["code"].step
    assert step is not None
    got = expand(step.commands, non_python)
    assert set(got) == {"npm test", "npm run lint", *GIT_COMMANDS} and "pytest" not in got
    bare = tmp_path / "bare"
    bare.mkdir()
    assert set(expand(step.commands, bare)) == set(GIT_COMMANDS)
