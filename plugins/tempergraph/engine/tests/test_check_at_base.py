"""A command run at the run's base commit (CHK-B18 to CHK-B21; CHK-AC8 to CHK-AC11)."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import CheckResult, callable_ref
from tempergraph.constants import ExitCode
from tempergraph.contracts import Criterion, GateSpec
from tempergraph.executors.standins import standin
from tempergraph.run import check_worker
from tempergraph.run.check_worker import run_in_worker
from tempergraph.run.checks import CheckContext, GitFacts, run_check
from tempergraph.store.layout import run_dir, state_root_path

from .test_check_repeat import idle, spec_of, steps, writes
from .test_run import go, records

ALLOW = ("git show", "git status", "pwd", "python -m timeit")
ABSENT = "git show HEAD:absent.txt"  # exits 128 in a workspace and at the base alike


def g(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def commit(repo: Path, name: str, text: str) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    g(repo, "add", name)
    g(repo, "commit", "-q", "-m", f"add {name}")
    return g(repo, "rev-parse", "HEAD").strip()


def repo_state(repo: Path) -> tuple[str, str, str]:
    return g(repo, "worktree", "list"), g(repo, "branch", "--list"), g(repo, "status", "--porcelain")


def make(repo: Path, tmp_path: Path, base: str | None, *, store: Path | None = None, visit: int = 1, attempt: int = 1,
         base_dir: Path | None = None, tag: str = "a") -> CheckContext:
    return CheckContext(unit="draft", workdir=repo, request={}, visit=visit, attempt=attempt, allow=ALLOW,
                        git=GitFacts(base=base or "", head=g(repo, "rev-parse", "HEAD").strip()),
                        out_dir=tmp_path / f"out-{tag}", reuse_store=store, base_dir=base_dir,
                        deadline_at=time.monotonic() + 120)


@pytest.fixture
def base_repo(repo: Path) -> tuple[Path, str]:
    """A repository whose base commit holds README.md and where.txt, with a commit and an uncommitted edit after it."""
    base = commit(repo, "where.txt", str(repo))
    commit(repo, "sub/inner.txt", "inner at head\n")
    (repo / "README.md").write_text("committed later\n")
    g(repo, "commit", "-q", "-am", "edit README")
    (repo / "README.md").write_text("uncommitted edit\n")
    (repo / "extra.txt").write_text("untracked\n")
    return repo, base


def test_a_run_at_the_base_sees_the_base_commit(base_repo: tuple[Path, str], tmp_path: Path) -> None:
    # CHK-AC8, AC 1
    repo, base = base_repo
    before = repo_state(repo)
    ctx = make(repo, tmp_path, base, base_dir=tmp_path / "bases")
    here = ctx.run("git show HEAD:sub/inner.txt")
    there = ctx.run("git show HEAD:sub/inner.txt", at_base=True)
    assert here.exit_code == 0 and not here.at_base
    assert there.at_base and there.finished and there.exit_code != 0  # the base commit has no sub/inner.txt
    shown = ctx.run("git show HEAD:README.md", at_base=True)
    assert shown.at_base and shown.exit_code == 0
    assert Path(shown.output_path).read_text() == "scratch\n"  # the file as the base commit has it
    assert shown.to_json()["at_base"] is True and here.to_json()["at_base"] is False
    assert repo_state(repo) == before and (repo / "README.md").read_text() == "uncommitted edit\n"
    assert [r.at_base for r in ctx.runs] == [False, True, True]


def test_a_run_at_the_base_starts_in_the_same_folder(repo: Path, tmp_path: Path) -> None:
    # CHK-AC8: `cd sub && ...` starts in `sub` of the base checkout
    base = commit(repo, "sub/inside.txt", "x")
    commit(repo, "sub/later.txt", "y")
    ctx = make(repo, tmp_path, base, base_dir=tmp_path / "bases")
    got = ctx.run("cd sub && pwd", at_base=True)
    assert got.at_base and got.exit_code == 0 and got.tail == "<workdir>/sub"
    listed = ctx.run("cd sub && git status --short", at_base=True)
    assert listed.at_base and listed.exit_code == 0 and listed.tail == ""  # a clean checkout of the base commit


def test_a_run_at_the_base_that_cannot_start_starts_nothing(repo: Path, tmp_path: Path) -> None:
    # CHK-AC8: no base commit, a base commit that is not a full commit id, a folder the base commit lacks
    before = repo_state(repo)
    bases = tmp_path / "bases"
    head = g(repo, "rev-parse", "HEAD").strip()
    for base in ("", "main", head[:12], "--upload-pack=x"):
        ctx = make(repo, tmp_path, base, base_dir=bases)
        r = ctx.run("git show HEAD:README.md", at_base=True)
        assert r.not_started and r.at_base and r.exit_code is None, base
        assert ctx.runs == [r]
    ctx = make(repo, tmp_path, head, base_dir=bases)
    r = ctx.run("cd newpkg && git show HEAD:x", at_base=True)
    assert r.not_started and r.at_base
    assert not bases.exists() or not list(bases.iterdir())  # nothing was checked out
    assert repo_state(repo) == before


def test_a_run_at_the_base_shows_no_path_of_the_workspace(base_repo: tuple[Path, str], tmp_path: Path) -> None:
    # CHK-AC4: the tail and program path hold neither the workspace nor the checkout path
    repo, base = base_repo
    ctx = make(repo, tmp_path, base, base_dir=tmp_path / "bases")
    printed = ctx.run("git show HEAD:where.txt", at_base=True)  # a file of the base commit that names the workspace
    where = ctx.run("pwd", at_base=True)
    for r in (printed, where):
        assert r.at_base and r.exit_code == 0
        for text in (r.tail, r.program_path):
            assert str(repo) not in text and str(tmp_path / "bases") not in text
    assert printed.tail == "<workdir>" and where.tail == "<workdir>"


def test_a_run_at_the_base_is_reused_in_the_visit(base_repo: tuple[Path, str], tmp_path: Path) -> None:
    # CHK-AC9, AC 5: no process, no checkout, although the workspace changed
    repo, base = base_repo
    store = tmp_path / "runs.jsonl"
    first = make(repo, tmp_path, base, store=store, base_dir=tmp_path / "b1", tag="1")
    a = first.run("git show HEAD:README.md", reuse=True, at_base=True)
    assert a.at_base and not a.reused and a.exit_code == 0
    (repo / "extra.txt").write_text("changed between the attempts\n")
    second = make(repo, tmp_path, base, store=store, attempt=2, base_dir=tmp_path / "b2", tag="2")
    b = second.run("git show HEAD:README.md", reuse=True, at_base=True)
    assert b.reused and b.at_base and b.exit_code == 0
    assert not (tmp_path / "b2").exists() or not list((tmp_path / "b2").iterdir())  # no checkout for a hit
    assert second.base_checkout is None
    nxt = make(repo, tmp_path, base, store=store, visit=2, base_dir=tmp_path / "b3", tag="3")
    c = nxt.run("git show HEAD:README.md", reuse=True, at_base=True)
    assert c.at_base and not c.reused  # the next visit starts it again
    other = make(repo, tmp_path, base, store=store, base_dir=tmp_path / "b4", tag="4")
    assert not other.run("git show HEAD:README.md", reuse=False, at_base=True).reused  # reuse is asked for


def test_a_run_killed_at_the_limit_is_not_stored(base_repo: tuple[Path, str], tmp_path: Path) -> None:
    # CHK-AC9: starts again after a run killed at the limit
    repo, base = base_repo
    store = tmp_path / "runs.jsonl"
    cmd = "python -m timeit -n 1000000000 pass"
    for n in (1, 2):
        ctx = make(repo, tmp_path, base, store=store, base_dir=tmp_path / f"b{n}", tag=str(n))
        r = ctx.run(cmd, timeout_s=1, reuse=True, at_base=True)
        assert r.at_base and r.timed_out and not r.finished and not r.reused
    assert not store.exists() or not store.read_text().strip()


def test_a_workspace_key_never_matches_a_base_key(base_repo: tuple[Path, str], tmp_path: Path) -> None:
    # CHK-AC1: the two kinds of run are stored apart
    repo, base = base_repo
    store = tmp_path / "runs.jsonl"
    cmd = "git show HEAD:README.md"
    ws = make(repo, tmp_path, base, store=store, base_dir=tmp_path / "b1", tag="1").run(cmd, reuse=True)
    assert not ws.reused and not ws.at_base
    at = make(repo, tmp_path, base, store=store, base_dir=tmp_path / "b2", tag="2").run(cmd, reuse=True, at_base=True)
    assert at.at_base and not at.reused  # the workspace run is not the base run
    again = make(repo, tmp_path, base, store=store, base_dir=tmp_path / "b3", tag="3").run(cmd, reuse=True)
    assert again.reused and not again.at_base  # and the base run is not the workspace run
    assert {json.loads(ln)["at_base"] for ln in store.read_text().splitlines()} == {False, True}


# --- nothing is left behind ----------------------------------------------------------------------------------


def runs_at_base(ctx: Any) -> CheckResult:
    r = ctx.run("git show HEAD:README.md", at_base=True)
    return CheckResult(result="PASS", evidence=f"at base {r.exit_code}")


def raises_at_base(ctx: Any) -> CheckResult:
    ctx.run("git show HEAD:README.md", at_base=True)
    raise RuntimeError("after the base run")


def hangs_at_base(ctx: Any) -> CheckResult:
    r = ctx.run("git show HEAD:README.md", at_base=True)
    seen = ctx.base_checkout
    Path(ctx.settings["seen"]).write_text(f"{seen} {seen is not None and seen.is_dir()} {r.exit_code}")
    time.sleep(60)
    return CheckResult(result="PASS")


def gate(fn: Any, timeout: int = 60) -> GateSpec:
    return GateSpec(check=callable_ref(fn), check_timeout_s=timeout, criteria=(Criterion(text="x", id="c-file"),))


def test_the_base_checkout_is_gone_after_a_check_returns(base_repo: tuple[Path, str], tmp_path: Path) -> None:
    # CHK-AC10, CHK-AC2, AC 1
    repo, base = base_repo
    before = repo_state(repo)
    bases = tmp_path / "bases"
    res, _ = run_check(gate(runs_at_base), make(repo, tmp_path, base, base_dir=bases))
    assert res.result == "PASS" and res.runs[0]["at_base"] is True and res.runs[0]["exit_code"] == 0
    assert not list(bases.iterdir())
    assert repo_state(repo) == before
    alone = make(repo, tmp_path, base, tag="own")  # no folder given: the context makes one and removes it
    res, _ = run_check(gate(runs_at_base), alone)
    assert res.runs[0]["at_base"] is True and alone.base_checkout is None
    assert repo_state(repo) == before


def test_the_base_checkout_is_gone_after_a_check_raises(base_repo: tuple[Path, str], tmp_path: Path) -> None:
    # CHK-AC10, CHK-AC2, AC 1
    repo, base = base_repo
    before = repo_state(repo)
    bases = tmp_path / "bases"
    res, notes = run_check(gate(raises_at_base), make(repo, tmp_path, base, base_dir=bases))
    assert res.result == "FAIL" and notes == ["check_raised: RuntimeError"]
    assert not list(bases.iterdir())
    assert repo_state(repo) == before


def test_the_base_checkout_is_gone_after_a_worker_is_ended(base_repo: tuple[Path, str], tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    # CHK-AC10, CHK-AC2, AC 1
    repo, base = base_repo
    before = repo_state(repo)
    monkeypatch.setattr(check_worker, "WORKER_GRACE_S", 1)
    seen = tmp_path / "seen.txt"
    ctx = make(repo, tmp_path, base, base_dir=tmp_path / "bases")
    ctx.settings = {"seen": str(seen)}
    # the worker imports the engine and makes the base checkout before it writes `seen`: under a loaded suite
    # that takes more than a second, so the limit leaves room for it and still ends the 60 s sleep
    res, notes = run_in_worker(gate(hangs_at_base, timeout=8), ctx)
    assert res.result == "FAIL" and res.environmental and notes == ["check_worker_limit"]
    folder, exists, code = seen.read_text().split()
    assert exists == "True" and code == "0" and folder != "None"  # the checkout was there while the worker ran
    assert not Path(folder).exists() and not Path(folder).parent.exists()
    assert repo_state(repo) == before


# --- an environmental result with both runs --------------------------------------------------------------------


def same_failure(ctx: Any) -> CheckResult:
    here = ctx.run(ABSENT)
    there = ctx.run(ABSENT, reuse=True, at_base=True)
    return CheckResult(result="FAIL", environmental=True, facts={f"k{i}": "v" for i in range(25)},
                       evidence=f"`{ABSENT}` exit {here.exit_code} at the gate and {there.exit_code} at the base")


def test_an_environmental_fail_keeps_its_evidence_and_both_runs(base_repo: tuple[Path, str], tmp_path: Path) -> None:
    # CHK-AC11, CHK-AC7, AC 4
    repo, base = base_repo
    res, _ = run_in_worker(gate(same_failure), make(repo, tmp_path, base, base_dir=tmp_path / "bases"))
    assert res.result == "FAIL" and res.environmental
    assert "exit 128 at the gate and 128 at the base" in res.evidence
    assert [(r["exit_code"], r["at_base"]) for r in res.runs] == [(128, False), (128, True)]
    assert len(res.facts) == 20  # CHK-AC7: facts of an environmental result are kept, at most 20


def test_an_environmental_fail_at_a_gate_escalates_with_no_judge_and_no_retry(repo: Path) -> None:
    # CHK-AC11, CHK-AC5, AC 1
    spec = dataclasses.replace(spec_of(same_failure), allow_commands=("pytest", "git show"))
    ex = standin("claude", steps=steps(writes("a1.txt"), idle))
    out = go(repo, ex, spec, task="E-1")
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "escalation"
    assert out.payload["reason"] == "environmental" and out.payload["unit"] == "draft"
    assert [c.kind for c in ex.calls] == ["step"]  # no judge session, no second step
    checks = [r for r in records(repo, "E-1") if r["kind"] == "check"]
    assert len(checks) == 1 and checks[0]["environmental"] is True
    assert "exit 128 at the gate and 128 at the base" in checks[0]["evidence"]
    store = run_dir(state_root_path(repo), "demo", "E-1") / "command_runs.jsonl"  # the run at the base was recorded
    rows = [json.loads(ln) for ln in store.read_text().splitlines()]
    assert [(r["at_base"], r["run"]["exit_code"], r["run"]["at_base"]) for r in rows] == [(True, 128, True)]
