# ADR-0078 Skills are a declared tool capability, named by plugin path

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

temperspec's steps declare skills as tools: discovery uses the spec-authoring and decision-record skills, phase and code use the test-fixing skill ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T11). The engine grants exactly the tools a step declares, but the capability list ([CON-B11](../specs/contracts.spec.md)) has no skill entry, so either the skill tool is granted to every step or to none. A skill named by bare name can also load a same-named skill of another plugin ([SHL-B7, SHL-B8, SHL-B11](../specs/plugin-shell.spec.md)).

## Decision

We will add the capability `skill:<plugin>:<name>`. It is not read-only (a skill runs with the step's own tools, it adds none). Executors that host an authoring surface map it to their skill tool, scoped to that skill where the permission layer allows; `messages-api` has no mapping, so preflight refuses it; `antigravity` has none until a probe confirms its skill tool. A skill's own text is the workflow's concern: a step prompt names only a skill whose text holds no instruction to ask a person, push or wait.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| `skill:<plugin>:<name>` capability (chosen) | Grant only what is declared; plugin path stops shadowing; the audit compares grant, need and use per skill | One more row per executor tool map |
| Grant the skill tool to every step that hosts an authoring surface | No declaration | Any skill can run in any step; the tool audit cannot see need |
| A bare `skill` capability | Simple | No scope; same as above for the audit |
| Inline the skill's text into the prompt | Works on every executor | Prompts grow past size caps; two copies drift |

## Decision rationale

| Criterion | Named capability | Grant all | Bare `skill` | Inline |
|---|---|---|---|---|
| Least privilege | yes | no | no | yes |
| Shadowing by name stopped | yes | no | no | n/a |
| Portable to `messages-api` | refused before spend | silently absent | silently absent | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| K1 | Claude Code's headless permission layer can allow the skill tool; whether a per-skill rule is accepted is probe P-CC-8. Until it passes, the claude executor allows the skill tool and the after-the-fact tool record checks the skill name. | [ECC-B7](../specs/executor-claude-code.spec.md) |
| K2 | The Agent SDK exposes skills like Claude Code when the step's setting sources include the workflow plugin. | [EAS](../specs/executor-agent-sdk.spec.md) |

## Consequences

- Positive: temperspec's skill-using steps keep "grant exactly what is declared".
- Negative: one more probe on each of two executors.
- Risk: a per-skill rule is not supported and the bare tool is allowed. Mitigation: the tool record names the skill called; a call to an undeclared skill is a `denied`-class friction finding ([TSA](../specs/tool-surface-audit.spec.md)).

## Revisit when

Probes P-CC-8 and the Antigravity skill probe have run.
