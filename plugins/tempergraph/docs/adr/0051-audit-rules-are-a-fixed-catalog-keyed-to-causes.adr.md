# ADR-0051 Audit rules are a fixed engine catalog, each keyed to a measured cause and a shared cause code

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

An audit can be a list of ad hoc checks or a catalog with a stated reason for each rule. Signals without causes rank nothing: a signal nearly every run raises flags every run, and fingerprints by signal set file near-identical issues ([R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md)). The loop works by cause codes from a fixed list ([SIL-B11](../specs/16-self-improvement.spec.md)), and the proposals design ([PRP](../specs/40-improvement-proposals.spec.md)) clusters findings by side, workflow, unit and cause. Comparable auditors give every finding a stable rule id, a severity and a confidence ([R-051 P2](../research/R-051-prior-art-for-workflow-audits.rsrch.md)).

## Decision

We will define the audit's rules as a fixed, versioned engine catalog ([ARC](../specs/56-audit-rule-catalog.spec.md), [TSA](../specs/57-tool-surface-audit.spec.md)). Each rule has a stable id, one layer, one R-050 cause family, one **cause code from SIL's list** (new codes are added to that list), a default severity and confidence, a fixed remedy text and, for history rules, a minimum sample. A workflow may ignore a rule with a reason; it cannot add or change one.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Fixed catalog keyed to causes and SIL codes (chosen) | Every rule has a reason in evidence; audit and loop findings group together; ids stable for CI and ignores | New rules need an engine release |
| Workflow-defined rules | Teams extend it | The engine would run workflow code in a read-only verb; rules drift between packages; no shared ranking |
| Audit-only codes | Independent of SIL | A static finding and the friction finding of the same defect never meet; the backlog counts one defect twice |

## Decision rationale

| Criterion | Fixed, keyed | Workflow-defined | Audit-only codes |
|---|---|---|---|
| Joins the improvement loop | yes | no | no |
| Stable ids for CI and ignores | yes | partly | yes |
| Each rule justified by evidence | yes | no | yes |
| Extensible without a release | no | yes | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| B1 | SIL's cause list may grow by the codes ARC and TSA mark *new*; SIL keeps classing each as fault, infra or designed. | SIL-B11 |
| B2 | Thresholds are defaults chosen without fitted data; they are named parameters so the loop's parameter record ([IMD](../specs/43-improvement-data.spec.md)) can hold them later. | ARC-B6 |

## Consequences

- Positive: a finding can be traced to the run evidence that justified its rule; the improvement backlog ([PRP](../specs/40-improvement-proposals.spec.md)) can show "audit predicted this" next to friction findings.
- Negative: SIL's cause list grows; reviewers of SIL must accept the new codes.
- Risk: the catalog grows into noise. Mitigation: a rule is added only with an R-050 style finding behind it, and the default view hides `low` confidence and `info`.

## Revisit when

A team needs a rule the catalog does not have, or a rule fires falsely on more than a third of the workflows it is run on.
