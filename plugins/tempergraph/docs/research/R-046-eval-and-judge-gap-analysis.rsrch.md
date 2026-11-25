# R-046 Evals and judges: what is measured, what is missing

## Problem statement

The owner raised a concern that "no one grades the judges". Every gate rests on a judge, and a gate that rejects work shows only that its judge is not a rubber stamp, not that each rejection was right; a confidence value that clusters on one anchor carries little information. This note lists every way this design measures judges and evaluates prompts, steps and workflows, and names each gap with a resolution grounded in public practice ([R-045](R-045-evaluating-llm-judges-public-practice.rsrch.md)). It also checks the work of two parallel threads that touch the same ground, so the resolutions here add to theirs instead of repeating them.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| This design on `main` | Specs | [JDG](../specs/judge-and-verdict.spec.md), [LIF](../specs/lifecycle-and-evals.spec.md), [SIL](../specs/self-improvement.spec.md), [OBS](../specs/observability-and-cost.spec.md), [SSN-B8, SSN-B9, SSN-B10](../specs/session-contract.spec.md), [R-006](R-006-planned-work-coverage.rsrch.md) |
| Design gap review, R-011 (gap G7, judge acceptance bar) | Research note, merged with pull request 3 | [R-011](R-011-design-gap-review.rsrch.md) |
| Self-improvement design: specs `improvement-proposals` PRP (proposals, case sets, paired trials) and `feedback-and-judge-reliability` FBK (feedback labels and judge reliability), ADR-0034 | Parallel thread, pull request 4, unmerged | `specs/40-…`, `specs/41-…` on that branch |
| Public practice | Research note | [R-045](R-045-evaluating-llm-judges-public-practice.rsrch.md) |

All read on 2026-11-19. Specs of pull request 4 are named in text rather than linked, because the links resolve only once those pull requests merge.

## Key findings

### What exists today

| Concern | This design (`main`) | Parallel threads |
|---|---|---|
| Judge calibration cases | Rubric scenarios bound to digests; readiness report counts cases ([LIF](../specs/lifecycle-and-evals.spec.md)) | — |
| Scoring a judge live | `evals score <gate> --executor` per executor and alias; no repeat count | — |
| What "a judge passes" means | Not defined | R-011 G7: proposes example floors (20 cases, agreement 0.85, false pass 0.05) |
| Second judge | `audit_judge`, recorded only (JDG-B7) | FBK: audit agreement below 0.8 marks a judge unreliable; counted apart from labels |
| Labels from people and facts | Harvest verb (LIF) | FBK: one label record from approvals, pull request state, re-runs, pushback, explicit labels; per-binding grades `reliable`, `unmeasured`, `unreliable`; a labelling queue; a binding-shift watch |
| Confidence | Anchors in [SSN-B8, SSN-B9, SSN-B10](../specs/session-contract.spec.md) | FBK: false-pass rate per anchor |
| Prompt checks without a model | Prompt lint in `validate` | — |
| Per-criterion and per-prompt rates | [OBS-B15](../specs/observability-and-cost.spec.md): per-criterion rates, gate escapes, prompt digests | — |
| Workflow-version comparison | `evals replay`: judges only over kept subjects | PRP: reviewed case sets, paired trials, A/A noise floor, sign test |
| Skill evals | Named in R-150 LIF | — |

### Gaps

Severity: **high** means a gate, a report or the loop rests on an unmeasured judge with no rule that stops it; **medium** means a figure is produced but can mislead; **low** means bookkeeping.

| # | Gap | Evidence | Severity | Resolution | Where | Confidence |
|---|---|---|---|---|---|---|
| E1 | **No figure defines judge quality.** A "score" exists, but nothing says what is computed from it. | LIF-B7 to LIF-B16 "last score" | high | Define per gate and judge binding: catch rate on known-bad findings, clean-pass rate on known-good findings, each with a Wilson 95% lower bound, and the flip rate under repeats ([R-045 F1, F5, F11](R-045-evaluating-llm-judges-public-practice.rsrch.md)) | [JCL](../specs/judge-calibration.spec.md), [ADR-0045](../adr/0045-judges-accepted-on-labelled-error-rates.adr.md) | confirmed |
| E2 | **No acceptance bar** (R-011 G7). `ready` and stable mode have no number behind them. | LIF-B6; R-011 G7 | high | A bar on lower bounds, so a small set can pass only with near-zero misses and a larger set tolerates proportionally more; defaults recorded as assumptions | JCL-B16, ADR-0045 | confirmed |
| E3 | **Production labels can call a judge reliable without any known-bad evidence.** FBK grades `reliable` from 20 labels and a false-pass ceiling; if people accept every result, the false-pass rate is 0. A person sees only what reaches a pause, so false fails are observed only when a person overrides, and an accepted approval is a weak label. Judges are known to be agreeable ([R-045 F2](R-045-evaluating-llm-judges-public-practice.rsrch.md)). | FBK-B11, FBK-B12 (pull request 4) | high | A gate's judge is **accepted** only when its offline bar on a class-balanced gold set is met **and** its production grade is not `unreliable`. Proposed to the self-improvement thread: FBK's `reliable` also requires the JCL bar | JCL-B17, ADR-0045 | inferred |
| E4 | **Calibration sets can be small, synthetic and unbalanced.** No rule on class balance, per-criterion coverage or provenance. | LIF's readiness report counts cases only | high | A case-set rule: minimum known-bad findings per gate, every blocker criterion covered by at least one known-bad case, provenance per case (`synthetic`, `harvested`, `expert`), and a cap on the synthetic share that counts toward the bar | JCL-B9, JCL-B10 | confirmed |
| E5 | **Repeat consistency is not measured.** `evals score` has no repeat count. Sampling settings are not recorded. | LIF-B7 to LIF-B16; R-011 G7 | medium | `evals score --repeat k` (default 3); flip rate per criterion; sampling settings recorded where the executor exposes them | JCL-B14 | confirmed |
| E6 | **No bias or robustness tests.** Self-preference, verbosity and persuasion are known; the "claims, not facts" label and cross-family judging are mitigations whose effect is unmeasured. | [R-045 F6, F7](R-045-evaluating-llm-judges-public-practice.rsrch.md) | medium | Metamorphic variants generated from gold cases: a persuasive step account, padded output, reordered criteria, a same-family producer; a variant must leave every blocker status unchanged | JCL-B13, [ADR-0047](../adr/0047-judge-robustness-by-metamorphic-variants.adr.md) | supported |
| E7 | **No tuning and held-out split.** The authoring skill fixes a brief against the same cases that then score it. | [R-045 F14](R-045-evaluating-llm-judges-public-practice.rsrch.md) | medium | Each case is `tune` or `holdout`; a case read while a brief was edited becomes `tune`; the bar is computed on `holdout` only | JCL-B9, JCL-B10, [ADR-0046](../adr/0046-calibration-cases-split-tune-and-holdout.adr.md) | inferred |
| E8 | **A score does not go stale when the judge's model changes.** LIF-B5 makes a score stale on a brief change only; an alias rebound to a new model, or an executor update, keeps the old score. | LIF-B5; FBK binding (production only) | high | A score is bound to the same binding fields as FBK labels (executor, version, alias, model slug, brief and criteria digests); any change makes it stale | JCL-B14 | confirmed |
| E9 | **Confidence calibration is unmeasured offline.** The anchors' adherence target (95% of values on anchors) and per-anchor error have no eval. | Anchors in SSN-B8 to SSN-B10, read by no eval | low | The score reports anchor adherence and error per anchor on gold cases; production per-anchor rates stay in FBK | JCL-B14 | confirmed |
| E10 | **Judge-graded rates are reported raw.** Per-criterion pass rates, the quality lens and trial targets read the judge's grade as truth. | OBS-B15; PRP targets (pull request 4) | medium | Every judge-graded rate in a report is shown with the corrected estimate from the judge's measured rates, or flagged `uncorrected` when the judge is not accepted ([R-045 F4](R-045-evaluating-llm-judges-public-practice.rsrch.md)) | [EVS-B15](../specs/eval-suites.spec.md), [ADR-0048](../adr/0048-judge-graded-rates-carry-the-judges-error.adr.md) | supported |
| E11 | **Filing licensed by a score that merely exists.** SIL-B7 files outcome issues once "a calibration score exists". | SIL-B12 to SIL-B16, SIL-B7 | high | "Calibration score" in SIL-B7 means an accepted score under JCL; the self-improvement judges are graded like any gate | JCL-B17 | confirmed |
| E12 | **Deterministic checks are never evaluated.** A check with a false fail burns retries (a check that trips on Windows line endings); one with a false pass skips nothing but misleads the judge, who is told to trust check evidence. | A check is code with no tests of its own | medium | Check suites: must-pass and must-fail fixtures per check, model-free, in the test suite | EVS-B9, EVS-B2, EVS-B10 | confirmed |
| E13 | **Steps and prompts have no eval of their own.** Prompt quality is seen only as live gate rates. | OBS-B15 | medium | Step suites: fixed input and workspace, k trials, graded by the gate's check, an accepted judge or a person, reporting pass^k, first-attempt pass and cost | EVS-B9, EVS-B2, EVS-B10, [ADR-0049](../adr/0049-eval-graders-in-a-fixed-order-of-trust.adr.md) | supported |
| E14 | **Whole-workflow evals have no standing regression role.** PRP compares two versions; `evals replay` reruns judges only; nothing says which cases must keep passing before a release. | LIF; PRP (pull request 4) | medium | Workflow suites reuse PRP's case-set format and add the role `regression` or `capability`, with graduation; a regression case failing blocks `upgrade-check --stamp` | EVS-B12 | inferred |
| E15 | **The recursion has no floor.** Audit judges, the outcome judge and the friction judge are judges too. | SIL; JDG-B7 | medium | Every judge, built-in included, is graded on gold under JCL; a judge never supplies a gold label; recursion stops at people and facts | JCL-B9, ADR-0045 | inferred |
| E16 | **Gold labels from people are noisy and unchecked.** A person may decline good work for another reason; harvested labels become expectations unreviewed. | Harvest verb (LIF-B14) | medium | A gold label carries the criterion, the expected status and a reviewer; harvested cases stay `candidate` until reviewed; an optional second reviewer records agreement | JCL-B9, JCL-B10 | confirmed |
| E17 | **Live evals have no cost rule.** Scoring, robustness variants and step trials spend money; the standing rule bans live model calls in tests. | The standing rule against live model calls in tests | low | Live suites are opt-in verbs with a cap per run; only model-free suites run in CI | EVS-B13, EVS-B14 | confirmed |
| E18 | Skill trigger and behaviour evals are named but unscored. | R-150 LIF | low | Out of scope here: owned by the plugin shell and the plugin eval harness | — | confirmed |

## Conclusions

1. The owner's concern holds on `main`: the design has an audit judge, harvest, live scoring and a readiness report, but no definition of what a judge must score, so the gap is still open there.
2. The parallel self-improvement thread (FBK) covers labels from production and per-binding grades well. Its blind spot is the one public work warns about most: an agreeable judge looks reliable on production labels, because few bad results reach a person and accepted results are weak labels. An offline, class-balanced gold set is the complement, not a duplicate.
3. Ten gaps (E1–E8, E11, E15–E16) close in one new spec, [JCL](../specs/judge-calibration.spec.md); the eval-suite gaps (E10, E12–E14, E17) close in [EVS](../specs/eval-suites.spec.md). Five decision records hold the choices: [ADR-0045](../adr/0045-judges-accepted-on-labelled-error-rates.adr.md) to [ADR-0049](../adr/0049-eval-graders-in-a-fixed-order-of-trust.adr.md).
4. Edits to shared specs are additive: one design note in JDG, two contract rows and one behaviour in LIF, and the index rows in the overview.
5. Every threshold proposed is a default with no data behind it, and is marked as such. The first live scoring run of one shipped gate is the next piece of evidence the whole design needs.

## Open questions

| Question | Owner |
|---|---|
| Should FBK's `reliable` grade require the JCL bar (E3), or should JCL's `accepted` stay a separate, stricter state? This note proposes the former; it is the self-improvement thread's spec. | Owner, with the self-improvement thread |
| Are the default bars of JCL-B16 too strict for a first release with small gold sets? They admit a gate with 20 known-bad findings and one miss. | Owner |
