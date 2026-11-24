"""The reuse key of a command run names the tree's content, not its history (CHK-B13, CHK-AC1, CHK-AC12, CHK-B17).

Part one: `reuse_key` on a scratch git repository and on a folder outside git. Part two: a step whose check preview
ran a command before an `after` script committed the step's files, and a gate check that runs the same command with
`reuse=True`. Nothing here names a workflow.
"""

from __future__ import annotations

import io
import json
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

from tempergraph.api import CheckFinding, CheckResult, Gate, Judge, Routing, Script, Step, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.standins import answer, standin
from tempergraph.run import selfcheck
from tempergraph.run.checks import reuse_key
from tempergraph.run.commands import CommandRefusal, ResolvedCommand, resolve_command
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from .conftest import _git
from .fixtures.workflows import crit, named
from .test_run import MET, registry

COMMAND = "git --version"
NO_SLEEP = RunSettings(sleep=lambda s: None)


def cmd_for(workdir: Path) -> ResolvedCommand:
    got = resolve_command((COMMAND,), COMMAND, workdir)
    assert not isinstance(got, CommandRefusal)
    return got


def key(workdir: Path) -> str:
    return reuse_key(cmd_for(workdir), workdir)


def commit_all(repo: Path, message: str = "more") -> None:
    _git(repo, "add", "-A", "--", ".", ":(exclude).tempergraph")
    _git(repo, "commit", "-q", "-m", message)


# -- part one: the key on a scratch repository ---------------------------------------------------------------------


def test_a_commit_of_unchanged_content_leaves_the_key(repo: Path) -> None:  # CHK-B13, AC 3
    (repo / "notes.md").write_text("one")
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("print(1)\n")
    before = key(repo)
    commit_all(repo)
    assert key(repo) == before
    _git(repo, "commit", "-q", "--allow-empty", "-m", "empty")  # a new HEAD and nothing else
    assert key(repo) == before


def test_a_changed_tracked_file_changes_the_key(repo: Path) -> None:  # CHK-B13, AC 4
    before = key(repo)
    (repo / "README.md").write_text("changed\n")
    changed = key(repo)
    assert changed != before
    commit_all(repo)
    assert key(repo) == changed  # committed, and still the same content


def test_an_added_and_a_removed_untracked_file_change_the_key(repo: Path) -> None:  # CHK-B13, AC 4
    before = key(repo)
    (repo / "new.txt").write_text("x")
    added = key(repo)
    assert added != before
    (repo / "new.txt").unlink()
    assert key(repo) == before  # removed again: the tree is what it was


def test_an_ignored_file_and_the_state_root_leave_the_key(repo: Path) -> None:  # CHK-B13, CHK-B12
    (repo / ".gitignore").write_text("scratch.log\n")
    commit_all(repo)
    before = key(repo)
    (repo / "scratch.log").write_text("noise")
    (repo / ".tempergraph").mkdir()
    (repo / ".tempergraph" / "state.json").write_text("{}")
    assert key(repo) == before


def test_a_tracked_file_deleted_from_the_tree_is_left_out(repo: Path) -> None:  # CHK-B13, AC 4
    (repo / "extra.txt").write_text("x")
    commit_all(repo)
    (repo / "extra.txt").unlink()  # still tracked by the index, gone from the tree
    never = repo.parent / "never"
    never.mkdir()
    _git(never, "init", "-q", "-b", "main")
    _git(never, "config", "user.email", "test@example.invalid")
    _git(never, "config", "user.name", "Test")
    (never / "README.md").write_text("scratch\n")
    _git(never, "add", "README.md")
    _git(never, "commit", "-q", "-m", "init")
    assert key(repo) == key(never)  # the same tree content, whatever the history


def test_the_executable_bit_changes_the_key(repo: Path) -> None:  # CHK-B13, AC 4
    (repo / "run.sh").write_text("#!/bin/sh\n")
    before = key(repo)
    (repo / "run.sh").chmod((repo / "run.sh").stat().st_mode | stat.S_IXUSR)
    assert key(repo) != before


def test_the_argv_and_the_working_folder_are_in_the_key(repo: Path) -> None:  # CHK-B13
    other = resolve_command(("git --version", "git status"), "git status", repo)
    assert not isinstance(other, CommandRefusal)
    assert reuse_key(other, repo) != key(repo)


def test_outside_git_every_file_outside_the_state_root_counts(tmp_path: Path) -> None:  # CHK-B13, AC 4
    folder = tmp_path / "plain"
    folder.mkdir()
    (folder / "a.txt").write_text("one")
    before = key(folder)
    assert key(folder) == before
    (folder / "a.txt").write_text("two")
    changed = key(folder)
    assert changed != before
    (folder / "sub").mkdir()
    (folder / "sub" / "b.txt").write_text("b")
    added = key(folder)
    assert added != changed
    (folder / ".tempergraph").mkdir()
    (folder / ".tempergraph" / "x.json").write_text("{}")
    assert key(folder) == added  # the state root is not part of the tree


# -- part two: a preview, an `after` script that commits, and the gate's check ------------------------------------


def commit_script(ctx: Any) -> dict[str, str]:
    """The workflow's own commit of the step's files, as an `after` script (the engine makes no commit)."""
    workdir = Path(ctx.workdir)
    _git(workdir, "add", "-A", "--", ".", ":(exclude).tempergraph")
    _git(workdir, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "step")
    return {}


def reusing_check(ctx: Any) -> CheckResult:
    """Runs one allowed command with `reuse=True`, in the preview and at the gate; says whether it was reused."""
    r = ctx.run(COMMAND, reuse=True)
    ok = bool(r.finished) and r.exit_code == 0
    return CheckResult(result="PASS" if ok else "FAIL", evidence=f"preview={ctx.preview} reused={r.reused}",
                       findings=[CheckFinding(status="pass" if ok else "fail", criterion="c1", place="notes.md",
                                              message="the command ran" if ok else "the command failed")])


def committing_wf() -> Any:
    units = {"build": Step(prompt="Build {request}", tools=["read", "write"], self_check=True,
                           after=[Script(call=commit_script)],
                           gate=Gate(check=reusing_check, judge=Judge(stance="V."), criteria=[crit("c1")]))}
    return named(Workflow(order=["build"], units=units, issue_repository="acme/x", allow_commands=(COMMAND,),
                          routing=Routing(description="Build and commit")))


class PreviewThenChange:
    """A step session that writes a file, previews once, and optionally changes the tree after the preview."""

    def __init__(self, repo: Path, change: str | None = None) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.repo, self.change = repo, change
        self.seen: list[str] = []
        self.workdir: Path | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        (ticket,) = set(re.findall(r"tempergraph self-check ([0-9a-f]{32})", req.prompt))
        work = self.workdir = Path(req.workdir)
        (work / "notes.md").write_text("notes\n")
        out = io.StringIO()
        assert selfcheck.run(state_root_path(self.repo), ticket, out) == 0
        self.seen.append(out.getvalue())
        if self.change == "edit":
            (work / "notes.md").write_text("notes, edited after the preview\n")
        elif self.change == "add":
            (work / "late.md").write_text("late\n")
        return answer("Built.", session_id="s")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        return answer(MET, tools=("Read",), session_id="j")


def gate_evidence(repo: Path, change: str | None) -> tuple[PreviewThenChange, str]:
    ex = PreviewThenChange(repo, change)
    out = start(committing_wf(), "S-1", {"request": "x"}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    path = run_dir(state_root_path(repo), "demo", "S-1") / "run.jsonl"
    checks = [r for r in map(json.loads, path.read_text().splitlines()) if r["kind"] == "check"]
    (check,) = checks
    assert "reused=False" in ex.seen[0] and "preview=True" in ex.seen[0]  # the preview ran the command
    return ex, str(check["evidence"])


def test_a_preview_run_before_the_commit_is_reused_by_the_gate_after_it(repo: Path) -> None:
    # CHK-AC12, CHK-B13, CHK-B17, AC 3
    ex, evidence = gate_evidence(repo, None)
    assert "preview=False reused=True" in evidence
    assert ex.workdir is not None
    log = subprocess.run(["git", "log", "--format=%s"], cwd=ex.workdir, capture_output=True, text=True,
                         check=True).stdout
    assert "step" in log.splitlines()  # the `after` script did commit the step's files between the two runs


def test_a_file_changed_after_the_preview_runs_the_command_again_at_the_gate(repo: Path) -> None:
    # CHK-AC12, CHK-B13, AC 4
    for n, change in enumerate(("edit", "add")):
        sub = repo.parent / f"case{n}"
        sub.mkdir()
        _git(sub, "init", "-q", "-b", "main")
        _git(sub, "config", "user.email", "test@example.invalid")
        _git(sub, "config", "user.name", "Test")
        (sub / "README.md").write_text("scratch\n")
        _git(sub, "add", "README.md")
        _git(sub, "commit", "-q", "-m", "init")
        _, evidence = gate_evidence(sub, change)
        assert "preview=False reused=False" in evidence, change
