# Judge calibration and acceptance

## Purpose

Every gate rests on an LLM judge, and public work shows judges pass bad work far more often than they fail good work ([research `evaluating-llm-judges-public-practice`](../research/evaluating-llm-judges-public-practice.rsrch.md) F2). This spec defines how a judge is graded before anything relies on its grades: a gold case set per gate with reviewed labels per criterion, a score of one judge binding on that set (repeated, and on generated variants), the figures computed from it, an acceptance bar on their lower confidence bounds, and the acceptance state other specs read. Acceptance never changes a verdict, a route or a budget: a gate always runs its judge and the engine always derives the verdict ([JDG](judge-and-verdict.spec.md)). What acceptance licenses is trust in the judge's grades elsewhere: stable mode ([LIF-B6](lifecycle-and-evals.spec.md)), outcome filing ([SIL-B7](self-improvement.spec.md)), corrected rates in reports ([EVS](eval-suites.spec.md)), judge-graded trial targets and ladder evidence. This is the offline half of judge reliability; production labels are the other half ([FBK](feedback-and-judge-reliability.spec.md)), and they measure different errors. The recursion stops at people: a judge never writes a gold label. The gaps it closes are E1 to E8, E11, E15 and E16 of [research `eval-and-judge-gap-analysis`](../research/eval-and-judge-gap-analysis.rsrch.md); design notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md). Workflow authors, operators moving a workflow to stable mode and the loop depend on it.

## Depends on

- `effort-ladder-and-model-escalation.spec.md`: effort ladder and one-step model escalation
- `eval-suites.spec.md`: eval suites for checks, steps and workflows
- `executor-interface.spec.md`: executor interface
- `judge-model-by-risk.spec.md`: judge model by risk
- `lifecycle-and-evals.spec.md`: live judge scoring (LIF-B15)
- `security.spec.md`: security posture
- `self-improvement.spec.md`: uncalibrated stays local (SIL-B7)
- `session-contract.spec.md`: session contract

## Behaviours

### JCL-B9 Gold case set

WHEN a workflow package holds calibration cases for a judged gate under `evals/calibration/<gate>/` (`<case_id>/case.json`, `<case_id>/fixture/`, `scores.jsonl`, outside the content digest so a score never changes the workflow version) THE engine SHALL read per case `case_id` (stable, never reused), `gate`, `fixture` (`workspace/`, `account.md`, `request.md`, `references.json`, `subject.json` and an optional recorded `check.json`: what the judge sees), `labels[]` (`{criterion_id, expected, reason, reviewer}`, one per criterion, `expected` one of `MET`, `PARTIAL`, `UNMET`, `N/A`, `UNVERIFIABLE`, each recording the criterion text's digest), `criteria_digest`, `provenance` (`synthetic`, `harvested` or `expert`), `state` (`candidate` or `reviewed`, only reviewed cases scored, harvested ones starting `candidate`), `split` (`tune` or `holdout`), `producer_family` (or `unknown`) and optional `second_review` (`{reviewer, agrees}`), and treat a case whose label names a criterion id the gate does not declare as invalid, listed and not scored.

- GIVEN a label naming an undeclared criterion WHEN scored THEN the case is listed invalid and not scored

### JCL-B10 Finding classes

WHEN a score counts findings, one per case and blocker criterion THE engine SHALL count a known-bad finding (expected `PARTIAL` or `UNMET`) caught when the judge's status after the engine's derivation rules is `PARTIAL` or `UNMET`, an out-of-reach finding (expected `UNVERIFIABLE`) correct when it is `UNVERIFIABLE`, `N/A` with a reason, or `gap` set and never `MET`, and a known-good finding (expected `MET` or `N/A`) clean when it is `MET` with evidence or `N/A` with a reason, scoring and reporting warning criteria the same way without counting them toward the bar.

- GIVEN an out-of-reach finding judged `MET` WHEN counted THEN it is not correct

### JCL-B11 Tune and holdout

WHEN a case is written THE engine SHALL mark it `holdout`, make it `tune` the first time the authoring skill or the improvement proposer shows it to anyone editing that gate's brief, stance or criteria, never move it back to `holdout`, compute the bar on holdout cases only, and score and show tune cases apart ([ADR `calibration-cases-split-tune-and-holdout`](../adr/calibration-cases-split-tune-and-holdout.adr.md)).

- GIVEN a tune case WHEN any later edit happens THEN it stays `tune`

### JCL-B4 Tuning consumes cases

WHEN the authoring skill shows three cases holding 9 of a gate's 24 holdout known-bad findings while the brief is edited THE engine SHALL make those cases `tune`, leaving 15 holdout findings, and grade the gate `below_bar` with rule "known-bad holdout findings ≥ 20" until new cases are added.

- GIVEN 9 of 24 findings shown during an edit WHEN the bar runs THEN the holdout count is 15 and the gate is `below_bar`

### JCL-B12 Stale labels and fixtures

WHEN a label's criterion text or check method changed since its digest, or a case's fixture changed since its labels were reviewed THE engine SHALL mark that label, or that case, `stale` and not score it until a reviewer confirms or changes it, leaving the case's other labels current ([research `evaluating-llm-judges-public-practice`](../research/evaluating-llm-judges-public-practice.rsrch.md) F8).

- GIVEN one reworded criterion WHEN scored THEN only its labels are stale

### JCL-B13 Variants

WHEN a score runs variants THE engine SHALL build each from the case by a fixed engine template with no model call, so it is reproducible and costs only its judge session ([ADR `judge-robustness-by-metamorphic-variants`](../adr/judge-robustness-by-metamorphic-variants.adr.md)): `persuasive_account` (the step account replaced by an engine text claiming every criterion met, confident and without evidence; every blocker status class unchanged), `padded` (the subject about doubled with plausible irrelevant filler; unchanged), `reordered` (criteria in a fixed permuted order, ids unchanged; every status unchanged per id) and `out_of_reach` (the read view of one reference a blocker depends on removed; that blocker `UNVERIFIABLE` or `N/A`, never `MET`), a status class being `pass` (`MET`, `N/A`) or `fail` (`PARTIAL`, `UNMET`, `UNVERIFIABLE`).

- GIVEN two generations of one variant WHEN their digests are compared THEN they are equal

### JCL-B5 Persuasion is tested

WHEN the `persuasive_account` variant of a known-bad case the judge caught in all three repeats is judged `MET` on that criterion THE engine SHALL count the finding toward `variant_flip[persuasive_account]` and list the case with the criterion id in the report.

- GIVEN a persuasive variant judged `MET` WHEN reported THEN the case and criterion are listed

### JCL-B6 Out of reach is never MET

WHEN the judge reports `MET` on an `out_of_reach` variant whose removed reference holds the text a blocker compares against THE engine SHALL put `out_of_reach_ok` below 1.0 and grade the gate `below_bar`, whatever its other figures.

- GIVEN one `MET` on an out-of-reach finding WHEN the bar runs THEN the gate is `below_bar`

### JCL-B14 Score

WHEN `evals score <gate> [--executor <name>] [--repeat k] [--variants <kinds>|none] [--cap <usd>]` runs ([LIF-B15](lifecycle-and-evals.spec.md)) THE engine SHALL run the gate's real judge (engine brief, workflow stance and brief, view set, independence guard) on a scratch copy of each reviewed case's fixture `k` times (default 3) and on the requested variants once each, opt-in and capped ([EVS](eval-suites.spec.md)), and append one score record with `score_id`, `at`, `run_by`, `gate`, `case_set_digest`, `split`, `binding` (`{executor, executor_version, alias, model_slug, brief_digest, criteria_digest, sampling}`, `sampling` holding temperature and effort where exposed else `not_exposed`), `repeats`, `results[]` (per case, repeat and variant: criterion ids with statuses, confidence and its source, guard status; ids and statuses only, no model text, [SEC](security.spec.md)), `figures` and `usage`; refusing before spend with exit 2 on an executor that cannot enforce the judge view set ([EXI](executor-interface.spec.md)), and on reaching the cap stopping cleanly with the record kept `partial: true` and never used for a state.

- GIVEN a cap reached mid-score WHEN the score ends THEN its record is `partial: true` and the state is unchanged

### JCL-B1 Discarded judgement is a fail, never a gap in the count

WHEN a judgement the guard discards, or that fails to parse, is scored THE engine SHALL count it as a fail status for every criterion of its case, caught on a known-bad finding and not clean on a known-good one, never dropping it from the denominator.

- GIVEN a known-good case whose judge called a tool outside its view set WHEN scored THEN each blocker finding counts as not clean and stays in the denominator

### JCL-B15 Figures

WHEN figures are computed on holdout findings with the first repeat as the primary judgement THE engine SHALL compute `catch_rate` with its Wilson 95 % lower bound `catch_lb`, `clean_rate` with `clean_lb`, `out_of_reach_ok` (any `MET` listed by case), `false_pass_cases` (known-bad cases whose derived verdict was PROCEED), `balanced_accuracy` (the mean of catch and clean rates), `flip_rate` (blocker findings whose status class differs across the `k` repeats), `variant_flip[kind]` (blocker findings whose class differs from the base case's majority, per kind), `self_family` (`catch_rate` split by `producer_family` same as or different from the judge's, a gap above 0.15 being a report line), `anchor_adherence` (judge-sourced confidence values on one of the four anchors of [SSN](session-contract.spec.md)), `confidence_by_anchor` (error share per anchor), `synthetic_share` (known-bad findings from synthetic cases) and `review_agreement`, the Wilson lower bound for `x` of `n` being `(p + z²/2n − z·√(p(1−p)/n + z²/4n²)) / (1 + z²/n)` with `p = x/n` and `z = 1.96`.

- GIVEN 19 of 20 caught WHEN computed THEN `catch_lb` is 0.76

### JCL-B16 Acceptance bar

WHEN the bar runs THE engine SHALL require at least 20 known-bad holdout findings from at least 8 distinct cases, at least 20 known-good from at least 5, every blocker criterion covered by a known-bad holdout finding, `catch_lb` at least 0.75, `clean_lb` at least 0.65, `out_of_reach_ok` 1.0 where out-of-reach findings exist, `flip_rate` at most 0.10 with `k` at least 3, `variant_flip[kind]` at most 0.10 for each kind scored with `persuasive_account` and `out_of_reach` required, and warn without failing for `anchor_adherence` below 0.95, the defaults held in one engine config file and raised per gate, never lowered, in the package's `evals/calibration/bar.json` ([ADR `judges-accepted-on-labelled-error-rates`](../adr/judges-accepted-on-labelled-error-rates.adr.md)).

- GIVEN a `bar.json` that lowers `catch_lb` WHEN read THEN the engine default holds

### JCL-B2 Small sets need near-zero misses

WHEN the bar runs on holdout known-bad counts THE engine SHALL decide the catch rule by `catch_lb`, not the point rate.

- GIVEN 20 findings with 19 caught WHEN the bar runs THEN `catch_lb` is 0.76 and the rule holds
- GIVEN 20 findings with 18 caught WHEN the bar runs THEN `catch_lb` is 0.70 and the rule fails
- GIVEN 40 findings with 37 caught WHEN the bar runs THEN `catch_lb` is 0.80 and the rule holds
- GIVEN 12 findings with 12 caught WHEN the bar runs THEN `catch_lb` is 0.76 and the rule fails on fewer than 20 findings

### JCL-B17 Acceptance state

WHEN a gate and binding's state is read THE engine SHALL decide it from the latest score for the current binding: `unscored` (none), `stale` (its binding or case-set digest differs from the current one), `below_bar` (a rule fails, the failing rules listed), `provisional` (every rule holds but `synthetic_share` above 0.5), `accepted` (every rule holds and `synthetic_share` at most 0.5) or `contradicted` (`accepted` or `provisional` while FBK's production grade for the binding is `unreliable`); and SHALL require `accepted` for readiness `ready` and stable mode, for outcome filing on the outcome judge, and for judge-graded trial targets beside FBK's grade, `accepted` or `provisional` for corrected rates in reports (else `uncorrected`), and `accepted` (`provisional` at stage `local-dev`) per risk level ([JRK](judge-model-by-risk.spec.md)) for a judge blocker as climbing evidence for a ladder ([LAD](effort-ladder-and-model-escalation.spec.md)).

- GIVEN a `provisional` gate WHEN stable mode validates THEN it is refused

### JCL-B3 A new model makes the score stale

WHEN `evals bar` runs for an `accepted` gate whose alias `medium` was rebound to another model slug THE engine SHALL show the gate `stale` with the old score as history, and stable-mode validation SHALL refuse the workflow until it is re-scored.

- GIVEN a rebound alias WHEN `evals bar` runs THEN the gate is `stale`

### JCL-B7 Production contradicts

WHEN `evals bar` runs for a gate `accepted` offline whose FBK grade for the same binding became `unreliable` THE engine SHALL show `contradicted`, refuse stable mode and filing as for `below_bar`, and list the disagreeing labels as harvest candidates.

- GIVEN an `unreliable` production grade WHEN `evals bar` runs THEN the gate is `contradicted`

### JCL-B8 Built-in judges are graded the same way

WHEN `evals bar` runs for the self-improvement outcome judge with four synthetic cases THE engine SHALL show it `below_bar` for too few findings, so SIL-B7 keeps every outcome finding `uncalibrated`; audit, outcome and friction judges are scored like any gate.

- GIVEN four synthetic cases WHEN `evals bar` runs THEN the outcome judge is `below_bar`

### JCL-B18 Bar and label verbs

WHEN `evals bar [<workflow>] [--json]` or `evals label <workflow>/<gate>/<case> --criterion <id> --expected <status> --reason <text>` runs THE engine SHALL show, with no model call, each gate's state, figures, failing rules and the cases still needed, or write or confirm one label with the caller block, a label by a non-person caller being a `candidate`, not gold.

- GIVEN `evals label` run by an agent WHEN written THEN the label is a `candidate`

## Acceptance criteria

- JCL-AC1 (JCL-B2, JCL-B15, JCL-B16): Every scenario of JCL-B2 is reproduced by the bar function, including the Wilson bounds to two decimals
- JCL-AC2 (JCL-B1): A discarded or unparsed judgement in a fixture score counts as a fail for every criterion of its case
- JCL-AC3 (JCL-B3, JCL-B17): A change to any field of `binding` or to the case-set digest turns an `accepted` state into `stale`
- JCL-AC4 (JCL-B11, JCL-B4): A case shown by the authoring skill or the proposer during a brief edit is `tune` afterwards, and no code path sets it back to `holdout`
- JCL-AC5 (JCL-B13): Each variant kind is generated with no model call and identically on two runs, by a digest test
- JCL-AC6 (JCL-B14): A score record contains no request, output or model text, by a canary test
- JCL-AC7 (JCL-B17, JCL-B7, JCL-B8): Stable-mode validation, outcome filing and corrected rates each refuse a gate in every state other than the one JCL-B17 allows
- JCL-AC8 (JCL-B18): `evals bar` and `evals label` make no model call
- JCL-AC9 (JCL-B5, JCL-B6, JCL-B9, JCL-B10, JCL-B12): Fixtures cover a persuasion flip, an out-of-reach `MET`, an invalid case, each finding class and a stale label

## Open questions

- Are the default bars right for a first release? They admit 20 known-bad findings with one miss; research `design-gap-review` G7 proposed a false-pass ceiling of 0.05 on a point value instead. Owner: owner.
- Should FBK's `reliable` grade require `accepted` here, merging the two states? Proposed in [research `eval-and-judge-gap-analysis`](../research/eval-and-judge-gap-analysis.rsrch.md). Owner: owner, with the self-improvement thread.
- Who may act as a reviewer of gold labels in a team? Until answered: anyone with commit rights to the workflow package. Owner: owner.
