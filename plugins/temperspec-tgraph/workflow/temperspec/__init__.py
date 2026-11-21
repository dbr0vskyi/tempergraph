"""temperspec: a task goes from triage through discovery and a plan to tested code and a draft pull request.

`prepare` runs no session: it installs the rule files and the project note, and sends a repository that has
no overview spec through `setup`, which writes the overview and one spec per component from the code as it is.

`triage` reads the task and routes it: no gap in the specs goes to `plan`, any gap to `discovery`, and a
docs-only task ends after `discovery`. `plan` states the task's complexity; a complex plan gets its task rows
from `expand`, a simple one already has them. `code` builds the whole plan in one session (per-phase coding
waits for the engine's sequential map). The engine commits after every step and the last stage pushes.

No unit uses the large model tier. `discovery` thinks at the highest effort.
"""

from typing import Any

from tempergraph.api import Gate, Judge, Route, Routing, Script, SessionOptions, Step, Value, Workflow, text

from . import specfmt
from .checks import code_check, discovery_check, expand_check, plan_check, setup_check, triage_check
from .routing import (
    commit_step,
    finalize,
    prepare,
    route_discovery,
    route_plan,
    route_setup,
    route_triage,
)

MODEL = "medium"
READ = ["read", "search", "list"]
# What a plan may list as verification (VERIFY), and what the last stage runs on top. A check refuses
# `git push` and `gh` in a plan. Release 1 of the engine reads no per-repository command resolver and its audit
# wants every program here on PATH, so the list holds one toolchain; add a repository's own prefixes here.
VERIFY = ["pytest", "python3 -m pytest", "ruff check", "ruff format --check", "mypy",
          "git --version", "git status", "git diff", "git log", "git show"]
ALLOW = [*VERIFY, "git remote", "git push -u origin", "gh pr list", "gh pr create"]


def _commit() -> Any:
    return Script(call=commit_step, name="commit", side_effects="workspace", summary="Commit the step's files")


def _judge(unit: str, references: list[str]) -> Any:
    return Judge(file=f"judges/{unit}.md", references=references, model=MODEL)


def workflow() -> Any:
    return Workflow(
        order=["prepare", "setup_route", "setup", "triage", "discovery", "plan", "expand", "code"],
        routing=Routing(
            description="Take a task from its acceptance criteria to specs, a plan, tested code and a draft "
                        "pull request",
            when_to_use="A change to a repository that keeps behaviour specs; say `docs only` to stop after "
                        "the specs"),
        issue_repository="dbr0vskyi/tempergraph",
        allow_commands=ALLOW,
        units={
            "prepare": Script(
                call=prepare, summary="Install rules and the project note; see if setup is due",
                side_effects="workspace", gate=Gate(),
                produces={"setup_needed": Value(choices=["yes"], optional=True),
                          "setup_ready": Value(choices=["yes"], optional=True)}),
            "setup_route": Route(select=route_setup, targets=["setup", "triage"]),
            "setup": Step(
                prompt=text("prompts/setup.md"), summary="Write the overview spec and one spec per component",
                model=MODEL, tools=[*READ, "edit", "write"], timeout_s=3600,
                produces={"overview": "file", "setup_note": "file"}, after=[_commit()],
                gate=Gate(check=setup_check, judge=_judge("setup", ["overview", "setup_note"]),
                          on_budget_spent="stop")),
            "triage": Step(
                prompt=text("prompts/triage.md"), summary="Read the task, find the gaps, pick the route",
                model=MODEL, tools=[*READ, "write"], timeout_s=1200,
                produces={"triage_note": "file", "gaps": Value(choices=["some", "none"]),
                          "route": Value(choices=list(specfmt.ROUTES))},
                after=[_commit()], route=route_triage, route_targets=["discovery", "plan"],
                gate=Gate(check=triage_check, judge=_judge("triage", ["triage_note"]), on_budget_spent="stop")),
            "discovery": Step(
                prompt=text("prompts/discovery.md"), summary="Close each gap with a spec, record or research note",
                model=MODEL, session_options=SessionOptions(effort="max"), timeout_s=3600,
                tools=[*READ, "edit", "write", "web_search", "web_fetch"], produces={"handoff": "file"},
                after=[_commit()], route=route_discovery, route_targets=["plan", "finalizer"],
                gate=Gate(check=discovery_check, judge=_judge("discovery", ["handoff", "triage_note"]),
                          on_budget_spent="stop")),
            "plan": Step(
                prompt=text("prompts/plan.md"), summary="Design requirements and phases; state complexity",
                model=MODEL, tools=[*READ, "edit", "write"], timeout_s=1800,
                produces={"plan": "file", "complexity": Value(choices=["complex", "simple"])},
                after=[_commit()], route=route_plan, route_targets=["expand", "code"],
                gate=Gate(check=plan_check, judge=_judge("plan", ["plan", "triage_note"]),
                          back_targets=["discovery"])),
            "expand": Step(
                prompt=text("prompts/expand.md"), summary="Write task rows and verification for a complex plan",
                model=MODEL, tools=[*READ, "edit", "write"], timeout_s=1800, produces={"phases": "file"},
                after=[_commit()],
                gate=Gate(check=expand_check, judge=_judge("expand", ["phases", "plan"]),
                          back_targets=["plan", "discovery"])),
            "code": Step(
                prompt=text("prompts/code.md"), summary="Build the plan test first in one session",
                model=MODEL, tools=[*READ, "edit", "write", "shell"], commands=VERIFY, timeout_s=5400,
                produces={"code_report": "file", "tests_passed": Value(choices=["yes", "no"])},
                after=[_commit()],
                gate=Gate(check=code_check, check_timeout_s=1800,
                          judge=_judge("code", ["code_report", "plan", "triage_note"]),
                          back_targets=["plan", "discovery"])),
        },
        finalizer=finalize,
        finalizer_outcomes=["opened", "reused", "pushed", "skipped"],
    )
