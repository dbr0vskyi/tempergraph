# Reruns, rewinds and feedback

## Purpose

Every way a person can make a run do work again, and every way their words reach the work. The engine already retries by budget, re-runs infra failures, re-opens stopped runs and takes a person's `retry` or `back` with feedback at a pause ([BUD](budgets-and-failures.spec.md), [HUM](gate-and-human.spec.md), [DUR](durability-and-resume.spec.md)). This spec adds feedback everywhere a person resumes, given once or as a lasting ruling that every later attempt of the units it names, and their judges, are shown until it is revoked ([ADR `feedback-can-be-a-lasting-ruling`](../adr/feedback-can-be-a-lasting-ruling.adr.md)); rewind, a person's decision that sends a live thread back to any unit it has completed; and rerun, a new thread forked from any earlier thread at the checkpoint before a chosen unit, keeping every earlier verdict and linked to its source ([ADR `rewind-on-the-thread-rerun-as-a-linked-fork`](../adr/rewind-on-the-thread-rerun-as-a-linked-fork.adr.md), [research `config-overrides-and-reruns-gaps`](../research/config-overrides-and-reruns-gaps.rsrch.md)). Settings may change at every one of these points ([RST-B26](run-settings-and-overrides.spec.md)). Every retry, rewind and rerun starts a fresh session, spends nothing before the restarted unit's first session, and refuses before it writes ([CLI-B17](engine-cli.spec.md)). People answering runs, orchestration and the improvement loop depend on it; design notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `budgets-and-failures.spec.md`: trip back clears (BUD-B4); automatic re-open (BUD-B6)
- `contracts.spec.md`: thread states and decisions (CON-B12)
- `durability-and-resume.spec.md`: resume by thread state (DUR-B9)
- `feedback-and-judge-reliability.spec.md`: feedback labels and judge reliability
- `flow-extensions.spec.md`: operator breakpoints (FLX-B10)
- `gate-and-human.spec.md`: several pending gates (HUM-B3); decisions (HUM-B12)
- `judge-and-verdict.spec.md`: judge and verdict
- `local-observability-store.spec.md`: state root top level (LOS-B7)
- `orchestration.spec.md`: orchestration of runs
- `overview.spec.md`: read-only verbs call no model (OVR-B15)
- `prompt-rendering.spec.md`: sections and their order (PRM-B6)
- `run-settings-and-overrides.spec.md`: one resolver (RST-B16)
- `security.spec.md`: canary (SEC-B2); scrubbing (SEC-B8)
- `state-and-run-migration.spec.md`: a workflow changed under a thread (MIG-B15)
- `worktree-mode.spec.md`: worktree mode

## Behaviours

### RRN-B12 Every way to run again

WHEN work is done again THE engine SHALL keep each way to its owner: an automatic retry by budget, an infra rerun by counter at the same attempt number and rung, a trip back to a declared back target ([BUD-B4](budgets-and-failures.spec.md)) and an automatic re-open as the person's retry given in advance ([BUD-B6](budgets-and-failures.spec.md)), all on the same thread; a person's `retry` or `back:<unit>` at a pause or stop ([HUM-B12](gate-and-human.spec.md)), continuing an unfinished thread at its pending nodes ([DUR-B9](durability-and-resume.spec.md)) and one map item, slot or member addressed `unit.item` ([HUM-B3](gate-and-human.spec.md)), on the same thread; and, owned here, `rewind:<unit>` on the same thread to any completed unit on the path, `rerun --from <unit>` and `rerun --from start` on a new linked thread, and an orchestration node's rerun by a person ([ORC](orchestration.spec.md)), the supervisor re-opening only for infrastructure.

- GIVEN a finished thread WHEN a person wants work done again THEN only `rerun` is accepted

### RRN-B13 The resume and rerun calls

WHEN a person resumes or reruns THE engine SHALL take `resume(workflow, thread_id, decision, inputs, feedback, options)` and `rerun(workflow, source_thread, start_at, feedback, options)`, `start_at` a `UnitRef` or `start` ([RST-B16](run-settings-and-overrides.spec.md)), and `Feedback` as `text_ref` (a pointer into the local evidence file, never the text), `chars`, `ruling` (bool) and `applies_to` (a list of `UnitRef` for a ruling, empty meaning the unit given at and every later unit).

- GIVEN feedback WHEN recorded THEN records carry its id and length only

### RRN-B14 Feedback

WHEN `resume` or `rerun` takes `--feedback <text>` or `--feedback-file <path>` (at most 8,000 characters) THE engine SHALL store the text in the run's local evidence file, scrub it in every record and never place it on argv ([SEC-B8](security.spec.md)); give it on `proceed` to the next unit's first attempt as "Notes from a person", and at a breakpoint ([FLX-B10](flow-extensions.spec.md)) to the unit about to run and its judge; on `retry` to the retried step and its judge; on `back:<unit>` or `rewind:<unit>` to that unit's visit reason and its judge's engine blocker that every point is addressed; on `stop` to the ledger's intervention row as the stop's cause (local evidence only); with no decision on an `unfinished` thread to the pending unit's next attempt and its judge; on `rerun --from <unit>` to that unit's visit reason in the new thread; and refuse it with exit 2 alongside `event:` or `answer:`, whose value is the input.

- GIVEN feedback over 8,000 characters WHEN resumed THEN it exits 2

### RRN-B2 One-time feedback stays one-time

WHEN feedback is given without `--ruling` THE engine SHALL show it only where RRN-B14 says.

- GIVEN `retry --feedback "rename the flag"` WHEN the retry passes and `code` later runs THEN `code` never sees the text

### RRN-B3 Proceed with a note

WHEN a person proceeds with feedback THE engine SHALL keep the verdict PROCEED, show the note to the next unit's first attempt and charge no retry.

- GIVEN an approval pause after `plan` WHEN resumed `proceed --feedback "phase 3 is optional"` THEN `expand`'s first attempt shows the note and no retry is charged

### RRN-B4 Feedback on an unfinished thread

WHEN an unfinished thread is resumed with feedback and no decision THE engine SHALL show it to the pending unit's first attempt and its judge, and refuse a decision on that thread with exit 2.

- GIVEN a thread drained before `code` WHEN `resume --feedback "use the existing retry helper"` runs THEN `code`'s first attempt and its judge show it, and `--decision proceed` is refused

### RRN-B15 Rulings

WHEN `--ruling` makes feedback a ruling (`Ruling`: `id`, `feedback`, `given_at`, `by` and `at`, optional `revoked_at` and `revoked_by`, kept in state under its own reducer and never cleared by a trip back) THE engine SHALL apply it to the unit it was given at and every later unit, or the units named by `--ruling-for <unit>[,<unit>…]`; show it to every attempt of each such unit under "Rulings from a person" ([PRM-B6](prompt-rendering.spec.md)) and to each one's judge as direction that wins over a reference, with one engine blocker per attempt that the output follows every ruling ([JDG](judge-and-verdict.spec.md)); keep it across retries, trips back, rewinds, resumes and engine moves ([MIG](state-and-run-migration.spec.md)) and copy it into a rerun unless `--drop-rulings`; end it only by `resume --revoke-ruling <id>`, recorded, never by the engine, an unknown id exiting 2; refuse beyond 10 active rulings or 16,000 characters together per thread with exit 2 naming the oldest; and escalate when the judge marks the ruling's blocker `no_change`, since the ruling and the work conflict.

- GIVEN 10 active rulings WHEN an eleventh is given THEN it exits 2 naming the oldest

### RRN-B1 A ruling reaches later judges

WHEN a ruling is given THE engine SHALL show it to every later attempt of the units it applies to and their judges.

- GIVEN `retry --ruling --feedback "Keep the public API unchanged"` at `plan` WHEN `plan`, `expand` and `code` later run THEN each attempt shows it, each judge grades its blocker, and a `code` retry two visits later still shows it

### RRN-B11 Revoke a ruling

WHEN a ruling is revoked THE engine SHALL show it to no later attempt or judge and record the revocation with who made it.

- GIVEN an active ruling `r2` WHEN `resume --decision retry --revoke-ruling r2` runs THEN the next attempt does not show it, its judge has no blocker for it, and the run log records who revoked it

### RRN-B16 Rewind

WHEN `rewind:<unit>` ([CON-B12](contracts.spec.md)) is given on a `paused`, `stopped` or `unfinished` thread THE engine SHALL accept as target a unit completed on the current path before the pending or stopped unit (a top-level unit, a parallel block or branch, a map unit, or `unit.item`), refusing another with exit 2 naming the completed units; clear the target's and every later unit's verdicts, judgements and artifacts on the path as a trip back ([BUD-B4](budgets-and-failures.spec.md)), leaving the workspace's files, with a fresh retry budget for the target starting its ladder at rung 1; close a pending pause as answered by the rewind with `rewind` in the intervention row; charge no loop budget and count it against the human cap like a retry; refuse with exit 2 listing them, unless `--accept-external`, when a cleared unit produced a `pull_request`, `tracker_issue` or `wiki_page` artifact or ran a script with `side_effects: external`, never undoing the effects; and keep rulings, `back:<unit>` keeping its meaning as the gate's own declared targets that reset that pair's loop budget.

- GIVEN `rewind` to a unit not completed on the current path WHEN resumed THEN it exits 2 naming the completed units

### RRN-B5 Rewind past the declared targets

WHEN a person rewinds to a unit the gate does not list as a back target THE engine SHALL clear it and every later unit and restart it.

- GIVEN a pause at `release` with `back_targets: [code]` WHEN resumed `rewind:plan --feedback "the plan missed the migration"` THEN `plan`, `expand`, `code` and `release` are cleared, `plan` starts at rung 1 with the feedback as its visit reason, no loop budget is charged and the human cap rises by one

### RRN-B17 Rerun

WHEN `rerun <workflow> <thread> --from <unit>[.<item>] | --from start [options]` runs from a source in any state but `none` and `running` (else exit 2) THE engine SHALL name the new thread `<workflow>/<task_id>~r<n>` (`n` one above the source's highest rerun) or `--task-id <id>`, refused if it exists; fork at the source's checkpoint just before the step node of `<unit>` on its last visit (`start` the checkpoint before the first unit), writing the new thread from its values and leaving the source's history unchanged; keep the resolved input (never resolved again), the verdicts, judgements, artifacts, answers and event values of every unit before the fork point, the source's settings snapshot then the rerun's own `--set`, `--unset` and `--profile`, and rulings unless `--drop-rulings`; clear `<unit>` and everything after it as a trip back; check the current content against the source's by the tests of [MIG-B15](state-and-run-migration.spec.md) with `<unit>` pending, refusing a failed test with exit 2; require `--accept-external` as for rewind; give fresh retry, loop, human-cap and attempt budgets, the run cost cap counting the new thread only; record `run_started` with `origin: rerun` and `rerun_of {thread, unit, checkpoint_id, workflow_version}`, add `lineage.json` listing reruns to the source's run folder ([LOS-B7](local-observability-store.spec.md)) and show `rerun_of`, `reruns` and `superseded_by` on status rows; and with `rerun --check` print the fork point, workspace plan, settings and external-effects list and create nothing (OVR-B15).

- GIVEN `rerun` from a `running` thread WHEN run THEN it exits 2
- GIVEN a source whose `review` sent the run back to `draft` and which paused on that visit of `draft` WHEN `rerun --from draft` runs THEN the new thread starts at `draft` and goes on to `review`

### RRN-B18 Rerun workspace

WHEN a rerun of a worktree workflow starts THE engine SHALL make a new worktree on a new branch `<branch>-r<n>` ([WTR](worktree-mode.spec.md); `~` is not allowed in a ref) from the source branch's tip (`--workspace current`, the default) or from the commit recorded when the source entered `<unit>` (`--workspace at-unit`, exit 2 suggesting `current` when none is recorded); with `--same-branch`, only on a `finished` source (else exit 2 `same_branch_not_finished`, nothing created), reuse the source's branch, mark the source `superseded_by` in its `lineage.json` and take over its kept worktree, re-attached when gone; and for an in-place workflow use the files as they are now, printing one warning.

- GIVEN `--same-branch` on a stopped source WHEN rerun THEN it exits 2 `same_branch_not_finished`

### RRN-B6 External effects need consent

WHEN a rewind or rerun would clear a unit with external effects THE engine SHALL refuse without `--accept-external`, listing each unit and kind.

- GIVEN a finished run whose `release` opened a pull request WHEN `rerun --from code` runs without `--accept-external` THEN it exits 2 listing `release: pull_request`, and with it the new thread runs and its finalizer follows the workflow's own rule for an existing pull request

### RRN-B7 Rerun keeps earlier verdicts

WHEN a rerun starts at a unit THE engine SHALL run no session and no judge for the units before it and link both threads.

- GIVEN a finished thread `wf/PROJ-12` WHEN `rerun wf PROJ-12 --from code --set code.model=large --feedback "handle the empty list"` runs THEN `wf/PROJ-12~r1` starts at `code` with triage, discovery, plan and expand kept as passed, `code` uses `large` with the feedback as its visit reason, `release` and the finalizer run after it, and both status rows show the link

### RRN-B8 Rerun from start reuses the input

WHEN `rerun --from start` runs THE engine SHALL ask no question and use the source's resolved input.

- GIVEN a source whose request resolved after two answered `needs` questions WHEN `rerun --from start` runs THEN no question is asked and the input digest is equal

### RRN-B9 Rerun refuses a broken fork

WHEN the workflow changed so the fork fails a MIG test THE engine SHALL exit 2 with the break and create nothing.

- GIVEN `discovery` removed since the source ran WHEN `rerun --from code` runs THEN it exits 2 with the break `units behind` naming `discovery`

### RRN-B10 Rerun with only settings changed

WHEN self-improvement reads a rerun and its source THE loop SHALL record a rerun with only settings changed as an experiment on the source, not a person's rejection ([FBK](feedback-and-judge-reliability.spec.md)), and a rerun of a finished source with feedback as a candidate outcome signal "reworked" for the source's gates from `<unit>` on, never a label by itself.

- GIVEN `rerun --from code --set code.model=small` with no feedback WHEN read THEN it is recorded as an experiment

### RRN-B19 Thread state against action

WHEN a person acts on a thread THE engine SHALL accept on `paused` and `stopped` `retry`, `back`, `rewind`, `--set` with a decision and `rerun`, refusing feedback with no decision; on `unfinished` `rewind`, feedback with no decision, `--set` alone and `rerun`, refusing `retry` and `back`; on `finished` only `rerun`; and on `running` and `none` nothing.

- GIVEN a `finished` thread WHEN `rewind:plan` is given THEN it exits 2 and nothing is written

### RRN-B20 Orchestrations

WHEN `orchestrate answer` resumes a node THE engine SHALL pass `--feedback`, `--ruling` and `--set` through to `resume`, and `orchestrate rerun <id> <node> [--item i] --from <unit> [options]` SHALL run `rerun` on the node's thread, point the node at the new thread, append a `rerun` event with `by: person` and keep the old thread as history, the supervisor never rerunning on its own (C16).

- GIVEN `orchestrate rerun` on a node WHEN run THEN the node points at the new thread and a `rerun` event records `by: person`

## Acceptance criteria

- RRN-AC1 (RRN-B14, RRN-B19, RRN-B2, RRN-B3, RRN-B4, RRN-B13): Every case of RRN-B14 and RRN-B19 is tested, including refusals that write nothing
- RRN-AC2 (RRN-B15, RRN-B1, RRN-B11): A ruling given at unit 1 of a five-unit fixture appears in every later prompt and judge brief across a retry, a trip back, a rewind and a resume, and in none after its revocation
- RRN-AC3 (RRN-B17, RRN-B7, RRN-B8, RRN-B12): A rerun from unit k of a finished fixture starts no session for units before k and leaves the source checkpoint byte-for-byte unchanged
- RRN-AC4 (RRN-B17, RRN-B9, RRN-B18): `rerun --check` and `rerun` agree on every refusal in a corpus of sources
- RRN-AC5 (RRN-B6, RRN-B16, RRN-B5): Every refusal for external effects names each unit and kind; no rewind or rerun crosses one without `--accept-external`
- RRN-AC6 (RRN-B14, RRN-B10, RRN-B20): Feedback and ruling text appears in no argv, ledger row, stats row, finding or published artifact (canary test, [SEC-B2](security.spec.md))

## Open questions

- Should a retry continue the previous session, with the feedback as the next turn, where the executor declares session resume? Cheaper and keeps context, but breaks the fresh-session rule and differs across executors; needs a paired measurement. Until answered: a fresh session. Owner: owner.
- Should an agent caller (`--as-agent`) be allowed to give rulings, or only one-time feedback? Until answered: both, with the caller recorded. Owner: owner.
