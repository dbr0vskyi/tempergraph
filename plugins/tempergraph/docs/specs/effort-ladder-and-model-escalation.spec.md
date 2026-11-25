# Effort ladder and one-step model escalation

## Purpose

A retry may run with more effort, and as a last resort on the next model tier up, only on evidence that a stronger session is the likely fix; every other failure retries on the same rung or pauses, as it would without a ladder ([research `effort-ladders-and-one-step-model-escalation`](../research/effort-ladders-and-one-step-model-escalation.rsrch.md), [research `judge-model-by-risk-and-evidence-for-escalation`](../research/judge-model-by-risk-and-evidence-for-escalation.rsrch.md), [ADR `ladders-climb-only-on-trusted-substantive-evidence`](../adr/ladders-climb-only-on-trusted-substantive-evidence.adr.md)). Workflow authors declare the ladder; the gate, the run records, reports and improvement trials depend on what it does. It replaces release 1's retry-count model list ([BUD-B7](budgets-and-failures.spec.md)). A ladder changes only the effort or model of attempts the retry budget already allows: it never adds an attempt, never reaches a judge, member, chair or slot, and never runs where the workflow did not declare it. The remedy order for one unit is the effort ladder, then a re-arm to a more detailed decomposition ([CXR](complexity-routing.spec.md)), then one model step, then a person ([ADR `complexity-chooses-a-decomposition-through-a-measured-switch`](../adr/complexity-chooses-a-decomposition-through-a-measured-switch.adr.md)).

## Behaviours

### LAD-B9 Declaring a ladder

WHEN a step (or the `arm_overrides` of a switch arm, [SWM-B6](measured-switches.spec.md)) declares `effort` (`low`, `medium`, `high`, `xhigh` or `max`), `effort_ladder` (2 to 4 efforts, strictly ascending, excluding `effort`) or `escalation` (`to`, `stages`, `effort`) THE engine SHALL run the first attempt of a visit at rung 0, and accept `escalation` only with `to` exactly one tier above the step's alias, stages defaulting to `local-dev: offer`, `local-stable: offer`, `pipeline: off`, and the escalated effort defaulting to the ladder's top rung, else `effort`.

- GIVEN `model: small` and `escalation: {to: medium}` WHEN the workflow is validated THEN it passes with the default stages
- GIVEN `model: small` and `escalation: {to: large}` WHEN the workflow is validated THEN it fails with `escalation-invalid`
- GIVEN `effort_ladder: [high, medium]` WHEN the workflow is validated THEN it fails with `ladder-invalid`
- GIVEN a step whose `model` is `claude:opus`, a `large` tier, an `item_model` function ([MAP](map-unit.spec.md)) or `inherit` WHEN it declares `escalation` THEN validation fails; an effort ladder alone passes

### LAD-B10 Climbing evidence

WHEN a failed attempt carries climbing evidence THE gate SHALL run the next attempt one rung up, and otherwise on the same rung; the evidence is `judge_blocker` (a parsed RETRY whose unmet blocker is neither `no_change` nor attributed upstream or to an earlier unit, from a binding `accepted` ([JCL-B17](judge-calibration.spec.md)), or `provisional` at stage `local-dev`, with no FBK grade `unreliable`, after an attempt that ended with a result) or `check_fail` (a check FAIL not marked environmental, with a failing finding that names a criterion and has `kind: substance`, none of kind `output_contract`, after an attempt that ended with a result).

- GIVEN `effort_ladder: [medium, high, xhigh]`, retry budget 3 and an `accepted` judge WHEN attempt 1 at `medium` ends with a judge RETRY on blocker `c2` THEN attempt 2 runs at `high`
- GIVEN that run WHEN attempt 2 at `high` times out THEN attempt 3 runs at `high`
- GIVEN that run WHEN attempt 3 ends with a check FAIL of `pytest` on criterion `c4` with `kind: substance` THEN attempt 4 runs at `xhigh`

### LAD-B1 Climb on trusted evidence only

WHEN the attempts of a visit fail THE gate SHALL raise the rung only on the two evidence kinds, never on any other cause ([BUD-B1, BUD-B11](budgets-and-failures.spec.md)).

- GIVEN `effort_ladder: [medium, high, xhigh]` WHEN attempts end with judge RETRY on `c2`, then a timeout, then a `check_fail` on `c4`, then a pass THEN they ran at `medium`, `high`, `high` and `xhigh`

### LAD-B2 An untrusted judge holds the rung

WHEN a judge RETRY comes from a binding not trusted for climbing THE gate SHALL keep the rung and record `held_by: judge_not_trusted`.

- GIVEN a judge binding `below_bar` WHEN attempt 1 fails with a judge RETRY THEN attempt 2 runs at `medium` with `held_by: judge_not_trusted`
- GIVEN a workflow with no calibration score WHEN its judge returns RETRY THEN the judge is `unscored` and the rung is held

### LAD-B3 An output-contract failure holds the rung

WHEN an attempt fails its output contract (a missing artifact, a value outside `choices` or `pattern`, output that does not parse) THE gate SHALL keep the rung.

- GIVEN a step whose `value` must be one of `choices` WHEN attempt 1 writes a value outside them THEN attempt 2 runs at the same effort with `held_by: output_contract`
- GIVEN the engine's own output checks and the stock check helpers WHEN they fail THEN their findings carry `kind: output_contract`

### LAD-B11 Held causes

WHEN a failed attempt ends with any other cause THE gate SHALL hold the rung, or not retry, as the cause says: timeout, stall, turn cap, session cost cap, `model` error and any `infra_cause` retry on the same rung (infra on the infra counter, BUD-B1); `auth`, `refused`, `tool_access`, an environmental check FAIL and a `no_change` blocker escalate with no retry; a blocker attributed upstream or to an earlier unit goes back ([HUM](gate-and-human.spec.md)); a placeholder judgement holds; and an operator pin of `effort` or `model` at any operator layer runs the pinned value with no ladder ([RST-B22, RST-B23](run-settings-and-overrides.spec.md)).

- GIVEN each cause WHEN it ends an attempt THEN the next attempt's record names its `held_by`, one of `timeout`, `stall`, `infra`, `turn_cap`, `cost_cap`, `model`, `cut_off`, `output_contract`, `check_no_substance`, `environmental`, `judge_not_trusted`, `judge_placeholder`, `no_substantive_blocker`, `step_failed` or `operator_pin`
- GIVEN `--set code.effort=high` WHEN a ladder step retries on `judge_blocker` THEN every attempt runs at `high`

### LAD-B8 Reset

WHEN a visit starts again by a person's retry, an automatic re-open, a trip back into the unit or a rewind THE gate SHALL start it at rung 0.

- GIVEN a visit at rung 2 that pauses WHEN a person resumes with `retry` and feedback THEN the next attempt runs at rung 0 with the feedback

### LAD-B12 Escalation conditions

WHEN an attempt fails with `judge_blocker` evidence THE gate SHALL consider one escalated attempt on `escalation.to` at `escalation.effort`, and take it only when every condition holds: E1 the step declares `escalation` and the stage allows it; E2 the last two attempts ran at the top rung (or a fixed `effort`); E3 both failed with `judge_blocker` and at least one blocker criterion is unmet in both; E4 the judge that will grade it has an alias at or above `escalation.to` and an `accepted` binding ([JRK-B8](judge-model-by-risk.spec.md)); E5 the visit has a retry left, which the attempt spends; E6 the run's remaining cost cap covers the estimate of one attempt on `escalation.to` from the price table and this visit's median usage; E7 preflight bound `escalation.to` on the step's executor; E8 no re-arm is available under the switch arm in force ([CXR-B4, CXR-B11, CXR-B7](complexity-routing.spec.md)); E9 no escalated attempt has run in this visit.

- GIVEN `model: medium`, `effort_ladder: [high, xhigh]`, `escalation: {to: large, stages: {local-stable: auto}}` at stage `local-stable`, an `accepted` gate judge on `large`, a met escalation record, retry budget 3 and cost headroom WHEN attempts 1 to 3 fail with a judge RETRY on `c2` THEN attempt 2 runs at `medium, xhigh` (climb), attempt 3 at `medium, xhigh` (E2 failed) and attempt 4 at `large, xhigh` with source `escalation:+1`
- GIVEN any one condition failing WHEN the gate decides THEN the step retries on its top rung and `escalation.held_by` names the first failed condition, `E1` to `E9`
- GIVEN an unmeasured cost estimate WHEN E6 is read THEN it fails with `held_by: E6_unmeasured`

### LAD-B5 Different blockers do not escalate

WHEN the top-rung attempts fail on different blocker criteria THE gate SHALL not escalate.

- GIVEN LAD-B12's set-up WHEN the top-rung attempts fail on `c2` and then on `c5` THEN E3 fails and no escalation runs

### LAD-B7 Escalation waits for a re-arm

WHEN a re-arm is declared for the unit under the switch arm in force THE gate SHALL apply the re-arm instead of escalating.

- GIVEN a unit under arm `direct` with `rearm` to `planned` WHEN E1 to E7 hold THEN E8 fails, no escalation runs, and the re-arm of [CXR-B4, CXR-B11, CXR-B7](complexity-routing.spec.md) applies when the budget is spent

### LAD-B4 A failed escalated attempt ends the escalation

WHEN an escalated attempt fails THE gate SHALL apply `on_budget_spent` at once, even with retries left, with reason `escalation`, and the payload shows both tiers' attempts.

- GIVEN LAD-B12's attempt 4 on `large` WHEN it ends with a judge RETRY THEN the gate pauses or stops by `on_budget_spent` and no attempt 5 runs
- GIVEN an escalated attempt that passes WHEN the next visit starts THEN it runs at the base tier and rung 0

### LAD-B6 Offer

WHEN every condition holds and the stage says `offer` THE gate SHALL pause with kind `budget` and reason `escalation_offer`, spending no retry, with the evidence and the exact `resume <thread> --escalate` command next to the retry, back and stop choices ([HUM-B7 to HUM-B11](gate-and-human.spec.md)).

- GIVEN LAD-B12's set-up at stage `local-dev` WHEN E1 to E9 hold THEN the run pauses and the escalated attempt runs only after a person's `resume --escalate`
- GIVEN that pause WHEN a resume without `--escalate` retries THEN the attempt runs on the base tier
- GIVEN an agent's `resume --escalate` with no relay evidence WHEN it runs THEN it is refused with exit 2 and `escalate_needs_person` ([PRV-B21, PRV-B22](caller-provenance.spec.md))
- GIVEN a pause with no offer WHEN `resume --escalate` runs THEN it is refused with `no_escalation_offered`

### LAD-B13 Stages

WHEN the gate reads the run's stage ([PRO-B7, PRO-B4](promotion-check.spec.md)) THE gate SHALL apply it: at `local-dev` an `auto` is read as `offer`; at `local-stable` `auto` runs only when the escalation record for this step and workflow version has at least 5 escalated attempts graded by an `accepted` judge with a pass rate whose Wilson lower bound is at least 0.5, else it offers; at `pipeline` `escalation` stays `off` until the promotion stamp covers escalated attempts of the step (PRO-B10) and the run has a run cost cap, `offer` is read as `off`, and an effort ladder runs only if the promotion stamp saw it.

- GIVEN `stages: {local-dev: auto}` at `local-dev` WHEN every condition holds THEN the run pauses with the offer
- GIVEN `local-stable: auto` and an escalation record of 4 attempts WHEN every condition holds THEN the run offers instead
- GIVEN an escalation record that cannot be read WHEN `auto` is decided THEN the record counts as not met and `auto` behaves as `offer`

### LAD-B14 Preflight and validation

WHEN a workflow with a ladder is validated or preflighted THE engine SHALL refuse at preflight with exit 2, naming the step, rung and model, a rung the executor declares it cannot apply to the bound model (`effort-rung-unsupported`) or an `escalation.to` it cannot bind; warn and record `applied_options` for a rung the executor reports `uncertain` (`effort-rung-uncertain`; `xhigh` and `max` until P-LAD-1); and fail validation for `effort_ladder` or `escalation` on a judge, member, chair or slot scope at any layer.

- GIVEN a rung the executor cannot apply WHEN the run is preflighted THEN it exits 2 before any session
- GIVEN `escalation.to: large` that preflight cannot bind WHEN the run is preflighted THEN it exits 2, not at the third attempt
- GIVEN `effort_ladder` on a council member WHEN the workflow is validated THEN it fails

### LAD-B15 Operators pin, workflows declare

WHEN an operator layer sets `effort_ladder` or `escalation` THE engine SHALL refuse it, because they are workflow data; an operator pins `effort` or `model` instead.

- GIVEN `--set code.effort_ladder=[high,max]` WHEN the options are checked THEN they are refused

### LAD-B16 Ladder records

WHEN an attempt ends THE engine SHALL write a `ladder` object on its step record with `rung`, `effort`, `alias`, `source` (`declared`, `ladder:effort[<i>]`, `escalation:+1`, `operator` or `arm:<switch>.<arm>`), `evidence` (with the criterion ids, the judge binding and its state), `held_by`, and for an offer `offered` and `taken_by` with the PRV caller block, and the gate that chose the next rung SHALL write a `ladder_decision` record ([EVT-B10 to EVT-B16](run-events.spec.md)).

- GIVEN a climbed attempt WHEN its step record is read THEN `ladder.source` is `ladder:effort[1]` and `ladder.evidence` names `judge_blocker` with the criterion ids
- GIVEN a judgement WHEN the gate reads it THEN it carries `judge_state` and `trusted`

### LAD-B17 Escalation record and reports

WHEN escalated attempts are graded THE engine SHALL keep the escalation record as ledger rows of kind `escalation` per workflow version and unit (attempts, passes, the judge state at each), and `report` SHALL show rung-0 and climbed attempts apart in first-pass yield and cost per completed run, and runs with an escalated attempt apart in per-version cost ([OBS](observability-and-cost.spec.md), [IMD](improvement-data.spec.md)).

- GIVEN a version with 10 rung-0 attempts and 3 climbed attempts WHEN `report` runs THEN its `ladder` section counts them apart and first-pass yield uses the rung-0 attempts only

### LAD-B18 Retiring the release 1 model list

WHEN a step's `model` or a `model_profile` is a list of aliases THE engine SHALL fail validation with `model-ladder-retired` and the rewrite in the message, and the release 2 changelog transform `model_list_to_escalation` ([VER-B9](version-metadata.spec.md)) SHALL rewrite `[a]` as `model: a`, `[a, b]` with `b` one tier above as `model: a` with `escalation: {to: b}`, and anything else as `model: a` with the owner item "choose an `escalation.to`, or none" ([WUP-B15, WUP-B16](workflow-upgrade.spec.md)).

- GIVEN `model: [small, medium]` WHEN the workflow is validated THEN it fails with `model-ladder-retired` naming `model: small` and `escalation: {to: medium}`
- GIVEN `model: [small, medium, large]` WHEN the transform runs THEN the result is `model: small` and an owner item

### LAD-B19 Proposals may add a ladder

WHEN the improvement loop proposes an `effort_ladder` or `escalation` THE engine SHALL treat it as a producer `model` proposal measured by a trial that counts rung-0 and climbed attempts apart ([PRP-B13](improvement-proposals.spec.md)).

- GIVEN a proposal adding `effort_ladder: [medium, high]` WHEN its trial runs THEN the trial report shows rung-0 and climbed attempts in separate rows

## Acceptance criteria

- LAD-AC1 (LAD-B1, LAD-B2, LAD-B3, LAD-B4, LAD-B5, LAD-B6, LAD-B7, LAD-B8, LAD-B11): Each scenario of these behaviours and each held cause holds offline with scripted executors and scripted judge states
- LAD-AC2 (LAD-B10, LAD-B11): For every cause of [BUD-B1, BUD-B11](budgets-and-failures.spec.md), a fixture shows the rung of the next attempt, and only the two evidence kinds ever raise it
- LAD-AC3 (LAD-B12): No fixture produces an escalated attempt unless all of E1 to E9 hold, and each condition has a fixture where it alone fails
- LAD-AC4 (LAD-B14): No judge, member, chair or slot session runs with a ladder effort or an escalated alias
- LAD-AC5 (LAD-B17): First-pass yield and cost per version in `report` exclude climbed attempts from the rung-0 figures
- LAD-AC6 (LAD-B18): The transform rewrites each fixture of release 1 `model` lists as LAD-B18 says, and V1 to V7 of the upgrade pass on the result
- LAD-AC7 (LAD-B14): Live: `--effort xhigh` and `--effort max` are applied on each alias of the shipped binding table (probe P-LAD-1 in the [live checks plan](../plans/live-checks.plan.md))
- LAD-AC8 (LAD-B9): Each declaration scenario of LAD-B9 validates or fails with the code it names
- LAD-AC9 (LAD-B13): At each stage, `auto` and `offer` behave as LAD-B13 says, and an unreadable escalation record behaves as `offer`
- LAD-AC10 (LAD-B15): An operator layer that sets `effort_ladder` or `escalation` is refused
- LAD-AC11 (LAD-B16): Every attempt of a ladder step has a `ladder` object with every field of LAD-B16, and every gate that chose a rung wrote `ladder_decision`
- LAD-AC12 (LAD-B19): A trial of a ladder proposal reports rung-0 and climbed attempts apart

## Open questions

- Is at least 5 escalated attempts with a lower bound of at least 0.5 the right bar for `auto` in `local-stable`? Owner, then data. Until answered: as stated, revisited after 20 escalations.
- Should a `check_fail` with the same failing test twice at the top rung also allow escalation? Owner. Until answered: no, because a repeated check failure points to an instruction or a tool ([research `judge-model-by-risk-and-evidence-for-escalation`](../research/judge-model-by-risk-and-evidence-for-escalation.rsrch.md) F4).
- Does the CLI honour `xhigh` on every alias? Live check P-LAD-1. Until it runs: `uncertain`, warned and not refused.
