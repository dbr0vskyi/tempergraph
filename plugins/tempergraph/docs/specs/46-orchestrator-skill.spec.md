# Orchestrator skill

## Purpose

The orchestrator skill (`tempergraph:orchestrate`) is the conversation side of an [orchestration](45-orchestration.spec.md). It turns a request for many runs ("run discovery on these five tickets, then plan each one, then deliver them two at a time") into an orchestration file, shows the person the engine-drawn plan, its run count and projected cost, starts it after approval, sleeps until the engine says a person is needed, walks the person through each pause one at a time, and reports at the end. It sits beside the run driver ([SHL-B5](19-plugin-shell.spec.md)): the run driver drives one run; the orchestrator plans and supervises a graph of runs through the `orchestrate` verbs. Like every shell skill it drives the engine and never decides a gate; unlike orchestration by hand it keeps no queue in its context, launches no run itself and tails no log, because the supervisor does that without a model ([ADR-0035](../adr/0035-orchestration-is-data-run-by-a-model-free-supervisor.adr.md)). It shares the pause walk-through and exit-code table with the run driver through one reference file, so the two never drift. People running many runs at once depend on it; design notes are kept in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### OSK-B8 When it is used

WHEN a request names several runs, a run that must wait for another's result, one workflow over a list of targets K at a time (a one-node map, [ADR-0038](../adr/0038-batch-is-a-one-node-orchestration.adr.md)), a saved orchestration template by name with arguments, or a question about a live or past orchestration THE shell SHALL use the orchestrator, the run driver handing over a request that names more than one run or a dependency and the orchestrator handing back a single-run question.

- GIVEN "status of thread auth-fix" WHEN asked of the orchestrator THEN it hands the question to the run driver

### OSK-B9 The plan is a file

WHEN the skill supervises an orchestration THE skill SHALL keep every run, dependency, policy and cap in the orchestration file the person approved and no second queue, read only the orchestration status document and `facts` (never a run log, transcript or checkpoint), and after a compaction re-read `orchestrate status` instead of its memory.

- GIVEN a wake after compaction WHEN the skill reports THEN its figures come from `orchestrate status` and `facts`

### OSK-B6 Re-attach after compaction

WHEN a long orchestration's conversation was compacted and the skill is woken THE skill SHALL rebuild what it shows from `orchestrate status` and `facts` only.

- GIVEN a compacted conversation WHEN woken THEN the skill reads `orchestrate status` before it reports

### OSK-B10 Draft, validate and plan

WHEN the skill drafts from a request THE skill SHALL pick, after the run driver's preflight once per session, workflows from the catalog, the nodes, `after` edges, `from` inputs, maps, phases, approval nodes where the person wants a sign-off between waves, `k`, a cap and each node's `on_failure` (default `skip_dependants`, stated aloud), ask for any declared input the request does not give in at most four rounds, write the draft to the orchestration's scratch path, run `orchestrate validate` (fixing from the message and re-running on exit 2, asking the person when the fix is a choice, and turning a `needs` result into questions), then `orchestrate plan --format md`.

- GIVEN `validate` exiting 2 on a choice the person must make WHEN the skill handles it THEN it asks the person

### OSK-B2 Dependencies stated, not guessed

WHEN the skill drafts "plan each ticket after its discovery" THE skill SHALL put each plan node `after` its discovery node taking the discovery's artifact by its declared key, and ask the person instead of passing prose between runs when the discovery workflow declares no artifact the planner can take.

- GIVEN a discovery workflow that declares no usable artifact WHEN drafting THEN the skill asks the person

### OSK-B7 Batch requests

WHEN the skill drafts "run triage on these 12 issues, 4 at a time" THE skill SHALL write one map node with 12 targets and `k: 4`, the plan showing 12 runs.

- GIVEN 12 issues, 4 at a time WHEN drafted THEN one map node holds 12 targets and `k: 4`

### OSK-B1 Approval before spend

WHEN the skill presents a drafted orchestration THE skill SHALL show the engine-drawn graph (never drawn by model), the node table, the run count, the projected cost range, the cap or "no cap", any large-orchestration warning and the raw file on request, start nothing without an explicit yes, and ask again for a changed plan.

- GIVEN 6 runs projected at $18 to $30 with no cap WHEN presented THEN the skill shows the range and "no cap" and starts nothing before a yes

### OSK-B11 Start and sleep

WHEN the person approves THE skill SHALL run `orchestrate start`, announce the id, start `orchestrate wait <id>` in the background (in the foreground in a host without background commands, the person's next message continuing) and end the turn, never polling status or waking on a timer while a wait runs, and start a new wait after `orchestrate status` shows the orchestration live when the background wait itself died.

- GIVEN a dead background wait WHEN the skill is next woken THEN it runs `orchestrate status` and starts a new wait for a live orchestration

### OSK-B4 Sleep between needs

WHEN runs start, pass gates and finish with no attention THE skill SHALL take no turn until `orchestrate wait` exits: none for a node that starts or finishes or a gate verdict inside a run, one after the settle window covering every pause in it, and one when the orchestration ends.

- GIVEN a run that pauses WHEN the settle window passes THEN the skill takes one turn

### OSK-B12 Walking through attention

WHEN `orchestrate wait` exits 3 THE skill SHALL read `orchestrate status --json`, list the attention items oldest first in one short message, walk the person through them one at a time (a paused run's payload from `facts` the way the run driver shows it; an approval node's question and artifacts; an `ask` failure's cause and its three choices), answer each with `orchestrate answer … --relayed` and the person's own decision word only after the person's reply so the host's person turn backs it ([PRV](85-caller-provenance.spec.md)), then restart the background wait.

- GIVEN a person's reply "retry" WHEN the skill answers THEN it runs `orchestrate answer … --decision retry --relayed`

### OSK-B3 Several pauses, one at a time

WHEN wait exits 3 with two paused runs and one approval node THE skill SHALL list the three in one message, ask for the oldest first, resume nothing until the person answers that one, and never answer the last remaining one for them.

- GIVEN three attention items WHEN the person has answered one THEN the other two stay unanswered by the skill

### OSK-B13 Outcomes and offers

WHEN `orchestrate wait` exits THE skill SHALL offer for 0 (`finished`) the report and saving the file as a template; for 4 (`stopped`) resuming stopped runs one by one or leaving them; for 5 `finished_with_failures` each failed node's own resume offer as the run driver states it and a new orchestration of the failed and skipped nodes; for 5 `halted` the same plus continuing the unstarted nodes by an edit; for 5 `cost_cap` raising the cap by an approved edit with `orchestrate resume`, or stopping; for 5 `supervisor_lost` `orchestrate resume <id>`; and for 2 the refusal's message fixed in the file; never offering proceed on a run's gate after an infra failure, and sending the person to the installer on 127.

- GIVEN `cost_cap` WHEN offered THEN the skill offers a cap raise by an approved edit or a stop

### OSK-B5 Failure explained by cause

WHEN the skill reports a node failed with exit 5 on a spent retry budget and two dependants skipped THE skill SHALL name the node, the gate and its blockers from `facts`, name both dependants as skipped (not failed, not done), and offer the run's own resume and a follow-up orchestration of the three.

- GIVEN two skipped dependants WHEN reported THEN each is named skipped

### OSK-B14 Report

WHEN the skill reports at the end THE skill SHALL send one message with the outcome, nodes by state, cost (reported and estimated apart, the incomplete flag, the cap), wall time, branches and pull requests per node from `facts`, pauses with who answered, and each failure with its cause, every figure from `orchestrate report` and none of its own.

- GIVEN a finished orchestration WHEN reported THEN every number equals a field of `orchestrate report`

### OSK-B15 Never

WHEN the skill acts THE skill SHALL never answer a pause, an approval or an `ask` failure itself in any mode (contract C6, [ADR-0039](../adr/0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md)), start a node's run with `run` (the supervisor owns starts), edit the orchestration folder, a checkpoint or run state by hand (edits go through `orchestrate edit` after the person's yes to a shown patch, runs through resume), set `mode: unattended` or pass `--as-agent`, draw the graph by model, or hand a person's request for a run outside the orchestration to anything but the run driver; a fix inside one run's worktree is made only when the person asks, by a fresh helper scoped to that worktree that answers no gate.

- GIVEN a request to edit the plan WHEN the skill handles it THEN it shows a patch and applies it with `orchestrate edit` only after a yes

## Acceptance criteria

- OSK-AC1 (OSK-B1, OSK-B3, OSK-B5, OSK-B12, OSK-B15): Rubric scenarios cover no start without a yes, never answering a pause (the last one included) and skipped never reported as done
- OSK-AC2 (OSK-B4, OSK-B11): In a scripted orchestration of 6 runs with 2 pause batches and 1 failure, the skill's session takes at most 2 + 2 + 1 turns between start and report, and makes no status call while a wait runs
- OSK-AC3 (OSK-B14): Every number in the skill's report equals the matching field of `orchestrate report`, by a test against fixtures
- OSK-AC4 (OSK-B4): On a live orchestration of three or more runs, the orchestrating session's own cost (marginal figure, `rewake` included, measured by [SCO](87-supervision-cost.spec.md)) is at most 3 % of the runs' cost, recorded with date, machine and executor; until then the figure is projected
- OSK-AC5 (OSK-B8, OSK-B10): The skill names no shipped workflow (as SHL-AC1)
- OSK-AC6 (OSK-B2, OSK-B6, OSK-B7, OSK-B9, OSK-B13): Rubric scenarios cover stated dependencies, re-attach after compaction, batch requests and each outcome's offer

## Open questions

- Should the skill offer a recurring schedule for a saved orchestration template? Schedules accept an orchestration target ([SCH](83-schedules.spec.md)) and the schedule skill drives them ([TCK](84-schedule-ticks-and-unattended-fires.spec.md)); whether this skill hands over to it after a template is saved is open. Owner: owner.
