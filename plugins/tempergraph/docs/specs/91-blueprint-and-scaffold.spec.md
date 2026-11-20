---
title: Blueprint, scaffold and authoring checks
type: component
status: review
prefix: SCF
adrs: [0059, 0106, 0110, 0113]
---

# Blueprint, scaffold and authoring checks

## 1. Overview

The authoring interview ([AUT](89-workflow-authoring.spec.md)) ends in three drafts: the outcome ([OUT](90-run-outcome.spec.md)), the authoring record, and a blueprint, a small strict JSON document of what was decided about the workflow's shape. This spec owns the blueprint and its drawing, the scaffold that writes a package from the three drafts ([PKG](88-workflow-package.spec.md)), the blueprint comparison and the literal check from, and `author verify`, the ladder of checks an authored workflow passes before anyone relies on it: model-free checks first, then one consented, capped trial run on a real case ([ADR-0110](../adr/0110-check-an-authored-workflow-model-free-then-by-one-consented-trial.adr.md)). Every verb here but the seed and trial rungs is model-free (OVR-B15), and no model draws or edits a diagram. The authoring skill and the person approving a workflow depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## 2. Contract

### 2.1 The blueprint (`blueprint.json`)

States only what was decided; an omitted field takes its default. An unknown key is an error, so a misspelt field is reported, never drawn as an empty step.

| Field | Kind | Meaning |
|---|---|---|
| `schema_version` | int | `1` |
| `name` | slug | The workflow |
| `units` | list, 1 to 20, of `{name, kind, summary, produces[], reads[], gate: {check: bool, judge: bool, signoff: bool}, on_fail?, on_budget_spent?, approval?, back_targets[]?, executor?}` | `kind` is a release kind ([PKG §2.4](88-workflow-package.spec.md)); `summary` ≤ 60 characters; `reads` names earlier `produces` keys |
| `flow` | map unit → `{route: [targets]}` \| `{switch: {arms, default}}` \| `{parallel: [branches]}` \| `{map: {over, item_unit}}` \| `{wait: {}}` | Shape only; no predicate |
| `outcome_ref` | `{revision, digest}` | The draft `outcome.json` approved with it |
| `input` | `{kind, parameters: [names]}` | |


`blueprint check <file>` turns the blueprint into a throwaway `WorkflowSpec` with stub prompts and stub gates and runs [WFM](02-workflow-model.spec.md) validation on it, so a reference no earlier unit produces, a backward target no gate allows and an unreachable unit are refused before anything is drawn. It also checks the blueprint against the draft outcome: each unit with a gate has an intermediate outcome, `outcome_ref` matches, every `check: true` gate has a `check` criterion and every `check` criterion a `check: true` gate.

### 2.2 Drawing for approval

`blueprint draw <file> [--outcome <file>] [--format md|svg|mermaid]` renders, from the diagram model of the throwaway spec ([LIF](18-lifecycle-and-evals.spec.md)):

| Part | Shows |
|---|---|
| Diagram | Units, artifacts and reads, failure policy, approval and sign-off points, routes and back-edges, and the outcome gate before the finalizer |
| Outcome table | The statement, deliverables, final criteria with severity |
| Verification table | Every criterion, final and intermediate: unit, text, `verified_by`, verifier, source, trust (OUT §2.3), serves |
| Unverified section | Every criterion at `unverified` trust with its reason and risk, and every uncovered final criterion; never empty by omission: "none" when there are none |
| Defaults shown | Each option the person did not set, with its default |

The person approves the drawing as a whole; the skill records the approval with the blueprint's and the outcome's digests ([AUT §2.6](89-workflow-authoring.spec.md)).

### 2.3 Literal check

`literals <workflow> [--cases]` is a deterministic scan, no model: a ticket id, a URL, an e-mail address, a path outside the package, or a run of at least six words from any case request, intake example or source file in a prompt, brief, stance, criterion, check method, outcome statement or check source. Each hit names the file and line. The person removes the literal or records why it belongs (an entry in `authoring.json` decisions with the hit's digest); a recorded hit is not reported again.

### 2.4 Scaffold

`scaffold <session id> --out <dir>` writes a package from an approved session. It refuses without the approval of AUT phase 7 and refuses an `--out` folder that exists and is not empty, unless it is the same workflow's package and `--update` is given.

| Writes | From |
|---|---|
| The layout of [PKG §2.1](88-workflow-package.spec.md) with both manifests | Blueprint, session |
| `outcome.json` | The approved draft, revision 1, `origin: authored` |
| `workflow/<module>/__init__.py` | One builder call per unit, from the blueprint and the tables ([ADR-0106](../adr/0106-declare-workflows-with-typed-python-builders-and-text-in-files.adr.md)) |
| `checks.py` | One check per unit with `check` criteria: for an `existing:` or `created` command, a call of `ctx.run` on the declared prefix with the criterion id in its finding; for a primitive, the engine's check helpers (`tempergraph.api.checks`: file present, headings in order, pattern present or absent, value in choices, git clean, git pushed); the person reviews each before verify |
| `evals/` | One case per intake example; check fixtures: each `example_good` as must-pass, each `example_bad` as must-fail; a must-fail fixture made by removing the checked element from a good one where no bad example exists |
| `docs/` | The docs half of [PKG §2.5](88-workflow-package.spec.md): overview and unit specs from the outcome and the blueprint, decision records from the session's decisions, the sources note from the inventory |
| `tests/` | The generated tests below |
| `diagram/` | Generated from the built spec, never from the blueprint |

| Generated test | Asserts |
|---|---|
| Diagram currency | The three diagram files match the spec by digest, not bytes; a failure names the regenerating command |
| Summaries | Every unit has a summary ≤ 60 characters |
| Examples resolve | Every declared start example resolves; the resolver is read-only and model-free |
| Check fixtures | Every check passes its must-pass and fails its must-fail fixtures, naming the criterion id; each fixture also with CRLF line endings ([EVS §2.2](51-eval-suites.spec.md)) |
| Stand-in run | A scripted executor stands in twice per step (step, judge) and for the outcome judge; the run reaches the finalizer in dry run |
| Compatibility | The package loads, validates and is compatible with the engine ([VER §2.7](61-version-metadata.spec.md)) |
| Docs | `docs-drift` passes ([PKG §2.5](88-workflow-package.spec.md)) |

`scaffold --update` (used by revise mode and by a person after editing the blueprint) rewrites only generated files and the docs sections generated from data; it never overwrites a prompt, brief, check or docs prose a person edited (it compares each file with the digest it last wrote) and lists those files instead.

### 2.5 Checking the authored workflow (`author verify`)

`author verify <workflow> [--trial --case <id> --cap <usd>]` runs the ladder in order and stops at the first failing rung, reporting every finding with its remedy. Rungs 1 to 7 are model-free.

| Rung | Check | Passes when |
|---|---|---|
| 1 Load and validate | [PKG §2.3](88-workflow-package.spec.md), [WFM](02-workflow-model.spec.md), OUT §4 | No error |
| 2 Blueprint comparison | The built spec against the approved blueprint: names, order, artifacts and reads, checks, judge references, sign-offs, failure and approval policy, back and route targets, map and wait parameters, and the outcome digest. Summaries, models, criteria texts and prompts are not compared. Each difference in words: fix the workflow, or change the blueprint with the person's yes; an accepted difference is a decision | No unaccepted difference |
| 3 Literal check | §2.3 | No unrecorded hit |
| 4 Generated tests | §2.4, run by the engine's test runner on stand-ins | All pass |
| 5 Coverage and trust | OUT §2.3: every final criterion covered or recorded as a decision; no blocker at `unverified` trust without a decision | As stated |
| 6 Audit | `audit --layer definition --layer host` ([AUD](55-workflow-audit.spec.md)); each finding shown with its remedy for the person to fix or ignore with a reason | No `error`; warnings shown |
| 7 Register | `workflows register <path> --check`, then `register` ([UPD §2.8](60-engine-update.spec.md)) | Entry `ok` |
| 8 First trial | With `--trial`, only after the person's yes on the stated cost (each step attempt is two sessions, plus the outcome judge): one live run of the case in a fresh worktree, dry run, capped by `--cap` (default $5), caller recorded ([PRV](85-caller-provenance.spec.md)) | The run reaches the outcome gate; the report is produced whatever the verdict |
| 9 Stamp | `upgrade --stamp` ([VER §2.5](61-version-metadata.spec.md)); the stamp records `docs_digest` | Stamp written |


### 2.6 Verbs

| Verb | Writes | Spends |
|---|---|---|
| `blueprint check <file> [--outcome <file>]` | no | no |
| `blueprint draw <file> [--outcome <file>] [--format …]` | no (prints) | no |
| `blueprint compare <workflow>` | no | no |
| `literals <workflow> [--cases]` | no | no |
| `scaffold <session> --out <dir> [--update] [--update-docs]` | the package folder | no |
| `author verify <workflow> [--trial --case <id> --cap <usd>] [--json]` | registry entry, stamp, trial run and labels | `--trial` only |

## 3. Behaviours

**SCF-B1 A misspelt field.** Given a blueprint unit with `prodcues: ["notes"]`, when `blueprint check` runs, then it fails with `unknown_key` at that unit and draws nothing.

**SCF-B2 A reference nobody produces.** Given a unit that reads `plan` and no earlier unit produces it on one path, when `blueprint check` runs, then it fails with WFM's reference finding naming the path.

**SCF-B3 The minimal workflow.** Given a one-unit blueprint `draft` with a check and a judge and the outcome of [OUT-B1](90-run-outcome.spec.md), when `scaffold` runs, then the package of [PKG §2.7](88-workflow-package.spec.md) is written, its generated tests pass, and `author verify` without `--trial` passes rungs 1 to 7.

**SCF-B4 Comparison catches drift.** Given a scaffolded package whose person later added `approval=True` to `draft` and did not change the blueprint, when `author verify` runs, then rung 2 reports "draft now pauses for approval after a pass; the blueprint does not" with the two fixes.

**SCF-B5 A literal.** Given a judge brief containing `RN-1423` and a case request naming the same ticket, when rung 3 runs, then the hit names the brief's file and line; recording a reason clears it.

**SCF-B6 Trial disagreement first.** Given a trial where the judge marked `rn-faithful` MET and the person grades it UNMET, when the trial report is shown, then that criterion is listed first, the label is written with `source: person` and `origin: authoring_trial`, and a calibration case candidate is saved for the `draft` judge.

**SCF-B7 Update keeps edits.** Given a package whose `prompts/draft.md` the person rewrote, when revise mode calls `scaffold --update`, then the prompt is not touched and is listed as person-edited; `outcome.json`-derived docs sections and the diagram are regenerated.

## 4. Error conditions

| Condition | Result |
|---|---|
| A blueprint with more than 20 units, a summary over 60 characters, or an unknown key | `blueprint check` error with the path |
| `outcome_ref` that does not match the outcome draft | `blueprint_outcome_mismatch`; the approval is cleared |
| `scaffold` into a non-empty folder without `--update` | Refused, exit 2 |
| `author verify --trial` without the person's yes, or with no case | Refused, exit 2; rungs 1 to 7 still run |
| The trial reaches the cap | No new session; the report is `partial` and the stamp is not written |
| Rung 9 under an engine with pending breaking changelog entries | As [WUP §2.6](63-workflow-upgrade.spec.md): no stamp |

## 5. Design notes

- **Model-free, then one real run.** A model-free ladder catches what is wrong with the package; only a live run on a real case shows whether the outcome and its verifications grade the way the person grades ([ADR-0110](../adr/0110-check-an-authored-workflow-model-free-then-by-one-consented-trial.adr.md)). The person's grades on that run are the first labels and calibration cases, which is where criteria drift shows first ([R-105 B2](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md)).
- **Release 1** ships all of §2; check helpers cover the primitives listed, and the engine's test runner is the one set up by plan track T0 of the first-release plan.

## 6. Acceptance criteria

- [ ] SCF-AC-1 Every row of §4 and SCF-B1, B2 has a fixture that fails with its own code.
- [ ] SCF-AC-2 The scaffold's output for the minimal blueprint passes its own generated tests and rungs 1 to 7 with no edit (SCF-B3).
- [ ] SCF-AC-3 The comparison reports each compared field when it differs, and none of the fields listed as not compared.
- [ ] SCF-AC-4 `scaffold --update` never changes a file whose digest differs from the one it last wrote (property test).
- [ ] SCF-AC-5 No verb of §2.6 but `author verify --trial` starts an executor session (stand-in counter test).
- [ ] SCF-AC-6 A trial writes one label per criterion the person grades and never changes `improvement_mode`.

## Open questions

| Question | Owner |
|---|---|
| Is $5 the right default cap for a first trial? A default with no data; the cost lens will show real figures after the first workflows. | Owner |

## References

