---
goal: Build observability and supervision — run events, the detail document, session logs and the store, reports and attention, the supervision record and improvement data, and supervision cost
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: In progress
tags: [track-plan, tempergraph, T7]
tracker: none
spec: plugins/tempergraph/docs/specs/30-run-events.spec.md
spec_commit: 0a4f06b
task_id: first-release-t7
---

# T7 Observability and supervision

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T7, built in parallel with T5 and T6 (thread "Build run events and detail view") |
| Specs | [EVT](../specs/30-run-events.spec.md), [RDD](../specs/31-run-detail-document.spec.md), [LOS](../specs/33-local-observability-store.spec.md), [OBS](../specs/15-observability-and-cost.spec.md), [SUP](../specs/86-supervision-metrics.spec.md), [IMD](../specs/43-improvement-data.spec.md), [FBK](../specs/41-feedback-and-judge-reliability.spec.md), [SCO](../specs/87-supervision-cost.spec.md) |
| Decisions | [ADR-0009](../adr/0009-normalized-session-event-stream.adr.md), [ADR-0022](../adr/0022-observers-read-files-not-sockets.adr.md), [ADR-0023](../adr/0023-local-activity-journal-with-tool-input-summaries.adr.md), [ADR-0027](../adr/0027-in-process-observers-and-wider-hook-events.adr.md), [ADR-0029](../adr/0029-own-observability-first-export-deferred.adr.md) |

**Status: Completed (offline).** T7.1 to T7.6 are built; open rows wait on records not yet written (7.4.6, 7.4.7, 7.5.6), on release 3 (7.6.8) or on the owner's machine (7.6.7, P-SUP-3). T7.1 and T7.2: every run-log record carries the EVT §2.1 envelope, sessions are announced by `session_opened`, the activity journal and live file follow EVT §2.3 with tool input summaries per §2.5, `events` reads and follows a thread, in-process observers are contained, and `status --detail` builds the RDD document read-only. Status pass: EVT and RDD are `ready-for-implementation`; EVT's two open questions have release 1 defaults (native transcript null until P-CC-7; no changed-line count on `edit`).

T7.3 is built: `logs`, `store usage|prune|export` and the session's `meta.json`; LOS records where release 1 differs (verbatim `raw.jsonl`, the check output layout, the 2 GB warning in `store usage`).

This track runs beside T5 and T6, which own the run log's writers in `run/nodes.py` and `run/runner.py`. T7 owns the `RunLog` envelope and the `LiveSink` in `run/log.py`, the readers, and the `status --detail` and `events` verbs. Records T5 and T6 still have to write are read when present and listed under each phase.

Doc changes this track made:
- EVT §2.1 says how the writer finds `segment`, that the optional keys are present and null, that a cut-off last line is ended, and that a `kind` field of §2.2 is written as `session_kind` or `pause_kind`.
- EVT §2.3 gives the journal's buffering, the cap's drop thresholds, and the live file's fields and removal at session end.
- EVT §2.5: a shell summary names a working directory only when the tool's input gives one, and the B4 table shows the scrubber's real marker, `[redacted]`.
- EVT §2.6 says where an observer's failure is recorded and what ships in release 1.
- RDD §2.1 gives the plan's edge form, the cost block, `repeat_cause` values, `scripts`, `waiting_s`, how records are placed in attempts, where evidence lines come from in release 1, and `--no-live`.
- CLI §2 lists `--unit`, `--no-live` and `events --json`.
- The release plan's feature list (§1.3, I-41 to I-46) now names the same T7 phases as its requirement table and phase headings; it had them shifted by one or two.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-24 | EVT | all; AC-5 for file observers and in-process observers | T7.1 |
| REQ-25 | RDD | all; AC-1's fixture without a map | T7.2 |
| REQ-3 | LOS | the rest of §2 after T1.4 | T7.3 |
| REQ-13 | OBS | the analysis verbs | T7.4 |
| REQ-26 | SUP, IMD, FBK | per the release plan | T7.5 |
| REQ-27 | SCO, SHL §2.2 | per the release plan | T7.6 |

## 2. Phases

✓ means built and tested; ○ means open.

### T7.1 Run events

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 7.1.1 | `run/log.py` | `RunLog` envelope: `thread_id` from the path, `segment` after the last `run_started`, null optional keys, unit and attempt from the session key, a cut-off line ended; `seq` continues (T5's `last_seq`) | EVT §2.1, B2 | yes | P1 | ✓ | 2026-11-20 |
| 7.1.2 | `run/log.py`, `run/nodes.py` (one line) | `session_sink`: `session_opened` with session id, model and transcript locator (`native` null until P-CC-7); the sink is closed after every session | EVT §2.2, §2.4, B1 | yes | P1 | ✓ | 2026-11-20 |
| 7.1.3 | `run/log.py` | `LiveSink`: buffered journal flushed at most once a second, `duration_s`, the cap with its drop order and `truncated` line, `tool_inputs` off, live file fields, live file removed at session end; a failing write turns the journal off for the session | EVT §2.3, B6, B7, §4 | yes | P1 | ✓ | 2026-11-20 |
| 7.1.4 | `executors/summary.py`, `executors/claude.py` | `capability_of` and `input_summary` per capability; the Claude Code translator fills `capability` and `input_summary` with paths relative to the session's workdir | EVT §2.5, B4, AC-3 | yes | P1 | ✓ | 2026-11-20 |
| 7.1.5 | `run/events.py` | `records`, `follow` (ends at the segment's `run_exit` with no lock, or on an orphan), `activity`, `follow_activity`, narrator lines | EVT §2.6, B3, AC-6 | yes | P1 | ✓ | 2026-11-20 |
| 7.1.6 | `run/events.py` | `RunObserver`, `register_observers` (entry points, named only, missing names reported), `ObserverHub` (thread and 1 000-item queue per observer, drop count, disable and one `engine_error`) | EVT §2.6, B5, AC-5 | yes | P1 | ✓ | 2026-11-20 |
| 7.1.7 | `cli/main.py` | `events <selector> [--since] [--follow] [--activity] [--json]`; exit 2 without a run log | EVT §2.6, §4, CLI §2 | yes | P1 | ✓ | 2026-11-20 |
| 7.1.8 | `run/log.py` | The `resources` line every 10 s from a read-only process listing of the session's process group; needs the launcher to pass `pgid` on `session_started` | EVT §2.3 | yes | P2 | ○ | |
| 7.1.9 | `run/runner.py` (T5, T6 owner) | `run_started` fields `alias`, `label`, `workflow_version`, `plan_digest`, `executors` (written by T5); still open: `cost_so_far` on `gate`, `pause`, `run_exit`; `budget`, `settings_resolved`, `grant`, `ruling`, `workspace`, `supervision` records. The readers here use each one when present | EVT §2.2 | yes | P1 | ○ | |
| 7.1.10 | `run/log.py` | Wire `observe.tool_inputs` and the `observers` list from the operator config once the settings catalog exists (T6.2) | EVT §2.5, §2.6, RST | yes | P2 | ○ | |

### T7.2 Detail document

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 7.2.1 | `observe/detail.py` | `detail`: status row, plan from the diagram model, the run log folded into visits, attempts and sessions, `repeat_cause`, cost and share, pause from the checkpoint's interrupt, budgets, health, supervision touches, `events_tail` | RDD §2.1, §2.3, B1–B3, B5, AC-1 | yes | P1 | ✓ | 2026-11-20 |
| 7.2.2 | `observe/detail.py` | Live blocks from each open session's live file when the thread holds its lock | RDD §2.2, B4 | yes | P1 | ✓ | 2026-11-20 |
| 7.2.3 | `observe/detail.py` | Scrub and clip; the 1 MB cut; `--unit`; unreadable log; stale plan | RDD §2.1, §4, AC-3, AC-4 | yes | P1 | ✓ | 2026-11-20 |
| 7.2.4 | `cli/main.py` | `status --detail [--unit] [--no-live]`; exit 2 for an unknown thread or unit | RDD §4, CLI §2 | yes | P1 | ✓ | 2026-11-20 |
| 7.2.5 | `tests/test_detail.py` | Read-only hash test and under 300 ms for a 5 000-record log | RDD-B6, AC-2 | yes | P1 | ✓ | 2026-11-20 |
| 7.2.6 | `observe/detail.py` | Per-attempt evidence and fix lines once T5 writes one judgement per attempt under `evidence/` | RDD §2.1, LOS §2.1 | yes | P2 | ○ | |
| 7.2.7 | `observe/detail.py` | Supervision level, hosts and cost from the `supervision` record (T5.1.3) and SCO's journal (T7.6) | RDD §2.1, SUP §2.5 | yes | P2 | ○ | |

### T7.3 Session logs and the store

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 7.3.1 | `run/log.py` | `meta.json` per session: written at open, completed with the session id, model and `ended_at` | LOS §2.1 | yes | P1 | ✓ | 2026-11-20 |
| 7.3.2 | `store/logs.py`, `cli/observe_cli.py` | `logs`: the file list, each kind, the engine log filtered by thread, `--follow` | LOS §2.4, AC-2 | yes | P1 | ✓ | 2026-11-20 |
| 7.3.3 | `store/logs.py`, `cli/observe_cli.py` | `store usage` with the retention flag and the 2 GB warning; `store prune` with `--older-than`, `--keep-failed`, `--dry-run`, refusing running threads | LOS §2.5, B5, §4, AC-2 | yes | P1 | ✓ | 2026-11-20 |
| 7.3.4 | `store/logs.py`, `cli/observe_cli.py` | `store export`: tar.gz, every text file scrubbed, binary files left out, never inside the state root | LOS §2.4, AC-3 | yes | P1 | ✓ | 2026-11-20 |
| 7.3.5 | `executors/launcher.py`, `run/log.py` | Capture level `observe.raw`, `observe.tool_inputs`, `observe.check_output`, recorded once per run (needs T6.2) | LOS §2.6 | yes | P2 | ○ | |

### T7.4 Reports and attention

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 7.4.1 | `observe/report.py`, `cli/observe_cli.py` | `report [window] [--by] [--json]`: cost per unit, first visit against repeats with one cause each, judges against steps, per executor and version with reported and estimated money never summed, per arm, per criterion with gate escapes, stalls and timeouts, time profile, loop signal | OBS §2.4, B2, B5, B6, AC-3, AC-5 | yes | P1 | ✓ | 2026-11-20 |
| 7.4.2 | `observe/rows.py`, `run/log.py` | The local `run` row at every `run_exit`, appended to the home `stats/<YYYY-MM>.jsonl`; the machine index at `run_started` under a lock | CST §2.1, §2.2, OBS §2.4 | yes | P1 | ✓ | 2026-11-20 |
| 7.4.3 | `observe/rows.py`, `cli/observe_cli.py` | `stats [--month\|--since] [--by] [--projection] [--json]` over the home rows: dedup by `row_id`, unknown schema counted, totals with the completeness flag, projection marked `thin` under 5 runs | CST §2.5, AC-3 | yes | P1 | ✓ | 2026-11-20 |
| 7.4.4 | `cli/main.py` | `status --all-roots`: rows of every indexed root, a gone root shown `missing` and never removed | CST §2.1 | yes | P1 | ✓ | 2026-11-20 |
| 7.4.5 | `observe/attention.py`, `cli/observe_cli.py` | `attention [--all-roots] [--json]`: every pending gate of every paused thread once, oldest first, with age, reason, decisions and the `resume` command; read-only | CLI-B6, AC-5 | yes | P1 | ✓ | 2026-11-20 |
| 7.4.6 | `observe/report.py` | Prompt digests and the diagram overlay, once `attempt_start` carries the rendered-template digest (T5) | OBS §2.4 | yes | P2 | ○ | |
| 7.4.7 | `observe/report.py` | `slow_host` timeouts and `agent_s`, once `agent_run` carries `duration_s` and the host-speed warning | OBS §2.4 | yes | P2 | ○ | |

Sinks, `stats flush|sync`, `--source`, `--live` and the heartbeat are T10.1 (`observe/sinks.py` is a stub until then).

### T7.5 Supervision record and improvement data

Split with the T5 and T6 owner: the run-path side (touch classes, the `supervision` record before every `run_exit`, the ledger's `supervision{}`; `run/supervision.py`) is theirs; the read side is here.

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 7.5.1 | `observe/rows.py`, `observe/sinks.py` | The stats and sink rows copy `touches_undesigned`, `touches_by_decider`, `agent_own_rescues`, `level`, `level_by`, `callers_unknown` from the segment's `supervision` record, the builder the ledger row uses | SUP §2.5, AC-2, CST §2.2 | yes | P1 | ✓ | 2026-11-20 |
| 7.5.2 | `observe/supervision_report.py`, `cli/observe_cli.py` | `report --supervision [window] [--by workflow\|version\|unit\|host\|level] [--json]`: runs by level and `level_by`, unattended rate with its Wilson interval, undesigned touches per run by class and decider, agent's own rescue share, relay quality, waits, cost and share with `measured k of n`, observations, data quality; eval runs left out; `thin` under 5 | SUP §2.4, B5, AC-3 (report half), AC-4, AC-5 | yes | P1 | ✓ | 2026-11-20 |
| 7.5.3 | `observe/detail.py` | The detail document's supervision block gains `level_by`, `designed_by`, the record's hosts and its cost | RDD §2.1, SUP §2.5 | yes | P1 | ✓ | 2026-11-20 |
| 7.5.4 | `observe/labels.py`, `cli/observe_cli.py` | `label <thread> <unit> --value agree\|disagree [--criterion] [--attempt]`: one `label` ledger row with IMD-R1 fields, the gate record, the judge binding and `source` from the caller's decider; no text option | FBK §2.1, §2.2 explicit, FBK-B2, FBK-AC-3, IMD-R1, IMD-R4 | yes | P1 | ✓ | 2026-11-20 |
| 7.5.5 | `tests/test_supervision_report.py` | IMD-AC-1 canary: a planted task id and feedback text reach no sink, fleet, outbox or label row | IMD-AC-1, §2.2 | yes | P1 | ✓ | 2026-11-20 |
| 7.5.6 | `observe/supervision_report.py` | Waits per pause kind, once intervention rows carry the pause kind with the wait | SUP §2.4 | yes | P3 | ○ | |

### T7.6 Supervision cost

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 7.6.1 | `observe/supervision_cost.py` | The journal: fixed entry schemas (`session`, `engine_call`, `person_turn`, `usage`, `reported`, `end`), checked before an all-or-nothing append; nothing inside `TEMPERGRAPH_SESSION_KEY` or with `observe.supervision = off` | SCO §2.2, §2.7, §4, B6, AC-5 | yes | P1 | ✓ | 2026-11-20 |
| 7.6.2 | `observe/supervision_cost.py`, `hooks/hooks.json` | The Claude Code hooks through `supervision hook <event>`: person turns with matched decision words, engine calls from the shim's commands (verb, resolved targets, output size), transcript usage by offset, `SessionEnd` then close; never raises, exit 0, 2 s timeout | SHL §2.2, SCO §2.3, PRV §2.4.1, AC-3, AC-4 | yes | P1 | ✓ | 2026-11-20 |
| 7.6.3 | `observe/supervision_cost.py` | One attribution function: categories, marginal and turn figures, `rewake`, `relay`, helpers' whole usage, `other` per session | SCO §2.4, B1, B2, B7, B8, AC-1 | yes | P1 | ✓ | 2026-11-20 |
| 7.6.4 | `observe/supervision_cost.py`, `observe/sinks.py`, `observe/rows.py` | Closing: a `supervision` ledger line per thread (a later one `replaces` it), the local row and an outbox reference; the sink row hashes thread and session ids; run from `stats flush`, after each `run_exit` and from `SessionEnd` | SCO §2.5, CST §2.2, §2.4 | yes | P1 | ✓ | 2026-11-20 |
| 7.6.5 | `cli/observe_cli.py` | `supervision hook\|log\|close\|show`; `show` is read-only | SCO §2.6, AC-2, CLI-AC-1 | yes | P1 | ✓ | 2026-11-20 |
| 7.6.6 | `observe/supervision_report.py`, `observe/detail.py` | `report --supervision` and the detail block read the closed figures: cost, share, observations | SUP §2.2, §2.4, AC-5 | yes | P1 | ✓ | 2026-11-20 |
| 7.6.7 | — | P-SUP-3 live probe of the Claude Code payloads on the owner's machine | SCO §5, AC-6 | no | P1 | ○ | |
| 7.6.8 | `observe/supervision_cost.py` | `measured_zero` and orchestration splits, once orchestrations exist (release 3); the status line's `reported` cross-check | SCO §2.3, B3 | yes | P3 | ○ | |

Deviations, recorded in SCO §5: the hook reads `tool_response.stdout` and `stderr` only for their size and a printed `thread_id` or `call_id`; `relay` counts messages; `duration_s` of an engine call is null (the hook payload has no duration); journals are not pruned at 90 days yet (LOS prune does not know them).

## 3. Hand-off notes

- **Status row fields handed over by T6:** `settings_digest`, `overridden_keys` and `settings_stale` (RST §2.7; T6 row 6.2.5) and `rerun_of` and `reruns` (RRN §2.4, from `run.meta.rerun_of` and the source's `lineage.json`) are filled in `durability/status.py`; `tests/test_reports.py` holds their tests.
- **Seen while testing, fixed by T5:** after a trip back from `review` to `draft`, the next `review` attempt used to write no `unit_entered` record and keep visit 1, and a trip back wrote `entered_from` as the bare unit name. T5 now opens a new visit entered by `proceed` and writes `back:<unit>`; `tests/test_detail.py` holds the corrected document (RDD-B3 for both units). The reader still maps a bare unit name to `back:<unit>` for logs written before the fix.
- The monitor mod's fixtures (`plugins/tempergraph-monitor/tests/fixtures/`) are written from this track's documents by `make_fixtures.py`; `test_monitor_fixtures_match_the_engine` fails when the engine's document shape moves away from them. The monitor's own build is the [T10 plan](t10-monitor.plan.md).
- `status --detail` reads the run's evidence lines from the checkpoint, so they are local only and never in a published document ([SEC §2.3](../specs/14-security.spec.md)).

## 4. Verification

From `plugins/tempergraph/engine/`: `python -m pytest`, `ruff check src tests` and `mypy` are clean. No test calls a model. `tests/test_events.py`, `tests/test_detail.py`, `tests/test_store.py` and `tests/test_reports.py`, `tests/test_sinks.py`, `tests/test_supervision_report.py` and `tests/test_supervision_cost.py` hold this track's tests.
