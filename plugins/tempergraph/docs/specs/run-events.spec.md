# Run events for observers

## Purpose

What the engine writes and emits while a run is live, so an observer (the `tempergraph-monitor` mod, an exporter, a tracker plugin, a script) can follow it without reading the checkpoint and without changing it: the observer record kinds added to the run log, the per-session activity journal, and the ways to subscribe (the `events` verb, the in-process observer interface and the widened lifecycle hook events). Everything here is best effort and never changes a run or its exit code (OVR-B4, owned by [OBS](observability-and-cost.spec.md)). The record kinds of [OBS](observability-and-cost.spec.md) stay where they are; this spec adds kinds and fields, never renames. Observers read append-only files and read-only verbs, with no socket and no daemon ([ADR `observers-read-files-not-sockets`](../adr/observers-read-files-not-sockets.adr.md)); shell commands stay local and scrubbed ([ADR `local-activity-journal-with-tool-input-summaries`](../adr/local-activity-journal-with-tool-input-summaries.adr.md)); observers and hook events follow [ADR `in-process-observers-and-wider-hook-events`](../adr/in-process-observers-and-wider-hook-events.adr.md). The monitor, exporters, central stats, tracker plugins and the detail document depend on these records ([research `observer-needs-against-engine-documents`](../research/observer-needs-against-engine-documents.rsrch.md)).

## Behaviours

### EVT-B8 Common record envelope

WHEN any run-log record is written, old kinds and new THE writer SHALL give it `seq` (per thread, strictly increasing across resumes), `ts` (RFC 3339 UTC write time), `kind`, `thread_id`, `segment` (0 for the start, one more per resume), `unit`, `item` and `attempt` (null when the record has no unit) and `session_key` (`<unit>[.<item>].<attempt>.<kind>[.<n>]`, such as `plan.2.judge` or `code.p3.1.judge_reask.2`, the stable name of one session's folder, [LOS](local-observability-store.spec.md)), keeping the run log's schema version ([CON-B14](contracts.spec.md)), filling `unit` and `attempt` from a named `session_key`, and writing a field named `kind` as `session_kind` on `session_opened` and `pause_kind` on `pause`.

- GIVEN a record naming `session_key` `plan.2.judge` and no unit WHEN written THEN its `unit` is `plan` and `attempt` 2

### EVT-B9 Segment and sequence from the log

WHEN a writer starts THE writer SHALL find its `segment` from the log itself (one more than the last `run_started`'s, or 0 for a new thread), end a last line cut off by a dead process before the next record, and continue `seq` from the last whole record.

- GIVEN a log whose last line was cut off WHEN the next record is written THEN the cut line is ended and `seq` follows the last whole record

### EVT-B2 Sequence across resume

WHEN a thread whose segment 0 ended at `seq` 812 with a pause is resumed THE writer SHALL write `run_started` as the first record of segment 1 with `seq` 813 and `segment` 1.

- GIVEN segment 0 ending at `seq` 812 WHEN resumed THEN the first record is `run_started` with `seq` 813 and `segment` 1

### EVT-B10 Run started

WHEN a process has taken the lock and before the first unit, on start and each resume THE engine SHALL write `run_started` with `origin`; `parent` (orchestration id, node and item, [ORC](orchestration.spec.md)) and `schedule` (schedule id, fire id and slot, [TCK](schedule-ticks-and-unattended-fires.spec.md)) when one started the run; `alias`, `label`, `workflow_version` and `content_version` (the version with its content digest, [VER](version-metadata.spec.md)); `plan_digest` (the diagram model's); `executors` planned per unit; `engine_version`, `shape_digest` and `moved_from` when the engine or workflow changed since the last process ([MIG](state-and-run-migration.spec.md)); `settings_digest`, `profiles` and `overridden_keys` ([RST](run-settings-and-overrides.spec.md)); `rerun_of` for a rerun ([RRN](reruns-and-feedback.spec.md)); `dry_run` for `--dry-run`; `caller`, the caller of the call that started or resumed the segment ([PRV](caller-provenance.spec.md)); `capture_lowered` ([LOS](local-observability-store.spec.md)); and `observers` with `observers_missing` when the operator config names observers.

- GIVEN a run started by a schedule WHEN `run_started` is read THEN it carries the schedule id, fire id and slot

### EVT-B11 Settings and workflow changes

WHEN `run_started` has been written on start, each resume and a rerun THE engine SHALL write `settings_resolved` with `settings_digest`, `rows[]` of `{key, value, layer, ref, shadowed[]}` and `changed_keys`, `caller` when `changed_keys` is not empty, and `stage` with `unpromoted_pipeline: true` for a pipeline caller without a stamp ([PRO](promotion-check.spec.md)); and once after it, on a resume whose workflow version differs from the last process's and passes the migration tests ([MIG](state-and-run-migration.spec.md)), `workflow_changed` with `from_version`, `to_version` and `units[]` (the units whose prompts, gates or limits changed).

- GIVEN a resume on a changed workflow version WHEN records are written THEN `workflow_changed` follows `settings_resolved` once

### EVT-B12 Units, sessions, checks and judgements

WHEN a unit's step node is entered (each visit, a trip back included), an executor's `session_started` event arrives, a deterministic check finishes, or a judgement block is parsed before the gate derives the verdict THE engine SHALL write `unit_entered` (`visit`, `entered_from` one of `start`, `proceed`, `retry`, `back:<unit>`, `rewind:<unit>`, `rerun`, `resume`, and `head_commit` and `dirty` for a git workspace); `session_opened` (session kind one of step, retry, judge, judge_reask, grouping, member, member_reask, chair, executor, alias, bound model, `session_id`, `transcript`, `pgid` on POSIX else null); `check` (`result` `PASS`, `MAYBE` or `FAIL`, `environmental`, `untracked_only`, `duration_s`, local `output_path`, `evidence` clipped to 200 characters and scrubbed); and `judgement` (per criterion `{n, id?, status}` with no evidence text, `met`, `total`, `blockers`, `confidence` and its source, `gap`, and the binding's `brief_digest` and `criteria_digest`, [FBK](feedback-and-judge-reliability.spec.md), [JCL](judge-calibration.spec.md)).

- GIVEN a judgement with evidence text WHEN its record is written THEN it holds statuses and ids and no evidence

### EVT-B13 Ladders, risk, budgets, pauses and scripts

WHEN a gate chooses the rung of a unit's next attempt ([LAD](effort-ladder-and-model-escalation.spec.md)), a judge with a risk rule resolves its level ([JRK](judge-model-by-risk.spec.md)), a budget counter is charged ([BUD](budgets-and-failures.spec.md)), a gate interrupts for a person, a script of a script unit or hybrid step ends ([SCR](script-units-and-hybrid-steps.spec.md)), or a council round's barrier closes ([CNL](council-unit.spec.md)) THE engine SHALL write `ladder_decision` (unit, item, attempt, `rung`, `effort`, `alias`, `source`, `evidence` kind and criterion ids, `held_by`, `offered`); `judge_risk` (unit, item, attempt, `level`, `would_choose`, `signals`, `chosen_by`, `alias`, `effort`, `fault`); `budget` (counter name, used, limit, cause); `pause` (pause kind, `reason`, `question` clipped and scrubbed, artifact keys to review, decision words, resume command, and `tool_access[]` of `{name, capability, class}` for cause `tool_access`); `script` (unit, name, phase `unit`, `before` or `after`, command prefix or null for a callable, exit code, `duration_s`, `cached`, `environmental`); and `council_round` (round, members answered, spoiled, missing, `changed` count, label order).

- GIVEN a pause for cause `tool_access` WHEN its record is written THEN it carries `tool_access[]` with name, capability and class

### EVT-B14 Findings and outcome

WHEN a `run_exit` has been written THE engine SHALL write, best effort, `finding_recorded` (cause codes and fault sides of the segment's findings and their count, at a final exit the lenses that fire, `mode`, `friction`, `outcome.fire`, `outcome.needs_judge`, `cost`, the per-gate `quality` scorecard, and `labels` with the label rows and `binding_shift` findings this exit added, [FBK](feedback-and-judge-reliability.spec.md), [SIL](self-improvement.spec.md)), and, when the segment reached the outcome gate, `outcome` with the thread's outcome record so far (`revision`, `verdict`, `criteria[]` with id, class, severity, trust, status and grader, `intermediate[]`, `later[]`), the latest one being the thread's record and the `run_segment` ledger row carrying it as `outcome{}`, `not_reached` before the gate ([OUT](run-outcome.spec.md)).

- GIVEN a segment that never reached the outcome gate WHEN its ledger row is written THEN `outcome` reads `not_reached`

### EVT-B15 Councils, contests, workspaces, grants, rulings, stops and exits

WHEN a council's outcome is derived, a contest's pick runs ([CTS](contest-unit.spec.md)), the run's workspace is prepared, reused, attached, changed by a person between segments, released, removed or kept, or a foreign worktree appears ([WTR](worktree-mode.spec.md)), a tool grant or allowed command takes effect or is removed ([RST](run-settings-and-overrides.spec.md)), a ruling is given or revoked ([RRN](reruns-and-feedback.spec.md)), a stop request is picked up ([RCT](run-control.spec.md)), a `run_exit` is about to be written, or the process ends the segment THE engine SHALL write `council_tally` (mode, rule, counts per option or Borda points, outcome `<option>` or `no_decision`, `chosen_by`); `contest` (`winner`, the place in the slots' order, counted from 1, of the slot the pick kept, null when every check failed; and per slot its `slot` place, `name`, check result, derived verdict, rank keys and cost, or `skipped` when the attempt's cost cap kept it from starting); `workspace` (`action` one of `prepared`, `reused`, `attached`, `external_change`, `released`, `removed`, `kept`, `foreign`, `mode`, `resolved_by`, `branch`, `base_commit`, `reason`, counts, and a path only in the local run log); `grant` (`unit`, `capability` or `prefix`, `action` `given` or `removed`, `answers` with the refusal class and `seq` of the pause it fixes, `by`, `via`); `ruling` (`id`, `action` `given` or `revoked`, `given_at`, `applies_to`, `by`, `chars`, never the text); `stop_requested` (mode `drain` or `now`, requested by the caller of `stop`); `supervision` (touches by class and decider, waits, level and `level_by`, cost fields null until closed, [SUP](supervision-metrics.spec.md), [SCO](supervision-cost.spec.md)); and `run_exit` (exit code, reason word, cost figures and completeness flag).

- GIVEN a ruling given WHEN its record is written THEN it holds the character count and not the text

### EVT-B16 Keys added to existing records

WHEN a `gate`, `attempt_start`, `agent_run`, `pause` or `run_exit` record is written THE engine SHALL add to `gate` the optional `route_target` and `judgement_seq` (the `seq` of its `judgement`), to `attempt_start` `session_key` and `prompt_digest` (the first 16 hex of the SHA-256 of the rendered prompt, [OBS](observability-and-cost.spec.md)), to `agent_run` `duration_s`, `tool_wall_share` and `slow_host`, and to `gate`, `pause` and `run_exit` `cost_so_far` (`reported`, `estimated` and the completeness flag for the thread so far), so a follower reads spend without building the detail document.

- GIVEN a `gate` record after a judgement WHEN read THEN its `judgement_seq` is the `seq` of that judgement

### EVT-B17 Activity journal

WHEN a session runs THE writer that feeds the live progress file SHALL write the session's activity journal at `sessions/<session_key>/activity.jsonl` in the run's folder ([LOS](local-observability-store.spec.md)) from the normalized events ([SSN-B7](session-contract.spec.md)), one line per event with `t` (receive time in seconds since spawn), `n` (per-session line number), `ev` (the event name) and the event's fields, plus `capability` and `input_summary` on `tool_started` and `duration_s` on `tool_finished`, append-only, local only, buffered and appended at most once a second, on the `result` event and at session end, never read by the analyzer for cost; in-process observers get each line after it is appended.

- GIVEN a session with three tool calls WHEN its journal is read THEN it holds a `tool_started` and a `tool_finished` line for each

### EVT-B1 A session is visible while it runs

WHEN an observer reads the run log of a step session on `claude` that has run for 40 s THE engine SHALL have written a `session_opened` record with the session id and the transcript locator, and an activity line for every tool call so far.

- GIVEN a session running for 40 s WHEN an observer reads the run log THEN `session_opened` and every tool call so far are there

### EVT-B18 Resource lines

WHEN a session runs on POSIX THE writer SHALL add a `resources` line every 10 s with CPU seconds and peak resident memory summed over the session's process group and the number of processes in it, from a read-only process listing with constant argv, numbers only, for the time profile and the detail document ([OBS](observability-and-cost.spec.md), [RDD](run-detail-document.spec.md)).

- GIVEN a session running 35 s on POSIX WHEN its journal is read THEN it holds three `resources` lines

### EVT-B7 Journal cap

WHEN a session's journal grows THE writer SHALL cap it at 20 000 lines or 8 MB, dropping `model_delta` lines past half the cap, `text` lines too past three quarters, and every line but `tool_started` and `tool_finished` past 95 %, keeping the last line for a `truncated` line that counts what was dropped per event name.

- GIVEN a session that emits 30 000 events WHEN it ends THEN its journal holds at most 20 000 lines, every tool line is kept and the last line is `truncated`

### EVT-B19 Live progress file

WHEN a session runs THE writer SHALL keep its live progress file with `open_tool` (name, capability, input summary, `started_at`), `recent` (the last ten finished calls with name, input summary, `ok` and `duration_s`), `last_text`, `tokens_so_far`, `turns_so_far`, `pgid` and `last_event_at`, and remove it at session end ([LOS](local-observability-store.spec.md)); the detail document turns its times into ages ([RDD](run-detail-document.spec.md)).

- GIVEN a session that ended WHEN its folder is read THEN no live progress file remains

### EVT-B20 Transcript locator

WHEN `session_opened` is written THE engine SHALL set `transcript` to `{engine, native, native_kind}`, `engine` always being the engine's own copy of the raw stream ([ADR `normalized-session-event-stream`](../adr/normalized-session-event-stream.adr.md)) and `native` the executor's own transcript when the executor declares one and its path is known (`claude` and `agent-sdk`, Claude Code's session store by session id, probes P-CC-7 and P-AS-4), else null.

- GIVEN a session on an executor with no native transcript WHEN `session_opened` is read THEN `native` is null

### EVT-B21 Tool input summaries

WHEN a tool starts THE executor's translator SHALL build `input_summary` as one line, scrubbed ([SEC-B8](security.spec.md)) and clipped to 200 characters: for `shell` the command line, with the working directory relative to the workspace when the input names one other than the workspace (Claude Code's `Bash` names none); for `read`, `edit`, `write` and `list` the path relative to the workspace, or `<outside workspace>`; for `search` the pattern; for `web_fetch` the URL's host only; for `web_search` the word `query`, never the query text; for `subagent` the type name; for an MCP tool server and tool name only; and null for an unknown tool; summaries live only in the activity journal and the live progress file, never in a run-log record, ledger row, stats row, finding, export or filed text.

- GIVEN a `web_fetch` of `https://example.com/a?b=c` WHEN summarized THEN the summary is `example.com`

### EVT-B4 Shell summary

WHEN a step runs `pytest -q tests/api` in `<workspace>/svc` THE translator SHALL write `tool_started` with name `Bash`, capability `shell` and `input_summary` `pytest -q tests/api (in svc)`.

- GIVEN `export TOKEN=sk-ant-abc… && make test` WHEN summarized THEN it reads `export TOKEN=[redacted] && make test`
- GIVEN `cat /etc/passwd` by the read tool WHEN summarized THEN it reads `<outside workspace>`
- GIVEN a 600-character heredoc WHEN summarized THEN it holds the first 199 characters and `…`

### EVT-B6 Hidden inputs

WHEN `observe.tool_inputs = off` is set in the operator config THE engine SHALL make every `input_summary` null, so the live progress file shows tool names only.

- GIVEN `observe.tool_inputs = off` WHEN any session runs THEN every `input_summary` is null

### EVT-B22 The events verb

WHEN `events <selector> [--since <seq>] [--follow] [--activity <session_key>] [--json]` runs THE engine SHALL print the records in `seq` order, read-only and model-free (OVR-B15), end `--follow` when the segment's `run_exit` is read and no lock is held, and exit 2 creating nothing on a selector with no run log.

- GIVEN a selector with no run log WHEN `events` runs THEN it exits 2 and nothing is created

### EVT-B3 Follow from an offset

WHEN `events auth-fix --since 500 --follow` runs while the run writes records 501 to 640 and exits 3 THE engine SHALL print exactly 501 to 640 and exit 0 once the lock is free.

- GIVEN records 501 to 640 then exit 3 WHEN followed from 500 THEN exactly those records print and the verb exits 0

### EVT-B23 In-process observers

WHEN the operator config's `observe.observers` names in-process observers (exporters such as [TEL](telemetry-export.spec.md) and sinks such as [CST](central-run-stats.spec.md)), each getting every run-log record and every activity line after it is written THE engine SHALL load only the named ones from the observers entry-point group, run each on its own thread behind a bounded queue of 1 000 items, drop and count when the queue is full, warn at preflight and record it when a named observer is not installed and still start the run, and enable none by default ([RST](run-settings-and-overrides.spec.md)).

- GIVEN a config naming an observer that is not installed WHEN preflighted THEN a warning is recorded and the run starts

### EVT-B5 Observer failure is contained

WHEN an in-process observer raises THE engine SHALL disable it for the segment, have the run's own writer write one `engine_error` record of scope `observer` at its next record, and leave the run's exit code unchanged.

- GIVEN an observer that raises on its third record WHEN the run continues THEN one `engine_error` of scope `observer` is written and the exit code is unchanged

### EVT-B24 Lifecycle hook events

WHEN a run-log record is written and lifecycle hooks are registered ([HOK](lifecycle-hooks.spec.md)) THE engine SHALL read the hook event off the record (`run_started` of segment 0 is `started`, of a later segment `resumed`; `unit_entered`; `gate` is `gate_verdict`; `pause` is `paused`; `stop_requested`; `run_exit` with code 0 `finished`, with 3 nothing, with any other `failed`; and `stalled`), start the hook detached and ticketed, and give it a facts file of the record's ids, enums and numbers only: event, workflow, thread, `seq`, `ts`, `segment`, unit, item, attempt, token, verdict, route target, pause kind, exit code and reason; orchestration events are [ORC](orchestration.spec.md)'s and schedule events [SCH](schedules.spec.md)'s.

- GIVEN a `run_exit` with code 3 WHEN hooks are read off it THEN no hook event fires

### EVT-B25 Write failures never change a run

WHEN the activity journal cannot be written, the ledger row or the exit file cannot be written, or recording the loop's findings fails THE engine SHALL disable the journal for that session while the session and live file go on, attempt one `engine_error` record of scope `ledger` or `exit_file` ([OBS-B3](observability-and-cost.spec.md)), or write one of scope `improve` ([SIL-B1](self-improvement.spec.md)), leaving the exit code unchanged, and a reader SHALL skip an unknown kind or field (OVR-B14).

- GIVEN a full disk when the ledger row is written WHEN the run exits THEN its exit code is unchanged

## Acceptance criteria

- EVT-AC1 (EVT-B8, EVT-B10, EVT-B11, EVT-B12, EVT-B13, EVT-B14, EVT-B15, EVT-B16): A scripted-executor run writes every record kind with the common envelope, and an old reader of the run log passes the same fixture
- EVT-AC2 (EVT-B2, EVT-B9): `seq` is strictly increasing over a fixture thread with three resumes and a cut-off attempt
- EVT-AC3 (EVT-B4, EVT-B21): Each scenario of EVT-B4 is reproduced by the translator test of every executor that declares `reports_actions`
- EVT-AC4 (EVT-B21, EVT-B6, EVT-B12): The canary test of [SEC-B2](security.spec.md) finds the canary in no record kind, and finds a planted tool input only in activity journals and live files
- EVT-AC5 (EVT-B5, EVT-B23, EVT-B25): A failure injected into each observer and write path leaves the run and its exit code unchanged
- EVT-AC6 (EVT-B3, EVT-B22): `events --follow` on a live fixture run prints every record once, in order, and creates nothing
- EVT-AC7 (EVT-B1, EVT-B17, EVT-B18, EVT-B7, EVT-B19, EVT-B20): A live fixture session shows its `session_opened`, journal lines, resource lines and live file while it runs, and a 30 000-event session is capped as EVT-B7 says
- EVT-AC8 (EVT-B24): Each hook event is read off its record, and a hook's facts file holds only the listed fields

## Open questions

- Probe P-CC-7 and P-AS-4: does a `claude -p` session started by the engine keep a native transcript, and at which path, when the engine passes its isolation flags? Until run, `native` is null. Owner: executor implementer.
- Should `input_summary` for `edit` carry a changed-line count? Release 1 default: no; deferred until the monitor shows a need. Owner: monitor owner.
