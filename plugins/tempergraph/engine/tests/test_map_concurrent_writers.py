"""A writing concurrent map: each item in its own sibling worktree cut after a checkpoint commit, the items merged into
the run branch at the end of the map, and the joined result checked once (WSP-AC16 to WSP-AC20, WTR-AC12, MAP-AC8,
MAP-AC9), on scripted executors and scratch git repositories."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from tempergraph.api import CheckResult
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding, SessionRequest, SessionResult

from .test_map_concurrent import FOUR, ByItem, concurrent, go
from .test_writer_branches import git, subjects, worktrees_root

RUN = "tg/demo/M-1"
TWO = [{"id": "p1", "text": "First"}, {"id": "p2", "text": "Second"}]


def where(ctx: Any) -> CheckResult:
    """A check that reports where it ran and for which item (it runs in a worker process)."""
    return CheckResult(result="PASS", evidence=f"{ctx.item}@{ctx.workdir}",
                       findings=[CheckFinding(status="pass", criterion="c-item")])


def lists(ctx: Any) -> CheckResult:
    """A check that lists the files of its working directory (it runs in a worker process)."""
    names = sorted(p.name for p in Path(ctx.workdir).glob("*.txt"))
    return CheckResult(result="PASS", evidence=f"{ctx.item}|{','.join(names)}|{ctx.workdir}",
                       findings=[CheckFinding(status="pass", criterion="c-item")])


def clashes(ctx: Any) -> CheckResult:
    """A check that passes every item and fails the joined result (it runs in a worker process)."""
    if ctx.item is not None:
        return CheckResult(result="PASS", evidence="item", findings=[CheckFinding(status="pass", criterion="c-item")])
    return CheckResult(result="FAIL", evidence="joined", findings=[
        CheckFinding(status="fail", criterion="c-item", message="joined files clash", place="one.txt")])


class Writes(ByItem):
    """A stand-in whose item sessions write the files named per item under the workdir they were given, and record the
    working directory and head of every item session and what the run's worktree held at the time."""

    def __init__(self, items: list[dict[str, str]], writes: dict[str, dict[str, str]], *, delays: dict[str, float] | None
                 = None, run_path: Path | None = None) -> None:
        super().__init__(items)
        self.writes = writes
        self.delays = delays or {}
        self.run_path = run_path
        self.workdirs: dict[tuple[str, str], Path] = {}
        self.heads: dict[str, str] = {}
        self.run_had: list[list[str]] = []  # per item session: the written files the run's worktree already held

    def _note(self, kind: str, req: SessionRequest) -> str | None:
        unit, item = self.whose(req)
        if unit == "phase" and item is not None:
            self.workdirs[(kind, item)] = Path(req.workdir)
            if self.run_path is not None:
                files = {f for per in self.writes.values() for f in per}
                self.run_had.append(sorted(f for f in files if (self.run_path / f).exists()))
        return item if unit == "phase" else None

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        item = self._note("step", req)
        if item is not None:
            self.heads[item] = git(Path(req.workdir), "rev-parse", "HEAD").strip()
            time.sleep(self.delays.get(item, 0.0))
            for rel, text in self.writes.get(item, {}).items():
                (Path(req.workdir) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(req.workdir) / rel).write_text(text)
        return super().run_step(req, sink)

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        self._note("judge", req)
        return super().run_judge(req, views, sink)


def writing(**fields: Any) -> Any:
    return concurrent(tools=("read", "write"), concurrency=fields.pop("concurrency", 2), **fields)


def checkpoint_of(repo: Path) -> str:
    (found,) = git(repo, "log", "--format=%H", "--grep=checkpoint before phase", "--end-of-options", RUN).split()
    return found


def test_entering_a_writing_map_commits_the_uncommitted_work_first(repo: Path) -> None:  # WSP-AC19 (WSP-B19), WSP-AC16
    ex = Writes(TWO, {"p1": {"one.txt": "1\n"}, "p2": {"two.txt": "2\n"}})
    out = go(repo, writing(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    checkpoint = checkpoint_of(repo)  # one commit
    assert git(repo, "show", "--name-only", "--format=", checkpoint).split() == ["phases.json"]  # what `plan` left
    for item in ("p1", "p2"):
        git(repo, "merge-base", "--is-ancestor", checkpoint, f"{RUN}--i-{item}")  # the item branch was cut after it
        assert ex.heads[item] == checkpoint  # and its session started at that commit
    assert git(worktrees_root(repo) / "demo--M-1", "status", "--porcelain", "--untracked-files=all").strip() == ""


def test_each_item_works_in_its_own_sibling_worktree(repo: Path) -> None:  # WSP-AC16 (WSP-B11), WTR-AC12 (WTR-B25, WTR-B20)
    run_path = worktrees_root(repo) / "demo--M-1"
    ex = Writes(TWO, {"p1": {"one.txt": "1\n"}, "p2": {"two.txt": "2\n"}}, run_path=run_path)
    out = go(repo, writing(check=where), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    for item in ("p1", "p2"):
        mine = worktrees_root(repo) / f"demo--M-1--i-{item}"
        assert ex.workdirs[("step", item)] == mine and ex.workdirs[("judge", item)] == mine  # step and judge
        assert git(repo, "rev-parse", f"{RUN}--i-{item}").strip()  # its own branch
    seen = {r["evidence"] for r in recs_of(repo, "check") if r["item"]}
    assert seen == {f"p1@{worktrees_root(repo) / 'demo--M-1--i-p1'}", f"p2@{worktrees_root(repo) / 'demo--M-1--i-p2'}"}
    assert all(had == [] for had in ex.run_had)  # until the merge the run's worktree held none of the items' files


def test_items_whose_ids_share_their_first_24_characters_get_two_worktrees(repo: Path) -> None:  # WSP-AC16 (WTR-B20)
    ids = ["a-long-item-id-sharing-24-one", "a-long-item-id-sharing-24-two"]
    items = [{"id": i, "text": i} for i in ids]
    ex = Writes(items, {i: {f"{i}.txt": "x\n"} for i in ids})
    out = go(repo, writing(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    paths = {ex.workdirs[("step", i)] for i in ids}
    assert len(paths) == 2 and all(p.name == f"demo--M-1--i-{i}" for p, i in zip(sorted(paths), sorted(ids), strict=True))


def test_the_items_are_merged_without_fast_forward_in_the_order_of_the_list(repo: Path) -> None:  # WSP-AC17 (WSP-B11)
    items = FOUR[:3]
    ex = Writes(items, {i["id"]: {f"{i['id']}.txt": "x\n"} for i in items}, delays={"p1": 0.4})  # the first ends last
    out = go(repo, writing(concurrency=3), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert sorted(git(repo, "ls-tree", "-r", "--name-only", RUN).split()) == [
        "README.md", "p1.txt", "p2.txt", "p3.txt", "phases.json"]
    merges = [ln.split() for ln in git(repo, "log", "--merges", "--reverse", "--format=%H %P", RUN).splitlines()]
    assert len(merges) == 3  # one merge commit per item, none fast-forwarded
    for (_commit, _, second), item in zip(merges, ("p1", "p2", "p3"), strict=True):
        assert second == git(repo, "rev-parse", f"{RUN}--i-{item}").strip()  # in the order of the list
    assert [s for s in subjects(repo, RUN) if s.startswith("Merge map item")][::-1] == [
        "Merge map item p1 of phase", "Merge map item p2 of phase", "Merge map item p3 of phase"]
    assert git(repo, "rev-parse", RUN).strip() == merges[-1][0]
    run_path = worktrees_root(repo) / "demo--M-1"
    assert all((run_path / f"{i['id']}.txt").exists() for i in items)  # the run's worktree holds every item's files


def test_a_merge_conflict_resets_the_run_branch_and_blocks_the_map_with_the_paths(repo: Path) -> None:  # WSP-AC20 (WSP-B12)
    ex = Writes(TWO, {"p1": {"shared.txt": "the first line\n", "one.txt": "1\n"}, "p2": {"shared.txt": "the second line\n"}})
    out = go(repo, writing(), ex)
    assert out.exit_code is ExitCode.PAUSED and out.reason == "escalation", out.message
    run_path = worktrees_root(repo) / "demo--M-1"
    assert git(repo, "rev-parse", RUN).strip() == checkpoint_of(repo)  # as before the first merge, p1's merge undone
    assert git(run_path, "status", "--porcelain", "--untracked-files=all").strip() == ""
    assert subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=run_path,
                          capture_output=True).returncode != 0
    assert not (run_path / "one.txt").exists() and not (run_path / "shared.txt").exists()
    payload = out.payload
    assert payload["unit"] == "phase" and payload["reason"] == "merge_conflict"
    assert [b["place"] for b in payload["blockers"]] == ["shared.txt"]  # the pause lists the conflicting path
    assert not [c for c in ex.calls if c[1] == "join"]  # the join never ran
    assert ex.calls[-1][0] == "judge" and len(ex.calls) == 6  # plan, then two items' step and judge: no session after


def test_the_joined_result_is_checked_once_on_the_run_worktree_after_the_merge(repo: Path) -> None:  # MAP-AC8 (MAP-B12)
    ex = Writes(TWO, {"p1": {"one.txt": "1\n"}, "p2": {"two.txt": "2\n"}})
    out = go(repo, writing(check=lists), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    run_path = worktrees_root(repo) / "demo--M-1"
    checks = [r for r in recs_of(repo, "check") if r["unit"] == "phase"]
    joined = [r for r in checks if r["item"] is None]
    assert len(joined) == 1  # once, with no item
    assert joined[0]["evidence"] == f"None|one.txt,two.txt|{run_path}"  # on the run's worktree, over both items' files
    mine = {r["item"]: r["evidence"] for r in checks if r["item"]}  # besides one call per item attempt, in its own worktree
    assert mine == {"p1": f"p1|one.txt|{worktrees_root(repo) / 'demo--M-1--i-p1'}",
                    "p2": f"p2|two.txt|{worktrees_root(repo) / 'demo--M-1--i-p2'}"}
    rows = recs_of(repo, "attempt_start")
    first_join = next(r for r in rows if r["session_key"] == "join.1.step")
    assert joined[0]["seq"] < first_join["seq"] and all(r["seq"] < joined[0]["seq"] for r in checks if r["item"])


def test_a_map_whose_gate_declares_no_check_runs_none_after_the_merge(repo: Path) -> None:  # MAP-AC8 (MAP-B12)
    ex = Writes(TWO, {"p1": {"one.txt": "1\n"}, "p2": {"two.txt": "2\n"}})
    out = go(repo, writing(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert not [r for r in recs_of(repo, "check") if r["unit"] == "phase" and r["item"] is None]  # none on the run's worktree
    assert ("step", "join", None) in ex.calls  # the next unit starts


def test_a_failing_joined_check_blocks_the_map_and_is_not_retried(repo: Path) -> None:  # MAP-AC9 (MAP-B13)
    ex = Writes(TWO, {"p1": {"one.txt": "1\n"}, "p2": {"two.txt": "2\n"}})
    out = go(repo, writing(check=clashes), ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    payload = out.payload
    assert payload["unit"] == "phase" and payload["item"] is None and payload["reason"] == "map_check"
    assert [(b["problem"], b["place"]) for b in payload["blockers"]] == [("joined files clash", "one.txt")]  # listed
    joined = [r for r in recs_of(repo, "check") if r["unit"] == "phase" and r["item"] is None]
    assert len(joined) == 1 and joined[0]["result"] == "FAIL"  # it ran once
    assert not [r for r in recs_of(repo, "budget") if r["unit"] == "phase"]  # no retry was spent
    assert len(git(repo, "log", "--merges", "--format=%H", RUN).split()) == 2  # the run branch still holds both merges
    assert len(ex.calls) == 6 and ex.calls[-1][0] == "judge"  # no item and no model session after the check
    assert not [c for c in ex.calls if c[1] == "join"]  # and the next unit never runs


def recs_of(repo: Path, kind: str) -> list[dict[str, Any]]:
    from .test_map import recs

    return recs(repo, kind)
