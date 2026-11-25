"""A writing contest: each slot in its own sibling worktree cut after a checkpoint commit, only the winner merged into
the run branch (CTS-AC4; CTS-B5, CTS-B6, CTS-B7, CTS-B9, WSP-B11, WSP-B12, WSP-B19, WTR-B20)."""

from __future__ import annotations

import dataclasses
import json
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


class PerAttempt(Writes):
    """`Writes` that writes `<slot> attempt <n>` (n counts the slot's own runs) and keeps every run's directory and head."""

    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.runs: list[tuple[str, Path, str]] = []  # (slot, working directory, head at the start), in order

    def run_step(self, req: Any, sink: Any) -> Any:
        slot = self.whose(req)
        if slot in self.content:
            n = 1 + sum(1 for s, _, _ in self.runs if s == slot)
            self.content = {**self.content, slot: f"{slot} attempt {n}\n"}
            self.runs.append((slot, Path(req.workdir), git(Path(req.workdir), "rev-parse", "HEAD").strip()))
        return super().run_step(req, sink)


def retried() -> PerAttempt:
    return PerAttempt({"s1": "", "s2": ""}, judges={"s1": [BLOCKED, BOTH_MET], "s2": [BLOCKED, BOTH_MET]})


def merges_of(repo: Path) -> list[list[str]]:
    """The merge commits of the run branch, newest first: `[hash, first parent, second parent]`."""
    return [ln.split() for ln in git(repo, "log", "--merges", "--format=%H %P", RUN).splitlines()]


def test_a_retry_of_a_writer_contest_runs_in_fresh_worktrees_of_its_attempt_WSP_AC26(repo: Path) -> None:  # WSP-AC26 (WSP-B20, WSP-B19, WTR-AC14)
    ex = retried()
    out = go(repo, writing(), ex)  # the default scope: the winner's slot alone runs again
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert not [r for r in recs(repo, "engine_error") if r.get("error") == "workspace_refused"]
    first, second = recs(repo, "contest")
    (again,) = [s["name"] for s in second["slots"]]
    assert again == first["slots"][first["winner"] - 1]["name"]
    root = worktrees_root(repo)
    assert sorted(s for s, _, _ in ex.runs[:2]) == ["s1", "s2"] and ex.runs[2][0] == again  # the slots of one attempt overlap
    assert ex.runs[2][1] == root / f"demo--C-1--s2-{again}"  # fresh, named by its attempt
    assert {s: d for s, d, _ in ex.runs[:2]} == {"s1": root / "demo--C-1--s-s1", "s2": root / "demo--C-1--s-s2"}  # WSP-B20
    assert git(ex.runs[2][1], "rev-parse", "--abbrev-ref", "HEAD").strip() == f"{RUN}--s2-{again}"
    merged_first = merges_of(repo)[-1][0]  # the first pick's merge: the head the retry's slot was cut from
    assert ex.runs[2][2] == merged_first
    for old in ("s1", "s2"):  # the first attempt's branches are left as they are
        assert git(repo, "rev-parse", f"{RUN}--s-{old}").strip()
        assert (root / f"demo--C-1--s-{old}").exists()


def test_the_pick_of_a_later_attempt_merges_only_its_own_winner_WSP_AC29(repo: Path) -> None:  # WSP-AC29 (WSP-B22, CTS-B7)
    ex = PerAttempt({"s1": "", "s2": ""}, judges={"s1": [BLOCKED, BOTH_MET], "s2": [BLOCKED, BOTH_MET]},
                    costs={"s1": 0.3, "s2": 0.1})  # `s2` is the cheaper: the winner of both attempts
    out = go(repo, writing(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    merges = merges_of(repo)
    assert [s for s in subjects(repo, RUN) if s.startswith("Merge contest slot")] == ["Merge contest slot s2 of pick"] * 2
    assert git(repo, "rev-parse", f"{RUN}--s2-s2").strip() == merges[0][2]  # the second merge takes the second attempt's branch
    assert git(repo, "rev-parse", f"{RUN}--s-s2").strip() == merges[1][2]
    parents = {p for m in merges for p in m[2:]}
    assert git(repo, "rev-parse", f"{RUN}--s-s1").strip() not in parents  # the losing slot's branch is never merged
    assert git(repo, "show", f"{RUN}:a.py") == "s2 attempt 2\n"


def test_a_retry_under_all_cuts_every_slot_in_fresh_worktrees_WSP_AC27(repo: Path) -> None:  # WSP-AC27 (WSP-B20, CTS-B8)
    ex = retried()
    out = go(repo, writing(retry_scope="all"), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert not [r for r in recs(repo, "engine_error") if r.get("error") == "workspace_refused"]
    root = worktrees_root(repo)
    assert sorted(s for s, _, _ in ex.runs) == ["s1", "s1", "s2", "s2"]
    assert {s: d for s, d, _ in ex.runs[2:]} == {"s1": root / "demo--C-1--s2-s1", "s2": root / "demo--C-1--s2-s2"}
    heads = {h for _, _, h in ex.runs[2:]}
    assert heads == {merges_of(repo)[-1][0]}  # both cut at the head the second attempt began from
    for slot in ("s1", "s2"):
        assert git(repo, "rev-parse", f"{RUN}--s2-{slot}").strip()


def test_the_first_run_after_a_back_is_a_later_attempt_with_fresh_worktrees_WSP_AC27(repo: Path) -> None:  # WSP-AC27 (WSP-B20)
    rows = [{"n": 1, "status": "UNMET", "evidence": "the plan is wrong", "defect_in": "doc", "no_change": False},
            {"n": 2, "status": "MET", "evidence": "x:1", "defect_in": None, "no_change": False}]
    back = "R.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.8}) + "\n```"
    ex = PerAttempt({"s1": "", "s2": ""}, judges={"s1": [back, BOTH_MET], "s2": [back, BOTH_MET]})
    spec = writing(plan=True, gate={"back_targets": ["plan"]})
    out = go(repo, spec, ex, flags={"plan.retry_budget": 2})
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert not [r for r in recs(repo, "engine_error") if r.get("error") == "workspace_refused"]
    root = worktrees_root(repo)
    assert {s: d for s, d, _ in ex.runs[:2]} == {"s1": root / "demo--C-1--s-s1", "s2": root / "demo--C-1--s-s2"}  # `--s-<slot>`
    assert {s: d for s, d, _ in ex.runs[2:]} == {"s1": root / "demo--C-1--s2-s1", "s2": root / "demo--C-1--s2-s2"}  # attempt 2
    assert len(recs(repo, "contest")) == 2


def test_the_records_of_an_earlier_attempt_keep_their_state_WSP_AC28(repo: Path) -> None:  # WSP-AC28 (WSP-B21, WTR-B23)
    ex = PerAttempt({"s1": "", "s2": ""}, judges={"s1": [BLOCKED, BOTH_MET], "s2": [BLOCKED, BOTH_MET]},
                    costs={"s1": 0.3, "s2": 0.1})  # `s2` wins both picks
    spec = writing()
    out = go(repo, spec, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    children = thread_values(repo, spec, "C-1")["workspace"]["children"]
    old = {c["unit"]: c for c in children if "visit" not in c}
    new = {c["unit"]: c for c in children if c.get("visit") == 2}
    assert set(old) == {"pick.s1", "pick.s2"} and set(new) == {"pick.s2"}  # the retry cut the winner's slot alone
    assert (old["pick.s1"]["state"], old["pick.s2"]["state"]) == ("discarded", "active")  # as the first pick left them
    assert new["pick.s2"]["state"] == "active"  # the second pick's winner
    assert all(Path(c["path"]).exists() for c in children)  # nothing was deleted
    assert old["pick.s2"]["path"] != new["pick.s2"]["path"] and old["pick.s2"]["branch"] != new["pick.s2"]["branch"]
