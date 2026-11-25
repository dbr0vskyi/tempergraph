# ADR-0019 Library-based executors run in an engine worker process behind the same launcher

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

OVR-B5 says executors behave the same everywhere: prompt off argv, constants-only argv, no raise, and children tied to the engine. The session launcher ([EXI-B2, EXI-B20, EXI-B21, EXI-B22, EXI-B23, EXI-B15](../specs/executor-interface.spec.md)) enforces this for CLIs: it owns the wall-clock timeout, the idle watchdog and the process-tree kill. The Agent SDK and the Messages API are Python libraries. Called inside the engine process, a hung network call or a hung tool command could not be killed with its tree, a library exception could escape, and a library's memory or thread state would live in the process that holds the graph and the checkpoint.

## Decision

We will run each library-based session in an engine **worker process**: the launcher starts the engine's own interpreter with a constant module entry point, writes a request document (prompt and engine-checked session fields) on stdin, and reads normalized events as JSON lines on stdout. The worker hosts the library, runs any tools it executes as its own children, and ends with one `result` line. Timeout, idle and tree-kill behaviour are those of every other session.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Worker process behind the launcher (chosen) | Same lifetime, timeout and kill as the CLIs; a crash cannot reach the graph; the conformance suite applies unchanged | One more process per session; the request document needs a schema |
| Call the library in the engine process, with threads and timeouts | No extra process | A hung call cannot be killed with its children; library state shares the graph's process; timeouts differ by executor |
| Async tasks in the engine's event loop | Light | Same kill problem; LangGraph nodes run synchronously in this design |

## Decision rationale

| Criterion | Worker | In process | Async |
|---|---|---|---|
| Tree kill on timeout and signal | yes | no | no |
| OVR-B5 holds unchanged | yes | partly | partly |
| Isolation of library failures | yes | no | no |
| Cost | one process per session | none | none |

## Consequences

- Positive: the launcher, idle watchdog and stop contract are written once for four executors.
- Negative: the worker's request document is a second place values are checked. Mitigation: the worker re-validates every field against the same rules (constants, shapes, paths inside the workspace), as a detached child already does with its hand-off ticket.
- Risk: the worker's normalized events drift from the engine's schema. Mitigation: the worker and the engine ship in one package and one version; the conformance suite runs the worker against recorded API and SDK responses.

## Revisit when

LangGraph nodes become asynchronous and a library offers cancellation that also ends the processes it started.
