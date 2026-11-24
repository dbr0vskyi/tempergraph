"""A writing concurrent map entered a second time: each visit cuts item worktrees and branches of its own (`--i<n>-<item>`),
leaves the earlier visits' as they are, and merges only its own (MAP-AC10 to MAP-AC14, WTR-AC13), on scripted executors and
scratch git repositories."""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from typing import Any

from tempergraph import git as gitmod
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult, WorktreeDecl
from tempergraph.run.runner import resume
from tempergraph.store.layout import ensure_state_root, state_root_path
from tempergraph.workspace import cut_writers, prepare_workspace, resolve_workspace, writer_names

from .fixtures.workflows import two_step
from .test_map import NO_SLEEP
from .test_map_concurrent import go
from .test_map_concurrent_writers import RUN, TWO, Writes, writing
from .test_run import registry, verdict_block
from .test_writer_branches import git, thread_values, worktrees_root

SECOND = [{"id": "p1", "text": "First"}, {"id": "p3", "text": "Third"}]
FIRST_FILES = {"p1": {"p1.txt": "1\n"}, "p2": {"p2.txt": "2\n"}}
SECOND_FILES = {"p1": {"p1-v2.txt": "1b\n"}, "p3": {"p3.txt": "3\n"}}
BACK = verdict_block("UNMET", defect_in="phases")
UNMET = verdict_block("UNMET")


class Revisit(Writes):
    """A stand-in whose second `plan` step switches the list from `p1, p2` to `p1, p3` and the files each item writes, and
    that records, per item session, the visit, the working directory, the heads and the files the directory held."""

    def __init__(self, run_path: Path, repo: Path, *, judges: dict[str, list[str]] | None = None,
                 second: dict[str, list[str]] | None = None) -> None:
        super().__init__(TWO, FIRST_FILES, run_path=run_path)
        self.judges = {k: list(v) for k, v in (judges or {}).items()}
        self.second = second or {}  # verdicts that apply from the second visit on
        self.repo, self.plans = repo, 0
        self.first_heads: dict[str, str] = {}  # the first visit's item branches when the second plan step began
        self.sessions_of: list[dict[str, Any]] = []

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit, item = self.whose(req)
        if unit == "plan":
            self.plans += 1
            if self.plans == 2:
                self.first_heads = {i: git(self.repo, "rev-parse", f"{RUN}--i-{i}").strip() for i in ("p1", "p2")}
                self.items, self.writes = SECOND, SECOND_FILES
                self.judges.update({k: list(v) for k, v in self.second.items()})
        elif unit == "phase" and item is not None:
            here = Path(req.workdir)
            self.sessions_of.append({
                "visit": self.plans, "item": item, "workdir": here, "head": git(here, "rev-parse", "HEAD").strip(),
                "run_head": git(self.run_path or here, "rev-parse", "HEAD").strip(),
                "files": sorted(p.name for p in here.glob("*.txt")), "list": (here / "phases.json").read_text()})
        return super().run_step(req, sink)

    def first_session(self, visit: int, item: str) -> dict[str, Any]:
        return next(s for s in self.sessions_of if (s["visit"], s["item"]) == (visit, item))


def valid_branch(repo: Path, name: str) -> None:
    subprocess.run(["git", "check-ref-format", "--branch", name], cwd=repo, check=True, capture_output=True)


def test_a_later_visit_cuts_items_of_its_own_and_keeps_the_first_visits(repo: Path) -> None:
    # WTR-AC13 (WTR-B20), MAP-AC13 (MAP-B15, WTR-B24), AC 2
    root = ensure_state_root(state_root_path(repo))
    rec = prepare_workspace("demo/T-7", resolve_workspace(two_step(), repo, task_id="T-7"), WorktreeDecl(), root)
    run_path = Path(rec.path)
    first = cut_writers(rec, "demo/T-7", ["phase.p1"], None, root, kind="i")  # the first visit: no keyword
    (one,) = first.children
    assert Path(one["path"]).name == f"{run_path.name}--i-p1" and one["branch"] == f"{rec.branch}--i-p1"
    assert "visit" not in one
    kept = gitmod.head(Path(one["path"]))

    (run_path / "after-first.txt").write_text("made between the visits\n")
    gitmod.commit_all(run_path, "tempergraph: checkpoint before phase")
    run_head = gitmod.head(run_path)
    second = cut_writers(first, "demo/T-7", ["phase.p1", "phase.p3"], None, root, kind="i", visit=2)
    later = [c for c in second.children if c.get("visit") == 2]
    assert [Path(c["path"]).name for c in later] == [f"{run_path.name}--i2-p1", f"{run_path.name}--i2-p3"]
    assert [c["branch"] for c in later] == [f"{rec.branch}--i2-p1", f"{rec.branch}--i2-p3"]
    for c in later:
        valid_branch(repo, c["branch"])
        assert gitmod.head(Path(c["path"])) == run_head and (Path(c["path"]) / "after-first.txt").exists()
    assert [c["branch"] for c in second.children if c.get("visit", 1) == 1] == [f"{rec.branch}--i-p1"]
    assert len(second.children) == 3  # the first visit's child and both of the second's
    assert Path(one["path"]).is_dir() and gitmod.head(Path(one["path"])) == kept  # the first visit's, as it was
    assert gitmod.git(["rev-parse", "--verify", f"refs/heads/{rec.branch}--i-p1"], repo).strip() == kept

    again = list(second.children)
    assert cut_writers(second, "demo/T-7", ["phase.p1", "phase.p3"], None, root, kind="i", visit=2).children == again
    assert cut_writers(second, "demo/T-7", ["phase.p1"], None, root, kind="i").children == again  # visit 1 reused

    long_run = Path("/x") / ("r" * 70)
    ids = "phase." + "a" * 40
    one_name = writer_names(long_run, "tg/demo/T", ids, "demo/T", kind="i")
    two_name = writer_names(long_run, "tg/demo/T", ids, "demo/T", kind="i", visit=2)
    assert one_name[0] != two_name[0] and len(one_name[0]) <= 80 and len(two_name[0]) <= 80


def test_a_trip_back_runs_the_second_visit_in_worktrees_of_its_own_and_merges_only_them(repo: Path) -> None:
    # MAP-AC10 (MAP-B14), MAP-AC11 (MAP-B14), MAP-AC13 (MAP-B15), MAP-AC14 (MAP-B16), WTR-AC13 (WTR-B20), AC 3, AC 4
    run_path = worktrees_root(repo) / "demo--M-1"
    ex = Revisit(run_path, repo, judges={"join.None": [BACK]})
    spec = writing()
    out = go(repo, spec, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (newest, *_) = git(repo, "log", "--format=%H", "--grep=checkpoint before phase", "--end-of-options", RUN).split()
    for item in ("p1", "p3"):  # MAP-AC10: its own worktree and branch, cut at the checkpoint before the visit
        s = ex.first_session(2, item)
        assert s["workdir"] == worktrees_root(repo) / f"demo--M-1--i2-{item}"
        assert s["head"] == newest == s["run_head"]
        assert git(repo, "rev-parse", f"{RUN}--i2-{item}").strip()
        valid_branch(repo, f"{RUN}--i2-{item}")
    for item in ("p1", "p2"):
        assert ex.first_session(1, item)["workdir"] == worktrees_root(repo) / f"demo--M-1--i-{item}"
    assert ex.first_session(2, "p1")["workdir"] != ex.first_session(1, "p1")["workdir"]
    for item in ("p1", "p3"):  # MAP-AC11: what the run branch held when the visit started
        s = ex.first_session(2, item)
        assert '"p3"' in s["list"] and "p2.txt" in s["files"] and "p1.txt" in s["files"]
    assert ex.first_session(2, "p3")["files"] == ["p1.txt", "p2.txt"]  # no file of a first-visit item branch's own work
    for item in ("p1", "p2"):  # MAP-AC13: the first visit's branches and worktrees stay as they were
        assert git(repo, "rev-parse", f"{RUN}--i-{item}").strip() == ex.first_heads[item]
        assert (worktrees_root(repo) / f"demo--M-1--i-{item}").is_dir()
    children = thread_values(repo, spec, "M-1")["workspace"]["children"]
    assert sorted(Path(c["path"]).name for c in children) == [
        "demo--M-1--i-p1", "demo--M-1--i-p2", "demo--M-1--i2-p1", "demo--M-1--i2-p3"]
    assert all(c["branch"] == f"{RUN}{Path(c['path']).name.removeprefix('demo--M-1')}" for c in children)
    for c in children:
        valid_branch(repo, c["branch"])
    merges = [ln.split("|") for ln in git(repo, "log", "--merges", "--reverse", "--format=%P|%s", RUN).splitlines()]
    assert len(merges) == 4  # two for each visit
    assert [m[1] for m in merges] == ["Merge map item p1 of phase", "Merge map item p2 of phase",
                                      "Merge map item p1 of phase", "Merge map item p3 of phase"]
    assert [m[0].split()[1] for m in merges[2:]] == [git(repo, "rev-parse", f"{RUN}--i2-{i}").strip()
                                                     for i in ("p1", "p3")]  # MAP-AC14: the second visit's own heads
    assert not {m[0].split()[1] for m in merges[2:]} & {ex.first_heads["p1"], ex.first_heads["p2"]}
    for name in ("p1.txt", "p2.txt", "p1-v2.txt", "p3.txt"):
        assert (run_path / name).exists(), name


def answer(repo: Path, spec: Any, ex: Revisit, item: str, decision: str) -> Any:
    """Answer the pause of one item of the map (a concurrent map's pauses are answered by item)."""
    return resume(spec, "M-1", repo, registry(ex), decision=decision,
                  settings=dataclasses.replace(NO_SLEEP, unit=f"phase.{item}"))


def test_a_second_visit_paused_on_a_spent_budget_resumes_in_its_own_worktree(repo: Path) -> None:
    # MAP-AC12 (MAP-B14), AC 3
    run_path = worktrees_root(repo) / "demo--M-1"
    spec = writing()
    ex = Revisit(run_path, repo, judges={"join.None": [BACK]}, second={"phase.p1": [UNMET, UNMET],
                                                                        "phase.p3": [UNMET, UNMET]})
    out = go(repo, spec, ex)  # both items of the second visit spend their retry and pause
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert out.payload["kind"] == "budget" and out.payload["unit"] == "phase" and out.payload["item"] in ("p1", "p3")
    before = ex.steps("p1")
    held = answer(repo, spec, ex, "p3", "retry")  # p3 runs again; p1 still waits for a person
    assert held.exit_code is ExitCode.PAUSED, held.message
    done = answer(repo, spec, ex, "p1", "proceed")
    assert done.exit_code is ExitCode.FINISHED, done.message
    again = [s for s in ex.sessions_of if s["item"] == "p3"]
    assert len(again) == 3 and {s["visit"] for s in again} == {2}
    assert {s["workdir"] for s in again} == {worktrees_root(repo) / "demo--M-1--i2-p3"}  # the retry too
    assert not (worktrees_root(repo) / "demo--M-1--i-p3").exists()
    assert git(repo, "branch", "--list", f"{RUN}--i-p3").strip() == ""  # a first-visit item p3 never existed
    assert ex.steps("p1") == before  # p1 started no session after the pause
