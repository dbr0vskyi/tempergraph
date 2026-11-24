"""The loop's own sessions think at the run setting `loop_effort`, default `max` (SIL-B17, SIL-AC13)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tempergraph.contracts import Usage
from tempergraph.improve import child, review
from tempergraph.settings import run_values

from .fixtures.workflows import two_step
from .test_ladder_retirement import settle

SUMMARY = {"lenses": {"friction": True}, "fault_fingerprints": ["f1"], "fingerprints": ["f1"]}


class Recorder:
    """A judge executor that keeps every request it is given."""

    name = "claude"

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def run_judge(self, req: Any, views: Any, sink: Any) -> Any:
        self.requests.append(req)
        return SimpleNamespace(ok=True, text="no block", usage=Usage(reported_cost_usd=0.01), model="")


def test_loop_effort_is_a_run_setting_with_default_max() -> None:
    assert run_values(settle({})[0])["loop_effort"] == "max"
    assert run_values(settle({"run.loop_effort": "high"})[0])["loop_effort"] == "high"
    assert [f.code for f in settle({"run.loop_effort": "huge"})[1]] == ["setting_value"]


def test_the_ticket_carries_the_effort(tmp_path: Path) -> None:
    kw: dict[str, Any] = {"dry_run": True, "judge_executor": "claude", "home": tmp_path}
    path = child.hand_off(tmp_path, two_step(), "T-1", "th", SUMMARY, **kw)
    assert path is not None
    ticket = json.loads(path.read_text())
    assert ticket["effort"] == "max" and child.options_of(ticket).effort == "max"
    path = child.hand_off(tmp_path, two_step(), "T-2", "th", SUMMARY, loop_effort="high", **kw)
    assert path is not None and child.options_of(json.loads(path.read_text())).effort == "high"
    assert child.options_of({}).effort == "max"  # a ticket written before the setting existed


def test_every_review_session_is_asked_at_the_effort(tmp_path: Path) -> None:
    # SRV-AC12: `_ask` returns the failure as a third value
    ex = Recorder()
    block, _, failure = review._ask(ex, tmp_path, "wf", "T-1", "draft.1.step", "the view", {}, "medium", "high")
    assert block is None and failure is not None  # the reply has no block, so the reviewer is asked twice
    assert [r.options.effort for r in ex.requests] == ["high", "high"]
    assert all(r.alias == "medium" for r in ex.requests)
    ex = Recorder()
    review._ask(ex, tmp_path, "wf", "T-2", "draft.1.step", "the view", {})
    assert {r.options.effort for r in ex.requests} == {"max"}
