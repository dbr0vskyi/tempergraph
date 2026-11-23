"""The working directory a session is given in a run on a worktree is the run worktree, and a `claude` launch cannot
leave it (WTR-AC4, WTR-B25, WTR-B12, WTR-B24). Scripted sessions only: the executors with launch code are the stand-in
and `claude`; `agent-sdk`, `messages-api` and `antigravity` exist as names and capability rows and have no launch code
to record a working directory from."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import EventSink, SessionRequest, SessionResult, ViewSet, WorkflowSpec
from tempergraph.executors import launcher
from tempergraph.executors.binding import BindingTable
from tempergraph.executors.claude import ClaudeExecutor
from tempergraph.executors.standins import answer

from .fixtures import streams as S
from .fixtures.workflows import named
from .test_run import MET
from .test_writer_branches import Writers, branch_step, go, thread_values, worktrees_root


def one_writer_step() -> WorkflowSpec:
    """One unit that declares `write`, so the workspace `auto` resolves to a run worktree."""
    from tempergraph.api import Routing

    return named(Workflow(order=["plan"], units={"plan": branch_step("plan", ("read", "write"))}, issue_repository="acme/x",
                          routing=Routing(description="Plan")))


def recorded_path(repo: Path, spec: WorkflowSpec, task: str) -> Path:
    record = thread_values(repo, spec, task)["workspace"]
    assert record["mode"] == "worktree", record
    return Path(record["path"])


def test_a_stand_in_session_is_given_the_run_worktree_as_its_working_directory(repo: Path) -> None:  # WTR-AC4 (WTR-B25)
    spec = one_writer_step()
    ex = Writers({"plan": {"notes.txt": "n\n"}})
    out = go(repo, spec, ex, "X-1")
    assert out.exit_code is ExitCode.FINISHED, out.message
    path = recorded_path(repo, spec, "X-1")
    assert path == worktrees_root(repo) / "demo--X-1"
    assert ex.workdirs[("step", "plan")] == path and ex.workdirs[("judge", "plan")] == path  # step and judge


class ClaudeInAWorktree(ClaudeExecutor):
    """The real `claude` executor, its launch replaced by the fake binary on PATH, recording the working directory each
    step request carries; the judge is scripted so that one fake scenario serves the step alone."""

    def __init__(self) -> None:
        super().__init__(bindings=BindingTable())
        self.workdirs: list[Path] = []

    def run_step(self, req: SessionRequest, sink: EventSink) -> SessionResult:
        self.workdirs.append(Path(req.workdir))
        return super().run_step(req, sink)

    def run_judge(self, req: SessionRequest, views: ViewSet, sink: EventSink) -> SessionResult:
        return answer(MET, tools=("Read",), session_id="j-claude")


def test_a_claude_session_is_launched_in_the_run_worktree_without_worktree_tools(
        repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # WTR-AC4 (WTR-B25, WTR-B12, WTR-B24)
    rec = tmp_path / "rec.json"
    S.fake_claude(tmp_path, monkeypatch, {"record": str(rec), "lines": [S.init(), S.text("done"), S.result()]})
    launched: list[tuple[list[str], Any]] = []
    real = subprocess.Popen

    def watch(argv: Any, *args: Any, **kw: Any) -> Any:
        if Path(str(list(argv)[0])).name == "claude" and "-p" in list(argv)[:3]:  # the step launch, not a probe
            launched.append((list(argv), kw.get("cwd")))
        return real(argv, *args, **kw)

    monkeypatch.setattr(launcher.subprocess, "Popen", watch)
    spec = one_writer_step()
    ex = ClaudeInAWorktree()
    out = go(repo, spec, ex, "X-2")
    assert out.exit_code is ExitCode.FINISHED, out.message
    path = recorded_path(repo, spec, "X-2")
    assert ex.workdirs == [path]  # the step request carries the run worktree
    (argv, cwd), = launched
    assert Path(cwd) == path  # and the child process runs there
    assert argv[argv.index("--disallowedTools") + 1] == "EnterWorktree,ExitWorktree"
    assert "--worktree" not in argv and "-w" not in argv
    seen = json.loads(rec.read_text())["argv"]  # what the launched binary itself was given
    assert "--worktree" not in seen and "-w" not in seen
    assert seen[seen.index("--disallowedTools") + 1] == "EnterWorktree,ExitWorktree"
