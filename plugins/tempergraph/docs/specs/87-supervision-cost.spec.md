---
title: Supervision cost
type: component
status: review
prefix: SCO
adrs: [0087, 0088]
---

# Supervision cost

## 1. Overview

What the sessions that babysit runs spend: the Claude session that starts a run and waits on it, reads its status and logs, diagnoses a failure, shows a pause to a person and resumes; the orchestrator skill's session; their helper subagents; an application that drives the engine. This spend happens in a host the engine does not run, so the engine cannot meter it the way it meters its own sessions ([OBS](15-observability-and-cost.spec.md)); it adds to run cost, most of it context re-read after a wake, and is lost unless it is recorded per run ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) B1, B2, B4). This spec owns the supervision journal that hosts and callers write, the sources of usage per host, the attribution of a supervising session's spend to threads and orchestrations, the closing of a thread's supervision cost, and the `supervision` verbs. Read-only verbs still write nothing (OVR-B15): the journal is written by the host's hooks and by one writing verb ([ADR-0087](../adr/0087-a-supervision-journal-written-by-the-host-not-by-read-only-verbs.adr.md)). Unmeasured is never zero. Supervision metrics ([SUP](86-supervision-metrics.spec.md)), reports, sinks ([CST](34-central-run-stats.spec.md)) and the orchestrator skill's share ([OSK](46-orchestrator-skill.spec.md)) depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

This spec owns the **supervision journal** that hosts and callers write, the **sources** of usage per host, the **attribution** of a supervising session's spend to threads and orchestrations, the closing of a thread's supervision cost, and the `supervision` verbs. The engine's read-only verbs still write nothing (contract C13): the journal is written by the host's hooks and by one writing verb ([ADR-0087](../adr/0087-a-supervision-journal-written-by-the-host-not-by-read-only-verbs.adr.md)). Unmeasured is never zero.

## 2. Contract

### 2.1 Supervising session

A **supervising session** is a host session (a Claude Code session, its subagents, an Agent SDK or Messages API application session, an Antigravity session) that made at least one engine call about a thread or an orchestration. Its **window** runs from its first such call to its end. Only spend inside the window that §2.4 attributes is supervision; the rest of the session's work is `other` and is never put on a run.

The engine's own step and judge sessions are never supervising sessions. Every session an executor starts carries `TEMPERGRAPH_SESSION_KEY` in its environment ([EXI §2.3](10-executor-interface.spec.md)); the plugin's hooks do nothing when it is set, so a step session that loads the tempergraph plugin and calls `self-check` is not counted twice.

### 2.2 Supervision journal

One JSON-lines file per host session at `~/.tempergraph/supervision/<host>/<host_session>.jsonl` in the home folder ([LOS §2.2](33-local-observability-store.spec.md)), because one session may supervise runs in several repositories. Owner-only. Append-only. Numbers, names from fixed lists, ids and times only.

| Entry | Written by | Fields |
|---|---|---|
| `session` | First write of the session | `host`, `host_session`, `started_at`, host version, `model` |
| `engine_call` | After an engine command finishes | `at`, `tool_use_id`, `agent_id` (a subagent, else null), `verb` (fixed list), `targets` (the selector resolved by the same function as the verbs: workflow, thread or orchestration ids), `mutating`, `background`, `exit_code`, `duration_s`, `output_bytes`, `call_id` (the engine's, when the verb printed one, [PRV §2.5](85-caller-provenance.spec.md)) |
| `person_turn` | A person submits a prompt | `at`, `prompt_id`, `names` ([PRV §2.4.1](85-caller-provenance.spec.md)) |
| `usage` | After each assistant message | `at`, `message_id`, `agent_id`, `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `tool_use_ids[]` (the calls the message issued) |
| `reported` | When the host reports a session figure | `at`, `reported_cost_usd`, its source (`statusline`, `sdk_result`) |
| `end` | Session end | `at`, reason |

Writers, by host:

| Writer | Entries | How |
|---|---|---|
| The tempergraph plugin's Claude Code hooks ([SHL §2.2](19-plugin-shell.spec.md)) | all | `SessionStart` → `session`; `UserPromptSubmit` → `person_turn`; `PostToolUse` on `Bash` whose command starts with the shim name → `engine_call`; `Stop` and `SubagentStop` → `usage` lines read from the transcript since the last offset, numbers only; `SessionEnd` → `end` |
| `supervision log` (§2.6) | all but `person_turn` | An application on the Agent SDK or the Messages API, or a wrapper around another host, pipes its own entries; an SDK application may also run the same hook logic through the SDK's hooks |
| Nobody | — | The orchestration supervisor, the schedule tick and a scripted pipeline call no model: their supervision cost is `measured_zero` by construction (contracts C16 and C18), with no journal |

A hook's failure, a full disk or a malformed transcript line costs that entry only; the host call it observed is never changed, delayed past 2 s or refused (contract C2). `observe.supervision = off` in the user config turns every write off; the next run records once that supervision is not measured.

### 2.3 Sources per host

The supervising host is not the step executor: a run whose steps execute on Antigravity may be babysat by Claude Code, and the reverse. Each of the four products can also be a supervising host.

| Host | Engine calls | Usage | Person turns | Figures |
|---|---|---|---|---|
| Claude Code (CLI, IDE, desktop, cloud) | `PostToolUse` hook | transcript usage per message via `Stop` / `SubagentStop`; `cost.total_cost_usd` of the status line as a session-level `reported` cross-check | `UserPromptSubmit` | tokens reported, cost estimated by the price table |
| Agent SDK application | SDK hooks or `supervision log` | per-message usage; `total_cost_usd` on the result message | the application's own, if any | tokens and session cost reported |
| Messages API application | `supervision log` | `usage` on each response | the application's own, if any | tokens reported, cost estimated |
| Antigravity session | not available until P-SUP-5 | tokens, if its hooks expose them (P-SUP-5) | not available | `unmeasured` until probed |
| Orchestration supervisor, schedule tick, scripted pipeline | — | — | — | `measured_zero` |
| `unknown` caller ([PRV §2.3](85-caller-provenance.spec.md)) | — | — | — | `unmeasured` |

### 2.4 Attribution

From the journal joined with the run logs by target and time. Each assistant message is counted at most once per thread, and each engine call is about the targets its selector resolved to; a call about an orchestration is split equally over the orchestration's runs live at that moment, and the orchestration keeps the total.

| Category | Calls or messages |
|---|---|
| `start` | `run`, `rerun`, `orchestrate start`, `batch` and the messages that prepared them after the session's first call (`run --check` rounds) |
| `watch` | `status`, `events`, `facts`, `wait`, `attention`, `orchestrate status`, `orchestrate wait` |
| `diagnose` | `logs`, `status --detail`, `audit`, `report`, `executors` about the target |
| `decide` | `resume`, `orchestrate answer`, `label` |
| `steer` | `stop`, `rerun --check`, `config`, `orchestrate edit`, a resume that only changes settings |
| `relay` | Messages between the message that read a pause (the consuming message of a call whose output held the pause) and the `decide` call that answered it, when a `person_turn` lies between |
| `rewake` | The cache write of a **wake message**: the first assistant message after the session was idle ≥ `observe.wake_idle_s` (default 300 s, the shortest prompt-cache lifetime) that follows the end of a background engine call or the arrival of its exit |

Two figures per call, never summed ([ADR-0088](../adr/0088-attribute-supervision-spend-by-marginal-tokens-beside-turn-totals.adr.md)):

| Figure | Tokens counted |
|---|---|
| **Marginal** | The issuing message's output tokens divided by the number of calls it issued; the call's result read by the next message, as `ceil(output_bytes / 4)` input tokens capped at that message's new input tokens; for a wake message, its cache write tokens (`rewake`) |
| **Turn** | The whole usage of the issuing message and of the next message, plus every `relay` message; and the whole usage of a subagent whose transcript holds a call about the target |

Both are priced with the engine's price table (cache reads and writes at their own rates, [OBS §2.2](15-observability-and-cost.spec.md)) as `estimated_usd`. A session-level `reported` figure is kept on the session and shown beside the sum of its attributed and `other` spend; it is never split onto threads.

### 2.5 Closing a thread's supervision cost

A thread's supervision cost is **open** while any supervising session that touched it is live, and **closes** when each has ended or has made no call about it for 24 h after the thread's last `run_exit`. On close:

- a ledger line of kind `supervision` is appended with the thread id and the cost fields of [SUP §2.2](86-supervision-metrics.spec.md); readers join it to the thread's row ([SIL §2.4](16-self-improvement.spec.md));
- a `supervision` row goes to the outbox of each configured sink ([CST §2.2](34-central-run-stats.spec.md)).

The closer runs from the next engine process on the machine (any verb that writes), from `stats flush`, and from the plugin's `SessionEnd` hook through `supervision close`; never from a read-only verb.

| Field | Meaning |
|---|---|
| `marginal`, `turn` | `{tokens by kind, estimated_usd}` per category of §2.4 and in total |
| `sessions[]` | Host, hashed host session, model, window, reported session figure |
| `completeness` | `complete` (every supervising session had usage), `estimated` (some result sizes stood in for tokens), `incomplete` (a supervisor was seen but is unmeasured), `measured_zero` (only the supervisor or a pipeline), `none_known` (no supervising call seen) |

`none_known` is not zero: a run started by a person who then did nothing has no supervising session, and a run babysat by an unmarked host looks the same; [SUP](86-supervision-metrics.spec.md) shows the caller data-quality figure beside it.

### 2.6 Verbs

| Verb | Does | Writes | Spends |
|---|---|---|---|
| `supervision log --host <name> --session <id> [--caller-app <name>]` | Appends entries read as JSON lines from standard input to that session's journal, after schema checks: fixed fields, numbers in range, no free text beyond ids | the journal only | no |
| `supervision close [--session <id>]` | Closes what §2.5 allows | ledger lines, outbox rows | no |
| `supervision show <selector> \| --session <id> [--json]` | A thread's or session's supervision: calls, person turns, categories, both figures, completeness | no | no |

`report --supervision` and `stats --by level|decider|host` read the closed figures ([SUP §2.4](86-supervision-metrics.spec.md)).

### 2.7 Privacy and retention

The journal holds no prompt, command line, tool output or transcript text: a verb word, resolved ids, counts, sizes and times. Anything that leaves the machine carries hashed host sessions and thread ids ([CST §2.4](34-central-run-stats.spec.md)). Journals are kept 90 days, like evidence ([LOS §2.5](33-local-observability-store.spec.md)); closed figures stay with the ledger.

## 3. Behaviours

**SCO-B1 A run driver session.** Given a Claude Code session that runs `run --check` twice, starts a run in the background, is woken by its exit 3 after 40 idle minutes, reads `facts`, shows the pause to the person, gets "proceed" and resumes with `--relayed`, when the thread's supervision closes, then the categories are filled as below and completeness is `complete`.

| Category | Calls | Marginal (example) | Turn (example) |
|---|---|---|---|
| start | 3 | 2.1K tokens | 61K |
| watch | 1 (`facts`) | 1.4K | 38K |
| rewake | 1 wake message | 95K cache write | (inside watch) |
| relay | 2 messages | — | 44K |
| decide | 1 | 0.6K | 41K |


**SCO-B3 An orchestration.** Given the orchestrator skill's session that calls `orchestrate wait` four times while three runs are live, when the orchestration ends, then each wait is split over the live runs, the orchestration report prints the skill's marginal figure, the runs' estimated cost and the share against [OSK-AC-4](46-orchestrator-skill.spec.md), and the supervisor's own figure is `measured_zero`.

**SCO-B4 An application reports.** Given an Agent SDK application that pipes `engine_call` and `usage` entries and its result message's cost to `supervision log`, when the thread closes, then the thread's figures come from those entries and the session's reported cost is shown beside them.

**SCO-B5 An unmeasured supervisor.** Given a run resumed by an `unknown` caller, when its supervision closes, then completeness is `incomplete`, the cost fields are null, and `report --supervision` counts the run under "cost not measured".

**SCO-B6 The engine's own sessions.** Given a step session on `claude` that loads the tempergraph plugin and calls `self-check`, when its hooks fire, then they write nothing, because `TEMPERGRAPH_SESSION_KEY` is set.

**SCO-B7 Other work stays off the run.** Given a session that supervises one run and also edits code for an hour, when the thread closes, then only the messages of §2.4 are on the thread, and `supervision show --session` lists the rest as `other`.

**SCO-B8 Helpers.** Given a supervising session that starts a subagent to diagnose a failed run and the subagent calls `logs` and `status --detail`, when the thread closes, then the subagent's whole usage is in the thread's turn figure under `diagnose`, and its calls' marginal tokens in the marginal figure.

## 4. Error conditions

| Condition | Result |
|---|---|
| `supervision log` input with a field outside the schema, free text or a negative number | Exit 2, nothing appended |
| A transcript line the hook cannot parse | Skipped and counted on the next entry; completeness `estimated` for that session |
| A journal names a target that no state root on the machine knows | Kept; attributed if the thread appears later; never an error |
| Two hosts claim the same `host_session` | Kept apart by host; the pair is shown in `supervision show` |

## 5. Design notes

- **Measured where it is spent** ([ADR-0087](../adr/0087-a-supervision-journal-written-by-the-host-not-by-read-only-verbs.adr.md)). The supervising session's host is the only place that sees its usage. The plugin already ships in that host, so the measurement comes with it and needs nothing from the person.
- **Two figures** ([ADR-0088](../adr/0088-attribute-supervision-spend-by-marginal-tokens-beside-turn-totals.adr.md)). A turn's input holds the whole conversation, so its total overstates what a run cost the session; the marginal figure understates the context a run makes the session carry. Showing both brackets the truth; promotion uses the marginal figure with `rewake` in it.
- **Probe.** P-SUP-3: `PostToolUse` input for `Bash` carries the command and the response size, and `Stop` and `SubagentStop` give a transcript path whose assistant lines carry usage. Not run. Until it passes the Claude Code row of §2.3 is projected.
- **Release 1 build** ([T7 plan](../plans/t7-observability.plan.md) T7.6): `observe/supervision_cost.py`, the plugin's `hooks/hooks.json` and the `supervision` verbs. The Claude Code payload fields used (`session_id`, `cwd`, `prompt`, `tool_name`, `tool_input.command`, `tool_input.run_in_background`, `tool_use_id`, `agent_id`, `tool_response.stdout|stderr|exit_code`, `transcript_path`, `agent_transcript_path`, `reason`) are the documented shape, not yet probed (P-SUP-3 pending). Deviations: the hook reads the printed output only for its size and a `thread_id` or `call_id` in it, and keeps neither text; an engine call's `duration_s` is null; `relay` in `calls` counts messages; the relay window starts at the read call; `measured_zero`, orchestration splits and the status line's `reported` entry wait for orchestrations (release 3) and a status line; journals are not yet pruned at 90 days. `observations` on the closed line counts `watch` and `diagnose` calls.

## 6. Acceptance criteria

- [ ] SCO-AC-1 Fixture transcripts and journals reproduce the SCO-B1 categories and both figures by one attribution function, used by `supervision show`, `report --supervision` and the closer.
- [ ] SCO-AC-2 Every read-only verb leaves the home folder's journal and ledger unchanged (hash test, CLI-AC-1).
- [ ] SCO-AC-3 A canary prompt, command and tool output appear in no journal entry, ledger line or sink row.
- [ ] SCO-AC-4 A hook failure injected at each entry kind leaves the host call's result and duration (within 2 s) unchanged.
- [ ] SCO-AC-5 Sessions with `TEMPERGRAPH_SESSION_KEY` write no journal entry.
- [ ] SCO-AC-6 P-SUP-3 has a recorded result with date, machine and Claude Code version, and on a live orchestration of three or more runs the share of [OSK-AC-4](46-orchestrator-skill.spec.md) is computed by this spec.

## Open questions

| Question | Owner |
|---|---|
| Should the `rewake` idle threshold follow the host's actual cache lifetime when the host reports it (the status line's `prompt_cache.ttl`)? Assumed a fixed 300 s default. | Implementer |
| Should a team sink receive the session-level reported figure? Assumed yes, hashed. | Owner |

## References

