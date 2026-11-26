# Lifecycle and evals

## Purpose

The model-free tooling around the runtime: how the engine and its workflows are installed, upgraded, checked against each other and against the executors' CLIs and libraries, drawn and tested. Decisions are made by content and data, never by a version string or prose. Every executor changes between releases, so their versions are part of compatibility ([ADR `two-first-class-executors`](../adr/two-first-class-executors.adr.md), [ADR `add-messages-api-and-agent-sdk-executors`](../adr/add-messages-api-and-agent-sdk-executors.adr.md)). Operators, workflow authors and the `update`, `upgrade`, `validate` and `evals` verbs depend on these rules; install and update in full are [UPD](engine-update.spec.md), the changelog and stamp [VER](version-metadata.spec.md), suites [EVS](eval-suites.spec.md) and judge scores [JCL](judge-calibration.spec.md).

## Behaviours

### LIF-B7 Install

WHEN the engine is installed THE installer SHALL create one managed Python 3.11+ virtual environment per machine, outside the plugin cache, and put the CLI on PATH through a shim, and stop with how to install Python when no Python 3.11+ is found or only an alias stub.

- GIVEN a machine with Python 3.10 only WHEN the installer runs THEN it stops and says how to install Python 3.11+

### LIF-B1 Same version, different code

WHEN `update` decides whether the engine is current THE engine SHALL compare a hash of the engine's source files, installing from the invoked package's staged copy with constants-only argv into a new environment beside the current one, switching atomically, and refusing a downgrade ([UPD](engine-update.spec.md)); runs and stores in flight follow [MIG](state-and-run-migration.spec.md).

- GIVEN an installed engine with the same version string as the plugin but different source WHEN `update` runs THEN it reinstalls
- GIVEN an interrupted package installer WHEN `update` ends THEN it exits 1 and nothing is stamped

### LIF-B8 Update output

WHEN `update --json` runs THE engine SHALL print one JSON object per line, one step, result or path per line.

- GIVEN `update --json` WHEN a skill reads it THEN every line parses as one object

### LIF-B9 Manifest reconcile

WHEN the manifest is reconciled THE engine SHALL repoint stale entries and register installed workflow packages, reporting an entry that points at a missing folder and never deleting an entry.

- GIVEN an entry whose folder was removed WHEN reconcile runs THEN it is reported and still in the manifest

### LIF-B2 Stamp only when clean

WHEN `upgrade --stamp` or `upgrade-check --stamp` runs THE engine SHALL write the workflow stamp (the engine release it was last verified against, with its stamp record) only after every check of [WUP-B19](workflow-upgrade.spec.md) passes, matching the workflow against the typed compatibility changelog ([VER-B9](version-metadata.spec.md)).

- GIVEN a workflow whose detect rules match code a breaking release changed WHEN `upgrade-check --stamp` runs THEN it prints each hit with its changelog entry and writes no stamp

### LIF-B10 Executor compatibility

WHEN preflight reads an executor's version THE engine SHALL compare it with the range in `tempergraph/data/executor_compat.json` that its probe facts or contract tests were recorded for (the CLI for `claude` and `antigravity`, the SDK package and its bundled CLI for `agent-sdk`, the client library and API version header for `messages-api`), warn `executor-version-untested` and report projected capabilities outside it ([EAG-B7](executor-antigravity.spec.md)), and show the table in `executors`.

- GIVEN `claude` 2.1.330 and a table recording 2.1.329 only WHEN a run is preflighted THEN it warns `executor-version-untested`

### LIF-B18 A confirmed version is a recorded version

WHEN a live probe of an executor is recorded `confirmed` on a CLI version ([ECC-B13](executor-claude-code.spec.md)) THE engine SHALL list that version in the executor's `recorded` versions and inside its `range` in the compatibility table.

- GIVEN a probe recorded `confirmed` on `claude` 2.4.0 and a table that lists 2.4.0 in `recorded` and inside `range` WHEN a run is preflighted on `claude` 2.4.0 THEN it raises no `executor-version-untested` warning and `executors` shows the version as recorded
- GIVEN the same table WHEN a run is preflighted on `claude` 2.5.0, above its `range` THEN it warns `executor-version-untested`

### LIF-B11 Diagram model

WHEN the diagram model is generated THE engine SHALL write versioned JSON with a digest generated from the spec and verified against the compiled graph, rendered by pure renderers.

- GIVEN a workflow WHEN `graph` runs twice THEN both outputs are equal

### LIF-B3 Diagram currency by digest

WHEN the diagram currency check (`diagram_current`) runs THE engine SHALL compare the digest in `diagram/model.json` with the spec's over nodes and edges only.

- GIVEN a committed diagram after a CRLF checkout WHEN the check runs THEN it passes
- GIVEN a unit added or an edge moved WHEN the check runs THEN it fails

### LIF-B12 Prompt lint

WHEN `validate` runs THE engine SHALL lint each step template, judge stance and brief, and each skill and agent file the package ships, once per file, with no model, and report each finding as a warning with file and line: `lint-vague-word` (a fixed list such as "properly", "as needed", "etc.", "robust" in a template or judge), `lint-self-grading` (the step asked to rate, score or confirm its own work), `lint-rule-branching` (two or more if/otherwise rules), `lint-human-wait` (the step told to ask, wait for or check with a person), `lint-accepting-brief` (the brief tells the judge to trust the step's word, claim or summary), `lint-tool-name-foreign` (a backticked tool name of another executor's map), `lint-ref-missing` (a named skill, agent or package file under `prompts/`, `judges/`, `skills/`, `agents/` or `lessons/` the package lacks) and `lint-oversized` (a template or brief over 32,000 characters, a skill or agent over 40,000, a table cell over 2,000); `audit` shows the same findings ([AUD](workflow-audit.spec.md)), and [PRA](prompt-audit.spec.md) and [TSA](tool-surface-audit.spec.md) reuse the name reader.

- GIVEN a template saying "rate your own work from 1 to 5" WHEN `validate` runs THEN it warns `lint-self-grading` with file and line
- GIVEN a template naming `` `view_file` `` on a `claude` step WHEN linted THEN it warns `lint-tool-name-foreign`

### LIF-B13 Judge readiness report

WHEN judge readiness is reported THE engine SHALL list, per judged gate and the outcome gate, a judged criterion with no `check_method`, a judge criterion whose scale lacks `met`, `unmet` or `evidence` (or `partial` for a blocker, [OUT-B11](run-outcome.spec.md)), vague words in a criterion, a gate with no judged blocker, criteria lint findings on `outcome.json` ([AUT-B19, AUT-B20, AUT-B21](workflow-authoring.spec.md)), the count of calibration cases under `evals/calibration/<gate>/`, and the last score per judge executor with its acceptance state ([JCL-B17](judge-calibration.spec.md)), and grade the gate `ready` (structure clean and the judge `accepted`), `needs cases` or `needs work`; a criteria lint finding grades it `needs work`, except `criterion-no-seed`, which is shown and left to calibration.

- GIVEN a gate whose judge criterion has no `check_method` WHEN reported THEN the gate grades `needs work`
- GIVEN a clean gate whose judge has no score WHEN reported THEN it does not grade `ready`

### LIF-B6 Stable mode needs ready gates

WHEN a workflow declaring `stable` is validated THE engine SHALL refuse it with `gate-not-ready` unless every gate grades `ready` for the judge binding it will run on, which needs that binding `accepted` under [JCL](judge-calibration.spec.md).

- GIVEN a `stable` workflow with one gate graded `needs cases` WHEN validated THEN it is refused with `gate-not-ready`

### LIF-B4 Executor conformance in the eval set

WHEN a package's deterministic scenario runs THE engine SHALL run its generated tests on stand-ins ([SCF-B11, SCF-B13, SCF-B15, SCF-B16, SCF-B17, SCF-B18, SCF-B19, SCF-B20, SCF-B22](blueprint-and-scaffold.spec.md)): a scripted `claude` as the reference plays every step and judge and the run must finish, and a step naming an executor without a stand-in is reported by name ("executors […] are not in release 1") rather than passed.

- GIVEN a package whose step names `antigravity` WHEN its scenario runs THEN the report names `antigravity` as not in this release

### LIF-B5 Rubric score goes stale

WHEN a rubric scenario's judge brief changes or its judge alias is bound to another model THE engine SHALL read the scenario as `stale` and manual until it is re-scored, a rubric scenario passing only from a recorded score whose digests match.

- GIVEN a rubric scenario scored last week WHEN its brief changes THEN it reads `stale`

### LIF-B14 Harvest

WHEN `evals harvest <workflow> <gate>` runs THE engine SHALL write one candidate per judged attempt a recorded label disagreed with (a gate escape, a person's pushback, an audit disagreement) under `evals/harvest/<gate>/<case_id>/case.json` in the state root, holding the origin (thread, attempt, label ids), the suggested expected status per criterion (`UNMET` where the gate proceeded, `MET` where it blocked), the unit's produced keys and the run's workspace, and no request text and no label, for a person to copy into the package and label.

- GIVEN two labels that disagreed with a gate WHEN harvest runs THEN two candidates exist under the state root and none in the package

### LIF-B15 Live judge scoring

WHEN `evals score <gate> --executor <name>` runs THE engine SHALL run the gate's judge on its calibration cases against a fixed subject and record the score per judge binding (executor, version, alias, model slug, digests), so a judge moved to another executor or model is scored before a gate relies on it ([JCL](judge-calibration.spec.md)).

- GIVEN a judge moved from `sonnet` to `haiku` WHEN readiness is reported THEN the `haiku` binding has no score until `evals score` runs for it

### LIF-B16 Replay

WHEN `evals replay <workflow>` runs THE engine SHALL rerun each judged gate's judge once on every reviewed case of its latest complete score, with kept subjects and no step session, and report the share of equal statuses and verdicts and each changed status in `evals/replays.jsonl`.

- GIVEN a replay of 10 cases with one changed status WHEN it ends THEN the report shows 90% equal and names the changed case

### LIF-B17 An escape is a harvest candidate

WHEN `evals harvest <workflow> outcome` runs THE engine SHALL write one candidate for each escape of the workflow ([OUT-B26](run-outcome.spec.md)) under `evals/harvest/outcome/<case_id>/case.json` in the state root, holding the origin (thread, the pull request's code host, repository and number, the counts and kinds of its entries), the suggested expected status `UNMET` per judged criterion, the run's workspace and no request or review text.

- GIVEN a `met` run whose pull request had a review in state `changes_requested` WHEN `evals harvest <workflow> outcome` runs THEN one candidate for that run exists under the state root and none in the package
- GIVEN a `met` run that is no escape WHEN harvest runs THEN it has no candidate
- GIVEN a canary in a review comment of an escaped run WHEN harvest runs THEN the candidate holds no review text

## Acceptance criteria

- LIF-AC1 (LIF-B1): `update` decides currency by content hash, by a test with equal versions and different files
- LIF-AC2 (LIF-B3, LIF-B11): The diagram-currency test fails on a shape change and passes on a line-ending change
- LIF-AC3 (LIF-B5): A rubric scenario passes only from a score whose digests match
- LIF-AC4 (LIF-B10): The executor compatibility table is read by preflight and shown by `executors`
- LIF-AC5 (LIF-B14): A harvested case contains no request text and is never written outside the state root until a person commits it
- LIF-AC6 (LIF-B12): Prompt lint finds each planted defect of its fixture set and nothing in the shipped workflows
- LIF-AC7 (LIF-B2): A stamp is written only after every upgrade check passes
- LIF-AC8 (LIF-B13, LIF-B6): Each readiness finding of LIF-B13 is produced by a fixture gate, and a `stable` workflow with a gate not `ready` is refused
- LIF-AC9 (LIF-B4): A package scenario finishes on the reference stand-in and names each executor without one
- LIF-AC10 (LIF-B7, LIF-B8, LIF-B9): The installer stops without Python 3.11+, `update --json` prints one object per line, and reconcile never deletes an entry
- LIF-AC11 (LIF-B15, LIF-B16): A score is recorded per judge binding, and a replay reports agreement and each changed status
- LIF-AC12 (LIF-B17): A harvest of a fixture workflow with a `met` run whose pull request had a review in state `changes_requested` and a `met` run that is no escape writes one candidate, for the first run, under the state root and none in the package, holding the pull request's code host, repository and number, the counts and kinds of its entries and no request or review text
- LIF-AC13 (LIF-B18): For each executor of the compatibility table, a version its facts name as confirmed is in its `recorded` versions and inside its `range`, and preflight on that version raises no `executor-version-untested` warning
