# Engine CLI

## Purpose

The `tempergraph` command line is the engine's public interface for people, skills and CI. Its verbs are plain words, and its exit codes are the caller contract ([CON-B12, CON-B13](contracts.spec.md), [ADR-0015](../adr/0015-exit-codes-as-caller-contract.adr.md)), so a skill or a CI job can tell waiting from stopped from budget spent. This spec owns the verb words, what each verb writes and whether it spends, and the verbs no other spec owns; a verb owned by another spec is named here with its synopsis and that spec's link. The options a run takes are [23 Run options](run-options.spec.md); lifecycle hooks are [24 Lifecycle hooks](lifecycle-hooks.spec.md).

## Behaviours

### CLI-B1 Check before spend

WHEN `run --check <workflow> <request…>` is given THE engine CLI SHALL resolve the request and preflight the run, print one JSON document with the status `ok`, `needs` (questions with choices), `error` or `broken`, create nothing, and refuse a full `run` in exactly the cases the check refuses.

- GIVEN a valid request WHEN `run --check` runs THEN it prints `ok`, exits 0 and the state root is unchanged
- GIVEN an empty request WHEN `run --check` runs THEN it prints `needs` with the question `request` and exits 2
- GIVEN a workflow whose resolver does not load WHEN `run --check` runs THEN it prints `broken` and exits 1
- GIVEN a request the check refuses with `error` WHEN `run` is given the same request THEN `run` refuses it with the same reason and exits 2

### CLI-B2 Reserved verbs

WHEN a request's first word is a verb name THE engine CLI SHALL refuse it as workflow input.

- GIVEN an older shim that passes `update` to `run` as the request WHEN `run` reads it THEN the run is refused and no thread is made

### CLI-B3 Executors verb

WHEN `executors [--probe]` is given THE engine CLI SHALL list each registered executor with its capabilities, its CLI or library version and each probe fact with its recorded state (`confirmed`, `refuted`, `not run`), and call no model.

- GIVEN the `claude` executor WHEN `executors --probe` runs THEN it shows `restricts_judge_tools` true, the version from `claude --version` and facts P-CC-1 to P-CC-8 with their states
- GIVEN the `antigravity` executor WHEN `executors` runs THEN it shows `restricts_judge_tools` false and facts P-AG-1 to P-AG-9
- GIVEN the `messages-api` executor WHEN `executors` runs THEN it shows `restricts_judge_tools` true by construction, the client library version and the API version header, and no probe fact
- GIVEN a capability that rests on a probe not run WHEN it is listed THEN it is shown as projected

### CLI-B4 A pause ends the process

WHEN a run pauses for a person THE engine CLI SHALL exit 3.

- GIVEN a caller that started `run` in the background WHEN the run pauses at an approval THEN the process exits 3 and the caller learns of the pause with no polling

### CLI-B5 Facts are read-only

WHEN `facts <selector> [--json]` is given THE engine CLI SHALL print the run's state, branch, artifacts by key, pending gates, cost figures, alias, label and origin from the status document and the run log only, with `schema_version`, create nothing and call no model.

- GIVEN a live run WHEN `facts --json` runs THEN the JSON carries `schema_version` and the state root's hash is unchanged

### CLI-B6 One list of what waits on a person

WHEN `attention [--all-roots] [--json]` is given THE engine CLI SHALL print every item waiting on a person, oldest first, each with the thread, workflow, unit and item, pause kind, age, a one-line reason and the exact command that answers it, reading only status documents and orchestration status documents for the items (CLI-B20 adds the loop summaries), and create nothing but the hand-off of a lost runner ([SIL-B29](runs-without-a-final-exit.spec.md), [ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)).

- GIVEN three paused threads (an approval, an escalation and an orchestration's paused node) WHEN `attention` runs THEN it prints three items, oldest first, each with a command that `resume` or `orchestrate answer` accepts
- GIVEN `--all-roots` WHEN `attention` runs THEN it reads every state root in the machine index ([CST-B8](central-run-stats.spec.md)), schedule items included ([TCK-B23, TCK-B24](schedule-ticks-and-unattended-fires.spec.md))
- GIVEN `--json` WHEN `attention` runs THEN the output carries `schema_version`

### CLI-B7 Verb words

WHEN the engine CLI is called THE engine CLI SHALL accept exactly the verbs `run`, `resume`, `rerun`, `config`, `status`, `events`, `logs`, `wait`, `attention`, `list`, `graph`, `report`, `validate`, `audit`, `executors`, `batch`, `orchestrate`, `schedule`, `stop`, `worktree`, `update`, `install`, `workflows`, `upgrade`, `upgrade-check`, `facts`, `stats`, `store`, `hooks`, `improve`, `label`, `labels`, `evals`, `promote-check`, `carry`, `supervision`, `author`, `blueprint`, `literals`, `scaffold`, `outcome`, `self-check` and `help`, and exit 2 on any other first word.

- GIVEN `tempergraph frobnicate` WHEN it runs THEN it exits 2 naming the unknown verb

### CLI-B8 Read-only verbs write nothing

WHEN a verb this spec marks read-only runs THE engine CLI SHALL leave the state root unchanged and start no session, except that `status` and `attention` hand a lost runner to the loop ([SIL-B29](runs-without-a-final-exit.spec.md)); the read-only verbs are `run --check`, `rerun --check`, `config`, `status`, `events`, `logs`, `wait`, `attention`, `list`, `graph`, `report`, `validate`, `audit`, `executors`, `facts`, `stats` (but `stats flush` and `stats sync`), `outcome`, `upgrade --check` and `install --check` and `update --check`.

- GIVEN a fixture state root WHEN each read-only verb runs THEN the state root's hash is unchanged and no process starts except the read-only probes of `executors --probe`

### CLI-B9 Run

WHEN `run <workflow> <request…> [options]` is given THE engine CLI SHALL resolve the request, preflight the run and start it, printing the run's one-line outcome and its resume command on standard error.

- GIVEN a valid request WHEN `run` ends THEN standard error holds one outcome line and the command that resumes the thread

### CLI-B10 Resume

WHEN `resume <workflow> <thread> [--decision …] [--feedback …|--feedback-file <path>] [--ruling] [--ruling-for <units>] [--revoke-ruling <id>] [--accept-external] [--set k=v] [--unset k] [--profile p] [--reload-settings] [--input k=v] [--answers <file>] [--apply-deadline] [--unit <name>] [--escalate] [--unpin]` is given THE engine CLI SHALL continue the thread by its state ([DUR](durability-and-resume.spec.md)), taking feedback, rulings and `rewind:` per [RRN](reruns-and-feedback.spec.md), settings per [RST-B26](run-settings-and-overrides.spec.md), answers for an ask ([ASK](ask-unit.spec.md)), a deadline per [FLX-B8](flow-extensions.spec.md) and an offered model escalation per [LAD-B12](effort-ladder-and-model-escalation.spec.md).

- GIVEN a parallel block with two pending gates WHEN `resume --decision proceed` runs without `--unit` THEN it is refused and names both units ([HUM-B3](gate-and-human.spec.md))
- GIVEN a thread paused with an offered escalation WHEN `resume --escalate` runs THEN the next attempt runs on the offered model

### CLI-B11 Rerun

WHEN `rerun <workflow> <thread> --from <unit>[.<item>]|start [--check] [--feedback …] [--ruling] [--set k=v] [--profile p] [--task-id <id>] [--workspace current|at-unit] [--same-branch] [--drop-rulings] [--accept-external]` is given THE engine CLI SHALL start a new thread forked from the checkpoint before that unit and linked to its source ([RRN-B17, RRN-B18](reruns-and-feedback.spec.md)), writing nothing with `--check`.

- GIVEN `rerun … --from plan --check` WHEN it runs THEN it prints the fork it would make and the state root is unchanged

### CLI-B12 Status, events, logs and wait

WHEN `status [selector] [--detail [--unit <name>] [--no-live]] [--all-roots]`, `events <selector> [--since <seq>] [--follow] [--activity <session_key>] [--json]`, `logs <selector> [--session <key>] [--kind …] [--follow] [--json]` or `wait <selector> [--timeout s]` is given THE engine CLI SHALL print the status document or one thread's detail document ([RDD](run-detail-document.spec.md)), the run-log records and activity lines in order ([EVT-B22, EVT-B23, EVT-B24](run-events.spec.md)), one log from the local store ([LOS-B14, LOS-B15](local-observability-store.spec.md)), or block until the thread has an outcome, respectively, and write nothing.

- GIVEN `status --all-roots` WHEN it runs THEN it reads every state root in the machine index ([CST-B8](central-run-stats.spec.md))
- GIVEN a running thread WHEN `wait <thread> --timeout 5` runs and the thread is still running after 5 s THEN `wait` returns with the thread still running and writes nothing

### CLI-B13 Catalog, diagram, validation and reports

WHEN `list`, `graph <workflow> [--format mermaid|svg|md] [--overlay <thread>]`, `validate <workflow>` or `report [window] [--by unit|executor|version] [--loop] [--switch <workflow>/<switch>] [--risk <workflow>] [--supervision [window] [--by workflow|version|unit|host|level]] [--json]` is given THE engine CLI SHALL print the catalog as versioned JSON or a table, the workflow's diagram from its model ([OBS-B15](observability-and-cost.spec.md)), the validation result with view deferrals and the prompt-tool check, or the cost, friction, loop ([IMD-B22](improvement-data.spec.md)), switch ([CXR-B13](complexity-routing.spec.md)), risk ([JRK-B10](judge-model-by-risk.spec.md)) or supervision ([SUP-B12](supervision-metrics.spec.md)) report, and write nothing.

- GIVEN `graph <workflow> --format mermaid` WHEN it runs THEN it prints a Mermaid diagram; `md` and `json` are drawn too, and `svg` is refused as not in this release
- GIVEN `graph <workflow> --overlay <thread>` WHEN it runs THEN the diagram carries that thread's counts and verdicts

### CLI-B14 Verbs owned by other specs

WHEN a verb owned by another spec is given THE engine CLI SHALL take the synopsis that spec states and write and spend only what it states: `config` ([RST-B31](run-settings-and-overrides.spec.md)), `audit` ([AUD](workflow-audit.spec.md)), `batch` ([ADR-0038](../adr/0038-batch-is-a-one-node-orchestration.adr.md)), `orchestrate` ([ORC-B24, ORC-B2, ORC-B6, ORC-B10, ORC-B14](orchestration.spec.md)), `schedule` ([SCH-B27](schedules.spec.md), [TCK](schedule-ticks-and-unattended-fires.spec.md)), `stop` ([RCT](run-control.spec.md)), `worktree` ([WTR-B27](worktree-mode.spec.md)), `update` and `install` and `workflows` ([UPD](engine-update.spec.md)), `upgrade` and `upgrade-check` ([WUP](workflow-upgrade.spec.md)), `stats` ([OBS-B15](observability-and-cost.spec.md), [CST-B10, CST-B12, CST-B13, CST-B14, CST-B15, CST-B16](central-run-stats.spec.md)), `store` ([LOS-B14, LOS-B15](local-observability-store.spec.md)), `hooks` ([HOK](lifecycle-hooks.spec.md)), `improve` ([PRP-B4, PRP-B12, PRP-B18, PRP-B21, PRP-B8, PRP-B22](improvement-proposals.spec.md), [SRV-B23](session-review.spec.md)), `label` and `labels` ([FBK](feedback-and-judge-reliability.spec.md)), `evals` ([EVS](eval-suites.spec.md), [JCL-B14, JCL-B18](judge-calibration.spec.md), [LIF-B7 to LIF-B16](lifecycle-and-evals.spec.md)), `promote-check` ([PRO](promotion-check.spec.md)), `carry` ([CAR](run-state-on-a-branch.spec.md)), `supervision` ([SHL-B14, SHL-B15](plugin-shell.spec.md), [SCO-B16](supervision-cost.spec.md)), `author` ([AUT-B11, AUT-B12, AUT-B15, AUT-B19, AUT-B24, AUT-B25](workflow-authoring.spec.md), [SCF-B23](blueprint-and-scaffold.spec.md)), `blueprint`, `literals` and `scaffold` ([SCF-B23](blueprint-and-scaffold.spec.md)), `outcome` ([OUT-B18, OUT-B19, OUT-B20, OUT-B21](run-outcome.spec.md)) and `self-check` ([CHK-B17](check-contract-and-command-runs.spec.md)).

- GIVEN `upgrade-check <workflow>` WHEN it runs THEN it does what `upgrade <workflow> --check` does
- GIVEN `supervision hook <event>` with an event's JSON on standard input WHEN it runs THEN it appends to the journal and exits 0 whatever happens

### CLI-B15 Machine output

WHEN a verb prints machine output THE engine CLI SHALL print JSON carrying `schema_version`.

- GIVEN `status --json` WHEN it runs THEN the document's first key is `schema_version`

### CLI-B16 Mutating verbs record their caller

WHEN a mutating verb runs THE engine CLI SHALL classify its caller once, before any write, and record the `caller` block ([PRV](caller-provenance.spec.md)); a read-only verb records none.

- GIVEN `resume` from a Claude Code tool child WHEN it writes its first record THEN the record carries the caller block with kind `agent`
- GIVEN `status` WHEN it runs THEN no caller block is written

### CLI-B17 Usage errors

WHEN a verb names an unknown workflow or option THE engine CLI SHALL exit 2 before any write.

- GIVEN `run nosuchflow "x"` WHEN it runs THEN it exits 2 and the state root is unchanged
- GIVEN `status --nosuchoption` WHEN it runs THEN it exits 2

### CLI-B18 The shim

WHEN the `tempergraph` shim finds no interpreter that has the engine THE shim SHALL exit 127.

- GIVEN a machine whose engine environment was removed WHEN `tempergraph status` runs THEN it exits 127

### CLI-B19 An unhandled error

WHEN an exception reaches the top of the engine CLI THE engine CLI SHALL write an engine-error record and exit 1.

- GIVEN a verb that raises an unexpected error WHEN it ends THEN the engine log holds the error record and the exit code is 1

### CLI-B20 The loop's findings beside what waits

WHEN `attention` is given and a workflow's newest `loop_summary` record ([SIL-B22](self-improvement.spec.md)) holds at least one recorded finding, kept observation or failed review ([SIL-B24](self-improvement.spec.md)) THE engine CLI SHALL print that summary after the items, one block per workflow, newest first, with the thread, the counts of findings recorded and filed, the failed reviews counted by error class, the observations as `category`, `unit` and `confidence`, and the command `tempergraph improve review show <thread>`, and in `--json` as `loop[]` beside `items`, with the failed-review counts as `review_failed`, never as an item waiting on a person.

- GIVEN a thread whose loop child ended with 3 findings recorded, none filed and two kept observations WHEN `attention` runs THEN after the items it shows that thread, 3 recorded, 0 filed, the two observations as category, unit and confidence and no note text
- GIVEN two threads of one workflow whose loop children ended one after the other WHEN `attention` runs THEN it shows the later thread's summary only for that workflow, and `status <thread> --detail` of the earlier thread still shows its own
- GIVEN `--json` WHEN `attention` runs THEN the document holds `loop[]` beside `items` and no summary is among `items`
- GIVEN a workflow whose newest summary holds no finding, no observation and no failed review WHEN `attention` runs THEN it shows nothing for that workflow
- GIVEN a thread whose loop child ended with no finding, no observation and 16 reviews failed as `usage_limit` WHEN `attention` runs THEN after the items it shows that thread with `usage_limit` 16 and the command, and with `--json` its `loop[]` entry holds `review_failed` with `usage_limit` 16

## Acceptance criteria

- CLI-AC1 (CLI-B8, CLI-B5, CLI-B6): Every read-only verb leaves a fixture state root's hash unchanged and starts no process except the read-only probes of `executors --probe`
- CLI-AC2 (CLI-B1): `run --check` and `run` agree on every refusal in a corpus of requests
- CLI-AC3 (CLI-B2, CLI-B7): Every verb word is refused as a request's first word, and the verb words in CLI-B7 equal the verbs the built CLI accepts
- CLI-AC4 (CLI-B4, CLI-B17, CLI-B18, CLI-B19): The exit codes this spec names equal the engine's exit-code constants by a drift test against [CON-B12, CON-B13](contracts.spec.md)
- CLI-AC5 (CLI-B6): `attention` lists every pause of a fixture state root exactly once, oldest first, each with a resume command that `resume` accepts, and leaves the state root unchanged
- CLI-AC6 (CLI-B3): `executors --probe` lists every registered executor's capabilities, version and probe facts with their states, and calls no model
- CLI-AC7 (CLI-B9, CLI-B10, CLI-B11, CLI-B12, CLI-B13, CLI-B14): Every long option the built CLI accepts is named in the engine's specs
- CLI-AC8 (CLI-B15): The JSON output of every verb that has `--json` carries `schema_version`
- CLI-AC9 (CLI-B16): A mutating verb's first record carries a caller block, and a read-only verb writes none
- CLI-AC10 (CLI-B20): After a fixture loop child has ended, `attention` shows the summary of the newest loop child of each workflow with its counts and at most three observations and no note text, carries it as `loop[]` and not as an item in `--json`, and leaves the state root unchanged
- CLI-AC11 (CLI-B20): After a fixture loop child that recorded no finding and no observation and whose reviews all failed as `usage_limit` has ended, `attention` shows its thread with the failed reviews counted by error class and `--json` carries `review_failed` in its `loop[]` entry, and a fixture summary with no finding, no observation and no failed review shows nothing

## Open questions

- Should a person be able to dismiss a loop summary in `attention`? Until answered: no, a summary stays until a later loop child of the same workflow ends. Owner: owner.
