---
title: Judge and verdict
type: component
status: ready-for-implementation
prefix: JDG
adrs: [0005, 0013, 0021, 0074, 0076]
---

# Judge and verdict

## 1. Overview

Every model step is graded by a fresh, read-only judge session that reports a finding per criterion. The engine, never the judge, derives the verdict by rule. A deterministic check runs first and can end the attempt with no model call. A judging failure never passes. This spec owns contract C4; [PRM](04-prompt-rendering.spec.md) and [GRD](06-independence-guard.spec.md) uphold it.

## 2. Contract

```python
def judge_node(unit: UnitSpec, state: RunState) -> JudgeOutcome: ...
def derive(judgement: Judgement | None, gate: GateSpec, check: CheckResult) -> Verdict: ...
class JudgeOutcome: verdict: Verdict; judgement: Judgement | None; blockers: list[Blocker]
                    gap: bool; confidence: float; confidence_source: str; judge_executor: str
```

### 2.1 Judge prompt

Rendered by an engine-owned brief that names no workflow, then the workflow's stance and brief:

| Part | Content |
|---|---|
| Engine brief | The reviewer's role and three fixed rules: the step's account is a claim to verify; only the tools given may be called, since a call to any other tool voids the whole review ([GRD](06-independence-guard.spec.md)); each criterion is graded on its own, so what could not be confirmed for one does not lower another. The last two were added after live judge sessions tried a shell for git and lowered one criterion for another's missing evidence |
| Workspace facts | Branch, base, changed files, diff stat, computed by the engine |
| References | The request (whole up to 32,000 chars, else head and tail around a marker with the omitted count) and earlier artifacts |
| Subject | The artifacts graded, the check's evidence and its findings ([CHK §2.4](75-check-contract-and-command-runs.spec.md)) |
| Step account | The step's final text, labelled "claims to verify, not facts", ≤ 8,000 chars |
| Feedback | A person's one-time feedback and every active ruling that applies to the unit, as direction that wins over a reference; each ruling adds one engine blocker, the output follows it ([RRN §2.2](81-reruns-and-feedback.spec.md)) |
| Criteria | Numbered, with id, text, check method, severity and, for an outcome criterion, its scale: what met, partial and unmet look like and the evidence met needs ([OUT §2.2.1](90-run-outcome.spec.md)); a `mechanical` criterion with the check's finding and a fixed sentence that its evidence is given; a criterion the check found `n_a` with the check's reason |
| Previous blockers | Re-checked first; the full rubric is still graded |
| Visit reason | When sent back: one engine blocker "every point of the reason is addressed" |
| Out of reach | For each artifact whose read view is absent: a fixed sentence telling the judge to report UNVERIFIABLE and not to accept the step's word |
| Answer format | The judgement block of [CON §2.8](01-contracts.spec.md); the confidence scale with its four anchors; an example line that is deliberately not valid JSON |

### 2.2 Verdict derivation

| Finding | Treated as |
|---|---|
| MET without evidence | PARTIAL |
| Not reported; N/A without a reason (a check's `n_a` message counts as the reason) | UNMET |
| Blocker UNVERIFIABLE, or `gap` true | Unresolved gap → ESCALATE |
| Blocker PARTIAL or UNMET, every one with `defect_in` naming an allowed back target (listed, and run or skipped by a route on this path) | BACK to the earliest such target |
| Blocker PARTIAL or UNMET, every one marked `no_change` and the criterion's `no_change_policy` is `escalate` | ESCALATE: a new attempt would meet the same wall, so no retry is spent |
| Blocker PARTIAL or UNMET otherwise | RETRY (budget permitting, [BUD](08-budgets-and-failures.spec.md)) |
| No failing blocker | PROCEED; unmet warnings pass once to the next step as notes |

A verdict the judge writes itself is ignored; a mismatch is only logged. Confidence never decides the verdict.

## 3. Behaviours

**JDG-B1 Check first.** Given a step that ended with a `BLOCKED:` line, or failed, or whose check returned FAIL, when the judge node runs, then no judge session starts and the outcome is set from the check or the step (FAIL → RETRY; blocked → ESCALATE with confidence placeholder 1.0, source `engine_placeholder`).

**JDG-B2 One re-ask.** Given a judge answer with no parsable judgement block, or a criterion id that does not match its number, when the judge node continues, then exactly one second session runs for the block only, fed the last 8,000 chars of the first answer; if it also fails, the judgement is unparsed: an unresolved gap with confidence 0.0, source `engine_placeholder`.

**JDG-B3 Judge on its own executor and model.** Given a step on `antigravity` with model `medium` and no judge settings, when the judge resolves, then its executor is chosen by [EXI §2.4](10-executor-interface.spec.md) and its model by the judge order of [CON §2.4](01-contracts.spec.md), so producer and judge may differ in both.

| Step executor / alias | Judge executor | Judge alias source | Judge model family |
|---|---|---|---|
| claude / `medium` | claude | step model | Claude |
| antigravity / `medium` | claude (cross-executor) | step model → tier `medium` | Claude |
| antigravity / `large`, gate judge `antigravity:gemini-pro` | antigravity (once restriction is confirmed) | gate | Gemini |
| agent-sdk / `medium` | agent-sdk | step model | Claude |
| messages-api / `small` | messages-api | the step's model | Claude |

**JDG-B4 Own timeout.** Given a judge timeout of 600 s and a step timeout of 1800 s, when the judge runs, then it gets 600 s; a judge timeout is an unparsed judgement that escalates, with a timeout row in its record.

**JDG-B5 Judge infra failure.** Given a judge session that fails with an `infra_cause`, when the judge node handles it, then it reruns the judge inside the node with backoff (10, 20, 40 s) up to the infra cap; it never pauses and never passes; when the cap is spent the run ends as an infra failure.

**JDG-B6 Mechanical criteria.** Given a criterion whose requirement is a file, heading, git fact or test result, when the workflow is authored, then it belongs in the deterministic check, and the judge reads the check's evidence rather than the step's claim. The same holds for rule-like branching written into a judge brief ("if the diff touches X, require Y"): validation warns, and the rule moves into the check or a route.

**JDG-B7 Sampled audit judge.** Given an operator audit rate of 0.1 and, optionally, an audit executor, when a gate's judge has produced a judgement, then with that probability a second judge runs on the same subject (on the audit executor if set, so a Claude judge can be audited by another model family and back), and its per-criterion agreement is recorded as an `audit_judge` record. The audit never changes the verdict, the route or a budget; its cost is logged like any judge.

**JDG-B8 No-change blocker escalates.** Given a judge RETRY whose only blocker is UNMET with `no_change = true` ("the ticket names no acceptance test"), when the verdict is derived, then it is ESCALATE, the retry budget is unchanged, and the pause payload shows the blocker.

**JDG-B9 An upstream claim is judged on its own.** Given a step that ended with `UPSTREAM draft: <defect>` on a gate that has a judge, when the judge node runs, then no check runs and one judge session grades a single engine criterion (`upstream-claim`: the defect is in `draft`'s output as claimed and the step could not work around it) with `draft`'s artifacts and values as the subject and the claim labelled as a claim. MET sends the run BACK to `draft` with the claim as the visit reason, inside the loop budget ([BUD](08-budgets-and-failures.spec.md)); PARTIAL or UNMET is a RETRY of the claiming step, told the claim was not confirmed; UNVERIFIABLE, a gap or an unparsed answer asks a person. A gate with no judge asks a person.

## 4. Error conditions

| Condition | Result |
|---|---|
| Judge executor cannot be bound | Preflight refusal (exit 2), never a run-time fallback |
| Judgement discarded by the guard | Unresolved gap, confidence 0.0, ESCALATE |
| Request longer than 32,000 chars | Cut head and tail with an exact marker; criteria in the cut part are UNVERIFIABLE, never failed |

## 5. Design notes

- A judge on a different model family than its producer is a feature, not a fallback: a model tends to rate its own kind of output well. Cross-executor judging makes that cheap ([ADR-0013](../adr/0013-cross-executor-judging.adr.md)).
- A panel of voting judges is deferred. A council ([CNL](71-council-unit.spec.md)) is a step whose combined output this spec's one judge grades; it is not a panel. Sampled audit judging (JDG-B7) is a measurement, recorded only, never routing; its agreement rates feed calibration ([LIF](18-lifecycle-and-evals.spec.md)) and the confidence-against-outcome study ([SIL](16-self-improvement.spec.md)).
- Whether a judge's grades can be trusted is measured outside this spec: a gold set per gate, the catch and clean rates, repeats and robustness variants, and the acceptance state other specs read are in [JCL](50-judge-calibration.spec.md). Acceptance never changes a verdict here. An audit judge's agreement measures consistency, not correctness, so it never counts as a gold label ([ADR-0045](../adr/0045-judges-accepted-on-labelled-error-rates.adr.md)).
- The `no_change` flag is the judge's claim; a workflow that finds it misused sets `no_change_policy: retry` on that criterion.

## 6. Acceptance criteria

- [ ] JDG-AC-1 Every row of §2.2 has a test with a scripted judge answer.
- [ ] JDG-AC-2 A failed step, a blocked step and a failed check start no judge session.
- [ ] JDG-AC-3 A missing block yields exactly one re-ask, logged as its own call with kind `judge_reask`.
- [ ] JDG-AC-4 No judging failure (timeout, parse failure, discard, infra) ever yields PROCEED.
- [ ] JDG-AC-5 Every judge record names its executor, alias, alias source and confidence source.
- [ ] JDG-AC-6 No shipped judge brief contains a sentence telling the judge to accept a step's claim (scan test).
- [ ] JDG-AC-7 An audit judge at any rate leaves every verdict, route and counter of a fixture run unchanged.
- [ ] JDG-AC-8 A confirmed upstream claim goes back with no pause, a refuted one retries the step, and an undecided one pauses (three scripted runs).

## Open questions

None.

## References

