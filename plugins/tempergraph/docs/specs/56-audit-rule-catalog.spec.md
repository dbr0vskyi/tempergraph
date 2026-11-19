---
title: Audit rule catalog
type: component
status: review
prefix: ARC
adrs: [0051, 0053, 0054]
---

# Audit rule catalog

## 1. Overview

The fixed list of rules the [workflow audit](55-workflow-audit.spec.md) applies, outside the tool surface rules of [TSA](57-tool-surface-audit.spec.md). Each rule answers one cause ranked in [R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md), names the layer it needs, carries a cause code shared with the self-improvement loop, and has a default severity, confidence and remedy. Rules owned by another component are listed with their owner and run through it ([ADR-0054](../adr/0054-audit-joins-existing-checks-and-files-nothing.adr.md)). The catalog is engine data, versioned with the engine; a workflow cannot add or change a rule, only ignore one with a reason ([AUD §2.4](55-workflow-audit.spec.md)).

## 2. Contract

### 2.1 Rule record

| Field | Meaning |
|---|---|
| `id` | Stable kebab-case slug; never reused, a rename keeps an alias |
| `layer` | `definition`, `host` or `history` (one; a cause seen in two layers has two rules) |
| `family` | R-050 family `C1`…`C8` |
| `cause` | Cause code from the self-improvement list ([SIL §2.3](16-self-improvement.spec.md)); codes marked *new* below are added to that list, which SIL owns |
| `severity` | `error` (a run will very likely fail, pause or be voided), `warning` (likely to cost attempts, time or money), `info` |
| `confidence` | `high` (a fact), `medium` (a shape that usually causes the cause), `low` (a heuristic) |
| `owner` | `audit` or the owning component; an owned rule is only rendered |
| `min_n` | History rules: minimum runs (or visits, attempts, as named) in the window before the rule may fire |
| `remedy` | Fixed text naming the field to change and the kind of change; never a generated patch |


### 2.2 Rank

Rules are ranked by family in R-050 order (C1 highest) and, within a family, by the order of the tables below. The rank only breaks ties after severity and confidence.

### 2.3 C1 Gate send-back loops

| id | layer | sev / conf | cause | Fires when | Remedy |
|---|---|---|---|---|---|
| `oversized-step` | definition | warning / medium | `oversized_step` *new* | A gate has more than 8 blocker criteria, or the step produces more than 3 artifact keys of kind `file`, or the rendered template without inputs exceeds 24,000 characters | Split the step into passes (design, then tables); give each pass its own gate (R-050 F1.2: yield 29% → 62%) |
| `no-change-blocker-retries` | definition | warning / high | `no_change_retry` *new* | A blocker has `no_change_policy: retry` | Keep the default `escalate`: a retry cannot fix what the step's output cannot change (F1.4) |
| `unverified-blocker` | definition | warning / high | `unverifiable_blocker` *new* | A blocker names an `unverified_system` | Give the judge a view of that system, move the fact to a check, or make it a warning: as a blocker it is always UNVERIFIABLE |
| `single-criterion-gate-judge-only` | definition | info / low | `prefer_check` *new* | A criterion's text names a file's existence, a command's result or a git fact, and the gate has no check | Make it a check (SHL-B4) |
| `loop-driver-criterion` | history | error / high | `retry_burst` | One criterion id is the leading unmet blocker in ≥ 50% of a gate's RETRY verdicts, with ≥ 5 RETRYs, and the gate's repeats are ≥ 20% of the workflow's spend; `min_n` 5 runs | Name the criterion; the remedy text lists: split the step, reword so a second visit can meet it, or move it to a check. The improvement backlog clusters on the same id |
| `low-first-pass` | history | warning / high | `low_first_pass` *new* | A gate passes on the first attempt in < 50% of visits; `min_n` 5 visits | Read `loop-driver-criterion` for the gate; consider a split |
| `no-change-retried` | history | warning / high | `no_change_retry` *new* | A RETRY whose unmet blockers are all `no_change` (only possible with policy `retry`) | As `no-change-blocker-retries` |
| `repeated-check-evidence` | history | warning / medium | `retry_cannot_fix` *new* | Within one visit, two or more check FAILs with the same evidence digest followed by a new attempt | Mark the failure environmental in the check, or fix the environment; a rerun will fail the same way (R-050 F2.1) |
| `missing-field-rendered` | history | error / high | `missing_input` *new* | A step record shows a `⟨missing:name⟩` marker | Supply the input or make the template field optional; the model saw a marker, not the value (F1.5, F7.1) |
| `judge-not-ready` | definition | per owner | — | The readiness report grades a gate `needs cases` or `needs work`, or judge calibration has not accepted its judge on the bound executor and alias | owner: [LIF](18-lifecycle-and-evals.spec.md) readiness; judge acceptance in spec 50 JCL (PR 6) |
| `brief-rule-branching` | definition | per owner | — | A brief branches on facts a check could compute | owner: [WFM §2.2](02-workflow-model.spec.md) |
| `criterion-without-method` | definition | per owner | — | A criterion has no `check_method` | owner: [WFM §2.2](02-workflow-model.spec.md) |

### 2.4 C2 Environment and infrastructure

| id | layer | sev / conf | cause | Fires when | Remedy |
|---|---|---|---|---|---|
| `check-program-missing` | host | error / high | `environment_missing` *new* | The program of a declared command prefix (after `command_resolver`) is not found on `PATH` or is not executable | Install it, or change the prefix or resolver; the check would run nothing (F2.4) |
| `interpreter-cannot-import` | host | error / high | `environment_missing` *new* | A declared interpreter resolves (workspace, main checkout, engine, in that order) but cannot import the test runner the check names | Install the runner in that environment (F2.2: 17 of 20 code gates ended at a person) |
| `toolchain-not-covered` | host | warning / medium | `toolchain_not_covered` *new* | The target repository documents build or test commands (contributor notes, `package.json` scripts, `Makefile`, `pyproject.toml`, `go.mod`, `Cargo.toml` and similar) and no declared prefix or resolver output covers any of them | Add a `command_resolver` or declare the repository's commands (F2.4) |
| `worktree-env-outside-worktree` | host | warning / medium | `stale_import` *new* | The workflow uses worktrees and the declared interpreter's environment has an editable install pointing at the main checkout of a package the steps change | Resolve the interpreter inside the worktree, or install non-editable (F2.7) |
| `slow-host` | host | warning / high | `slow_host` | The host-speed probe finds a login shell above 15 s, or more than five times a plain shell | Fix the host before running; timeouts on it are classed `slow_host` and spend no retries (F2.5) |
| `check-ran-nothing` | history | error / high | `blocked_without_check` | A check's evidence records every declared command as not run, in any run of the window; `min_n` 1 | As `toolchain-not-covered`; this is a fault, not a designed pause (F2.4) |
| `infra-heavy` | history | warning / medium | `infra_heavy` *new* | Infra tries are ≥ 10% of attempts on this host; `min_n` 20 attempts | Read the leading `infra_cause`; `prompt_not_delivered` or `broken_pipe` points at host load (F2.6) |
| `executor-outside-tested-range` | host | per owner | — | An executor's version is outside its compatibility table | owner: [LIF](18-lifecycle-and-evals.spec.md) executor compatibility |

### 2.5 C3 Timeouts, stalls and hangs

| id | layer | sev / conf | cause | Fires when | Remedy |
|---|---|---|---|---|---|
| `default-step-timeout` | definition | warning / high | `default_timeout` *new* | A step sets no `timeout_s` and the workflow sets no default, so the engine's 600 s applies | Set a limit near the p90 of the same work (F3.4, F3.6) |
| `default-judge-timeout` | definition | info / high | `default_timeout` *new* | A judge sets no `timeout_s` and the workflow no judge default | As above; a judge never takes the step's limit |
| `idle-limit-inert` | definition | warning / high | `idle_inert` *new* | `idle_s` ≥ the resolved `timeout_s` | Lower `idle_s` below the wall limit, or remove it; it can never fire |
| `no-idle-limit` | definition | info / medium | `no_idle_limit` *new* | A step with `timeout_s` above 1,800 s has no `idle_s` | Declare one below the wall limit, above the longest silent tool call (F3.5) |
| `hold-time-exposure` | definition | warning / high | `hold_exposure` *new* | For a unit, `timeout_s × (retry_budget + 1)` plus `timeout_s × infra tries` exceeds 4 h; or the sum over `order` exceeds 12 h | Lower the limit, the budget, or set an idle limit; the report prints the hours (F3.5: 6 h on one unit) |
| `timeout-below-pass-p90` | history | error / high | `timeout_too_short` *new* | A step or judge limit is below 1.25 × the p90 duration of its passing attempts; `min_n` 5 passing attempts | Set it to about 1.5 × that p90; the report prints the figure (F3.4) |
| `attempts-at-limit` | history | warning / high | `timeout_share` *new* | ≥ 20% of a unit's attempts end timed out or stalled; `min_n` 5 attempts. The evidence splits them by tool share: ≥ 60% tools (slow host), one long call in flight (hung), model silent | By split: slow host → `slow-host`; hung → idle limit; model → write in parts (F3.2, F3.7) |
| `limit-far-above-p90` | history | info / medium | `timeout_loose` *new* | A limit is above 4 × the p90 of passing attempts; `min_n` 5 | Lower it: a hang holds the run for the whole limit on every attempt |
| `request-timed-out` | history | warning / high | `request_timed_out` | Any `request_timed_out` infra cause for a step in the window | Write the long output in parts so no response nears the window; the report gives the step's largest single response (F3.3: 87.6 KB) |

### 2.6 C5 Pauses that add nothing

| id | layer | sev / conf | cause | Fires when | Remedy |
|---|---|---|---|---|---|
| `every-retry-asks` | definition | warning / high | `ask_without_budget` *new* | A gate has `retry_budget: 0` and `on_budget_spent: ask` | Give one retry, or `stop`; every RETRY pauses for a person |
| `approval-on-most-gates` | definition | info / medium | `approval_heavy` *new* | `approval` is set on more than half the gates | Keep approval where a person decides something a judge cannot |
| `empty-pauses` | history | warning / medium | `empty_pause` *new* | ≥ 50% of a gate's pauses end in `proceed` with no feedback and no workspace change; `min_n` 4 pauses | The pause adds nothing: mark the cause environmental, fix the environment, or stop instead (F5.3: 13 of 16) |
| `interventions-per-run` | history | info / high | `person_rate` *new* | Person interventions (escalations and budget pauses, approvals apart) exceed 1.0 per run; `min_n` 5 runs | The report splits them by kind; the leading kind names the rule to read |

### 2.7 C6 Cost shape

| id | layer | sev / conf | cause | Fires when | Remedy |
|---|---|---|---|---|---|
| `small-judge-cross-file` | definition | warning / medium | `model_too_small` *new* | A judge or review step on tier `small` has references or subject spanning more than one artifact | Use `medium` or `large` for reading across files (F6.4: 5 of 19 against 18 of 19) |
| `large-everywhere` | definition | info / low | `model_heavy` *new* | Every step and judge resolves to `large` | Choose models by what each step must find; start mechanical steps lower |
| `no-run-cost-cap` | definition | info / high | `no_cost_cap` *new* | `run_cost_cap_usd` unset and `improvement_mode` is `stable` | Set a cap near the p90 run cost |
| `context-heavy-step` | history | warning / medium | `context_heavy` *new* | A step's median `peak_context_tokens` exceeds 150,000, or ≥ 50% of its cost is in turns above 200,000; `min_n` 5 attempts | Split the step or narrow what it reads (F6.3) |
| `cost-lens-rules` | history | per owner | per rule | The cost lens's model-free rules over the same window: repeat share, retries after a deterministic check, recurring blocker, judge against step cost, an expensive model whose judge never blocked, an unpriced gate | owner: [SIL §2.2](16-self-improvement.spec.md) cost lens; the audit calls the same functions and shows their findings |

### 2.8 C7 Prompt defects and C8 engine side

| id | layer | sev / conf | cause | Fires when | Remedy |
|---|---|---|---|---|---|
| `prompt-lint` | definition | per owner | per rule | Prompt lint's findings over templates, briefs and the skills a step names | owner: [LIF](18-lifecycle-and-evals.spec.md) prompt lint |
| `template-grammar` | definition | per owner | — | Validation's prompt rows | owner: [WFM §2.1](02-workflow-model.spec.md) |
| `engine-fault-open` | history | info / high | — | Open engine-side or executor-side findings of the loop name this workflow's units | owner: [SIL](16-self-improvement.spec.md); shown so the author does not chase them in the workflow |

C4 rules are in [TSA §2.4](57-tool-surface-audit.spec.md).

## 3. Behaviours

**ARC-B1 Owned rules are rendered.** Given the cost lens reports "judge against step cost" for gate `verify` over the window, when the audit runs history, then the finding carries the cost lens's code and numbers, owner `SIL`, and the audit computes nothing of its own for it.

**ARC-B2 Hold-time arithmetic.** Given unit `code` with `timeout_s` 7,200, `retry_budget` 2 and the default 3 infra tries, when `hold-time-exposure` runs, then it reports 7,200 × 3 + 7,200 × 3 = 12 h for the unit and fires.

| timeout_s | retry_budget | infra tries | Unit hold | Fires |
|---|---|---|---|---|
| 600 | 2 | 3 | 1 h | no |
| 3,600 | 2 | 3 | 6 h | yes |
| 7,200 | 2 | 3 | 12 h | yes |

**ARC-B3 Timeout fit.** Given step `plan` with limit 600 s and 8 passing attempts whose p90 is 540 s, when `timeout-below-pass-p90` runs, then it fires (600 < 1.25 × 540 = 675) and recommends about 810 s.

**ARC-B4 New cause codes join the loop.** Given an audit finding with cause `oversized_step` on unit `plan` and a later friction finding of the same cause on `plan`, when the improvement backlog clusters findings, then both fall in one cluster keyed by side, workflow, unit and cause.

**ARC-B5 Remedy, never a patch.** Given any rule, when it fires, then its remedy names a field and a kind of change, and no file content or diff is produced.

## 4. Error conditions

| Condition | Result |
|---|---|
| A rule's input is missing (no probe, no runs) | Rule skipped with reason; never counted as passed |
| An owner component is not available in this engine (for example judge calibration before PR 6 merges) | The owned rule is skipped with reason `owner not present` |
| Two rules fire on the same field for the same cause | Both shown; the lower-ranked one cites the higher |

## 5. Design notes

- One rule, one cause. A rule that would need prose judgement (whether a criterion holds on a second visit, whether a document is stale) is not in the catalog: that is a judge's work, and C13 keeps models out of the audit ([ADR-0050](../adr/0050-advisory-read-only-audit-verb-in-three-layers.adr.md)).
- The cause codes marked *new* are additions to SIL's list. SIL classes each `fault`, `infra` or `designed`; the audit reports the class SIL gives.
- Several R-050 findings stay engine work and get no rule: concurrent writer limits, orphaned sessions, how a retry resumes. A workflow cannot change them.

## 6. Acceptance criteria

- [ ] ARC-AC-1 Every rule has an `id`, `layer`, `family`, `severity`, `confidence`, `owner` and `remedy`, and every history rule a `min_n`, checked by a catalog schema test.
- [ ] ARC-AC-2 Every R-050 family C1 to C7 has at least one rule here or in TSA; C8 is listed as engine-side.
- [ ] ARC-AC-3 Each threshold is a named parameter with its default and the R-050 finding it comes from.
- [ ] ARC-AC-4 Owned rules call the owning component's function; a source test fails if an owned rule's logic is reimplemented in the audit.
- [ ] ARC-AC-5 ARC-B2 and ARC-B3 hold as table tests.

## Open questions

| Question | Owner |
|---|---|
| Is 24,000 characters the right size signal for `oversized-step`, or should it be the step's recorded output size from history? | First runs |
| Should `toolchain-not-covered` read a repository's CI configuration as a documented command source? | Owner |

## References

[AUD](55-workflow-audit.spec.md) · [TSA](57-tool-surface-audit.spec.md) · [R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) · [SIL](16-self-improvement.spec.md) · [BUD](08-budgets-and-failures.spec.md)
