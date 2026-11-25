# A stop verb with drain is the only run control an observer may ask for

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The Claude Code dynamic workflows view lets a person pause, stop and restart agents from the view ([monitor research `dynamic-workflows-view`](../../../tempergraph-monitor/docs/research/dynamic-workflows-view.rsrch.md)). A read-only monitor can offer a stop control only through an engine verb. tempergraph's rules put decisions at gates only and only a person decides a pause (C4, C6); a skip would pass a step no judge assessed. A runaway shell command or a cost burn is still a real reason to stop a run before its budget ends it.

## Decision

We will add `stop [--drain | --now]`, which writes a request file the running engine acts on through the launcher's stop contract, leaving the thread `unfinished` and resumable ([RCT](../specs/run-control.spec.md)). There is no pause, skip or restart verb. The monitor never runs `stop` itself; it fills the prompt with the command for the person to send.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Stop with drain, request file (chosen) | Covers runaway and cost cases; resumable; no gate bypass | No mid-run pause other than stop and resume |
| Stop, pause, skip, restart like the workflows view | Familiar to a workflows user | Skip and restart bypass the gate (C4); pause duplicates gate pauses |
| Signal to the process id | No new file | Unsafe with id reuse; no mode; Windows differs |
| No control; a person kills the process | Nothing to build | The attempt is cut off without a record of why; the tree may survive |

## Decision rationale

| Criterion | Stop verb | Full control set | Signal | None |
|---|---|---|---|---|
| Keeps C4 and C6 | yes | no | yes | yes |
| Resumable with records | yes | partly | partly | partly |
| Kills the whole tree | yes | yes | depends | no |
| Safe from a read-only observer | yes (person sends it) | no | no | n/a |

## Consequences

- Positive: the monitor offers a stop that a person confirms, with the same result as typing it.
- Negative: a person who wanted "pause here" uses stop and resume; the resume re-enters at the next unit (drain) or re-runs the attempt (now).
- Risk: an automated caller stops runs. Mitigation: `--as-agent` is recorded, as for resume ([HUM](../specs/gate-and-human.spec.md)).

## Assumptions

- Stopping is rare enough that one verb with two modes is enough.

## Revisit when

Operators repeatedly stop and resume at the same place, which would point to a missing gate in the workflow rather than a missing verb.
