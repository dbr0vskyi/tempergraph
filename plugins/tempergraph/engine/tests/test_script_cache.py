"""The per-thread script cache (SCR-B9, SCR-B3, SCR-B7, SCR-B2; SCR-AC4).

The scripts here are module-level callables that record each real run in `RUNS`, so a hit shows as a script
record with `cached: true` and no new entry in `RUNS`. A scripted judge reply is a function of the request: it
reads and edits the workspace between two visits of the script unit, in the test's own process.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate, Routing, Script, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.standins import standin
from tempergraph.run import scriptcache
from tempergraph.run.runner import start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named, two_step
from .test_run import DRAFT, MET, NO_SLEEP, REVIEW, judge, registry, verdict_block

NOT_SURE = verdict_block("UNVERIFIABLE")

RUNS: list[str] = []
SEEN: list[bool] = []
THREAD: dict[str, Path] = {}
BREAK_CACHE: list[bool] = []


@pytest.fixture(autouse=True)
def _reset() -> None:
    RUNS.clear()
    SEEN.clear()
    THREAD.clear()
    BREAK_CACHE.clear()


def build_script(ctx: Any) -> dict[str, str]:
    RUNS.append("build")
    if BREAK_CACHE and len(RUNS) == 1:  # `cache` becomes a file where the folder belongs
        folder = THREAD["dir"] / "cache"
        folder.parent.mkdir(parents=True, exist_ok=True)
        folder.write_text("not a folder", encoding="utf-8")
    (ctx.workdir / "notes.md").write_text("notes from " + (ctx.workdir / "src.txt").read_text(), encoding="utf-8")
    return {"notes": "notes.md"}


def empty_script(ctx: Any) -> dict[str, str]:
    RUNS.append("empty")
    return {}


def before_script(ctx: Any) -> dict[str, str]:
    RUNS.append("before")
    return {}


def after_script(ctx: Any) -> dict[str, str]:
    RUNS.append("after")
    return {}


def change_input(workdir: Path) -> None:
    (workdir / "src.txt").write_text("changed\n", encoding="utf-8")


def delete_output(workdir: Path) -> None:
    (workdir / "notes.md").unlink()


def reply(text: str, edit: Callable[[Path], None] | None = None) -> Callable[[SessionRequest], SessionResult]:
    """A scripted judge reply that notes whether the script's file is there, then edits the workspace."""

    def run(req: SessionRequest) -> SessionResult:
        SEEN.append((req.workdir / "notes.md").exists())
        if edit is not None:
            edit(req.workdir)
        return judge(text)

    return run


def control(workdir: Path) -> Path:
    """Where a test steers the author check, which runs in a worker process: next to the repository."""
    return workdir.parent / "control"


def steer(repo: Path, *modes: str) -> None:
    folder = control(repo)
    folder.mkdir(exist_ok=True)
    (folder / "mode").write_text(",".join(modes), encoding="utf-8")


def seen(repo: Path) -> list[bool]:
    """Whether the script's file was in the workspace at each call of the check, in order."""
    files = sorted(control(repo).glob("seen-*"), key=lambda p: int(p.name.split("-")[1]))
    return [p.read_text(encoding="utf-8") == "True" for p in files]


def steered_check(ctx: Any) -> Any:
    """The author check of the script unit: it runs on every visit, restored or not (SCR-B9). On its first call
    it does what `mode` says: `retry` fails the attempt, `change` edits a tracked input, `delete` removes the
    script's file."""
    from tempergraph.contracts import CheckFinding, CheckResult

    folder = control(ctx.workdir)
    folder.mkdir(exist_ok=True)
    n = len(list(folder.glob("call-*")))
    (folder / f"call-{n}").write_text("", encoding="utf-8")
    (folder / f"seen-{n}").write_text(str((ctx.workdir / "notes.md").exists()), encoding="utf-8")
    modes = (folder / "mode").read_text(encoding="utf-8").split(",") if (folder / "mode").exists() else []
    failed = False
    if n == 0:
        if "change" in modes:
            (ctx.workdir / "src.txt").write_text("changed\n", encoding="utf-8")
        if "delete" in modes:
            (ctx.workdir / "notes.md").unlink()
        failed = "retry" in modes
    if failed:
        return CheckResult(result="FAIL", evidence="again", findings=[
            CheckFinding(status="fail", criterion="c-file", place="notes.md", fix="again")])
    return CheckResult(result="PASS", evidence="ok", findings=[CheckFinding(status="pass", criterion="c-file")])


def checked_gate(**kw: Any) -> Gate:
    return Gate(check=steered_check, criteria=[crit("c-file")], **kw)


def cached_script(**kw: Any) -> Any:
    fields: dict[str, Any] = {"call": build_script, "produces": {"notes": "file"}, "inputs": ["src.txt"],
                              "side_effects": "none", "cache": "thread", "gate": checked_gate()}
    fields.update(kw)
    return Script(**fields)


def seeded(repo: Path) -> Path:
    (repo / "src.txt").write_text("source\n", encoding="utf-8")
    subprocess.run(["git", "add", "src.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "src"], cwd=repo, check=True, capture_output=True)
    return repo


def script_only(**kw: Any) -> Any:
    return named(Workflow(order=["build"], units={"build": cached_script(**kw)}, issue_repository="acme/x",
                          routing=Routing(description="Build notes"), allow_commands=["git status", "sleep"]))


def build_then_review(**kw: Any) -> Any:
    review = two_step().units["review"]
    review = dataclasses.replace(review, gate=dataclasses.replace(review.gate, back_targets=("build",)))
    kw.setdefault("gate", Gate(criteria=[crit("c-file")]))
    return named(Workflow(order=["build", "review"], units={"build": cached_script(**kw), "review": review},
                          issue_repository="acme/x", routing=Routing(description="Build and review"),
                          allow_commands=["git status"]))


def run_flow(repo: Path, spec: Any, ex: Any, task: str = "T-1") -> Any:
    THREAD["dir"] = run_dir(state_root_path(repo), spec.name, task)
    return start(spec, task, {"request": "notes"}, repo, registry(ex), dataclasses.replace(NO_SLEEP))


def scripts(repo: Path, task: str = "T-1", unit: str | None = None) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    recs = [json.loads(ln) for ln in p.read_text().splitlines()]
    return [r for r in recs if r["kind"] == "script" and (unit is None or r.get("unit") == unit)]


def cache_files(repo: Path, task: str = "T-1") -> list[Path]:
    folder = run_dir(state_root_path(repo), "demo", task) / "cache"
    return sorted(folder.rglob("*")) if folder.is_dir() else []


def test_scr_ac4_a_second_visit_with_the_same_inputs_restores_and_runs_nothing(repo: Path) -> None:
    seeded(repo)
    steer(repo, "retry")  # the first call of the gate's check fails the attempt: a RETRY of the unit
    out = run_flow(repo, script_only(), standin("claude"))
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert RUNS == ["build"]  # the second attempt ran nothing
    recs = scripts(repo, unit="build")
    assert [r["cached"] for r in recs] == [False, True] and all(r["phase"] == "unit" for r in recs)
    assert seen(repo) == [True, True]  # the unit's gate ran on the restored output too
    assert recs[1]["duration_s"] < 5


def test_scr_ac4_a_restore_brings_back_the_recorded_files(repo: Path) -> None:
    seeded(repo)
    steer(repo, "retry", "delete")  # the first call of the check deletes the file the script wrote
    assert run_flow(repo, script_only(), standin("claude")).exit_code is ExitCode.FINISHED
    assert RUNS == ["build"] and seen(repo) == [True, True]  # the file is back when the second call looks for it


def test_scr_ac4_a_changed_declared_input_is_a_miss(repo: Path) -> None:
    seeded(repo)
    steer(repo, "retry", "change")
    assert run_flow(repo, script_only(), standin("claude")).exit_code is ExitCode.FINISHED
    assert RUNS == ["build", "build"]
    assert [r["cached"] for r in scripts(repo, unit="build")] == [False, False]


def test_scr_ac4_the_key_covers_argv_arguments_workflow_and_each_input() -> None:
    def key(**kw: Any) -> str:
        fields: dict[str, Any] = {"argv": ("git",), "reference": None, "workflow": "v1", "arguments": ("status",),
                                  "inputs": {"src.txt": "d1"}}
        fields.update(kw)
        return scriptcache.key(**fields)

    base = key()
    assert key() == base
    assert key(arguments=("log",)) != base  # a changed argument
    assert key(argv=("hg",)) != base  # a changed resolved argv
    assert key(argv=(), reference="pkg.mod:fn") != base  # a callable reference
    assert key(workflow="v2") != base  # a changed workflow digest
    assert key(inputs={"src.txt": "d2"}) != base  # a changed input digest
    assert key(inputs={"other.txt": "d1"}) != base  # a different declared input


def test_scr_ac4_the_workspace_input_is_the_tree_of_tracked_and_untracked_files(repo: Path) -> None:
    seeded(repo)
    state_root = state_root_path(repo)
    first = scriptcache.tree_hash(repo, state_root)
    assert scriptcache.tree_hash(repo, state_root) == first
    (repo / "src.txt").write_text("edited\n", encoding="utf-8")  # a tracked file changes
    second = scriptcache.tree_hash(repo, state_root)
    assert second != first
    (repo / "fresh.txt").write_text("new\n", encoding="utf-8")  # an untracked file appears
    third = scriptcache.tree_hash(repo, state_root)
    assert third != second
    assert scriptcache.tree_hash(repo, state_root, exclude={"fresh.txt"}) == second
    (state_root / "runs").mkdir(parents=True, exist_ok=True)
    (state_root / "runs" / "noise.json").write_text("{}", encoding="utf-8")  # the state root is outside the tree
    assert scriptcache.tree_hash(repo, state_root) == third


def test_scr_ac4_a_workspace_input_change_between_visits_is_a_miss(repo: Path) -> None:
    seeded(repo)
    steer(repo, "retry", "change")  # src.txt is a tracked file of the tree
    out = run_flow(repo, script_only(inputs=["workspace"]), standin("claude"))
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert RUNS == ["build", "build"]


def test_scr_ac4_a_workspace_input_with_nothing_changed_is_a_hit(repo: Path) -> None:
    seeded(repo)
    steer(repo, "retry")
    assert run_flow(repo, script_only(inputs=["workspace"]), standin("claude")).exit_code is ExitCode.FINISHED
    assert RUNS == ["build"]  # the script's own output file is not part of its input


def test_scr_ac4_a_trip_back_restores_when_inputs_are_unchanged(repo: Path) -> None:  # SCR-B3
    seeded(repo)
    ex = standin("claude", steps=[REVIEW, REVIEW], judges=[reply(NOT_SURE), reply(MET)])
    assert run_flow(repo, build_then_review(), ex).exit_code is ExitCode.PAUSED
    out = back_to_build(repo, ex)  # the person sends the run back past the script unit
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert RUNS == ["build"]
    assert [r["cached"] for r in scripts(repo, unit="build")] == [False, True]


def back_to_build(repo: Path, ex: Any) -> Any:
    from tempergraph.run.runner import resume

    return resume(build_then_review(), "T-1", repo, registry(ex), decision="back:build", settings=NO_SLEEP)


def test_scr_ac4_a_trip_back_runs_the_script_again_when_an_input_changed(repo: Path) -> None:  # SCR-B3
    seeded(repo)
    ex = standin("claude", steps=[REVIEW, REVIEW], judges=[reply(NOT_SURE), reply(MET)])
    assert run_flow(repo, build_then_review(), ex).exit_code is ExitCode.PAUSED
    change_input(repo)  # one input file changed while the run waited
    out = back_to_build(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert RUNS == ["build", "build"]
    assert [r["cached"] for r in scripts(repo, unit="build")] == [False, False]


def test_scr_ac4_hybrid_before_and_after_scripts_are_cached(repo: Path) -> None:  # SCR-B2, SCR-B9
    seeded(repo)
    kw: dict[str, Any] = {"produces": {}, "inputs": ["src.txt"], "side_effects": "none", "cache": "thread"}
    spec = two_step()
    d = spec.units["draft"]
    assert d.step is not None
    step = dataclasses.replace(d.step, before=(Script(call=before_script, **kw),), after=(Script(call=after_script, **kw),))
    spec = dataclasses.replace(spec, units={**spec.units, "draft": dataclasses.replace(d, step=step)})
    ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW], judges=[judge(verdict_block("UNMET")), judge(), judge()])
    out = run_flow(repo, spec, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert RUNS == ["before", "after"]  # the retry restored both
    recs = [(r["phase"], r["cached"]) for r in scripts(repo, unit="draft")]
    assert recs == [("before", False), ("after", False), ("before", True), ("after", True)]
    assert [c.kind for c in ex.calls].count("step") == 3  # the sessions still ran; only the scripts did not


def test_ac1_a_failed_run_is_not_recorded_so_a_retry_runs_it_again(repo: Path) -> None:
    seeded(repo)
    spec = script_only(call=None, run=["git", "no-such-subcommand"], produces={})
    out = run_flow(repo, spec, standin("claude"))
    assert out.exit_code is ExitCode.PAUSED
    recs = scripts(repo, unit="build")
    assert len(recs) == 3 and all(r["cached"] is False and r["exit_code"] not in (0, None) for r in recs)
    assert cache_files(repo) == []


def test_ac1_an_environmental_exit_is_not_recorded(repo: Path) -> None:
    seeded(repo)
    spec = script_only(call=None, run=["git", "no-such-subcommand"], produces={}, environmental_exit_codes=[1, 129])
    run_flow(repo, spec, standin("claude"))
    recs = scripts(repo, unit="build")
    assert recs and all(r["environmental"] and not r["cached"] for r in recs)
    assert cache_files(repo) == []


def test_ac1_a_timed_out_run_is_not_recorded(repo: Path) -> None:
    seeded(repo)
    spec = script_only(call=None, run=["sleep", "5"], produces={}, timeout_s=1, gate=checked_gate(retry_budget=1))
    run_flow(repo, spec, standin("claude"))
    recs = scripts(repo, unit="build")
    assert len(recs) == 2 and not any(r["cached"] for r in recs)
    assert cache_files(repo) == []


def test_ac1_a_run_missing_a_produces_key_is_not_recorded(repo: Path) -> None:
    seeded(repo)
    steer(repo, "retry")  # the attempt is run again, and nothing was recorded to restore
    spec = script_only(call=empty_script, produces={"notes": "file"})
    run_flow(repo, spec, standin("claude"))
    assert RUNS == ["empty", "empty"] and not any(r["cached"] for r in scripts(repo, unit="build"))
    assert cache_files(repo) == []


def test_ac1_an_unreadable_cache_folder_is_a_logged_miss(repo: Path) -> None:
    seeded(repo)
    BREAK_CACHE.append(True)
    steer(repo, "retry")
    out = run_flow(repo, script_only(), standin("claude"))
    assert out.exit_code is ExitCode.FINISHED, out.message  # no engine error
    assert RUNS == ["build", "build"]
    recs = scripts(repo, unit="build")
    assert [r["cached"] for r in recs] == [False, False]
    assert all(r.get("cache_error") for r in recs)


def test_ac1_scriptcache_round_trip_and_unreadable_entry(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.txt").write_text("hello", encoding="utf-8")
    folder = tmp_path / "cache"
    result = scriptcache.Result(exit_code=0, artifacts={"a": "a.txt"}, kinds={"a": "file"})
    scriptcache.store(folder, "k1", result, work)
    (work / "a.txt").unlink()
    got = scriptcache.lookup(folder, "k1", work)
    assert got is not None and got.artifacts == {"a": "a.txt"} and (work / "a.txt").read_text() == "hello"
    assert scriptcache.lookup(folder, "other", work) is None
    (folder / "k1.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(scriptcache.CacheError):
        scriptcache.lookup(folder, "k1", work)
