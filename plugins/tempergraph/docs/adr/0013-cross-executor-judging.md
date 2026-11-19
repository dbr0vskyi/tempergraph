# ADR-0013 A judge may run on another executor than its step; selection is a fixed order

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Judges must be read-only ([ADR-0010](0010-judge-isolation-per-executor.adr.md)). Antigravity cannot yet prove that, so its steps would have no judge. A judge on another model family than the producer is also widely recommended to reduce self-preference bias, and a judge that always runs on the step's executor shares its family.

## Decision

We will choose each gate's judge executor by a fixed order ([EXI §2.4](../specs/10-executor-interface.md)): operator override, the gate's named judge executor, the step's executor if it declares `restricts_judge_tools`, the workflow's designated judge executor, then the first registered executor that declares it. No candidate is a preflight refusal. `claude` is the default judge executor. The chosen executor and the reason are recorded on the judgement.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Fixed selection order, cross-executor allowed (chosen) | Antigravity steps get judges now; mixed-family judging by default | Two CLIs installed for mixed workflows |
| Judge always on the step's executor | Simple; one CLI | Antigravity steps have no judge until probes pass |
| Judge always on `claude` | Simple | No path to Gemini judges; Claude steps judged by the same family |
| Author picks per gate, no fallback | Explicit | Every gate repeats the choice; brittle when an executor changes |

## Decision rationale

| Criterion | Fixed order | Same executor | Always claude | Author only |
|---|---|---|---|---|
| Antigravity steps gated today | yes | no | yes | yes |
| Mixed-family judging possible | yes | no | partly | yes |
| Author effort | low | none | none | high |
| Deterministic and recorded | yes | yes | yes | yes |

## Consequences

- Positive: moving a step to Antigravity keeps its gate working with no other edit.
- Negative: the judge reads a workspace written by another CLI, whose instruction files and tool traces differ. Mitigation: the judge sees only the workspace, views and criteria, never the producer's transcript.
- Risk: a judge model's leniency differs by family. Mitigation: calibration sets per gate record the judge executor and model ([LIF](../specs/18-lifecycle-and-evals.md)).

## Revisit when

Calibration shows a family pairing that judges reliably worse, or Antigravity passes P-AG-1 to P-AG-3.
