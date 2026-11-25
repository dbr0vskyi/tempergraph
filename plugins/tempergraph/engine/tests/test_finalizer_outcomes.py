"""Every case of a finalizer's return holds offline, and a skipped or failed finalizer is seen (FIN-AC1, FIN-B1 to
FIN-B3, FIN-B8; task AC 1)."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import callable_ref
from tempergraph.catalog import Catalog
from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.run import finalize
from tempergraph.run.finalize import FinalizerResult
from tempergraph.store.layout import state_root_path

from .fixtures.workflows import two_step
from .test_cli import cli
from .test_run import DRAFT, REVIEW, go, judge, records

PR = "https://example.test/acme/notes/pull/7"
CANARY = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
HEADS: list[str] = []


def git_out(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def spec_with(fn: Any, outcomes: tuple[str, ...] = ("opened", "skipped"), **kw: Any) -> Any:
    return dataclasses.replace(two_step(allow_commands=["pytest", "git status", "git push"], **kw),
                               finalizer=callable_ref(fn), finalizer_outcomes=outcomes)


def happy() -> Any:
    return standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])


def finalize_record(repo: Path) -> dict[str, Any]:
    got = [r for r in records(repo) if r["kind"] == "finalize"]
    assert len(got) == 1
    return got[0]


def pushes(ctx: Any) -> FinalizerResult:
    run = ctx.run("git push origin HEAD:refs/heads/published")
    assert not run.not_started, run.extra
    return FinalizerResult(outcome="opened", reason="pushed", url=PR)


def skips(ctx: Any) -> FinalizerResult:
    return FinalizerResult(outcome="skipped", reason="no origin", manual_steps=["add a remote", "push the branch"])


def skips_quietly(ctx: Any) -> FinalizerResult:
    return FinalizerResult(outcome="skipped", reason="nothing to do")


def raises(ctx: Any) -> FinalizerResult:
    HEADS.append(git_out(ctx.workdir, "rev-parse", "HEAD"))
    raise RuntimeError(CANARY)


def sleeps(ctx: Any) -> FinalizerResult:
    time.sleep(2)
    return FinalizerResult(outcome="opened")


def undeclared(ctx: Any) -> FinalizerResult:
    return FinalizerResult(outcome="x" * 300 + "-undeclared")


def long_fields(ctx: Any) -> FinalizerResult:
    return FinalizerResult(outcome="opened", reason=f"{CANARY} " + "r" * 400,
                           manual_steps=[f"step {i} {CANARY} " + "m" * 400 for i in range(6)])


def ledger(repo: Path) -> list[dict[str, Any]]:
    p = state_root_path(repo) / "ledger.jsonl"
    rows = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    return [r for r in rows if r.get("kind") == "run_segment"]


def run_cli(repo: Path, fn: Any) -> tuple[int, Any, str]:
    return cli(repo, happy(), "run", "demo", "notes", "--task-id", "T-1", catalog=Catalog(specs={"demo": spec_with(fn)}))


def test_fin_ac1_a_published_run_pushes_to_the_bare_remote(repo: Path, tmp_path: Path) -> None:  # FIN-AC1, AC 1
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    git_out(repo, "remote", "add", "origin", str(bare))
    out = go(repo, happy(), spec_with(pushes))
    assert out.exit_code is ExitCode.FINISHED, out.message
    rec = finalize_record(repo)
    assert rec["outcome"] == "opened" and rec["reason"] == "pushed" and rec["url"] == PR
    assert "duration_s" in rec and rec["manual_steps"] == []
    row = ledger(repo)[0]
    assert (row["pull_request"]["repo"], row["pull_request"]["number"]) == ("acme/notes", 7)
    assert git_out(bare, "rev-parse", "refs/heads/published") == row["pull_request"]["commit"]


def test_fin_ac1_a_skipped_run_writes_one_line_and_shows_its_steps(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # FIN-AC1, AC 1
    code, _, _ = run_cli(repo, skips)
    assert code == 0
    lines = [ln for ln in capsys.readouterr().err.splitlines() if "skipped" in ln and "demo/T-1" in ln]
    assert len(lines) == 1 and "no origin" in lines[0]
    _, st, _ = cli(repo, None, "status", catalog=Catalog(specs={"demo": spec_with(skips)}))
    fin = st["threads"][0]["finalizer"]
    assert fin["outcome"] == "skipped" and fin["manual_steps"] == ["add a remote", "push the branch"]


def test_fin_ac1_a_skipped_run_with_no_steps_is_quiet(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # FIN-AC1, AC 1
    code, _, _ = run_cli(repo, skips_quietly)
    assert code == 0
    assert "skipped" not in capsys.readouterr().err.replace("demo/T-1: ", "")
    _, st, _ = cli(repo, None, "status", catalog=Catalog(specs={"demo": spec_with(skips_quietly)}))
    assert "finalizer" not in st["threads"][0]


def test_fin_ac1_a_raising_finalizer_is_an_error_record_and_exit_zero(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # FIN-AC1, AC 1
    HEADS.clear()
    out = go(repo, happy(), spec_with(raises))
    assert out.exit_code is ExitCode.FINISHED, out.message
    rec = finalize_record(repo)
    assert rec["outcome"] == "error" and rec["reason"] == "RuntimeError"
    err = capsys.readouterr().err
    assert len([ln for ln in err.splitlines() if "demo/T-1" in ln and "error" in ln and "RuntimeError" in ln]) == 1
    branch = [r for r in records(repo) if r["kind"] != "finalize"] and git_out(repo, "branch", "--list", "tg/*")
    assert HEADS and git_out(repo, "rev-parse", branch.split()[-1]) == HEADS[0]


def test_fin_ac1_a_finalizer_past_its_limit_is_timed_out(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FIN-AC1, AC 1
    monkeypatch.setattr(finalize, "FINALIZER_LIMIT_S", 0.2)
    out = go(repo, happy(), spec_with(sleeps))
    assert out.exit_code is ExitCode.FINISHED, out.message
    rec = finalize_record(repo)
    assert rec["outcome"] == "error" and rec["reason"] == "timed_out"


def test_fin_ac1_an_undeclared_outcome_is_invalid_and_clipped(repo: Path) -> None:  # FIN-AC1, AC 1
    out = go(repo, happy(), spec_with(undeclared))
    assert out.exit_code is ExitCode.FINISHED, out.message
    rec = finalize_record(repo)
    assert rec["outcome"] == "invalid" and 0 < len(rec["reason"]) <= 200


def test_fin_ac1_returned_fields_are_clipped_cut_and_scrubbed(repo: Path) -> None:  # FIN-AC1, AC 1
    out = go(repo, happy(), spec_with(long_fields))
    assert out.exit_code is ExitCode.FINISHED, out.message
    rec = finalize_record(repo)
    assert len(rec["reason"]) <= 200
    assert len(rec["manual_steps"]) == 5 and all(len(s) <= 300 for s in rec["manual_steps"])
    assert CANARY not in json.dumps(rec)
