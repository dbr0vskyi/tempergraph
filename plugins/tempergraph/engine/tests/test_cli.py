"""The CLI core verbs end to end on stand-ins (CLI-B1–B5, CLI-AC1, AC-3, AC-4; milestone M1)."""

from __future__ import annotations

import io
import json
import textwrap
from pathlib import Path
from typing import Any

import pytest

import dataclasses
import subprocess

from tempergraph.catalog import Catalog, from_registry, resolve_request
from tempergraph.cli.main import VERBS, main
from tempergraph.constants import ExitCode
from tempergraph.contracts import InputDeclaration
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import ScriptedExecutor, standin
from tempergraph.run.runner import RunSettings

from .conftest import hash_tree
from .fixtures.packages import minimal_package, package_parts
from .fixtures.workflows import two_step
from .test_run import DRAFT, REVIEW, judge, records, verdict_block


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


def test_resume_dry_run_files_nothing_for_the_whole_thread(
        repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # ROP-AC12 (ROP-B14), task AC 9
    from tempergraph import detach
    from tempergraph.improve import child
    from tempergraph.improve.codehost import MemoryCodeHost
    from tempergraph.store.layout import home_path

    from .test_loop_child import judge_says

    monkeypatch.setenv("TEMPERGRAPH_LOOP", "detached")
    monkeypatch.setattr(detach, "start", lambda *a, **k: True)  # the child is drained below
    for verb in ("resume", "run"):
        capsys.readouterr()
        cli(repo, None, verb, "--help")
        assert "--dry-run" in capsys.readouterr().out, verb

    ex = standin("claude", steps=[DRAFT, DRAFT], judges=[judge(verdict_block("UNMET")),
                                                         judge(verdict_block("UNVERIFIABLE"))])
    code, _, err = cli(repo, ex, "run", "demo", "notes", "--task-id", "D-1")
    assert code == ExitCode.PAUSED, err
    ex.steps, ex.judges = [REVIEW], [judge(verdict_block("UNVERIFIABLE"))]
    code, _, err = cli(repo, ex, "resume", "demo", "D-1", "--decision", "proceed", "--dry-run")
    assert code == ExitCode.PAUSED, err  # a second pause: the hold must outlast this segment
    ex.steps, ex.judges = [REVIEW], [judge()]
    code, _, err = cli(repo, ex, "resume", "demo", "D-1", "--decision", "proceed")  # no --dry-run here
    assert code == 0, err
    tickets = sorted(child.tickets_dir(home_path()).glob("*.json"))
    assert tickets and json.loads(tickets[0].read_text())["dry_run"] is True
    for t in tickets:
        doc = json.loads(t.read_text())
        doc["issue_repository"] = "team/notes"
        t.write_text(json.dumps(doc))
    host = MemoryCodeHost(down=True)  # any call would raise
    outs = child.drain(registry=_loop_registry(judge_says(0.9)), host=lambda: host)
    assert "would_file" in {r["op"] for o in outs for r in o["results"]} and not host.issues
    assert not host.comments


def _loop_registry(reply: Any) -> Registry:
    reg = Registry()
    reg.register(standin("claude", judges=[reply]))
    return reg


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


def test_worktree_prune_records_its_caller_only_when_it_applies(repo: Path) -> None:  # WTR-AC6 (WTR-B27)
    cc = ({"CLAUDECODE": "1"}, False)  # an agent inside a Claude Code session
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "T-9")
    assert code == 0, err
    wt = Path(next(r for r in records(repo, "T-9") if r["kind"] == "workspace")["path"])
    code, doc, err = cli(repo, None, "worktree", "prune", "--finished")  # a listing: not a mutation
    assert code == 0, err
    assert [r["thread"] for r in doc["removable"]] == ["demo/T-9"] and "caller" not in doc and wt.exists()
    code, doc, err = cli(repo, None, "worktree", "list", "--all", "--json")
    assert code == 0 and [r["thread"] for r in doc["worktrees"]] == ["demo/T-9"], err
    code, doc, err = cli(repo, None, "worktree", "prune", "--finished", "--apply", "--caller", "agent", signals=cc)
    assert code == 0, err
    assert [r["result"] for r in doc["removed"]] == ["removed"] and not wt.exists()
    assert doc["caller"]["kind"] == "agent" and doc["caller"]["call_id"]
    code, doc, err = cli(repo, None, "worktree", "prune", "--apply")  # a person at a terminal, nothing left to remove
    assert code == 0 and doc["removed"] == [] and doc["caller"]["kind"] == "person"


def test_stop_needs_a_live_run(repo: Path) -> None:  # RCT-AC5
    from tempergraph.durability.control import stop_file
    from tempergraph.store.layout import state_root_path

    cli(repo, happy(), "run", "demo", "notes", "--task-id", "T-4")
    code, _, err = cli(repo, None, "stop", "demo/T-4")
    assert code == ExitCode.USAGE and "not running" in err
    assert not stop_file(state_root_path(repo), "demo", "T-4").exists()  # no request file is left


def test_executors_lists_live_facts_with_their_state(repo: Path) -> None:
    from tempergraph.executors.claude import ClaudeExecutor

    reg = Registry()
    reg.register(ClaudeExecutor())
    out = io.StringIO()
    assert main(["executors"], catalog=Catalog(), registry=reg, cwd=repo, out=out, err=io.StringIO()) == 0
    row = json.loads(out.getvalue())["executors"][0]
    facts = row["live_facts"]
    assert row["name"] == "claude" and set(facts.values()) == {"confirmed", "not run"}  # CLI-B3, AC 6
    assert facts["P-CC-13"] == "confirmed"
    assert all(facts[f"P-CC-{i}"] == "not run" for i in range(1, 13))


def test_exit_codes_match_the_contract() -> None:
    con = (Path(__file__).resolve().parents[2] / "docs" / "specs" / "contracts.spec.md").read_text()
    for code in ExitCode:
        assert f"`{int(code)}`" in con  # CLI-AC4


def test_reserved_words_cover_every_spec_verb() -> None:
    spec = (Path(__file__).resolve().parents[2] / "docs" / "specs" / "engine-cli.spec.md").read_text()
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
    assert "unknown workflow" not in err  # the plugin name names the same workflow (ADR `a-workflow-plugin-name-is-the-workflow-name-plus-tgraph`)
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


# CLI-AC12
_OVERLAP_OUTCOME: dict[str, Any] = {
    "schema_version": 1, "revision": 1,
    "statement": "Notes covering every requested change in the notes file.",
    "deliverables": [{"key": "notes", "kind": "file", "where": "the run's branch"}],
    "final": [
        {"id": "f1", "severity": "blocker", "verified_by": "judge",
         "text": "The notes cover every requested change accurately",
         "check_method": "Read notes and compare with request",
         "verifier": {"references": ["notes"], "scale": {
             "met": "every change covered", "partial": "most covered",
             "unmet": "a change missing", "evidence": "comparison"}}},
        {"id": "f2", "severity": "blocker", "verified_by": "judge",
         "text": "The notes include every requested change with accuracy",
         "check_method": "Read notes and compare with request",
         "verifier": {"references": ["notes"], "scale": {
             "met": "all changes included", "partial": "most included",
             "unmet": "a change missing", "evidence": "comparison"}}},
    ],
    "intermediate": {"draft": {"statement": "A draft of the notes", "criteria": [
        {"id": "d1", "severity": "blocker", "verified_by": "judge", "serves": ["f1"],
         "text": "The notes cover requested change",
         "check_method": "Read draft and request",
         "verifier": {"references": ["notes"], "scale": {
             "met": "covered", "partial": "partial",
             "unmet": "missing", "evidence": "diff"}}}
    ]}},
}


def test_authoring_warnings_aggregated_on_check_ok(repo: Path, tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:  # CLI-AC12
    home = tmp_path / "home"
    home.mkdir()
    pkg = minimal_package(tmp_path / "pkgs")
    (pkg / "outcome.json").write_text(json.dumps(_OVERLAP_OUTCOME))
    (home / "registry.json").write_text(json.dumps({"schema_version": 1, "workflows": [
        {"name": "release-notes", "kind": "local", "path": str(pkg)}]}))
    cat = from_registry(home)
    code, doc, _ = cli(repo, standin("claude"), "run", "release-notes", "v1.2", "--check", catalog=cat)
    assert code == 0 and doc["status"] == "ok"
    assert not any(w.get("code") == "criterion-overlap" for w in doc.get("warnings", []))
    aw = doc["authoring_warnings"]
    assert aw["counts"].get("criterion-overlap") == 2
    assert aw["command"] == "tempergraph validate release-notes"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_check_and_run_refuse_file_missing_at_base(repo: Path) -> None:  # CLI-AC13
    # Branch `b` exists and has README.md but not task.md; task.md is added on the current branch.
    _git(repo, "checkout", "-q", "-b", "b")
    _git(repo, "checkout", "-q", "main")
    task = repo / "task.md"
    task.write_text("do the thing\n")
    _git(repo, "add", "task.md")
    _git(repo, "commit", "-q", "-m", "add task")

    file_wf = dataclasses.replace(two_step(), input=InputDeclaration(kind="file"))
    cat = Catalog(specs={"demo": file_wf})
    args_check = ["run", "demo", str(task), "--check", "--worktree", "--worktree-base", "ref:b"]
    args_run = ["run", "demo", str(task), "--worktree", "--worktree-base", "ref:b"]

    code, doc, _ = cli(repo, happy(), *args_check, catalog=cat)
    assert code == ExitCode.USAGE and doc["status"] == "error"
    assert any(r["code"] == "request_missing_at_base" for r in doc.get("refusals", []))
    assert "task.md" in doc["refusals"][0]["message"] and "ref:b" in doc["refusals"][0]["message"]

    code2, out2, err2 = cli(repo, happy(), *args_run, catalog=cat)
    assert code2 == ExitCode.USAGE and err2
    assert "request_missing_at_base" in err2 or "task.md" in err2
