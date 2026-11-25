"""temperspec: a task goes from triage through discovery and a plan to tested code and a draft pull request.

`prepare` runs no session: it installs the rule files and the project note, and sends a repository that has
no overview spec through `setup`, which writes the overview and one spec per component from the code as it is.
Setup starts with its reading sessions: `list_components` lists the component folders and `read_component` reads
each in a read-only session, three at a time, before `setup` writes the specs from their findings (spec
parallel-reading).

`triage` reads the task and routes it: a small fix that changes no spec goes straight to `code` (the quick
lane), no gap in the specs goes to `plan`, any gap to `discovery`, and a docs-only task ends after `discovery`.
A task whose every gap a spec already answers (the triage check has verified each `Covered by` mark) takes the
short visit `discovery_short` instead: it confirms the cited behaviours, writes the hand-off and its reading list,
and hands a gap it finds not answered to the full `discovery` (decision record 0003). The full discovery starts
with `owner_questions` and `ask_route`: a run whose list of questions holds one goes to `ask_owner`, the one pause
(a 24 hour deadline that takes the defaults of the open questions), and any other run to `read_gap` (spec
owner-questions). `read_gap` is one read-only reading session for each gap of two or more, three at a time on the
engine's concurrent map, and then the one writing session `discovery`, briefed with their findings and the owner's
answers (spec parallel-reading).
The code gate measures a quick change and sends a larger one back to `triage`, which then plans it. After `plan` the
switch `code_mode` chooses: `single` goes straight to `code` when the facts the plan check records are inside the
limits of `routing/code_mode.json`, and `phases` goes through `expand`, which writes the plan's task rows, otherwise
or when the switch cannot decide; the operator names the arm with `--arm code_mode=<arm>`. On `phases`, after
`expand`, the sequential map `phase` runs one item for each phase of the plan, one after another, each in a session of
its own that builds only that phase's rows, tests first, and is checked and committed on its own; `code` then runs as
the join on the whole change and holds the lines back to `plan`, `discovery` and `triage`. On `single`, `code` builds the
whole plan in one session. `code_join` is where both arms meet. The engine commits after every step and the last stage
pushes.

The setting `conversation` (`never`, `blocking` or `always`, default `blocking`) says how much a run may ask the
owner. Under all three triage sorts each gap and writes the owner decisions with their defaults. `never` stops for
none of them (no step or gate asks, and the pull request lists the defaults as assumptions to confirm); `blocking`
pauses once after triage for the owner decisions; `always` pauses once for them and for the reading of each findable
gap (spec `conversation`).

Every step and judge states its model tier, its effort and why (`SIZING` below; decision record 0002). No unit
uses the large model tier. `discovery` thinks at the highest effort; its short visit, which designs nothing, at `high`.
"""

from typing import Any

from tempergraph.api import (
    Ask,
    ComplexitySwitch,
    Gate,
    Judge,
    Map,
    Measure,
    Route,
    Routing,
    Script,
    Setting,
    Step,
    Value,
    Workflow,
    stock,
    text,
)

from . import specfmt
from .checks import (
    code_check,
    discovery_check,
    discovery_short_check,
    expand_check,
    owner_answers_check,
    phase_check,
    plan_check,
    setup_check,
    triage_check,
)
from .routing import (
    code_join,
    commit_step,
    finalize,
    gap_items,
    list_components,
    owner_questions,
    phase_items,
    prepare,
    route_ask,
    route_discovery,
    route_setup,
    route_short,
    route_triage,
)

MODEL = "medium"
READ = ["read", "search", "list"]
# What a plan may list as verification (VERIFY), and what the last stage runs on top. The toolchain commands are
# the repository's own: `@repository` stands for the commands its `tempergraph.commands.json` declares (CHK-B11,
# spec repository-commands), and `prepare` writes that file for a Python repository that has none. No toolchain
# command is listed here; read-only git is allowed in every repository. A check refuses `git push` and `gh` in a
# plan. The engine reads `cd <folder> && <command>` as the command run in that folder (CHK-B11), so a plan may
# copy a command from a repository's CLAUDE.md as written.
READ_ONLY_GIT = ["git --version", "git status", "git diff", "git log", "git show"]
VERIFY = [*READ_ONLY_GIT, "@repository"]
ALLOW = [*VERIFY, "git remote", "git push -u origin", "gh pr list", "gh pr create", "gh pr edit"]


# Per unit: the step's effort and why, then its judge's effort and why. Every session runs on MODEL.
SIZING = {
    "setup": (("high", "It reads a whole repository once and writes the specs every later task trusts"),
             ("medium", "It compares each written spec with the code it describes, one file at a time")),
    "read_component": (("medium", "It reads one folder's code and tests and writes nothing; the writing session confirms each claim"),
                       ("medium", "It reads one findings line against one folder, and the writing step's own check comes later")),
    "triage": (("medium", "It reads one task and the spec index to sort gaps and pick a route; the check verifies the note's shape"),
              ("medium", "It reads one note against the task; the route it confirms is cheap to correct later")),
    "discovery_short": (("high", "It confirms that each behaviour triage cited answers its gap and lists the files the plan "
                                 "will need; it designs nothing, and the check verifies the cited ids"),
                        ("high", "A gap wrongly taken as answered costs a whole code session, so the verdict keeps the "
                                 "effort of the full visit's judge")),
    "read_gap": (("medium", "It reads one gap's documents and code and writes nothing; the writing session confirms each claim"),
                 ("medium", "It reads one findings line against one gap row, and the check of the writing step comes later")),
    "discovery": (("max", "It closes gaps by research and design, the deepest thinking in the workflow, and nothing downstream rechecks its facts"),
                 ("high", "It decides whether each gap is really closed across specs, records and research notes")),
    "plan": (("high", "It designs across specs and code, and a weak plan costs a whole code session"),
            ("high", "It judges that the design covers every criterion and contradicts no spec it references")),
    "expand": (("medium", "It turns an approved plan into task rows and decides little"),
              ("medium", "It compares the task rows with the plan they expand")),
    "phase": (("medium", "One phase of rows with the tests named; the check reads the rows and the judge the change"),
              ("medium", "It reads the rows of one phase against the files they name, and the check has read the marks")),
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
        order=["prepare", "setup_route", "list_components", "read_component", "setup", "triage", "discovery_short",
               "owner_questions", "ask_route", "ask_owner", "read_gap", "discovery", "plan", "code_mode",
               "expand", "phase", "code", "code_join"],
        routing=Routing(
            description="Take a task from its acceptance criteria to specs, a plan, tested code and a draft "
                        "pull request",
            when_to_use="A change to a repository that keeps behaviour specs; say `docs only` to stop after "
                        "the specs"),
        issue_repository="dbr0vskyi/tempergraph",
        allow_commands=ALLOW,
        settings={"conversation": Setting(
            kind="choice", default="blocking", choices=["never", "blocking", "always"],
            meaning="How much a run may ask the owner. `never` keeps the run unattended: triage sorts each gap and "
                    "takes a default for each owner decision, no step stops for one, and the pull request lists the "
                    "defaults as assumptions to confirm. `blocking` sorts the same way and pauses the run once after "
                    "triage for the owner decisions, each with its default. `always` pauses once in the same way and "
                    "also asks whether the reading of each findable gap is right")},
        units={
            "prepare": Script(
                call=prepare, summary="Install rules and the project note; see if setup is due",
                side_effects="workspace", gate=Gate(),
                produces={"setup_needed": Value(choices=["yes"], optional=True),
                          "setup_ready": Value(choices=["yes"], optional=True)}),
            "setup_route": Route(select=route_setup, targets=["list_components", "triage"]),
            "list_components": Script(
                call=list_components, summary="List the component folders to read", side_effects="workspace",
                gate=Gate(), produces={"component_list": "file"}),
            "read_component": Map(
                items_from=("list_components", "component_list"), mode="concurrent", concurrency=3,
                on_empty="skip",
                step=Step(
                    prompt=text("prompts/read_component.md"), summary="Read one component folder; report findings",
                    **_sized("read_component"), tools=READ, timeout_s=1200,
                    produces={"component_finding": Value(max_chars=1500)},
                    gate=Gate(judge=_judge("read_component", []), on_budget_spent="stop"))),
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
                after=[_commit()], route=route_triage, route_targets=["discovery_short", "owner_questions", "plan", "code"],
                gate=Gate(check=triage_check, judge=_judge("triage", ["triage_note"]), on_budget_spent="stop")),
            "discovery_short": Step(
                prompt=text("prompts/discovery_short.md"),
                summary="Confirm the cited behaviours; write the hand-off",
                **_sized("discovery_short"), timeout_s=1200, tools=[*READ, "write"],
                produces={"handoff": "file", "settled": Value(choices=["no", "yes"])},
                after=[_commit()], route=route_short, route_targets=["read_gap", "plan"],
                gate=Gate(check=discovery_short_check,
                          judge=_judge("discovery_short", ["handoff", "triage_note"]), on_budget_spent="stop")),
            # OWQ-B1, OWQ-B2: a run that goes to the full discovery lists what the owner is asked; a run whose list
            # holds a question pauses once, before any reading session, and takes the defaults at its deadline.
            "owner_questions": Script(
                call=owner_questions, summary="List the owner's questions of the one pause", side_effects="workspace",
                gate=Gate(), produces={"question_list": "file", "empty": Value(choices=["yes"], optional=True)}),
            "ask_route": Route(select=route_ask, targets=["ask_owner", "read_gap"]),
            "ask_owner": Ask(questions_from="question_list", context=["triage_note"], check=owner_answers_check,
                             deadline_s=86400, on_deadline="defaults"),
            "read_gap": Map(
                items_from=("triage", "triage_note"), extract=gap_items, mode="concurrent", concurrency=3,
                on_empty="skip",
                step=Step(
                    prompt=text("prompts/read_gap.md"), summary="Read one gap's documents and code; report findings",
                    **_sized("read_gap"), tools=[*READ, "web_search", "web_fetch"], timeout_s=1200,
                    produces={"gap_finding": Value(max_chars=1500)},
                    gate=Gate(judge=_judge("read_gap", ["triage_note"]), on_budget_spent="stop"))),
            "discovery": Step(
                prompt=text("prompts/discovery.md"), summary="Close each gap with a spec, record or research note",
                **_sized("discovery"), timeout_s=3600,
                tools=[*READ, "edit", "write", "web_search", "web_fetch"], produces={"handoff": "file"},
                after=[_commit()], route=route_discovery, route_targets=["plan", "finalizer"],
                gate=Gate(check=discovery_check, judge=_judge("discovery", {"handoff": "required", "triage_note": "required",
                                                          "answers": "optional"}),
                          on_budget_spent="stop")),
            "plan": Step(
                prompt=text("prompts/plan.md"), summary="Design requirements and phases; state complexity",
                **_sized("plan"), tools=[*READ, "edit", "write"], timeout_s=1800,
                produces={"plan": "file", "complexity": Value(choices=["complex", "simple"])},
                after=[_commit()],
                gate=Gate(check=plan_check, judge=_judge("plan", ["plan", "triage_note"]),
                          back_targets=["discovery"])),
            # CDM-B1 to CDM-B7: the route after the plan is the engine's complexity switch. `single` goes to the code
            # step, `phases` (the safe arm) through the expand step first; the measures are the facts the plan check
            # records, the limits are read from `routing/code_mode.json`, and both arms meet at `code_join`.
            "code_mode": ComplexitySwitch(
                arms={"single": "code", "phases": "expand"},
                measures=[Measure(name, stock.fact("plan", name)) for name in (
                    "phases", "rows", "test_rows", "files", "commands", "reading_bytes", "heavy_phases")],
                joins_at="code_join", size="phases"),
            "expand": Step(
                prompt=text("prompts/expand.md"), summary="Write task rows and verification for a complex plan",
                **_sized("expand"), tools=[*READ, "edit", "write"], timeout_s=1800, produces={"phases": "file"},
                after=[_commit()],
                gate=Gate(check=expand_check, judge=_judge("expand", ["phases", "plan"]),
                          back_targets=["plan", "discovery"])),
            # PHC-B1 to PHC-B10: on the arm `phases` the map runs one item for each phase of the expanded plan, one after
            # another, each in a session of its own that the `after` script commits; its gate has no line back (MAP-B11),
            # so the lines back stay with the code step, which is the join (PHC-B11 to PHC-B14).
            "phase": Map(
                items_from=("expand", "phases"), extract=phase_items, mode="sequential",
                step=Step(
                    prompt=text("prompts/phase.md"), summary="Build one phase of the plan, tests first, and commit it",
                    **_sized("phase"), tools=[*READ, "edit", "write", "shell"], commands=VERIFY, timeout_s=3600,
                    produces={"phase_note": Value(max_chars=1500)}, after=[_commit()],
                    gate=Gate(check=phase_check, judge=_judge("phase", ["phases", "triage_note"])))),
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
            "code_join": Script(call=code_join, name="code_join", side_effects="none",
                                summary="Where both arms meet after the code step", gate=Gate()),
        },
        finalizer=finalize,
        finalizer_outcomes=["opened", "reused", "pushed", "skipped"],
    )
