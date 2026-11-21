---
title: Run events for observers
type: component
status: ready-for-implementation
prefix: EVT
adrs: [0009, 0022, 0023, 0027]
---

# Run events for observers

## 1. Overview

What the engine writes and emits while a run is live, so an observer (the `tempergraph-monitor` mod, an exporter, a tracker plugin, a script) can follow it without reading the checkpoint and without changing it. Three things are defined here: the observer record kinds added to the run log, the per-session **activity journal**, and the two ways to subscribe (the `events` verb and the in-process observer interface, plus the widened lifecycle hook events). Everything here is best effort and never changes a run or its exit code (contract C2, owned by [OBS](15-observability-and-cost.spec.md)). The record kinds of [OBS §2.1](15-observability-and-cost.spec.md) stay where they are; this spec adds kinds and fields, never renames.

## 2. Contract

### 2.1 Common record envelope

Every run-log record, old kinds and new, carries these keys. Adding them keeps the run log's schema version ([CON §2.10](01-contracts.spec.md)).

| Key | Type | Meaning |
|---|---|---|
| `seq` | int | Per-thread, strictly increasing across resumes; the first record of a resume continues from the last committed `seq` |
| `ts` | RFC 3339 UTC | Write time |
| `kind` | string | Record kind |
| `thread_id`, `segment` | string, int | `segment` counts process lifetimes of the thread: 0 for the start, +1 per resume |
| `unit`, `item`, `attempt` | string?, string?, int? | Where in the graph, when the record belongs to a unit |
| `session_key` | string? | `<unit>[.<item>].<attempt>.<kind>[.<n>]`, e.g. `plan.2.judge` or `code.p3.1.judge_reask.2`; stable name of one session's folder ([LOS](33-local-observability-store.spec.md)) |

The optional keys are present on every record, null when the record has no unit. A record that names a `session_key` and leaves `unit` or `attempt` out gets them from the key. The writer finds its `segment` from the log itself: one more than the last `run_started`'s, or 0 for a new thread, so every writer in one process agrees. A last line cut off by a dead process is ended before the next record, and `seq` continues from the last whole record. A field named `kind` in §2.2 is written as `session_kind` (on `session_opened`) or `pause_kind` (on `pause`), because `kind` is the record kind.

### 2.2 Observer record kinds (additive)

| Kind | Written when | Key fields |
|---|---|---|
| `run_started` | After the lock and before the first unit, on start and each resume | `origin`, `parent` (orchestration id, node and item, when an orchestration started the run, [ORC](45-orchestration.spec.md)), `schedule` (schedule id, fire id and slot, when a schedule started it, [TCK §2.7](84-schedule-ticks-and-unattended-fires.spec.md)), `alias`, `label`, `workflow_version` ([VER §2.4](61-version-metadata.spec.md)), `plan_digest` (the diagram model's), `executors` planned per unit; `engine_version`, `shape_digest` and `moved_from` when the engine or the workflow changed since the last process ([MIG §2.1](62-state-and-run-migration.spec.md)); `settings_digest`, `profiles`, `overridden_keys` ([RST §2.7](80-run-settings-and-overrides.spec.md)); `rerun_of` for a rerun ([RRN §2.4](81-reruns-and-feedback.spec.md)); `dry_run` when the run was started with `--dry-run` ([CLI §2.1](17-engine-cli.spec.md)); `caller`, the `Caller` of the call that started or resumed the segment ([PRV §2.5](85-caller-provenance.spec.md)); `capture_lowered` (the capture items the operator turned off, [LOS §2.6](33-local-observability-store.spec.md)) and `observers` with `observers_missing` when the operator config names observers (§2.6); `content_version`, the workflow version with its content digest ([VER §2.4](61-version-metadata.spec.md)) |
| `settings_resolved` | Right after `run_started`, on start, each resume and a rerun | `settings_digest`, `rows[]` of `{key, value, layer, ref, shadowed[]}`, `changed_keys` ([RST §2.7](80-run-settings-and-overrides.spec.md)); `caller` when `changed_keys` is not empty; `stage`, and `unpromoted_pipeline: true` for a pipeline caller without a stamp ([PRO §2.1](95-promotion-check.spec.md)) |
| `workflow_changed` | Once, after `settings_resolved`, on a resume whose workflow version differs from the last process's and passes the tests of [MIG §2.5](62-state-and-run-migration.spec.md) | `from_version`, `to_version`, `units[]` (the units of the earlier version whose prompts, gates or limits changed) |
| `unit_entered` | A unit's step node is entered (also each visit after a trip back) | `visit`, `entered_from` (`start`, `proceed`, `retry`, `back:<unit>`, `rewind:<unit>`, `rerun`, `resume`); `head_commit` and `dirty` of the workspace when it is a git checkout, so a rerun can start from it ([RRN §2.4](81-reruns-and-feedback.spec.md)) |
| `session_opened` | The executor's `session_started` event arrives | `kind` (step, retry, judge, judge_reask, grouping, member, member_reask, chair), executor, alias, bound model, `session_id`, `transcript` (§2.4), `pgid` (process group id on POSIX, null elsewhere) |
| `check` | A deterministic check finishes | `result` (`PASS`, `MAYBE`, `FAIL`), `environmental`, `untracked_only`, `duration_s`, `output_path` (local), `evidence` clipped to 200 chars, scrubbed |
| `judgement` | A judgement block is parsed, before the gate derives the verdict | per criterion `{n, id?, status}` (no evidence text), `met`, `total`, `blockers` (criterion ids), `confidence` and its source, `gap`; `brief_digest` and `criteria_digest` of the judge binding ([FBK §2.1](41-feedback-and-judge-reliability.spec.md), [JCL §2.3](50-judge-calibration.spec.md)) |
| `ladder_decision` | A gate chose the rung of a unit's next attempt (release 2, [LAD §2.7](92-effort-ladder-and-model-escalation.spec.md)) | unit, item, attempt, `rung`, `effort`, `alias`, `source`, `evidence` (kind and criterion ids), `held_by`, `offered` |
| `judge_risk` | A judge with a risk rule resolved its level (release 2, [JRK §2.5](93-judge-model-by-risk.spec.md)) | unit, item, attempt, `level`, `would_choose`, `signals`, `chosen_by`, `alias`, `effort`, `fault` |
| `budget` | A budget counter is charged ([BUD](08-budgets-and-failures.spec.md)) | counter name, used, limit, cause |
| `pause` | A gate interrupts for a person | pause kind, `reason`, `question` (clipped, scrubbed), artifact keys to review, decision words, resume command, `tool_access[]` of `{name, capability, class}` for cause `tool_access` |
| `script` | A script of a script unit or a hybrid step ends ([SCR](70-script-units-and-hybrid-steps.spec.md)) | unit, name, phase (`unit`, `before`, `after`), command prefix (null for a callable), exit code, `duration_s`, `cached`, `environmental` |
| `council_round` | A council round's barrier closes ([CNL](71-council-unit.spec.md)) | round, members answered, spoiled, missing, `changed` count, label order |
| `finding_recorded` | After every `run_exit`, best effort | Cause codes and fault sides of the segment's findings, their count, and at a final exit the lenses that fire (`mode`, `friction`, `outcome.fire`, `outcome.needs_judge`, `cost`, the per-gate `quality` scorecard), and `labels` (`{labels, shifts}`: label rows and `binding_shift` findings this exit added, [FBK §2.2, §2.5](41-feedback-and-judge-reliability.spec.md)) ([SIL §2.1, §2.2](16-self-improvement.spec.md), IMD §2.3) |
| `outcome` | At a `run_exit` whose segment reached the outcome gate | The thread's `OutcomeRecord` so far: `revision`, `verdict`, `criteria[]` (id, class, severity, trust, status, grader), `intermediate[]`, `later[]`; the latest one is the thread's record, and the `run_segment` ledger row carries it as `outcome{}` (`not_reached` before the gate) ([OUT §2.5](90-run-outcome.spec.md)) |
| `council_tally` | A council's outcome is derived | mode, rule, counts per option or Borda points, outcome (`<option>`, `no_decision`), `chosen_by` |
| `contest_pick` | A contest's pick runs ([CTS](72-contest-unit.spec.md)) | per slot: check result, derived verdict, rank keys, cost; winner |
| `workspace` | The run's workspace is prepared, reused, attached, changed by a person between segments, released, removed or kept, or a foreign worktree appears during a session ([WTR §2.6, §2.10](82-worktree-mode.spec.md)) | `action` (`prepared`, `reused`, `attached`, `external_change`, `released`, `removed`, `kept`, `foreign`), `mode`, `resolved_by`, `branch`, `base_commit`, `reason`, counts; a path only in the local run log |
| `grant` | A tool grant or allowed command takes effect, on start, resume or rerun, or is removed ([RST §2.8](80-run-settings-and-overrides.spec.md)) | `unit`, `capability` or `prefix`, `action` (`given`, `removed`), `answers` (the refusal class and `seq` of the pause it fixes, if any), `by` (the `Caller`), `via` |
| `ruling` | A ruling is given or revoked ([RRN §2.2](81-reruns-and-feedback.spec.md)) | `id`, `action` (`given`, `revoked`), `given_at`, `applies_to`, `by` (the `Caller`), `chars`; never the text |
| `stop_requested` | A stop request is picked up ([RCT](32-run-control.spec.md)) | mode (`drain`, `now`), requested by (the `Caller` of the `stop` call, [PRV §2.5](85-caller-provenance.spec.md)) |
| `supervision` | At every `run_exit`, just before it | The thread's supervision record so far: touches by class and decider, waits, level and `level_by` ([SUP §2.2](86-supervision-metrics.spec.md)); cost fields null until closed ([SCO §2.5](87-supervision-cost.spec.md)) |
| `run_exit` | The process ends the segment | exit code, reason word, cost figures and completeness flag |

The existing `gate` record gains the optional keys `route_target` and `judgement_seq` (the `seq` of its `judgement`). The existing `attempt_start` gains `session_key` and `prompt_digest` (the first 16 hex of the SHA-256 of the rendered prompt, [OBS §2.4](15-observability-and-cost.spec.md)); `agent_run` gains `duration_s`, `tool_wall_share` and `slow_host`. The `gate`, `pause` and `run_exit` records carry `cost_so_far` (`reported`, `estimated`, completeness flag for the thread so far), so a follower such as the orchestration supervisor reads spend without building the detail document.

### 2.3 Activity journal

One JSON-lines file per session at `sessions/<session_key>/activity.jsonl` in the run's folder ([LOS §2.1](33-local-observability-store.spec.md)), written by the same writer that feeds the live progress file, from the normalized events ([CON §2.7](01-contracts.spec.md)). The writer buffers lines and appends them at most once a second, on the `result` event and at session end; in-process observers get each line after it is appended (§2.6).

| Field | Meaning |
|---|---|
| `t` | Receive time from the launcher, seconds since session spawn (float) |
| `n` | Per-session line number |
| `ev` | Normalized event name |
| event fields | As in CON §2.7, plus `capability` and `input_summary` on `tool_started` (§2.5) and `duration_s` on `tool_finished` |

A `resources` line is added every 10 s while the session runs (POSIX): CPU seconds and peak resident memory summed over the session's process group, and the number of processes in it, from a read-only process listing with constant argv; numbers only. The time profile and the detail document read it ([OBS](15-observability-and-cost.spec.md), [RDD](31-run-detail-document.spec.md)).

Rules: append-only, flushed at most once a second and at session end; local only; capped at 20 000 lines or 8 MB per session, after which `model_delta` lines are dropped first, then `text` lines, and a final `truncated` line counts what was dropped. The cap is applied as the journal grows, so tool lines are never the ones dropped: past half the cap `model_delta` lines are dropped, past three quarters `text` lines too, past 95 % every line but `tool_started` and `tool_finished`, and the last line is kept for `truncated`. The journal is not a run-log record and is never read by the analyzer for cost.

The live progress file of the same session holds `open_tool` (name, capability, input summary, `started_at`), `recent` (the last ten finished calls with name, input summary, `ok` and `duration_s`), `last_text`, `tokens_so_far`, `turns_so_far`, `pgid` and `last_event_at`; it is removed at session end ([LOS §2.1](33-local-observability-store.spec.md)). The detail document turns its times into the ages of [RDD §2.2](31-run-detail-document.spec.md).

### 2.4 Transcript locator

`transcript` on `session_opened` says where the session's full record is: `{engine: <path of raw.jsonl>, native: <path or null>, native_kind}`. `engine` is always the engine's own copy of the raw stream ([ADR-0009](../adr/0009-normalized-session-event-stream.adr.md), [LOS](33-local-observability-store.spec.md)). `native` is the executor's own transcript when the executor declares one and its path is known: `claude` and `agent-sdk` (Claude Code's session store, by session id; probe P-CC-7 / P-AS-4), else null.

### 2.5 Tool input summaries

`tool_started` gains `input_summary`: one line, scrubbed by the pattern scrubber ([SEC §2.3](14-security.spec.md)), clipped to 200 characters, built by the executor's translator from the tool's input.

| Capability ([CON §2.5](01-contracts.spec.md)) | Summary |
|---|---|
| `shell` | The command line as given to the shell; the working directory relative to the workspace if not the workspace itself, when the tool's input names one (Claude Code's `Bash` input has no working directory, so its summary is the command alone) |
| `read`, `edit`, `write`, `list` | The path relative to the workspace; a path outside it reads `<outside workspace>` |
| `search` | The pattern, clipped |
| `web_fetch` | The URL's host only |
| `web_search` | `query` (the word, never the query text) |
| `subagent` | The subagent type name |
| MCP tool | Server and tool name only |
| Unknown | null |

An operator may set `observe.tool_inputs = off` in the operator config: summaries are then null everywhere. Summaries live only in the activity journal and the live progress file; no run-log record, ledger row, stats row, finding, export or filed text carries them.

### 2.6 Subscribing

```python
class RunObserver(Protocol):
    name: str
    def on_record(self, record: dict) -> None: ...        # every run-log record, after it is written
    def on_activity(self, session_key: str, line: dict) -> None: ...   # every activity line, after it is written

def register_observers(entry_point_group: str = "tempergraph.observers") -> list[RunObserver]: ...
```

| Way | For | Rule |
|---|---|---|
| `events <selector> [--since <seq>] [--follow] [--activity <session_key>] [--json]` | Any reader: the monitor, a script | Read-only, model-free (contract C13); prints records in `seq` order; `--follow` ends when the segment's `run_exit` is read and no lock is held |
| In-process observer | Exporters ([TEL](35-telemetry-export.spec.md)) and sinks ([CST](34-central-run-stats.spec.md)) | Enabled by name in the operator config only; each runs on its own thread behind a bounded queue (1 000 items); a full queue drops and counts; an exception disables that observer for the segment and is recorded once, as an `engine_error` record of scope `observer` written by the run's own writer at its next record |
| Lifecycle hook ([CLI §2.2](17-engine-cli.spec.md)) | Commands such as a tracker plugin | Run events widened to `started`, `unit_entered`, `gate_verdict`, `paused`, `resumed`, `stop_requested`, `stalled`, `finished`, `failed`; orchestration events are [ORC](45-orchestration.spec.md)'s and schedule events [SCH](83-schedules.spec.md)'s; detached, ticketed, with a facts file only |

Release 1 ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)): the `events` verb and the observer interface ship; no observer is enabled unless the `observers` list of the operator's `observe` settings names it ([RST §2.4](80-run-settings-and-overrides.spec.md)), and lifecycle hooks are release 2. As built (R2-T7): a hook event is read off the run log's own record (`run_started` of segment 0 is `started`, of a later segment `resumed`; `unit_entered`; `gate` is `gate_verdict`; `pause` is `paused`; `stop_requested`; `run_exit` with code 0 is `finished`, with 3 nothing, with any other `failed`), and the facts file holds the record's ids, enums and numbers only: event, workflow, thread, `seq`, `ts`, `segment`, unit, item, attempt, token, verdict, route target, pause kind, exit code and reason.

## 3. Behaviours

**EVT-B1 A session is visible while it runs.** Given a step session on `claude` that has been running for 40 s, when an observer reads the run log, then it finds a `session_opened` record with the session id and the transcript locator, and the activity journal has a line for every tool call so far.

**EVT-B2 Sequence across resume.** Given a thread whose segment 0 ended at `seq` 812 with a pause, when it is resumed, then the first record of segment 1 is `run_started` with `seq` 813 and `segment` 1.

**EVT-B3 Follow from an offset.** Given `events auth-fix --since 500 --follow`, when the run writes records 501 to 640 and exits 3, then the verb prints exactly 501 to 640 and exits 0 once the lock is free.

**EVT-B4 Shell summary.** Given a step that runs `pytest -q tests/api` in `<workspace>/svc`, when the tool starts, then the activity line is `tool_started` with name `Bash`, capability `shell` and `input_summary` `pytest -q tests/api (in svc)`.

| Raw input | `input_summary` |
|---|---|
| `export TOKEN=sk-ant-abc… && make test` | `export TOKEN=[redacted] && make test` (the scrubber's marker, [SEC §2.3](14-security.spec.md)) |
| `cat /etc/passwd` (read tool) | `<outside workspace>` |
| 600-character heredoc | first 199 characters and `…` |

**EVT-B5 Observer failure is contained.** Given an in-process observer that raises on its third record, when the run continues, then the observer is disabled for the segment, one `engine_error` record of scope `observer` is written, and the run's exit code is unchanged.

**EVT-B6 Hidden inputs.** Given `observe.tool_inputs = off`, when any session runs, then every `input_summary` is null and the live progress file shows tool names only.

**EVT-B7 Journal cap.** Given a session that emits 30 000 events, when it ends, then its journal holds at most 20 000 lines, every `tool_started` and `tool_finished` is kept, and the last line is `truncated` with counts per dropped event name.

## 4. Error conditions

| Condition | Result |
|---|---|
| Activity journal write fails | Journal disabled for that session, one `engine_error` record; the session and the live file go on |
| The ledger row or the exit file cannot be written (a full disk) | The exit code is unchanged; one `engine_error` record of scope `ledger` or `exit_file` is attempted ([OBS-B3](15-observability-and-cost.spec.md)) |
| Recording the loop's findings fails | The exit code is unchanged; one `engine_error` record of scope `improve` ([SIL-B1](16-self-improvement.spec.md)) |
| A reader meets an unknown kind or field | Skipped (contract C12) |
| `events` on a selector with no run log | Exit 2, nothing created |
| An observer named in config is not installed | Warning at preflight, recorded; the run starts |

## 5. Design notes

- Observers read append-only files and read-only verbs; there is no socket and no daemon, so an observer can start after the run, survive the engine dying, and never hold anything the run waits on ([ADR-0022](../adr/0022-observers-read-files-not-sockets.adr.md)).
- The live progress file stays the cheap "now" view; the activity journal is the "so far" view. Both come from one writer thread, so the stream pump never waits on disk ([ADR-0009](../adr/0009-normalized-session-event-stream.adr.md)).
- Shell commands are the most useful and the most sensitive field; they stay local and scrubbed, and can be switched off ([ADR-0023](../adr/0023-local-activity-journal-with-tool-input-summaries.adr.md)).
- Observer and hook widening follow [ADR-0027](../adr/0027-in-process-observers-and-wider-hook-events.adr.md); the engine still ships no hook and no exporter enabled by default.
- The `judgement` record and the `gate` record linked to it by `judgement_seq` together hold what [IMD-R3](43-improvement-data.spec.md) asks of a gate; the loop's events of IMD-R11 reach observers through the same `on_record` path and hook events.
- The `judgement` record carries statuses and ids, never evidence text; evidence is in the local evidence file and is shown by the detail document from there ([RDD](31-run-detail-document.spec.md)).

## 6. Acceptance criteria

- [ ] EVT-AC-1 A scripted-executor run writes every kind of §2.2 with the envelope of §2.1, and an old reader of the run log passes the same fixture.
- [ ] EVT-AC-2 `seq` is strictly increasing over a fixture thread with three resumes and a cut-off attempt.
- [ ] EVT-AC-3 Each row of EVT-B4's table is reproduced by the translator test of every executor that declares `reports_actions`.
- [ ] EVT-AC-4 The canary test of [SEC-B2](14-security.spec.md) finds the canary in no record of §2.2, and finds a planted tool input only in activity journals and live files.
- [ ] EVT-AC-5 A failure injected into each observer path leaves the run and its exit code unchanged.
- [ ] EVT-AC-6 `events --follow` on a live fixture run prints every record once, in order, and creates nothing.

## Open questions

| Question | Owner |
|---|---|
| Probe P-CC-7 / P-AS-4: does a `claude -p` session started by the engine keep a native transcript, and at which path, when the engine passes its isolation flags? Until run, `native` is null. | Executor implementer |
| Should `input_summary` for `edit` carry a changed-line count? Release 1 default: no; deferred until the monitor shows a need. | Monitor owner |

## References

