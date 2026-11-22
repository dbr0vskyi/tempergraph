# Blueprint, scaffold and authoring checks

## Purpose

The authoring interview ([AUT](89-workflow-authoring.spec.md)) ends in three drafts: the outcome ([OUT](90-run-outcome.spec.md)), the authoring record, and a blueprint, a small strict JSON document of what was decided about the workflow's shape. This spec owns the blueprint and its drawing, the scaffold that writes a package from the three drafts ([PKG](88-workflow-package.spec.md)), the blueprint comparison and the literal check from, and `author verify`, the ladder of checks an authored workflow passes before anyone relies on it: model-free checks first, then one consented, capped trial run on a real case ([ADR-0110](../adr/0110-check-an-authored-workflow-model-free-then-by-one-consented-trial.adr.md)). Every verb here but the seed and trial rungs is model-free (OVR-B15), and no model draws or edits a diagram. The authoring skill and the person approving a workflow depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### SCF-B1 A misspelt field

WHEN `blueprint check` meets an unknown key THE engine SHALL fail with `unknown_key` at its path and draw nothing.

- GIVEN a unit with `prodcues: ["notes"]` WHEN `blueprint check` runs THEN it fails with `unknown_key` at that unit

### SCF-B2 A reference nobody produces

WHEN a unit reads a key that no earlier unit produces on some path THE engine SHALL fail `blueprint check` with the workflow model's reference finding naming the path, `template-key-not-on-every-path` raised to an error here.

- GIVEN a unit that reads `plan` with no producer on one path WHEN `blueprint check` runs THEN it fails naming that path

### SCF-B3 The minimal workflow

WHEN `scaffold` runs on an approved one-unit session THE scaffold SHALL write the minimal package ([PKG-B25](88-workflow-package.spec.md)) whose generated tests pass and on which `author verify` without `--trial` passes rungs 1 to 7 with no edit.

- GIVEN a one-unit blueprint `draft` with a check and a judge and the outcome of [OUT-B1](90-run-outcome.spec.md) WHEN `scaffold` and `author verify` run THEN rungs 1 to 7 pass

### SCF-B4 Comparison catches drift

WHEN the built spec differs from the approved blueprint in a compared field THE engine SHALL report the difference in words with its two fixes at rung 2.

- GIVEN a package whose person added `approval=True` to `draft` without changing the blueprint WHEN `author verify` runs THEN rung 2 reports "draft now pauses for approval after a pass; the blueprint does not"

### SCF-B5 A literal

WHEN a prompt, brief or other scanned text holds a literal from a case request THE engine SHALL report the hit with file and line until a reason is recorded for it.

- GIVEN a judge brief containing `RN-1423` and a case request naming the same ticket WHEN rung 3 runs THEN the hit names the brief's file and line, and recording a reason clears it

### SCF-B6 Trial disagreement first

WHEN the person grades a trial's criterion differently from its verifier THE engine SHALL list that criterion first in the trial report, write the label with `source: person` and `origin: authoring_trial`, and save a calibration case candidate for the judge.

- GIVEN a trial where the judge marked `rn-faithful` MET and the person grades it UNMET WHEN the report is shown THEN `rn-faithful` is first and a candidate is saved for the `draft` judge

### SCF-B7 Update keeps edits

WHEN `scaffold --update` runs on a package with person-edited files THE scaffold SHALL leave every file whose digest differs from the one it last wrote untouched and list it as person-edited, regenerating only generated files and data-derived docs sections.

- GIVEN a package whose `prompts/draft.md` the person rewrote WHEN revise mode calls `scaffold --update` THEN the prompt is untouched and listed, and the diagram is regenerated

### SCF-B8 An unclear scale

WHEN a seed is graded differently on its two gradings at rung 8 THE engine SHALL fail the rung naming the criterion, and the skill SHALL return to the guidance ladder ([AUT-B21](89-workflow-authoring.spec.md)) for it.

- GIVEN `rn-faithful` whose `partial` anchor reads "mostly right" WHEN its `unmet` seed is graded PARTIAL once and UNMET once THEN rung 8 fails `seed-unstable` naming `rn-faithful`

### SCF-B9 The blueprint

WHEN `blueprint.json` is read, stating only what was decided, an omitted field taking its default THE engine SHALL read `schema_version` (`1`); `name` (the workflow name, [PKG-B14](88-workflow-package.spec.md), a name ending in `-tgraph`, with a reserved prefix or over 57 characters being `blueprint-invalid`); `units` (1 to 20 of `{name, kind, summary, produces[], reads[], gate: {check, judge, signoff}, on_fail?, on_budget_spent?, approval?, back_targets[]?, executor?, sizing, judge_sizing}`, `kind` a release kind, `summary` at most 60 characters (`summary-too-long`), `reads` naming earlier `produces` keys); `flow` (unit to `{route: [targets]}`, `{switch: {arms, default}}`, `{parallel: [branches]}`, `{map: {over: "<unit>.<key>"}}` or `{wait: {event?}}`, shape only and no predicate, `parallel`, `map` and `wait` sitting on a unit of that kind, a `map` unit being the step run per item, an `ask` unit producing `answers` only with its `reads` what the person is shown, a `wait` without `event` waiting for one named after the unit, a kind or shape of a later release `not_in_release`); `outcome_ref` (`{revision, digest}`, the digest a SHA-256 of the outcome as canonical JSON with sorted keys and no spaces, without its `revisions` history); and `input` (`{kind, parameters}`); holding no criteria, prompts, tools or paths, and stating no sub-workflow or which branches write.

- GIVEN a blueprint with 21 units WHEN `blueprint check` runs THEN it fails with the path

### SCF-B10 Sizing

WHEN a `step` unit, and a `step` unit whose gate has a judge, is checked THE engine SHALL require `sizing` and `judge_sizing` as `{model, effort, why}`, `model` a tier (`small`, `medium`, `large`) or a qualified alias, never `inherit`, `effort` an effort level ([SSN](25-session-contract.spec.md)) or stated by an `effort_ladder` ([LAD](92-effort-ladder-and-model-escalation.spec.md)), `why` at least four words on why they fit the session; report a missing one `sizing-missing` and a malformed or misplaced one `sizing-invalid`; write them as the step's and judge's `model`, `effort` and `sizing`; and hold a hand-written workflow to the same three on `Step` and `Judge` through the audit error `sizing-unassessed` ([ARC](56-audit-rule-catalog.spec.md)); the authoring skill starting from the guide: sorting, extracting or reformatting one input at `small` or `medium` with `low` or `medium`, raised when its gate fails on substance; writing one document from a few inputs at `medium`, `medium`, raised to reconcile several sources; designing, planning, researching or reading many files at `medium`, `high`, `large` only with a measured reason; running long with tools and tests at `medium`, `high`; and judging one file against a few criteria at the step's tier with `low` or `medium`, never `small` when it reads across files, `high` when a miss ships a defect.

- GIVEN a step with `sizing: {model: inherit, effort: high, why: "plans the change"}` WHEN `blueprint check` runs THEN it reports `sizing-invalid`

### SCF-B11 Blueprint check

WHEN `blueprint check <file> [--outcome <file>]` runs THE engine SHALL build a throwaway `WorkflowSpec` (each unit's stub prompt naming its `reads` as template fields, each `produces` key a `file` artifact, a `judge: true` gate one stub criterion, `signoff` setting approval) and run workflow model validation on it ([WFM](02-workflow-model.spec.md)), refusing a reference no earlier unit produces, a back target no gate allows and an unreachable unit; check it against the draft outcome: each gated unit has an intermediate outcome, `outcome_ref` matches (`blueprint_outcome_mismatch`, clearing the approval), every `check: true` gate has a `check` criterion (`blueprint-check-without-criterion`) and the reverse (`blueprint-criterion-without-check`), sign-offs match (`blueprint-signoff-mismatch`); and exit 2 on any error, writing nothing.

- GIVEN an `outcome_ref` that does not match the draft WHEN `blueprint check` runs THEN it exits 2 `blueprint_outcome_mismatch`

### SCF-B12 Drawing for approval

WHEN `blueprint draw <file> [--outcome <file>] [--format md|svg|mermaid]` runs THE engine SHALL print, from the throwaway spec's diagram model ([LIF](18-lifecycle-and-evals.spec.md)), the diagram (units, artifacts and reads, failure policy, approval and sign-off points, routes and back edges, the outcome gate before the finalizer; Markdown holding Mermaid, `svg` a plain stacked renderer with dashed back edges); the outcome table (statement, deliverables, final criteria with severity); the verification table (every criterion with unit, text, `verified_by`, verifier, source, trust and serves); the unverified section (every `unverified` criterion with reason and risk and every uncovered final criterion, "none" when there are none); and each option not set with its default; a bad blueprint exiting 2; the person approving the drawing as a whole, recorded with the blueprint's and outcome's digests ([AUT-B24](89-workflow-authoring.spec.md)).

- GIVEN a blueprint with no unverified criterion WHEN it is drawn THEN the unverified section reads "none"

### SCF-B13 Literal check

WHEN `literals <workflow> [--cases]` or rung 3 runs THE engine SHALL scan with no model every prompt, brief, stance, criterion, check method, outcome statement and check source for a ticket id, a URL, an e-mail address, a path outside the package, or a run of at least six words from a case request of `evals/cases.json`, an input example, or (in `author check`) a session source file; name each hit's file and line; skip a hit recorded as a decision in `authoring.json` with `literal_digest`, the SHA-256 of file, kind and text; and exit 6 on a hit (advisory, like `audit --fail-on`).

- GIVEN a prompt holding `https://example.com/ticket/7` WHEN `literals` runs THEN it exits 6 naming the file and line

### SCF-B14 Scaffold

WHEN `scaffold <session> --out <dir>` runs on a session folder (`<state root>/authoring/<id>/`, or a folder given by path) THE scaffold SHALL refuse without phase 7 approved with matching `blueprint_digest` and `outcome_revision` (`blueprint_not_approved`) and refuse a non-empty `--out` with exit 2 unless it is the same workflow's package and `--update` is given; and write the package layout ([PKG-B11](88-workflow-package.spec.md)) with `tempergraph.json` `name` the blueprint's name and `plugin.json` `name` it plus `-tgraph` ([ADR-0120](../adr/0120-a-workflow-plugin-name-is-the-workflow-name-plus-tgraph.adr.md)), the session's `issue_repository`, `routing` and `author` in the manifests; `outcome.json` as revision 1 with `origin: authored`; `workflow/<module>/__init__.py` with one builder call per unit ([ADR-0106](../adr/0106-declare-workflows-with-typed-python-builders-and-text-in-files.adr.md)); `prompts/<unit>.md` and `judges/<unit>.md` outlines from phase 5 with the unit's criteria texts as the target and no check method; `docs/` (overview and unit specs from the outcome and blueprint, decision records from the session, the sources note, [PKG-B21](88-workflow-package.spec.md)); `tests/`; and `diagram/` from the built spec, never from the blueprint.

- GIVEN a session approved through phase 6 WHEN `scaffold` runs THEN it is refused `blueprint_not_approved`

### SCF-B15 Checks and fixtures written

WHEN the scaffold writes checks and fixtures THE scaffold SHALL write one check per unit with `check` criteria in `checks.py`: a `{primitive, artifact, …}` verifier as a call of the check helpers `tempergraph.api.checks` (`file_present`, `headings_in_order`, `pattern_present`, `pattern_absent`, `value_in_choices`, `git_clean`, `git_pushed`), a `{command}` verifier as a `ctx.run` on the prefix, which joins `allow_commands`, with the criterion id in its finding, and a `{check: name}` verifier as a stub finding `maybe` listed under `to_write`, route, switch and script units getting listed defaults in `routing.py`, the person reviewing each before verify; one eval case per intake example; and check fixtures `evals/checks/<unit>/must-pass|must-fail/<key><suffix>` from each `example_good` and `example_bad` source, a missing bad example replaced by the good one with every heading after the first removed, or an empty file.

- GIVEN a unit with one good example and no bad one WHEN it is scaffolded THEN its must-fail fixture is the good one cut after its first heading

### SCF-B16 Generated tests

WHEN the scaffold writes `tests/test_<module>_generated.py` THE generated tests SHALL call the package self-test so rung 4 runs the same functions in process, asserting diagram currency (`diagram/model.json` and `diagram/workflow.md` match the spec by digest, a failure naming the regenerating command); every unit's summary at most 60 characters; every start example resolving, read-only and model-free; every check passing its must-pass and failing its must-fail fixtures naming the criterion id, also with CRLF line endings ([EVS-B9](51-eval-suites.spec.md)), a fixture being one file or a folder named by artifact key; a stand-in run in a scratch repository with a scripted executor (step stand-ins writing their unit's first must-pass fixture, values taking their first choice, judges and the outcome judge answering MET, approvals `proceed`, no real script) reaching the finalizer and touching nothing outside the scratch folder; compatibility with the engine ([VER-B2](61-version-metadata.spec.md)); and `docs-drift` passing in stable mode ([PKG-B22](88-workflow-package.spec.md)).

- GIVEN a check that misses its must-fail fixture with CRLF endings WHEN the generated tests run THEN they fail naming the criterion id

### SCF-B17 Scaffold update

WHEN `scaffold --update` or `--update-docs` runs THE scaffold SHALL keep `scaffold.files` in `authoring.json`, mapping each written path to its SHA-256; rewrite a file whose digest is unchanged and list the rest as `person_edited`, a person-edited unit spec getting only its acceptance criteria regenerated; with `--update-docs` limit the rewrite to `docs/`, `outcome.json` and `blueprint.json` (whose `outcome_ref` follows a revised outcome), adding a `revisions` entry where missing with `origin: revise_session` from a revise session, else `authored`.

- GIVEN a revise session WHEN `scaffold --update-docs` runs THEN `outcome.json` gains an entry with `origin: revise_session`

### SCF-B18 Verify ladder, model-free rungs

WHEN `author verify <workflow>` runs on a package folder or a registered workflow THE engine SHALL run the rungs in order, stop at the first failing one with exit 2 and report each finding with `code`, `message` and `remedy`, `--json` printing `rungs[]` with `state` passed, failed, skipped, refused or waiting: 1 load and validate ([PKG-B15](88-workflow-package.spec.md), WFM, OUT's validation and the criteria lint at authoring severities, `criterion-no-seed` a warning here); 2 blueprint comparison (names, order, artifacts and reads, checks, judge references, sign-offs, failure and approval policy, back and route targets, map and wait parameters and the outcome digest, never summaries, models, criteria texts or prompts; an accepted difference recorded as a decision); 3 the literal check; 4 the generated tests on stand-ins; 5 coverage and trust ([OUT-B14](90-run-outcome.spec.md)), a final criterion or blocker settled by a decision whose `subject` or `criterion` is its id; 6 `audit --layer definition --layer host` ([AUD](55-workflow-audit.spec.md)) with no `error`; and 7 `workflows register <path> --check`, then `register` ([UPD-B20](60-engine-update.spec.md)).

- GIVEN a package with an unrecorded literal WHEN `author verify` runs THEN rung 3 fails, exit 2, and rungs 4 to 10 are skipped

### SCF-B19 Rung 8, judge seeds

WHEN `author verify --judge-seeds` (or `--trial`, which implies it) runs, the flag being the person's yes on the stated cost and a deciding call whose caller is recorded ([PRV](85-caller-provenance.spec.md)) THE engine SHALL require per judged gate two seeds for each `verified_by: judge` criterion (`criterion-no-seed`), each a case under `evals/calibration/<gate>/` (`seed-not-found`) with an expected status (`seed-unlabelled`): a person's label, or else the author's expectation in the case's `seed` block (`criterion_id`, `expected`, `reason`), which serves rung 8 only; run one judge session per seed grading every criterion of the gate twice on a scratch copy with no step session ([JCL](50-judge-calibration.spec.md)), a differing status being `seed-unstable` and one wrong both times `seed-misgraded`, both naming the criterion; write nothing to calibration scores; stop before the next session when the cap is spent (`seeds-cap-reached`); keep a failing criterion's shown seeds as `seeds_shown` with a digest of the gate's criteria and brief, moving them to `tune` ([JCL-B11](50-judge-calibration.spec.md)) when a later rung 8 finds the digest changed, a seed only graded staying `holdout`; and keep a seed graded right both times as `seeds_passed` keyed by the gate's digest, the judge's binding, the seed's files and expectations, a later rung 8 with the same key starting no session for it.

- GIVEN a rerun after one seed failed WHEN rung 8 runs with unchanged keys THEN only the failed seed is graded again

### SCF-B20 Rung 9, first trial

WHEN `author verify --trial --case <id> [--cap <usd>]` runs after the person's yes on the stated cost THE engine SHALL refuse `--trial` without `--case` (`trial-needs-case`) after rungs 1 to 7 have run, refuse an unknown case (`trial-case-unknown`), and run the case in process as task `trial-<case>-<4 hex>` with `run.workspace = worktree`, `--dry-run` and `run.run_cost_cap_usd` set to what rung 8 left of `--cap` (default $5, covering rungs 8 and 9); pass when the run's outcome record has a verdict other than `not_reached`; make a pause `waiting` with exit 3, the person resuming through the run driver and a later `author verify` without `--trial` stamping it; make a spent cap `trial-cap-reached` with a partial report and no stamp; keep `trial {case, task, thread, state, exit_code, verdict, grades}` in `authoring.json`; and leave `improvement_mode` at `dev`, passing meaning ready to run and be measured, never trusted.

- GIVEN `author verify --trial` with no case WHEN it runs THEN rungs 1 to 7 run and rung 9 is refused `trial-needs-case`

### SCF-B21 Rung 10, stamp

WHEN rung 10 runs THE engine SHALL run `upgrade --stamp` ([VER-B16](61-version-metadata.spec.md)) with `docs_digest`, write no stamp under an engine with pending breaking changelog entries ([WUP-B19](63-workflow-upgrade.spec.md)), make the audit findings rung 6 showed the new baseline under an outcome revision newer than the stamped one, and record `verify {at, ok, rungs}` in `authoring.json`, which no digest covers.

- GIVEN a passing ladder WHEN rung 10 runs THEN the stamp carries `docs_digest` and `authoring.json` records `verify` with `ok: true`

### SCF-B22 Trial report and grades

WHEN `author trial <workflow> [--json]` runs, read-only THE engine SHALL list each outcome criterion with its verifier's status (a judge's from the thread's `judgement` records, a check's from its unit's `check` record, PASS as MET) and the person's grade, disagreements first with the criterion's text and check method; and WHEN `author grade <workflow> [--unit <unit>] --criterion <id> --status <status> --reason <text> [--reviewer <handle>] [--relayed] [--json]` runs, a deciding call THE engine SHALL, for a judged criterion, append a `label` row ([FBK](41-feedback-and-judge-reliability.spec.md), `agree` or `disagree` with the judge, `source` from the decider, `origin: authoring_trial`) and save the grade as a label of the candidate case `trial-<task>` in `evals/calibration/<gate>/` (`provenance: harvested`, `state: candidate`, the request and a copy of the trial worktree's files up to 5 MB), the candidate becoming `reviewed` only through `evals label`, and keep a check's or person's criterion grade in `authoring.json` only.

- GIVEN a grade on a check criterion WHEN `author grade` runs THEN no label row is written and the grade is in `authoring.json`

### SCF-B23 Verbs

WHEN the scaffold and check verbs run THE engine CLI SHALL offer `blueprint check <file> [--outcome <file>]`, `blueprint draw <file> [--outcome <file>] [--format md|svg|mermaid]`, `blueprint compare <workflow>` (exit 2 on a difference), `literals <workflow> [--cases]` and `author trial <workflow> [--json]`, all writing nothing; `scaffold <session> --out <dir> [--update] [--update-docs]`, writing the package folder; `author verify <workflow> [--judge-seeds] [--trial --case <id>] [--cap <usd>] [--json]`, writing the registry entry, stamp and trial run; and `author grade` as SCF-B22; only `--judge-seeds` (judge sessions only) and `--trial` starting an executor session.

- GIVEN a stand-in session counter WHEN every verb but `author verify --judge-seeds` and `--trial` runs THEN the counter stays at zero

## Acceptance criteria

- SCF-AC1 (SCF-B1, SCF-B2, SCF-B9, SCF-B10, SCF-B11, SCF-B14): Every blueprint, sizing and scaffold refusal has a fixture that fails with its own code
- SCF-AC2 (SCF-B3, SCF-B15, SCF-B16): The scaffold's output for the minimal blueprint passes its own generated tests and rungs 1 to 7 with no edit
- SCF-AC3 (SCF-B4, SCF-B12, SCF-B18): The comparison reports each compared field when it differs, and none of the fields listed as not compared
- SCF-AC4 (SCF-B7, SCF-B17): `scaffold --update` never changes a file whose digest differs from the one it last wrote (property test)
- SCF-AC5 (SCF-B5, SCF-B13, SCF-B23): No verb but `author verify --judge-seeds` or `--trial` starts an executor session, and `--judge-seeds` starts judge sessions only (stand-in counter test)
- SCF-AC6 (SCF-B6, SCF-B20, SCF-B21, SCF-B22): A trial writes one label per judged criterion the person grades and never changes `improvement_mode`
- SCF-AC7 (SCF-B8, SCF-B19): A seed fixture graded against its expected status, or flipping between the two runs, fails rung 8 naming the criterion

## Open questions

- Is $5 the right default cap for a first trial? Until answered: $5, a default with no data; the cost lens will show real figures after the first workflows. Owner: owner.
