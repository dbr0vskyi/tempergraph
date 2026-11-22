"""The CLI core verbs end to end on stand-ins (CLI-B1–B5, CLI-AC1, AC-3, AC-4; milestone M1)."""

from __future__ import annotations

import io
import json
import textwrap
from pathlib import Path
from typing import Any

import pytest

from tempergraph.catalog import Catalog, from_registry, resolve_request
from tempergraph.cli.main import VERBS, main
from tempergraph.constants import ExitCode
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import ScriptedExecutor, standin
from tempergraph.run.runner import RunSettings

from .conftest import hash_tree
from .fixtures.packages import package_parts
from .fixtures.workflows import two_step
from .test_run import DRAFT, REVIEW, judge, verdict_block


def settings(**kw: Any) -> RunSettings:
    return RunSettings(sleep=lambda s: None, **kw)


PERSON = ({}, True)  # a person at a plain terminal (PRV-B1)


def cli(repo: Path, ex: ScriptedExecutor | None, *argv: str, catalog: Catalog | None = None,
        signals: tuple[dict[str, str], bool] = PERSON) -> tuple[int, Any, str]:
    reg = Registry()
    if ex is not None:
        reg.register(ex)
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), catalog=catalog or Catalog(specs={"demo": two_step()}), registry=reg, cwd=repo,
                out=out, err=err, run_settings=settings, signals=signals)
    text = out.getvalue()
    try:
        doc = json.loads(text) if text.strip() else None
    except ValueError:
        doc = text
    return code, doc, err.getvalue()


def happy() -> ScriptedExecutor:
    return standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])


def test_m1_run_status_facts_wait(repo: Path) -> None:
    code, doc, err = cli(repo, happy(), "run", "demo", "Release", "1.2", "notes", "--task-id", "T-1", "--json")
    assert code == 0 and doc["thread_id"] == "demo/T-1", err
    code, st, _ = cli(repo, None, "status")
    assert code == 0 and st["threads"][0]["state"] == "finished" and st["schema_version"] == 1
    code, facts, _ = cli(repo, None, "facts", "demo/T-1")
    assert code == 0 and facts["state"] == "finished" and facts["exit_code"] == 0
    code, w, _ = cli(repo, None, "wait", "demo/T-1", "--timeout", "5")
    assert code == 0 and w["state"] == "finished"


def test_pause_exits_3_and_resume_finishes(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    code, _, err = cli(repo, ex, "run", "demo", "notes", "--task-id", "T-2")
    assert code == ExitCode.PAUSED and "tempergraph resume demo T-2" in err  # CLI-B4
    ex.steps, ex.judges = [REVIEW], [judge()]
    code, _, err = cli(repo, ex, "resume", "demo", "T-2", "--decision", "proceed")
    assert code == 0, err


def test_check_creates_nothing(repo: Path) -> None:
    before = hash_tree(repo)
    code, doc, _ = cli(repo, happy(), "run", "demo", "Release notes", "--check")
    assert code == 0 and doc["status"] == "ok" and doc["task_id"].startswith("t-")  # CLI-B1
    assert hash_tree(repo) == before
    code, doc, _ = cli(repo, happy(), "run", "demo", "--check")
    assert code == ExitCode.USAGE and doc["status"] == "needs" and doc["questions"][0]["name"] == "request"


def test_check_and_run_refuse_alike(repo: Path) -> None:
    no_judge = standin("antigravity")  # cannot restrict judge tools: preflight refuses (CLI-AC2)
    code, doc, _ = cli(repo, no_judge, "run", "demo", "x", "--check")
    assert code == ExitCode.USAGE and doc["status"] == "error" and doc["refusals"]
    code, _, err = cli(repo, no_judge, "run", "demo", "x")
    assert code == ExitCode.USAGE and err
    assert not (repo / ".tempergraph" / "runs").exists()


def test_same_request_same_thread() -> None:
    a = resolve_request(two_step(), ["Release", "notes"], {}, Path("."))
    b = resolve_request(two_step(), ["Release ", " notes"], {}, Path("."))
    assert a.task_id == b.task_id and a.inputs["request"] == "Release notes"


@pytest.mark.parametrize("argv", [["schedule"], ["run", "update", "x"], ["run", "demo", "status"], ["nope"],
                                  ["run", "missing", "x"], ["run", "demo", "x", "--bogus"]])
def test_usage_refusals_exit_2(repo: Path, argv: list[str]) -> None:
    code, _, err = cli(repo, happy(), *argv)
    assert code == ExitCode.USAGE and err  # CLI-AC3, CLI-B17, CLI-B18, CLI-B19


def test_read_only_verbs_leave_the_root_unchanged(repo: Path) -> None:
    cli(repo, happy(), "run", "demo", "notes", "--task-id", "T-3")
    before = hash_tree(repo / ".tempergraph")
    for argv in (["status"], ["list"], ["validate", "demo"], ["executors"], ["facts", "demo/T-3"],
                 ["graph", "demo"], ["graph", "demo", "--format", "json"], ["worktree", "list"]):
        code, _, err = cli(repo, happy(), *argv)
        assert code == 0, (argv, err)
    assert hash_tree(repo / ".tempergraph") == before  # CLI-AC1


def test_stop_needs_a_live_run(repo: Path) -> None:
    cli(repo, happy(), "run", "demo", "notes", "--task-id", "T-4")
    code, _, err = cli(repo, None, "stop", "demo/T-4")
    assert code == ExitCode.USAGE and "not running" in err


def test_executors_lists_live_facts_as_not_run(repo: Path) -> None:
    from tempergraph.executors.claude import ClaudeExecutor

    reg = Registry()
    reg.register(ClaudeExecutor())
    out = io.StringIO()
    assert main(["executors"], catalog=Catalog(), registry=reg, cwd=repo, out=out, err=io.StringIO()) == 0
    row = json.loads(out.getvalue())["executors"][0]
    assert row["name"] == "claude" and set(row["live_facts"].values()) == {"not run"}  # CLI-B3


def test_exit_codes_match_the_contract() -> None:
    con = (Path(__file__).resolve().parents[2] / "docs" / "specs" / "01-contracts.spec.md").read_text()
    for code in ExitCode:
        assert f"`{int(code)}`" in con  # CLI-AC4


def test_reserved_words_cover_every_spec_verb() -> None:
    spec = (Path(__file__).resolve().parents[2] / "docs" / "specs" / "17-engine-cli.spec.md").read_text()
    import re

    verbs = {m.group(1) for m in re.finditer(r"^\| `([a-z][a-z-]*)", spec, re.M)}
    assert verbs <= set(VERBS), verbs - set(VERBS)


def package(root: Path, name: str = "notes-flow") -> Path:
    pkg = root / name
    mod = name.replace("-", "_")
    (pkg / ".claude-plugin").mkdir(parents=True)
    (pkg / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": f"{name}-tgraph", "version": "0.2.0"}))
    (pkg / "tempergraph.json").write_text(json.dumps({"schema_version": 1, "name": name,
                                                      "entry": f"{mod}:workflow", "workflow_api": 1}))
    (pkg / "workflow" / mod).mkdir(parents=True)
    (pkg / "workflow" / mod / "__init__.py").write_text(textwrap.dedent('''
        from tempergraph.api import CheckResult, Criterion, Gate, Judge, Routing, Step, Workflow

        def draft_check(ctx):
            return CheckResult(result="PASS", evidence="ok")

        def workflow():
            return Workflow(order=["draft"], routing=Routing(description="Write notes"), issue_repository="acme/notes", units={
                "draft": Step(prompt="Write {request} into notes.md", tools=["read", "write"],
                              produces={"notes": "file"},
                              gate=Gate(check=draft_check, judge=Judge(stance="Verify."),
                                        criteria=[Criterion(id="c-file", text="notes.md exists")]))})
    '''))
    return package_parts(pkg, name, units=("draft",))


def test_registered_package_loads_and_runs(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    pkg = package(tmp_path / "pkgs")
    (home / "registry.json").write_text(json.dumps({"schema_version": 1, "workflows": [
        {"name": "notes-flow", "kind": "local", "path": str(pkg)},
        {"name": "gone", "kind": "local", "path": str(tmp_path / "missing")}]}))
    cat = from_registry(home)
    assert cat.specs["notes-flow"].version == "0.2.0" and cat.broken == {"gone": "manifest"}
    code, doc, _ = cli(repo, None, "list", catalog=cat)
    assert {r["name"]: r["state"] for r in doc["workflows"]} == {"notes-flow": "ok", "gone": "not_loaded"}
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("MET")), judge(verdict_block("MET"))])
    code, _, err = cli(repo, ex, "run", "notes-flow", "Release 1.2", "--task-id", "N-1", catalog=cat)
    assert code == 0, err  # the check ran in the worker, importing the package's own module
    code, _, err = cli(repo, ex, "run", "notes-flow-tgraph", "Release 1.2", "--task-id", "N-2", "--check",
                       catalog=cat)
    assert "unknown workflow" not in err  # the plugin name names the same workflow (ADR-0120)
    code, _, err = cli(repo, None, "run", "gone", "x", catalog=cat)
    assert code == ExitCode.INTERNAL and "not_loaded" in err


def test_pause_before_and_dry_run(repo: Path) -> None:  # ROP-B1 to ROP-B13, FLX-B10, FLX-B11
    for argv in (["--check"], []):
        code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "D-1", "--pause-before", "nowhere",
                           *argv)
        assert code == 2 and "breakpoint_unknown" in err
    assert not (repo / ".tempergraph" / "runs" / "demo" / "D-1").exists()
    ex = happy()
    code, doc, err = cli(repo, ex, "run", "demo", "notes", "--task-id", "D-1", "--pause-before", "draft", "--json")
    assert code == ExitCode.PAUSED and doc["reason"] == "breakpoint" and ex.calls == [], err
    code, _, err = cli(repo, ex, "resume", "demo", "D-1", "--decision", "proceed")
    assert code == 0, err
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "D-2", "--dry-run", "--auto-reopen", "1")
    assert code == 0, err
    log = (repo / ".tempergraph" / "runs" / "demo" / "D-2" / "run.jsonl").read_text().splitlines()
    started = [json.loads(x) for x in log if '"run_started"' in x][0]
    assert started["dry_run"] is True and "run.auto_reopen" in started["overridden_keys"]
