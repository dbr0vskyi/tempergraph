"""Writer branches of a parallel block: their own sibling worktrees, the checkpoint before them and the merge at the
join (WSP-B11, WSP-B12, WSP-B19, WTR-B20, WTR-B23 to WTR-B27), on scripted executors and scratch git repositories."""

from __future__ import annotations

import dataclasses
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

import tempergraph
from tempergraph import git as gitmod
from tempergraph import workspace as workspace_mod
from tempergraph.api import CheckResult, Gate, Judge, Parallel, Routing, Script, Step, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding, SessionRequest, SessionResult, WorkflowSpec
from tempergraph.durability.status import _read as read_thread
from tempergraph.executors.standins import answer, standin
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import ensure_state_root, state_root_path
from tempergraph.workspace import (
    WorkspaceRefused,
    list_worktrees,
    prepare_workspace,
    resolve_workspace,
    worktree_path,
)

from .fixtures.workflows import crit, named
from .test_parallel import recs
from .test_run import MET, registry

NO_SLEEP = RunSettings(sleep=lambda s: None)
SEEN: dict[str, str] = {}  # what a check and a script of the branch `security` were given as their workdir


def security_check(ctx: Any) -> CheckResult:  # runs in a worker process: its workdir travels back as its evidence
    return CheckResult(result="PASS", evidence=str(ctx.workdir), findings=[CheckFinding(status="pass", criterion="c1")])


def security_after(ctx: Any) -> dict[str, str]:
    SEEN["script"] = str(ctx.workdir)
    return {}


def branch_step(unit: str, tools: tuple[str, ...], **gate: Any) -> Any:
    check = security_check if unit == "security" else None
    after = [Script(call=security_after, side_effects="none")] if unit == "security" else []
    return Step(prompt=f"Work on {unit} of {{request}}", tools=list(tools), after=after,
                gate=Gate(check=check, judge=Judge(stance="V."), criteria=[crit("c1")], **gate))


def block_wf(branches: dict[str, tuple[str, ...]] | None = None, gates: dict[str, dict[str, Any]] | None = None,
             report_approval: bool = False) -> WorkflowSpec:
    """`plan`, a block `reviews` of the named branches (their tools declare the writers), then `report`."""
    branches = branches or {"security": ("read", "write"), "perf": ("read",)}
    units: dict[str, Any] = {"plan": branch_step("plan", ("read", "write"))}
    for name, tools in branches.items():
        units[name] = branch_step(name, tools, **(gates or {}).get(name, {}))
    units["reviews"] = Parallel(branches=list(branches))
    units["report"] = branch_step("report", ("read",), approval=report_approval)
    return named(Workflow(order=["plan", *branches, "reviews", "report"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Plan, work in parallel, report")))


class Writers:
    """A stand-in whose sessions write the files named per unit under the workdir they were given, and record it."""

    def __init__(self, writes: dict[str, dict[str, str]] | None = None) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.writes = writes or {}
        self.workdirs: dict[tuple[str, str], Path] = {}
        self.heads: dict[str, str] = {}
        self.saw_early: dict[str, bool] = {}
        self.calls: list[tuple[str, str]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        unit = req.session_key.split(".")[0]
        self.calls.append(("step", unit))
        self.workdirs[("step", unit)] = Path(req.workdir)
        self.heads[unit] = git(Path(req.workdir), "rev-parse", "HEAD").strip()
        self.saw_early[unit] = (Path(req.workdir) / "early.txt").exists()
        for rel, text in self.writes.get(unit, {}).items():
            (Path(req.workdir) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(req.workdir) / rel).write_text(text)
        return answer("Done.", session_id=f"s-{unit}")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        unit = req.session_key.split(".")[0]
        self.calls.append(("judge", unit))
        self.workdirs[("judge", unit)] = Path(req.workdir)
        return answer(MET, tools=("Read",), session_id=f"j-{unit}")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def go(repo: Path, spec: WorkflowSpec, ex: Any, task: str = "W-1") -> Any:
    return start(spec, task, {"request": "x"}, repo, registry(ex), NO_SLEEP)


def worktrees_root(repo: Path) -> Path:
    return repo.parent / "repo.worktrees"


def thread_values(repo: Path, spec: WorkflowSpec, task: str) -> dict[str, Any]:
    snap, _ = read_thread(state_root_path(repo), spec, f"demo/{task}")
    return dict(snap.values)


def subjects(repo: Path, branch: str) -> list[str]:
    return git(repo, "log", "--format=%s", "--end-of-options", branch).splitlines()


# -- the checkpoint (WSP-B19) -----------------------------------------------------------------------------------


def test_entering_a_block_with_a_writer_branch_commits_the_uncommitted_work_first(repo: Path) -> None:  # WSP-AC13
    ex = Writers({"plan": {"early.txt": "an earlier unit left this\n"}, "security": {"sec.txt": "s\n"}})
    out = go(repo, block_wf(), ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    run = "tg/demo/W-1"
    (checkpoint,) = git(repo, "log", "--format=%H", "--grep=checkpoint", "--end-of-options", run).split()
    assert git(repo, "show", "--name-only", "--format=", checkpoint).split() == ["early.txt"]
    writer = "tg/demo/W-1--w-security"
    git(repo, "merge-base", "--is-ancestor", checkpoint, writer)  # the writer branch was cut after the commit
    assert ex.heads["security"] == checkpoint and ex.saw_early["security"]  # and holds the file in its worktree
    assert ex.heads["perf"] == checkpoint  # the read-only branch runs in the run worktree, which is at the commit


def test_a_clean_tree_and_a_block_of_read_only_branches_add_no_commit(repo: Path) -> None:  # WSP-AC14
    clean = go(repo, block_wf(), Writers(), "W-2")  # the earlier unit left nothing uncommitted
    assert clean.exit_code is ExitCode.FINISHED, clean.message
    assert not [s for s in subjects(repo, "tg/demo/W-2") if "checkpoint" in s]
    ex = Writers({"plan": {"early.txt": "uncommitted\n"}})
    readonly = block_wf({"security": ("read",), "perf": ("read",)})
    out = go(repo, readonly, ex, "W-3")
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert git(repo, "rev-list", "--count", "main..tg/demo/W-3").strip() == "0"  # no commit on the run's branch
    assert (Path(ex.workdirs[("step", "plan")]) / "early.txt").exists()  # the file stays uncommitted


@pytest.mark.parametrize("ignored", [True, False])
def test_the_checkpoint_commits_whether_or_not_git_ignores_the_state_root(tmp_path: Path, ignored: bool) -> None:
    # WSP-AC13 (WSP-B19): git 2.39 exits 1 on an exclude pathspec that names an ignored path, so the state root is
    # excluded by the pathspec only where git does not already ignore it
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".gitignore").write_text(".tempergraph/\n" if ignored else "build/\n")
    git(tmp_path, "add", ".gitignore")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "start")
    (tmp_path / ".tempergraph").mkdir()
    (tmp_path / ".tempergraph" / "state.json").write_text("{}\n")
    (tmp_path / "early.txt").write_text("an earlier unit left this\n")
    assert gitmod.stage_all_args(tmp_path)[-1] == ("." if ignored else ":(exclude).tempergraph")
    commit = gitmod.commit_all(tmp_path, "tempergraph: checkpoint before block")
    assert commit and git(tmp_path, "show", "--name-only", "--format=", commit).split() == ["early.txt"]
    assert gitmod.commit_all(tmp_path, "tempergraph: checkpoint before block") == ""  # nothing left to commit


# -- the writer worktrees (WSP-B11, WTR-B20, WTR-B24) -----------------------------------------------------------


def test_each_writer_branch_gets_its_own_sibling_worktree_and_branch(repo: Path) -> None:  # WSP-AC10, WTR-AC2, WTR-AC9
    spec = block_wf({"security": ("read", "write"), "perf": ("read", "edit")}, report_approval=True)
    ex = Writers({"security": {"sec.txt": "s\n"}, "perf": {"perf.txt": "p\n"}})
    out = go(repo, spec, ex, "W-4")
    assert out.exit_code is ExitCode.PAUSED, out.message  # paused after the block: the worktrees still exist
    run_path = worktrees_root(repo) / "demo--W-4"
    base = git(repo, "rev-parse", "main").strip()
    record = thread_values(repo, spec, "W-4")["workspace"]
    kids = {c["name"]: c for c in record["children"]}
    assert sorted(kids) == ["demo--W-4--w-perf", "demo--W-4--w-security"]
    for unit in ("security", "perf"):
        child = kids[f"demo--W-4--w-{unit}"]
        path = worktrees_root(repo) / f"demo--W-4--w-{unit}"
        assert Path(child["path"]) == path and path != run_path and path.is_dir()
        assert child["branch"] == f"tg/demo/W-4--w-{unit}" and child["state"] == "active"
        assert ex.workdirs[("step", unit)] == path  # never the run worktree
        assert ex.heads[unit] == base  # cut from the head the run's branch held before the block
        assert git(path, "rev-parse", "--abbrev-ref", "HEAD").strip() == child["branch"]
        git(repo, "check-ref-format", "--branch", child["branch"])
        assert not child["branch"].startswith("tg/demo/W-4/")  # never a child path of the run branch
    locked = git(repo, "worktree", "list", "--porcelain")
    assert locked.count("locked tempergraph demo/W-4") == 3  # the run worktree and both writers


def test_a_failed_writer_bootstrap_leaves_no_worktree_or_branch(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = workspace_mod.bootstrap  # WSP-AC7

    def failing(main: Path, path: Path, decl: Any, run_command: Any, **kw: Any) -> dict[str, Any]:
        if "--w-" in path.name:
            raise WorkspaceRefused("bootstrap_failed", "setup command 'make' exited 2")
        return original(main, path, decl, run_command, **kw)

    monkeypatch.setattr(workspace_mod, "bootstrap", failing)
    ex = Writers()
    out = go(repo, block_wf({"security": ("read", "write"), "perf": ("read", "write")}), ex, "W-5")
    assert out.exit_code is ExitCode.STOPPED and out.reason == "workspace_refused", out.message
    assert [c for c in ex.calls if c[1] in ("security", "perf")] == []  # no branch started
    assert not list(worktrees_root(repo).glob("*--w-*"))
    assert "--w-" not in git(repo, "branch", "--list")
    assert any(r.get("error") == "workspace_refused" and "bootstrap_failed" in r.get("detail", "")
               for r in recs(repo, "engine_error", "W-5"))
    # the cut itself raises `WorkspaceRefused` naming the failing step and records no child
    root = ensure_state_root(state_root_path(repo))
    rec = prepare_workspace("demo/W-6", resolve_workspace(block_wf(), repo, task_id="W-6"), None, root)
    with pytest.raises(WorkspaceRefused) as err:
        workspace_mod.cut_writers(rec, "demo/W-6", ["security", "perf"], None, root)
    assert err.value.word == "bootstrap_failed" and "security" in str(err.value) and rec.children == []
    assert not list(worktrees_root(repo).glob("*--w-*")) and "--w-" not in git(repo, "branch", "--list")


# -- the workdir of each branch (WSP-B11, WTR-B25) --------------------------------------------------------------


def test_a_writer_branchs_session_judge_check_and_script_run_in_its_worktree(repo: Path) -> None:  # WTR-AC8, WSP-AC12
    SEEN.clear()
    ex = Writers({"security": {"sec.txt": "s\n"}})
    out = go(repo, block_wf(), ex, "W-7")
    assert out.exit_code is ExitCode.FINISHED, out.message
    run_path, writer = worktrees_root(repo) / "demo--W-7", worktrees_root(repo) / "demo--W-7--w-security"
    assert ex.workdirs[("step", "security")] == writer and ex.workdirs[("judge", "security")] == writer
    assert SEEN.get("script") == str(writer) and list(SEEN) == ["script"]
    (check,) = [r for r in recs(repo, "check", "W-7") if r["unit"] == "security"]
    assert check["evidence"] == str(writer)
    assert ex.workdirs[("step", "perf")] == run_path and ex.workdirs[("judge", "perf")] == run_path
    assert [g["token"] for g in recs(repo, "gate", "W-7") if g["unit"] == "security"][-1] == "PROCEED"
    assert (writer / "sec.txt").exists() and not (run_path / "perf.txt").exists()


def test_a_read_only_branch_that_changes_a_file_fails_and_a_writer_does_not(repo: Path) -> None:  # WSP-AC12
    gates = {"perf": {"retry_budget": 0, "on_budget_spent": "stop"}}
    ex = Writers({"perf": {"leak.txt": "a read-only branch wrote this\n"}, "security": {"sec.txt": "s\n"}})
    spec = block_wf(gates=gates)
    out = go(repo, spec, ex, "W-8")
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA, out.message
    stopped = [g for g in recs(repo, "gate", "W-8") if g["unit"] == "perf"][-1]
    assert stopped["token"] == "STOP" and stopped["verdict"] == "RETRY"
    assert "report" not in [u for _, u in ex.calls] and "reviews" not in [r["unit"] for r in recs(repo, "unit_entered", "W-8")]
    attempts = thread_values(repo, spec, "W-8")["attempts"]
    assert attempts["perf"]["error_kind"] == "branch_changed_the_workspace" and attempts["security"]["ok"] is True
    assert [g["token"] for g in recs(repo, "gate", "W-8") if g["unit"] == "security"][-1] == "PROCEED"


# -- the listing and the cleanup (WTR-B23, WTR-B24, WTR-B27) ---------------------------------------------------


def test_the_worktree_listing_shows_the_writers_and_the_path_is_the_runs(repo: Path) -> None:  # WTR-AC9, WTR-AC11, WTR-AC10
    spec = block_wf({"security": ("read", "write"), "perf": ("read", "write")}, report_approval=True)
    ex = Writers({"security": {"sec.txt": "s\n"}, "perf": {"perf.txt": "p\n"}})
    out = go(repo, spec, ex, "W-9")
    assert out.exit_code is ExitCode.PAUSED, out.message
    rows = list_worktrees(repo)
    assert [r["path"] for r in rows if not r.get("writer")] == [str(worktrees_root(repo) / "demo--W-9")]
    writers = {r["writer"]: r for r in rows if r.get("writer")}
    assert sorted(writers) == ["perf", "security"] and all(r["thread"] == "demo/W-9" for r in rows)
    assert writers["security"]["path"] == str(worktrees_root(repo) / "demo--W-9--w-security")
    assert writers["security"]["branch"] == "tg/demo/W-9--w-security" and writers["security"]["exists"]
    assert worktree_path(repo, "demo/W-9") == worktrees_root(repo) / "demo--W-9"  # never a writer's
    done = resume(spec, "W-9", repo, registry(ex), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    for unit in ("security", "perf"):  # `cleanup: never`: every writer worktree and branch is still there
        assert (worktrees_root(repo) / f"demo--W-9--w-{unit}").is_dir()
        assert f"tg/demo/W-9--w-{unit}" in git(repo, "branch", "--list")


def test_no_code_path_force_removes_a_worktree_or_deletes_a_branch() -> None:  # WTR-AC5
    src = Path(tempergraph.__file__).parent
    pattern = re.compile(r'"worktree",\s*"remove",\s*"--force"|"branch",\s*"-[dD]"')
    hits = [str(p.relative_to(src)) for p in src.rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert hits == []


# -- the merge at the join (WSP-B11, WSP-B12) -------------------------------------------------------------------


def declared_order(spec: WorkflowSpec, branches: list[str]) -> WorkflowSpec:
    """The same block, its parallel unit naming `branches` in an order other than the one in `order`."""
    return dataclasses.replace(spec, units={**spec.units, "reviews": Parallel(branches=branches)})


def test_the_join_merges_the_writer_branches_without_fast_forward_in_declared_order(repo: Path) -> None:  # WSP-AC11
    spec = declared_order(block_wf({"security": ("read", "write"), "perf": ("read", "edit")}), ["perf", "security"])
    ex = Writers({"security": {"sec.txt": "s\n"}, "perf": {"perf.txt": "p\n"}})
    out = go(repo, spec, ex, "W-11")
    assert out.exit_code is ExitCode.FINISHED, out.message
    run = "tg/demo/W-11"
    assert sorted(git(repo, "ls-tree", "-r", "--name-only", run).split()) == ["README.md", "perf.txt", "sec.txt"]
    merges = [ln.split() for ln in git(repo, "log", "--merges", "--reverse", "--format=%H %P", run).splitlines()]
    assert len(merges) == 2  # one merge commit per writer branch, none fast-forwarded
    (first, first_parent, first_second), (second, second_parent, second_second) = merges
    assert first_second == git(repo, "rev-parse", "tg/demo/W-11--w-perf").strip()  # `perf` is named first by the block
    assert second_second == git(repo, "rev-parse", "tg/demo/W-11--w-security").strip()
    assert first_parent == git(repo, "rev-parse", "main").strip() and second_parent == first
    assert git(repo, "rev-parse", run).strip() == second
    assert git(repo, "status", "--porcelain", "--untracked-files=all").strip() == ""  # the main checkout is untouched


def test_a_merge_conflict_resets_the_run_branch_and_blocks_the_join_with_the_paths(repo: Path) -> None:  # WSP-AC15
    ex = Writers({"plan": {"shared.txt": "base line\n"},
                  "security": {"shared.txt": "the security line\n", "sec.txt": "s\n"},
                  "perf": {"shared.txt": "the perf line\n"}})
    spec = block_wf({"security": ("read", "write"), "perf": ("read", "write")})
    out = go(repo, spec, ex, "W-12")
    assert out.exit_code is ExitCode.PAUSED and out.reason == "escalation", out.message
    run, run_path = "tg/demo/W-12", worktrees_root(repo) / "demo--W-12"
    (checkpoint,) = git(repo, "log", "--format=%H", "--grep=checkpoint", "--end-of-options", run).split()
    assert git(repo, "rev-parse", run).strip() == checkpoint  # as before the join's first merge, security's merge undone
    assert git(run_path, "status", "--porcelain", "--untracked-files=all").strip() == ""
    assert subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=run_path, capture_output=True).returncode != 0
    assert not (run_path / "sec.txt").exists() and (run_path / "shared.txt").read_text() == "base line\n"
    payload = out.payload
    assert payload["unit"] == "reviews" and payload["reason"] == "merge_conflict"
    assert [b["place"] for b in payload["blockers"]] == ["shared.txt"]  # the pause lists the conflicting path
    assert [c for c in ex.calls if c[1] == "reviews"] == []  # no model session for the join
    assert "report" not in [u for _, u in ex.calls]


def test_a_join_attempt_that_escalates_on_a_merge_conflict_reaches_the_pause() -> None:  # WSP-AC15
    from tempergraph.run.gate import ESCALATE_CAUSES, decide

    assert "merge_conflict" in ESCALATE_CAUSES
    spec = block_wf({"security": ("read", "write"), "perf": ("read", "write")})
    blockers = [{"criterion": "merge", "place": "shared.txt", "problem": "merge conflict in shared.txt", "fix": ""}]
    state = {"attempts": {"reviews": {"attempt": 1, "visit": 1, "ok": True, "escalate": "merge_conflict",
                                      "conflicts": ["shared.txt"]}},
             "judgements": {"reviews": {"verdict": "ESCALATE", "reason": "merge_conflict", "blockers": blockers}},
             "workspace": {"path": "/x"}}
    got = decide(spec, "reviews", state, "W-1")
    assert got["route"]["reviews"]["token"] == "ESCALATE" and got["route"]["reviews"]["node"] == "reviews.human"
    assert got["pause"]["reviews"]["reason"] == "merge_conflict" and got["pause"]["reviews"]["blockers"] == blockers

