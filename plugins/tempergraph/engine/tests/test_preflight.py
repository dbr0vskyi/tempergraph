"""Registry, judge executor selection and the preflight refusals (EXI-B16, EXI-B17, EXI-B24, EXI-B1, B10, B12;
EXI-AC2, AC-8)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate, Judge, Step
from tempergraph.contracts import ProbeReport, SessionOptions
from tempergraph.executors.registry import NoJudgeExecutor, Registry, UnknownExecutor, default_registry
from tempergraph.executors.standins import ScriptedExecutor, standin

from .conftest import hash_tree
from .fixtures.workflows import crit, two_step


def reg(*names: str, **probe: ProbeReport) -> Registry:
    r = Registry()
    for n in names:
        ex = standin(n)
        if n in probe:
            ex.probe_report = probe[n]
        r.register(ex)
    return r


def with_step(spec: Any, unit: str, **fields: Any) -> Any:
    u = spec.units[unit]
    step = dataclasses.replace(u.step, **fields)
    return dataclasses.replace(spec, units={**spec.units, unit: dataclasses.replace(u, step=step)})


def test_registry_order_and_unknown() -> None:
    r = reg("antigravity", "claude")
    assert r.available() == ["claude", "antigravity"]
    with pytest.raises(UnknownExecutor):
        r.get("messages-api")
    with pytest.raises(ValueError):
        r.register(ScriptedExecutor(caps=dataclasses.replace(standin("claude").caps, name="my-cli")))


def test_shipped_registry_is_claude_only() -> None:
    assert default_registry().available() == ["claude"]  # ADR-0091


def test_judge_selection_order() -> None:
    r = reg("claude", "antigravity", "messages-api")
    assert r.judge_executor("antigravity", None, None) == "claude"  # EXI-B10
    assert r.judge_executor("messages-api", None, None) == "messages-api"
    assert r.judge_executor("claude", "messages-api", None) == "messages-api"
    assert r.judge_executor("claude", "messages-api", "antigravity") == "antigravity"
    with pytest.raises(NoJudgeExecutor):
        reg("antigravity").judge_executor("antigravity", None, None)


def test_clean_workflow_passes(repo: Path) -> None:
    before = hash_tree(repo)
    rep = preflight_of(two_step(), reg("claude"))
    assert rep.ok, rep.refusals
    assert rep.judges == {"draft": "claude", "review": "claude"}
    assert hash_tree(repo) == before  # nothing created (EXI-AC2)


def preflight_of(spec: Any, registry: Registry, **kw: Any) -> Any:
    from tempergraph.executors.preflight import preflight

    return preflight(spec, registry, **kw)


def codes(rep: Any) -> list[str]:
    return [f.code for f in rep.refusals]


def test_unknown_executor_refused() -> None:
    assert "executor-unknown" in codes(preflight_of(two_step(default_executor="antigravity"), reg("claude")))


def test_probe_failure_refused() -> None:
    rep = preflight_of(two_step(), reg("claude", claude=ProbeReport(ok=False, reason="signed_out")))
    assert rep.first() is not None and rep.first().code == "executor-probe-failed"
    assert "signed_out" in rep.first().message


def test_qualified_alias_not_in_binding_table() -> None:
    assert "alias-unbound" in codes(preflight_of(with_step(two_step(), "draft", model="claude:deep"), reg("claude")))


def test_tool_unmapped_refused() -> None:
    spec = with_step(two_step(default_executor="messages-api"), "draft", tools=("read", "subagent"))
    assert "tool-unmapped" in codes(preflight_of(spec, reg("claude", "messages-api")))


def test_cross_executor_judge_and_none() -> None:
    spec = two_step(default_executor="antigravity")
    rep = preflight_of(spec, reg("claude", "antigravity"))
    assert rep.ok, rep.refusals
    assert rep.judges == {"draft": "claude", "review": "claude"}  # EXI-AC8
    assert "judge-executor-none" in codes(preflight_of(spec, reg("antigravity")))


def test_option_unsupported_and_effort_warning() -> None:
    spec = with_step(two_step(default_executor="antigravity"), "draft",
                     session_options=SessionOptions(cost_cap_usd=1.0, effort="high"))
    assert "option-unsupported" in codes(preflight_of(spec, reg("claude", "antigravity")))
    r = reg("claude")
    bare = standin("antigravity")
    bare.caps = dataclasses.replace(bare.caps, session_options=frozenset())
    r.register(bare)
    spec = with_step(two_step(default_executor="antigravity"), "draft", session_options=SessionOptions(effort="high"))
    rep = preflight_of(spec, r)
    assert rep.ok and "effort-unsupported" in [w.code for w in rep.warnings]


def test_enforcement_refused_when_undeclared() -> None:
    spec = two_step(default_executor="antigravity")
    assert "enforcement-unsupported" in codes(preflight_of(spec, reg("claude", "antigravity"), strict_permissions=True))
    assert preflight_of(two_step(), reg("claude"), enforce_tools=True).ok  # EXI-B12


def _mcp_spec() -> Any:
    units = dict(two_step().units)
    units["review"] = Step(prompt="Review", tools=["read", "mcp:tracker/get_issue"],
                           gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-r")]))
    return dataclasses.replace(two_step(), units=units)


def test_ecc_ac9_mcp_judge_views_are_not_deferred_on_claude() -> None:  # ECC-AC9
    rep = preflight_of(_mcp_spec(), reg("claude"))  # `claude` declares `judge_mcp` (ECC-B6)
    assert rep.ok, rep.refusals
    assert "review" not in rep.deferred
    assert "judge-view-deferred" not in [w.code for w in rep.warnings]


def test_ecc_ac9_mcp_judge_views_are_deferred_where_judge_mcp_is_false() -> None:  # ECC-AC9
    r = Registry()
    bare = standin("claude")
    bare.caps = dataclasses.replace(bare.caps, judge_mcp=False)  # a judge executor that restricts tools but has no proxy
    r.register(bare)
    rep = preflight_of(_mcp_spec(), r)
    assert rep.ok, rep.refusals
    assert [(d.capability, d.reason) for d in rep.deferred["review"]] == [("mcp:tracker/get_issue", "judge_mcp")]  # EXI-B19
    assert "judge-view-deferred" in [w.code for w in rep.warnings]
