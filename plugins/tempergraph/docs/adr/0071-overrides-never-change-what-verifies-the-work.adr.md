# ADR-0071 Overrides change cost, time, repetition and model choice, never what verifies the work

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

"All possible variations" of configuration could be read as letting an operator change anything in a workflow for one run. The engine's promise rests on a fixed verification surface: criteria a judge grades, checks the engine runs, an independent judge with a read-only view, the engine's verdict, declared flow targets (OVR-B6 to OVR-B8, [ADR-0005](0005-independent-judge-engine-verdict.adr.md)). A per-run override of any of them would let a run pass a gate its workflow would fail, invisibly to the workflow's owner and its improvement loop.

## Decision

We will make only these settable: executor and model choices, session options, limits, budgets and caps, approvals and breakpoints added, enforcement tightened, workspace mode, the audit rate, a switch's arm, workflow-declared settings, and a person's recorded tool grants that widen a step's tools or a judge's read-only views ([RST-B18, RST-B19, RST-B20, RST-B21, RST-B28, RST-B29, RST-B30](../specs/80-run-settings-and-overrides.spec.md), [ADR-0080](0080-a-person-may-grant-a-step-tools-for-a-run.adr.md)). Criteria, checks, the presence of a judge, the judge's independence and write-free view, flow and back targets and prompts are not settings; an override that names them is refused with `not_a_setting`. `approve`, `enforce_tools` and `strict_permissions` are tighten-only. Changing the verification surface is a workflow change, made in the package and reviewed.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Fixed surface, settable knobs (chosen) | A passed gate means the same thing on every run | An author wanting a quick experiment on a criterion edits the package or uses a trial ([PRP](../specs/40-improvement-proposals.spec.md)) |
| Everything overridable, recorded | Maximum flexibility | A recorded weakening is still a weakening; reports would need to discount runs |
| Overridable in `dev` mode only | Flexible locally | Two meanings of a pass across modes; the lifecycle graduates on measured runs ([ADR-0041](0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)) |

## Decision rationale

| Criterion | Fixed surface | Everything | Dev only |
|---|---|---|---|
| A pass means the same everywhere | yes | no | no |
| Measured runs comparable for the loop | yes | partly | partly |
| Quick experiments | through trials | yes | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | A model or a budget override can lower quality but cannot make a failing gate pass, because the judge and the verdict rule are unchanged. | RST |
| A2 | The owner's "all variations" means every knob of cost, time, repetition and model choice, not the gates themselves. | [R-070](../research/R-070-config-overrides-and-reruns-gaps.rsrch.md) problem statement |

## Consequences

- Positive: an override can never be the reason a defect passed a gate.
- Negative: the catalog has to say for each new field which side it is on.
- Risk: a judge model overridden to a weak one passes too much. Mitigation: judge bindings are graded per binding ([FBK](../specs/41-feedback-and-judge-reliability.spec.md)); an unaccepted binding cannot license stable mode ([JCL](../specs/50-judge-calibration.spec.md)).
