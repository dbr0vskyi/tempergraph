# R-031 The self-improvement loop as designed: gaps, data needs and a trial rule

## Problem statement

[SIL](../specs/self-improvement.spec.md) designs the loop: three lenses, cause codes, de-duplication by cause, the pattern rule, executor and host sides, an `uncalibrated` state. This note checks it against the project goal ("self-improvement loop and other batteries-included features", [README](../../../../README.md)), names what is missing, states which data a complete loop needs, and fixes the statistical rule a version trial uses. It feeds [ADR-0030](../adr/0030-improvement-closes-through-measured-proposals.adr.md) to [ADR-0034](../adr/0034-paired-trial-on-a-fixed-case-set.adr.md) and specs [40](../specs/improvement-proposals.spec.md) to [43](../specs/improvement-data.spec.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| SIL, OBS, JDG, LIF, CON specs of this set | Design | [specs/](../specs/overview.spec.md) |
| Public work on self-improving systems | Survey | [R-030](R-030-self-improving-agent-systems.rsrch.md) |
| Binomial sign test, exact tail probabilities | Arithmetic | Computed here, shown below |

## Key findings

### F1 Gaps in the designed loop

| # | Gap | Evidence | Mark | Closed by |
|---|---|---|---|---|
| G1 | The loop is open after filing: no candidate change, no measurement against the same work. A drafted remedy is prose. | SIL-B12 to SIL-B16: a person decides every change, and the loop opens no pull request | `confirmed` | [PRP](../specs/improvement-proposals.spec.md) |
| G2 | No fixed case set for comparing workflow versions. LIF's `evals replay` re-runs judges only; a set of whole past runs to replay is not in the design. | LIF-B7 to LIF-B16; figures per version move with the mix of work each version ran on | `confirmed` | [PRP](../specs/improvement-proposals.spec.md) trial over a case set |
| G3 | Human ground truth is scattered (approval answers, pull-request state, re-runs, feedback, audit disagreements) and read ad hoc. Judge reliability is never computed against it, so the quality lens is deferred with no path out. | SIL-B10 quality row; JDG-B7 records agreement only | `confirmed` | [FBK](../specs/feedback-and-judge-reliability.spec.md) |
| G4 | Nothing stops a fix from weakening the gate that found the fault (drop a criterion, lower a severity, widen a check's pass). This is the gaming failure of R-030 F5. | A person check written as advice stops nothing | `inferred` | [PRP](../specs/improvement-proposals.spec.md) change classes, [ADR-0031](../adr/0031-steps-and-their-graders-change-apart.adr.md) |
| G5 | The backlog is not ranked: an issue seen in one run sits beside one seen in many, and an engine issue and a workflow issue can describe one fault. Filing selects nothing beyond de-duplication. | SIL-B2 | `inferred` | [PRP](../specs/improvement-proposals.spec.md) clusters and ranking |
| G6 | The pattern rule and the cost windows read one machine's ledger. Other developers' runs of the same workflow are invisible, so a pattern seen once on each of three machines never fires. | A ledger holds only the runs of its own machine | `supported` | [IMD](../specs/improvement-data.spec.md) requirement on the shared store |
| G7 | A change of executor, bound model or CLI version can shift quality silently; only unknown tool names are attributed (SIL-B4). | SIL-B4; LIF executor table | `inferred` | [FBK](../specs/feedback-and-judge-reliability.spec.md) drift watch |
| G8 | The loop is never measured itself: how many filed issues were fixed, closed as noise or left; how long; whether a fix held. | A one-off review of flagged runs measures the loop once, not over time | `inferred` | [IMD](../specs/improvement-data.spec.md) loop metrics |
| G9 | Learned guidance has no home but a prompt edit; there is no small, itemised place for step lessons. | R-030 F4 | `inferred` | [LSN](../specs/workflow-lessons.spec.md) |
| G10 | Thresholds are constants with no provenance; when data arrives nothing says which value was fitted on what. | Defaults set before any data exist name no source | `inferred` | [IMD](../specs/improvement-data.spec.md) parameter records |
| G11 | Engine-side faults need code changes, which C14 and the docs-only first release keep out of reach of the loop. | C14; ADR-0021 | `confirmed` | Stays an issue; see Conclusions 6 |

### F2 Data a complete loop needs

Grouped by the question it answers. "Where" says which record carries it today; "new" means a requirement in [IMD](../specs/improvement-data.spec.md).

| Question | Data | Where today |
|---|---|---|
| What happened | Unit, attempt, kind, executor, alias, model slug, CLI version, usage, timings, cause per repeat | Run log `agent_run`, `gate` ([OBS](../specs/observability-and-cost.spec.md)) |
| Why the judge decided | Per-criterion id, status, `defect_in`, `no_change`, confidence and source | `gate` record |
| What version ran | Workflow version, prompt digest per template, criterion-set digest, check digest, lessons digest | Prompt digests in OBS-B15; criterion and lessons digests **new** |
| Was the judge right | Labels from people and from later facts, joined to run, gate and criterion | **new** (FBK) |
| Does a change help | Trial results per case, per version, paired | **new** (PRP) |
| Is the loop worth it | Issue and proposal states over time | **new** (IMD) |
| Is it the same elsewhere | The above, metadata only, from every machine | **new** requirement on the shared store |

Text (request, outputs, feedback) stays in the local evidence file; every new record is names, ids, counts, digests and enums, so it can be aggregated across machines without crossing the publish boundary (C9). `inferred` from C9 and SIL-B8.

### F3 How many cases a paired trial needs

A trial runs each case on the current version (A) and the candidate (B) and scores the pair as a win, loss or tie on the target metric. Under "no difference" a non-tie is a win with probability 0.5. Exact one-sided tail probabilities of the sign test:

| Non-tied pairs n | Wins needed for p ≤ 0.05 | p at that count | p at one fewer |
|---|---|---|---|
| 6 | 6 | 0.016 | 0.109 |
| 8 | 7 | 0.035 | 0.145 |
| 10 | 9 | 0.011 | 0.055 |
| 12 | 10 | 0.019 | 0.073 |
| 16 | 12 | 0.038 | 0.105 |
| 20 | 15 | 0.021 | 0.058 |

`confirmed` (binomial arithmetic). Take a large effect, first-pass yield from 30% to 60%, as a per-case pass or fail. B alone passes with probability 0.60 × 0.70 = 0.42, A alone 0.30 × 0.40 = 0.12, so about 54% of pairs are non-tied and B wins about 78% of those. A 20-case trial then has about 11 non-tied pairs, needs 9 wins (p = 0.033), and reaches it with probability about 0.54. So even an effect this large is shown only about half the time at 20 cases, and a small prompt fix will not show on 8. A trial can confirm only large effects at an affordable size, and must say "not shown" rather than "no effect" otherwise. `inferred` (arithmetic on an assumed effect).

Model output is not deterministic, so A against A also produces wins and losses. Running the case set twice on the same version (an **A/A run**) once per case set gives its noise floor: the share of pairs that differ with no change at all. `inferred` (standard practice; not measured on this engine).

### F4 Cost of a trial

A 12-case paired trial runs the workflow 24 times, once per case on each version. For a workflow whose run costs tens of dollars that is hundreds of dollars; for a small one, tens. `inferred` (arithmetic; tempergraph has no runs). A trial is therefore an operator decision with a cap, never automatic per issue.

## Conclusions

1. The design detects well and decides nothing: G1 to G5 are the missing half of the loop, and they need no new trust in models, only records, a case set and rules.
2. Every new record is metadata only, so the shared store designed by the observability work can aggregate it across machines unchanged.
3. Trial rule: paired cases, sign test at one-sided p ≤ 0.05 on the target metric, every guard metric within its margin, and an A/A noise floor recorded for the case set; fewer than 8 non-tied pairs reports "not shown".
4. Judge grades can drive promotion only through a judge whose agreement with human labels is measured; until then trials score on deterministic checks, cost and labels alone.
5. A proposal that weakens a gate, or touches a step and its grader together, is not a proposal the loop may make.
6. Engine-side faults stay issues; the loop drafts no engine code in the first release.

## Open questions

| Question | Owner |
|---|---|
| Is one-sided p ≤ 0.05 the right bar, given that a person reviews every merge anyway? A looser bar (0.10) halves the case count at the price of more weak changes reaching review. | Owner |
| Who curates the first case set of each workflow: the author at release, or harvest from real runs only? Assumed: both, and harvested cases need a person's review. | Owner |
