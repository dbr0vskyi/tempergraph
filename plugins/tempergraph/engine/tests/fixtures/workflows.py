"""Fixture workflows built with the public builders, as a workflow package would (PKG §2.4)."""

from __future__ import annotations

import dataclasses
from typing import Any

from tempergraph.api import CheckResult, Criterion, Gate, Judge, Route, Routing, Step, Switch, Value, Workflow
from tempergraph.contracts import CheckFinding, WorkflowSpec


def draft_check(ctx: Any) -> CheckResult:
    return CheckResult(result="PASS", evidence="ok", findings=[CheckFinding(status="pass", criterion="c-file")])


def pick_route(view: Any) -> str:
    return "review" if view.values.get("mode") == "full" else "finalizer"


def pick_arm(view: Any) -> str:
    return str(view.values.get("mode", ""))


def crit(cid: str, text: str = "The output is good", severity: str = "blocker") -> Criterion:
    return Criterion(id=cid, text=text, check_method="Read the file and compare", severity=severity)  # type: ignore[arg-type]


def named(spec: WorkflowSpec, name: str = "demo", version: str = "0.1.0") -> WorkflowSpec:
    return dataclasses.replace(spec, name=name, version=version)


def two_step(**overrides: Any) -> WorkflowSpec:
    """A two-step workflow: draft (file) then review (value), both judged."""
    units = {
        "draft": Step(
            prompt="Write the notes for {request} into notes.md",
            tools=["read", "write", "shell"], commands=["pytest"], produces={"notes": "file"},
            gate=Gate(check=draft_check, judge=Judge(stance="Verify.", brief="Read notes.md"), criteria=[crit("c-file")]),
        ),
        "review": Step(
            prompt="Review {notes} for {task_id}",
            tools=["read"], produces={"verdict": Value(choices=["ok", "redo"])},
            gate=Gate(judge=Judge(stance="Verify.", references=["notes"]), criteria=[crit("c-review")],
                      back_targets=["draft"]),
        ),
    }
    fields: dict[str, Any] = {
        "order": ["draft", "review"], "units": units, "issue_repository": "acme/notes",
        "routing": Routing(description="Draft and review release notes"), "allow_commands": ["pytest", "git status"],
    }
    fields.update(overrides)
    return named(Workflow(**fields))


def routed() -> WorkflowSpec:
    units = {
        "draft": Step(prompt="Draft {request}", tools=["read", "write"], produces={"mode": Value(choices=["full", "light"])},
                      gate=Gate(judge=Judge(stance="Verify."), criteria=[crit("c1")]),
                      route=pick_route, route_targets=["review", "finalizer"]),
        "review": Step(prompt="Review", tools=["read"], gate=Gate(judge=Judge(stance="Verify."), criteria=[crit("c2")],
                                                                 back_targets=["draft"])),
    }
    return named(Workflow(order=["draft", "review"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Route a draft")))


def switched() -> WorkflowSpec:
    units = {
        "triage": Step(prompt="Triage {request}", tools=["read"], produces={"mode": Value(choices=["full", "light"])},
                       gate=Gate(judge=Judge(stance="Verify."), criteria=[crit("c1")])),
        "mode": Switch(predicate=pick_arm, arms={"full": "deep", "light": "finalizer"}, default="full"),
        "deep": Step(prompt="Deep work", tools=["read"], gate=Gate(judge=Judge(stance="Verify."), criteria=[crit("c2")])),
    }
    return named(Workflow(order=["triage", "mode", "deep"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Switch on a value")))


def single_route() -> WorkflowSpec:
    units = {
        "a": Step(prompt="A {request}", tools=["read"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("a1")])),
        "r": Route(select=pick_route, targets=["b", "finalizer"]),
        "b": Step(prompt="B", tools=["read"], gate=Gate(judge=Judge(stance="V."), criteria=[crit("b1")])),
    }
    return named(Workflow(order=["a", "r", "b"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Route unit")))
