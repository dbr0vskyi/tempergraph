---
title: Orchestrator skill
type: component
status: review
prefix: OSK
adrs: [0035, 0037, 0039]
---

# Orchestrator skill

## 1. Overview

The orchestrator skill (`tempergraph:orchestrate`) is the conversation side of an [orchestration](45-orchestration.spec.md). It turns a request for many runs ("run discovery on these five tickets, then plan each one, then deliver them two at a time") into an orchestration file, shows the person the engine-drawn plan, its run count and projected cost, starts it after approval, and then sleeps until the engine says a person is needed. It walks the person through each pause, one at a time, and reports at the end.


## 2. Contract

### 2.1 When it is used

| Request shape | Skill used |
|---|---|
| One run, start, resume, status of one thread | Run driver |
| Several runs, or a run that must wait for another's result | Orchestrator |
| One workflow over a list of targets, K at a time | Orchestrator (a one-node map; [ADR-0038](../adr/0038-batch-is-a-one-node-orchestration.adr.md)) |
| A saved orchestration template by name, with arguments | Orchestrator |
| A question about a live or past orchestration | Orchestrator (read-only verbs) |

The run driver hands a request over when it names more than one run or a dependency; the orchestrator hands a single-run question back.

### 2.2 Principles

Inherited from the run driver: the person decides every gate, one at a time (contract C6); ask, never guess; check before spend; wait, do not poll. Added for many runs:

| Principle | Meaning |
|---|---|
| The plan is a file | Every run, dependency, policy and cap is in the orchestration file the person approved; the skill keeps no second queue. After a compaction it re-reads `orchestrate status`, never its memory. |
| One wake per need | The skill waits on one background `orchestrate wait` and is woken only for attention or an end ([ADR-0037](../adr/0037-attention-batched-waking-of-the-orchestrating-session.adr.md)). |
| Status, not logs | It reads the orchestration status document and `facts`; it never reads a run log, transcript or checkpoint. |
| Show the price first | Run count, projected cost, the cap and any large-orchestration warning are shown before approval. |
| Failures are not successes | A node that failed, was skipped or was cancelled is listed as such in every report. |

### 2.3 Procedure

1. **Preflight, once per session**, as the run driver: engine current, catalog read.
2. **Draft.** From the request, pick the workflows from the catalog, the nodes, `after` edges, `from` inputs, maps, phases, approval nodes where the person wants a sign-off between waves, `k`, a cap and each node's `on_failure` (default `skip_dependants`, stated aloud). Ask for any declared input the request does not give, at most four rounds.
3. **Validate and plan.** Write the draft to the orchestration's scratch path, run `orchestrate validate` (fix and re-run on exit 2; a `needs` result goes back to the person as questions), then `orchestrate plan --format md`.
4. **Approval.** Show the engine-drawn graph, the node table, the run count, the projected cost range and the cap, and any warning, and offer the raw file. Nothing starts without an explicit yes. A changed plan is approved again.
5. **Start.** `orchestrate start`, announce the id, then start `orchestrate wait <id>` in the background and end the turn.
6. **On exit 3 (attention).** Read `orchestrate status --json`, list the attention items oldest first in one short message, and walk the person through them one at a time: for a paused run show its pause payload from `facts` (kind, reason, artifacts, rubric, decisions) the way the run driver does; for an approval node its question and artifacts; for an `ask` failure the cause and the three choices. Answer each with `orchestrate answer … --relayed` and the person's own decision word, after the person's reply in the conversation, so the host's person turn backs it ([PRV §2.4](85-caller-provenance.spec.md)); then restart the background wait.
7. **On exit 5 or 4.** Report the outcome with each failed, skipped and cancelled node and its cause; offer the actions the state allows (§2.4).
8. **On exit 0.** Report (§2.5) and offer to save the file as a template.
9. **Edits on request.** Build a patch, show it, apply with `orchestrate edit` after a yes.

### 2.4 Outcomes and offers

| Wait exit | Status `state` | The skill offers |
|---|---|---|
| 0 | `finished` | Report; save as template |
| 3 | `attention` | The walk-through of step 6 |
| 4 | `stopped` | Resume stopped runs one by one, or leave them |
| 5 | `finished_with_failures` | Per failed node: its run's own resume offer (as the run driver states it for exit 4 and 5); a new orchestration of the failed and skipped nodes |
| 5 | `halted` | As above, plus continuing the unstarted nodes by an edit |
| 5 | `cost_cap` | Raise the cap (an edit, approved) and `orchestrate resume`, or stop |
| 5 | `supervisor_lost` | `orchestrate resume <id>`; nothing is restarted twice |
| 2 | — | The refusal's message, fixed in the file |

After an infra failure the skill never offers proceed on that run's gate: nothing was judged.

### 2.5 Report

One message: outcome, nodes by state, cost (reported and estimated apart, the incomplete flag, the cap), wall time, branches and pull requests per node from `facts`, pauses with who answered, and each failure with its cause. Figures come from `orchestrate report`; the skill adds no number of its own.

### 2.6 Never

| The skill never | Because |
|---|---|
| Answers a pause, an approval or an `ask` failure itself, in any mode | Contract C6; [ADR-0039](../adr/0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md) |
| Starts runs with `run` for an orchestration's nodes | The supervisor owns starts; a second starter breaks `k`, `exclusive` and identity |
| Edits the orchestration folder, a checkpoint or run state by hand | Edits go through `orchestrate edit`; runs through resume |
| Sets `mode: unattended` or passes `--as-agent` | Reserved and refused |
| Draws the graph by model | The diagram comes from `orchestrate plan` |
| Polls status in a loop or wakes on a timer while a wait is running | One wake per need |

A fix needed inside one run's worktree (for example a failing test a pause points at) is done only when the person asks, by a fresh helper scoped to that worktree that answers no gate; the person then answers the pause.

## 3. Behaviours

**OSK-B1 Approval before spend.** Given a drafted orchestration of 6 runs with a projected cost of $18 to $30 and no cap, when the skill presents it, then it shows the graph, the 6 runs, the range and "no cap", asks for a yes, and starts nothing before it.

**OSK-B2 Dependencies stated, not guessed.** Given "plan each ticket after its discovery", when the skill drafts, then each plan node is `after` its discovery node and takes the discovery's artifact by its declared key; if the discovery workflow declares no artifact the planner can take, the skill asks the person instead of passing prose between runs.

**OSK-B3 Several pauses, one at a time.** Given wait exit 3 with two paused runs and one approval node, when the skill reports, then it lists the three in one message and asks for the oldest first; it resumes nothing until the person answers that one, and never answers the last remaining one for them.

**OSK-B4 Sleep between needs.** Given a running orchestration with no attention, when runs start, pass gates and finish, then the skill's session takes no turn until `orchestrate wait` exits.

| Event while waiting | Skill turn |
|---|---|
| A node starts or finishes | none |
| A gate verdict inside a run | none |
| A run pauses | one, after the settle window, covering every pause in it |
| The orchestration ends | one |

**OSK-B5 Failure explained by cause.** Given a node failed with exit 5 on a spent retry budget and two dependants skipped, when the skill reports, then it names the node, the gate and its blockers from `facts`, names both skipped nodes as skipped (not failed, not done), and offers the run's own resume and a follow-up orchestration of the three.

**OSK-B6 Re-attach after compaction.** Given a long orchestration whose conversation was compacted, when the skill is woken, then it rebuilds what it shows from `orchestrate status` and `facts` only.

**OSK-B7 Batch requests.** Given "run triage on these 12 issues, 4 at a time", when the skill drafts, then it writes one map node with 12 targets and `k: 4`, and the plan shows 12 runs.

## 4. Error conditions

| Condition | Skill behaviour |
|---|---|
| Exit 127 | Send the person to the installer |
| `validate` exit 2 | Fix the file from the message, or ask the person when the fix is a choice |
| The background wait itself dies (session restarted) | Run `orchestrate status`; if the orchestration is live, start a new wait |
| A person asks for a run outside the orchestration | Hand it to the run driver; the orchestration is not edited |

## 5. Design notes

- **Why a separate skill.** The run driver's core is already near its size budget; orchestration adds drafting, approval and multi-pause walk-throughs. Shared text (the pause walk-through, the exit-code table) lives in one reference file both skills read, so the two never drift.
- **What is borrowed from dynamic workflows.** Planning in code (here, in data) with a runtime that drives it; approval with the plan visible; labels and phases; a size warning; saved templates with arguments ([R-035](../research/R-035-dynamic-workflows-as-orchestration-model.rsrch.md) conclusions 1 to 5). The skill does not write a Claude Code workflow script: a workflow agent per run would put a model session in front of every start and wait, and a script cannot take a person's decision mid-run ([ADR-0035](../adr/0035-orchestration-is-data-run-by-a-model-free-supervisor.adr.md)).
- **Where the person sees progress.** Between wakes the person watches the monitor, which renders the orchestration status document like the `/workflows` view: phases, nodes, then a node's run, steps and live session ([ORC §2.8](45-orchestration.spec.md) N8).
- **Assumption** (owner unavailable): the skill runs in Claude Code with background commands; in a host without them, it runs `orchestrate wait` in the foreground and the person's next message continues.

## 6. Acceptance criteria

- [ ] OSK-AC-1 Rubric scenarios cover OSK-B1 (no start without a yes), OSK-B3 (never answers a pause, the last one included) and OSK-B5 (skipped is never reported as done).
- [ ] OSK-AC-2 In a scripted orchestration of 6 runs with 2 pause batches and 1 failure, the skill's session takes at most 2 + 2 + 1 turns between start and report (one per wait exit plus the start and the report), and makes no status call while a wait runs.
- [ ] OSK-AC-3 Every number in the skill's report equals the matching field of `orchestrate report` (test against fixtures).
- [ ] OSK-AC-5 The skill names no shipped workflow (as SHL-AC-1).

## Open questions

| Question | Owner |
|---|---|
| Should the skill offer a recurring schedule for a saved orchestration template? Schedules now accept an orchestration target ([SCH §2.2](83-schedules.spec.md)) and the schedule skill drives them ([TCK §2.6](84-schedule-ticks-and-unattended-fires.spec.md)); whether this skill hands over to it after a template is saved is open. | Owner |

## References

