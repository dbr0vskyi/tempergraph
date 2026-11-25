# Design tempergraph as a spec-driven doc set, standalone, with recorded assumptions

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for the design of tempergraph as docs only: an overview spec, component specs, decision records and research where needed, following the spec-driven method temperspec uses. The owner was not available to answer questions. The inputs were the repository README, which names the intended capabilities, and the temperspec method. A hard requirement is support for two executors, the Claude Code CLI and the Antigravity CLI.

## Decision

We will write a self-contained design set under `plugins/tempergraph/docs/` (specs, decision records, research), shaped by the temperspec artifact rules, that designs every intended capability for two executors from the start and builds in the safeguards that agent workflows are known to need, and records every assumption in a decision record so a reviewer can overturn it.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| A. Full design of the intended capabilities, for two executors, with known safeguards built in (chosen) | Known failure modes are designed out up front; contracts are explicit; each choice has a record | A large set; some parts may be more than a first release needs |
| B. Minimal design from the README alone | Small, fast to build | Leaves out known safeguards (no self-grading, retries as edges, unmeasured never zero) until failures show the need |
| C. Wait for the owner's answers | No wrong assumption | Blocks the work; the owner asked for standalone work |

## Decision rationale

| Criterion | A | B | C |
|---|---|---|---|
| Covers the README's intended capabilities | yes | partly | — |
| Meets the two-executor requirement with evidence | yes | weakly | — |
| Risk of re-learning known failures | low | high | — |
| Can start now | yes | yes | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | tempergraph is a fresh implementation; it forks no existing code. | Whole set |
| A2 | "Antigravity CLI" means Google's `agy` terminal agent as documented at antigravity.google in November 2026. | [research `antigravity-cli-headless`](../research/antigravity-cli-headless.rsrch.md) |
| A3 | Both executors drive their CLIs as child processes; no SDK or raw model API is needed for the first release. | [ADR `executors-as-capability-adapters`](executors-as-capability-adapters.adr.md) |
| A4 | The model gateway for Claude Code may be Amazon Bedrock or the Anthropic API; binding is per machine. | [ADR `portable-model-aliases`](portable-model-aliases.adr.md) |
| A5 | The first workflow is temperspec, but the engine must not name it. | [ADR `workflows-as-data`](workflows-as-data.adr.md) |
| A6 | Workflows run on non-production, synthetic data; the engine is not hardened for production data. | [Overview](../specs/overview.spec.md) |
| A7 | Specs are left in status `review`, not `ready-for-implementation`, because no person has reviewed them. | All specs |
| A8 | The engine is Python 3.11+ and ships inside the `tempergraph` Claude Code plugin with a shim. | [LIF](../specs/lifecycle-and-evals.spec.md) |

## Consequences

- Positive: a fresh session can plan any component from one spec plus the contracts spec; every non-obvious choice has a record.
- Negative: the set is large (20 specs); some components (batch, self-improvement lenses, event waits) may be deferred by the owner.
- Risk: an assumption is wrong. Mitigation: assumptions are listed here and in the record that depends on each; specs stay in `review`.

## Revisit when

The owner reviews the set, or the first implementation plan is written.
