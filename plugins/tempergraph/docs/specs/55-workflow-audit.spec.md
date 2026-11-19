---
title: Workflow audit
type: component
status: review
prefix: AUD
adrs: [0050, 0051, 0053, 0054, 0015]
---

# Workflow audit

## 1. Overview

`tempergraph audit` reads one workflow and reports what is likely to make its runs fail, pause, retry, hang or overspend, ranked, with evidence and a remedy for each finding. It is **advisory**: it never refuses a start, never changes a file and never calls a model (contract C13). Refusing a broken workflow stays [validation](02-workflow-model.spec.md)'s job; changing a workflow stays the improvement loop's ([SIL](16-self-improvement.spec.md)).

The audit looks in three **layers**, because the causes found in [R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) need different evidence:

| Layer | Reads | Finds (R-050 family) |
|---|---|---|
| `definition` | The workflow package only: spec, prompts, briefs, criteria, declared tools and commands, limits | Shapes known to loop (C1), timeout and hold-time exposure (C3), tool-grant defects (C4), pauses that cannot help (C5), cost shape (C6), prompt defects (C7) |
| `host` | This machine and the target repository: executor probe facts, programs on `PATH`, the declared interpreter, documented repository commands, MCP servers and plugin tools a headless session would see, host speed | Environment causes (C2), tool exposure (C4), engine and executor versions (C8) |
| `history` | Recorded runs of this workflow in a window: run logs, judgements, ledger rows, activity journals where present, the cost lens's output | What actually drove repeats, timeouts, refusals, pauses and cost (C1 to C6) |

What it checks is a fixed catalog of rules ([ARC](56-audit-rule-catalog.spec.md)); the tool surface comparison for steps and judges has its own spec ([TSA](57-tool-surface-audit.spec.md)). Rules that another component already owns (validation, prompt lint, the judge readiness report, judge calibration, the cost lens) are run through that component and shown, never reimplemented ([ADR-0054](../adr/0054-audit-joins-existing-checks-and-files-nothing.adr.md)).

## 2. Contract

### 2.1 Verb

```text
tempergraph audit <workflow>
    [--layer definition|host|history]...     # default: every layer whose inputs exist
    [--target <path>]                        # repository the runs will work on; default: current directory
    [--executor <name>] [--step <unit>]...   # narrow to one executor binding or some units
    [--window <days>] [--version current|all|<id>]   # history; default 30 days, current version
    [--all]                                  # also low-confidence and info findings, and ignored ones
    [--format text|json|sarif]               # default text
    [--fail-on error|warning|never]          # default never
audit tools <workflow> [same options]        # the tool surface matrix of TSA §2.3 instead of findings
```

```python
def audit(spec: WorkflowSpec, layers: set[Layer], ctx: AuditContext) -> AuditReport: ...  # pure over its inputs
class AuditContext: registry: Registry; target: Path; window_days: int; version: str; executor: str | None
```

| Rule | Value |
|---|---|
| Writes | Nothing under the state root, the package or the target; `--format` output goes to stdout only |
| Spends | No model call. The `host` layer may start the read-only probes of `executors --probe` and the host-speed probe, under a total budget of 30 s |
| Order | Validation first. A workflow that does not validate is audited in `definition` only, and its validation errors lead the report |
| Exit | `0` by default whatever is found; with `--fail-on`, `6` when any finding not ignored is at or above the level; `2` for an unknown workflow or option ([CON §2.9](01-contracts.spec.md)) |

### 2.2 Report

`AuditReport` and `AuditFinding` are defined in [CON §2.11](01-contracts.spec.md). The report holds:

| Part | Content |
|---|---|
| Header | Workflow, version id, engine version, layers run, layers skipped with the reason (`no runs in window`, `--layer` not given, `probe failed`), window and run count |
| Findings | Ordered by severity, then confidence, then the rule's rank in [ARC](56-audit-rule-catalog.spec.md), then unit order |
| Hot spots | Per unit: repeat share of spend, first-pass yield, timeouts, refusals, pauses per run (history only) |
| Owned checks | One line per owning component whose output was included: validation, prompt lint, readiness, judge acceptance, cost lens; with its own counts |
| Summary | Counts by severity, ignored count, skipped rules count, the one-line "highest-weight cause" |

Text output prints one finding per block: rule id, severity and confidence, unit, a one-line statement, the evidence (numbers with their `n`), the remedy, and the field or file it points at. JSON carries `schema_version` ([CON §2.10](01-contracts.spec.md)); SARIF maps a finding to the package file and, where known, the line of the field.

### 2.3 Views and noise

| View | Shows |
|---|---|
| Default | Findings with severity `error` or `warning` and confidence `high` or `medium`, not ignored |
| `--all` | Every finding, including `info`, `low` confidence and ignored ones, each marked |

One finding per (rule, unit, item); a rule that matches several fields of one unit lists them as evidence of one finding.

### 2.4 Accepting a finding

A workflow package may carry `audit.ignore`, a list of `{rule, unit?, reason, until?}`. `reason` is required (one sentence); `until` is an optional date after which the ignore lapses. An ignored finding is counted in the summary and shown under `--all`. An ignore for a rule id the catalog does not know is itself an `info` finding. Ignores cannot hide a validation error.

## 3. Behaviours

**AUD-B1 Definition only, before the first run.** Given a new workflow with no recorded runs, when `audit` runs, then it runs `definition` and `host`, skips `history` with reason `no runs in window`, and every history rule is listed as skipped, never as passed.

**AUD-B2 Validation leads.** Given a workflow with an unbalanced brace, when `audit` runs, then the validation error is the first finding (rule `validate:<code>`), only the `definition` layer runs, and the exit is `0` unless `--fail-on error` is given, then `6`.

**AUD-B3 Cause ranking from history.** Given 12 runs of the current version in the window, where the `expand` gate's repeats are 41% of spend and criterion `reading-sets` is the leading unmet blocker in 9 of 11 RETRY verdicts, when `audit --layer history` runs, then the first finding is `loop-driver-criterion` on `expand` with those numbers, and the summary names it as the highest-weight cause.

| Unit | Repeat share | Leading criterion (RETRYs) | First-pass yield | Finding |
|---|---|---|---|---|
| expand | 41% | `reading-sets` (9 of 11) | 2 of 12 | `loop-driver-criterion`, error, high |
| plan | 12% | `doc-rows` (2 of 3) | 9 of 12 | none (below the rule's share) |

**AUD-B4 Host catches what the definition cannot.** Given a workflow whose check runs prefix `test` and a target repository with a `package.json` whose `scripts.test` is defined, no `command_resolver` and no Node prefix declared, when `audit --layer host` runs, then it reports `toolchain-not-covered` naming the documented command, and `check-program-missing` if the declared program is not on `PATH`.

**AUD-B5 Small samples are said, not judged.** Given 3 runs in the window and a history rule with a minimum of 5, when the audit runs, then the rule yields no finding and the report lists it under skipped with `n=3 of 5` ([ADR-0053](../adr/0053-history-findings-need-a-minimum-sample.adr.md)).

**AUD-B6 Read-only and model-free.** Given any workflow and layers, when `audit` runs, then the state root, the package and the target are byte-for-byte unchanged, no model session is started, and the only child processes are the probes of §2.1.

**AUD-B7 Quiet by default.** Given a workflow with 2 warnings at high confidence, 6 info findings and 1 ignored warning, when `audit` runs without `--all`, then 2 findings are shown and the summary reads "2 shown, 6 info, 1 ignored".

**AUD-B8 Owned checks are not duplicated.** Given a judge brief that branches on a fact a check could compute, when the audit runs, then the finding appears once, as the `validate:<code>` of that warning in [WFM §2.2](02-workflow-model.spec.md), and no audit rule restates it.

**AUD-B9 CI gate by choice.** Given a CI job running `audit --format sarif --fail-on error`, when a finding at `error` is not ignored, then the job's step exits `6` and the SARIF file lists the finding at its package file.

**AUD-B10 Older logs.** Given run logs from an older engine without the activity journal, when history rules that need input summaries run, then they report what the run log alone supports and mark the rest `unclassified`, never zero ([CON §2.10](01-contracts.spec.md)).

## 4. Error conditions

| Condition | Result |
|---|---|
| Unknown workflow or option | Exit 2; nothing read beyond the manifest |
| Workflow not loaded (import error) | One finding `validate:not_loaded`; only the manifest row is shown; exit 0, or 6 with `--fail-on error` |
| A probe exceeds its budget or fails | The rules that need it are skipped with reason `probe failed`; the report continues |
| A run log or journal unreadable | That run is left out; the count of left-out runs is in the header |
| A rule raises | That rule is skipped with reason `rule error` and its id; the report continues; the engine code log records the exception type |
| `--target` is not a directory | Exit 2 |

## 5. Design notes

- **Advisory, separate from `validate`.** Validation is a gate: the same function guards every start and must stay fast, deterministic and free of the host and of history. The audit reads more, may be wrong in a ranked way, and must never block a start ([ADR-0050](../adr/0050-advisory-read-only-audit-verb-in-three-layers.adr.md)).
- **A fixed catalog, keyed to causes.** Each rule carries a cause code shared with the self-improvement loop, so a static finding and a history finding about the same defect group together, and a proposal ([PRP](40-improvement-proposals.spec.md)) can cite both ([ADR-0051](../adr/0051-audit-rules-are-a-fixed-catalog-keyed-to-causes.adr.md)).
- **Quiet by default.** R-050 N1: a signal raised on every run ranks nothing. The default view, the per-rule confidence and the minimum samples exist for that.
- **Where it is used.** The authoring skill runs `audit --layer definition --layer host` before the first run and walks the author through each finding ([SHL](19-plugin-shell.spec.md)); the troubleshooter skill reads `audit --format json` for the workflow of a failed run; `promote-check` ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)) may require no unignored `error`; a CI job may gate on `--fail-on`.
- **History sources.** The audit reads the run log ([OBS](15-observability-and-cost.spec.md)) and the ledger ([SIL](16-self-improvement.spec.md)); where the activity journal of spec 30 (PR 7) exists it adds input summaries for refusal classes; where the shared run store of spec 34 (PR 7) is configured, `--source` may be added later. Until those merge, the run log alone is enough for every rule except refusal classes.
- **Exit 6** is new: an advisory verb must not reuse a code that means a run ended, so CI can tell "the audit found something" from "the audit could not run" (2).

## 6. Acceptance criteria

- [ ] AUD-AC-1 Every rule in [ARC](56-audit-rule-catalog.spec.md) and [TSA](57-tool-surface-audit.spec.md) has a fixture workflow or fixture run set that raises it, and a clean fixture that does not.
- [ ] AUD-AC-2 `audit` leaves the state root, the package and the target unchanged (hash test) and starts no model session (process audit in tests).
- [ ] AUD-AC-3 A history rule below its minimum sample yields no finding and is listed as skipped with its `n`.
- [ ] AUD-AC-4 A finding owned by another component appears once, under that component's code, on a fixture that would raise both.
- [ ] AUD-AC-5 `--fail-on` exits 6 exactly when a non-ignored finding is at or above the level, and 0 otherwise, on a corpus of fixtures.
- [ ] AUD-AC-6 The JSON report validates against its schema and carries `schema_version`; an old reader skips an unknown key.
- [ ] AUD-AC-7 An ignore without a reason is refused by validation; a lapsed `until` shows the finding again.

## Open questions

| Question | Owner |
|---|---|
| Should the monitor show the audit's summary counts per workflow? | Monitor design (PR 7) |

## References

[R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) · [R-051](../research/R-051-prior-art-for-workflow-audits.rsrch.md) · [ARC](56-audit-rule-catalog.spec.md) · [TSA](57-tool-surface-audit.spec.md) · [WFM](02-workflow-model.spec.md) · [LIF](18-lifecycle-and-evals.spec.md) · [SIL](16-self-improvement.spec.md) · [CLI](17-engine-cli.spec.md)
