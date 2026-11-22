# Orchestration of runs

## Purpose

An orchestration is a graph of tempergraph runs: which workflow runs on what, in what order, how many at once, what a failure does to the runs after it, and where a person must sign off between waves. A workflow is a graph of steps inside one run; an orchestration is a graph of runs. Like a workflow it is data, validated before any spend and executed by the engine, not by a conversation ([ADR-0035](../adr/0035-orchestration-is-data-run-by-a-model-free-supervisor.adr.md)): orchestration driven by hand from a conversation adds cost on top of run cost, most of it from being woken and re-reading context. A model-free engine process, the supervisor, starts each run through the engine's own `run` verb, watches it through the status document, keeps independent runs moving while one waits for a person, and stops starting new runs when a cap or a failure policy says so; it never calls a model and never answers a gate (OVR-B18). The file holds intent, each run's status holds truth, and the event log holds history ([ADR-0036](../adr/0036-orchestration-state-is-a-file-and-an-event-log.adr.md)); `wait` wakes the orchestrating session once per batch of attention ([ADR-0037](../adr/0037-attention-batched-waking-of-the-orchestrating-session.adr.md)); `batch` is a one-node orchestration ([ADR-0038](../adr/0038-batch-is-a-one-node-orchestration.adr.md)); pauses stay with the person and failures follow node policy ([ADR-0039](../adr/0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md)). The model is borrowed from Claude Code's dynamic workflows and departs from it where runs pause for people, cost real money per rerun and leave branches, so identity is by node id and nothing is replayed ([R-035](../research/R-035-dynamic-workflows-as-orchestration-model.rsrch.md)). The [orchestrator skill](46-orchestrator-skill.spec.md) writes the file with the person, starts it and walks the person through each pause; the monitor shows it read-only; design notes and assumptions are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md). It ships in a later release ([ADR-0132](../adr/0132-release-three-is-workflows-that-compose-run-in-parallel-and-grade-in-the-pipeline.adr.md)).

## Behaviours

### ORC-B18 Orchestration, nodes and threads

WHEN an orchestration starts THE engine SHALL give it an `orchestration_id` of `<name>-<yyyymmdd>-<4 hex>`, keep its file and event log under `<state root>/orchestrations/<orchestration_id>/`, run at most one supervisor for it under an OS file lock (a second refused with exit 2 naming the holder), and name each node's run thread `<workflow>/o-<orchestration_id>-<node>[-<item>]`, so a re-run finds it by name; a node is a `run`, a `map` (one run per target) or an `approval` (a pause owned by the orchestration), becomes ready when every node of its `after` list has finished, and its `phase` is display only.

- GIVEN a second supervisor for one orchestration WHEN started THEN it exits 2 naming the lock holder

### ORC-B19 Orchestration file

WHEN an orchestration file (schema version 1, `<name>.orch.json` when saved as a template) is read THE engine SHALL read `schema_version`, `name` (a slug) and `description` (at most 200 characters), `params` (`{name, meaning, example}`, taken by `{param}` fields in `inputs` and `targets` with the template grammar of [CON-B8](01-contracts.spec.md)), `k` (1 to 16, default 3, runs in flight at once), optional `cost_cap_usd`, `mode` (`attended`; `unattended` refused as reserved), and `nodes` (at least one, at most 50 runs after expansion), every value a constant, a checked number or a scrubbed string so nothing typed reaches a launch ([SEC](14-security.spec.md)).

- GIVEN `mode: unattended` WHEN validated THEN it exits 2, reserved

### ORC-B20 Node fields

WHEN a node is read THE engine SHALL read `id` (a slug unique in the file, never reused for another node), `kind`, `label` and `phase` (at most 40 characters), `after` (acyclic), `workflow` (registered), optional `repo` (another local git repository with an engine state root, whose state root the run uses), `inputs` (name to literal, `{param}` or `{from: <node>, artifact: <key>}` read from the finished upstream run through `facts`), `options` (any settings key, [RST](80-run-settings-and-overrides.spec.md), plus `profiles`, applied on the `flag` layer with `via: orchestration`, `--as-agent` refused), for a map `targets` or `targets_from` (`{node, artifact}`, a JSON array of strings expanded when that node finishes) with `max_items` (1 to 50, required with `targets_from`) and optional `k`, `on_failure` (`skip_dependants` by default, `continue`, `halt`, `ask`), `reopen_infra` (0 to 3, default 0), `exclusive` (resource names no two nodes hold at once) and for an approval `question` and `artifacts` (`{node, artifact}`).

- GIVEN a node `repo` that is not a git repository with a state root WHEN validated THEN it exits 2

### ORC-B1 Refuse before spend

WHEN an orchestration file is validated or started THE engine SHALL check with no model call the schema, an acyclic graph, every workflow's registration, every `after`, `from` and `targets_from` reference, the 50-run limit, the `mode` and a `run --check` of every node whose inputs are all literals or params, exit 2 at the first miss naming the node, and create nothing on `start`.

- GIVEN a cycle `a → b → a` WHEN validated THEN it exits 2 naming the cycle
- GIVEN a `from` artifact key the upstream workflow does not declare in `produces` WHEN validated THEN it exits 2
- GIVEN a node whose `run --check` says `needs` WHEN validated THEN it exits 2 with the questions, so the skill asks the person
- GIVEN 4 maps of 20 targets WHEN validated THEN it exits 2, over 50 runs

### ORC-B2 Plan before approval

WHEN `orchestrate plan <file> [--format md|mermaid|json]` runs on a valid file THE engine SHALL print, writing and spending nothing, the engine-drawn graph (never by model), phases, a node table with workflow, inputs, dependencies and policy, the run count (a `targets_from` map shown as "up to `max_items`"), the projected cost range from `stats --projection` ([CST-B15](34-central-run-stats.spec.md)) or "not known", a thin projection shown as such, the cap, and a warning when the run count exceeds 10 or the projected high end exceeds the cap.

- GIVEN 12 runs planned WHEN `orchestrate plan` runs THEN it warns about the run count

### ORC-B21 Node states

WHEN a node's state is read THE engine SHALL derive it from its thread's status every time, never from the event log: `waiting` (an `after` node not finished), `ready` (waiting for a slot or an `exclusive` resource), `running`, `paused` (exit 3, attention), `approval` (attention), `finished` (exit 0; for a map every item), `failed` (exit 4 or 5 after any re-opens, with the run's reason), `skipped`, `cancelled` (removed by an edit before it started, or by a stop) and `lost` (the thread `unfinished` with no live lock and no exit seen), a map's state being the worst of its items' (`paused` before `failed` before `running`) with counts per state.

- GIVEN a map with one paused and one failed item WHEN read THEN the map is `paused`

### ORC-B22 Event log

WHEN a transition happens THE supervisor SHALL append one JSON line beside the file with `seq`, `at`, `kind`, `node`, `item` and metadata only, of kind `planned`, `started` (with thread id), `state` (from, to, reason), `expanded`, `reopened`, `answered` (node, decision word, caller), `edited` (diff summary), `cost_cap`, `stopping`, `supervisor_started`, `supervisor_lost` or `finished` (outcome), and when the write fails note it once on standard error and go on scheduling, status falling back to run status (contract C2).

- GIVEN an event log write that fails WHEN the next node is due THEN it starts and status reads from run status

### ORC-B3 Scheduling

WHEN a slot is free and nodes are ready THE supervisor SHALL start them in file order, never more than `k` runs at once across all nodes and map items, never two nodes sharing an `exclusive` name together, record `started` before the child process starts, take no slot for an approval node, run each child in its own process group so the supervisor's exit or kill never ends it, and mark a node whose run is refused at start `failed` with reason `refused` and the run's message.

- GIVEN `k = 3` and five ready nodes WHEN scheduled THEN three run and two stay `ready`

### ORC-B4 Data between runs

WHEN node `plan` has `inputs: {spec: {from: design, artifact: spec_path}}` and `design` finishes THE supervisor SHALL read `spec_path` through `facts` of `design`'s thread ([CLI-B5](17-engine-cli.spec.md)) and pass it as a declared input of the new run, and fail `plan` with reason `input_missing` before any spend when the key is missing or the upstream run is deleted or unreadable.

- GIVEN `design` finished without `spec_path` WHEN `plan` is due THEN it fails `input_missing` and nothing is spent

### ORC-B5 Pauses do not stop the graph

WHEN one of three running nodes pauses THE supervisor SHALL make its node `paused` and attention, hold its dependants, and keep the other runs and every node not depending on it starting and finishing.

- GIVEN one paused node of three WHEN the supervisor runs THEN the other two go on

### ORC-B6 Answering a node

WHEN `orchestrate answer <id> <node> [--item i] --decision … [--feedback …] [--ruling] [--set k=v] [--relayed]` runs on a paused node THE engine SHALL run `resume` of that node's thread with that decision, passing feedback, rulings and settings through ([RRN](81-reruns-and-feedback.spec.md)), append an `answered` event carrying the answer's caller ([PRV](85-caller-provenance.spec.md)) and make the node `running`, refuse with exit 2 `answer_not_by_person` an answer whose decider is not a person (an agent's own answer, a relay without a person turn, an `unknown` caller), and refuse with exit 2 a decision the run's gate does not offer ([HUM](07-gate-and-human.spec.md)).

- GIVEN an agent's own answer WHEN `orchestrate answer` runs THEN it exits 2 `answer_not_by_person`

### ORC-B7 Approval nodes

WHEN the nodes before an approval node finish THE supervisor SHALL show its question and listed artifacts and wait, release its dependants on `--decision proceed`, end the orchestration `stopped` on `--decision stop`, and accept no other decision.

- GIVEN an approval node WHEN answered `retry` THEN it is refused

### ORC-B23 Failure policy

WHEN a node fails THE supervisor SHALL first re-open a run that ended with exit 5 on an infra cause ([BUD](08-budgets-and-failures.spec.md)) with `resume` up to `reopen_infra` times, never re-opening one that spent a quality budget, stopped at a gate or hit a cost cap, then apply `on_failure`: `skip_dependants` skips every direct and indirect dependant while independent nodes go on; `continue` releases dependants as if it finished, a missing `from` input failing a dependant with `input_missing`; `halt` starts no new node while running nodes go to their own end, the outcome `halted`; and `ask` makes it attention while dependants wait for the person to pick skip, continue or halt.

- GIVEN `on_failure: ask` WHEN a node fails THEN its dependants wait for the person's pick

### ORC-B8 Failures by policy

WHEN node `a` fails, with `b` after it and `c` independent THE supervisor SHALL apply ORC-B23 with these outcomes.

- GIVEN `skip_dependants` WHEN `a` fails THEN `b` is skipped, `c` runs, and the outcome is `finished_with_failures`
- GIVEN `continue` WHEN `a` fails THEN `b` runs or fails `input_missing`, `c` runs, and the outcome is `finished_with_failures`
- GIVEN `halt` WHEN `a` fails THEN `b` never starts, `c` runs only if already running, and the outcome is `halted`
- GIVEN `ask` WHEN `a` fails THEN `b` waits for the person, `c` runs, and the outcome is as picked

### ORC-B9 Infra re-open

WHEN a run with `reopen_infra: 1` exits 5 with an infra cause THE supervisor SHALL resume the thread once, record `reopened`, and apply `on_failure` only if the re-opened run fails again, never re-opening a run that exited 5 with `cost_cap` or a spent retry budget.

- GIVEN a run that exits 5 on `cost_cap` WHEN seen THEN it is not re-opened

### ORC-B10 Stop

WHEN `orchestrate stop <id> [--node n] [--now]` runs THE engine SHALL start no node again, make unstarted nodes `cancelled`, drain running runs with `stop` ([RCT](32-run-control.spec.md)) so their threads stay resumable, leave paused runs paused, end the outcome `stopped`, stop each run's open session at once with `--now`, and apply the same to one node with `--node`.

- GIVEN `orchestrate stop` WHEN run THEN running threads end `unfinished` and resumable

### ORC-B11 Cost cap

WHEN the summed cost of the node runs (reported where present, else estimated) reaches `cost_cap_usd` THE supervisor SHALL start no node again, let running runs go on to their own end, write a `cost_cap` event and end the outcome `cost_cap`, an edit that raises the cap with `orchestrate resume` continuing it, and each node's own `--run-cost-cap` still applying to its run.

- GIVEN `cost_cap_usd: 40` reached WHEN the next node is due THEN it does not start and the outcome is `cost_cap`

### ORC-B12 Supervisor loss and resume

WHEN `orchestrate resume <id>` runs after its supervisor was killed while runs were live THE engine SHALL take the lock, read each node's state from its thread status (re-attaching live runs through the lock probe, restarting no finished one), append `supervisor_started` and go on, and `orchestrate wait` on an orchestration whose supervisor lock is free and whose outcome is not written SHALL exit 5 with `supervisor_lost`.

- GIVEN a killed supervisor and no resume WHEN `orchestrate wait` runs THEN it exits 5 with `supervisor_lost`

### ORC-B13 Re-run skips by identity

WHEN the same file is started again under the same `orchestration_id` with `orchestrate resume` THE engine SHALL never start afresh a node whose thread exists, taking it in its current state, so reordering nodes changes nothing that ran.

- GIVEN nodes reordered in the file WHEN resumed THEN no finished node runs again

### ORC-B17 The supervisor's mark

WHEN the supervisor starts a node's run THE supervisor SHALL pass `--parent <orchestration_id>/<node>[/<item>]` (shown as `parent` in the status document, `run_started`, the ledger and the stats row, with `origin` `orchestration`) and a random per-orchestration token in `TEMPERGRAPH_SUPERVISOR_TOKEN` whose SHA-256 it keeps in the orchestration's state file, so the run records caller `orchestrator` (`attested`) with supervision cost `measured_zero` ([PRV](85-caller-provenance.spec.md), [SCO](87-supervision-cost.spec.md)), the token never being on argv, in a record or in a step session's environment ([EXI](10-executor-interface.spec.md)).

- GIVEN a node's run WHEN its step session's environment is read THEN it holds no supervisor token

### ORC-B14 Edits while running

WHEN `orchestrate edit <id> <patch file>` adds a node after a finished one, cancels a `waiting` node, or changes `k` or the cap THE engine SHALL apply it at the next scheduling pass and record an `edited` event, and refuse with exit 2, changing nothing, an edit that changes or removes a started node or creates a cycle.

- GIVEN an edit that removes a started node WHEN applied THEN it exits 2 and nothing changes

### ORC-B15 Dynamic map

WHEN the upstream node of a map with `targets_from` and `max_items: 8` finishes THE supervisor SHALL plan one run per string of the artifact with an `expanded` event, and fail the map with reason `expansion_failed`, starting no item, when it holds more than `max_items` strings or is not an array.

- GIVEN 5 strings WHEN expanded THEN 5 runs are planned
- GIVEN 9 strings or a non-array WHEN expanded THEN the map fails `expansion_failed`

### ORC-B24 Status, wait and other verbs

WHEN `orchestrate status [id] [--json]`, `orchestrate wait <id> [--timeout s] [--settle s]`, `orchestrate start`, `orchestrate validate`, `orchestrate rerun <id> <node> [--item i] --from <unit>`, `orchestrate list` or `orchestrate report <id>` runs THE engine SHALL print the status document of ORC-B25 writing nothing; block until attention changes or the orchestration ends, exiting 0 when every node finished, 3 on attention, 4 when stopped by a person, 5 on `finished_with_failures`, `halted`, `cost_cap` or `supervisor_lost`, and 2 for an unknown id ([CON-B12](01-contracts.spec.md)); validate, write the folder and start the supervisor detached, printing the id and exiting 0 once it runs, or 2 with nothing created; validate only; rerun the node's thread from a unit and point the node at the new thread ([RRN](81-reruns-and-feedback.spec.md)); list orchestrations under the state root with outcome and cost; or report cost per node and phase, time, pauses with who answered (caller kind and decider), failures with causes, and supervision (touches per node, the orchestrating sessions' cost and its share of the runs' cost, [SUP](86-supervision-metrics.spec.md)).

- GIVEN an unknown id WHEN `orchestrate wait` runs THEN it exits 2

### ORC-B25 Status document

WHEN the orchestration status document (schema version 1) is built THE engine SHALL read the file, the event log and each node's run status, writing nothing, and give `schema_version`, `orchestration_id`, `name`, `description`, `state` (`running`, `attention`, `finished`, `finished_with_failures`, `halted`, `stopped`, `cost_cap`, `supervisor_lost`), `supervisor` (`alive` from the lock probe, `started_at`, `restarts`), `k`, `in_flight`, `counts` per node state, `cost` (`reported`, `estimated`, `incomplete`, `cap`, `projected`), `phases` in first-use order with their node ids, `nodes` (`id`, `kind`, `label`, `phase`, `after`, `state`, `reason`, `workflow`, `thread_id`, `alias`, `repo`, `started_at`, `ended_at`, `exit`, `cost`, the run's `attempt_in_flight` and `pending_gates` with each decision's `orchestrate answer` command, and for a map `items` with state and thread id), `attention` (`{node, item, kind, since}`, oldest first), the orchestration's `schedule` when a schedule started it, and `events_path`, readers ignoring unknown keys ([CON-B1](01-contracts.spec.md)).

- GIVEN a paused node WHEN the document is built THEN its `pending_gates` carry the exact `orchestrate answer` commands

### ORC-B16 Wait coalesces

WHEN two runs pause 20 s apart while `orchestrate wait --settle 30` waits THE engine SHALL return once with exit 3 and both in `attention`, and never return for a step verdict, a cost update or a node that started or finished while attention is unchanged, except when the whole orchestration ends.

- GIVEN two pauses 20 s apart WHEN waiting with a 30 s settle THEN it returns once

### ORC-B26 Attention and hooks across the state root

WHEN an orchestration node needs a person THE engine SHALL list a paused node's run in `tempergraph attention` with its `parent` and an approval node or `ask` failure as an orchestration item ([ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)), and fire the lifecycle hook events `orchestration_attention` and `orchestration_finished` ([HOK](24-lifecycle-hooks.spec.md)) so a notifier can reach a person when no conversation is open.

- GIVEN an approval node waiting WHEN `tempergraph attention` runs THEN it lists the orchestration item

## Acceptance criteria

- ORC-AC1 (ORC-B1, ORC-B19, ORC-B20): Every scenario of ORC-B1 exits 2 and leaves the state root unchanged, by a hash test
- ORC-AC2 (ORC-B3, ORC-B5, ORC-B8, ORC-B9, ORC-B23, ORC-B21): With scripted runs, a 6-node graph with one pause, one infra failure and one quality failure reaches the outcome each ORC-B8 scenario states, with `k` never exceeded and no `exclusive` pair overlapping
- ORC-AC3 (ORC-B12, ORC-B13, ORC-B18): Killing the supervisor at each event kind and running `orchestrate resume` never starts a node's thread twice and ends in the same outcome as an uninterrupted run
- ORC-AC4 (ORC-B2, ORC-B24, ORC-B25): The supervisor and every read-only verb start no model session, by a process audit in tests; status and wait write nothing
- ORC-AC5 (ORC-B16): `orchestrate wait` returns once for pauses arriving within the settle window and never for a change that leaves attention unchanged
- ORC-AC6 (ORC-B3): `batch <workflow> <targets…> -k N` and the equivalent one-node map orchestration start the same threads and produce the same report
- ORC-AC7 (ORC-B22, ORC-B17): No event log line and no status field carries run text beyond labels, ids, decision words and scrubbed reasons, and the supervisor token appears in no record
- ORC-AC8 (ORC-B4, ORC-B6, ORC-B7, ORC-B10, ORC-B11, ORC-B14, ORC-B15, ORC-B26): Fixtures cover data between runs, answers by and not by a person, approval nodes, stop, the cost cap, edits, dynamic maps and attention items

## Open questions

- Should an orchestration be able to span machines (a shared state store), or stay local with per-machine stats rolled up later? Until answered: local. Owner: owner, with the observability design.
- Should integration (merging node branches into one pull request) become an engine node kind rather than a workflow node? Owner: owner ([R-006](../research/R-006-planned-work-coverage.rsrch.md)).
