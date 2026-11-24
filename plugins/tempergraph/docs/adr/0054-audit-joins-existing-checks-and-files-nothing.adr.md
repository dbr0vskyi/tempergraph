# ADR-0054 The audit joins the checks other components own and files nothing

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Several components already analyze a workflow or its runs without a model: validation and its warnings ([WFM](../specs/02-workflow-model.spec.md)), prompt lint and the judge readiness report ([LIF](../specs/18-lifecycle-and-evals.spec.md)), the cost lens's eight rules and the friction causes ([SIL](../specs/16-self-improvement.spec.md)), judge calibration ([JCL](../specs/50-judge-calibration.spec.md)), eval suites ([EVS](../specs/51-eval-suites.spec.md)) and the improvement backlog and proposals ([PRP](../specs/40-improvement-proposals.spec.md)). The coordinator asked that the audit relate to prompt checks, evals and the self-improvement loop rather than duplicate them. A tool that files on its own has a cost: duplicate issues, and a flag raised on nearly every run that ranks nothing ([R-050 N1, N2](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md)).

## Decision

We will make the audit a **reader and a joiner**:

| Component | The audit |
|---|---|
| Validation | Calls it first and shows its findings under `validate:<code>` |
| Prompt lint | Runs it and shows its findings; rules about prompt text belong there, so the audit's need for checks on human-wait instructions, accepting sentences, references to missing skills, agents, files or tools, and oversized model-facing files is met by adding them to prompt lint. What needs the host or a baseline (names resolved against the executor, the catalog and installed plugins; renamed or retired tool names; text against declarations; rendered size) is the audit's own prompt audit ([PRA](../specs/58-prompt-audit.spec.md)) |
| Readiness report, judge calibration | Shows each gate's grade and acceptance state; never scores a judge |
| Evals | Shows whether suites exist and are stale; never runs one, since a rubric run spends |
| Cost lens | Calls the same model-free rule functions over the audit's window and shows their output |
| Friction lens and proposals | Shares cause codes so findings cluster together; never files, comments or proposes |

The audit owns only rules no one else owns: host checks, timeout fit and hold-time exposure, the tool surface comparison, the host-resolved prompt rules, and loop drivers read from judgements.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Join and file nothing (chosen) | One answer per rule; no second filer; owners keep their logic | Depends on other components' outputs being callable |
| Reimplement what it needs | Self-contained | Two copies of each rule drift; the same defect reported twice in different words |
| Let the audit file issues | Findings reach the backlog without a person | A second filer files duplicate issues; static findings are predictions, not run evidence |
| Fold the audit into the self-improvement loop | One mechanism | The loop runs after runs and spends; an author needs the audit before the first run |

## Decision rationale

| Criterion | Join, no filing | Reimplement | Audit files | Fold into loop |
|---|---|---|---|---|
| One home per rule | yes | no | yes | yes |
| Useful before the first run | yes | yes | yes | no |
| No new duplicate-issue path | yes | yes | no | yes |
| Free to run | yes | yes | yes | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| J1 | The cost lens's rules are functions that can run over any window without a model. | ARC-B13 |
| J2 | Judge calibration and the proposals backlog are merged; any owner not yet built makes the rules that show it skip with `owner not present`. | ARC-B7 |
| J3 | Prompt lint (LIF) may grow the four text rules named above; its owner accepts them. | LIF-B7 to LIF-B16 |

## Consequences

- Positive: an author gets one report; each finding has one owner; the loop's backlog can show which clusters the audit predicted.
- Negative: the audit's coverage moves with its owners; a missing owner shows as skipped rules.
- Risk: an owner changes a function's output and the audit misreads it. Mitigation: owners' outputs carry schema versions and the audit reads them tolerantly (OVR-B14).

## Revisit when

The proposer workflow ([PRP](../specs/40-improvement-proposals.spec.md)) wants audit findings as input context, or `promote-check` makes an audit criterion part of graduation.
