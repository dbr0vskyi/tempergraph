"""Task i166e: the workflow removes the file of each marked removal row after the session (file-removal spec,
FRM-B1 to FRM-B6): the script `remove_marked` of the `after` list of the code step and of a phase. The file builds
its own scratch repositories."""

from __future__ import annotations

import importlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, run_check

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
removal = importlib.import_module("tgwf_temperspec.removal")
PLAN = "docs/plans/t.plan.md"
MARK = "✓ 2026-11-28"
FORBIDDEN = {"delete", "remove", "move", "rm", "mv", "git"}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


def _plan(rows: list[tuple[str, str, str]], unit_marks: bool = True) -> str:
    out = ["---\ntask: t\ncomplexity: simple\nstatus: in-progress\nspecs: []\n---\n", "# Plan: t\n",
           "## 2. Phases\n\n### Phase 1: part\n\nGoal: g.\nWeight: light\n",
           "| Row | Kind | Req | File | Proves | Change | Completed |", "|---|---|---|---|---|---|---|"]
    out += [f"| {i} | remove | R1 | `{f}` | | Remove it | {m} |" for i, f, m in rows]
    return "\n".join(out) + "\n"


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for rel, text in {"keep.txt": "k\n", **files}.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _put_plan(repo: Path, rows: list[tuple[str, str, str]], unit: str = "plan") -> None:
    (repo / PLAN).parent.mkdir(parents=True, exist_ok=True)
    (repo / PLAN).write_text(_plan(rows), encoding="utf-8")


def _ctx(repo: Path, unit: str = "code", artifacts: dict[str, Any] | None = None) -> Any:
    return CheckContext(unit=unit, workdir=repo, request={"task_id": "t"},
                        artifacts=artifacts if artifacts is not None else {"plan": {"plan": PLAN}})


def _report(repo: Path) -> list[dict[str, Any]]:
    return removal.refused(repo)


def test_frm_ac1_no_session_tool_deletes_or_moves_a_file_and_the_removal_comes_before_the_commit() -> None:
    # FRM-AC1, AC 2
    for unit in (SPEC.units["code"].step, SPEC.units["phase"].step):
        tools = set(unit.tools)
        assert {"read", "search", "list", "edit", "write", "shell"} <= tools
        assert not tools & FORBIDDEN
        names = [s.name for s in unit.after]
        assert names.index("removal") < names.index("commit")


def test_frm_ac3_a_marked_row_removes_its_file_and_an_unmarked_row_keeps_it(tmp_path: Path) -> None:
    # FRM-AC3, AC 2
    repo = _repo(tmp_path, {"src/old.py": "x\n", "src/other.py": "y\n"})
    _put_plan(repo, [("1.1", "src/old.py", MARK), ("1.2", "src/other.py", "")])
    assert removal.remove_marked(_ctx(repo)) == {}
    assert not (repo / "src/old.py").exists()
    assert (repo / "src/other.py").exists()
    assert _report(repo) == []


def test_frm_ac3_a_plan_with_no_removal_row_removes_nothing(tmp_path: Path) -> None:
    # FRM-AC3, AC 2
    repo = _repo(tmp_path, {"src/old.py": "x\n"})
    (repo / PLAN).parent.mkdir(parents=True)
    (repo / PLAN).write_text(_plan([]).replace("| remove |", "| code |"), encoding="utf-8")
    removal.remove_marked(_ctx(repo))
    assert (repo / "src/old.py").exists()


def test_frm_ac3_the_expanded_plan_is_read_when_the_run_has_one(tmp_path: Path) -> None:
    # FRM-AC3, AC 2
    repo = _repo(tmp_path, {"src/old.py": "x\n"})
    _put_plan(repo, [("1.1", "src/old.py", MARK)])
    removal.remove_marked(_ctx(repo, artifacts={"plan": {"plan": "missing.md"}, "expand": {"phases": PLAN}}))
    assert not (repo / "src/old.py").exists()


def test_frm_ac5_the_commit_holds_the_session_file_the_marks_and_the_deletion(tmp_path: Path) -> None:
    # FRM-AC5, AC 2
    routing = importlib.import_module("tgwf_temperspec.routing")
    repo = _repo(tmp_path, {"src/old.py": "x\n"})
    (repo / "src/new.py").write_text("n\n", encoding="utf-8")
    _put_plan(repo, [("1.1", "src/old.py", MARK)])
    ctx = _ctx(repo)
    removal.remove_marked(ctx)
    routing.commit_step(ctx)
    assert _git(repo, "status", "--porcelain") == ""
    shown = _git(repo, "show", "--name-status", "--format=", "HEAD").split("\n")
    assert "D\tsrc/old.py" in shown and "A\tsrc/new.py" in shown and f"A\t{PLAN}" in shown
    assert int(_git(repo, "rev-list", "--count", "HEAD").strip()) == 2


def test_frm_ac6_a_file_already_gone_passes_and_records_no_refusal(tmp_path: Path) -> None:
    # FRM-AC6, AC 2
    repo = _repo(tmp_path, {"src/old.py": "x\n"})
    _put_plan(repo, [("1.1", "src/old.py", MARK)])
    removal.remove_marked(_ctx(repo))
    assert removal.remove_marked(_ctx(repo)) == {}
    assert not (repo / "src/old.py").exists() and _report(repo) == []


def test_frm_ac3_the_script_starts_no_command_and_no_session(tmp_path: Path) -> None:
    # FRM-AC3, AC 2
    repo = _repo(tmp_path, {"src/old.py": "x\n"})
    _put_plan(repo, [("1.1", "src/old.py", MARK)])
    ctx = _ctx(repo)

    def boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("a command was started")

    ctx.run = boom
    removal.remove_marked(ctx)
    assert not (repo / "src/old.py").exists()


def test_frm_ac7_a_folder_is_refused_with_its_row_path_and_reason(tmp_path: Path) -> None:
    # FRM-AC7 (the script's part), AC 2
    repo = _repo(tmp_path, {"src/pkg/a.py": "x\n"})
    _put_plan(repo, [("1.1", "src/pkg", MARK)])
    assert removal.remove_marked(_ctx(repo)) == {}
    assert (repo / "src/pkg/a.py").exists()
    got = _report(repo)
    assert [(r["row"], r["path"]) for r in got] == [("1.1", "src/pkg")] and got[0]["reason"]
    assert json.loads((repo / ".tempergraph/removal/report.json").read_text())


def test_frm_ac7_a_path_outside_the_workspace_is_refused(tmp_path: Path) -> None:
    # FRM-AC7 (the script's part), AC 2
    repo = _repo(tmp_path, {})
    (tmp_path / "outside.txt").write_text("o\n", encoding="utf-8")
    _put_plan(repo, [("1.1", "../outside.txt", MARK)])
    removal.remove_marked(_ctx(repo))
    assert (tmp_path / "outside.txt").exists()
    got = _report(repo)
    assert [(r["row"], r["path"]) for r in got] == [("1.1", "../outside.txt")] and got[0]["reason"]


def test_frm_ac7_a_refusal_of_the_file_system_is_recorded_and_raises_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FRM-AC7 (the script's part), AC 2
    repo = _repo(tmp_path, {"src/old.py": "x\n"})
    _put_plan(repo, [("1.1", "src/old.py", MARK)])

    def refuse(self: Path, *a: Any, **k: Any) -> None:
        raise PermissionError("Operation not permitted")

    monkeypatch.setattr(Path, "unlink", refuse)
    assert removal.remove_marked(_ctx(repo)) == {}
    assert (repo / "src/old.py").exists()
    got = _report(repo)
    assert [(r["row"], r["path"]) for r in got] == [("1.1", "src/old.py")]
    assert "Operation not permitted" in got[0]["reason"]


# -- FRM-B6, FRM-B7: the gates read a removal -----------------------------------------------------------------

DONE = ROOT / "evals" / "checks" / "code" / "must-pass" / "1-done"
CHANGED = ("tests/test_config.py", "src/tool/config.py", "README.md")


def _gate_ctx(tmp_path: Path, unit: str, rows: list[tuple[str, str, str]], changed: tuple[str, ...] = CHANGED,
              refused: list[dict[str, str]] | None = None, preview: bool = False) -> Any:
    """The fixture of a finished code step, with a phase 5 of removal rows added."""
    for f in sorted(p for p in DONE.rglob("*") if p.is_file()):
        (tmp_path / f.relative_to(DONE)).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f.relative_to(DONE)).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    text = (tmp_path / "phases.md").read_text(encoding="utf-8")
    block = ("### Phase 5: Removal\n\nGoal: removal is in place.\nWeight: light\n\n"
             "| Row | Kind | Req | File | Proves | Change | Completed |\n|---|---|---|---|---|---|---|\n"
             + "".join(f"| {i} | remove | R1 | `{f}` | | Remove it | {m} |\n" for i, f, m in rows) + "\n")
    (tmp_path / "phases.md").write_text(text.replace("## 3. Verification", block + "## 3. Verification"),
                                        encoding="utf-8")
    if refused is not None:
        (tmp_path / ".tempergraph/removal").mkdir(parents=True)
        (tmp_path / ".tempergraph/removal/report.json").write_text(json.dumps({"refused": refused}), encoding="utf-8")
    artifacts = {"code": {"code_report": "code_report.md"}, "expand": {"phases": "phases.md"}}
    return CheckContext(unit=unit, workdir=tmp_path, request={}, artifacts=artifacts, item=None,
                        git=GitFacts(base="abc123", changed_paths=changed), values={"triage": {"route": "plan"}},
                        allow=SPEC.allow_commands, preview=preview,
                        out_dir=tmp_path.parent / f"{tmp_path.name}.out", deadline_at=time.monotonic() + 60)


def _findings(ctx: Any, criterion: str) -> list[Any]:
    res, _ = run_check(SPEC.units[ctx.unit].gate, ctx)
    return [f for f in res.findings if f.criterion == criterion]


@pytest.mark.parametrize(("unit", "criterion"), [("code", "ts-code-changed"), ("phase", "ts-phs-changed")])
def test_frm_ac7_a_refused_removal_is_an_environmental_finding_naming_the_path(
        tmp_path: Path, unit: str, criterion: str) -> None:
    # FRM-AC7 (the check side), AC 2, AC 3
    refused = [{"row": "5.1", "path": "src/pkg", "reason": "the path is a folder"}]
    ctx = _gate_ctx(tmp_path, unit, [("5.1", "src/pkg", MARK)], refused=refused)
    res, _ = run_check(SPEC.units[unit].gate, ctx)
    failing = [f for f in res.findings if f.criterion == criterion and f.status == "fail"]
    assert len(failing) == 1 and "src/pkg" in failing[0].message and "the path is a folder" in failing[0].message
    assert "row `5.1`" in failing[0].message and res.environmental is True


def test_frm_ac8_the_preview_fails_no_marked_removal_row_whose_file_is_still_there(tmp_path: Path) -> None:
    # FRM-AC8, AC 3
    (tmp_path / "src").mkdir()
    (tmp_path / "src/old.py").write_text("x\n", encoding="utf-8")
    rows = [("5.1", "src/old.py", MARK)]
    preview = _findings(_gate_ctx(tmp_path, "code", rows, preview=True), "ts-code-changed")
    assert [f for f in preview if f.status == "fail"] == []


def test_frm_ac8_the_gate_fails_a_marked_removal_row_whose_file_is_still_there(tmp_path: Path) -> None:
    # FRM-AC8, AC 3
    (tmp_path / "src").mkdir()
    (tmp_path / "src/old.py").write_text("x\n", encoding="utf-8")
    gate = _findings(_gate_ctx(tmp_path, "code", [("5.1", "src/old.py", MARK)]), "ts-code-changed")
    assert any(f.status == "fail" and "5.1" in f.message for f in gate)


def test_frm_ac8_the_gate_passes_a_removal_row_whose_file_is_gone_and_listed_as_changed(tmp_path: Path) -> None:
    # FRM-AC8, AC 3
    ctx = _gate_ctx(tmp_path, "code", [("5.1", "src/old.py", MARK)], changed=(*CHANGED, "src/old.py"))
    gate = _findings(ctx, "ts-code-changed")
    assert [f.status for f in gate] == ["pass"]
