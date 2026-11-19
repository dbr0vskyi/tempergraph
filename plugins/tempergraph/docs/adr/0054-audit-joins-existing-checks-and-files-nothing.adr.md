# ADR-0054 The audit joins the checks other components own and files nothing

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context


## Decision

We will make the audit a **reader and a joiner**:

| Component | The audit |
|---|---|
| Validation | Calls it first and shows its findings under `validate:<code>` |
| Prompt lint | Runs it and shows its findings; rules about prompt text belong there, so the audit's need for checks on human-wait instructions, accepting sentences, references to missing skills, agents, files or tools, and oversized model-facing files is met by adding them to prompt lint |
| Readiness report, judge calibration | Shows each gate's grade and acceptance state; never scores a judge |
| Evals | Shows whether suites exist and are stale; never runs one, since a rubric run spends |
| Cost lens | Calls the same model-free rule functions over the audit's window and shows their output |
| Friction lens and proposals | Shares cause codes so findings cluster together; never files, comments or proposes |

The audit owns only rules no one else owns: host checks, timeout fit and hold-time exposure, the tool surface comparison, and loop drivers read from judgements.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Join and file nothing (chosen) | One answer per rule; no second filer; owners keep their logic | Depends on other components' outputs being callable |
| Reimplement what it needs | Self-contained | Two copies of each rule drift; the same defect reported twice in different words |
| Let the audit file issues | Findings reach the backlog without a person | A second filer repeats the duplicate-issue failure; static findings are predictions, not run evidence |
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
| J2 | Judge calibration and the proposals backlog land as designed in PRs 6 and 4; until then the rules that show them are skipped with `owner not present`. | ARC §4 |
| J3 | Prompt lint (LIF) may grow the four text rules named above; its owner accepts them. | LIF §2 |

## Consequences

- Positive: an author gets one report; each finding has one owner; the loop's backlog can show which clusters the audit predicted.
- Negative: the audit's coverage moves with its owners; a missing owner shows as skipped rules.
- Risk: an owner changes a function's output and the audit misreads it. Mitigation: owners' outputs carry schema versions and the audit reads them tolerantly (contract C12).

## Revisit when

The proposer workflow of PR 4 wants audit findings as input context, or `promote-check` makes an audit criterion part of graduation.
