"""A writing contest: each slot in its own sibling worktree cut after a checkpoint commit, only the winner merged into
the run branch (CTS-AC4; CTS-B5, CTS-B6, CTS-B7, CTS-B9, WSP-B11, WSP-B12, WSP-B19, WTR-B20)."""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode

from .test_contest_run import BLOCKED, BOTH_MET, BySlot, contest_spec, go, recs
from .test_writer_branches import git, subjects, thread_values, worktrees_root

RUN = "tg/demo/C-1"


class Writes(BySlot):
    """`BySlot` whose steps write `content[slot]` to `a.py` in the working directory they were given, and note it."""

    def __init__(self, content: dict[str, str], **kw: Any) -> None:
        super().__init__(**kw)
        self.content = content
        self.workdirs: dict[str, Path] = {}
        self.heads: dict[str, str] = {}

    def run_step(self, req: Any, sink: Any) -> Any:
        slot = self.whose(req)
        if slot == "plan":  # an earlier unit leaves uncommitted work: the checkpoint commit takes it
            (Path(req.workdir) / "plan.txt").write_text("the plan\n")
        if slot in self.content:
            self.workdirs[slot] = Path(req.workdir)
            self.heads[slot] = git(Path(req.workdir), "rev-parse", "HEAD").strip()
            (Path(req.workdir) / "a.py").write_text(self.content[slot])
        return super().run_step(req, sink)


def writing(plan: bool = False, **fields: Any) -> Any:
    spec = contest_spec(slots=2, writes=True, then=False, plan=plan, **fields)
    pick = spec.units["pick"]
    step = dataclasses.replace(pick.step, tools=("read", "write"))
    return dataclasses.replace(spec, units={**spec.units, "pick": dataclasses.replace(pick, step=step)})


def run_files(repo: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in (worktrees_root(repo) / "demo--C-1").glob("a.py")}


def test_only_the_winners_worktree_is_merged_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B5, CTS-B7), WSP-AC17
    ex = Writes({"s1": "one\n", "s2": "two\n"}, costs={"s1": 0.3, "s2": 0.1})  # both edit a.py; `s2` is the cheaper tie
    out = go(repo, writing(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (rec,) = recs(repo, "contest")
    assert rec["winner"] == 2
    assert run_files(repo) == {"a.py": "two\n"}  # the run's worktree holds the winner's file, no conflict arose
    assert git(repo, "show", f"{RUN}:a.py") == "two\n"
    merges = [ln.split() for ln in git(repo, "log", "--merges", "--format=%H %P", RUN).splitlines()]
    assert len(merges) == 1 and merges[0][2] == git(repo, "rev-parse", f"{RUN}--s-s2").strip()  # without fast-forward
    assert [s for s in subjects(repo, RUN) if s.startswith("Merge contest slot")] == ["Merge contest slot s2 of pick"]
    assert git(repo, "rev-parse", f"{RUN}--s-s1").strip() != merges[0][2]  # the other branch was not merged


def test_each_slot_works_in_its_own_sibling_worktree_cut_after_the_checkpoint_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B6, WSP-B19, WTR-B20)
    ex = Writes({"s1": "one\n", "s2": "two\n"})
    out = go(repo, writing(plan=True), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    root = worktrees_root(repo)
    assert ex.workdirs == {"s1": root / "demo--C-1--s-s1", "s2": root / "demo--C-1--s-s2"}
    (checkpoint,) = git(repo, "log", "--format=%H", "--grep=checkpoint before pick", "--end-of-options", RUN).split()
    assert git(repo, "show", "--name-only", "--format=", checkpoint).split() == ["plan.txt"]  # what `plan` left
    assert ex.heads == {"s1": checkpoint, "s2": checkpoint}  # the slots started at the commit taken when it was entered


def test_the_other_slots_worktrees_are_discarded_and_their_records_kept_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B7)
    ex = Writes({"s1": "one\n", "s2": "two\n"}, costs={"s1": 0.1, "s2": 0.3})
    spec = writing()
    out = go(repo, spec, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    children = {c["unit"]: c for c in thread_values(repo, spec, "C-1")["workspace"]["children"]}
    assert set(children) == {"pick.s1", "pick.s2"}  # the records stay
    assert (children["pick.s1"]["state"], children["pick.s2"]["state"]) == ("active", "discarded")  # s2 lost
    assert Path(children["pick.s2"]["path"]).exists() is True  # nothing was deleted: only the record says discarded


def test_a_failed_winner_merge_is_a_writer_join_conflict_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (CTS-B9, WSP-B12)
    ex = Writes({"s1": "one\n", "s2": "two\n"}, costs={"s1": 0.1, "s2": 0.3})
    spec = writing()
    # the run branch changes a.py after the checkpoint, so the winner's merge cannot apply
    original = Writes.run_step

    def spoil(self: Writes, req: Any, sink: Any) -> Any:
        res = original(self, req, sink)
        run = worktrees_root(repo) / "demo--C-1"
        if self.whose(req) == "s2" and not (run / "a.py").exists():
            (run / "a.py").write_text("clash\n")
            git(run, "add", "a.py")
            git(run, "-c", "user.email=t@example.invalid", "-c", "user.name=T", "commit", "-q", "-m", "run branch edit")
        return res

    Writes.run_step = spoil  # type: ignore[method-assign]
    try:
        out = go(repo, spec, ex)
    finally:
        Writes.run_step = original  # type: ignore[method-assign]
    assert out.exit_code is ExitCode.PAUSED and out.payload["reason"] == "merge_conflict", out.message
    assert out.payload["unit"] == "pick" and [b["place"] for b in out.payload["blockers"]] == ["a.py"]
    run = worktrees_root(repo) / "demo--C-1"
    assert git(run, "status", "--porcelain", "--untracked-files=all").strip() == ""  # the run branch is put back
    assert subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=run, capture_output=True).returncode != 0


def test_a_read_only_slot_that_changes_the_run_worktree_fails_CTS_AC4(repo: Path) -> None:  # CTS-AC4 (WSP-B11)
    ex = BySlot(touch={"s2": "leak.txt"}, judges={"s1": [BLOCKED]})
    spec = contest_spec(slots=2, retry_budget=0, then=False, concurrency=1)  # one at a time, as the map's test does
    out = go(repo, spec, ex)
    (rec,) = recs(repo, "contest")
    by = {s["name"]: s for s in rec["slots"]}
    assert by["s2"]["verdict"] is None and by["s2"]["keys"] is None  # put out: its step failed on the worktree rule
    assert rec["winner"] == 1 and out.exit_code is ExitCode.PAUSED and out.payload["winner"] == "s1"
    blockers = thread_values(repo, spec, "C-1")["judgements"]["pick.s2"]["blockers"]
    assert [b["problem"] for b in blockers] == ["branch_changed_the_workspace"]  # WSP-B11, as for a map item


def test_a_second_attempt_of_a_writer_contest_ends_blocked_rather_than_overwrite_a_slot_branch_CTS_AC4(repo: Path) -> None:  # CTS-AC4
    ex = Writes({"s1": "one\n", "s2": "two\n"}, judges={"s1": [BLOCKED, BOTH_MET], "s2": [BLOCKED, BOTH_MET]})
    out = go(repo, writing(), ex)
    errors = [r for r in recs(repo, "engine_error") if r.get("error") == "workspace_refused"]
    assert errors and "second attempt" in errors[0]["detail"], out.message  # the retry meets the first attempt's branches
    assert out.exit_code is not ExitCode.FINISHED
    assert git(repo, "rev-parse", f"{RUN}--s-s1").strip() and git(repo, "rev-parse", f"{RUN}--s-s2").strip()  # untouched
    assert sum(1 for k in ex.sessions if k.startswith("step.")) == 2 and ex.sessions["step.s1"] == 1
