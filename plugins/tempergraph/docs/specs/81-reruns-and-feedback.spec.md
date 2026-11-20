---
title: Reruns, rewinds and feedback
type: component
status: review
prefix: RRN
adrs: [0073, 0074, 0072]
---

# Reruns, rewinds and feedback

## 1. Overview

Every way a person can make a run do work again, and every way their words reach the work. The engine already retries by budget, re-runs infra failures, re-opens stopped runs and takes a person's `retry` or `back` with feedback at a pause ([BUD](08-budgets-and-failures.spec.md), [HUM](07-gate-and-human.spec.md), [DUR](09-durability-and-resume.spec.md)). This spec adds three things ([R-070](../research/R-070-config-overrides-and-reruns-gaps.rsrch.md)):

- **Feedback everywhere a person resumes**, given once or as a lasting **ruling** that every later attempt of the units it names, and their judges, are shown until it is revoked ([ADR-0074](../adr/0074-feedback-can-be-a-lasting-ruling.adr.md)).
- **Rewind**: a person's decision that sends a live thread back to any unit it has completed, not only to the gate's declared back targets.
- **Rerun**: a new thread forked from any earlier thread, finished ones included, at the checkpoint before a chosen unit, keeping every earlier verdict and linked to its source ([ADR-0073](../adr/0073-rewind-on-the-thread-rerun-as-a-linked-fork.adr.md)).

Settings may change at every one of these points ([RST §2.6](80-run-settings-and-overrides.spec.md)).

## 2. Contract

```python
def resume(workflow: str, thread_id: str, decision: Decision | None, inputs: dict[str, str],
           feedback: Feedback | None, options: RunOptions) -> ExitCode: ...
def rerun(workflow: str, source_thread: str, start_at: UnitRef | Literal["start"],
          feedback: Feedback | None, options: RunOptions) -> ExitCode: ...
```

`Feedback`, `Ruling` and `UnitRef` are defined in [CON §2.12](01-contracts.spec.md).

### 2.1 Every way to run again

| Way | Who | Thread | Starts at | Owner |
|---|---|---|---|---|
| Automatic retry | Engine, by budget | same | the unit's step | [BUD](08-budgets-and-failures.spec.md) |
| Infra rerun | Engine, by counter | same | the same attempt number and rung | [BUD](08-budgets-and-failures.spec.md) |
| Trip back | Engine, by route, claim or attribution | same | a declared back target | [BUD-B4](08-budgets-and-failures.spec.md) |
| Automatic re-open | Engine, as the person's retry given in advance | same | the stopped unit | [BUD-B6](08-budgets-and-failures.spec.md) |
| `retry`, `back:<unit>` at a pause or a stop | Person | same | the paused unit, or a declared back target | [HUM §2.2](07-gate-and-human.spec.md) |
| Continue an unfinished thread | Person | same | the pending nodes | [DUR §2.1](09-durability-and-resume.spec.md) |
| One map item, slot or member | Person, addressed by `unit.item` | same | that item | [HUM-B3](07-gate-and-human.spec.md) |
| `rewind:<unit>` | Person | same | any completed unit on the path (§2.3) | this spec |
| `rerun --from <unit>` | Person | new, linked | the checkpoint before that unit (§2.4) | this spec |
| `rerun --from start` | Person | new, linked | the first unit, with the source's resolved input | this spec |
| Orchestration node re-open or rerun | Supervisor (infra only) or person | per the node | per the engine verbs | [ORC](45-orchestration.spec.md), §2.6 |

### 2.2 Feedback

Given with `--feedback <text>` or `--feedback-file <path>` (at most 8 000 characters), on `resume` and `rerun`. The text is stored in the run's local evidence file, scrubbed in every record, and never placed on argv ([SEC §2.3](14-security.spec.md)); records carry its id and length only.

| Resume with | Feedback goes to |
|---|---|
| `proceed` | The next unit on the path, as "Notes from a person", on its first attempt |
| `proceed` at a breakpoint ([FLX §2.5](74-flow-extensions.spec.md)) | The unit about to run, on its first attempt, and its judge |
| `retry` | The retried step and its judge (unchanged) |
| `back:<unit>`, `rewind:<unit>` | That unit's visit reason (unchanged for `back`) and its judge's engine blocker that every point is addressed |
| `stop` | The ledger's intervention row as the stop's cause (local evidence only) |
| No decision, `unfinished` thread | The pending unit's next attempt and its judge |
| `rerun --from <unit>` | That unit's visit reason in the new thread |
| `event:`, `answer:` | Refused (exit 2): the value or the answer is the input |

`--ruling` makes the same text a ruling (below) instead of one-time feedback.

| `Ruling` behaviour | Rule |
|---|---|
| Applies to | The unit it was given at and every later unit on the path, or the units named with `--ruling-for <unit>[,<unit>…]` |
| Shown to | Every attempt of each unit it applies to, under "Rulings from a person" ([PRM §2.1](04-prompt-rendering.spec.md)); each such unit's judge as direction that wins over a reference, with one engine blocker per attempt: the output follows every ruling ([JDG §2.1](05-judge-and-verdict.spec.md)) |
| Survives | Retries, trips back, rewinds, resumes and engine moves ([MIG](62-state-and-run-migration.spec.md)); copied into a rerun unless `--drop-rulings` |
| Ends | `resume --revoke-ruling <id>`, recorded; never by the engine |
| Limits | At most 10 active rulings and 16 000 characters together per thread; beyond that the resume is refused with exit 2 naming the oldest |
| A blocker the judge marks `no_change` against a ruling | Escalates: the ruling and the work conflict, and a person decides ([JDG §2.2](05-judge-and-verdict.spec.md)) |

### 2.3 Rewind

`rewind:<unit>` is a decision ([CON §2.9](01-contracts.spec.md)) accepted on a `paused`, `stopped` or `unfinished` thread.

| Rule | Detail |
|---|---|
| Target | A unit that completed on the thread's current path before the pending or stopped unit: a top-level unit, a parallel block or branch, a map unit, or `unit.item` for one item |
| Effect | As a trip back ([BUD-B4](08-budgets-and-failures.spec.md)): the target's and every later unit's verdicts, judgements and artifacts on the path are cleared, files in the workspace are untouched, the target gets a fresh retry budget and starts its ladder at rung 1 |
| A pending pause | Closed as answered by the rewind; the intervention row records `rewind` |
| Budgets | No loop budget is charged; a person's rewind counts against the human cap like a retry |
| Units with external effects | If a cleared unit produced a `pull_request`, `tracker_issue` or `wiki_page` artifact, or ran a script with `side_effects: external`, the resume is refused with exit 2 listing them unless `--accept-external` is given; the effects are never undone by the engine |
| Rulings | Kept |

`back:<unit>` keeps its meaning: the gate's own vocabulary, limited to declared targets, resetting that pair's loop budget.

### 2.4 Rerun

`rerun <workflow> <thread> --from <unit>[.<item>] | --from start [options]` starts a new thread from a source thread in any state but `none` and `running`.

| Rule | Detail |
|---|---|
| New thread | `<workflow>/<task_id>~r<n>` (`n` one above the source's highest rerun), or `--task-id <id>`; refused (exit 2) if it exists ([CON §2.9](01-contracts.spec.md)) |
| Fork point | The source's checkpoint just before the step node of `<unit>` on its last visit, found in the thread's checkpoint history; `start` is the checkpoint before the first unit. The new thread is written from that checkpoint's values; the source's history is not changed |
| Kept | The resolved input (never resolved again, so no question is asked twice); the verdicts, judgements, artifacts, answers and event values of every unit before the fork point; the source's settings snapshot ([RST §2.6](80-run-settings-and-overrides.spec.md)), then the rerun's own `--set`, `--unset`, `--profile`; rulings unless `--drop-rulings` |
| Cleared | `<unit>` and everything after it on the path, as a trip back |
| Workflow version | The current content, checked against the source's by the tests of [MIG §2.5](62-state-and-run-migration.spec.md) with `<unit>` as the pending unit; a failed test refuses with exit 2 |
| Workspace, worktree workflow | A new worktree on a new branch `<branch>~r<n>` from the source branch's tip (default, `--workspace current`), or from the commit recorded when the source entered `<unit>` (`--workspace at-unit`; refused if none is recorded). `--same-branch` reuses the source's branch, only when the source is `finished`; the source is then marked `superseded_by` |
| Workspace, in place | Files as they are now; the start prints one warning saying so |
| External effects | As for rewind: units after the fork point with external effects in the source need `--accept-external` |
| Budgets | Fresh: retry, loop, human cap, attempt allowance; the run cost cap counts the new thread only |
| Records | `run_started` with `origin: rerun` and `rerun_of {thread, unit, checkpoint_id, workflow_version}`; the source's run folder gains `lineage.json` listing its reruns ([LOS §2.1](33-local-observability-store.spec.md)); status rows show `rerun_of` and `reruns` |

`rerun --check` resolves the fork point, the workspace plan, the settings and the external-effects list, prints them and creates nothing (contract C13).

### 2.5 Thread state against action

| State | `retry` / `back` | `rewind` | feedback, no decision | `--set` alone | `rerun` from it |
|---|---|---|---|---|---|
| `paused` | yes | yes | refused (a pause needs a decision) | with a decision | yes |
| `stopped` | yes | yes | refused | with a decision | yes |
| `unfinished` | refused | yes | yes | yes | yes |
| `finished` | refused | refused | refused | refused | yes |
| `running` | refused | refused | refused | refused | refused |
| `none` | refused | refused | refused | refused | refused |

### 2.6 Orchestrations

`orchestrate answer` passes `--feedback`, `--ruling` and `--set` through to `resume`. `orchestrate rerun <id> <node> [--item i] --from <unit> [options]` runs `rerun` on the node's thread, points the node at the new thread, appends a `rerun` event with `by: person` and leaves the old thread as history; the supervisor never reruns on its own (C16).

## 3. Behaviours

**RRN-B1 A ruling reaches later judges.** Given a run paused at `plan` where a person resumes with `retry --ruling --feedback "Keep the public API unchanged"`, when `plan`, `expand` and `code` later run, then each of their attempts shows the ruling, each of their judges grades the engine blocker for it, and a `code` retry two visits later still shows it.

**RRN-B2 One-time feedback stays one-time.** Given `retry --feedback "rename the flag"` without `--ruling`, when the retry passes and `code` later runs, then `code` never sees the text.

**RRN-B3 Proceed with a note.** Given an approval pause after `plan`, when the person resumes `proceed --feedback "phase 3 is optional"`, then the recorded verdict stays PROCEED, `expand`'s first attempt shows the note, and no retry is charged.

**RRN-B4 Feedback on an unfinished thread.** Given a thread drained by `stop --drain` before `code` started, when `resume --feedback "use the existing retry helper"` runs, then `code`'s first attempt and its judge show it; a `--decision proceed` on the same thread is refused with exit 2.

**RRN-B5 Rewind past the declared targets.** Given a run paused at `release` whose gate lists `back_targets: [code]`, when a person resumes `rewind:plan --feedback "the plan missed the migration"`, then `plan`, `expand`, `code` and `release` are cleared, `plan` starts at rung 1 with the feedback as its visit reason, no loop budget is charged, and the human cap rises by one.

**RRN-B6 External effects need consent.** Given a finished run whose `release` step opened a pull request, when `rerun --from code` is given without `--accept-external`, then it exits 2 listing `release: pull_request`; with it, the new thread runs and its finalizer follows the workflow's own rule for an existing pull request.

**RRN-B7 Rerun keeps earlier verdicts.** Given a finished thread `temperspec/PROJ-12`, when `rerun temperspec PROJ-12 --from code --set code.model=large --feedback "handle the empty list"` runs, then a thread `temperspec/PROJ-12~r1` starts at `code` with triage, discovery, plan and expand kept as passed (no session and no judge runs for them), `code` uses `large`, the feedback is the visit reason, and both threads' status rows show the link.

| Unit | Source thread | Rerun thread |
|---|---|---|
| triage, discovery, plan, expand | passed | kept, not run |
| code | passed | runs, fresh budget |
| release | passed | runs after code passes |
| finalizer | ran | runs |

**RRN-B8 Rerun from start reuses the input.** Given a source whose request resolved after the person answered two `needs` questions, when `rerun --from start` runs, then no question is asked and the resolved input is identical (digest equal).

**RRN-B9 Rerun refuses a broken fork.** Given the workflow removed the unit `discovery` since the source ran, when `rerun --from code` runs, then it exits 2 with the MIG break `units behind` naming `discovery`, and nothing is created.

**RRN-B10 Rerun with only settings changed.** Given `rerun --from code --set code.model=small` with no feedback, when self-improvement reads the pair, then the rerun is recorded as an experiment on the source, not as a person's rejection of it ([FBK](41-feedback-and-judge-reliability.spec.md)); a rerun of a finished source with feedback is a candidate outcome signal "reworked" for the source's gates from `<unit>` on, never a label by itself.

**RRN-B11 Revoke a ruling.** Given an active ruling `r2`, when `resume --decision retry --revoke-ruling r2` runs, then the next attempt does not show it, its judge has no blocker for it, and the run log records the revocation with who made it.

## 4. Error conditions

| Condition | Result |
|---|---|
| `rewind` to a unit not completed on the current path | Exit 2, naming the completed units |
| `rewind` or `rerun` across external effects without `--accept-external` | Exit 2, listing unit and artifact kind |
| `rerun` from a `running` or `none` thread | Exit 2 |
| `rerun --workspace at-unit` with no recorded commit for the unit | Exit 2, suggesting `--workspace current` |
| `--same-branch` on a source that is not `finished` | Exit 2 |
| Feedback over 8 000 characters; rulings over their limits | Exit 2 |
| `--revoke-ruling` with an unknown id | Exit 2 |
| Feedback with `event:` or `answer:` | Exit 2 |

## 5. Design notes

- **Same thread for a correction, a new thread for a do-over.** A rewind keeps one run's story in one thread while it is still live. A finished thread's finalizer has run, its stats row and its improvement record exist, and a pull request may be open; reopening it would rewrite what was reported. A rerun leaves it as it was and links to it, as Temporal's reset starts a new run and keeps the old history, and as Argo's resubmit makes a new workflow ([R-070](../research/R-070-config-overrides-and-reruns-gaps.rsrch.md) F20; [ADR-0073](../adr/0073-rewind-on-the-thread-rerun-as-a-linked-fork.adr.md)).
- **LangGraph does the forking.** The checkpointer keeps each thread's history; reading the checkpoint before a unit and writing its values to a new thread id is the public time-travel mechanism, so no engine-owned history is needed ([ADR-0002](../adr/0002-langgraph-graph-runtime.adr.md)).
- **Fresh sessions stay the rule.** Every retry, rewind and rerun starts a fresh session; continuing an agent's own conversation is an open question.
- Rewind and rerun spend nothing before the first session of the restarted unit, and refuse before they write ([CLI §4](17-engine-cli.spec.md)).

## 6. Acceptance criteria

- [ ] RRN-AC-1 Every row of §2.2's feedback table and of §2.5 is tested, including refusals that write nothing.
- [ ] RRN-AC-2 A ruling given at unit 1 of a five-unit fixture appears in every later prompt and judge brief across a retry, a trip back, a rewind and a resume, and in none after its revocation.
- [ ] RRN-AC-3 A rerun from unit k of a finished fixture starts no session for units before k and leaves the source checkpoint byte-for-byte unchanged.
- [ ] RRN-AC-4 `rerun --check` and `rerun` agree on every refusal in a corpus of sources.
- [ ] RRN-AC-5 Every refusal for external effects names each unit and kind; no rewind or rerun crosses one without `--accept-external`.
- [ ] RRN-AC-6 Feedback and ruling text appears in no argv, ledger row, stats row, finding or published artifact (canary test, [SEC-B2](14-security.spec.md)).

## Open questions

| Question | Owner |
|---|---|
| Should a retry continue the previous session, with the feedback as the next turn, where the executor declares session resume? Cheaper and keeps context, but breaks the fresh-session rule and differs across executors. Needs a paired measurement. | Owner |
| Should an agent caller (`--as-agent`) be allowed to give rulings, or only one-time feedback? First release allows both and records the caller. | Owner |

## References

