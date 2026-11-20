---
title: Effort ladder and one-step model escalation
type: component
status: review
prefix: LAD
adrs: [0121, 0123]
---

# Effort ladder and one-step model escalation

## 1. Overview

A retry may run with more effort, and as a last resort on the next model tier up, **only on evidence that a stronger session is the likely fix**. Every other failure retries on the same rung or pauses, exactly as it would without a ladder ([R-120](../research/R-120-effort-ladders-and-one-step-model-escalation.rsrch.md), [R-121](../research/R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md), [ADR-0121](../adr/0121-ladders-climb-only-on-trusted-substantive-evidence.adr.md)).

This spec replaces release 1's retry-count model ladder ([BUD-B7](08-budgets-and-failures.spec.md)): from release 2, a list of aliases in a step's `model` is refused and the upgrade transform of §2.8 rewrites it. A ladder never adds an attempt, never reaches a judge, member, chair or slot, and never runs where the workflow did not declare it.

## 2. Contract

### 2.1 Declaration

| Field (on `StepSpec`, or `arm_overrides` of a switch arm, [SWM §2.3](79-measured-switches.spec.md)) | Kind | Meaning |
|---|---|---|
| `effort` | `low` \| `medium` \| `high` \| `xhigh` \| `max` | The fixed effort without a ladder; release 2 adds `xhigh` to the enum ([CON §2.6](01-contracts.spec.md)) |
| `effort_ladder` | list of 2 to 4 efforts, strictly ascending | Rung 0 is the effort of the first attempt of a visit. Excludes `effort` |
| `escalation` | `EscalationSpec`, optional | §2.4; never on by default |
| `EscalationSpec.to` | tier alias | Exactly one tier above the step's alias: `small` → `medium` or `medium` → `large` |
| `EscalationSpec.stages` | map stage → `off` \| `offer` \| `auto` | Defaults: `local-dev: offer`, `local-stable: offer`, `pipeline: off` (§2.5) |
| `EscalationSpec.effort` | effort, optional | Effort of the escalated attempt; default the ladder's top rung, else `effort` |

A step whose `model` is a qualified alias (`claude:opus`), a `large` tier, an item function ([MAP](77-map-unit.spec.md) `item_model`) or `inherit` may declare an effort ladder but no `escalation`.

### 2.2 Climbing evidence

After a failed attempt the gate classifies it ([BUD §2.2](08-budgets-and-failures.spec.md)) and then asks whether it carries **climbing evidence**. The next attempt moves one rung up only when the answer is yes; otherwise it stays on its rung.

| Evidence | Every condition must hold |
|---|---|
| `judge_blocker` | Judge verdict RETRY; the judgement was parsed (source not `engine_placeholder`); at least one unmet blocker is neither `no_change` nor attributed to an earlier unit or upstream; the judge's binding is `accepted` ([JCL §2.5](50-judge-calibration.spec.md)), or `provisional` at stage `local-dev`; no FBK grade `unreliable` for that binding; the attempt ended with a result (none of the held causes of §2.3) |
| `check_fail` | Check FAIL not marked environmental; at least one failing finding names a criterion and has `kind: substance` (a test, rule or fact the check verified, [CON §2.8](01-contracts.spec.md)); no failing finding of kind `output_contract` (a missing artifact, a value outside `choices` or `pattern`, unparsable output; the engine's own output checks always use this kind); the attempt ended with a result |

### 2.3 Held causes

| Cause of the failed attempt | Rung of the next attempt | Why |
|---|---|---|
| Timeout, stall, turn cap, session cost cap, `model` error | same | More effort runs longer and costs more |
| Any `infra_cause` | same (infra counter, BUD-B1) | The machine, not the model |
| `auth`, `refused`, `tool_access`, environmental check FAIL, `no_change` blocker | none (escalates, no retry, BUD §2.2) | No retry can fix it |
| Output-contract check failure | same | Instruction following; a prompt or check fixes it |
| Blocker attributed upstream or to an earlier unit | none (trip back or attribution, [HUM](07-gate-and-human.spec.md)) | The cause is not in this unit |
| Judge RETRY from a binding not trusted per §2.2 | same | Its RETRYs are not known to be right |
| Judge RETRY whose judgement is a placeholder | same | Nothing was judged |
| Operator pin of `effort` or `model` at any operator layer | pinned value, no ladder | The operator decided ([RST §2.3](80-run-settings-and-overrides.spec.md)) |

A person's retry, an automatic re-open, a trip back into the unit and a rewind start the visit at rung 0; a person's feedback is new information, so the cheap rung gets its chance again with it.

### 2.4 One-step model escalation

An escalated attempt runs the step on `escalation.to` at `escalation.effort`. It is considered only after a failed attempt whose evidence is `judge_blocker`, and is taken only when **every** condition holds:

| # | Condition |
|---|---|
| E1 | The step declares `escalation` and the run's stage allows it (§2.5) |
| E2 | The effort ladder is at its top rung (or the step has a fixed `effort`) on both of the last two attempts |
| E3 | The last two attempts of this visit both failed with `judge_blocker` evidence, and at least one blocker criterion id is unmet in both |
| E4 | The judge that will grade the escalated attempt has an alias at or above `escalation.to`, and that binding is `accepted` ([JRK §2.3](93-judge-model-by-risk.spec.md)) |
| E5 | The visit has a retry left; the escalated attempt spends it like any retry |
| E6 | The run's remaining cost cap covers the estimate of one attempt on `escalation.to` (the price table and the step's recorded median usage, else the cap is not checked and the condition fails) |
| E7 | Preflight bound `escalation.to` on the step's executor at run start |
| E8 | No re-arm is available for this unit under the switch arm in force ([CXR §2.5](94-complexity-routing.spec.md)): decomposing is tried before a stronger model |
| E9 | No escalated attempt has run in this visit |

When E1 to E9 hold and the stage says `auto`, the next attempt is escalated. With `offer`, the gate pauses with kind `budget` and the payload carries the evidence and the exact `resume --escalate` command next to the usual retry, back and stop choices ([HUM §2.1](07-gate-and-human.spec.md)); a resume without `--escalate` retries on the base tier. When any condition fails, the step retries on its top rung as usual, and the record names the first condition that failed.

An escalated attempt that fails ends the escalation: the gate applies `on_budget_spent` at once, even with retries left, and the payload shows both tiers' attempts. An escalated attempt that passes ends the visit as a pass; the next visit starts at the base tier and rung 0.

### 2.5 Stages

The stage of a run is read from [PRO §2.1](95-promotion-check.spec.md): `local-dev`, `local-stable` or `pipeline`.

| Stage | Effort ladder | Escalation `auto` allowed when | `offer` |
|---|---|---|---|
| `local-dev` | as declared | never: `auto` is read as `offer` | pause with the choice |
| `local-stable` | as declared | the escalation record (§2.7) for this step and workflow version has ≥ 5 escalated attempts graded by an `accepted` judge with a pass rate whose Wilson lower bound is ≥ 0.5 | pause with the choice |
| `pipeline` | only if the promotion stamp saw the ladder (PRO §2.4) | the promotion stamp covered escalated attempts of this step (PRO §2.4) and the run has a run cost cap | refused at validation: a pipeline never waits on an offer it could not make; `offer` is read as `off` |

### 2.6 Preflight and validation

| Rule | Result |
|---|---|
| A rung the executor declares it cannot apply to the bound model (`Capabilities.session_options`, [EXI](10-executor-interface.spec.md)) | Preflight refusal, exit 2; two rungs that would apply the same effort would make a climb silent |
| A rung the executor reports as `uncertain` for the bound model (no live probe yet) | Warning recorded; the rung runs and records `applied_options` |
| `escalation.to` not one tier above, or declared on a step that may not escalate (§2.1) | Validation error |
| `effort_ladder` or `escalation` on a judge, member, chair or slot scope, at any layer | Validation error |
| A list of aliases in `model` | Validation error `model-ladder-retired` with the transform of §2.8 |
| `--set` of `effort_ladder` or `escalation` at an operator layer | Refused: they are workflow data; an operator pins `effort` or `model` instead |

### 2.7 Records

Every attempt's step record gains a `ladder` object; a `ladder_decision` run-log record ([EVT §2.2](30-run-events.spec.md)) is written at every gate that chose the next attempt's rung.

| Field | Meaning |
|---|---|
| `rung`, `effort`, `alias` | What this attempt ran with |
| `source` | `declared`, `ladder:effort[<i>]`, `escalation:+1`, `operator`, `arm:<switch>.<arm>` |
| `evidence` | `judge_blocker`, `check_fail` or null, with the criterion ids, the judge binding and its state |
| `held_by` | The held cause of §2.3, or the first failed condition of §2.4 |
| `offered`, `taken_by` | For an offer: whether a person took it, with the PRV caller block |

The **escalation record** is the ledger's aggregate per (workflow version, unit): escalated attempts, their pass count, and the judge state at each. First-pass yield, cost per completed run and PRP trials report rung-0 attempts and climbed attempts apart, and a run with an escalated attempt is shown apart in per-version cost ([OBS](15-observability-and-cost.spec.md), [IMD](43-improvement-data.spec.md)).

### 2.8 Migration of a release 1 model ladder

A changelog entry of release 2 ([VER §2.3](61-version-metadata.spec.md)) detects `model` lists and transforms them by rule:

| Release 1 `model` | Release 2 |
|---|---|
| `[a]` | `model: a` |
| `[a, b]` with `b` one tier above `a` | `model: a`, `escalation: {to: b}` with default stages |
| Anything else (three or more rungs, qualified aliases, a jump of two tiers) | `model: a` and an owner item: "choose an `escalation.to`, or none" ([WUP §2.3](63-workflow-upgrade.spec.md)) |

## 3. Behaviours

**LAD-B1 Climb on trusted evidence only.** Given `effort_ladder: [medium, high, xhigh]`, retry budget 3 and an `accepted` judge, when the attempts fail as below, then they run at the efforts shown.

| Attempt | Effort | Ends with | Evidence | Next effort |
|---|---|---|---|---|
| 1 | medium | judge RETRY, blocker `c2` unmet | `judge_blocker` | high |
| 2 | high | timeout | none (held) | high |
| 3 | high | check FAIL, `pytest` failed on criterion `c4` | `check_fail` | xhigh |
| 4 | xhigh | pass | | |

**LAD-B2 An untrusted judge holds the rung.** Given the same ladder and a judge binding `below_bar`, when attempt 1 fails with a judge RETRY, then attempt 2 runs at `medium` and the record says `held_by: judge_not_trusted`.

**LAD-B3 An output-contract failure holds the rung.** Given a step whose `value` must be one of `choices`, when attempt 1 writes a value outside them, then attempt 2 runs at the same effort.

**LAD-B4 Escalation on a repeated blocker.** Given `model: medium`, `effort_ladder: [high, xhigh]`, `escalation: {to: large, stages: {local-stable: auto}}` at stage `local-stable`, a gate judge on `large` that is `accepted`, a met escalation record, retry budget 3 and cost headroom, when the attempts fail as below, then they run as shown.

| Attempt | Alias, effort | Ends with | Next attempt | Why |
|---|---|---|---|---|
| 1 | medium, high | judge RETRY, `c2` unmet | medium, xhigh | `judge_blocker` climbs the effort ladder |
| 2 | medium, xhigh | judge RETRY, `c2` unmet | medium, xhigh | E2 fails: attempt 1 was not on the top rung |
| 3 | medium, xhigh | judge RETRY, `c2` unmet | large, xhigh (`escalation:+1`) | E1 to E9 hold |
| 4 | large, xhigh | judge RETRY | gate's `on_budget_spent` | A failed escalated attempt ends the escalation |

**LAD-B5 Different blockers do not escalate.** Given LAD-B4's set-up, when the top-rung attempts fail on `c2` and then on `c5`, then E3 fails and no escalation runs.

**LAD-B6 Offer in local-dev.** Given LAD-B4's set-up at stage `local-dev`, when E1 to E9 hold, then the run pauses with kind `budget`, the payload lists `resume <thread> --escalate`, and the escalated attempt runs only after a person's resume with it; an agent's resume with `--escalate` and no relay evidence is refused with exit 2 ([PRV](85-caller-provenance.spec.md)).

**LAD-B7 Escalation waits for a re-arm.** Given a unit under switch arm `direct` with `rearm` to `planned` declared, when E1 to E7 hold, then E8 fails, no escalation runs, and the re-arm of [CXR §2.5](94-complexity-routing.spec.md) applies when the budget is spent.

**LAD-B8 Reset.** Given a visit at rung 2 that pauses, when a person resumes with `retry` and feedback, then the next attempt runs at rung 0 with the feedback.

## 4. Error conditions

| Condition | Result |
|---|---|
| A rung the executor cannot apply | Preflight exit 2 naming the step, rung and model |
| An escalated alias that preflight cannot bind | Preflight exit 2; the run never learns at the third attempt that the tier is missing |
| The cost estimate for E6 is unmeasured | E6 fails; recorded `held_by: E6_unmeasured` |
| An escalation record that cannot be read | Treated as not met; `auto` behaves as `offer` |

## 5. Design notes

- The ladder changes only the effort or model of attempts the retry budget already allows (BUD §2); budgets and the run cost cap are unchanged.
- Strictness comes from the cause table the engine already keeps, narrowed by trust: a RETRY counts only from a judge whose clean rate was measured ([R-121](../research/R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md) F3).
- Remedy order for one unit: the effort ladder, then a re-arm to a more detailed decomposition ([CXR](94-complexity-routing.spec.md)), then one model step, then a person ([ADR-0123](../adr/0123-complexity-chooses-a-decomposition-through-a-measured-switch.adr.md)).
- Judges stay fixed per attempt; a stronger producer is graded only by a judge at least as strong and calibrated there (E4). That replaces release 1's "judge on the ladder's last rung".
- The improvement loop may propose an `effort_ladder` or `escalation` as a producer `model` proposal measured by a trial ([PRP §2.3](40-improvement-proposals.spec.md)); a trial counts rung-0 and climbed attempts apart.

## 6. Acceptance criteria

- [ ] LAD-AC-1 LAD-B1 to LAD-B8 and every row of §2.3 hold offline with scripted executors and scripted judge states.
- [ ] LAD-AC-2 For every cause of BUD §2.2, a fixture shows the rung of the next attempt; only the two evidence kinds of §2.2 ever raise it.
- [ ] LAD-AC-3 No fixture produces an escalated attempt unless all of E1 to E9 hold; each condition has a fixture where it alone fails.
- [ ] LAD-AC-4 No judge, member, chair or slot session ever runs with a ladder effort or an escalated alias.
- [ ] LAD-AC-5 First-pass yield and cost per version in `report` exclude climbed attempts from the rung-0 figures.
- [ ] LAD-AC-6 The §2.8 transform rewrites each fixture of release 1 `model` lists as its table says, and V1 to V7 of the upgrade pass on the result.
- [ ] LAD-AC-7 Live: `--effort xhigh` and `--effort max` are applied on each alias of the shipped binding table (probe P-LAD-1 in the [live checks plan](../plans/live-checks.plan.md)).

## Open questions

| Question | Owner | Default |
|---|---|---|
| Is ≥ 5 escalated attempts with a lower bound ≥ 0.5 the right bar for `auto` in `local-stable`? | Owner, then data | As stated; revisit after 20 escalations |
| Should a `check_fail` with the same failing test twice at the top rung also allow escalation? | Owner | No: a repeated check failure points to an instruction or a tool ([R-121](../research/R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md) F4) |
| Does the CLI honour `xhigh` on every alias? | Live check P-LAD-1 | `uncertain`: warned, not refused |

## References

[BUD](08-budgets-and-failures.spec.md) · [RST](80-run-settings-and-overrides.spec.md) · [JCL](50-judge-calibration.spec.md) · [FBK](41-feedback-and-judge-reliability.spec.md) · [JRK](93-judge-model-by-risk.spec.md) · [CXR](94-complexity-routing.spec.md) · [PRO](95-promotion-check.spec.md) · [R-120](../research/R-120-effort-ladders-and-one-step-model-escalation.rsrch.md) · [R-121](../research/R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md)
