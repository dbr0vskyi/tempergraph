# Judge model by risk

## Purpose

A gate may raise its judge to a stronger model, or a higher effort, when model-free facts about the attempt say the work is riskier: the diff touches engine code, a migration or many files; the check counted many rows. A delivery workflow may want to judge code on a stronger model than the one that wrote it; this spec makes such a rule data, per attempt, while keeping every judge a calibrated binding ([R-121](../research/R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md), [ADR-0122](../adr/0122-a-judge-is-raised-by-a-model-free-risk-rule-and-every-level-is-calibrated.adr.md)). A risk rule only ever raises the judge, never reads what the step says about itself, and a fault picks the strongest level. Gates, calibration ([JCL](50-judge-calibration.spec.md)), readiness, promotion ([PRO](95-promotion-check.spec.md)) and reports depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### JRK-B1 Raise on engine code

WHEN a risk rule returns a level for an attempt THE engine SHALL run the judge at that level with `chosen_by: rule` and the rule's signals recorded.

- GIVEN levels `[base: medium, code: large]` and a rule that returns `code` when `git.paths_by_glob(["src/**"]) > 0` WHEN an attempt changes `docs/a.md` and `src/x.py` THEN the judge runs on `large` with signals `{src_paths: 1}`
- GIVEN the same rule WHEN an attempt changes only `docs/a.md` THEN the judge runs on `medium`

### JRK-B2 Fault takes the strongest level

WHEN the rule raises, returns an undeclared level name or runs longer than 1 s THE engine SHALL run the judge at the last level with `chosen_by: fault`, record the exception type or the time, and continue the run.

- GIVEN levels `[base: medium, code: large]` WHEN the rule raises `KeyError` THEN the judge runs on `large` with `chosen_by: fault`

### JRK-B3 Floor after escalation

WHEN the attempt's producer ran on an escalated tier ([LAD-B12](92-effort-ladder-and-model-escalation.spec.md)) THE engine SHALL run the judge at no level below the first whose model is at or above that tier, with `chosen_by: floor` when the floor decided.

- GIVEN a rule that returns `base` and a producer that ran on `large` by `escalation:+1` WHEN the judge resolves THEN it runs on `large` with `chosen_by: floor`

### JRK-B4 Shadow

WHEN `RiskSpec.mode` is `shadow` THE engine SHALL run level 0, unless the floor needs a higher one, and record the rule's level as `would_choose`.

- GIVEN a shadow rule that returns `code` WHEN the judge resolves THEN level 0 runs and the record holds `would_choose: code`

### JRK-B5 Stable needs every level

WHEN a workflow is validated for stable mode or readiness `ready` ([LIF-B6](18-lifecycle-and-evals.spec.md)) THE engine SHALL require every level `accepted` for a gate in `route` mode and level 0 only in `shadow` mode, refusing otherwise with the gate, the level and the `evals score` command that fixes it.

- GIVEN `route` mode with level 0 and level 1 accepted WHEN validated for stable THEN it is allowed
- GIVEN `route` mode with level 1 `unscored` WHEN validated for stable THEN it is refused naming the level
- GIVEN `shadow` mode with level 1 `unscored` WHEN validated for stable THEN it is allowed

### JRK-B6 Declaring a risk rule

WHEN a `JudgeSpec` declares `risk` THE engine SHALL accept a `RiskSpec` with either `rule`, a callable `risk(ctx: RiskContext) -> str | tuple[str, dict[str, int | float | str]]` returning a level name and optional signals, pure and model-free like a route predicate (OVR-B7), or `when`, a list of stock rules `{level, paths, min_paths, min_lines, fact, min_fact}`, a level holding when the attempt changed `min_paths` paths under the globs, `min_lines` lines, or a check fact reached `min_fact`, the highest holding level winning and a missing fact being a fault; `levels`, an ordered list of 2 or 3 `{name, model?, effort?}`, level 0 being the gate's own judge with no model stated, each later level at a tier at or above the one before, never at a lower effort, differing from it in model or effort, and keeping the model before when it states none; and `mode` `route` (default) or `shadow`; refuse as the validation error `risk-invalid` a level below or equal to the one before, and `risk` on a council member, chair, contest slot or the audit judge, whose bindings their own specs fix; refuse a level model that preflight cannot bind with exit 2 naming the gate and level; and resolve a judge without `risk` as before ([CON-B3](01-contracts.spec.md)).

- GIVEN levels `[base: medium, code: medium]` with the same effort WHEN the workflow validates THEN it reports `risk-invalid`

### JRK-B7 What the rule reads

WHEN a rule runs THE engine SHALL give it a `RiskContext` holding only `unit`, `item`, `visit` and `attempt`; `git`, the attempt's `GitFacts` ([CHK-B10](75-check-contract-and-command-runs.spec.md)) plus `lines_added` (counting untracked files' lines), `lines_removed` and `paths_by_glob(globs) -> int`, `*` and `**` both crossing directories; `facts`, this attempt's check facts and those of earlier checks on the path; `request`, the resolved request's inputs; `settings`, the workflow's resolved settings; `stage`, the run's stage ([PRO](95-promotion-check.spec.md)); and `producer`, the alias and source of the attempt's producer, including `escalation:+1` ([LAD-B16](92-effort-ladder-and-model-escalation.spec.md)); never the step's text, its artifacts' contents or its values, a step value counting only once a check verified it and recorded it as a fact.

- GIVEN a step whose artifacts contain the word "trivial" WHEN the rule runs THEN it picks the same level as for an empty artifact

### JRK-B8 Resolution order

WHEN the judge for one attempt is resolved THE engine SHALL apply in order operator layers on the judge scopes ([RST-B22](80-run-settings-and-overrides.spec.md)), a pinned `model` or `effort` winning with level `operator` while the rule still runs and records `would_choose`; then the rule's level or JRK-B2's fault level; then the JRK-B3 floor; then JRK-B4's shadow rule; and bind the attempt's judge as the level's `{executor, alias, model_slug, sampling, brief_digest, criteria_digest}` ([JCL-B9](50-judge-calibration.spec.md)), each level being a separate binding for calibration ([JCL-B17](50-judge-calibration.spec.md)), labels and reliability grades ([FBK](41-feedback-and-judge-reliability.spec.md)) and the trust a ladder needs ([LAD-B10](92-effort-ladder-and-model-escalation.spec.md)), an operator-pinned judge being the judge's own binding with the pinned alias, stale until re-scored.

- GIVEN `--set judge.model=large` on a gate with a risk rule WHEN the judge resolves THEN it runs on `large` with `chosen_by: operator` and `would_choose` recorded

### JRK-B9 Calibration per level

WHEN levels are scored and read THE engine SHALL score each level binding on the gate's gold cases with `evals score <workflow> <gate> --level <name>`, kept in the gate's `scores.jsonl` with `level`; list a state per level in `evals bar`, a change to one level's model or effort making that level alone `stale`; count a gate accepted only when every level a routed rule may pick is accepted; require for promotion to `pipeline` every level the window used `accepted` on the pipeline's binding and at least 5 runs per used level in the risk report ([PRO](95-promotion-check.spec.md)); and use for outcome filing, corrected rates and the trust a ladder reads the level that graded each attempt.

- GIVEN a change to level `code`'s effort WHEN `evals bar` runs THEN only `code` is `stale`

### JRK-B10 Risk records and report

WHEN a judge resolves with a risk rule THE engine SHALL add `risk: {level, would_choose, signals, chosen_by}` to the judge's record, `chosen_by` one of `rule`, `fault`, `floor`, `shadow` and `operator`, with the alias and effort that ran, and write a `judge_risk` run-log record ([EVT](30-run-events.spec.md)); and `report --risk <workflow>` SHALL show per gate and level attempts, judge PROCEED and RETRY rates, judge cost and `chosen_by`, gate escapes and labels joined with the per-level reliability grades, and in shadow mode the same by `would_choose`; the sampled audit judge ([JDG](05-judge-and-verdict.spec.md)) auditing whatever level graded the attempt, its agreement recorded per level.

- GIVEN a shadow gate WHEN `report --risk` runs THEN its rows are grouped by `would_choose`

## Acceptance criteria

- JRK-AC1 (JRK-B1, JRK-B2, JRK-B3, JRK-B4, JRK-B5, JRK-B6, JRK-B8, JRK-B10): JRK-B1 to JRK-B5 and every case of JRK-B5 hold offline with scripted executors
- JRK-AC2 (JRK-B3, JRK-B8): No fixture makes a judge run below level 0, or below the producer's escalated tier
- JRK-AC3 (JRK-B7): A rule given a context built from a step whose artifacts contain the word "trivial" picks the same level as from an empty artifact
- JRK-AC4 (JRK-B9): `evals bar` lists a state per level, and a change to any level's model or effort makes that level, and only it, `stale`
