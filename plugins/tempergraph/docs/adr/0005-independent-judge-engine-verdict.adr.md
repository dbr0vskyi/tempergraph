# ADR-0005 An independent read-only judge reports; the engine derives the verdict

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The README promises deterministic checks plus LLM-as-judge checks for what rules cannot express. A step that grades itself is not independent: well-formatted, wrong output passes, a model that believes it has finished reports everything met, and every attempt pays for a report nobody can trust.

## Decision

We will run a deterministic check first and, only when it does not fail, a fresh read-only judge session that reports a status per criterion with evidence. The engine derives the verdict by fixed rules (MET without evidence is PARTIAL; a blocker UNVERIFIABLE escalates; any judging failure is an unresolved gap). The step is shown the criteria as its target and asked for no self-report.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Check, then independent judge, verdict by rule (chosen) | Independent; cheap failures skip the judge; blockers cannot be averaged away | Two sessions per attempt |
| Producer self-grades | One session | Not independent; measured failure |
| One structured-output call with evidence pasted | Cheap | The judge cannot read the code; large diffs do not fit; outside the executor layer |
| Panel of voting judges | Reliability | N times the cost; deferred until one judge is calibrated |

## Decision rationale

| Criterion | Chosen | Self-grade | Pasted call | Panel |
|---|---|---|---|---|
| Independence | yes | no | yes | yes |
| Can read the workspace | yes | yes | no | yes |
| Cost per attempt | 2 sessions | 1 | 1 call | N+1 |
| Logged and costed like any call | yes | yes | no | yes |

## Consequences

- Positive: a pass means an independent reader found evidence for every blocker.
- Negative: judges are a large share of spend. Mitigation: mechanical criteria go to checks; narrow judges on per-item gates.
- Risk: judge reliability is unmeasured. Mitigation: calibration sets per gate; sampled double-judging later; workflows stay in dev mode until gates are ready.

## Revisit when

A reliability measurement shows a judge configuration that needs no independent session for some gate class.
