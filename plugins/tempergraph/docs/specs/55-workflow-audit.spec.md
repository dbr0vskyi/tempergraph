# Workflow audit

## Purpose

`tempergraph audit` reads one workflow and reports what is likely to make its runs fail, pause, retry, hang or overspend, ranked, with evidence and a remedy for each finding. It is advisory: it never refuses a start, never changes a file and never calls a model, as the overview's contract on read-only verbs requires ([OVR](00-overview.spec.md)). Refusing a broken workflow stays [validation](02-workflow-model.spec.md)'s job; changing a workflow stays the improvement loop's ([SIL](16-self-improvement.spec.md)). It looks in three layers because the causes found in [R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) need different evidence: `definition` reads the workflow package only, `host` reads this machine and the target repository, `history` reads recorded runs. What it checks is a fixed catalog of rules ([ARC](56-audit-rule-catalog.spec.md)); the tool surface comparison has its own spec ([TSA](57-tool-surface-audit.spec.md)), and so does the audit of prompts and the other model-facing text ([PRA](58-prompt-audit.spec.md)). The engine code is `tempergraph.audit` and `tempergraph.cli.audit`; design notes and the release 1 build notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### AUD-B1 Definition only before the first run

WHEN `audit` runs with no `--layer` THE audit SHALL run every built layer whose inputs exist, list each layer it skipped with the reason (`no runs in window`, `--layer not given`, `probe failed`, `the workflow does not validate`, or `not in this release` for a layer not built), and list every rule of a skipped layer as skipped with its `min_n`, never as passed.

- GIVEN a new workflow with no recorded runs WHEN `audit` runs THEN it runs `definition` and `host`, skips `history` with its reason and lists every history rule as skipped

### AUD-B2 Validation leads

WHEN the audited workflow does not validate THE audit SHALL put the validation errors first as `validate:<code>` findings and run the `definition` layer only; and WHEN the workflow is not loaded (an import error) it SHALL show one finding `validate:not_loaded` with the manifest row only.

- GIVEN a workflow with an unbalanced brace WHEN `audit` runs THEN the validation error is the first finding, only `definition` runs and the exit is 0, or 6 with `--fail-on error`

### AUD-B3 Cause ranking from history

WHEN the `history` layer reads the runs of the chosen version in the window THE audit SHALL rank the causes that drove repeats, timeouts, refusals, pauses and cost (R-050 families C1 to C6), show hot spots per unit (repeat share of spend, first-pass yield, timeouts, refusals, pauses per run) and name the highest-weight cause in the summary.

- GIVEN 12 runs where the `expand` gate's repeats are 41% of spend and criterion `reading-sets` is the leading unmet blocker in 9 of 11 RETRY verdicts, while `plan` repeats are 12% of spend WHEN `audit --layer history` runs THEN the first finding is `loop-driver-criterion` on `expand`, error, high, with those numbers, `plan` raises none, and the summary names `expand` as the highest-weight cause

### AUD-B4 Host catches what the definition cannot

WHEN the `host` layer runs THE audit SHALL compare the workflow's declared programs, interpreter and check commands with this machine and the target repository (executor probe facts, programs on `PATH`, documented repository commands, MCP servers and plugin tools a headless session would see, host speed, engine and executor versions) and report each gap.

- GIVEN check runs that prefix `test`, a target whose `package.json` defines `scripts.test`, no `command_resolver` and no Node prefix declared WHEN `audit --layer host` runs THEN it reports `toolchain-not-covered` naming the documented command, and `check-program-missing` when the declared program is not on `PATH`

### AUD-B17 The repository's commands entry is no program

WHEN a workflow lists the entry `@repository` ([CHK-B11](75-check-contract-and-command-runs.spec.md)) in its command allow-list or in a step's commands THE audit SHALL report no `check-program-missing` for the entry in the `host` layer, whatever programs `PATH` holds.

- GIVEN an allow-list of `git status` and `@repository`, a target with no `tempergraph.commands.json` and `git` as the only program on `PATH` WHEN `audit --layer host` runs THEN it reports no `check-program-missing`
- GIVEN a step with the tool `shell` and the commands `git status` and `@repository`, an allow-list of the same two entries and `git` as the only program on `PATH` WHEN `audit --layer host` runs THEN no finding names `@repository`

### AUD-B18 The programs of the target's declared commands are looked up

WHEN a workflow lists `@repository` in its command allow-list or in a step's commands THE audit SHALL report `check-program-missing` in the `host` layer for the first word of each prefix that the target's `tempergraph.commands.json` declares ([CHK-B11](75-check-contract-and-command-runs.spec.md)) when `PATH` lacks that program, pointing the finding at that file.

- GIVEN an allow-list of `git status` and `@repository`, a target whose `tempergraph.commands.json` declares `npm test` and `npm run lint`, and `git` but no `npm` on `PATH` WHEN `audit --layer host` runs THEN it reports one `check-program-missing` for `npm`, pointing at `tempergraph.commands.json`
- GIVEN the same allow-list and target and `git` and `npm` on `PATH` WHEN `audit --layer host` runs THEN it reports no `check-program-missing`
- GIVEN a step with the tool `shell` and the commands `@repository`, an allow-list of `@repository`, a target whose `tempergraph.commands.json` declares `make check` and no `make` on `PATH` WHEN `audit --layer host` runs THEN it reports one `check-program-missing` for `make`
- GIVEN an allow-list of `git status` and `@repository`, a target whose `tempergraph.commands.json` is not valid JSON and `git` as the only program on `PATH` WHEN `audit --layer host` runs THEN it reports no `check-program-missing`

### AUD-B19 The target's declared commands cover its toolchain

WHEN a workflow lists `@repository` in its command allow-list or in a step's commands THE audit SHALL count each prefix that the target's `tempergraph.commands.json` declares as a prefix the workflow declares when it decides `toolchain-not-covered` ([ARC-B10](56-audit-rule-catalog.spec.md)).

- GIVEN an allow-list of `@repository`, a target whose `package.json` defines `scripts.test` and whose `tempergraph.commands.json` declares `npm test` WHEN `audit --layer host` runs THEN it reports no `toolchain-not-covered`
- GIVEN that allow-list and `package.json` and a `tempergraph.commands.json` that declares only `make check` WHEN `audit --layer host` runs THEN it reports `toolchain-not-covered` naming `package.json scripts.test`

### AUD-B5 Small samples are said, not judged

WHEN a history rule has fewer runs than its minimum THE audit SHALL yield no finding for it and list it under skipped with `n=<runs> of <min>` ([ADR-0053](../adr/0053-history-findings-need-a-minimum-sample.adr.md)).

- GIVEN 3 runs in the window and a rule with a minimum of 5 WHEN the audit runs THEN the rule is listed as skipped with `n=3 of 5`

### AUD-B6 Read-only and model-free

WHEN `audit` runs THE audit SHALL leave the state root, the package and the target byte-for-byte unchanged, write its output to stdout only, start no model session, and start no child process beyond the read-only probes of `executors --probe` and the login-shell host-speed timing, under a total budget of 30 s.

- GIVEN any workflow and layers WHEN `audit` runs THEN a hash of the state root, package and target is unchanged and no model session started

### AUD-B7 Quiet by default

WHEN `audit` runs without `--all` THE audit SHALL show only findings at severity `error` or `warning` and confidence `high` or `medium` that are not ignored, and count the rest in the summary; with `--all` it SHALL show every finding, including `info`, `low` confidence and ignored ones, each marked.

- GIVEN 2 warnings at high confidence, 6 info findings and 1 ignored warning WHEN `audit` runs without `--all` THEN 2 findings are shown and the summary reads "2 shown, 6 info, 1 ignored"

### AUD-B8 Owned checks are not duplicated

WHEN a defect is already reported by an owning component THE audit SHALL run that component and show its finding once under the component's code, never restate it as an audit rule ([ADR-0054](../adr/0054-audit-joins-existing-checks-and-files-nothing.adr.md)): validation as `validate:<code>`, prompt lint as `prompt-lint:<code>`, the readiness report as `readiness:needs-work` (warning) and `readiness:needs-cases` (info), the executor compatibility table as `executor-compat:executor-version-untested`; a gate with validation's `gate-not-ready` (stable mode) SHALL get no readiness finding too, and `AuditFinding.owner` SHALL say `audit` or the owning component.

- GIVEN a judge brief that branches on a fact a check could compute WHEN the audit runs THEN the finding appears once, as the validation warning's `validate:<code>` ([WFM](02-workflow-model.spec.md)), and no audit rule restates it

### AUD-B9 CI gate by choice

WHEN `audit` ends THE audit SHALL exit 0 whatever it found by default; with `--fail-on error|warning` exit 6 when any finding not ignored is at or above the level; and exit 2 for an unknown workflow or option or a `--target` that is not a directory, reading nothing beyond the manifest ([CON](01-contracts.spec.md)).

- GIVEN a CI job running `audit --format sarif --fail-on error` WHEN a finding at `error` is not ignored THEN the step exits 6 and the SARIF file lists the finding at its package file

### AUD-B10 Older logs

WHEN history rules that need input summaries read run logs from an older engine without the activity journal THE audit SHALL report what the run log alone supports and mark the rest `unclassified`, never zero.

- GIVEN run logs without activity journals WHEN the refusal-class rule runs THEN its counts read `unclassified`, not 0

### AUD-B11 Verb and options

WHEN an operator runs `tempergraph audit <workflow> [--layer definition|host|history]... [--target <path>] [--executor <name>] [--step <unit>]... [--window <days>] [--version current|all|<id>] [--all] [--format text|json|sarif] [--fail-on error|warning|never]` THE audit SHALL default the target to the current directory, the window to 30 days, the version to `current`, the format to `text` and `--fail-on` to `never`, narrow to the executor binding and units given, and record the window and version in the header; `audit tools <workflow>` SHALL print the tool surface matrix of [TSA](57-tool-surface-audit.spec.md) and `audit prompts <workflow>` one row per model-facing file ([PRA](58-prompt-audit.spec.md)), each with the same options; the function is `audit(spec, layers, ctx) -> AuditReport`, pure over its inputs, with `AuditContext` holding the registry, target, window days, version and executor.

- GIVEN `audit wf --step plan` WHEN it runs THEN only findings on unit `plan` and on the workflow as a whole are shown

### AUD-B12 Report parts and order

WHEN the report is built THE audit SHALL hold a header (workflow, version id, engine version, layers run and skipped with reasons, window and run count, and the count of runs left out as unreadable), findings ordered by severity, then confidence, then the rule's rank in [ARC](56-audit-rule-catalog.spec.md), then unit order, one finding per (rule, unit, item) with several matching fields of one unit listed as its evidence, hot spots per unit (history only), one owned-checks line per owning component with its counts, and a summary of counts by severity, ignored and skipped rules and the one-line highest-weight cause; `AuditReport` and `AuditFinding` are defined in [CON](01-contracts.spec.md).

- GIVEN a rule that matches three fields of one unit WHEN the report is built THEN it is one finding with three evidence lines

### AUD-B13 Output formats

WHEN the format is chosen THE audit SHALL print in text one block per finding (rule id, severity and confidence, unit, a one-line statement, the evidence as numbers with their `n`, the remedy, and the field or file it points at); in JSON the report with `schema_version`, readable by an old reader that skips an unknown key ([CON](01-contracts.spec.md)); and in SARIF each finding mapped to the package file and, where known, the line of the field.

- GIVEN a JSON report with a key an older reader does not know WHEN that reader loads it THEN the key is skipped and the rest is read

### AUD-B14 Accepting a finding

WHEN a package carries `audit.ignore` in `tempergraph.json` (`{"audit": {"ignore": [{rule, unit?, reason, until?}]}}`, [PKG](88-workflow-package.spec.md)) THE audit SHALL count an ignored finding in the summary and show it under `--all`, show it again once `until` has passed, accept as `rule` a catalog id or an owned code (`validate:<code>`, `prompt-lint:<code>`, `readiness:<grade>`, `executor-compat:<code>`) and raise the `info` finding `ignore-rule-unknown` for any other id; validation SHALL refuse an entry without a one-sentence reason or with an `until` that is not a date as `audit-ignore-invalid`, and no ignore SHALL hide a validation error.

- GIVEN an ignore whose `until` was yesterday WHEN `audit` runs THEN the finding shows again
- GIVEN an ignore without a reason WHEN the package validates THEN it is refused with `audit-ignore-invalid`

### AUD-B15 Failures inside the audit

WHEN a probe exceeds its budget or fails, a run log or journal is unreadable, or a rule raises THE audit SHALL skip the rules that need the probe with reason `probe failed`, leave the unreadable run out and count it in the header, skip the raising rule with reason `rule error` and its id while the engine code log records the exception type, and continue the report.

- GIVEN a rule that raises WHEN the audit runs THEN it is listed as skipped with `rule error` and the other findings are shown

### AUD-B16 Where the audit is used

WHEN the definition and host layers are needed outside the verb THE engine SHALL run them the same way for the authoring skill before a first run ([SHL](19-plugin-shell.spec.md)), for `upgrade-check --stamp` as its V4 check ([WUP](63-workflow-upgrade.spec.md)) and for `promote-check` when it requires no unignored `error`; the troubleshooter skill reads `audit --format json` for the workflow of a failed run.

- GIVEN `upgrade-check --stamp` on a package WHEN it runs THEN the V4 result is the `definition` layer's findings

## Acceptance criteria

- AUD-AC1 (AUD-B3, AUD-B4, AUD-B11): Every rule in [ARC](56-audit-rule-catalog.spec.md), [TSA](57-tool-surface-audit.spec.md) and [PRA](58-prompt-audit.spec.md) has a fixture workflow or fixture run set that raises it, and a clean fixture that does not
- AUD-AC2 (AUD-B6, AUD-B16): `audit` leaves the state root, the package and the target unchanged (hash test) and starts no model session (process audit in tests)
- AUD-AC3 (AUD-B1, AUD-B5, AUD-B10): A history rule below its minimum sample yields no finding and is listed as skipped with its `n`
- AUD-AC4 (AUD-B2, AUD-B8): A finding owned by another component appears once, under that component's code, on a fixture that would raise both
- AUD-AC5 (AUD-B9, AUD-B15): `--fail-on` exits 6 exactly when a non-ignored finding is at or above the level, and 0 otherwise, on a corpus of fixtures
- AUD-AC6 (AUD-B12, AUD-B13): The JSON report validates against its schema and carries `schema_version`; an old reader skips an unknown key
- AUD-AC7 (AUD-B7, AUD-B14): An ignore without a reason is refused by validation; a lapsed `until` shows the finding again
- AUD-AC8 (AUD-B17): A fixture workflow whose allow-list and a step's commands hold `git status` and `@repository`, audited with `git` as the only program on `PATH` and a target with no `tempergraph.commands.json`, raises no `check-program-missing` and no finding that names `@repository`
- AUD-AC10 (AUD-B18): For a target whose `tempergraph.commands.json` declares `npm test` and `npm run lint`, the `host` layer reports one `check-program-missing` for `npm`, pointing at that file, when `npm` is not on `PATH` and none when it is; for a target whose file is not valid JSON it reports none
- AUD-AC11 (AUD-B19): For a target whose `package.json` defines `scripts.test` and a workflow whose allow-list is `@repository`, the `host` layer reports no `toolchain-not-covered` when `tempergraph.commands.json` declares `npm test` and reports it, naming `package.json scripts.test`, when the file declares only `make check`

## Open questions

- Should a model-assisted review (a large-tier reading of prompts and skills across files, which can find defects no single-file rule sees) ship later as a separate built-in workflow that the audit can suggest? Until answered: no; it is outside this verb, which calls no model. Owner: owner.
- Should the monitor show the audit's summary counts per workflow? Until answered: no. Owner: monitor design.
- Not built yet: the post-release watch behind `prompt-change-moved-gate` and the probe that lists plugin tools for `judge-ambient-tool`, both skipped with their reason until they exist; and the history facts the run log does not record yet (the judgement's `no_change` blockers for `no-change-retried`, the renderer's cut flag for `rendered-near-cut`), so those two rules stay quiet on real logs. Owner: engine owner.
