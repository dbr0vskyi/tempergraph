---
title: Workflow upgrade
type: component
status: ready-for-implementation
prefix: WUP
adrs: [0058, 0059, 0057, 0031]
---

# Workflow upgrade

## 1. Overview

`tempergraph upgrade <workflow>` brings a workflow's source up to the running engine. It reads the workflow's version metadata and the engine's compatibility changelog ([VER](61-version-metadata.spec.md)), works out what each entry since the workflow's stamp touches, changes it, verifies the result against what the workflow was before, and stamps it. It works on a branch of the workflow's source; a person reviews and merges, and an installed copy is never changed. The work is split by what can decide it ([ADR-0058](../adr/0058-upgrade-by-transforms-first-and-a-gated-model-workflow-for-the-rest.adr.md)): detect rules find what an entry touches and engine-shipped transforms make the changes a rule can express, spending nothing; the built-in upgrade workflow ([UWF](64-upgrade-workflow.spec.md)), a gated tempergraph run, makes the changes that need reading and judgement; the owner answers what only the owner knows, at a pause, from a drafted proposal; and model-free checks against the pre-upgrade baseline decide whether it is done ([ADR-0059](../adr/0059-an-upgrade-is-done-when-model-free-checks-pass-against-the-old-baseline.adr.md)). Workflow owners, the upgrade skill ([LSK](65-lifecycle-skills.spec.md)) and `author verify` depend on it; design and build notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

The work is split by what can decide it ([ADR-0058](../adr/0058-upgrade-by-transforms-first-and-a-gated-model-workflow-for-the-rest.adr.md)):

| Part | Decided by | Spends |
|---|---|---|
| Find what an entry touches | Detect rules ([VER §2.3.2](61-version-metadata.spec.md)) | no |
| Changes a rule can express (renamed field, renamed tool, kept default) | Engine-shipped transforms ([VER §2.3.4](61-version-metadata.spec.md)) | no |
| Changes that need reading and judgement (a prompt that relies on a changed behaviour, a check written against a changed state view) | The built-in upgrade workflow, a gated tempergraph run ([UWF](64-upgrade-workflow.spec.md)) | yes |
| Answers only the owner has (a new required criterion, a repository name, a bar) | The owner, at a pause, from a drafted proposal | the draft only |
| Whether the result is done | Model-free checks against the pre-upgrade baseline (§2.6, [ADR-0059](../adr/0059-an-upgrade-is-done-when-model-free-checks-pass-against-the-old-baseline.adr.md)) | no |

## 2. Contract

### 2.1 Verb

```text
tempergraph upgrade <workflow>
    [--check [--fail-on pending|never]]      # plan only: read-only, model-free (was upgrade-check)
    [--no-assist]                            # transforms only; assisted items become manual
    [--executor <name>] [--cap <usd>]        # for the upgrade workflow's sessions; default from UpgradePolicy, cap $10
    [--trial [--cases <set>]]                # also a paired trial of the result (PRP), opt-in
    [--stamp] [--bump] [--open-pr]
    [--continue <upgrade_id>]                # after a pause, a fix by hand, or a failed check
    [--format text|json]
tempergraph upgrade-check <workflow> [--stamp]   # kept: same as upgrade --check, and --stamp on a clean check
```

| Phase | Does | Writes | Spends |
|---|---|---|---|
| 1 Locate | Finds the workflow's source and refuses an installed copy (§2.2) | no | no |
| 2 Baseline | Records the workflow before any change (§2.3) | upgrade record | no |
| 3 Plan | Turns each changelog hit into an item (§2.3) | upgrade record | no |
| 4 Transform | Applies transform items in release order (§2.4) | branch | no |
| 5 Assist | Runs the upgrade workflow over assisted and owner items (§2.5) | branch, a run | yes |
| 6 Verify | §2.6 | upgrade record | no, or the trial with `--trial` |
| 7 Finish | Proposes the version fields, stamps with `--stamp`, opens a draft pull request with `--open-pr` (§2.7) | branch, pull request | no |

`--check` runs phases 1 to 3 without writing (contract C13) and prints the plan; it replaces `upgrade-check`, which stays as an alias so no caller breaks.

**Release 1** builds `upgrade --check [--fail-on pending] [--stamp]` and `upgrade-check [--stamp]` only. Phases 4 to 7 come in release 3, and `upgrade` without `--check` is refused with `not_in_release` ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)). `--stamp` on a clean plan runs V1 to V7 in place in the package, with no branch, because there is nothing to change. V4 and V6 report `skipped` until audit (plan T8.5) and eval suites (release 2) exist. V5 passes, because nothing was changed. V7 regenerates `diagram/model.json` and `diagram/workflow.md`, since the diagram is generated and never typed. The stamp is written only after every check that runs has passed; otherwise the verb exits 4. Output is JSON.

| Exit | When |
|---|---|
| 0 | Nothing to do, or done (verified; stamped when asked) |
| 2 | Unknown workflow, installed copy, dirty source branch, `--continue` of an unknown id |
| 3 | The upgrade workflow paused for the owner ([HUM](07-gate-and-human.spec.md)) |
| 4 | Verification failed; the branch and the report stay; `--continue` re-verifies after a fix |
| 5 | The cap was spent |
| 6 | `--check --fail-on pending` with at least one pending item |

### 2.2 Where it works

| Rule | Value |
|---|---|
| Source | The registered package path must be inside a git work tree that is not under Claude Code's plugin cache ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U4). Otherwise exit 2: "upgrade the workflow's source; this is an installed copy". |
| Branch | `tempergraph/upgrade/<workflow>/<engine_version>` from the source's current commit, in an engine worktree ([WSP](13-workspace-and-concurrency.spec.md)); the person's checkout is never touched |
| Record | `upgrades/<upgrade_id>/` under the source repository's state root: `plan.json`, `baseline.json`, `report.json`, all with `schema_version` |
| Scope | Edits only inside the package folder; a change outside it is refused by the transform engine and by the upgrade workflow's gate |

### 2.3 Baseline and plan


|---|---|
| Validation | Every finding with its code and location |
| Audit | `audit --layer definition --layer host` findings, keyed by rule and location ([AUD](55-workflow-audit.spec.md)) |
| Suites | The result of every model-free regression suite ([EVS](51-eval-suites.spec.md)) |
| Shape | `shape_digest` and the diagram model |
| Parse | The parsed workflow, for change classification ([PRP §2.4](40-improvement-proposals.spec.md)) |

The plan reads the changelog entries between the stamp and the running engine, oldest first ([VER-B2](61-version-metadata.spec.md)), runs each entry's detect rules, and adds the host items the audit already finds: `tool-name-stale` ([PRA](58-prompt-audit.spec.md)), `declared-tool-stale` and `tool-set-drift` ([TSA](57-tool-surface-audit.spec.md)), and the change notes of every sub-workflow the workflow uses ([VER §2.6](61-version-metadata.spec.md)).

| Item field | Meaning |
|---|---|
| `item_id`, `entry` | The changelog entry id, or the audit rule for a host item |
| `hits[]` | File, field path or line, rule id, confidence |
| `action` | `transform`, `assisted`, `owner`, `manual` (assisted with `--no-assist` or `assist: off`), `none` |
| `protected` | True when a hit lies on a path `UpgradePolicy.protected` names ([VER §2.4](61-version-metadata.spec.md)); an assisted item on a protected path becomes `owner` |
| `state` | `pending`, `done`, `failed`, `skipped` (by the owner, with a reason), `answered` |
| `by` | `transform`, `model`, `person` |

An entry with no hit is listed under `not_touched` with its id, so a reviewer sees what was considered.

### 2.4 Transforms

Each transform item is applied with its parameters, one commit per changelog entry, oldest release first. After each, the entry's detect rules run again: no hit marks it `done`; a remaining hit marks it `failed` and turns the rest of its hits into an `assisted` item. Transforms never call a model and never touch a path outside the package.

### 2.5 Assisted and owner items

The assisted and owner items go to the built-in upgrade workflow ([UWF](64-upgrade-workflow.spec.md)) as one run on the upgrade branch, thread `upgrade/<upgrade_id>`, under `--cap`. It is an ordinary run: its steps are gated by checks and an independent judge, its pauses are the owner's, its cost is recorded, and `status`, `events` and the monitor show it. When it pauses the verb exits 3; after the person resumes it and it finishes, `upgrade --continue <upgrade_id>` goes on to verification. With `--no-assist` the verb lists the `manual` items with each entry's `note` and stops at verification.

### 2.6 Verification

Model-free, in this order; the first failure stops the list and exits 4 with every failing check reported.

| # | Check | Passes when |
|---|---|---|
| V1 | Load | The package imports and `load()` returns a spec |
| V3 | Proof | Every `done` item's `proof` codes are absent and its detect rules find nothing ([VER §2.3](61-version-metadata.spec.md)) |
| V5 | Change classes | The parsed before and after are classified ([PRP §2.4](40-improvement-proposals.spec.md)); `weakening` appears only where an owner item answered with it; a `protected` path changed only by a transform or a person |
| V7 | Diagram | The diagram model is regenerated and committed; a shape change is listed unit by unit ([LIF](18-lifecycle-and-evals.spec.md)) |
| V8 | Trial (with `--trial`) | The paired trial on the case set ([PRP](40-improvement-proposals.spec.md), [ADR-0034](../adr/0034-paired-trial-on-a-fixed-case-set.adr.md)) does not decide `regressed` |

Rubric scores and judge acceptance whose digests the upgrade changed are shown as `stale` ([LIF-B5](18-lifecycle-and-evals.spec.md), [JCL](50-judge-calibration.spec.md)); that is a line in the report, not a failure, and a `stable` workflow then fails V2 by validation's own rule ([LIF-B6](18-lifecycle-and-evals.spec.md)).

### 2.7 Finish and report

| Output | Rule |
|---|---|
| Version proposal | `patch` when every change is by transform and none is model-facing; `minor` when prompts, briefs, lessons or criteria changed or an optional input was added; `major` when a change matches a workflow change-note surface ([VER §2.6](61-version-metadata.spec.md)): a removed or renamed input, artifact key or unit a parent may name. `requires_engine` proposed as `>=<engine_version>,<next major>`. Written to the branch only with `--bump`. |
| Change notes | For a `major` or `minor` proposal, a drafted `changes/<new version>.json` for the owner to edit |
| Stamp | With `--stamp` and V1 to V7 (and V8 when asked) passing: `stamp.json` and `verified_engine` on the branch ([VER §2.5](61-version-metadata.spec.md)) |
| Pull request | With `--open-pr`: a draft, labelled `engine-upgrade`, and `weakens-gate` with before and after when V5 found an owner-approved weakening; the body is the report |
| Report | Header (workflow, from and to engine, from and proposed version); items by state and by `by`, with the share by transform, model and person; each entry's `note`; V1 to V8 with evidence; `not_touched`; cost of the assist run; the branch |

The verb never merges and never writes the installed copy. Consumers receive the upgraded workflow when its owner releases a new plugin version and Claude Code updates it ([UPD §2.1](60-engine-update.spec.md)).

## 3. Behaviours

**WUP-B1 Plan only.** Given a workflow stamped at 1.2.0 and an engine at 1.5.1, when `upgrade --check` runs, then it prints one item per hit with its action, the entries with no hit under `not_touched`, writes nothing and calls no model.

**WUP-B2 Transforms only, no model.** Given entries whose hits all carry `transform` (a renamed gate field and a renamed tool), when `upgrade` runs, then two commits are made, no session starts, V1 to V7 pass, and the report shows 100% by transform.

**WUP-B3 Judgement goes to the gated workflow.** Given an entry `behaviour` on surface `callable` (a check's state view no longer carries retried outputs) with `migrate: assisted` and a hit in `checks/coverage.py`, when `upgrade` runs, then the upgrade workflow edits the check on the branch, its gate re-runs the entry's detect rules and the package's check fixtures, and an independent judge grades the edit against the entry's instruction.

**WUP-B4 The owner answers the owner's question.** Given a `tightened` entry that now requires `issue_repository` and a workflow without one, when the plan runs, then the item is `owner`; the upgrade workflow pauses with a drafted value read from the package's git remote and the question; the verb exits 3; only the person's answer is written.

**WUP-B5 A new audit finding blocks.** Given a model edit that adds a tool to a judge's grant, when V4 runs, then the new `judge-exposed-tool` finding fails it, the verb exits 4, and the stamp is not written.

**WUP-B6 A sub-workflow's change reaches its parent.** Given a parent workflow whose `verify` unit runs a sub-workflow that renamed its output key in 2.0.0's change notes, when the parent's upgrade plans, then a `rename_field` item points at the parent's reference to the old key.

**WUP-B7 An installed copy is refused.** Given a workflow registered from `~/.claude/plugins/cache/…`, when `upgrade` runs, then it exits 2 naming the copy and saying where the source must be; nothing is written.

**WUP-B8 Weakening needs the owner.** Given an assisted edit that lowers a criterion from blocker to warning, when V5 runs, then it fails, because no owner item answered with that weakening.

| Change found by V5 | Answered by an owner item | V5 |
|---|---|---|
| `prompt` | — | pass |
| `criterion` on a protected path, by the model | no | fail |
| `weakening` | yes, recorded | pass, labelled |
| `weakening` | no | fail |

**WUP-B9 Two releases behind.** Given entries in 1.3.0 and 1.5.0 that touch the same field, when `upgrade` runs, then 1.3.0's transform is committed before 1.5.0's, and V3 checks both.

## 4. Error conditions

| Condition | Result |
|---|---|
| The source's branch for this engine already exists and is not this upgrade's | Exit 2, naming it; `--continue` with its id resumes it |
| A transform raises | The item is `failed`, its hits become assisted; the run goes on |
| The upgrade workflow fails or is stopped | Exit 4 or 5 per its own exit; items it did not finish stay `pending` |
| No code host credentials for `--open-pr` | The branch and report stay; exit 0 with a warning |

## 5. Design notes

- The model work is a tempergraph workflow, not a loose session, so it inherits the engine's own rails: an independent judge, a deterministic check first, budgets, pauses and records ([UWF](64-upgrade-workflow.spec.md)).
- The shares by transform, model and person in every report are the measurement R-056's open question asks for.

## 6. Acceptance criteria

- [ ] WUP-AC-1 `upgrade --check` and `upgrade-check` give the same plan and leave the source, the state root and the package unchanged (hash test).
- [ ] WUP-AC-2 A fixture workflow per transform of [VER §2.3.4](61-version-metadata.spec.md) is upgraded with no session started.
- [ ] WUP-AC-3 Each check V1 to V8 has a fixture upgrade that fails it alone, exits 4 and writes no stamp.
- [ ] WUP-AC-4 Every row of WUP-B8's table is a test.
- [ ] WUP-AC-5 No upgrade writes outside its branch's package folder and its upgrade record (file-system guard in tests).
- [ ] WUP-AC-6 The report's shares by transform, model and person add up to the items done.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Should `upgrade` also run over every registered workflow whose source is local (`upgrade --all`)? The design upgrades one workflow per call; a batch is an orchestration of upgrades if wanted. | Owner | No: one workflow per call |

## References

