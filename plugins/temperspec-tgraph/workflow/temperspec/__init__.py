"""temperspec: a task goes from triage through discovery and a plan to tested code and a draft pull request.

`prepare` runs no session: it installs the rule files and the project note, and sends a repository that has
no overview spec through `setup`, which writes the overview and one spec per component from the code as it is.

`triage` reads the task and routes it: a small fix that changes no spec goes straight to `code` (the quick
lane), no gap in the specs goes to `plan`, any gap to `discovery`, and a docs-only task ends after `discovery`.
A task whose every gap a spec already answers (the triage check has verified each `Covered by` mark) takes the
short visit `discovery_short` instead: it confirms the cited behaviours, writes the hand-off and its reading list,
and hands a gap it finds not answered to the full `discovery` (decision record 0003).
The code gate measures a quick change and sends a larger one back to `triage`, which then plans it. `plan` states the task's complexity; a complex plan gets its task rows
from `expand`, a simple one already has them. `code` builds the whole plan in one session (per-phase coding
waits for the engine's sequential map). The engine commits after every step and the last stage pushes.

Every step and judge states its model tier, its effort and why (`SIZING` below; decision record 0002). No unit
uses the large model tier. `discovery` thinks at the highest effort; its short visit, which designs nothing, at `high`.
"""

from typing import Any

from tempergraph.api import Gate, Judge, Route, Routing, Script, Step, Value, Workflow, text

from . import specfmt
from .checks import (
    code_check,
    discovery_check,
    discovery_short_check,
    expand_check,
    plan_check,
    setup_check,
    triage_check,
)
from .routing import (
    commit_step,
    finalize,
    prepare,
    route_discovery,
    route_plan,
    route_setup,
    route_short,
    route_triage,
)

MODEL = "medium"
READ = ["read", "search", "list"]
# What a plan may list as verification (VERIFY), and what the last stage runs on top. A check refuses
# `git push` and `gh` in a plan. Release 1 of the engine reads no per-repository command resolver and its audit
# wants every program here on PATH, so the list holds one toolchain; add a repository's own prefixes here.
# Both spellings of the test runner are listed because a repository's CLAUDE.md writes either, and the engine
# reads `cd <folder> && <command>` as the command run in that folder (CHK-B11), so a plan may copy them as written.
VERIFY = ["pytest", "python -m pytest", "python3 -m pytest", "ruff check", "ruff format --check", "mypy",
          "git --version", "git status", "git diff", "git log", "git show"]
ALLOW = [*VERIFY, "git remote", "git push -u origin", "gh pr list", "gh pr create", "gh pr edit"]


# Per unit: the step's effort and why, then its judge's effort and why. Every session runs on MODEL.
SIZING = {
    "setup": (("high", "It reads a whole repository once and writes the specs every later task trusts"),
             ("medium", "It compares each written spec with the code it describes, one file at a time")),
    "triage": (("medium", "It reads one task and the spec index to sort gaps and pick a route; the check verifies the note's shape"),
              ("medium", "It reads one note against the task; the route it confirms is cheap to correct later")),
    "discovery_short": (("high", "It confirms that each behaviour triage cited answers its gap and lists the files the plan "
                                 "will need; it designs nothing, and the check verifies the cited ids"),
                        ("high", "A gap wrongly taken as answered costs a whole code session, so the verdict keeps the "
                                 "effort of the full visit's judge")),
    "discovery": (("max", "It closes gaps by research and design, the deepest thinking in the workflow, and nothing downstream rechecks its facts"),
                 ("high", "It decides whether each gap is really closed across specs, records and research notes")),
    "plan": (("high", "It designs across specs and code, and a weak plan costs a whole code session"),
            ("high", "It judges that the design covers every criterion and contradicts no spec it references")),
    "expand": (("medium", "It turns an approved plan into task rows and decides little"),
              ("medium", "It compares the task rows with the plan they expand")),
    "code": (("high", "It is a long session that builds test first; the tests and the code check catch slips that more effort would not"),
            ("high", "It reads the diff, the report and the proof of every criterion, and a miss ships a defect")),
}


def _sized(unit: str) -> dict[str, Any]:
    effort, why = SIZING[unit][0]
    return {"model": MODEL, "effort": effort, "sizing": why}


def _commit() -> Any:
    return Script(call=commit_step, name="commit", side_effects="workspace", summary="Commit the step's files")


def _judge(unit: str, references: Any, timeout_s: int | None = None) -> Any:
    effort, why = SIZING[unit][1]
    return Judge(file=f"judges/{unit}.md", references=references, model=MODEL, effort=effort, sizing=why,
                 timeout_s=timeout_s)


def workflow() -> Any:
    return Workflow(
        order=["prepare", "setup_route", "setup", "triage", "discovery_short", "discovery", "plan", "expand", "code"],
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
                **_sized("setup"), tools=[*READ, "edit", "write"], timeout_s=3600,
                produces={"overview": "file", "setup_note": "file"}, after=[_commit()],
                gate=Gate(check=setup_check, judge=_judge("setup", ["overview", "setup_note"]),
                          on_budget_spent="stop")),
            "triage": Step(
                prompt=text("prompts/triage.md"), summary="Read the task, find the gaps, pick the route",
                **_sized("triage"), tools=[*READ, "write"], timeout_s=1200,
                produces={"triage_note": "file", "gaps": Value(choices=["some", "none"]),
                          "route": Value(choices=list(specfmt.ROUTES)),
                          "covered": Value(choices=["no", "yes"], optional=True)},
                after=[_commit()], route=route_triage, route_targets=["discovery_short", "discovery", "plan", "code"],
                gate=Gate(check=triage_check, judge=_judge("triage", ["triage_note"]), on_budget_spent="stop")),
            "discovery_short": Step(
                prompt=text("prompts/discovery_short.md"),
                summary="Confirm the cited behaviours; write the hand-off",
                **_sized("discovery_short"), timeout_s=1200, tools=[*READ, "write"],
                produces={"handoff": "file", "settled": Value(choices=["no", "yes"])},
                after=[_commit()], route=route_short, route_targets=["discovery", "plan"],
                gate=Gate(check=discovery_short_check,
                          judge=_judge("discovery_short", ["handoff", "triage_note"]), on_budget_spent="stop")),
            "discovery": Step(
                prompt=text("prompts/discovery.md"), summary="Close each gap with a spec, record or research note",
                **_sized("discovery"), timeout_s=3600,
                tools=[*READ, "edit", "write", "web_search", "web_fetch"], produces={"handoff": "file"},
                after=[_commit()], route=route_discovery, route_targets=["plan", "finalizer"],
                gate=Gate(check=discovery_check, judge=_judge("discovery", ["handoff", "triage_note"]),
                          on_budget_spent="stop")),
            "plan": Step(
                prompt=text("prompts/plan.md"), summary="Design requirements and phases; state complexity",
                **_sized("plan"), tools=[*READ, "edit", "write"], timeout_s=1800,
                produces={"plan": "file", "complexity": Value(choices=["complex", "simple"])},
                after=[_commit()], route=route_plan, route_targets=["expand", "code"],
                gate=Gate(check=plan_check, judge=_judge("plan", ["plan", "triage_note"]),
                          back_targets=["discovery"])),
            "expand": Step(
                prompt=text("prompts/expand.md"), summary="Write task rows and verification for a complex plan",
                **_sized("expand"), tools=[*READ, "edit", "write"], timeout_s=1800, produces={"phases": "file"},
                after=[_commit()],
                gate=Gate(check=expand_check, judge=_judge("expand", ["phases", "plan"]),
                          back_targets=["plan", "discovery"])),
            "code": Step(
                prompt=text("prompts/code.md"), summary="Build the plan test first in one session",
                **_sized("code"), tools=[*READ, "edit", "write", "shell"], commands=VERIFY, timeout_s=5400,
                produces={"code_report": "file", "tests_passed": Value(choices=["yes", "no"])},
                after=[_commit()], self_check=True,
                gate=Gate(check=code_check, check_timeout_s=1800,
                          # A read of up to 50 source files (the reading budget of the check evidence) may not fit
                          # the engine's default judge time of 600 s, and a judge timeout escalates (JDG-B4).
                          judge=_judge("code", {"code_report": "required", "triage_note": "required",
                                                "plan": "optional"}, timeout_s=1800),
                          back_targets=["plan", "discovery", "triage"])),
        },
        finalizer=finalize,
        finalizer_outcomes=["opened", "reused", "pushed", "skipped"],
    )
