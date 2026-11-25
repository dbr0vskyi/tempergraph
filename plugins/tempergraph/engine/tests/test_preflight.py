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
    assert default_registry().available() == ["claude"]  # ADR `first-release-ships-the-claude-executor-only`


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


def _claude_registry() -> Registry:
    from tempergraph.executors.binding import BindingTable
    from tempergraph.executors.claude import ClaudeExecutor

    r = Registry()
    r.register(ClaudeExecutor(bindings=BindingTable()))
    return r


def test_ecc_ac16_a_cli_without_strict_mcp_config_is_refused_and_launches_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # ECC-AC16 (ECC-B21)
    from .fixtures import streams as S

    record = tmp_path / "record.json"
    S.fake_claude(tmp_path, monkeypatch, {"help": "--tools --bare", "record": str(record)})
    rep = preflight_of(two_step(), _claude_registry())
    assert not rep.ok
    first = rep.first()
    assert first is not None and first.code == "executor-probe-failed"
    assert "probe_failed" in first.message and "--strict-mcp-config" in first.message
    assert not record.exists()


def test_ecc_ac16_a_cli_that_lists_strict_mcp_config_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # ECC-AC16
    from .fixtures import streams as S

    S.fake_claude(tmp_path, monkeypatch, {"help": "--tools --strict-mcp-config", "version": "2.1.329 (Claude Code)"})
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    rep = preflight_of(two_step(), _claude_registry())
    assert not [f for f in rep.refusals if f.code == "executor-probe-failed"], rep.refusals
    assert all(w.code != "executor-version-untested" for w in rep.warnings)


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


def _contest_spec(*slots: Any, tools: tuple[str, ...] = ("read",)) -> Any:
    from tempergraph.api import Contest, Routing, Workflow

    from .fixtures.workflows import named

    step = Step(prompt="Draft {request}", tools=list(tools),
                gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-slot")]))
    return named(Workflow(order=["pick"], units={"pick": Contest(step=step, slots=list(slots))},
                          issue_repository="acme/x", routing=Routing(description="Best of two")))


def test_a_contest_slot_override_that_cannot_bind_or_map_is_refused() -> None:  # CTS-AC1 (CTS-B10)
    from tempergraph.api import Slot

    registry = reg("claude", "messages-api")
    ok = _contest_spec(Slot("a", executor="messages-api", model="large"), Slot("b", model="small"))
    rep = preflight_of(ok, registry)
    assert rep.ok, rep.refusals  # slots that bind and map pass
    unbound = _contest_spec(Slot("a", executor="messages-api", model="messages-api:deep"), Slot("b", model="small"))
    assert "contest-slot-alias-unbound" in codes(preflight_of(unbound, registry))  # the alias is no executor's
    unmapped = _contest_spec(Slot("a", executor="messages-api"), Slot("b"), tools=("read", "subagent"))
    assert "contest-slot-tool-unmapped" in codes(preflight_of(unmapped, registry))  # `messages-api` maps no `subagent`
    unknown = _contest_spec(Slot("a", executor="antigravity"), Slot("b", model="small"))
    assert "contest-slot-executor-unknown" in codes(preflight_of(unknown, registry))
    assert preflight_of(ok, registry).step_executors == {"pick": "claude"}


def council_of(*members: Any, chair: Any = None, judge: Any = None) -> Any:
    from tempergraph.api import Chair, Council

    unit = Council(question="Which design?", members=members, chair=chair or Chair(),
                   gate=Gate(judge=judge or Judge(stance="V."), criteria=[crit("c-dec")]))
    base = two_step()
    return dataclasses.replace(base, units={"decide": unit, **base.units}, order=("decide", *base.order))


def test_cnl_ac7_a_mixed_executor_council_checks_each_member_against_its_own_executor() -> None:  # CNL-AC7 (CNL-B6)
    from tempergraph.api import Member

    spec = council_of(Member(name="a", executor="claude", tools=["read", "search"]),
                      Member(name="b", executor="antigravity", tools=["read", "list"]),
                      Member(name="c", executor="messages-api", model="small", tools=["read", "web_fetch"]))
    rep = preflight_of(spec, reg("claude", "antigravity", "messages-api"))
    assert rep.ok, rep.refusals
    assert {k: v for k, v in rep.step_executors.items() if k.startswith("decide.")} == {
        "decide.member:a": "claude", "decide.member:b": "antigravity", "decide.member:c": "messages-api",
        "decide.chair": "claude"}
    assert rep.judges["decide"] == "claude"  # the judge resolves on the gate's layer, none of the members' executors


def test_cnl_ac7_a_gap_in_one_members_executor_is_refused_and_the_others_are_not() -> None:  # CNL-AC7 (CNL-B6, EXI-B1)
    from tempergraph.api import Member

    r = reg("claude")
    bare = standin("messages-api")
    bare.caps = dataclasses.replace(bare.caps, tool_map={"read": ("read_file",)})  # no `search` on this executor
    r.register(bare)
    spec = council_of(Member(name="a", executor="claude", tools=["read", "search"]),
                      Member(name="b", executor="messages-api", tools=["read", "search"]))
    rep = preflight_of(spec, r)
    gaps = [f for f in rep.refusals if f.code == "tool-unmapped"]
    assert len(gaps) == 1 and "'b'" in gaps[0].message and "messages-api" in gaps[0].message  # exit 2 at the start


def test_cnl_ac7_a_qualified_alias_of_a_members_executor_must_be_in_its_binding_table() -> None:  # CNL-AC7 (CNL-B6)
    from tempergraph.api import Member

    spec = council_of(Member(name="a"), Member(name="b", executor="antigravity", model="antigravity:deep"))
    got = [f for f in preflight_of(spec, reg("claude", "antigravity")).refusals if f.code == "alias-unbound"]
    assert len(got) == 1 and "'b'" in got[0].message


def test_cnl_ac7_a_council_is_not_skipped_by_the_preflight() -> None:  # CNL-AC7 (CNL-B6)
    from tempergraph.api import Member

    spec = council_of(Member(name="a"), Member(name="b", executor="antigravity"))
    down = reg("claude", "antigravity", antigravity=ProbeReport(ok=False, reason="signed_out"))
    rep = preflight_of(spec, down)
    assert [f.unit for f in rep.refusals if f.code == "executor-probe-failed"] == ["decide"]
    assert "executor-unknown" in codes(preflight_of(spec, reg("claude")))  # a member on an executor nobody registered


def test_cnl_ac7_the_chair_and_the_judge_resolve_on_their_own_layers() -> None:  # CNL-AC7 (CNL-B6)
    from tempergraph.api import Chair, Member

    spec = council_of(Member(name="a"), Member(name="b"), chair=Chair(executor="antigravity"),
                      judge=Judge(stance="V.", executor="messages-api"))
    rep = preflight_of(spec, reg("claude", "antigravity", "messages-api"))
    assert rep.ok, rep.refusals
    assert rep.step_executors["decide.chair"] == "antigravity" and rep.step_executors["decide.member:a"] == "claude"
    assert rep.judges["decide"] == "messages-api"


def test_missing_observers_are_preflight_warnings() -> None:  # EVT-AC5 (EVT-B23): one warning per missing name
    from tempergraph.executors.preflight import observer_warnings

    got = observer_warnings(["alpha", "beta"])
    assert [f.severity for f in got] == ["warning", "warning"]
    assert "alpha" in got[0].message and "beta" in got[1].message
    assert {f.code for f in got} == {"observer-missing"}
    assert observer_warnings([]) == []
