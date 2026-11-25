# A step previews its own gate's check inside its attempt through one engine command

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

When a step's output fails its deterministic check, the next attempt is a fresh session that re-reads everything. A step that writes a structured artifact, such as temperspec's expand step, can fail its check on structural misses (a missing line range, a file named whole), and each miss costs a whole new attempt. Two remedies fit: run the checks inside the attempt through a declared command, or resume the session with the failing entries ([research `temperspec-needs-against-the-engine`](../research/temperspec-needs-against-the-engine.rsrch.md) T38). A resumed retry carries the whole conversation so far, so it costs more than a fresh session told the last report ([F20](../research/claude-code-cli-headless.rsrch.md)), which is why a retry here is always fresh ([PRM-B5](../specs/prompt-rendering.spec.md)).

## Decision

We will let a step declare `self_check: true`. The engine then grants it one command, `tempergraph self-check <ticket>`, which runs the unit's own check on the current workspace and prints the findings, without a judge, a state write or a budget change, at most three times an attempt. The gate's real check still runs after the session; its command runs can reuse the preview's on an unchanged tree ([CHK-B17](../specs/check-contract-and-command-runs.spec.md)). No session is resumed.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Preview command (chosen) | Same session, no resume, no judge; executor-neutral; the check is the gate's own code | Needs a command grant; a step may game the check (it already sees criteria texts, and the judge still runs) |
| Resume the session with the failing findings | No tool needed | Dearer, as it carries the whole conversation; executor-specific (no resume on two executors); a judge-free repair loop the engine must bound |
| The workflow ships its own lint as a declared command | No engine work | A second copy of the check that drifts from the gate's |
| Nothing | Simplest | Every structural miss costs a whole attempt |

## Decision rationale

| Criterion | Preview | Resume | Own lint | Nothing |
|---|---|---|---|---|
| Works on all four executors | yes | no | yes | yes |
| Same rules as the gate | yes | yes | no | n/a |
| Extra cost per failed check | one command run | resumed context | one command run | a whole attempt |
| Judge independence | unchanged | unchanged | unchanged | unchanged |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| K1 | Structural findings (place and fix) are enough for a session to repair without the check's source. | CHK-B17 |
| K2 | A narrow allow rule for one engine command is accepted by each executor's permission layer, as for any declared prefix. | ECC, EAS, EAG, THS tool maps |

## Consequences

- Positive: a check's structural failures are repaired inside the attempt that made them, at no judge cost.
- Negative: one more prompt section and one more verb.
- Risk: a step loops on the preview. Mitigation: three calls per attempt, then exit 2; each call is a `self_check` run event the audit can count.

## Revisit when

History shows first-attempt check pass rates no better with `self_check` than without on the same workflow version.
