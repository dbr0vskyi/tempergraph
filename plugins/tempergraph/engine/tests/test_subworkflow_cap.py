"""One cap over a parent and its child: a child attempt over the run cost cap drains the run, its spend counts against the run and the day, and reports show it apart (SWF-B4; SWF-AC1; task AC 4)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.standins import answer, standin
from tempergraph.observe.report import by_unit, threads
from tempergraph.run.log import split_costs
from tempergraph.run.runner import ledger_rows
from tempergraph.store.layout import state_root_path

from .fixtures.subworkflows import home_dir, register_workflow
from .test_run import judge
from .test_subworkflow_run import go, parent, records

CAP = 5.0


def costly_draft() -> SessionResult:
    return answer("Wrote notes.md\nARTIFACT notes: notes.md", cost=4.0, session_id="s-draft")


def costly_work(req: SessionRequest) -> SessionResult:
    (req.workdir / "overview.md").write_text("an overview\n")
    return answer("Made the overview\nARTIFACT overview: overview.md", cost=1.5, session_id="s-work")


@pytest.fixture
def capped(tmp_path: Path, repo: Path) -> Path:
    """A parent with a run cost cap of 5 USD; its `draft` costs 4 USD and the child's `work` 1.5 USD, so the child's
    next attempt (its outcome gate) would start over the cap."""
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"])
    ex = standin("claude", steps=[costly_draft(), costly_work], judges=[judge(), judge()])
    out = go(repo, ex, dataclasses.replace(parent(), run_cost_cap_usd=CAP))
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA == 5 and out.reason == "cost_cap", (out.exit_code, out.message)
    return repo


def test_a_child_attempt_over_the_cap_drains_the_run_with_exit_5(capped: Path) -> None:  # SWF-AC1, AC 4
    rows = records(capped)
    exit_row = [r for r in rows if r["kind"] == "run_exit"][-1]
    assert exit_row["exit_code"] == 5 and exit_row["reason"] == "cost_cap"
    started = [r["unit"] for r in rows if r["kind"] == "attempt_start" and r.get("child")]
    assert started == ["work", "work"]  # the child's step and its judge ran; its outcome gate did not start


def test_the_childs_spend_counts_against_the_run_and_the_daily_cap(capped: Path) -> None:  # SWF-AC1, AC 4
    exit_row = [r for r in records(capped) if r["kind"] == "run_exit"][-1]
    assert exit_row["cost"]["reported"] == pytest.approx(4.0 + 1.5 + 0.01 * 2)  # draft, its judge, the child's work, its judge
    segment = [r for r in ledger_rows(state_root_path(capped)) if r.get("kind") == "run_segment"][-1]
    assert segment["cost"]["reported"] == exit_row["cost"]["reported"]  # the ledger row the daily cap sums


def test_the_report_shows_the_childs_spend_on_its_own_line(capped: Path) -> None:  # SWF-AC1, AC 4
    rows = {r["unit"]: r for r in by_unit(list(threads(state_root_path(capped))))}
    assert rows["setup/work"]["total"]["reported_usd"] == pytest.approx(1.5 + 0.01)
    assert rows["draft"]["total"]["reported_usd"] == pytest.approx(4.0 + 0.01)  # the parent's own steps do not include it
    assert "work" not in rows
    spent = split_costs(records(capped))
    assert spent["setup"]["reported"] == pytest.approx(1.51) and spent[None]["reported"] == pytest.approx(4.01)
