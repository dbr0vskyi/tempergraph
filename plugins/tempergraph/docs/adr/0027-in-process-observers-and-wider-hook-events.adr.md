# ADR-0027 Add an in-process observer interface for exporters, and widen lifecycle hook events

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked whether the engine needs "more interfaces, hooks, events" for the monitor and other plugins. Lifecycle hooks today fire on four events as detached commands with a facts file ([CLI §2.2](../specs/17-engine-cli.spec.md)). That suits a tracker integration, but an exporter that turns every record into a span would start a process per record. Contract C2 forbids anything that can change a run; contract C3 and the launch rules forbid run text on argv ([SEC](../specs/14-security.spec.md)).

## Decision

We will add a `RunObserver` protocol, loaded from the `tempergraph.observers` entry-point group and enabled by name in operator config only, that receives every run-log record and activity line after it is written, each observer on its own thread behind a bounded, dropping queue, disabled for the segment on its first exception ([EVT §2.6](../specs/30-run-events.spec.md)). We will widen lifecycle hook events to `started`, `unit_entered`, `gate_verdict`, `paused`, `resumed`, `stop_requested`, `stalled`, `finished` and `failed`, unchanged in how they run.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Observer protocol plus wider hooks (chosen) | Exporters run cheaply in process; commands keep the safe detached path | An observer is code in the engine's process |
| Hooks only, more events | One mechanism | A process per record is too slow for spans |
| Observers can veto or annotate | Policy plugins possible | Breaks C2 and C5; a gate would depend on a plugin |
| Readers tail files only | No in-process code | Exporters must run as a second process per run, and miss the run's end if killed with it |

## Decision rationale

| Criterion | Observer + hooks | Hooks only | Veto observers | Tail only |
|---|---|---|---|---|
| Cannot change a run | yes (after-write, dropping queue) | yes | no | yes |
| Cheap per record | yes | no | yes | yes |
| No run text on argv | yes | yes | yes | yes |
| Enabled only by the operator | yes | yes | yes | yes |

## Consequences

- Positive: TEL and CST are observers; a third party can ship one without an engine change.
- Negative: an observer can still use CPU or memory. Mitigation: bounded queue, drop counting, and the run's own timing records show any slowdown.
- Risk: a malicious observer package. Mitigation: nothing loads unless named in operator config; the entry point is code the operator installed, like any dependency.

## Assumptions

- The monitor itself needs neither interface: it reads files ([ADR-0022](0022-observers-read-files-not-sockets.adr.md)).

## Revisit when

A use case needs an observer to influence a run; that is a new decision against C2, not an extension of this one.
