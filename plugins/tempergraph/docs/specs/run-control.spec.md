# Run control

## Purpose

The one control an observer may ask for: stop a live run. A person asks for it with the `stop` verb, typed or filled into the prompt by the monitor and sent by the person; the orchestration supervisor stops its node runs with the same verb ([ORC-B17, ORC-B24, ORC-B26](orchestration.spec.md)). The running engine stops through the launcher's stop contract ([EXI-B2, EXI-B20, EXI-B21, EXI-B22, EXI-B23, EXI-B15](executor-interface.spec.md)), so the thread ends resumable and nothing the engine already wrote is lost. A stop never decides a gate: a run paused for a person is already stopped, and its decision stays theirs. Why a request file and no pause or skip verb: [ADR `stop-verb-as-the-only-observer-control`](../adr/stop-verb-as-the-only-observer-control.adr.md).

## Behaviours

### RCT-B6 Stop writes one request file

WHEN `stop <selector> [--drain | --now] [--caller …] [--relayed]` names a live thread THE engine CLI SHALL write the request file `runs/<workflow>/<task_id>/control/stop.json` under the state root ([LOS-B7, LOS-B8, LOS-B9](local-observability-store.spec.md)), created atomically and readable by the owner only, with the fields `schema_version`, `mode`, `requested_at` and `caller`, and spend no session.

- GIVEN a live thread WHEN `stop <task_id> --now` runs THEN the request file holds `mode` `now`, the command exits 0 and no session starts
- GIVEN a live thread WHEN `stop <task_id>` runs with no mode THEN the request file holds `mode` `drain`

### RCT-B7 The running engine acts on the request

WHEN a request file exists for the thread it runs THE engine SHALL notice it between records and at least once a second while a session runs, write `stop_requested` ([EVT-B10 to EVT-B16](run-events.spec.md)), remove the file, stop by the mode and exit 4 with reason `stopped_by_request`.

- GIVEN a session that writes no record for a minute WHEN a request file appears THEN `stop_requested` is written within 2 seconds and the file is gone
- GIVEN a stopped run WHEN its status is read THEN the thread is `unfinished` and the exit reason is `stopped_by_request`

### RCT-B1 Drain

WHEN a `drain` stop is requested THE engine SHALL let the session in flight finish with its check, judge and gate, start no new attempt and no new unit, and leave the thread `unfinished`, resumable where the gate routed with no extra charge to any budget.

- GIVEN a run inside the step session of unit `code` WHEN `stop --drain` is requested THEN `code`'s session, check, judge and gate complete, no retry attempt and no next unit starts, and the run exits 4
- GIVEN that drained thread WHEN it is resumed THEN it continues with the retry or the next unit the gate chose and every budget counter is as the gate left it

### RCT-B2 Now

WHEN a `now` stop is requested THE engine SHALL run the stop contract on the open session at once (graceful stop, 10 s grace, tree kill) and record the attempt as interrupted with its partial usage.

- GIVEN a run whose shell tool has run for 20 minutes WHEN `stop --now` is requested THEN within 15 s the session's process tree is gone and the attempt is recorded interrupted
- GIVEN that thread WHEN it is resumed THEN the interrupted attempt runs again under the same number ([DUR-B2](durability-and-resume.spec.md))

### RCT-B3 Not live

WHEN `stop` names a thread whose lock is not held THE engine CLI SHALL exit 2 and write nothing, except the hand-off of a lost runner ([SIL-B29](runs-without-a-final-exit.spec.md)).

- GIVEN a finished thread WHEN `stop` names it THEN the command exits 2 and no request file exists
- GIVEN a thread paused for a person WHEN `stop` names it THEN the message names `resume` and the decision words instead
- GIVEN a thread whose runner was killed WHEN `stop` names it THEN the command exits 2 and no request file exists

### RCT-B4 Batch

WHEN `stop` is given a batch selector THE engine CLI SHALL write one request per live child, and the batch parent SHALL start no new child.

- GIVEN a batch with two live children and three waiting WHEN `stop <batch>` runs THEN two request files are written and none of the three waiting children starts

### RCT-B5 Agent caller

WHEN a stop requested by a Claude Code tool child is acted on THE engine SHALL record the `Caller` with kind `agent` on the `stop_requested` record ([PRV-B13](caller-provenance.spec.md)), with or without `--as-agent`.

- GIVEN a `stop` run from a Claude Code tool child without `--as-agent` WHEN the engine acts on it THEN the `stop_requested` record's caller kind is `agent`

### RCT-B8 A second request keeps the stronger mode

WHEN `stop` runs while a request file already exists THE engine CLI SHALL keep the stronger mode, `now` over `drain`, and exit 0.

- GIVEN a `drain` request waiting WHEN `stop --now` runs THEN the file holds `now`
- GIVEN a `now` request waiting WHEN `stop --drain` runs THEN the file still holds `now`

### RCT-B9 A stale request is cleared

WHEN a resume finds a request file that no running engine acted on THE engine SHALL remove it and record it as stale before the run continues.

- GIVEN an engine that died after a request was written WHEN the thread is resumed THEN the file is removed, a stale request is recorded and the run is not stopped by it

### RCT-B10 An unreadable request drains

WHEN a request file does not parse THE engine SHALL act on it as a `drain` request and record that it did not parse.

- GIVEN a request file holding `{"mode":` WHEN the engine reads it THEN the run drains and the record notes the unreadable request

### RCT-B11 A thread stopped by request resumes with no decision

WHEN `resume` names a thread that stopped by request and carries no decision THE engine SHALL continue the thread, asking for no decision, from the attempt a `now` stop interrupted or, after a `drain` stop, from the attempt that was due next, as the same run would have gone on without the stop.

- GIVEN a run drained between unit `a` and unit `b` WHEN `resume` runs with no decision THEN `b` starts its first attempt, no request file exists and the run ends with the exit it would have had without the stop
- GIVEN a step session in unit `a`, whose retry budget is 1, that a `now` stop ended WHEN `resume` runs with no decision THEN that attempt runs under the number it had, the retry budget is unspent and the run ends with the exit it would have had without the stop

## Acceptance criteria

- RCT-AC1 (RCT-B1, RCT-B2): The drain and now scenarios pass with scripted executors and a real process tree, on Linux and macOS
- RCT-AC2 (RCT-B2): After every stop path, listing the session's process group finds no live process
- RCT-AC3 (RCT-B1, RCT-B2): A stopped thread resumes and finishes with the same budget counters as an unstopped fixture
- RCT-AC4 (RCT-B6): `stop` on a live thread writes the request file with the four fields, readable by the owner only
- RCT-AC5 (RCT-B3): `stop` on a thread with no held lock exits 2 and leaves no request file
- RCT-AC6 (RCT-B7, RCT-B5): An acted-on request leaves a `stop_requested` record carrying the caller's kind, no request file, and exit 4 with reason `stopped_by_request`
- RCT-AC7 (RCT-B4): A batch stop writes one request per live child, and no waiting child starts afterwards
- RCT-AC8 (RCT-B8): A `drain` request after a `now` request leaves the file holding `now`
- RCT-AC9 (RCT-B9): The next resume removes a stale request file and records it as stale
- RCT-AC10 (RCT-B10): A request file that does not parse drains the run
- RCT-AC11 (RCT-B11): For each of the modes `drain` and `now`, a plain `resume` of a fixture thread stopped by request ends with the exit the same fixture has without the stop, asks for no decision, leaves no request file, and leaves every budget counter as the unstopped fixture has it

## Open questions

- Windows: process groups differ, and the `now` path uses the launcher's job object. Until it is tested on Windows, the engine runs `taskkill /F /T` on the session's process tree. Owner: engine implementer.
