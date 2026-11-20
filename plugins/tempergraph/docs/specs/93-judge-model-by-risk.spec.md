---
title: Judge model by risk
type: component
status: review
prefix: JRK
adrs: [0122, 0121]
---

# Judge model by risk

## 1. Overview

A gate may raise its judge to a stronger model, or a higher effort, when model-free facts about the attempt say the work is riskier: the diff touches engine code, a migration or many files; the check counted many rows. temperspec judges code on a stronger model than the one that wrote it for this reason, by a fixed rule. This spec makes the rule data, per attempt, while keeping every judge a calibrated binding ([R-121](../research/R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md), [ADR-0122](../adr/0122-a-judge-is-raised-by-a-model-free-risk-rule-and-every-level-is-calibrated.adr.md)).

A risk rule only ever raises the judge. It never reads what the step says about itself, and a fault picks the strongest level.

## 2. Contract

```python
def risk(ctx: RiskContext) -> str | tuple[str, dict[str, int | float | str]]: ...   # level name, optional signals
```

### 2.1 Declaration

| Field (on `JudgeSpec`) | Kind | Meaning |
|---|---|---|
| `risk` | `RiskSpec`, optional | Without it the judge resolves as today ([CON §2.4](01-contracts.spec.md)) |
| `RiskSpec.rule` | callable ref | Pure and model-free, like a route predicate (contract C5) |
| `RiskSpec.levels` | ordered list of 2 or 3 `{name, model, effort?}` | Level 0 is the gate's own judge model (resolved as without `risk`); each later level is at a tier at or above the one before, and differs from it in model or effort |
| `RiskSpec.mode` | `route` \| `shadow`, default `route` | Shadow records the level and runs level 0 |

### 2.2 What the rule reads

| Field of `RiskContext` | Source |
|---|---|
| `unit`, `item`, `visit`, `attempt` | The engine |
| `git` | `GitFacts` of the attempt ([CHK §2.1](75-check-contract-and-command-runs.spec.md)), plus `lines_added`, `lines_removed` and `paths_by_glob(globs) -> int` |
| `facts` | This attempt's check facts and the facts of earlier checks on the path |
| `request` | The resolved request's inputs |
| `settings` | The workflow's resolved settings |
| `stage` | The run's stage ([PRO §2.1](95-promotion-check.spec.md)) |
| `producer` | The alias and source of the attempt's producer, including `escalation:+1` ([LAD §2.7](92-effort-ladder-and-model-escalation.spec.md)) |

It never receives the step's text, its artifacts' contents or its `value`s. A step value counts only once the check verified it and recorded it as a fact.

### 2.3 Resolution of the judge for one attempt

| Order | Rule |
|---|---|
| 1 | Operator layers on the judge scopes ([RST §2.3](80-run-settings-and-overrides.spec.md)): a pinned judge `model` or `effort` wins; the rule still runs and records `would_choose`; the level is `operator` |
| 2 | The rule's level, or the last level when the rule raises, returns an undeclared name or exceeds 1 s |
| 3 | Floor: when the producer of the attempt ran on an escalated tier, the first level whose model is at or above that tier ([LAD §2.4](92-effort-ladder-and-model-escalation.spec.md) E4) |
| 4 | In shadow mode, level 0 runs, unless rule 3 needs a higher one |

The judge's binding for the attempt is the level's `{executor, alias, model_slug, sampling, brief_digest, criteria_digest}` ([JCL §2.1](50-judge-calibration.spec.md)). Each level is a separate binding for calibration ([JCL §2.5](50-judge-calibration.spec.md)), for labels and reliability grades ([FBK](41-feedback-and-judge-reliability.spec.md)), and for the trust a ladder needs ([LAD §2.2](92-effort-ladder-and-model-escalation.spec.md)).

### 2.4 Calibration and stages

| Reader | Needs, per level |
|---|---|
| `evals score` and `evals bar` | Score and state per level; the gold cases are the gate's set, scored once per level binding |
| Readiness `ready` and stable mode ([LIF-B6](18-lifecycle-and-evals.spec.md)) | Every level `accepted`, in `route` mode; level 0 only in `shadow` mode |
| Promotion to `pipeline` ([PRO §2.3](95-promotion-check.spec.md)) | Every level the window used is `accepted` on the pipeline's binding, and the risk report of §2.5 has at least 5 runs per used level |
| Outcome filing and corrected rates | As JCL §2.5 says, for the level that graded each run |

### 2.5 Records

The judge's record gains `risk: {level, would_choose, signals, chosen_by}` with `chosen_by` ∈ `rule`, `fault`, `floor`, `shadow`, `operator`, and a `judge_risk` run-log record ([EVT §2.2](30-run-events.spec.md)). `report --risk <workflow>` shows, per gate and level: attempts, judge PROCEED and RETRY rates, gate escapes, labels and judge cost; in shadow mode, the same by `would_choose`.

## 3. Behaviours

**JRK-B1 Raise on engine code.** Given levels `[base: medium, code: large]` and a rule that returns `code` when `git.paths_by_glob(["src/**"]) > 0` and else `base`, when an attempt changes `docs/a.md` and `src/x.py`, then the judge runs on `large` with `chosen_by: rule` and signals `{src_paths: 1}`; when an attempt changes only `docs/a.md`, it runs on `medium`.

**JRK-B2 Fault takes the strongest level.** Given the same levels, when the rule raises `KeyError`, then the judge runs on `large`, `chosen_by: fault`, with the exception type recorded; the run continues.

**JRK-B3 Floor after escalation.** Given levels `[base: medium, code: large]`, a rule that returns `base`, and an attempt whose producer ran on `large` by `escalation:+1`, when the judge resolves, then it runs on `large` with `chosen_by: floor`.

**JRK-B4 Shadow.** Given `mode: shadow` and a rule that returns `code`, when the judge resolves, then it runs on level 0 and the record holds `would_choose: code`.

**JRK-B5 Stable needs every level.** Given a workflow in stable mode whose gate has `risk` in `route` mode with level `code` `unscored`, when it is validated, then it is refused with the gate, the level and the `evals score` command that fixes it.

| Mode | Level 0 | Level 1 | Stable mode |
|---|---|---|---|
| route | accepted | accepted | allowed |
| route | accepted | unscored | refused |
| shadow | accepted | unscored | allowed |

## 4. Error conditions

| Condition | Result |
|---|---|
| A level at a lower tier than the level before it, or equal in both model and effort | Validation error |
| A level model that preflight cannot bind | Preflight exit 2, naming the gate and level |
| `risk` on a council member, chair, contest slot or the audit judge | Validation error: those bindings are fixed by their own specs |
| The rule reads a field outside `RiskContext` | Not possible: the context carries no other field |
| A rule slower than 1 s | Treated as a fault (JRK-B2), recorded with the time |

## 5. Design notes

- Only up: a cheaper judge for "low-risk" work is the agreeable-judge hazard in a new form ([R-045](../research/R-045-evaluating-llm-judges-public-practice.rsrch.md) F2).
- The sampled audit judge ([JDG-B7](05-judge-and-verdict.spec.md)) audits whatever level graded the attempt; its agreement is recorded per level.
- A risk rule is a cost bet like a switch ([SWM](79-measured-switches.spec.md)), so it has the same shadow mode, and moving a threshold is a `judge_model` proposal of class `grader` measured by a trial ([PRP §2.3](40-improvement-proposals.spec.md)).

## 6. Acceptance criteria

- [ ] JRK-AC-1 JRK-B1 to JRK-B5 and every row of the JRK-B5 table hold offline with scripted executors.
- [ ] JRK-AC-2 No fixture makes a judge run below level 0, or below the producer's escalated tier.
- [ ] JRK-AC-3 A rule given a context built from a step whose artifacts contain the word "trivial" picks the same level as from an empty artifact (the rule cannot read them).
- [ ] JRK-AC-4 `evals bar` lists a state per level, and a change to any level's model or effort makes that level, and only it, `stale`.

## Open questions

| Question | Owner | Default |
|---|---|---|
| Should the engine ship stock rules (paths by glob, lines changed) so a workflow declares only thresholds? | Owner | Yes, as helpers in the builder library; a workflow may still write its own |

## References

[JDG](05-judge-and-verdict.spec.md) · [JCL](50-judge-calibration.spec.md) · [FBK](41-feedback-and-judge-reliability.spec.md) · [LAD](92-effort-ladder-and-model-escalation.spec.md) · [SWM](79-measured-switches.spec.md) · [R-121](../research/R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md)
