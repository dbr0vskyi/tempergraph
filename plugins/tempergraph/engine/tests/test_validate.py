"""Validation before spend (WFM §2.1, WFM-AC-1, AC-5, AC-6; CON-AC-5; WFM-B3)."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

from tempergraph import api
from tempergraph.api import Criterion, Gate, Judge, Script, SessionOptions, Step, Value
from tempergraph.contracts import FlowSpec, WorkflowSpec
from tempergraph.executors.capabilities import CLAUDE, DECLARED
from tempergraph.model.validate import errors, validate

from .fixtures.workflows import crit, two_step

ALL = DECLARED
CLAUDE_ONLY = {"claude": CLAUDE}


def codes(spec: WorkflowSpec, executors: dict = CLAUDE_ONLY) -> set[str]:
    return {f.code for f in errors(validate(spec, executors))}


def test_valid_two_step() -> None:
    assert errors(validate(two_step(), CLAUDE_ONLY)) == []


def _unit(spec: WorkflowSpec, name: str, **changes: Any) -> WorkflowSpec:
    units = dict(spec.units)
    units[name] = dataclasses.replace(units[name], **changes)
    return dataclasses.replace(spec, units=units)


def _step(spec: WorkflowSpec, name: str, **changes: Any) -> WorkflowSpec:
    u = spec.units[name]
    assert u.step is not None
    return _unit(spec, name, step=dataclasses.replace(u.step, **changes))


def _gate(spec: WorkflowSpec, name: str, **changes: Any) -> WorkflowSpec:
    return _unit(spec, name, gate=dataclasses.replace(spec.units[name].gate, **changes))


def not_module_level(ctx: Any) -> None:
    return None


BROKEN = api.callable_ref(not_module_level)
BROKEN = dataclasses.replace(BROKEN, qualname="does_not_exist", func=None)

# One fixture per row of WFM §2.1 built by release 1, with its own finding code (WFM-AC-1).
CASES: list[tuple[str, Callable[[], WorkflowSpec]]] = [
    ("order-empty", lambda: dataclasses.replace(two_step(), order=())),
    ("order-unknown-unit", lambda: dataclasses.replace(two_step(), order=("draft", "nope"))),
    ("judge-missing", lambda: _gate(two_step(), "draft", judge=None)),
    ("criteria-missing", lambda: _gate(two_step(), "draft", criteria=())),
    ("reference-unknown", lambda: _gate(two_step(), "review", judge=Judge(stance="V.", references=["ghost"]))),
    ("target-unknown", lambda: _gate(two_step(), "review", back_targets=("ghost",))),
    ("back-target-not-earlier", lambda: _gate(two_step(), "draft", back_targets=("review",))),
    ("target-not-forward", lambda: dataclasses.replace(two_step(), flow={"review": FlowSpec(next="draft")})),
    ("unreachable", lambda: dataclasses.replace(two_step(), flow={"draft": FlowSpec(next="finalizer")})),
    ("executor-unknown", lambda: _step(two_step(), "draft", executor="antigravity")),
    ("alias-unbound", lambda: _step(two_step(), "draft", model="enormous")),
    ("tool-unmapped", lambda: _step(dataclasses.replace(two_step(), default_executor="messages-api"), "draft",
                                    tools=("read", "subagent", "shell"))),
    ("tool-unknown", lambda: _step(two_step(), "draft", tools=("read", "teleport", "shell"))),
    ("judge-tool-not-read-only", lambda: _gate(two_step(), "draft", judge=Judge(stance="V.", tools=["write"]))),
    ("judge-view-unavailable", lambda: _step(two_step(), "draft", produces={"page": "wiki_page"})),
    ("command-not-allowed", lambda: _step(two_step(), "draft", commands=("rm -r",))),
    ("command-metacharacter", lambda: _step(two_step(), "draft", commands=("pytest; rm",))),
    ("command-without-shell", lambda: _step(two_step(), "draft", tools=("read",))),
    ("template-invalid", lambda: _step(two_step(), "draft", prompt="Write {notes")),
    ("template-unknown-field", lambda: _step(two_step(), "draft", prompt="Write {ticket}")),
    ("template-unreadable", lambda: _step(two_step(), "draft", prompt=api.text("prompts/missing.md"))),
    ("timeout-invalid", lambda: _step(two_step(), "draft", timeout_s=0)),
    ("issue-repository-invalid", lambda: dataclasses.replace(two_step(), issue_repository="nope")),
    ("model-ladder-retired", lambda: _step(two_step(), "draft", model=("small", "medium"))),
    ("setting-default-invalid", lambda: dataclasses.replace(
        two_step(), settings={"depth": api.Setting(kind="int", default=99, max=5)})),
    ("profile-key-unknown", lambda: dataclasses.replace(two_step(), profiles={"fast": {"settings.nope": 1}})),
    ("routing-description-missing", lambda: dataclasses.replace(two_step(), routing=api.Routing(description=""))),
    ("reserved-unit-name", lambda: dataclasses.replace(
        two_step(), order=("draft", "outcome"), units={"draft": two_step().units["draft"],
                                                        "outcome": two_step().units["review"]})),
    ("reserved-key", lambda: _step(two_step(), "draft", produces={"task_id": "file"})),
    ("mechanical-without-check", lambda: _gate(two_step(), "review", criteria=(
        Criterion(id="m", text="t", check_method="m", mechanical=True),))),
    ("value-choices-and-pattern", lambda: _step(two_step(), "review", produces={"v": Value(choices=["a"], pattern="a")})),
    ("value-pattern-invalid", lambda: _step(two_step(), "review", produces={"v": Value(pattern="(")})),
    ("finalizer-outcomes-missing", lambda: dataclasses.replace(two_step(), finalizer=api.callable_ref(not_module_level))),
    ("callable-not-importable", lambda: _gate(two_step(), "draft", check=BROKEN)),
    ("skill-not-installed", lambda: _step(two_step(), "draft", tools=("read", "shell", "skill:demo:notes"))),
    ("option-unsupported", lambda: _step(dataclasses.replace(two_step(), default_executor="messages-api"), "draft",
                                         session_options=SessionOptions(fallback_alias="small"))),
    ("script-run-or-call", lambda: _step(two_step(), "draft", before=(Script(),))),
    ("script-before-external", lambda: _step(two_step(), "draft", before=(
        Script(run=["pytest"], side_effects="external"),))),
    ("not_in_release", lambda: _step(two_step(), "draft", self_check=True)),
]


@pytest.mark.parametrize("code,build", CASES, ids=[c for c, _ in CASES])
def test_each_refusal_has_its_code(code: str, build: Callable[[], WorkflowSpec]) -> None:
    executors = CLAUDE_ONLY if code == "executor-unknown" else ALL
    assert code in codes(build(), executors)


def test_codes_are_distinct_per_fixture() -> None:
    assert len({c for c, _ in CASES}) == len(CASES)


LATER = ["Parallel", "Ask", "Wait", "Council", "Contest", "Subworkflow"]


@pytest.mark.parametrize("builder", LATER)
def test_later_kinds_not_in_release(builder: str) -> None:
    spec = two_step()
    units = dict(spec.units)
    units["later"] = getattr(api, builder)(branches=["a", "b"])
    spec = dataclasses.replace(spec, units=units, order=(*spec.order, "later"))
    found = [f for f in validate(spec, CLAUDE_ONLY) if f.code == "not_in_release"]
    assert found and any("release" in f.message for f in found)


@pytest.mark.parametrize("field", ["fallback", "cache"])
def test_later_fields_not_in_release(field: str) -> None:
    spec = two_step()
    if field == "fallback":
        spec = _gate(spec, "draft", on_budget_spent="fallback", fallback="review")
    else:
        spec = _step(spec, "draft", before=(Script(run=["pytest"], cache="thread", side_effects="none", inputs=["x"]),))
    assert "not_in_release" in codes(spec)


def portable() -> WorkflowSpec:
    """Only tiers and the six portable capabilities (CON-AC-5, WFM-AC-5)."""
    return _step(two_step(), "draft", tools=("read", "search", "list", "edit", "write", "shell"), model="medium")


@pytest.mark.parametrize("executor", sorted(DECLARED))
def test_portable_workflow_valid_on_all_four(executor: str) -> None:
    spec = dataclasses.replace(portable(), default_executor=executor)
    assert errors(validate(spec, ALL)) == []


def test_wfm_b3_no_binding_refuses() -> None:
    no_medium = dataclasses.replace(DECLARED["antigravity"], binds_aliases=frozenset({"small", "large"}))
    spec = dataclasses.replace(portable(), default_executor="antigravity")
    assert "alias-unbound" in codes(spec, {**ALL, "antigravity": no_medium})


def test_effort_only_warns() -> None:
    spec = dataclasses.replace(_step(two_step(), "draft", session_options=SessionOptions(effort="high")),
                               default_executor="messages-api")
    spec = _step(spec, "draft", tools=("read", "write", "shell"))
    assert not any(f.code == "effort-unsupported" for f in validate(spec, ALL))  # messages-api applies it
    no_effort = dataclasses.replace(DECLARED["messages-api"], session_options=frozenset())
    found = validate(spec, {**ALL, "messages-api": no_effort})
    assert any(f.code == "effort-unsupported" and f.severity == "warning" for f in found)
    assert "effort-unsupported" not in {f.code for f in errors(found)}


def test_criterion_without_method_warns() -> None:
    spec = _gate(two_step(), "draft", criteria=(Criterion(id="x", text="Good"),))
    assert any(f.code == "criterion-no-check-method" for f in validate(spec, CLAUDE_ONLY))


def test_route_and_switch_fixtures_valid() -> None:
    from .fixtures.workflows import routed, single_route, switched

    for spec in (routed(), switched(), single_route()):
        assert errors(validate(spec, CLAUDE_ONLY)) == [], spec.order


def test_template_key_not_on_every_path_warns() -> None:
    from .fixtures.workflows import routed

    spec = routed()
    units = dict(spec.units)
    units["review"] = Step(prompt="Review {mode}", tools=["read"],
                           gate=Gate(judge=Judge(stance="V."), criteria=[crit("c2")]))
    spec = dataclasses.replace(spec, units=units)
    assert errors(validate(spec, CLAUDE_ONLY)) == []
