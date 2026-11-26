# Audit rule catalog

## Purpose

The fixed list of rules the [workflow audit](workflow-audit.spec.md) applies, outside the tool surface rules of [TSA](tool-surface-audit.spec.md) and the prompt rules of [PRA](prompt-audit.spec.md). Each rule answers one cause ranked in [research `why-runs-fail-stall-repeat-or-overspend`](../research/why-runs-fail-stall-repeat-or-overspend.rsrch.md), names the layer it needs, carries a cause code shared with the self-improvement loop, and has a default severity, confidence and remedy. Rules owned by another component are listed with their owner and run through it ([ADR `audit-joins-existing-checks-and-files-nothing`](../adr/audit-joins-existing-checks-and-files-nothing.adr.md)). The catalog is engine data, versioned with the engine; a workflow cannot add or change a rule, only ignore one with a reason ([AUD](workflow-audit.spec.md)). One rule answers one cause; a rule that would need prose judgement is a judge's work and stays out, because the audit calls no model (OVR-B15, [ADR `advisory-read-only-audit-verb-in-three-layers`](../adr/advisory-read-only-audit-verb-in-three-layers.adr.md)). Thresholds are defaults chosen to fire on clearly bad runs and stay quiet on healthy ones, not fitted ([ADR `history-findings-need-a-minimum-sample`](../adr/history-findings-need-a-minimum-sample.adr.md)), recorded as named parameters with the research `why-runs-fail-stall-repeat-or-overspend` finding (F) that motivated them and revisited after the first 20 runs of a real workflow. Workflow authors, the audit and the loop's backlog depend on these ids and cause codes; release notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `ask-unit.spec.md`: ask unit
- `blueprint-and-scaffold.spec.md`: blueprint, scaffold and authoring checks
- `caller-provenance.spec.md`: caller provenance
- `contest-unit.spec.md`: contest unit
- `council-unit.spec.md`: council unit
- `flow-extensions.spec.md`: flow extensions
- `judge-calibration.spec.md`: judge calibration and acceptance
- `lifecycle-and-evals.spec.md`: executor compatibility (LIF-B10); prompt lint (LIF-B12); judge readiness report (LIF-B13)
- `plugin-shell.spec.md`: prefer a check (SHL-B4)
- `prompt-audit.spec.md`: structure rules (PRA-B13)
- `run-outcome.spec.md`: run-level good outcome
- `script-units-and-hybrid-steps.spec.md`: script units and hybrid steps
- `self-improvement.spec.md`: self-improvement loop
- `supervision-cost.spec.md`: supervision cost
- `supervision-metrics.spec.md`: supervision metrics
- `workflow-audit.spec.md`: the repository's commands entry is no program (AUD-B17); the programs of the target's declared commands are looked up (AUD-B18); the target's declared commands cover its toolchain (AUD-B19)
- `workflow-model.spec.md`: workflow model and validation

## Behaviours

### ARC-B6 Rule record

WHEN a rule is listed in the catalog THE engine SHALL give it `id` (a stable kebab-case slug, never reused, a rename keeping an alias), `layer` (`definition`, `host` or `history`, one per rule), `family` (research `why-runs-fail-stall-repeat-or-overspend`'s `C1` to `C8`), `cause` (a code of the self-improvement list, [SIL](self-improvement.spec.md), which owns the codes this catalog adds and classes each `fault`, `infra` or `designed`), `severity` (`error`, `warning` or `info`), `confidence` (`high` a fact, `medium` a shape that usually causes the cause, `low` a heuristic), `owner` (`audit` or the owning component, an owned rule being only rendered), `min_n` for a history rule (1, any run in the window, unless a rule names more), `remedy` (fixed text naming the field and the kind of change) and `built` (the release that builds it).

- GIVEN any history rule WHEN the catalog schema test reads it THEN it has a `min_n`

### ARC-B7 Rank and skips

WHEN findings are ranked THE audit SHALL break ties after severity and confidence by family in research `why-runs-fail-stall-repeat-or-overspend` order (C1 highest) and within a family by catalog order, skip with its reason a rule whose input is missing (no probe, no runs) or whose owner component is not present (`owner not present`), never counting it as passed, and show both of two rules that fire on one field for one cause, the lower-ranked citing the higher.

- GIVEN no runs in the window WHEN history rules run THEN each is skipped with its reason

### ARC-B8 C1 definition rules

WHEN the definition layer runs THE audit SHALL fire `oversized-step` (warning/medium, `oversized_step`) when a gate has more than 8 blocker criteria, the step produces more than 3 `file` artifact keys, or the rendered template without inputs exceeds 24,000 characters (remedy: split into passes with their own gates; F1.2 yield 29 % to 62 %); `no-change-blocker-retries` (warning/high, `no_change_retry`) when a blocker has `no_change_policy: retry` (keep `escalate`; F1.4); `unverified-blocker` (warning/high, `unverifiable_blocker`) when a blocker names an `unverified_system` (give the judge a view, move the fact to a check, or make it a warning); `single-criterion-gate-judge-only` (info/low, `prefer_check`) when a fixed pattern finds a criterion naming a file or folder that exists, a command or tests that pass, or a git fact on a gate with no check (make it a check, SHL-B4); and render `judge-not-ready` from the readiness report ([LIF-B13](lifecycle-and-evals.spec.md), [JCL](judge-calibration.spec.md)) as `readiness:needs-work` (warning/high) and `readiness:needs-cases` (info/high), and `brief-rule-branching` and `criterion-without-method` from validation ([WFM](workflow-model.spec.md)).

- GIVEN a gate with 9 blockers WHEN audited THEN `oversized-step` fires

### ARC-B9 C1 history rules

WHEN the history layer runs THE audit SHALL fire `loop-driver-criterion` (error/high, `retry_burst`, `min_n` 5 runs) when one criterion is the leading unmet blocker in at least 50 % of a gate's RETRY verdicts with at least 5 RETRYs and the gate's repeats are at least 20 % of the workflow's spend (name it: split the step, reword so a second visit can meet it, or move it to a check); `low-first-pass` (warning/high, `low_first_pass`, `min_n` 5 visits) when a gate passes first time in under 50 % of visits; `no-change-retried` (warning/high, `no_change_retry`) on a RETRY whose unmet blockers are all `no_change`; `repeated-check-evidence` (warning/medium, `retry_cannot_fix`) on two or more check FAILs with one evidence digest in a visit followed by a new attempt (mark it environmental or fix the environment; F2.1); and `missing-field-rendered` (error/high, `missing_input`) when a step record shows a `⟨missing:name⟩` marker (supply the input or make the field optional; F1.5, F7.1).

- GIVEN 6 RETRYs of which 4 lead with criterion `C3` and repeats at 25 % of spend WHEN audited THEN `loop-driver-criterion` names `C3`

### ARC-B10 C2 environment rules

WHEN the host and history layers run THE audit SHALL fire `check-program-missing` (error/high, `environment_missing`) when the first word of a prefix in `allow_commands` or a step's `commands` is not found on `PATH` or not executable (F2.4); `toolchain-not-covered` (warning/medium, `toolchain_not_covered`) when the workflow declares commands or a gate has a check and the repository's `package.json` scripts, `Makefile` targets, `pyproject.toml`, `go.mod` or `Cargo.toml` are covered by none of their own programs (npm, yarn, pnpm, node, bun; make; python, pytest, uv and the like; go; cargo), an entry `@repository` being no program and standing in both rules for the prefixes of the target's `tempergraph.commands.json` ([AUD-B17](workflow-audit.spec.md), [AUD-B18](workflow-audit.spec.md), [AUD-B19](workflow-audit.spec.md)); both skipped with a `command_resolver` because its output is not read; `interpreter-cannot-import` and `worktree-env-outside-worktree` (error/high `environment_missing`, warning/medium `stale_import`; F2.2, F2.7) skipped while the workflow declares no interpreter; `slow-host` (warning/high, `slow_host`) when the host-speed probe times `$SHELL -lc true` above 15 s, or above five times `$SHELL -c true` and above a floor of 1 s (`slow_login_shell_floor_s`; F2.5); `check-ran-nothing` (error/high, `blocked_without_check`) when a check's evidence records every declared command not run; `infra-heavy` (warning/medium, `infra_heavy`, `min_n` 20 attempts) when infra tries are at least 10 % of attempts on the host (F2.6); and render `executor-outside-tested-range` from executor compatibility ([LIF-B10](lifecycle-and-evals.spec.md)).

- GIVEN a login shell at 0.4 s and a plain shell at 0.05 s WHEN `slow-host` runs THEN it does not fire, being under the 1 s floor

### ARC-B11 C3 timeout rules

WHEN the definition and history layers run THE audit SHALL fire `default-step-timeout` (warning/high, `default_timeout`) when a step and the workflow set no `timeout_s`, so 600 s applies (F3.4, F3.6); `default-judge-timeout` (info/high, `default_timeout`) for a judge likewise, a judge never taking the step's limit; `idle-limit-inert` (warning/high, `idle_inert`) when `idle_s` is at least the resolved `timeout_s`; `no-idle-limit` (info/medium, `no_idle_limit`) when a step above 1,800 s has no `idle_s` (F3.5); `hold-time-exposure` (warning/high, `hold_exposure`) when `timeout_s × (retry_budget + 1)` plus `timeout_s ×` infra tries exceeds 4 h for a unit or 12 h over `order`, a unit with no check and no judge having one attempt, printing the hours; `timeout-below-pass-p90` (error/high, `timeout_too_short`, `min_n` 5 passing attempts) when a limit is below 1.25 × the p90 of passing attempts, recommending about 1.5 × it; `attempts-at-limit` (warning/high, `timeout_share`, `min_n` 5) when at least 20 % of a unit's attempts time out or stall, split by tool share at least 60 % (slow host), one long call in flight (hung) or model silent (F3.2, F3.7); `limit-far-above-p90` (info/medium, `timeout_loose`, `min_n` 5) above 4 × that p90; and `request-timed-out` (warning/high, `request_timed_out`) on any `request_timed_out` cause, giving the step's largest single response (F3.3).

- GIVEN `idle_s` 900 and `timeout_s` 600 WHEN audited THEN `idle-limit-inert` fires

### ARC-B2 Hold-time arithmetic

WHEN `hold-time-exposure` runs on a unit with the default 3 infra tries THE audit SHALL compute `timeout_s × (retry_budget + 1) + timeout_s × 3` and fire above 4 h.

- GIVEN `timeout_s` 600 and `retry_budget` 2 WHEN computed THEN the hold is 1 h and the rule does not fire
- GIVEN `timeout_s` 3,600 and `retry_budget` 2 WHEN computed THEN the hold is 6 h and the rule fires
- GIVEN `timeout_s` 7,200 and `retry_budget` 2 WHEN computed THEN the hold is 12 h and the rule fires

### ARC-B3 Timeout fit

WHEN `timeout-below-pass-p90` runs on step `plan` with limit 600 s and 8 passing attempts whose p90 is 540 s THE audit SHALL fire (600 < 1.25 × 540 = 675) and recommend about 810 s.

- GIVEN a 600 s limit and a 540 s p90 WHEN audited THEN the rule fires recommending about 810 s

### ARC-B12 C5 pause rules

WHEN the definition and history layers run THE audit SHALL fire `every-retry-asks` (warning/high, `ask_without_budget`) when a gate has `retry_budget: 0` and `on_budget_spent: ask`; `approval-on-most-gates` (info/medium, `approval_heavy`) when more than half the gates set `approval`; `empty-pauses` (warning/medium, `empty_pause`, `min_n` 4 pauses) when at least 50 % of a gate's pauses end in `proceed` with no feedback and no workspace change (F5.3); `interventions-per-run` (info/high, `person_rate`, `min_n` 5 runs) when undesigned touches by every decider, approvals apart ([SUP](supervision-metrics.spec.md)), exceed 1.0 per run, split by class, pause kind and decider; `agent-rescues-alone` (warning/high, `agent_decided`, `min_n` 5 rescues) when agents made at least 30 % of a gate's rescue decisions on their own ([PRV](caller-provenance.spec.md)); `supervision-cost-share` (warning/medium, `supervision_heavy`, `min_n` 5 runs with measured cost) above a median 10 % share; `polling-supervisor` (warning/high, `supervisor_polling`, `min_n` 5) above 20 observations per run or `rewake` above half the supervision cost ([SCO](supervision-cost.spec.md), [ADR `attention-batched-waking-of-the-orchestrating-session`](../adr/attention-batched-waking-of-the-orchestrating-session.adr.md)); and `callers-unknown` (info/high, `caller_unknown`, `min_n` 10 touches) above 20 % of touches with caller `unknown`.

- GIVEN a gate with `retry_budget: 0` and `on_budget_spent: ask` WHEN audited THEN `every-retry-asks` fires

### ARC-B13 C6 cost rules

WHEN the definition and history layers run THE audit SHALL fire `small-judge-cross-file` (warning/medium, `model_too_small`) when a judge or review step on tier `small` reads references or a subject spanning more than one artifact (F6.4), the tier being the alias's last part (`small`, `haiku`; `large`, `opus`) and a step's model falling back to its `model_profile` entry; `sizing-unassessed` (error/high, `sizing_unassessed`) when a step or judge states no model (or `inherit`), no effort nor an effort ladder, or no reason of four words ([SCF](blueprint-and-scaffold.spec.md)); `large-everywhere` (info/low, `model_heavy`) when every step and judge resolves to `large`; `no-run-cost-cap` (info/high, `no_cost_cap`) when `run_cost_cap_usd` is unset in `stable` mode; `context-heavy-step` (warning/medium, `context_heavy`, `min_n` 5 attempts) when a step's median `peak_context_tokens` exceeds 150,000 or at least half its cost is in turns above 200,000 (F6.3); and render `cost-lens-rules` from the cost lens over the same window ([SIL](self-improvement.spec.md)).

- GIVEN a judge with no effort and no ladder WHEN audited THEN `sizing-unassessed` fires as an error

### ARC-B14 C7 and C8 rules

WHEN the definition and history layers run THE audit SHALL render `prompt-lint` from prompt lint ([LIF-B12](lifecycle-and-evals.spec.md)), run the structure rules of the prompt audit ([PRA-B13](prompt-audit.spec.md)) and render `template-grammar` from validation ([WFM](workflow-model.spec.md)); fire `outcome-unverified-blocker` (warning/high, `outcome_unverified`) when a blocker of the good outcome has trust `unverified` or `uncalibrated` ([OUT](run-outcome.spec.md)), naming calibration in the remedy while no judge is calibrated; `outcome-uncovered` (warning/high, `outcome_uncovered`) when a final criterion is not covered; `outcome-escapes` (warning/medium, `outcome_escape`, `min_n` 10) when the escape rate is at least 10 % of graded runs; and render `engine-fault-open` (info/high) from open engine- or executor-side findings that name this workflow's units ([SIL](self-improvement.spec.md)), so the author does not chase them in the workflow.

- GIVEN an uncalibrated judged blocker of the outcome WHEN audited THEN `outcome-unverified-blocker` fires

### ARC-B15 Rules for the newer unit kinds

WHEN a workflow uses the kinds of [SCR](script-units-and-hybrid-steps.spec.md), [CNL](council-unit.spec.md), [CTS](contest-unit.spec.md), [ASK](ask-unit.spec.md) or [FLX](flow-extensions.spec.md) THE audit SHALL fire `council-one-family` (C1, warning/medium, `council_monoculture`) when every member binds to one model family (research `councils-debate-and-voting` K3, K6); `council-even-majority` (C5, info/high, `tie_prone`) for a `vote` council with `rule: majority` and an even count; `council-rounds-no-gain` (C6, warning/medium, `rounds_no_gain`, `min_n` 10 visits) when later rounds changed the outcome in under 5 % of visits (K2); `council-conformity` (C1, info/low, `council_conformity`, `min_n` 10 rounds) when in at least 80 % of rounds after round 0 every changing member moved to the round-0 majority (K4); `contest-identical-slots` (C6, warning/high, `contest_no_diversity`) when every slot shares executor, model and prompt; `contest-no-gain` (C6, warning/medium, `contest_no_gain`, `min_n` 10) when the lowest-numbered slot won at least 90 % of picks; `fallback-rate` (C1, warning/high, `fallback_heavy`, `min_n` 5) when a gate took its `fallback` in at least 30 % of visits; `unbounded-wait` (C5, info/medium, `wait_unbounded`) when a `wait` or `ask` has no `deadline_s` in `stable` mode; and render `external-after-without-approval` (C7, warning/high, `publish_before_review`) from validation, its thresholds resting on [research `councils-debate-and-voting`](../research/councils-debate-and-voting.rsrch.md) and revisited with the first 10 visits.

- GIVEN a majority vote council of 4 members WHEN audited THEN `council-even-majority` fires

### ARC-B16 Unknown ignore

WHEN a workflow's ignore list names no known rule THE audit SHALL report `ignore-rule-unknown` (info/high).

- GIVEN an ignore naming `no-such-rule` WHEN audited THEN `ignore-rule-unknown` is reported

### ARC-B1 Owned rules are rendered

WHEN the audit runs history while the cost lens reports "judge against step cost" for gate `verify` THE audit SHALL carry the cost lens's code and numbers with owner `SIL`, computing nothing of its own for it.

- GIVEN that cost-lens finding WHEN rendered THEN it shows owner `SIL` and the lens's numbers

### ARC-B4 New cause codes join the loop

WHEN the improvement backlog clusters an audit finding with cause `oversized_step` on unit `plan` and a later friction finding of the same cause on `plan` THE engine SHALL put both in one cluster keyed by side, workflow, unit and cause.

- GIVEN both findings WHEN clustered THEN they share one cluster

### ARC-B5 Remedy, never a patch

WHEN any rule fires THE audit SHALL give a remedy naming a field and a kind of change, producing no file content or diff.

- GIVEN any firing rule WHEN reported THEN no diff is produced

## Acceptance criteria

- ARC-AC1 (ARC-B6): Every rule has an `id`, `layer`, `family`, `severity`, `confidence`, `owner` and `remedy`, and every history rule a `min_n`, checked by a catalog schema test
- ARC-AC2 (ARC-B8, ARC-B9, ARC-B10, ARC-B11, ARC-B12, ARC-B13, ARC-B14, ARC-B15): Every research `why-runs-fail-stall-repeat-or-overspend` family C1 to C7 has at least one rule here or in TSA; C8 is listed as engine-side
- ARC-AC3 (ARC-B6): Each threshold is a named parameter with its default and the research `why-runs-fail-stall-repeat-or-overspend` finding it comes from
- ARC-AC4 (ARC-B1, ARC-B7): Owned rules call the owning component's function; a source test fails if an owned rule's logic is reimplemented in the audit
- ARC-AC5 (ARC-B2, ARC-B3): ARC-B2 and ARC-B3 hold as table tests
- ARC-AC6 (ARC-B4, ARC-B5, ARC-B16): An audit finding and a friction finding of one cause cluster together, no rule produces a diff, and an unknown ignore is reported

## Open questions

- Is 24,000 characters the right size signal for `oversized-step`, or should it be the step's recorded output size from history? Owner: first runs.
- Should `toolchain-not-covered` read a repository's CI configuration as a documented command source? Owner: owner.
