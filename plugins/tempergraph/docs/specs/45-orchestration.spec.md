---
title: Orchestration of runs
type: component
status: review
prefix: ORC
adrs: [0035, 0036, 0037, 0038, 0039]
---

# Orchestration of runs

## 1. Overview

An **orchestration** is a graph of tempergraph runs: which workflow runs on what, in what order, how many at once, what a failure does to the runs after it, and where a person must sign off between waves. It is the run-level counterpart of a workflow: a workflow is a graph of steps inside one run, an orchestration is a graph of runs. Like a workflow it is **data**, validated before any spend and executed by the engine, not by a conversation ([ADR-0035](../adr/0035-orchestration-is-data-run-by-a-model-free-supervisor.adr.md)).

A model-free engine process, the **supervisor**, starts each run through the engine's own `run` verb, watches it through the status document, keeps independent runs moving while one waits for a person, and stops starting new runs when a cap or a failure policy says so. It never calls a model and never answers a gate (contract C16). The [orchestrator skill](46-orchestrator-skill.spec.md) writes the file with the person, starts it and walks the person through each pause; the `tempergraph-monitor` plugin shows it read-only.

The model is borrowed from Claude Code's dynamic workflows (labels, phases, barriers, per-item pipelines, live drill-down, size warning, saved templates) and departs from it where tempergraph runs differ: runs pause for people, cost real money per rerun and leave branches, so identity is by node id, not by position, and nothing is replayed ([R-035](../research/R-035-dynamic-workflows-as-orchestration-model.rsrch.md)). The existing `batch` verb becomes a one-node orchestration ([ADR-0038](../adr/0038-batch-is-a-one-node-orchestration.adr.md)).

## 2. Contract

### 2.1 Concepts

| Concept | Definition |
|---|---|
| Orchestration | One orchestration file plus its event log, under `<state root>/orchestrations/<orchestration_id>/`. |
| `orchestration_id` | `<name>-<yyyymmdd>-<4 hex>`, fixed at start; the name is a slug from the file. |
| Node | One unit of the graph: a `run`, a `map` (one run per target) or an `approval` (a pause owned by the orchestration). |
| Edge | `after: [node ids]`: the node becomes ready when every listed node has `finished`. |
| Phase | A display group of nodes (`phase: "<title>"`); it has no effect on scheduling. |
| Supervisor | A detached engine process that executes one orchestration; at most one per orchestration (an OS file lock). |
| Node thread | The run a node starts: `thread_id = <workflow>/o-<orchestration_id>-<node>[-<item>]`, so a re-run finds it by name. |
| Attention | A node state a person must act on: a paused run, an approval node, a failed node whose policy asks, or a lost supervisor. |

### 2.2 Orchestration file (schema version 1)

JSON, named `<name>.orch.json` when saved as a template. Every value is a constant, a checked number or a scrubbed string; nothing in the file reaches a launch as typed text ([SEC](14-security.spec.md)).

| Field | Kind | Meaning |
|---|---|---|
| `schema_version` | int | `1` |
| `name`, `description` | slug, text ≤ 200 | Shown in status, monitor and reports. |
| `params` | list of `{name, meaning, example}` | Declared arguments of a template; `{param}` fields in `inputs` and `targets` take them (template grammar of [CON §2.2](01-contracts.spec.md)). |
| `k` | int 1–16, default 3 | Runs in flight at once across the orchestration. |
| `cost_cap_usd` | float, optional | Aggregate cap over every node's run cost, children included. |
| `mode` | `attended` | `unattended` is reserved and refused until a delegation policy exists ([ADR-0039](../adr/0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md)). |
| `nodes` | list of `NodeSpec` | At least one; at most 50 runs after expansion. |

| `NodeSpec` field | Kind | Meaning |
|---|---|---|
| `id` | slug | Unique in the file; never reused for a different node. |
| `kind` | `run` \| `map` \| `approval` | |
| `label`, `phase` | text ≤ 40 | Display only. |
| `after` | list of node ids | Dependencies; the graph must be acyclic. |
| `workflow` | registered workflow name | For `run` and `map`. |
| `repo` | absolute path, optional | Another local git repository whose state root the run uses; default the orchestration's. |
| `inputs` | map name → literal \| `{param}` \| `{from: <node>, artifact: <key>}` | The run's declared inputs; a `from` value is read from the finished upstream run's artifacts by key through `facts`. |
| `options` | subset of run options | Executor, model and timeout overrides, `--approve`, `--run-cost-cap`, workspace mode. Options that hand gates to an agent (`--as-agent`) are refused. |
| `targets` | list of strings, for `map` | One run per target. |
| `targets_from` | `{node, artifact}`, for `map` | A JSON file artifact of an upstream run holding an array of strings; expanded when that node finishes. |
| `max_items` | int 1–50, for `map` | Required with `targets_from`; more items fail the expansion. |
| `k` | int, for `map`, optional | Per-map limit, within the orchestration's `k`. |
| `on_failure` | `skip_dependants` (default) \| `continue` \| `halt` \| `ask` | What a failed run does to the rest (§2.5). |
| `reopen_infra` | int 0–3, default 0 | Re-opens of a run that ended on an infra cause, given in advance. |
| `exclusive` | list of resource names | No two nodes sharing a name run at the same time (for example a version field or an id counter). |
| `question`, `artifacts` | text, list of `{node, artifact}`, for `approval` | What the person signs off and what to look at. |

### 2.3 Node states

| State | Meaning | Comes from |
|---|---|---|
| `waiting` | An `after` node is not yet finished | Plan |
| `ready` | All dependencies finished; waiting for a slot or an `exclusive` resource | Supervisor |
| `running` | The node thread is `running` | Run status |
| `paused` | The node thread is `paused` (exit 3); attention | Run status |
| `approval` | An approval node is waiting for a person; attention | Supervisor |
| `finished` | Exit 0; for a map, every item finished | Run status |
| `failed` | Exit 4 or 5 after any re-opens; carries the run's reason | Run status |
| `skipped` | A dependency failed under `skip_dependants`, or was cancelled | Supervisor |
| `cancelled` | Removed by an edit before it started, or by a stop | Edit, stop |
| `lost` | The thread is `unfinished` with no live lock and no exit was seen | Lock probe |

A node's state is derived from its thread's status every time; the event log records transitions but never overrides the run's own status ([ADR-0036](../adr/0036-orchestration-state-is-a-file-and-an-event-log.adr.md)). A map node's state is the worst of its items' (`paused` before `failed` before `running`), with counts per state.

### 2.4 Event log

Append-only JSON lines beside the file, one per transition, each with `seq`, `at`, `kind`, `node`, `item` and metadata only (no run text):

`planned`, `started` (with thread id), `state` (from, to, reason), `expanded` (map items), `reopened`, `answered` (node, decision word, by `person`), `edited` (diff summary), `cost_cap`, `stopping`, `supervisor_started`, `supervisor_lost`, `finished` (outcome).

### 2.5 Failure policy

| `on_failure` | Effect of a `failed` node |
|---|---|
| `skip_dependants` | Every node that depends on it, directly or not, becomes `skipped`; independent nodes go on |
| `continue` | Dependants are released as if it finished; a `from` input it should have given makes the dependant `failed` with reason `input_missing` |
| `halt` | No new node starts; running nodes go on to their own end; the outcome is `halted` |
| `ask` | The node is `failed` and attention; dependants wait until the person picks skip, continue or halt for it |

Before a policy applies, a run that ended with exit 5 on an infra cause ([BUD §2.2](08-budgets-and-failures.spec.md)) is re-opened with `resume` up to `reopen_infra` times. A run that spent a quality budget, stopped at a gate or hit a cost cap is never re-opened by the supervisor.

### 2.6 Verbs

| Verb | Does | Writes | Spends |
|---|---|---|---|
| `orchestrate validate <file> [--arg k=v…]` | Schema, graph, and `run --check` of every node whose inputs are known | no | no |
| `orchestrate plan <file> [--format md\|mermaid\|json]` | Validation plus the drawn graph, phases, node table, projected cost and warnings | no | no |
| `orchestrate start <file> [--arg k=v…]` | Validate, write the orchestration folder, start the supervisor detached; prints the id | yes | yes |
| `orchestrate status [id] [--json]` | Orchestration status document (§2.7) | no | no |
| `orchestrate wait <id> [--timeout s] [--settle s]` | Block until attention changes or the orchestration ends | no | no |
| `orchestrate answer <id> <node> [--item i] --decision …` | Resume that node's paused run, sign an approval, or pick the policy of an `ask` failure | yes | yes |
| `orchestrate edit <id> <patch file>` | Add nodes, cancel unstarted nodes, change `k` or the cap | yes | no |
| `orchestrate stop <id> [--node n] [--now]` | Stop starting nodes; drain or stop running runs (ORC-B10) | yes | no |
| `orchestrate resume <id>` | Start a supervisor for an orchestration whose supervisor is gone | yes | yes |
| `orchestrate list` | Orchestrations under the state root with outcome and cost | no | no |
| `orchestrate report <id>` | Cost per node and phase, time, pauses and who answered, failures with causes | no | no |

`orchestrate wait` exits 0 (all nodes finished), 3 (attention: the document lists what), 4 (stopped by a person), 5 (ended `finished_with_failures`, `halted`, `cost_cap` or `supervisor_lost`), 2 (unknown id). `start` exits 0 once the supervisor runs, 2 on any refusal with nothing created. The meanings are those of [CON §2.9](01-contracts.spec.md).

### 2.7 Orchestration status document (schema version 1)

The one document the skill and the monitor read about an orchestration. Read-only to produce: it opens the file, the event log and each node's run status, and writes nothing.

| Field | Meaning |
|---|---|
| `schema_version`, `orchestration_id`, `name`, `description` | |
| `state` | `running`, `attention`, `finished`, `finished_with_failures`, `halted`, `stopped`, `cost_cap`, `supervisor_lost` |
| `supervisor` | `alive` from the lock probe, `started_at`, `restarts` |
| `k`, `in_flight` | Limit and runs in flight |
| `counts` | Nodes and map items per node state |
| `cost` | `reported`, `estimated`, `incomplete` summed over node runs, plus `cap` and `projected` |
| `phases` | Titles in first-use order, each with its node ids |
| `nodes` | Per node: `id`, `kind`, `label`, `phase`, `after`, `state`, `reason`, `workflow`, `thread_id`, `alias`, `repo`, `started_at`, `ended_at`, `exit`, `cost`, `attempt_in_flight` (copied from the run's status), `pending_gates` (copied, with each decision's `orchestrate answer` command), and for a map `items` with per-item state and thread id |
| `attention` | Ordered list of `{node, item, kind, since}`, oldest first |
| `events_path` | Local path of the event log |

Readers follow [CON §2.10](01-contracts.spec.md): unknown keys are ignored, a missing key is "not recorded".

### 2.8 Needs from the engine

What the supervisor needs from the rest of the engine. Rows marked **requested** are requirements on the observability and run-data design being written in parallel; the supervisor works without them through the fallback named.

| # | Need | Owner | Fallback until it exists |
|---|---|---|---|
| N1 | Run option `--parent <orchestration_id>/<node>[/<item>]`, stored with the run options and shown as `parent` in the status document, the run log's first line, the ledger and the `stats` row; `origin` value `orchestration` | [DUR §2.2](09-durability-and-resume.spec.md) (added), run log and stats: **requested** | Thread id prefix `o-<id>-` |
| N2 | A per-run lifecycle event stream (append-only, ordered, versioned): started, attempt started, gate verdict, paused, resumed, finished, failed, cost so far | Observability: **requested** | One `wait` per running child ([DUR-B5](09-durability-and-resume.spec.md)) |
| N3 | `stop <selector> [--now]` for one run: drain (no new attempt, thread ends `unfinished`, exit 4) or now (tree-kill the open session; resume treats it as a cut-off attempt, [DUR-B2](09-durability-and-resume.spec.md)) | [CLI §2](17-engine-cli.spec.md) (added) | None: `orchestrate stop` only stops starting nodes |
| N4 | `facts --json` lists each pending gate's payload: kind, decisions, artifacts, the resume argv; and artifacts by key with resolved paths | [CLI-B5](17-engine-cli.spec.md) | — (already designed) |
| N5 | A run started by the supervisor runs in its own process group; the supervisor's exit or kill never ends it | This spec | — |
| N6 | Orchestration hook events `orchestration_attention` and `orchestration_finished`, so a notifier can reach a person when no conversation is open | [CLI §2.2](17-engine-cli.spec.md) (added) | The skill's `wait` |
| N7 | Projected cost per workflow from past runs: median and 90th percentile of estimated cost per run, with the sample size | [OBS §2.4](15-observability-and-cost.spec.md) `stats`: **requested** | `projected` not recorded |
| N8 | The monitor's drill-down from an orchestration node into the run, its steps, attempts and the live session (open tool, shell command) | Monitor and observability: **requested** | Node row only |

## 3. Behaviours

**ORC-B1 Refuse before spend.** Given an orchestration file, when it is validated or started, then the schema, an acyclic graph, every workflow's registration, every `after`, `from` and `targets_from` reference, the 50-run limit, the `mode` and a `run --check` of every node whose inputs are all literals or params are checked with no model call; the first miss exits 2 naming the node, and `start` creates nothing.

| Fault | Result |
|---|---|
| Cycle `a → b → a` | exit 2, the cycle named |
| `from` an artifact key the upstream workflow does not declare in `produces` | exit 2 |
| A node's `run --check` says `needs` | exit 2 with the questions, so the skill asks the person |
| `mode: unattended` | exit 2, reserved |
| 4 maps of 20 targets | exit 2, over 50 runs |

**ORC-B2 Plan before approval.** Given a valid file, when `orchestrate plan` runs, then it prints the graph (engine-drawn, never by model), phases, a node table with workflow, inputs, dependencies and policy, the run count (a `targets_from` map shown as "up to `max_items`"), the projected cost range from N7 or "not known", the cap, and a warning when the run count exceeds 10 or the projected high end exceeds the cap.

**ORC-B3 Scheduling.** Given ready nodes, when a slot is free, then the supervisor starts them in file order, never more than `k` runs at once across all nodes and map items, never two nodes sharing an `exclusive` name together, and records `started` before the child process starts. An approval node takes no slot.

**ORC-B4 Data between runs.** Given node `plan` with `inputs: {spec: {from: design, artifact: spec_path}}`, when `design` finishes, then the supervisor reads `spec_path` through `facts` of `design`'s thread and passes it as a declared input of the new run; if the key is missing, `plan` fails with reason `input_missing` before any spend.

**ORC-B5 Pauses do not stop the graph.** Given three running nodes, when one run pauses, then its node becomes `paused` and attention, its dependants wait, and the other two runs and every node not depending on it go on starting and finishing.

**ORC-B6 Answering a node.** Given a paused node, when `orchestrate answer <id> <node> --decision retry --feedback …` runs, then the engine's `resume` of that node's thread is run with that decision, an `answered` event with `by: person` is appended, and the node becomes `running`. A decision the run's gate does not offer is refused with exit 2, as `resume` refuses it ([HUM §2.2](07-gate-and-human.spec.md)).

**ORC-B7 Approval nodes.** Given an approval node after a map, when the map finishes, then the node shows its question and the listed artifacts and waits; `--decision proceed` releases its dependants and `--decision stop` ends the orchestration `stopped`; no other decision is accepted.

**ORC-B8 Failures by policy.** Given node `b` after `a` and node `c` independent, when `a` fails, then the rows hold:

| `a.on_failure` | `b` | `c` | Outcome when the rest ends |
|---|---|---|---|
| `skip_dependants` | skipped | runs | `finished_with_failures` |
| `continue` | runs (or fails `input_missing`) | runs | `finished_with_failures` |
| `halt` | never starts | runs only if already running | `halted` |
| `ask` | waits for the person | runs | as picked |

**ORC-B9 Infra re-open.** Given `reopen_infra: 1` and a run that exits 5 with an infra cause, when the supervisor sees it, then it resumes the thread once, records `reopened`, and applies `on_failure` only if the re-opened run fails again. A run that exits 5 with reason `cost_cap` or a spent retry budget is not re-opened.

**ORC-B10 Stop.** Given a running orchestration, when `orchestrate stop` runs, then no node starts again, unstarted nodes become `cancelled`, running runs are drained with `stop` (N3) and their threads stay resumable, paused runs stay paused, and the outcome is `stopped`; with `--now` each run's open session is stopped at once. `--node` applies the same to one node.

**ORC-B11 Cost cap.** Given `cost_cap_usd: 40`, when the summed cost of the node runs (reported where present, else estimated) reaches 40, then no node starts again, running runs go on to their own end, a `cost_cap` event is written and the outcome is `cost_cap`; an edit that raises the cap and `orchestrate resume` continue it. A node's own `--run-cost-cap` still applies to its run.

**ORC-B12 Supervisor loss and resume.** Given a supervisor killed while two runs are live, when `orchestrate resume <id>` runs, then the new supervisor takes the lock, reads each node's state from its thread status (live runs are re-attached through the lock probe, finished ones are not restarted), appends `supervisor_started`, and goes on. `orchestrate wait` on an orchestration whose supervisor lock is free and whose outcome is not written exits 5 with `supervisor_lost`.

**ORC-B13 Re-run skips by identity.** Given a file started once, when the same file is started again under the same `orchestration_id` with `orchestrate resume`, then a node whose thread exists is never started afresh; it is taken in its current state. Reordering nodes in the file changes nothing that ran.

**ORC-B14 Edits while running.** Given a running orchestration, when an edit adds a node after a finished one, cancels a `waiting` node, or lowers `k`, then it applies at the next scheduling pass and an `edited` event records it; an edit that changes a node that has started, removes a started node, or creates a cycle is refused with exit 2 and nothing changes.

**ORC-B15 Dynamic map.** Given `targets_from: {node: triage, artifact: items}` and `max_items: 8`, when `triage` finishes and its artifact holds 5 strings, then 5 runs are planned (`expanded` event) and scheduled; with 9 strings or a non-array the map node fails with reason `expansion_failed` and no item starts.

**ORC-B16 Wait coalesces.** Given two runs that pause 20 s apart, when `orchestrate wait --settle 30` is waiting, then it returns once, exit 3, with both in `attention`; it never returns for a step verdict, a cost update or a node that started or finished while attention is unchanged, except when the whole orchestration ends.

## 4. Error conditions

| Condition | Result |
|---|---|
| A second supervisor for the same orchestration | Refused, exit 2; the lock holder is named |
| A node's run is refused at start (exit 2) though validation passed | Node `failed` with reason `refused` and the run's message; policy applies |
| Upstream run deleted or unreadable | Dependants `failed` with reason `input_missing` |
| `repo` is not a git repository with an engine state root | Exit 2 at validation |
| Event log write fails | Recorded once on stderr; scheduling goes on; status falls back to run status (contract C2) |

## 5. Design notes

- **Truth from runs.** The file holds intent; each run's status holds truth; the event log holds history. A crash of any one never makes another wrong ([ADR-0036](../adr/0036-orchestration-state-is-a-file-and-an-event-log.adr.md)).
- **No LangGraph graph for the supervisor.** Its state is a set of independent child processes with their own checkpoints and many pauses at once; one interrupt per gate and one graph per process (C6, C11) fit runs, not a supervisor of runs.
- **One wake per batch of attention.** `wait` returns only when a person is needed, after a settle window, so the skill's session is woken as rarely as the graph allows ([ADR-0037](../adr/0037-attention-batched-waking-of-the-orchestrating-session.adr.md)).
- **Shared resources.** `exclusive` names stop concurrent runs from colliding on counters and version fields (R-035 B3). Engine-managed claims (a reserved slice of an id range per run) and deterministic integration of branches with a judged conflict step are deferred; an integration step is a workflow node today ([R-006](../research/R-006-planned-work-coverage.rsrch.md) open question).
- **Several repositories, one machine.** A node may run in another local repository; its run uses that repository's state root, and the orchestration's folder stays in the home state root. Several machines, CI hosts and a hosted runner are out of scope for the first release.
- **Assumptions** (owner unavailable): K defaults to 3 as for batches; 50 runs per orchestration matches the batch limit; the settle window defaults to 30 s; an orchestration runs on one machine; templates are saved by the skill under `tempergraph/orchestrations/` in the repository, a path the owner may change.

## 6. Acceptance criteria

- [ ] ORC-AC-1 Every row of ORC-B1's table exits 2 and leaves the state root unchanged (hash test).
- [ ] ORC-AC-2 With scripted runs, a 6-node graph with one pause, one infra failure and one quality failure reaches the outcome each ORC-B8 row states, with `k` never exceeded and no `exclusive` pair overlapping.
- [ ] ORC-AC-3 Killing the supervisor at each event kind and running `orchestrate resume` never starts a node's thread twice and ends in the same outcome as an uninterrupted run.
- [ ] ORC-AC-4 The supervisor and every read-only verb start no model session (process audit in tests); status and wait write nothing.
- [ ] ORC-AC-5 `orchestrate wait` returns once for pauses arriving within the settle window and never for a change that leaves attention unchanged.
- [ ] ORC-AC-6 `batch <workflow> <targets…> -k N` and the equivalent one-node map orchestration start the same threads and produce the same report.
- [ ] ORC-AC-7 No event log line and no status field carries run text beyond labels, ids, decision words and scrubbed reasons.

## Open questions

| Question | Owner |
|---|---|
| Should an orchestration be able to span machines (a shared state store), or stay local with per-machine stats rolled up later? Local is assumed. | Owner, with the observability design |
| Should integration (merging node branches into one pull request) become an engine node kind rather than a workflow node? | Owner ([R-006](../research/R-006-planned-work-coverage.rsrch.md)) |

## References

