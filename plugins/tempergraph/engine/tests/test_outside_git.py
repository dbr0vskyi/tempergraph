"""Runs in a folder outside git: the state root, in place only, the manifest and the refusals (WSP §2.4, AC-5)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tempergraph import git as gitmod
from tempergraph.api import CheckResult, ComplexitySwitch, Level, Measure, Risk, When, stock
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.standins import answer, standin
from tempergraph.run import checks as checkmod
from tempergraph.run.runner import RunSettings, needs_git, start
from tempergraph.store import manifest
from tempergraph.store.layout import NotInRepository, home_path, run_dir, state_root_path
from tempergraph.workspace import WorkspaceRefused, resolve_workspace

from .fixtures.workflows import two_step
from .test_cli import cli, happy
from .test_run import DRAFT, MET, REVIEW, judge, records, registry

NO_SLEEP = RunSettings(sleep=lambda s: None)
SEEN: dict[str, Any] = {}


@pytest.fixture
def plain(tmp_path: Path) -> Path:
    folder = tmp_path / "plain"
    folder.mkdir()
    (folder / "README.md").write_text("no git here\n")
    return folder


# -- the state root -------------------------------------------------------------------------------------------


def test_the_root_is_the_start_dir_then_the_nearest_one_upward(plain: Path) -> None:
    assert state_root_path(plain) == plain / ".tempergraph"
    deep = plain / "a" / "b"
    deep.mkdir(parents=True)
    assert state_root_path(deep) == deep / ".tempergraph"  # nothing upward holds a manifest yet
    (plain / ".tempergraph").mkdir()
    (plain / ".tempergraph" / "manifest.json").write_text("{}")
    assert state_root_path(deep) == plain / ".tempergraph"


def test_a_declared_root_wins_outside_git_only(plain: Path, repo: Path, tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPERGRAPH_STATE_ROOT", str(tmp_path / "state"))
    assert state_root_path(plain) == tmp_path / "state"
    assert state_root_path(repo) == repo / ".tempergraph"  # inside a repository the rule never changes


def test_the_home_folder_is_never_a_state_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = home_path()
    home.mkdir(parents=True, exist_ok=True)
    (home / "manifest.json").write_text("{}")
    with pytest.raises(NotInRepository):
        state_root_path(home.parent)  # `<start dir>/.tempergraph` would be the home folder
    below = home.parent / "work"
    below.mkdir()
    assert state_root_path(below) == below / ".tempergraph"  # the walk upward skips the home folder
    monkeypatch.setenv("TEMPERGRAPH_STATE_ROOT", str(home))
    with pytest.raises(NotInRepository):
        state_root_path(tmp_path)


# -- a run in a plain folder ----------------------------------------------------------------------------------


def test_a_run_works_in_place_and_keeps_its_state_beside_the_work(plain: Path) -> None:
    out = start(two_step(), "T-1", {"request": "x"}, plain,
                registry(standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])), NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    root = plain / ".tempergraph"
    assert (root / "manifest.json").is_file() and (run_dir(root, "demo", "T-1") / "manifest.json").is_file()
    entered = [r for r in records_at(root) if r["kind"] == "unit_entered"]
    assert entered and all(r["head_commit"] == "" and r["dirty"] is None for r in entered)


def records_at(root: Path) -> list[dict[str, Any]]:
    import json

    return [json.loads(x) for x in (run_dir(root, "demo", "T-1") / "run.jsonl").read_text().splitlines()]


def test_auto_is_in_place_and_a_worktree_is_refused(plain: Path) -> None:
    assert resolve_workspace(two_step(), plain, task_id="T-1").mode == "in_place"
    with pytest.raises(WorkspaceRefused):
        resolve_workspace(two_step(), plain, "worktree", task_id="T-1")
    code, _, err = cli(plain, happy(), "run", "demo", "x", "--workspace", "worktree")
    assert code == ExitCode.USAGE and "needs a git checkout" in err and not (plain / ".tempergraph").exists()


def test_the_cli_takes_a_state_root(plain: Path, tmp_path: Path) -> None:
    code, doc, err = cli(plain, happy(), "--state-root", str(tmp_path / "elsewhere"), "run", "demo", "x", "--json")
    assert code == ExitCode.FINISHED, err
    assert (tmp_path / "elsewhere" / "runs" / "demo").is_dir() and not (plain / ".tempergraph").exists()
    code, st, _ = cli(plain, None, "--state-root", str(tmp_path / "elsewhere"), "status")
    assert code == 0 and st["threads"][0]["state"] == "finished"
    assert cli(plain, None, "status")[1]["threads"] == []  # without it, the start dir's own (empty) root


# -- the manifest fingerprint ---------------------------------------------------------------------------------


def test_the_manifest_sees_a_write_a_touch_and_a_removal_but_not_the_state_root(plain: Path) -> None:
    before = gitmod.fingerprint(plain)
    assert before.manifest and before.status.startswith("manifest:1:") and before == gitmod.fingerprint(plain)
    (plain / ".tempergraph").mkdir()
    (plain / ".tempergraph" / "x.json").write_text("{}")
    assert gitmod.fingerprint(plain) == before
    base = {k: list(v) for k, v in manifest.scan(plain).items()}
    (plain / "new.txt").write_text("n")
    (plain / "README.md").write_text("changed, another size\n")
    assert gitmod.fingerprint(plain) != before
    assert manifest.changed(plain, base) == ["README.md", "new.txt"]
    (plain / "new.txt").unlink()
    assert manifest.changed(plain, base) == ["README.md"]
    assert manifest.file_hash(plain / "README.md") and manifest.file_hash(plain / "gone") is None


def test_a_folder_past_the_limit_is_refused_at_start(plain: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manifest, "MAX_FILES", 2)
    for n in range(3):
        (plain / f"f{n}.txt").write_text("x")
    assert manifest.count_over(plain, 2) and gitmod.fingerprint(plain).manifest
    out = start(two_step(), "T-1", {"request": "x"}, plain, registry(happy()), NO_SLEEP)
    assert out.exit_code is ExitCode.USAGE and out.reason == "workspace_too_large"
    assert not (plain / ".tempergraph").exists()


class WritingJudge:
    """A stand-in whose judge session writes the workspace, which a read-only session must not."""

    def __init__(self, folder: Path) -> None:
        self.inner = standin("claude", steps=[DRAFT, REVIEW])
        self.name, self.folder = self.inner.name, folder

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        (self.folder / "judge-was-here.txt").write_text("oops")
        return answer(MET, tools=("Read",), session_id="j")


def test_the_guard_catches_a_judge_that_writes_outside_git(plain: Path) -> None:  # WSP-AC-5, GRD
    start(two_step(), "T-1", {"request": "x"}, plain, registry(WritingJudge(plain)), NO_SLEEP)
    gates = [r for r in records(plain) if r["kind"] == "judgement"]
    assert gates and gates[0]["guard"] == "warned"  # in place a changed tree warns (GRD); in git it is the same


# -- checks and refusals --------------------------------------------------------------------------------------


def seeing_check(ctx: Any) -> CheckResult:
    SEEN["git"], SEEN["changed"] = ctx.git, tuple(ctx.changed_paths)
    return CheckResult(result="PASS", evidence="seen")


def test_a_check_gets_no_git_facts_and_the_manifests_changed_paths(plain: Path, repo: Path) -> None:
    assert checkmod.git_facts(plain) is None and checkmod.git_facts(repo) is not None
    base = plain / ".tempergraph" / "m.json"
    base.parent.mkdir()
    import json

    base.write_text(json.dumps({"files": {k: list(v) for k, v in manifest.scan(plain).items()}}))
    (plain / "notes.md").write_text("n")
    assert checkmod.changed_paths(plain, None, base) == ("notes.md",)
    assert checkmod.changed_paths(plain, None, plain / "missing.json") == ()
    facts = checkmod.git_facts(repo)
    assert checkmod.changed_paths(repo, facts, None) == tuple(facts.changed_paths)


def spec_needing_git() -> Any:
    base = two_step()
    units = dict(base.units)
    risky = Risk(levels=[Level("base"), Level("high", model="large")], when=[When("high", paths=["src/**"])])
    gate = units["draft"].gate
    units["draft"] = dataclasses.replace(
        units["draft"], gate=dataclasses.replace(gate, judge=dataclasses.replace(gate.judge, risk=risky)))
    units["size"] = ComplexitySwitch(arms={"small": "draft", "large": "review"},
                                     measures=[Measure("touched", stock.changed_paths())], joins_at="review")
    return dataclasses.replace(base, units=units)


def test_what_needs_git_is_named_and_refused_before_spend(plain: Path) -> None:
    assert needs_git(two_step(), NO_SLEEP) == []
    assert needs_git(two_step(), dataclasses.replace(NO_SLEEP, carry=True)) == ["--carry (run state on a branch)"]
    named_needs = needs_git(spec_needing_git(), NO_SLEEP)
    assert any("risk rule of draft" in n for n in named_needs) and any("changed_paths" in n for n in named_needs)
    out = start(two_step(), "T-1", {"request": "x"}, plain, registry(happy()),
                dataclasses.replace(NO_SLEEP, carry=True))
    assert out.exit_code is ExitCode.USAGE and out.reason == "needs_git" and not (plain / ".tempergraph").exists()
    for verb in (["carry", "status", "demo", "T-1"], ["improve", "trial", "p-1"]):
        code, _, err = cli(plain, None, *verb)
        assert code == ExitCode.USAGE and "needs_git" in err, verb
