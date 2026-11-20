"""The check worker and check results (CHK §2.4, §2.6, §4)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import CheckResult, callable_ref
from tempergraph.contracts import CheckFinding, Criterion, GateSpec
from tempergraph.run import check_worker
from tempergraph.run.check_worker import run_in_worker
from tempergraph.run.checks import CheckContext, normalise


def passing(ctx: Any) -> CheckResult:
    print("noise on stdout")  # never mixes with the result
    text = ctx.read_text("notes.md")
    return CheckResult(result="PASS", evidence=f"{ctx.unit} read {len(text)} chars", facts={"chars": str(len(text))},
                       findings=[CheckFinding(status="pass", criterion="c-file", place="notes.md")])


def raising(ctx: Any) -> CheckResult:
    raise RuntimeError("bug in the check")


def hanging(ctx: Any) -> CheckResult:
    time.sleep(60)
    return CheckResult(result="PASS")


def not_a_result(ctx: Any) -> Any:
    return {"result": "PASS"}


def gate(fn: Any, timeout: int = 60) -> GateSpec:
    return GateSpec(check=callable_ref(fn), check_timeout_s=timeout, criteria=(Criterion(text="x", id="c-file"),))


def ctx(tmp_path: Path) -> CheckContext:
    (tmp_path / "notes.md").write_text("hello")
    return CheckContext(unit="draft", workdir=tmp_path, request={"request": "r"}, out_dir=tmp_path / "out")


def test_worker_returns_the_result(tmp_path: Path) -> None:
    res, notes = run_in_worker(gate(passing), ctx(tmp_path))
    assert res.result == "PASS" and res.evidence == "draft read 5 chars" and res.facts == {"chars": "5"}
    assert res.findings[0].criterion == "c-file" and notes == []


def test_raising_check_is_a_workflow_fault(tmp_path: Path) -> None:
    res, notes = run_in_worker(gate(raising), ctx(tmp_path))
    assert res.result == "FAIL" and not res.environmental and "RuntimeError" in res.evidence  # CHK §4
    assert "bug in the check" not in res.evidence  # the exception type only


def test_invalid_return_fails(tmp_path: Path) -> None:
    res, _ = run_in_worker(gate(not_a_result), ctx(tmp_path))
    assert res.result == "FAIL" and not res.environmental


def test_worker_past_its_limit_is_environmental(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_worker, "WORKER_GRACE_S", 1)
    t0 = time.monotonic()
    res, notes = run_in_worker(gate(hanging, timeout=1), ctx(tmp_path))
    assert res.result == "FAIL" and res.environmental and notes == ["check_worker_limit"]
    assert time.monotonic() - t0 < 30


def test_normalise_takes_the_worst_finding() -> None:
    res, notes = normalise(CheckResult(result="PASS", findings=[CheckFinding(status="fail", criterion="a")],
                                       facts={"Bad Key": "x", "ok": "y" * 300}))
    assert res.result == "FAIL" and res.facts.keys() == {"ok"} and len(res.facts["ok"]) <= 200
    assert any(n.startswith("check_result_mismatch") for n in notes)
    assert any(n.startswith("fact_key_invalid") for n in notes)


def test_read_outside_the_workspace_is_refused(tmp_path: Path) -> None:
    c = ctx(tmp_path / "ws") if (tmp_path / "ws").mkdir() is None else None
    assert c is not None
    with pytest.raises(PermissionError):
        c.read_text("../outside.txt")


def counting(ctx: Any) -> CheckResult:
    r = ctx.run("git --version", reuse=True)
    return CheckResult(result="PASS" if r.finished else "FAIL", evidence=f"reused={r.reused}")


def test_command_runs_are_reused_while_the_tree_is_unchanged(repo: Path) -> None:  # CHK §2.3 Reuse
    (repo / "notes.md").write_text("one")
    store = repo / ".tempergraph" / "command_runs.jsonl"

    def context() -> CheckContext:
        return CheckContext(unit="draft", workdir=repo, request={}, out_dir=repo / ".tempergraph" / "out",
                            allow=("git --version",), reuse_store=store)

    first, _ = run_in_worker(gate(counting), context())
    again, _ = run_in_worker(gate(counting), context())
    assert (first.evidence, again.evidence) == ("reused=False", "reused=True")
    assert again.runs[0]["reused"] is True and again.runs[0]["exit_code"] == 0
    (repo / "notes.md").write_text("two")  # a changed file changes the key
    third, _ = run_in_worker(gate(counting), context())
    assert third.evidence == "reused=False"
