# ADR-0041 A workflow graduates from local runs to a pipeline by measured, model-free criteria

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner stated the intended lifecycle of a workflow on 2026-11-19. You first run it and self-improve it locally. Once it reaches a level of autonomy and quality, with fewer pauses for a person, you move it to the pipeline. The executor-agnostic design is what makes that move possible.

The design has pieces of this but no path. `improvement_mode` is `dev` or `stable`, and stable mode needs every gate graded `ready` ([LIF-B6](../specs/lifecycle-and-evals.spec.md)). The Agent SDK and Messages API executors need no interactive sign-in, so they suit CI ([SHL](../specs/plugin-shell.spec.md)). The run origin `ci` exists ([DUR-B11](../specs/durability-and-resume.spec.md)). What is missing:

- the criteria that say a workflow is ready to leave the laptop;
- a check that measures them;
- proof that the workflow behaves the same on the pipeline's executor;
- the rule for what a pause means once a person is not at the terminal;
- what happens when quality drops after the move.

[R-011 G4, G5 and G7](../research/R-011-design-gap-review.rsrch.md) are prerequisites. The extended self-improvement design (PR 4: judge reliability grades per binding and the autonomy record) supplies several of the numbers.

## Decision

We will define three **stages** for a workflow, each recorded in its package as a stamp with the measured evidence: `local-dev` (dev mode, a person at every escalation), `local-stable` (stable mode, gates `ready`) and `pipeline`.

A model-free verb `tempergraph promote-check <workflow> --to <stage> [--executor <name>] [--stamp]` reads the ledger, run logs and calibration scores and reports each criterion below as met or not, with its number. It writes a stamp only with `--stamp` and only when every criterion is met, as `upgrade-check --stamp` does. The workflow's version identity ([R-011 G5](../research/R-011-design-gap-review.rsrch.md)) is part of the stamp, so any change to the workflow voids it.

| Criterion (default; no data behind it yet) | To `local-stable` | To `pipeline` |
|---|---|---|
| Runs of this workflow version, with at least 3 distinct requests | 10 | 20 |
| First-pass yield (gates passed on the first attempt) | ≥ 0.5 | ≥ 0.7 |
| Person interventions per run (escalations and budget pauses, not approvals) | ≤ 1.0 | ≤ 0.3 |
| Gate escapes (passed at a gate, failed later or by a person) in the window | ≤ 2 | 0 |
| Judges | every gate `ready` | every gate `ready` **on the pipeline's executor and alias**, with agreement with a person's labels measured |
| Cost per run, p90 | — | under the run cost cap |
| Open engine-side or executor-side faults for this workflow | — | none |
| Portability | — | the eval scenarios pass on the target executor's stand-in, and the judges are re-scored on it ([LIF](../specs/lifecycle-and-evals.spec.md) `evals score`) |

In the pipeline:

- A run never answers its own pause. A pause still exits 3. The pipeline job ends there, and the question reaches a person through `attention` ([ADR-0040](0040-take-script-steps-attention-and-composition-from-archon.adr.md)), a hook or an adapter. The run resumes where its state lives. OVR-B8 and the rule that only a person decides a pause hold. A delegation policy stays out of scope.
- Self-improvement records are written. Filing follows the workflow's own settings, so the pipeline still feeds the loop that improved the workflow.
- After every pipeline run, `promote-check` re-reads the same criteria over a sliding window. When a criterion fails, the status row and the next `attention` listing show the workflow as **regressed** with the failing number. The engine never demotes a workflow on its own or stops a pipeline. A person decides, using the evidence.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Measured stages with a model-free check and a stamp (chosen) | The move rests on numbers the engine already records; reversible; a changed workflow must earn the stamp again | Thresholds are guesses until real runs exist |
| A person decides with no criteria | Simple | "Trust" becomes a feeling; the concept's promise of a workflow you can trust is not checked |
| Automatic promotion and demotion by the engine | No operator step | A pipeline changes under a team without a person's decision; conflicts with the tenet that a person decides |
| Same workflow, separate CI copy | Pipeline isolated | Two versions drift; the improvement loop learns on one and runs the other |

## Decision rationale

| Criterion | Measured stages | Person only | Automatic | CI copy |
|---|---|---|---|---|
| Uses the engine's own records | yes | no | yes | partly |
| A person still decides | yes | yes | no | yes |
| One workflow, no drift | yes | yes | yes | no |
| Shows when quality drops after the move | yes | no | yes | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| C1 | "The pipeline" means an unattended CI job that runs the engine CLI with the `agent-sdk` or `messages-api` executor. A hosted service may come later as another executor. | EXI, SHL |
| C2 | A pipeline job may end on a pause and leave the run resumable. Where the run state lives between jobs (a runner cache, the branch, a shared store) is not decided here. It needs the cross-machine store of the observability work (PR 7, spec `central-run-stats`) or carrying the run state on the branch. | DUR, WSP |
| C3 | The thresholds are defaults chosen without data, as every self-improvement threshold is. They are recorded as such and revisited after the first 20 runs of a real workflow. | LIF, SIL |
| C4 | Judge agreement with a person's labels comes from the feedback design of PR 4 (spec `feedback-and-judge-reliability` FBK). Until it lands, the `pipeline` stage cannot be stamped. | LIF, SIL |

## Consequences

- Positive: "a workflow you can trust" becomes a checkable claim, the executor-agnostic design earns its cost, and a team can see why a workflow is or is not ready for the pipeline.
- Negative: one more verb and a stamp, and the pipeline stage waits on judge-label agreement and a shared run-state location.
- Risk: authors tune for the numbers, for example by approving instead of escalating. Mitigation: approvals are counted apart from escalations ([HUM-B5](../specs/gate-and-human.spec.md)), agent resumes are counted apart from a person's ([HUM-B6](../specs/gate-and-human.spec.md)), and gate escapes reset the window.

## Revisit when

The first workflow reaches 20 runs of one version, or the shared run store and judge labels land.
