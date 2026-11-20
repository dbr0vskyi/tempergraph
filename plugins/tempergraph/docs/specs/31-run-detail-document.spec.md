---
title: Run detail document
type: component
status: review
prefix: RDD
adrs: [0022, 0023]
---

# Run detail document

## 1. Overview


## 2. Contract

```python
def detail(selector: Selector, unit: str | None = None, with_live: bool = True) -> DetailDocument: ...
```

### 2.1 Document (schema version 1)

| Block | Fields |
|---|---|
| `schema_version`, `generated_at` | |
| `run` | Every field of the status document row for the thread, plus `segment`, `last_seq`, `run_dir` (local path), `plan_digest` |
| `plan` | Units in graph order: `name`, `kind` (`step`, `map`, `fork`, `join`, `switch`, `human`, `sub_workflow`, `finalizer`), `gated`, declared executor and judge executor, alias, `edges` (targets with the verdict or arm that takes them), `items` count for map and fork |
| `units[]` | Per unit: `state` (`not_reached`, `running`, `passed`, `failed`, `paused`, `skipped`), `visits[]`, `cost` (reported, estimated, flag), `duration_s`, `share` (fraction of the run's estimated cost) |
| `visits[]` | `visit`, `entered_from`, `attempts[]` |
| `attempts[]` | `attempt`, `item`, `started_at`, `ended_at`, `step` (session), `check` (result, duration, `output_path`, clipped evidence), `judge` (session, verdict inputs: per-criterion `{n, id, status}`, `met`, `total`, `blockers` with clipped evidence and fix from the local evidence file, `confidence` and source), `gate` (verdict, route target, guard status), `repeat_cause` |
| `sessions[]` (inside step and judge) | `session_key`, `kind`, executor, alias, model, `session_id`, `transcript`, `activity_path`, `live_path`, `usage`, `tool_calls` count, `outcome` (`ok`, `timed_out`, `stalled`, `partial`, `infra_cause`, `error_kind`), and when live, `live` (§2.2) |
| `pause` | When paused: kind, `question`, artifact keys with local paths, decision words, exact resume commands, `waiting_since` |
| `budgets` | Each counter: used, limit; run cost cap and what is left of it |
| `health` | §2.3 |
| `events_tail` | The last 20 run-log records of kinds `unit_entered`, `check`, `gate`, `route`, `pause`, `human`, `budget`, `stop_requested`, rendered as one line each (the "narrator" lines of a monitor) |

Text fields are scrubbed and clipped to 200 characters; evidence and fix lines are clipped to 400. Paths are local. A document larger than 1 MB is cut by dropping `events_tail`, then attempt detail of passed units, and says so in `truncated`; `--unit <name>` returns one unit in full.

### 2.2 Live block of a running session

Read from the live progress file and the activity journal ([EVT §2.3](30-run-events.spec.md)) when `with_live`:

| Field | Meaning |
|---|---|
| `open_tool` | name, capability, `input_summary`, elapsed seconds |
| `recent[]` | Last 10 finished tool calls: name, `input_summary`, `ok`, `duration_s` |
| `last_text` | Last text line, scrubbed, clipped |
| `tokens_so_far`, `turns_so_far` | From the stream, null if not reported yet |
| `pgid` | Process group id (POSIX), for a read-only process listing by an observer |
| `last_event_age_s` | Seconds since the session's last normalized event |

### 2.3 Health

| Field | Rule |
|---|---|
| `alive` | From the lock probe ([DUR](09-durability-and-resume.spec.md)) |
| `silent_s` | Seconds since the newest run-log record or activity line of the segment |
| `suspect_stall` | `alive` and the open session's `last_event_age_s` ≥ 80 % of its idle limit |
| `orphaned` | Not `alive`, state `running` in the checkpoint's last view, and no `run_exit` for the segment: the process died |
| `waiting_for_person_s` | Seconds since the open `pause` record |
| `burn_usd_per_h` | Estimated cost of the segment divided by its wall time |
| `cap_eta_min` | Minutes until the run cost cap at the current burn, null without a cap |

## 3. Behaviours

**RDD-B1 Plan before any run.** Given a thread that has reached unit 2 of 5, when the detail is built, then `plan` lists all five units in graph order and units 3 to 5 are `not_reached`.

**RDD-B2 Retry history.** Given a unit whose first attempt was sent back by its judge and whose second passed, when the detail is built, then that unit has one visit with two attempts: the first with gate `RETRY`, its blockers and `repeat_cause = blocker:<id>`, the second with gate `PROCEED`.

| Attempt | Check | Judge met/total | Blockers | Gate |
|---|---|---|---|---|
| 1 | PASS | 4/6 | c3, c5 | RETRY |
| 2 | PASS | 6/6 | — | PROCEED |

**RDD-B3 Trip back.** Given a gate that routed `back:plan` from `code`, when the detail is built, then `plan` has a second visit with `entered_from = back:code`, and `code`'s first visit ends with gate `BACK` and route target `plan`.

**RDD-B4 Live session.** Given a running judge session whose open tool is `Grep` for 12 s, when the detail is built with live data, then the judge's session has `live.open_tool = {name: Grep, capability: search, elapsed: 12}` and `recent` holds up to ten earlier calls.

**RDD-B5 Orphan.** Given a thread whose process was killed by the host without a `run_exit`, when the detail is built, then `health.orphaned` is true and `pause` is absent; the resume command the status document shows applies ([DUR-B2](09-durability-and-resume.spec.md)).

**RDD-B6 Read-only.** Given a live run, when the detail is built 100 times, then the state root's file hashes and sizes are those the run itself wrote, and the run's timing records show no wait on the reader.

## 4. Error conditions

| Condition | Result |
|---|---|
| Run log unreadable or missing | `units` empty, `truncated = run_log_unreadable`; exit 0 with the status fields still filled |
| Diagram model digest differs from the run's `plan_digest` | `plan` built from the run's own records, `plan_stale = true` |
| Live file mid-replace | The previous complete read is used; never a partial JSON |
| Unknown thread | Exit 2 |

## 5. Design notes

- Built on demand rather than stored, so it never disagrees with the run log and the reader needs no write ([ADR-0022](../adr/0022-observers-read-files-not-sockets.adr.md)).
- Evidence and fix texts come from the local evidence file and appear only in this local document, never in a published one ([SEC §2.3](14-security.spec.md)).
- `health` fields are hints for a person, not decisions: nothing in the engine acts on them.
- The newer unit kinds add no new section: scripts are attempts with no session, council members and chairs are sessions of the step with their round, contest slots are items, and an ask's questions are the pause's payload ([SCR](70-script-units-and-hybrid-steps.spec.md), [CNL](71-council-unit.spec.md), [CTS](72-contest-unit.spec.md), [ASK](73-ask-unit.spec.md)).

## 6. Acceptance criteria

- [ ] RDD-AC-1 A fixture run with a retry, a trip back, a map of three items and a pause reproduces a hand-written expected document.
- [ ] RDD-AC-2 Building the detail leaves the state root unchanged (hash test) and takes under 300 ms for a 5 000-record run log on the reference machine.
- [ ] RDD-AC-3 Every text field is scrubbed (canary test) and within its clip length.
- [ ] RDD-AC-4 The 1 MB cut drops blocks in the order of §2.1 and says so.

## Open questions

None.

## References

