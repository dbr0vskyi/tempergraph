---
title: Run control
type: component
status: ready-for-implementation
prefix: RCT
adrs: [0028]
---

# Run control

## 1. Overview

The one control an observer may ask for: stop a live run. A person asks for it with the `stop` verb (typed, or filled into the prompt by the monitor and sent by the person). The verb writes a stop request; the running engine picks it up and stops through the launcher's stop contract ([EXI §2.3](10-executor-interface.spec.md)), so the thread ends resumable and nothing is lost that the engine already wrote. A stop never decides a gate: a run paused for a person is already stopped, and its decision stays theirs (contract C6).

## 2. Contract

| Verb | Does | Writes | Spends |
|---|---|---|---|
| `stop <selector> [--drain \| --now] [--caller …] [--relayed]` | Requests a stop of a live thread | one request file | no |

| Mode | Effect | Thread state after |
|---|---|---|
| `--drain` (default) | The session in flight finishes; its check, judge and gate run; no new attempt and no new unit starts | `unfinished` |
| `--now` | The stop contract runs on the open session at once: graceful stop, 10 s grace, tree kill; the attempt is recorded interrupted with its partial usage | `unfinished` |

The request file is `runs/<workflow>/<task_id>/control/stop.json` under the state root ([LOS §2.1](33-local-observability-store.spec.md)): `{schema_version, mode, requested_at, caller}`, created atomically, owner-only. The engine checks for it between records and at least once a second while a session runs, writes `stop_requested` ([EVT §2.2](30-run-events.spec.md)), removes the file, acts, and exits 4 with reason `stopped_by_request`.

## 3. Behaviours

**RCT-B1 Drain.** Given a run inside the step session of unit `code`, when `stop --drain` is requested, then `code`'s session, check, judge and gate complete, no retry attempt and no next unit starts, and the run exits 4; a resume continues where the gate routed (a retry or the next unit) with no extra charge to any budget.

**RCT-B2 Now.** Given a run whose shell tool has run for 20 minutes, when `stop --now` is requested, then within 15 s the session's process tree is gone, the attempt is recorded interrupted, and a resume runs the attempt again under the same number ([DUR-B2](09-durability-and-resume.spec.md)).

**RCT-B3 Not live.** Given a thread whose lock is not held, when `stop` runs, then it exits 2 and writes nothing; a paused thread's message names `resume` and the decision words instead.

**RCT-B4 Batch.** Given `stop` with a batch selector, when it runs, then one request per live child is written and the batch parent starts no new child.

**RCT-B5 Agent caller.** Given a `stop` from a Claude Code tool child, with or without `--as-agent`, when the request is acted on, then the `stop_requested` record carries the `Caller` with kind `agent` ([PRV §2.3](85-caller-provenance.spec.md)), so a later reader can tell a person's stop from an automated caller's.

## 4. Error conditions

| Condition | Result |
|---|---|
| A request file already exists | The stronger mode wins (`now` over `drain`); exit 0 |
| The engine dies before acting | The request file is removed by the next resume, which records it as stale |
| A request file that does not parse | Treated as `drain`, recorded |

## 5. Design notes

- A file request, not a signal: a signal to a process id is unsafe after id reuse and cannot carry a mode; the file is read by the one process holding the lock ([ADR-0028](../adr/0028-stop-verb-as-the-only-observer-control.adr.md)).
- No pause or skip verb: a skip would bypass a gate (contract C4) and a pause is a gate's to make.
- The orchestration supervisor stops its node runs with this verb ([ORC §2.8](45-orchestration.spec.md) N3); this spec owns the verb's behaviour.
- The monitor never runs this verb itself; it fills the prompt with the command and the person sends it ([monitor MAC](../../../tempergraph-monitor/docs/specs/05-actions-and-safety.spec.md)).

## 6. Acceptance criteria

- [ ] RCT-AC-1 RCT-B1 and RCT-B2 pass with scripted executors and a real process tree, on Linux and macOS.
- [ ] RCT-AC-2 No stop path leaves a session's process alive (test lists the process group).
- [ ] RCT-AC-3 A stopped thread resumes and finishes with the same budget counters as an unstopped fixture.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Windows: process groups differ; the `--now` path uses the launcher's job object. Untested. | Engine implementer | `taskkill /F /T` on the session's process tree; untested on Windows |

## References

