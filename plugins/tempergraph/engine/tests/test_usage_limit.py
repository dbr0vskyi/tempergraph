"""A session the account's usage limit ends is read, logged and charged to nothing (BUD-AC15, EVT-AC9; task AC 1,
AC 4, AC 7)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.contracts import InfraCause, SessionResult, Usage
from tempergraph.executors.standins import standin
from tempergraph.store.layout import state_root_path

from .fixtures.workflows import two_step
from .test_council_run import UNIT, Crew, council_wf
from .test_council_run import go as council_go
from .test_run import DRAFT, REVIEW, go, judge, records


def refused(resets_at: float | None, **kw: Any) -> SessionResult:
    return SessionResult(ok=False, usage_limit=True, usage_limit_resets_at=resets_at, usage=Usage(), **kw)


def values(repo: Path, spec: Any, task: str) -> dict[str, Any]:
    from tempergraph.durability.checkpoint import observer_graph, open_readonly, snapshot
    from tempergraph.run.outcome import with_outcome

    with open_readonly(state_root_path(repo) / "checkpoints" / "demo.sqlite") as saver:
        assert saver is not None
        return dict(snapshot(observer_graph(with_outcome(spec), saver), f"demo/{task}").values)


def spent(vals: dict[str, Any], unit: str = "draft") -> tuple[int, int]:
    c = (vals.get("counters") or {}).get(unit) or {}
    return int(c.get("retries", 0)), int(c.get("infra", 0))


@pytest.mark.parametrize("flavour", [{"error_kind": "model"}, {"infra_cause": InfraCause.THROTTLED}])
def test_bud_ac15_a_refused_step_spends_no_retry_and_no_infra_try(repo: Path, flavour: dict[str, Any]) -> None:
    # BUD-AC15, EVT-AC9 (task AC 1, AC 4)
    at = time.time() + 3600
    ex = standin("claude", steps=[refused(at, **flavour)] * 3)
    out = go(repo, ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert [c.kind for c in ex.calls] == ["step"]  # no infra rerun, no backoff
    vals = values(repo, two_step(), "T-1")
    assert spent(vals) == (0, 0)
    att = vals["attempts"]["draft"]
    assert att["escalate"] == "usage_limit" and att["infra_spent"] is False
    assert att["usage_limit_resets_at"] == at
    run = [r for r in records(repo) if r["kind"] == "agent_run"]
    assert len(run) == 1 and run[0]["usage_limit"] is True and run[0]["usage_limit_resets_at"] == at
    assert run[0]["error_kind"] == flavour.get("error_kind")  # the executor's own value stays


def test_evt_ac9_an_ok_session_records_no_limit(repo: Path) -> None:  # EVT-AC9 (task AC 4)
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    runs = [r for r in records(repo) if r["kind"] == "agent_run"]
    assert runs and all(r["usage_limit"] is False and r["usage_limit_resets_at"] is None for r in runs)


def test_bud_ac15_a_failure_without_the_limit_is_counted_as_before(repo: Path) -> None:  # BUD-AC15 (task AC 7)
    failed = SessionResult(ok=False, error_kind="model", usage=Usage())
    ex = standin("claude", steps=[failed, DRAFT, REVIEW], judges=[judge(), judge()])
    out = go(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert [c.request.kind for c in ex.calls][:2] == ["step", "retry"]  # the retry was spent
    assert all(r["usage_limit"] is False for r in records(repo) if r["kind"] == "agent_run")


def test_bud_ac15_a_throttled_session_without_the_limit_is_rerun_until_infra_is_spent(repo: Path) -> None:
    # BUD-AC15 (task AC 7)
    throttled = SessionResult(ok=False, infra_cause=InfraCause.THROTTLED, usage_limit=False, usage=Usage())
    ex = standin("claude", steps=[throttled] * 3)
    out = go(repo, ex)
    assert out.exit_code is ExitCode.BUDGET_OR_INFRA and out.reason == "infra"
    assert len(ex.calls) == 3


def test_bud_ac15_a_refused_council_member_is_not_a_missing_answer(repo: Path) -> None:  # BUD-AC15 (task AC 1)
    at = time.time() + 3600
    ex = Crew({("b", 0): [refused(at, error_kind="model")]})
    out = council_go(repo, council_wf(), ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    vals = values(repo, council_wf(), "C-1")
    assert spent(vals, UNIT) == (0, 0)
    att = vals["attempts"][UNIT]
    assert att["escalate"] == "usage_limit" and att["infra_spent"] is False and att["usage_limit_resets_at"] == at
    assert att["ok"] is False and not ex.of("chair")  # no tally and no chair on a refused round


def test_bud_ac15_a_refused_chair_spends_nothing(repo: Path) -> None:  # BUD-AC15 (task AC 1)
    at = time.time() + 3600
    ex = Crew(chair=refused(at))
    out = council_go(repo, council_wf(), ex)
    assert out.exit_code is ExitCode.PAUSED, out.message
    vals = values(repo, council_wf(), "C-1")
    assert spent(vals, UNIT) == (0, 0)
    att = vals["attempts"][UNIT]
    assert att["escalate"] == "usage_limit" and att["infra_spent"] is False and att["usage_limit_resets_at"] == at
