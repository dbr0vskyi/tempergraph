---
title: Audit rule catalog
type: component
status: ready-for-implementation
prefix: ARC
adrs: [0051, 0053, 0054, 0063, 0064, 0066]
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
| `judge-not-ready` | definition | per owner | — | The readiness report grades a gate `needs cases` or `needs work`, or judge calibration has not accepted its judge on the bound executor and alias | owner: [LIF](18-lifecycle-and-evals.spec.md) readiness; judge acceptance in [JCL](50-judge-calibration.spec.md) |
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
| `interventions-per-run` | history | info / high | `person_rate` *new* | Undesigned touches (rescue and steer, by every decider: person, agent, unknown; approvals apart, [SUP §2.1](86-supervision-metrics.spec.md)) exceed 1.0 per run; `min_n` 5 runs | The report splits them by class, pause kind and decider; the leading kind names the rule to read |
| `supervision-cost-share` | history | warning / medium | `supervision_heavy` *new* | Median supervision share above 10% ([SUP §2.2](86-supervision-metrics.spec.md)); `min_n` 5 runs with measured supervision cost | The report splits the cost by category; the leading one names the fix (watch and rewake: wait in the background; diagnose: the failure rule it points to) |
| `polling-supervisor` | history | warning / high | `supervisor_polling` *new* | Observations per run above 20, or `rewake` above half the supervision cost ([SCO §2.4](87-supervision-cost.spec.md)); `min_n` 5 runs | Wait on the run's exit or `orchestrate wait` in the background instead of polling ([ADR-0037](../adr/0037-attention-batched-waking-of-the-orchestrating-session.adr.md)) |
| `callers-unknown` | history | info / high | `caller_unknown` *new* | More than 20% of touches have caller `unknown`; `min_n` 10 touches | Run through a marked host, or declare the caller (`--caller`, `--caller-app`); supervision figures are weak until then |

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
| `outcome-unverified-blocker` | definition | warning / high | `outcome_unverified` *new* | A blocker of the good outcome has trust `unverified` or `uncalibrated` ([OUT §2.3](90-run-outcome.spec.md)) | Find a verifier by the search order of [AUT §2.4](89-workflow-authoring.spec.md), or make it a sign-off |
| `outcome-uncovered` | definition | warning / high | `outcome_uncovered` *new* | A final criterion is not covered (OUT §2.3) | Add a serving criterion on the units before the outcome gate, or verify it at the outcome gate |
| `outcome-escapes` | history | warning / medium | `outcome_escape` *new* | Escape rate ≥ 10% of graded runs; `min_n` 10 ([OUT §2.5](90-run-outcome.spec.md)) | Revise the outcome: `outcome candidates`, then revise mode |
| `engine-fault-open` | history | info / high | — | Open engine-side or executor-side findings of the loop name this workflow's units | owner: [SIL](16-self-improvement.spec.md); shown so the author does not chase them in the workflow |

### 2.9 Rules for the newer unit kinds

Each rule keeps its R-050 family; they are listed together because they read fields of the kinds in [SCR](70-script-units-and-hybrid-steps.spec.md), [CNL](71-council-unit.spec.md), [CTS](72-contest-unit.spec.md), [ASK](73-ask-unit.spec.md) and [FLX](74-flow-extensions.spec.md). Their thresholds rest on [R-061](../research/R-061-councils-debate-and-voting.rsrch.md), not on a baseline measurement, and are revisited with the first 10 visits.

| id | family | layer | sev / conf | cause | Fires when | Remedy |
|---|---|---|---|---|---|---|
| `council-one-family` | C1 | definition | warning / medium | `council_monoculture` *new* | Every member of a council binds to one model family (`Capabilities.families`) | Put at least one member on another family or give members distinct stances; same-family members share errors (R-061 K3, K6) |
| `council-even-majority` | C5 | definition | info / high | `tie_prone` *new* | A `vote` council with `rule: majority` has an even member count | Use an odd count, or `plurality`; ties pause for a person |
| `council-rounds-no-gain` | C6 | history | warning / medium | `rounds_no_gain` *new* | A council with `rounds > 0` changed its outcome in a later round in < 5% of visits; `min_n` 10 visits | Set `rounds: 0`; independent answers and a vote carry most of the gain (R-061 K2) |
| `council-conformity` | C1 | history | info / low | `council_conformity` *new* | In ≥ 80% of rounds after round 0, every member that changed moved to the round-0 majority; `min_n` 10 rounds | Check stances and anonymity; a majority may be pulling members, not evidence (R-061 K4) |
| `contest-identical-slots` | C6 | definition | warning / high | `contest_no_diversity` *new* | Every slot of a contest shares executor, model and prompt | Vary model, executor or `prompt_variant`, or use a single step with retries |
| `contest-no-gain` | C6 | history | warning / medium | `contest_no_gain` *new* | The slot with the lowest number won ≥ 90% of picks; `min_n` 10 visits | The other slots add cost but rarely win: reduce `slots` |
| `fallback-rate` | C1 | history | warning / high | `fallback_heavy` *new* | A gate took its `fallback` in ≥ 30% of visits; `min_n` 5 visits | The unit fails more than it passes; read its `loop-driver-criterion` and `low-first-pass` findings |
| `unbounded-wait` | C5 | definition | info / medium | `wait_unbounded` *new* | A `wait` or `ask` has no `deadline_s` and the workflow's `improvement_mode` is `stable` | Add a deadline and an `on_deadline` so overdue pauses show in `attention` |
| `external-after-without-approval` | C7 | definition | warning / high | `publish_before_review` *new* | An `after` script with `side_effects: external` runs on a step whose gate has no approval | Move publishing to the finalizer or a script unit after an approval ([ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)) |

C4 rules are in [TSA §2.4](57-tool-surface-audit.spec.md). The prompt rules that resolve names against the host, check staleness, compare text with declarations and measure size are in [PRA §2.3](58-prompt-audit.spec.md).

### 2.10 Release 1

The catalog is `tempergraph.audit.catalog`: every row above, with `built` naming its release. Release 1 runs the `definition` and `host` rules; history rules are listed as skipped (AUD §2.5). Decisions made while building, recorded here as the spec:

| Rule or part | Release 1 |
|---|---|
| `min_n` | A history rule with no minimum named above has `min_n` 1 ("any run in the window") |
| `slow-host` | The host-speed probe times `$SHELL -lc true` against `$SHELL -c true`. Besides the 15 s rule, the five-times ratio counts only above a floor of 1 s (`slow_login_shell_floor_s`), because a login shell is always several times a plain one in milliseconds |
| `check-program-missing`, `toolchain-not-covered` | Read the workflow's `allow_commands` and each step's `commands`; the program is the prefix's first word. With a `command_resolver` both are skipped with reason `command_resolver output is not read in release 1` (the run's command runner uses no custom resolver yet). `toolchain-not-covered` reads `package.json` scripts, `Makefile` targets and the presence of `pyproject.toml`, `go.mod` and `Cargo.toml`, each covered by its own programs (npm, yarn, pnpm, node, bun; make; python, pytest, uv and the like; go; cargo), and fires only when the workflow declares commands or a gate has a check |
| `interpreter-cannot-import`, `worktree-env-outside-worktree` | Skipped: WFM declares no interpreter in release 1 |
| `hold-time-exposure` | Steps use `timeout_s` or the engine's 600 s, script units their `timeout_s`; a unit with no check and no judge has one attempt |
| `single-criterion-gate-judge-only` | A fixed pattern over the criterion text (a file or folder that exists, a command or tests that pass, a git fact) on a gate with no check |
| `small-judge-cross-file`, `large-everywhere` | The tier is the alias's last part (`small`, `haiku`; `large`, `opus`); a step's model falls back to its `model_profile` entry |
| `judge-not-ready` | Rendered from the readiness report as `readiness:needs-work` (warning, high) and `readiness:needs-cases` (info, high: before JCL no judge is `accepted`, so every gate is `needs cases`) |
| `external-after-without-approval` | Owned by validation, which already warns on it (`validate:external-after-without-approval`) |
| `outcome-unverified-blocker`, `outcome-uncovered` | Read OUT's trust and coverage from `tempergraph.run.outcome_trust` (OUT §2.3 as read in [SCF §2.7](91-blueprint-and-scaffold.spec.md)). Before calibration (JCL, plan T12) every judged blocker is `uncalibrated`, so the first rule fires on each; that is the true state, and the remedy names calibration |
| §2.9 kinds | Not built; validation refuses their kinds in release 1 (`unbounded-wait` waits on `wait` and `ask`, release 2) |
| `ignore-rule-unknown` | New, `info / high`, AUD §2.4's finding for an ignore naming no known rule |

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
| An owner component is not available in this engine (for example the activity journal of spec 30 before it merges) | The owned rule is skipped with reason `owner not present` |
| Two rules fire on the same field for the same cause | Both shown; the lower-ranked one cites the higher |

## 5. Design notes

- One rule, one cause. A rule that would need prose judgement (whether a criterion holds on a second visit, whether a document is stale) is not in the catalog: that is a judge's work, and C13 keeps models out of the audit ([ADR-0050](../adr/0050-advisory-read-only-audit-verb-in-three-layers.adr.md)).
- The cause codes marked *new* are additions to SIL's list. SIL classes each `fault`, `infra` or `designed`; the audit reports the class SIL gives.
- Several R-050 findings stay engine work and get no rule: concurrent writer limits, orphaned sessions, how a retry resumes. A workflow cannot change them.

## 6. Acceptance criteria

Release 1 (2026-11-20, `tests/test_audit.py`): AC-1 to AC-4 hold; AC-5 holds for ARC-B2, and ARC-B3 waits on the history layer.

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
