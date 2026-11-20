---
title: Run-level good outcome
type: component
status: ready-for-implementation
prefix: OUT
adrs: [0031, 0045, 0089, 0107, 0108, 0111, 0114]
---

# Run-level good outcome

## 1. Overview

Every workflow states what a **good outcome** of one run is, and everything that grades a run grades against it ([R-011 G1](../research/R-011-design-gap-review.rsrch.md), goal G1). The good outcome is one data file in the package, `outcome.json` ([PKG §2.1](88-workflow-package.spec.md)), written first during authoring ([AUT](89-workflow-authoring.spec.md)) and revised after runs have been graded ([ADR-0107](../adr/0107-the-good-outcome-is-one-data-file-of-final-and-intermediate-outcomes.adr.md)). It holds:

- the **final outcome**: a statement of the good end state, the deliverables, and the final criteria;
- one **intermediate outcome** per unit: what that unit's result must be for the final outcome to be reachable, with its criteria;
- for **every criterion**, who verifies it: a script check, a judge, a person, or nobody yet, and for "nobody", why.

Step gates take their criteria from the intermediate outcomes. A final **outcome gate** grades the run against the final criteria before the finalizer ([ADR-0108](../adr/0108-a-run-is-measured-at-a-final-outcome-gate.adr.md)). Each run leaves an **outcome record**; the workflow's outcome measures are computed from those records and from what people said afterwards. A criterion that nothing trustworthy verifies is shown on every report, never passed silently. Revisions follow the grader-side rules of [ADR-0031](../adr/0031-steps-and-their-graders-change-apart.adr.md): weakening is a person's act, and a verifier moves up the ladder from person to judge to check only on measured evidence ([ADR-0111](../adr/0111-outcome-revisions-are-grader-changes-and-verifiers-climb-a-ladder.adr.md)).

## 2. Contract

Types are in [CON §2.14](01-contracts.spec.md).

```python
def read_outcome(package_path: Path) -> OutcomeSpec | list[Finding]: ...       # model-free
def gate_criteria(outcome: OutcomeSpec, unit: str) -> list[Criterion]: ...      # PKG §2.3 step 5
def check_against(outcome: OutcomeSpec, spec: WorkflowSpec) -> list[Finding]: ... # the unit rows of §4
def outcome_record(state: RunState, outcome: OutcomeSpec) -> OutcomeRecord: ...
```

### 2.1 The outcome file

| Field | Kind | Meaning |
|---|---|---|
| `schema_version` | int | `1` |
| `revision` | int ≥ 1 | Grows by one with every change of this file (§2.6) |
| `statement` | 1 to 3 sentences | The good end state in the person's words, observable, no request literal |
| `deliverables` | list of `{key, kind, where}` | The artifacts a good run leaves: artifact keys of final state ([CON §2.1](01-contracts.spec.md) `produces`) and where they land (a branch, a folder, a wiki space) |
| `final` | list of `OutcomeCriterion`, at least one | Graded by the outcome gate (§2.4) |
| `intermediate` | map unit → `{statement, criteria: list of OutcomeCriterion}` | One per model step and per script unit with a gate; graded by that unit's gate |
| `judge` | `{stance, brief_file?, references[], executor?, model?}`, optional | The outcome judge; defaults in §2.4 |
| `check` | callable ref, optional | The outcome check, `(ctx: CheckContext) -> CheckResult` over final state ([PKG §2.4](88-workflow-package.spec.md)) |
| `assumptions` | list of text | What authoring assumed and the person did not settle ([AUT §2.5](89-workflow-authoring.spec.md)) |
| `revisions` | list of `OutcomeRevision` | Metadata of every change (§2.6), newest last |

`OutcomeCriterion` is a `Criterion` ([CON §2.1](01-contracts.spec.md): `id` required here, `text`, `check_method`, `severity`, `no_change_policy`, `unverified_system`) plus:

| Field | Kind | Meaning |
|---|---|---|
| `verified_by` | `check` \| `judge` \| `person` \| `none` | Who decides its status (§2.2) |
| `verifier` | per class, see §2.2 | What does the verifying |
| `source` | `existing:<kind>` \| `example` \| `interview` \| `created` | Where the criterion and its verification came from; `<kind>` is one of `test`, `linter`, `type_check`, `schema`, `checklist`, `acceptance_criteria`, `definition_of_done`, `review_rule`, `template`, `style_guide`, `other` ([AUT §2.4](89-workflow-authoring.spec.md)) |
| `serves` | list of final criterion ids | For an intermediate criterion: the final criteria it makes reachable. Empty means it serves the unit's own work only |
| `trust` | computed, never written | §2.3 |

### 2.2 Verifier classes

| `verified_by` | `verifier` holds | Graded by | Rule |
|---|---|---|---|
| `check` | `{check: ref}`, `{command: prefix}`, or `{primitive: <helper>, artifact: <key>, …}` naming a check helper of [SCF §2.4](91-blueprint-and-scaffold.spec.md), with the finding it expects | The gate's check ([CHK](75-check-contract-and-command-runs.spec.md)); sets `mechanical: true` on the criterion | The check must name the criterion id in its findings; a check that never names it is `check-criterion-unnamed` (validation, from the check's fixtures) |
| `judge` | `{references: [keys], read_systems?: [names], scale}` | The unit's judge, or the outcome judge for a final criterion | `check_method` and a complete `scale` required (§2.2.1) |
| `person` | `{role, question}`: who signs it off ("release manager") and the yes/no question shown | A sign-off: the approval pause of the unit (or of the outcome gate) lists these criteria and records a status per criterion ([HUM](07-gate-and-human.spec.md)) | The pause is designed supervision ([SUP §2.1](86-supervision-metrics.spec.md)); a criterion never answered is `not_verified` |
| `none` | `{reason, risk}` | Nobody | Allowed only as a recorded decision ([AUT §2.4](89-workflow-authoring.spec.md)); listed on every report (§2.5). A `blocker` with `none` is a validation warning in `dev` and an error in `stable` |

#### 2.2.1 The scoring scale of a judged criterion

The judge's statuses and the verdict rule are fixed engine-wide ([CON §2.8](01-contracts.spec.md), [JDG §2.2](05-judge-and-verdict.spec.md)); what each status **means for this criterion** is written by the author, so two judges, or one judge twice, grade the same output the same way ([ADR-0114](../adr/0114-judged-criteria-carry-a-scale-and-authoring-guides-until-criteria-are-clear.adr.md)).

| `scale` field | Holds | Rule |
|---|---|---|
| `met` | What a result that fully meets the criterion shows, in observable terms | Required |
| `partial` | What counts as partly met, and where the line to `met` is | Required for a blocker; for a criterion with no middle ground, the fixed text "no partial: any gap is UNMET" |
| `unmet` | The typical failure, phrased so a reviewer would recognise it | Required |
| `evidence` | What the judge must cite for `met`: a quote, a path and line, a count, a command result | Required; `MET` without it is `PARTIAL` already (JDG §2.2) |
| `n_a` | When the criterion does not apply, if ever | Optional; absent means N/A is never valid and is read as UNMET |
| `seeds` | Ids of fixtures in `evals/calibration/<gate>/`: at least one expected `met` and one expected `unmet` or `partial` | Required before `author verify` rung 8, which grades them ([SCF §2.5](91-blueprint-and-scaffold.spec.md)) |

The judge prompt renders each criterion's `met`, `partial`, `unmet` and `evidence` beside its check method ([JDG §2.1](05-judge-and-verdict.spec.md)); the step sees only the criterion text and `met` as its target, never the check method or the failure descriptions. A reworded scale stales the judge's score for that criterion, as a reworded text does (§2.6).


### 2.3 Trust and coverage

The engine computes, never stores, a **trust** per criterion from its class and the state of its verifier:

| Trust | When |
|---|---|
| `deterministic` | `check`, with at least one must-pass and one must-fail fixture ([EVS §2.2](51-eval-suites.spec.md)) |
| `calibrated` | `judge` whose binding is `accepted` on cases that name this criterion ([JCL §2.5](50-judge-calibration.spec.md)) |
| `uncalibrated` | `judge` in any other state, or `check` without both fixtures |
| `human` | `person` |
| `unverified` | `none` |

**Coverage** of a final criterion is the set of intermediate criteria that serve it, with their trust. A final criterion is **covered** when the outcome gate verifies it at `deterministic`, `calibrated` or `human` trust, or when it has no verifier of its own at the outcome gate and every unit on every path to the outcome gate has a serving criterion of such trust. `outcome show` prints the trust profile (counts per trust) and the coverage table; the audit reads both ([AUD](55-workflow-audit.spec.md), rules `outcome-uncovered`, `outcome-unverified-blocker`).

### 2.4 The outcome gate

| Part | Rule |
|---|---|
| Place | A unit named `outcome`, compiled after every unit and before the finalizer; every path that reaches the finalizer passes it ([CMP §2.2](03-compiler-and-flow.spec.md)). The name is reserved |
| Step node | No session: it assembles the subject from final state (the deliverables' pointers, values, facts, git facts) and records it |
| Check | `outcome.json` `check`, if any, plus a built-in check that every deliverable exists (a file present, a URL recorded, a value set) |
| Person | When any final criterion is `person`, a sign-off (approval pause) after check and judge pass, listing those criteria |
| Failure | A blocker UNMET or PARTIAL sends the run back to the earliest unit whose serving criterion of that final criterion is on the path (`serves`), with the judge's reason; loop budget 1 per target, then the gate's `on_budget_spent` (default `ask`). With no serving unit, the run escalates. Back targets are derived, never declared |
| Mode | In `dev`, the judge runs on every run. In `stable`, setting `outcome.judge` (`always` default, or `on_trigger` with the stable triggers of the outcome lens, [SIL §2.2](16-self-improvement.spec.md)); a run where the judge did not run records its judge criteria as `not_judged` |

Compiled form: the engine adds the `outcome` unit to the run-time spec with no session, `retry_budget` 0 (a retry has nothing to redo) and `loop_budget` 1. Its gate grades the final criteria verified by `check` or `judge`; `person` criteria go into the approval payload as `sign_off` (id, text, role, question); `none` criteria are graded by nobody and reach the outcome record. A failing check, such as a missing deliverable, routes like a failing blocker: when it names no final criterion, every final criterion counts as failing for the `serves` lookup.

The outcome gate is what the self-improvement outcome lens reads: the lens takes the outcome record instead of starting a second judge, so the step gates, the outcome gate and the loop share one bar ([SIL §2.2](16-self-improvement.spec.md)).

### 2.5 The outcome record and the workflow's measures

One `OutcomeRecord` per thread: a run-log record `outcome` at the outcome gate and the ledger row's `outcome{}` ([CON §2.14](01-contracts.spec.md)).

| Field | Meaning |
|---|---|
| `revision` | The `outcome.json` revision the run graded against |
| `verdict` | `met` (every blocker MET), `met_with_open` (blockers met, a warning unmet or a criterion `not_verified`, `not_judged` or `none`), `unmet`, `needs_person` (an UNVERIFIABLE blocker or an unanswered sign-off), `not_reached` (the run ended before the gate) |
| `criteria[]` | Per final criterion: id, class, trust at run time, status (`MET`, `PARTIAL`, `UNMET`, `UNVERIFIABLE`, `n_a`, `signed`, `declined`, `not_verified`, `not_judged`), grader (check ref, judge binding, or the `Caller` who signed) |
| `intermediate[]` | Per unit and criterion id: the final status at the unit's last visit; never text |
| `later[]` | Signals after the run, appended by later commands: a person's outcome label ([FBK](41-feedback-and-judge-reliability.spec.md) `label <thread> outcome`), a rerun of the same task, a finalizer fact that the pull request was closed unmerged |

| Measure per workflow version and revision | Definition | Shown as |
|---|---|---|
| Outcome met rate | Runs with verdict `met` or `met_with_open` over runs that reached the gate | Raw and, for judge-graded criteria, corrected by the judge's error ([EVS §2.5](51-eval-suites.spec.md)) |
| Escape rate | Runs graded `met` that a later signal contradicts | With `n`; the miss is a harvest candidate ([LIF](18-lifecycle-and-evals.spec.md) `evals harvest outcome`) |
| Unverified share | Final blockers at trust `unverified` or `uncalibrated`, and the share of runs with any `not_verified` | Always printed, never zero by omission (§4) |
| Upstream agreement | For each final criterion, how often its serving intermediate criteria all passed and it then failed | Names the serving unit whose gate lets defects through |
| Sign-off load | Person-verified criteria per run and their wait | Feeds supervision ([SUP §2.4](86-supervision-metrics.spec.md)) as designed touches |

`outcome show <workflow> --runs [window]` prints these; `report` and the monitor read the record ([OBS](15-observability-and-cost.spec.md)). Promotion reads the outcome met rate, the escape rate and the unverified share beside the supervision rows ([SUP §2.7](86-supervision-metrics.spec.md), [ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)): a workflow with a final blocker at `unverified` trust is never promoted to `pipeline`.

### 2.6 Revising the outcome

Criteria drift is expected: people find new criteria after grading outputs ([R-105 B2](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md)). A revision is a change of `outcome.json`; it bumps `revision`, appends an `OutcomeRevision` and, through the content digest, gives a new `workflow_version` ([VER §2.4](61-version-metadata.spec.md)).

| `OutcomeRevision` field | Meaning |
|---|---|
| `revision`, `at`, `by` (`Caller`) | Who changed it; a weakening needs a person ([PRV](85-caller-provenance.spec.md)) |
| `origin` | `authored`, `revise_session`, `proposal:<id>`, `upgrade` |
| `changes[]` | Per criterion id: `added`, `removed`, `text`, `severity`, `verifier_up`, `verifier_down`, `serves`, `statement`; each classed `strengthening`, `weakening` or `neutral` by comparing parsed files |
| `evidence[]` | Thread ids, label counts, calibration score ids, never text |

| Change | Class | Needs |
|---|---|---|
| A criterion added; severity raised; a verifier moved up the ladder `none → person → judge → check` | strengthening | For `person → judge`: the judge binding `accepted` on cases naming the criterion ([JCL](50-judge-calibration.spec.md)). For `judge → check`: the check's must-pass and must-fail fixtures, and agreement with the judge's past statuses on at least 10 recorded runs (`evals replay`, [LIF](18-lifecycle-and-evals.spec.md)) |
| A criterion removed; severity lowered; a verifier moved down; `serves` narrowed; a sign-off dropped | weakening | A person, always; the change is labelled weakening in its pull request ([ADR-0031](../adr/0031-steps-and-their-graders-change-apart.adr.md), PRP class `weakening`) |
| Text reworded with the same id | neutral, but stales the judge's calibration score for that criterion ([LIF-B5](18-lifecycle-and-evals.spec.md)) | — |

Where revision candidates come from, read model-free by `outcome candidates <workflow> [--window]`:

| Signal | Candidate |
|---|---|
| A ruling or feedback that recurs on three runs with three requests ([RRN](81-reruns-and-feedback.spec.md)) | A new criterion on the unit it was given at, text drafted from the ruling's id only; the person writes the text |
| Escapes (§2.5) | A missing final criterion, or a serving criterion that is too weak |
| A `declined` sign-off with feedback | A criterion the person checks that no criterion states |
| A criterion at `unverified` trust on more than half the runs | A verifier to find ([AUT §2.4](89-workflow-authoring.spec.md)) |
| A `person` criterion signed `signed` on every run of the window with ≥ 20 runs | Move it up to `judge`: calibration cases to collect |
| Low upstream agreement | A stronger serving criterion on the named unit |

A revision is made by a person through the authoring skill's revise mode ([AUT §2.7](89-workflow-authoring.spec.md)), or proposed by the improvement loop as class `outcome` ([PRP §2.4](40-improvement-proposals.spec.md)), which never makes a weakening; both are in release 1 ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)).

## 3. Behaviours

**OUT-B1 The minimal outcome.** Given the release-notes package of [PKG §2.7](88-workflow-package.spec.md) with this `outcome.json`, when it loads, then the `draft` gate has criteria `rn-sections` (check, mechanical) and `rn-faithful` (judge), and the outcome gate has `rn-complete` (judge):

| Id | Where | Text | `verified_by` | `serves` |
|---|---|---|---|---|
| `rn-complete` | final, blocker | Every merged change since the last tag is in the notes or listed as excluded with a reason | judge | — |
| `rn-sections` | `draft`, blocker | The notes have the template's four headings in order | check | `rn-complete` |
| `rn-faithful` | `draft`, blocker | Every entry matches what its merged change did | judge | `rn-complete` |

**OUT-B2 An unverified criterion is shown.** Given a final warning "readers find the notes useful" with `verified_by: none` and reason "no reader feedback channel", when a run passes, then the verdict is `met_with_open`, the report lists the criterion as `not_verified` with its reason, and the unverified share is above zero.

**OUT-B3 Derived back target.** Given a temperspec run whose outcome judge finds final criterion `ac-addressed` UNMET, and whose `plan` and `code` units carry criteria serving `ac-addressed`, when the gate routes, then the run goes back to `plan`, the earlier of the two on the path, with the judge's reason, once; a second failure asks a person.

**OUT-B4 Sign-off.** Given a final criterion verified by `person` (role "release manager", question "Is this safe to publish?"), when check and judge pass, then the run pauses with an approval payload listing that criterion; `resume --decision proceed --criterion rn-safe=signed` records `signed` with the caller; a relayed answer counts only with host turn evidence ([PRV §2.4](85-caller-provenance.spec.md)).

**OUT-B5 Weakening needs a person.** Given an improvement proposal that moves `rn-faithful` from `judge` to `none`, when it is classified, then it is `weakening` and refused as a proposal; the same change by a person in revise mode is recorded with `by.kind = person` and labelled.

**OUT-B6 Climbing the ladder.** Given `rn-safe` verified by `person` and signed on 24 of 24 runs, when `outcome candidates` runs, then it proposes collecting calibration cases for a judge; the move to `judge` is accepted only after the judge binding is `accepted` on cases naming `rn-safe`.

**OUT-B7 Revision stales comparisons.** Given runs graded at revision 3 and revision 4, where revision 4 rewrote `rn-complete`, when `outcome show --runs` reports the met rate, then it reports per revision and never pools a criterion whose text digest differs.

## 4. Error conditions

| Condition | Result |
|---|---|
| `outcome.json` missing, unreadable, or with no final criterion | Validation error `outcome-missing`; nothing runs |
| An intermediate outcome for a unit not in `order`, or a model step with none | `outcome-unit-unknown` / `outcome-unit-missing` (error) |
| `serves` names an id that is not a final criterion | `outcome-serves-unknown` (error) |
| Duplicate criterion id anywhere in the file | `criterion-id-duplicate` (error) |
| `verified_by: check` on a unit whose gate has no check | `mechanical-without-check`, the refusal of [CHK §4](75-check-contract-and-command-runs.spec.md) |
| `verified_by: none` without a reason | `outcome-none-unexplained` (error) |
| A criterion without `id` or `text`, or with an unknown `verified_by` or `severity` | `outcome-criterion-invalid` (error) |
| A report computing a measure with no records | The measure is `unmeasured` with `n = 0`, never 0 |
| A criterion text or the statement holds a request literal | Literal check finding ([SCF §2.3](91-blueprint-and-scaffold.spec.md)) |

## 5. Design notes

- **One file, one bar.** Step gates, the outcome gate, the outcome lens, eval trials ([EVS §2.3](51-eval-suites.spec.md)) and promotion read the same criteria, so a revision moves all of them together ([ADR-0107](../adr/0107-the-good-outcome-is-one-data-file-of-final-and-intermediate-outcomes.adr.md)).
- **Why the outcome gate is mandatory.** R-011 recommended it; without it, a run whose every step passed can still miss the request, and the loop has nothing to grade against. Its cost is one judge session per run in `dev`; `stable` may sample ([ADR-0108](../adr/0108-a-run-is-measured-at-a-final-outcome-gate.adr.md)).
- **Why show, not hide.** An unverifiable requirement left out of the file looks verified to everyone who reads the reports. Keeping it as `none` with a reason makes the gap a number the owner can watch and the promotion rule can refuse.
- **Release 1** builds §2.1 to §2.5, sign-off, the measures without correction where no judge is calibrated, `outcome show` and `outcome candidates`, and revise mode. Calibration, corrected rates and `outcome` proposals from the loop are in release 1 too, built after the core ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)).

## 6. Acceptance criteria

- [ ] OUT-AC-1 Every row of §4 has a fixture `outcome.json` that fails with its own code.
- [ ] OUT-AC-2 A package's gates get exactly the criteria of their unit's intermediate outcome, with `mechanical` set for `check` criteria (OUT-B1).
- [ ] OUT-AC-3 Every path to the finalizer passes the outcome gate (property test over generated workflows), and its back target is derived from `serves` (OUT-B3).
- [ ] OUT-AC-4 Every report, `outcome show`, the run detail document and the audit print the unverified criteria and the unverified share; no measure with `n = 0` prints as 0.
- [ ] OUT-AC-5 The revision classifier labels each change kind of §2.6 from parsed files only, and a weakening by any caller but a person is refused.
- [ ] OUT-AC-6 The outcome lens of self-improvement reads the outcome record and starts no judge of its own when the record has a judged verdict.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Should `stable` workflows default to `outcome.judge = on_trigger` to save one judge per run? Assumed `always` until cost data exists. | Owner | `always` |
| Is ten replayed runs enough agreement to move a criterion from judge to check? A default with no data behind it, like the thresholds of [SUP §2.7](86-supervision-metrics.spec.md). | Owner | Ten |

## References

[PKG](88-workflow-package.spec.md) · [AUT](89-workflow-authoring.spec.md) · [JDG](05-judge-and-verdict.spec.md) · [HUM](07-gate-and-human.spec.md) · [SIL](16-self-improvement.spec.md) · [PRP](40-improvement-proposals.spec.md) · [JCL](50-judge-calibration.spec.md) · [EVS](51-eval-suites.spec.md) · [SUP](86-supervision-metrics.spec.md) · [R-105](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md) · [R-011 G1](../research/R-011-design-gap-review.rsrch.md)
