# ADR-0015 Exit codes, not prose, are the contract with every caller

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The engine is started by people, by skills inside an agent session, by background shells and by CI. A caller must tell "a person is needed" from "stopped by a rule" from "budget spent" from "broken input" without parsing text, and a background caller must learn of a pause without polling.

## Decision

We will fix a table of exit codes ([CON-B12, CON-B13](../specs/01-contracts.spec.md)): 0 finished, 1 internal error, 2 usage or preflight refusal with nothing spent or created, 3 paused for a person, 4 stopped, 5 budget spent or infra failure, 127 engine not installed (found by the shim). The docs' table is generated from the constants with a drift test. A paused run exits 3 rather than waiting.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Fixed exit-code table (chosen) | Works for shells, skills and CI alike; no parsing | Few codes; detail lives in the status file |
| 0 or 1 plus a JSON status | Rich | Every caller parses JSON; a crash before the JSON is written is ambiguous |
| A long-running server with an API | Rich, live | A server for a local tool; background skills still need a signal |

## Decision rationale

| Criterion | Exit table | 0/1 plus JSON | Server |
|---|---|---|---|
| Caller needs no parser | yes | no | no |
| Pause learnt without polling | yes | yes | no |
| Crash distinguishable | yes | weak | yes |
| Setup | none | none | server |

## Consequences

- Positive: skills route on the code alone (3 asks the person, 5 offers a budget raise, 2 shows the refusal).
- Negative: codes cannot be renumbered once callers depend on them. Mitigation: new conditions get new codes; existing ones never change meaning.
- Risk: a library under the engine exits with its own code. Mitigation: the entry point maps every uncaught error to 1.

## Revisit when

A caller needs a distinction the table cannot express without parsing.
