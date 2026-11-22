# Prompt rendering and output contract

## Purpose

One renderer builds every step prompt for every executor, so what a step is told and must emit is the same whether it runs on Claude Code or Antigravity. The step is shown its criteria as the target and is never asked to grade itself: its output is a claim, the judge assesses it and the engine decides. Workflow authors depend on the sections a prompt holds and on the output lines a step must end with; the judge, checks and routes read artifacts, and a step reads only what its template names, which keeps context small on every executor. Instruction files differ per executor (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`) and the engine adds nothing to them; rules a step needs on several executors ship through the workflow's authoring surface ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)).

## Behaviours

### PRM-B1 Same prompt on every executor

WHEN a step is rendered for different executors THE renderer SHALL produce prompts that differ only in the tool names inside the tools block, taken from each executor's `tool_map`.

- GIVEN a step declaring `read` and `shell` WHEN rendered for `claude` and `agent-sdk` THEN the tools block names `Read` and `Bash`
- GIVEN the same step WHEN rendered for `messages-api` THEN the tools block names `read_file` and `run_command`
- GIVEN the same step WHEN rendered for `antigravity` THEN the tools block names `view_file` and `run_command`

### PRM-B6 Sections and their order

WHEN a step prompt is rendered THE renderer SHALL write, in this order and each only when its condition holds: the step's template ([CON-B8](01-contracts.spec.md)); item and event sections (item id, index and count; an event value cut at 4000 characters); commands you may run (declared prefixes, or `self_check`); check your work before you end, with the `self-check` command and what it reports ([CHK-B17](75-check-contract-and-command-runs.spec.md)); tools for this step; lessons from earlier runs, active entries in id order with their ids ([LSN-B8, LSN-B2](42-workflow-lessons.spec.md)); the artifact contract, one line per declared key and kind; how this output will be judged (criterion texts only); the blocked line and, when allowed, the upstream line; notes from the previous judgement (unmet warnings of the last pass); the reason for this visit and who sent it; the rejection reason on a retry; human feedback ([RRN-B14, RRN-B15](81-reruns-and-feedback.spec.md)); and rulings from a person.

- GIVEN a step with commands and `self_check` WHEN rendered THEN the commands section comes before the self-check section, and both after the template
- GIVEN active lessons for the unit WHEN its judge's prompt is rendered THEN no lesson appears in it

### PRM-B3 Absent when unused

WHEN a step has no tools, no retry and no visit reason THE renderer SHALL write only the rendered template and the sections its declaration requires.

- GIVEN a step with no tools, no criteria and no produced keys WHEN rendered on its first attempt THEN the prompt is the rendered template and the blocked line

### PRM-B4 Braces in appended text

WHEN text is appended after the template THE renderer SHALL append it verbatim, never format-processed.

- GIVEN human feedback containing `{not_a_field}` WHEN it is appended THEN it appears literally and rendering does not fail

### PRM-B7 The default prompt

WHEN a step's `prompt` is `default` THE renderer SHALL render the engine template `{request}`, the whole start request, which is the one input of a workflow that declares no input parameters ([VAL-B8](76-step-values-and-template-keys.spec.md)).

- GIVEN a workflow with no input parameters and a step with `prompt: default` WHEN started with "summarize the changes" THEN the prompt begins with "summarize the changes"

### PRM-B2 No self-assessment

WHEN a gate has criteria THE renderer SHALL list their texts as the target and ask for no status, verdict, confidence or report on them, showing no check method and no severity.

- GIVEN a gate with three criteria WHEN the step prompt is rendered THEN it lists the three texts and contains no check method, severity or request for self-grading

### PRM-B8 The tools block

WHEN a step declares tools or holds a tool grant ([RST-B28, RST-B29, RST-B30](80-run-settings-and-overrides.spec.md)) THE renderer SHALL write the tools by their executor names and the rules to stay in the working directory, prefer file tools over the shell when both are declared, run git without a leading change of directory and run only the listed commands, say there is no shell when `shell` is not declared, and never say an undeclared tool is unavailable, because enforcement is opt-in.

- GIVEN a step declaring `read` and `edit` WHEN rendered THEN the tools block says there is no shell
- GIVEN a grant of `shell` for this run WHEN the step is rendered THEN the tools block lists the shell tool

### PRM-B9 The upstream line

WHEN a step has back targets THE renderer SHALL offer the upstream line only for a listed target that has run on this path or that a route skipped ([ADR-0076](../adr/0076-claims-may-target-a-route-skipped-back-target.adr.md)), and the blocked line always.

- GIVEN `back_targets: [plan]` and a path on which `plan` ran WHEN rendered THEN the prompt offers `UPSTREAM plan: <defect>`
- GIVEN a path on which `plan` neither ran nor was skipped by a route WHEN rendered THEN no upstream line is offered

### PRM-B5 Retry told, not resumed

WHEN a retry is rendered THE renderer SHALL give a fresh session the rejection reason (for a check FAIL each failing finding's criterion, place and fix, then the evidence; for a judged RETRY the blockers with criterion, place, problem and fix), the previous attempt's report labelled a claim (at most 3000 characters, head and tail) and the paths changed since it began (at most 20).

- GIVEN a judged RETRY WHEN the next attempt is rendered THEN it carries the blockers, the previous report labelled a claim and the changed paths
- GIVEN a retry after a timeout, an infra failure or a cut-off WHEN rendered THEN only the changed paths are given

### PRM-B10 Feedback and rulings

WHEN a person gave feedback or rulings THE renderer SHALL show one-time feedback (from a retry, a proceed for the next unit, a breakpoint or an unfinished thread) once, and active rulings that apply to the unit on every attempt and visit until revoked.

- GIVEN feedback at a resume WHEN the next two attempts are rendered THEN only the first shows it
- GIVEN a ruling for unit `code` WHEN `code` runs on a later visit THEN the ruling is shown

### PRM-B11 Output contract

WHEN a step ends THE engine SHALL read its last non-blank lines: `ARTIFACT <key>: <value>`, one per declared key (a key with no line falls back to the raw output; for a `value` key the text sets the value, [VAL-B5, VAL-B6](76-step-values-and-template-keys.spec.md)); `BLOCKED: <what a person must decide or provide>`, which skips the judge; or `UPSTREAM <unit>: <defect>`.

- GIVEN a step ending `BLOCKED: need the API key` WHEN its gate runs THEN no judge session starts and the run pauses for a person
- GIVEN `UPSTREAM deploy: …` where `deploy` is not a listed target on this path WHEN read THEN the claim is read as blocked

### PRM-B12 A template that cannot be read

WHEN a template file cannot be read at run time THE engine SHALL fail the attempt with infra cause `prompt_not_delivered`, outside the retry budget.

- GIVEN a template file deleted after the run started WHEN the step renders THEN the attempt fails with `prompt_not_delivered` and the retry budget is unchanged

### PRM-B13 A prompt too large

WHEN a rendered prompt is above the executor's standard-input cap (for `messages-api`, the bound model's context window less the tool definitions) THE engine SHALL fail the step before launch with a finding that the step must be split.

- GIVEN a prompt of 2 MB WHEN the step is launched THEN no session starts and the finding names the cap

### PRM-B14 The engine's text is neutral

WHEN the engine adds text to a prompt THE renderer SHALL name no workflow, step or path, and write only sentences that are true when tools are not enforced.

- GIVEN the engine's sections WHEN rendered for any workflow THEN they contain no workflow, step or path name of the engine's own choosing

## Acceptance criteria

- PRM-AC1 (PRM-B6, PRM-B3): Golden tests render every section combination of PRM-B6 for all four executors
- PRM-AC2 (PRM-B1): Two renders for different executors differ only inside the tools block
- PRM-AC3 (PRM-B2): No rendered step prompt contains a check method, a severity or a request for self-grading
- PRM-AC4 (PRM-B5, PRM-B6): Every appended section respects its stated size bound
- PRM-AC5 (PRM-B4, PRM-B7): Appended text with braces renders literally, and `prompt: default` renders the whole request
- PRM-AC6 (PRM-B8, PRM-B9): The tools block holds the rules of PRM-B8, and the upstream line is offered only for a target that ran or was route-skipped on the path
- PRM-AC7 (PRM-B10): One-time feedback is shown once, and a ruling on every attempt until it is revoked
- PRM-AC8 (PRM-B11): Each output line form sets its artifact, skips the judge or makes its claim, and a claim to an unlisted target is read as blocked
- PRM-AC9 (PRM-B12, PRM-B13): An unreadable template fails with `prompt_not_delivered` outside the retry budget, and an over-cap prompt fails before launch
- PRM-AC10 (PRM-B14): A scan of the engine's prompt text finds no workflow, step or path name
