# Run-level good outcome

## Purpose

Every workflow states what a good outcome of one run is, and everything that grades a run grades against it ([R-011](../research/R-011-design-gap-review.rsrch.md) G1). The good outcome is one data file in the package, `outcome.json` ([PKG](88-workflow-package.spec.md)), written first during authoring ([AUT](89-workflow-authoring.spec.md)) and revised after runs have been graded ([ADR-0107](../adr/0107-the-good-outcome-is-one-data-file-of-final-and-intermediate-outcomes.adr.md)). It holds the final outcome (a statement of the good end state, the deliverables and the final criteria), one intermediate outcome per unit (what that unit's result must be for the final outcome to be reachable, with its criteria), and for every criterion who verifies it: a script check, a judge, a person, or nobody yet, and for nobody, why. Step gates take their criteria from the intermediate outcomes; a final outcome gate grades the run against the final criteria before the finalizer ([ADR-0108](../adr/0108-a-run-is-measured-at-a-final-outcome-gate.adr.md)); each run leaves an outcome record from which the workflow's measures are computed. A criterion nothing trustworthy verifies is shown on every report, never passed silently. Revisions follow the grader-side rules of [ADR-0031](../adr/0031-steps-and-their-graders-change-apart.adr.md): weakening is a person's act, and a verifier moves up the ladder from person to judge to check only on measured evidence ([ADR-0111](../adr/0111-outcome-revisions-are-grader-changes-and-verifiers-climb-a-ladder.adr.md)). Step gates, the self-improvement outcome lens ([SIL](16-self-improvement.spec.md)), eval trials, reports and promotion depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### OUT-B1 The minimal outcome

WHEN a package's outcome loads THE engine SHALL give each unit's gate the criteria of its intermediate outcome, `mechanical` set on `check` criteria, and the outcome gate the final criteria.

- GIVEN the minimal release-notes package with final blocker `rn-complete` (judge: "every merged change since the last tag is in the notes or listed as excluded with a reason"), and `draft` blockers `rn-sections` (check: "the notes have the template's four headings in order") and `rn-faithful` (judge: "every entry matches what its merged change did"), both serving `rn-complete` WHEN it loads THEN the `draft` gate has `rn-sections` (mechanical) and `rn-faithful` and the outcome gate has `rn-complete`

### OUT-B2 An unverified criterion is shown

WHEN a run passes with a final criterion verified by `none` THE engine SHALL give the verdict `met_with_open`, list the criterion as `not_verified` with its reason in the report, and count it in the unverified share.

- GIVEN a final warning "readers find the notes useful" with `verified_by: none` and reason "no reader feedback channel" WHEN a run passes THEN the verdict is `met_with_open` and the unverified share is above zero

### OUT-B3 Derived back target

WHEN the outcome gate finds a final blocker UNMET or PARTIAL THE engine SHALL send the run back, with the judge's reason and once per target, to the earliest unit on the path whose criterion serves it, a second failure taking the gate's `on_budget_spent`.

- GIVEN a run whose outcome judge finds `ac-addressed` UNMET and whose `plan` and `code` units carry criteria serving it WHEN the gate routes THEN the run goes back to `plan` once, and a second failure asks a person

### OUT-B4 Sign-off

WHEN check and judge pass and a final criterion is verified by `person` THE engine SHALL pause with an approval payload listing it, record the per-criterion status given on resume with the caller, and count a relayed answer only with host turn evidence ([PRV-B14](85-caller-provenance.spec.md)).

- GIVEN `rn-safe` verified by `person` (role "release manager", question "Is this safe to publish?") WHEN `resume --decision proceed --criterion rn-safe=signed` runs THEN `signed` is recorded with the caller

### OUT-B5 Weakening needs a person

WHEN a change to the outcome is classed `weakening` THE engine SHALL refuse it as an improvement proposal and accept it from a person in revise mode, recorded with `by.kind = person` and labelled.

- GIVEN a proposal that moves `rn-faithful` from `judge` to `none` WHEN it is classified THEN it is `weakening` and refused as a proposal

### OUT-B6 Climbing the ladder

WHEN a `person` criterion is signed on every run of a window of at least 20 runs THE engine SHALL propose collecting calibration cases for a judge, accepting the move to `judge` only once the judge binding is `accepted` on cases naming the criterion.

- GIVEN `rn-safe` signed on 24 of 24 runs WHEN `outcome candidates` runs THEN it proposes calibration cases for a judge

### OUT-B7 Revision stales comparisons

WHEN measures span runs graded at different revisions THE engine SHALL report per revision and never pool a criterion whose text digest differs.

- GIVEN runs at revision 3 and 4 where 4 rewrote `rn-complete` WHEN `outcome show --runs` reports the met rate THEN it reports each revision apart

### OUT-B8 The outcome file

WHEN `read_outcome(package_path) -> OutcomeSpec | list[Finding]` reads `outcome.json`, model-free THE engine SHALL read `schema_version` (`1`); `revision` (an integer of at least 1, growing by one with every change); `statement` (1 to 3 sentences, observable, no request literal); `deliverables` (`{key, kind, where}`: artifact keys of final state and where they land, [CON-B4](01-contracts.spec.md)); `final` (at least one `OutcomeCriterion`); `intermediate` (unit to `{statement, criteria}`, one per model step and per script unit with a gate); optional `judge` (`{stance, brief_file?, references[], executor?, model?}`); optional `check` (a callable ref `(ctx: CheckContext) -> CheckResult` over final state, [PKG-B20](88-workflow-package.spec.md)); `assumptions` (what authoring assumed and the person did not settle, [AUT-B22](89-workflow-authoring.spec.md)); and `revisions` (`OutcomeRevision` list, newest last); and offer `gate_criteria(outcome, unit) -> list[Criterion]`, `check_against(outcome, spec) -> list[Finding]` and `outcome_record(state, outcome) -> OutcomeRecord`.

- GIVEN an `outcome.json` with no final criterion WHEN it is read THEN it is `outcome-missing`

### OUT-B9 Outcome criterion

WHEN a criterion is read THE engine SHALL take it as a `Criterion` ([CON-B4](01-contracts.spec.md): `id` required here, `text`, `check_method`, `severity`, `no_change_policy`, `unverified_system`) plus `verified_by` (`check`, `judge`, `person` or `none`); `verifier` per class (OUT-B10); `source` (`existing:<kind>` with kind one of `test`, `linter`, `type_check`, `schema`, `checklist`, `acceptance_criteria`, `definition_of_done`, `review_rule`, `template`, `style_guide`, `other`, or `example`, `interview`, `created`, [AUT-B18](89-workflow-authoring.spec.md)); `serves` (for an intermediate criterion, the final criteria it makes reachable, empty for the unit's own work); and a computed, never written `trust`.

- GIVEN a criterion with `verified_by: robot` WHEN it is read THEN it is `outcome-criterion-invalid`

### OUT-B10 Verifier classes

WHEN a criterion's class is checked THE engine SHALL require for `check` a verifier `{check: ref}`, `{command: prefix}` or `{primitive: <helper>, artifact: <key>, …}` naming a check helper of [SCF](91-blueprint-and-scaffold.spec.md) with its expected finding, graded by the gate's check ([CHK](75-check-contract-and-command-runs.spec.md)) with `mechanical: true`, a check whose fixtures never name the criterion id being `check-criterion-unnamed`; for `judge` `{references: [keys], read_systems?: [names], scale}` with `check_method` and a complete scale, graded by the unit's judge or the outcome judge; for `person` `{role, question}`, a sign-off at the unit's or the outcome gate's approval pause recording a status per criterion ([HUM](07-gate-and-human.spec.md)), a designed touch ([SUP-B9](86-supervision-metrics.spec.md)), never answered being `not_verified`; and for `none` `{reason, risk}`, allowed only as a recorded decision and listed on every report, a blocker with `none` being a warning in `dev` and an error in `stable`.

- GIVEN a `none` blocker WHEN `validate` runs in `stable` mode THEN it is an error

### OUT-B11 The scoring scale

WHEN a judged criterion carries its `scale` ([ADR-0114](../adr/0114-judged-criteria-carry-a-scale-and-authoring-guides-until-criteria-are-clear.adr.md)), the statuses and verdict rule staying engine-wide ([JDG](05-judge-and-verdict.spec.md)) THE engine SHALL require `met` (what a fully meeting result shows, observably), `partial` (what counts as partly met and where the line is; required for a blocker, or the fixed text "no partial: any gap is UNMET"), `unmet` (the typical failure as a reviewer would recognise it) and `evidence` (what the judge must cite for `met`, `MET` without it being `PARTIAL`); read optional `n_a` (absent meaning N/A is never valid and read as UNMET); require `seeds` (fixture ids in `evals/calibration/<gate>/`, at least one expected `met` and one expected `unmet` or `partial`, each stating its expectation in its `case.json`) before SCF's seed rung; render `met`, `partial`, `unmet` and `evidence` beside the check method in the judge prompt while the step sees only the text and `met`; and stale the judge's score for the criterion when its scale is reworded.

- GIVEN a judged blocker without `partial` WHEN `author check` runs THEN it reports `criterion-unanchored`

### OUT-B12 One class per criterion

WHEN a requirement needs both a check and a judge THE engine SHALL require it split into two criteria whose `serves` link both to the same final criterion, each criterion having exactly one class.

- GIVEN a criterion with two `verified_by` values WHEN it is read THEN it is `outcome-criterion-invalid`

### OUT-B13 Trust

WHEN trust is computed for a criterion, never stored THE engine SHALL give `deterministic` to a `check` with at least one must-pass and one must-fail fixture ([EVS-B9](51-eval-suites.spec.md)); `calibrated` to a `judge` whose binding is `accepted` on cases naming the criterion ([JCL-B17](50-judge-calibration.spec.md)); `uncalibrated` to a `judge` in any other state and a `check` without both fixtures; `human` to `person`; and `unverified` to `none`; a judge grade before calibration being `uncalibrated` in the record.

- GIVEN a check with only a must-pass fixture WHEN trust is computed THEN it is `uncalibrated`

### OUT-B14 Coverage

WHEN coverage of a final criterion is computed THE engine SHALL take the set of intermediate criteria that serve it with their trust, count it covered when the outcome gate verifies it at `deterministic`, `calibrated` or `human` trust, or when it has no verifier of its own there and every unit on every path to the outcome gate has a serving criterion of such trust, and print the trust profile and coverage table in `outcome show` for audit to read ([AUD](55-workflow-audit.spec.md), rules `outcome-uncovered`, `outcome-unverified-blocker`).

- GIVEN a final judge criterion with no accepted binding and no serving criteria WHEN `outcome show` runs THEN it is listed uncovered

### OUT-B15 The outcome gate

WHEN a workflow is compiled THE engine SHALL add a unit named `outcome` (the name reserved) after every unit and before the finalizer, on every path that reaches the finalizer ([CMP-B10](03-compiler-and-flow.spec.md)), with no session, `retry_budget` 0 and `loop_budget` 1; its step node assembling and recording the subject from final state (deliverables' pointers, values, facts, git facts); its check being `outcome.json` `check`, if any, plus a built-in check that every deliverable exists (a file present, a URL recorded, a value set), required only on a path that produces it, a deliverable no unit declares still required; its judge a fresh read-only judge over the final `judge` criteria with default stance "The request and the deliverables are the truth; everything a step said is a claim to verify", default references the request and every deliverable (a reference to an off-path artifact optional), its model defaulting to the strongest any step judge uses; `person` criteria going into an approval pause after check and judge pass as `sign_off` (id, text, role, question); and `none` criteria graded by nobody and reaching the record.

- GIVEN a deliverable produced only on a switch arm the run did not take WHEN the outcome gate checks deliverables THEN it is not required

### OUT-B16 Outcome gate failure

WHEN a blocker is UNMET or PARTIAL or the outcome check fails THE engine SHALL route as OUT-B3, back targets being derived from `serves` and never declared, a failing check that names no final criterion counting every final criterion as failing for the lookup, the run escalating when no serving unit is on the path, and the gate's `on_budget_spent` defaulting to `ask`.

- GIVEN a missing deliverable and no serving unit WHEN the outcome gate fails THEN the run escalates

### OUT-B17 Outcome judge mode

WHEN the outcome judge would run THE engine SHALL run it on every run in `dev`, and in `stable` follow the setting `outcome.judge` (`always` by default, or `on_trigger` with the outcome lens's stable triggers, [SIL-B10](16-self-improvement.spec.md)), a run where it did not run recording its judge criteria `not_judged`; and the self-improvement outcome lens SHALL read the outcome record instead of starting a second judge, so step gates, the outcome gate and the loop share one bar.

- GIVEN a `stable` workflow with `outcome.judge = on_trigger` and no trigger WHEN a run ends THEN its judge criteria are `not_judged`

### OUT-B18 The outcome record

WHEN a thread reaches or misses the outcome gate THE engine SHALL write one `OutcomeRecord` as a run-log record `outcome` and the ledger row's `outcome{}` with `revision`; `verdict` (`met` when every blocker is MET, `met_with_open` when blockers are met and a warning is unmet or a criterion is `not_verified`, `not_judged` or `none`, `unmet`, `needs_person` for an UNVERIFIABLE blocker or an unanswered sign-off, `not_reached` when the run ended before the gate); `criteria[]` per final criterion (id, class, trust at run time, status `MET`, `PARTIAL`, `UNMET`, `UNVERIFIABLE`, `n_a`, `signed`, `declined`, `not_verified` or `not_judged`, and grader: check ref, judge binding or the signing `Caller`); `intermediate[]` (per unit and criterion id the final status at the last visit, never text); and `later[]`, appended by later commands (a person's outcome label `label <thread> outcome`, [FBK](41-feedback-and-judge-reliability.spec.md), a rerun of the same task, a finalizer fact that the pull request was closed unmerged).

- GIVEN a run stopped before the outcome gate WHEN its record is written THEN the verdict is `not_reached`

### OUT-B19 Outcome measures

WHEN `outcome show <workflow> [--runs [window]] [--json]` runs, read-only THE engine SHALL print per workflow version and revision the outcome met rate (runs `met` or `met_with_open` over runs that reached the gate, raw and, for judge-graded criteria, corrected by the judge's error, [EVS-B15](51-eval-suites.spec.md)); the escape rate (runs graded `met` that a later signal contradicts, with `n`, each a harvest candidate for `evals harvest outcome`, [LIF](18-lifecycle-and-evals.spec.md)); the unverified share (final blockers at `unverified` or `uncalibrated` and the share of runs with any `not_verified`, always printed); upstream agreement (how often a final criterion failed after all its serving criteria passed, low being 20% or more of at least 5 runs); and sign-off load (person-verified criteria per run and their wait, [SUP-B12](86-supervision-metrics.spec.md)); a measure with no records being `unmeasured` with `n = 0`, never 0; `report`, the monitor and the detail document reading the record ([OBS](15-observability-and-cost.spec.md)); and promotion reading the met rate, escape rate and unverified share beside the supervision rows ([SUP-B17](86-supervision-metrics.spec.md)), never promoting to `pipeline` a workflow with a final blocker at `unverified` trust.

- GIVEN a workflow with no runs WHEN `outcome show --runs` runs THEN every measure is `unmeasured` with `n = 0`

### OUT-B20 Revisions

WHEN `outcome.json` changes THE engine SHALL require `revision` bumped, append an `OutcomeRevision` with `revision`, `at`, `by` (a `Caller`, [PRV](85-caller-provenance.spec.md)), `origin` (`authored`, `revise_session`, `proposal:<id>`, `upgrade`), `changes[]` per criterion id (`added`, `removed`, `text`, `severity`, `verifier_up`, `verifier_down`, `serves`, `statement`, each classed by comparing parsed files) and `evidence[]` (thread ids, label counts, calibration score ids, never text), the content digest giving a new `workflow_version` ([VER-B14](61-version-metadata.spec.md)); class as `strengthening` an added criterion, a raised severity and a verifier moved up `none → person → judge → check`; as `weakening` a removed criterion, a lowered severity, a verifier moved down, `serves` narrowed and a dropped sign-off, which needs a person always and is labelled weakening in its pull request ([ADR-0031](../adr/0031-steps-and-their-graders-change-apart.adr.md)); as `neutral` a text reworded with the same id, which stales the judge's calibration score for it ([LIF](18-lifecycle-and-evals.spec.md)); and accept `person → judge` only with the judge binding `accepted` on cases naming the criterion ([JCL](50-judge-calibration.spec.md)) and `judge → check` only with the check's must-pass and must-fail fixtures and agreement with the judge's past statuses on at least 10 recorded runs (`evals replay`).

- GIVEN a `judge → check` move with agreement on 6 replayed runs WHEN it is proposed THEN it is refused

### OUT-B21 Revision candidates

WHEN `outcome candidates <workflow> [--window <days>]` runs, read-only and model-free THE engine SHALL list with thread ids and counts a ruling or feedback recurring on three runs with three requests ([RRN](81-reruns-and-feedback.spec.md)) as a new criterion on its unit, the person writing the text; escapes as a missing final criterion or a too-weak serving one; a `declined` sign-off with feedback as a criterion no criterion states; a criterion at `unverified` trust on more than half the runs as a verifier to find; a `person` criterion signed on every run of a window of at least 20 as a move to `judge`; and low upstream agreement as a stronger serving criterion on the named unit; a revision being made by a person through the authoring skill's revise mode ([AUT-B25](89-workflow-authoring.spec.md)) or proposed by the improvement loop as class `outcome` ([PRP-B14](40-improvement-proposals.spec.md)), which never makes a weakening.

- GIVEN a ruling given on three runs of three requests WHEN `outcome candidates` runs THEN it lists a new criterion on that unit with the ruling's id and no drafted text

### OUT-B22 Outcome validation

WHEN `check_against` and validation read an outcome THE engine SHALL report as errors `outcome-missing` (missing, unreadable or no final criterion; nothing runs), `outcome-unit-unknown` (an intermediate outcome for a unit not in `order`), `outcome-unit-missing` (a model step with none), `outcome-serves-unknown` (`serves` naming an id that is not a final criterion), `criterion-id-duplicate`, `mechanical-without-check` (a `check` criterion on a unit whose gate has no check, [CHK-B15](75-check-contract-and-command-runs.spec.md)), `outcome-none-unexplained` (`none` without a reason) and `outcome-criterion-invalid` (no `id` or `text`, or an unknown `verified_by` or `severity`), and the literal check finding of [SCF](91-blueprint-and-scaffold.spec.md) for a request literal in a criterion text or the statement.

- GIVEN `serves: ["rn-missing"]` WHEN the package validates THEN it reports `outcome-serves-unknown`

## Acceptance criteria

- OUT-AC1 (OUT-B8, OUT-B9, OUT-B10, OUT-B12, OUT-B22): Every outcome validation code has a fixture `outcome.json` that fails with its own code
- OUT-AC2 (OUT-B1, OUT-B11, OUT-B13, OUT-B14): A package's gates get exactly the criteria of their unit's intermediate outcome, with `mechanical` set for `check` criteria
- OUT-AC3 (OUT-B3, OUT-B4, OUT-B15, OUT-B16): Every path to the finalizer passes the outcome gate (property test over generated workflows), and its back target is derived from `serves`
- OUT-AC4 (OUT-B2, OUT-B18, OUT-B19): Every report, `outcome show`, the run detail document and the audit print the unverified criteria and the unverified share; no measure with `n = 0` prints as 0
- OUT-AC5 (OUT-B5, OUT-B6, OUT-B7, OUT-B20, OUT-B21): The revision classifier labels each change kind from parsed files only, and a weakening by any caller but a person is refused
- OUT-AC6 (OUT-B17): The outcome lens of self-improvement reads the outcome record and starts no judge of its own when the record has a judged verdict

## Open questions

- Should `stable` workflows default to `outcome.judge = on_trigger` to save one judge per run? Until answered: `always`, until cost data exists. Owner: owner.
- What counts as a later signal that contradicts a `met` grade before labels exist? Until answered: a rerun of the thread (an intervention row with cause `rerun`); person labels and closed pull requests join with FBK and the finalizer facts. Owner: owner.
- When is upstream agreement low? Until answered: a final criterion that failed after all its serving criteria passed on 20% or more of at least 5 runs. Owner: owner.
- Is ten replayed runs enough agreement to move a criterion from judge to check? Until answered: ten, a default with no data behind it. Owner: owner.
