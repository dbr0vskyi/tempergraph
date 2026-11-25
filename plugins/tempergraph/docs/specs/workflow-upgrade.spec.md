# Workflow upgrade

## Purpose

`tempergraph upgrade <workflow>` brings a workflow's source up to the running engine. It reads the workflow's version metadata and the engine's compatibility changelog ([VER](version-metadata.spec.md)), works out what each entry since the workflow's stamp touches, changes it, verifies the result against what the workflow was before, and stamps it. It works on a branch of the workflow's source; a person reviews and merges, and an installed copy is never changed. The work is split by what can decide it ([ADR `upgrade-by-transforms-first-and-a-gated-model-workflow-for-the-rest`](../adr/upgrade-by-transforms-first-and-a-gated-model-workflow-for-the-rest.adr.md)): detect rules find what an entry touches and engine-shipped transforms make the changes a rule can express, spending nothing; the built-in upgrade workflow ([UWF](upgrade-workflow.spec.md)), a gated tempergraph run, makes the changes that need reading and judgement; the owner answers what only the owner knows, at a pause, from a drafted proposal; and model-free checks against the pre-upgrade baseline decide whether it is done ([ADR `an-upgrade-is-done-when-model-free-checks-pass`](../adr/an-upgrade-is-done-when-model-free-checks-pass.adr.md)). Workflow owners, the upgrade skill ([LSK](lifecycle-skills.spec.md)) and `author verify` depend on it; design and build notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### WUP-B10 The verb and its phases

WHEN `tempergraph upgrade <workflow> [--check [--fail-on pending|never]] [--no-assist] [--executor <name>] [--cap <usd>] [--trial [--cases <set>]] [--stamp] [--bump] [--open-pr] [--continue <upgrade_id>] [--format text|json]` runs THE engine SHALL run in order locate (find the source and refuse an installed copy), baseline, plan, transform, assist (the upgrade workflow over assisted and owner items, the only phase that spends, under `--executor` and `--cap`, defaults from `UpgradePolicy` and $10), verify (and the trial with `--trial`) and finish, and SHALL keep `tempergraph upgrade-check <workflow> [--stamp]` as an alias of `upgrade --check`, which runs locate to plan writing nothing (OVR-B15) and prints the plan.

- GIVEN `upgrade-check` and `upgrade --check` on one workflow WHEN both run THEN they print the same plan

### WUP-B11 Exit codes

WHEN `upgrade` ends THE engine SHALL exit 0 when there is nothing to do or it is done (verified, stamped when asked, or with a warning when `--open-pr` has no code host credentials, the branch and report kept); 2 for an unknown workflow, an installed copy, a dirty source branch, `--continue` of an unknown id, or an upgrade branch for this engine that exists and is not this upgrade's (named, `--continue` with its id resuming it); 3 when the upgrade workflow paused for the owner ([HUM](gate-and-human.spec.md)); 4 when verification failed, the branch and report kept, `--continue` re-verifying after a fix; 5 when the cap was spent; and 6 for `--check --fail-on pending` with at least one pending item.

- GIVEN `--check --fail-on pending` and one pending item WHEN it ends THEN it exits 6

### WUP-B12 Stamp on a clean plan

WHEN `upgrade --stamp` or `upgrade-check --stamp` runs on a plan with nothing to change THE engine SHALL run V1 to V7 in place in the package with no branch, V4 running the audit's `definition` layer only and failing on a finding at `warning` or above, not ignored, whose rule, unit, item and file the last stamp's `audit` list lacks (a first stamp passes and records the list), V5 passing because nothing changed, V6 running the package's check suite with both line endings and failing on a failing case ([EVS-B7](eval-suites.spec.md)), and V7 regenerating `diagram/model.json` and `diagram/workflow.md`; write the stamp only after every check that ran passed, else exit 4; and print JSON.

- GIVEN a clean plan and a new audit warning WHEN `upgrade-check --stamp` runs THEN it exits 4 and writes no stamp

### WUP-B13 Authoring's re-approval exception

WHEN rung 10 of `author verify` ([SCF](blueprint-and-scaffold.spec.md)) stamps a workflow whose outcome `revision` is newer than the last stamp's `outcome_revision` THE engine SHALL pass V4, name the new findings in its evidence and record the list anew, because a new outcome revision is the owner's re-approval, and `upgrade --stamp` and `upgrade-check --stamp` SHALL never do this.

- GIVEN an outcome revised from 2 to 3 and a new finding WHEN `author verify` reaches rung 10 THEN V4 passes naming the finding

### WUP-B7 An installed copy is refused

WHEN `upgrade` locates a workflow whose registered path is not inside a git work tree or lies under Claude Code's plugin cache ([research `updating-a-tool-with-long-lived-runs`](../research/updating-a-tool-with-long-lived-runs.rsrch.md) U4) THE engine SHALL exit 2 saying "upgrade the workflow's source; this is an installed copy" and write nothing.

- GIVEN a workflow registered from `~/.claude/plugins/cache/…` WHEN `upgrade` runs THEN it exits 2 naming the copy and where the source must be, and nothing is written

### WUP-B14 Where it works

WHEN an upgrade writes THE engine SHALL work on branch `tempergraph/upgrade/<workflow>/<engine_version>` from the source's current commit in a sibling worktree `<repo>.worktrees/upgrade--<workflow>--<engine>` ([WSP](workspace-and-concurrency.spec.md)), never the person's checkout; keep the record `.tempergraph/upgrades/<workflow>-<engine>/` under the source repository's state root with `plan.json`, `baseline.json` and `report.json`, each with `schema_version`; and refuse in the transform engine and the upgrade workflow's gate any edit outside the package folder.

- GIVEN an upgrade WHEN it ends THEN nothing outside the branch's package folder and the record has changed

### WUP-B15 The baseline

WHEN an upgrade takes its baseline under the running engine on the unchanged package THE engine SHALL record every validation finding with code and location, the `audit --layer definition --layer host` findings by rule and location ([AUD](workflow-audit.spec.md)), the result of every model-free regression suite ([EVS](eval-suites.spec.md)), the `shape_digest` and diagram model, and the parsed workflow for change classification ([PRP-B14](improvement-proposals.spec.md)), and SHALL go on when the baseline has validation `error` findings, leading the report with them and not counting them against V2.

- GIVEN a baseline with a validation error WHEN the upgrade verifies THEN V2 does not count it and the report leads with it

### WUP-B16 The plan

WHEN an upgrade plans THE engine SHALL read the changelog entries between the stamp and the running engine oldest first ([VER-B2](version-metadata.spec.md)), run each entry's detect rules, add the host items the audit finds (`tool-name-stale` of [PRA](prompt-audit.spec.md), `declared-tool-stale` and `tool-set-drift` of [TSA](tool-surface-audit.spec.md)) and the change notes of every sub-workflow it uses ([VER-B17](version-metadata.spec.md)), and give each item `item_id` and `entry` (the changelog id, or the audit rule), `hits[]` (file, field path or line, rule id, confidence), `action` (`transform`, `assisted`, `owner`, `manual` when assisted under `--no-assist` or `assist: off`, or `none`), `protected` (true when a hit lies on a path `UpgradePolicy.protected` names, an assisted item there becoming `owner`, [VER-B14](version-metadata.spec.md)), `state` (`pending`, `done`, `failed`, `skipped` by the owner with a reason, or `answered`) and `by` (`transform`, `model`, `person`), listing an entry with no hit under `not_touched`.

- GIVEN an assisted hit on a protected path WHEN planned THEN its item is `owner`

### WUP-B1 Plan only

WHEN `upgrade --check` runs THE engine SHALL print one item per hit with its action and the entries with no hit under `not_touched`, write nothing and call no model.

- GIVEN a workflow stamped at 1.2.0 and an engine at 1.5.1 WHEN `upgrade --check` runs THEN the plan is printed, nothing is written and no model is called

### WUP-B17 Transforms

WHEN transform items are applied THE engine SHALL apply each with its parameters, one commit per changelog entry, oldest release first, re-run the entry's detect rules after each (no hit marks it `done`; a remaining hit, or a transform that raises, marks it `failed` and turns its remaining hits into an item for the model or the owner, not counted against V2), and never call a model or touch a path outside the package.

- GIVEN a transform that raises WHEN applied THEN its item is `failed` and the upgrade goes on

### WUP-B2 Transforms only, no model

WHEN every hit carries `transform` THE engine SHALL upgrade with no session started.

- GIVEN a renamed gate field and a renamed tool WHEN `upgrade` runs THEN two commits are made, no session starts, V1 to V7 pass and the report shows 100% by transform

### WUP-B9 Two releases behind

WHEN entries of two releases touch the same field THE engine SHALL commit the older release's transform first and check both in V3.

- GIVEN entries in 1.3.0 and 1.5.0 on one field WHEN `upgrade` runs THEN 1.3.0's transform is committed before 1.5.0's and V3 checks both

### WUP-B18 Assisted and owner items

WHEN assisted or owner items remain THE engine SHALL run the upgrade workflow ([UWF](upgrade-workflow.spec.md)) once on the upgrade branch, thread `upgrade/<upgrade_id>`, under `--cap`, as an ordinary run gated by checks and an independent judge, with the owner's pauses, its cost recorded and shown by `status`, `events` and the monitor; exit 3 when it pauses; go on to verification with `upgrade --continue <upgrade_id>` after it finishes, reconciling owner items only there by re-reading the package and closing an item whose hit is gone; exit 4 or 5 by its own exit when it fails or is stopped, unfinished items staying `pending`; and with `--no-assist` list the `manual` items with each entry's `note` and stop at verification.

- GIVEN `--no-assist` and one assisted item WHEN `upgrade` runs THEN no session starts and the item is listed `manual` with its note

### WUP-B3 Judgement goes to the gated workflow

WHEN an `assisted` entry has a hit THE upgrade workflow SHALL edit it on the branch, its gate re-running the entry's detect rules and the package's check fixtures and an independent judge grading the edit against the entry's instruction.

- GIVEN an entry `behaviour` on `callable` with `migrate: assisted` and a hit in `checks/coverage.py` WHEN `upgrade` runs THEN the workflow edits the check, its gate re-runs the rules and fixtures, and a judge grades the edit

### WUP-B4 The owner answers the owner's question

WHEN an item is `owner` THE upgrade workflow SHALL pause with a drafted value and the question, and write only the person's answer.

- GIVEN a `tightened` entry now requiring `issue_repository` and a workflow without one WHEN planned and run THEN the item is `owner`, the workflow pauses with a value drafted from the package's git remote, the verb exits 3, and only the person's answer is written

### WUP-B19 Verification

WHEN an upgrade verifies THE engine SHALL run, model-free and in order, stopping at the first failure with exit 4 and every failing check reported: V1 load (the package imports and `load` returns a spec), V2 validation (no `error`, no `warning` absent from the baseline), V3 proof (every `done` item's `proof` codes are absent and its detect rules find nothing, [VER-B9](version-metadata.spec.md)), V4 audit (no finding at `warning` or above the baseline lacks, by rule and location), V5 change classes (the parsed before and after are classified, [PRP-B14](improvement-proposals.spec.md); `weakening` only where an owner item answered with it; a `protected` path changed only by a transform or a person), V6 suites (every model-free suite that passed still passes; one that failed before is reported pre-existing and fails on no more cases), V7 diagram (regenerated and committed, a shape change listed unit by unit, [LIF-B11](lifecycle-and-evals.spec.md)) and V8 trial with `--trial` (the paired trial of [PRP](improvement-proposals.spec.md) and [ADR `paired-trial-on-a-fixed-case-set`](../adr/paired-trial-on-a-fixed-case-set.adr.md) does not decide `regressed`), and show rubric scores and judge acceptance whose digests changed as `stale` ([LIF-B5](lifecycle-and-evals.spec.md), [JCL](judge-calibration.spec.md)), a report line and not a failure, a `stable` workflow then failing V2 by [LIF-B6](lifecycle-and-evals.spec.md).

- GIVEN a fixture that fails one check alone WHEN verified THEN it exits 4 and writes no stamp

### WUP-B5 A new audit finding blocks

WHEN V4 finds a finding the baseline lacks THE engine SHALL fail the upgrade and write no stamp.

- GIVEN a model edit that adds a tool to a judge's grant WHEN V4 runs THEN `judge-exposed-tool` fails it, the verb exits 4 and no stamp is written

### WUP-B8 Weakening needs the owner

WHEN V5 classifies a change THE engine SHALL pass a `prompt` change, fail a `criterion` change on a protected path by the model, pass and label a `weakening` an owner item answered and recorded, and fail a `weakening` no owner item answered.

- GIVEN an assisted edit lowering a criterion from blocker to warning with no owner answer WHEN V5 runs THEN it fails
- GIVEN a `weakening` the owner answered WHEN V5 runs THEN it passes, labelled

### WUP-B20 Version proposal and change notes

WHEN an upgrade finishes THE engine SHALL propose `patch` when every change is by transform and none is model-facing, `minor` when prompts, briefs, lessons or criteria changed or an optional input was added, and `major` when a change matches a change-note surface ([VER-B17](version-metadata.spec.md)), a removed or renamed input, artifact key or unit a parent may name; propose `requires_engine` as `>=<engine_version>,<next major>`; write both to the branch only with `--bump`; and for a `major` or `minor` proposal draft `changes/<new version>.json` for the owner to edit.

- GIVEN only transform changes to declarations WHEN finished THEN the proposal is `patch`

### WUP-B21 Stamp, pull request and report

WHEN an upgrade finishes THE engine SHALL write with `--stamp`, once V1 to V7 (and V8 when asked) pass, `stamp.json` and `verified_engine` on the branch ([VER-B16](version-metadata.spec.md)); open with `--open-pr` a draft labelled `engine-upgrade`, and `weakens-gate` with before and after when V5 found an owner-approved weakening, whose body is the report; report the header (workflow, from and to engine, from and proposed version), items by state and by `by` with the shares by transform, model and person, each entry's `note`, V1 to V8 with evidence, `not_touched`, the assist run's cost and the branch; and never merge or write the installed copy, consumers receiving the upgrade when its owner releases a new plugin version ([UPD-B10](engine-update.spec.md)).

- GIVEN a finished upgrade WHEN the report is read THEN its shares add up to the items done

### WUP-B6 A sub-workflow's change reaches its parent

WHEN a parent's upgrade plans and a sub-workflow it runs renamed an output key in its change notes THE engine SHALL add a `rename_field` item at the parent's reference to the old key.

- GIVEN a parent whose `verify` unit runs a sub-workflow that renamed its output key in 2.0.0's change notes WHEN the parent plans THEN a `rename_field` item points at the parent's reference

## Acceptance criteria

- WUP-AC1 (WUP-B1, WUP-B10, WUP-B16, WUP-B15): `upgrade --check` and `upgrade-check` give the same plan and leave the source, the state root and the package unchanged (hash test)
- WUP-AC2 (WUP-B2, WUP-B17, WUP-B9): A fixture workflow per transform of [VER-B13](version-metadata.spec.md) is upgraded with no session started
- WUP-AC3 (WUP-B19, WUP-B5, WUP-B11, WUP-B12): Each check V1 to V8 has a fixture upgrade that fails it alone, exits 4 and writes no stamp
- WUP-AC4 (WUP-B8): Every scenario of WUP-B8 is a test
- WUP-AC5 (WUP-B14, WUP-B7): No upgrade writes outside its branch's package folder and its upgrade record (file-system guard in tests), and an installed copy is refused
- WUP-AC6 (WUP-B21, WUP-B20): The report's shares by transform, model and person add up to the items done, and the version proposal follows its rule
- WUP-AC7 (WUP-B3, WUP-B4, WUP-B6, WUP-B13, WUP-B18): Fixtures cover an assisted edit gated by its rules and a judge, an owner pause, a sub-workflow's rename reaching its parent, authoring's re-approval exception and `--no-assist`

## Open questions

- Should `upgrade` also run over every registered workflow whose source is local (`upgrade --all`)? Until answered: one workflow per call; a batch is an orchestration of upgrades if wanted. Owner: owner.
- Not built yet: `--trial` and so V8 (refused with `not_in_release`) and the host audit items; tests drive two of the eight transforms through the verb and the other six as transforms; V7 has no failing fixture, since every earlier check already refuses what would trip it; WUP-B8's protected-criterion case is covered by the upgrade workflow's scope check ([UWF](upgrade-workflow.spec.md)), not by a test of this verb. Owner: engine owner.
