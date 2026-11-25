---
goal: Build run operations — the CLI's core verbs and exit codes, then settings, tool grants, feedback and reruns, and caller provenance
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: Completed
tags: [track-plan, tempergraph, T6]
tracker: none
spec: plugins/tempergraph/docs/specs/engine-cli.spec.md
spec_commit: 41ca415
task_id: first-release-t6
---

# T6 Run operations

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T6 |
| Specs | [CLI](../specs/engine-cli.spec.md), [RST](../specs/run-settings-and-overrides.spec.md), [RRN](../specs/reruns-and-feedback.spec.md), [PRV](../specs/caller-provenance.spec.md) |

**Status: Completed** for the offline build. Milestone M1 holds on stand-ins: a two-step workflow defined in Python test code runs end to end through `tempergraph run`, pauses with exit 3, and finishes through `tempergraph resume`. What is left needs a signed-in Claude Code on the owner's machine: M1 on a live `claude` (T0.1), the MCP and plugin listing check (6.3.5), and the probes P-SUP-1, P-SUP-2 and P-SUP-4 (6.5.5).

Status pass: CLI, RST, RRN and PRV are `ready-for-implementation`. RST, RRN and PRV have release 1 defaults for their open questions.

Doc changes this track made:
- ROP-B1 to ROP-B13 adds `--task-id` and `--input` on `run`.
- ROP-B1 to ROP-B13 gives the resolution rule for a workflow with no resolver, so the same request finds the same thread.
- ROP-B1 to ROP-B13 gives the exit codes of `run --check` and says where machine output goes.

The catalog reads the home registry and loads each package by the first steps of PKG-B15, PKG-B16, PKG-B17 (both manifests, the entry import from `workflow/`, the build). The rest of PKG-B15, PKG-B16, PKG-B17 is T8.1: the private import name, the source scan, the interface level, `outcome.json` and the package rules.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-20 | CLI | all, for the release 1 verbs of ADR-0090 (T6.1 here; the observability verbs in T7.4) | T6.1 |
| REQ-21 | RST | all but rows for orchestration, council, contest and switch-arm keys | T6.2, T6.3 |
| REQ-22 | RRN | all but §2.6 | T6.4 |
| REQ-23 | PRV | all; AC-6 for P-SUP-1 and P-SUP-2 | T6.5 |

## 2. Phases

### T6.1 Core verbs

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 6.1.1 | `engine/tests/test_cli.py` | M1 through the CLI; pause exit 3 and resume; `run --check` creates nothing and agrees with `run` on refusals; usage refusals exit 2; read-only verbs leave the state root unchanged (hash test); `executors` shows live facts as `not run`; exit codes and reserved words against the spec text | CLI-B1, CLI-AC1 | yes | P1 | ✓ | 2026-11-20 |
| 6.1.2 | `engine/src/tempergraph/catalog.py` | `Catalog`, `load_package` (PKG-B15, PKG-B16, PKG-B17 steps 1, 3, 4), `from_registry`, `resolve_request` | ROP-B1 to ROP-B13, CON-B9, UPD-B20 to UPD-B24 | | P1 | ✓ | 2026-11-20 |
| 6.1.3 | `engine/src/tempergraph/cli/main.py` | `run`, `run --check`, `resume`, `status`, `list`, `validate`, `executors [--probe]`, `facts`, `graph`, `wait`, `stop`, `worktree list` and `path`; reserved words; exit codes; `entry` for the `tempergraph` script | CLI-B7, CLI-B8, CLI-B14, CLI-B17, CLI-B18, CLI-B19 | | P1 | ✓ | 2026-11-20 |
| 6.1.4 | `engine/tests/test_contract_tables.py` | Drift tests for the hand-written CLI tables (CLI-AC7, as revised): the verb words equal `VERBS`, every built long option is documented in CLI, RST or PRV, exit codes equal CON-B12, CON-B13 | CLI-AC7 | yes | P2 | ✓ | 2026-11-20 |
| 6.1.5 | — | `attention` (CLI-B6, AC-5): moved to T7.4, which builds it with the reports | CLI-B6 | | | moved | |
| 6.1.6 | `engine/src/tempergraph/cli/main.py`, `run/runner.py` | The other run options of ROP-B1 to ROP-B13: executor and model overrides, timeouts, `--approve` (spellings of `--set`, T6.2); `--auto-reopen` (BUD-B6: a retry by the `engine` caller after a `budget` or `infra` stop, at most N per thread, also after a resume or rerun); `--pause-before` refused `not_in_release` (FLX is X2-13); `--dry-run` recorded on `run_started` and in the run's meta for the loop (T12) | ROP-B1 to ROP-B13, RST, BUD-B6 | yes | P1 | ✓ | 2026-11-20 |

### T6.2 Settings

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 6.2.1 | `engine/tests/test_settings.py` | RST-B1, B2, B5 to B11 on the resolver; AC-2 (refusals create nothing), AC-3 (property: no step key reaches a judge, tighten-only stays true), AC-5 (snapshot on resume), AC-7 (text canary); `config show` equals `settings_resolved` | RST-B1 to RST-B15, RST-AC1 | yes | P1 | ✓ | 2026-11-20 |
| 6.2.2 | `engine/src/tempergraph/settings.py` | The catalog of RST-B18, RST-B19, RST-B20, RST-B21, key parsing with the nearest name, the layers of §2.3 (no `arm:` layer: measured switches are release 2), both files, profiles first found whole, the snapshot, `resolve`, `validate_overrides`, the digest, and `effective_spec`: resolved values written into the spec the run executes, judges' models resolved on the judge chain | RST-B17, RST-B18, RST-B19, RST-B20, RST-B21, RST-B22, RST-B23, RST-B24, RST-B25, RST-B26 | | P1 | ✓ | 2026-11-20 |
| 6.2.3 | `engine/src/tempergraph/run/runner.py` | `settle_start` and `settle_resume` (`--set`, `--unset`, `--profile`, `--reload-settings`); the snapshot in `run.options`; `settings_resolved` after `run_started`; `run_started` and the ledger row carry `settings_digest` and `overridden_keys`; run values reach the context (attempt cap, infra tries and backoff, human cap, enforcement, workspace, branch prefix, `.worktreeinclude`); workflow settings reach checks | RST-B26, RST-B27 | | P1 | ✓ | 2026-11-20 |
| 6.2.4 | `engine/src/tempergraph/cli/main.py` | `--set`, `--settings`, `--profile` on `run`, `resume` and `config show`; `--unset`, `--reload-settings` on `resume`; the named spellings of ROP-B1 to ROP-B13; `config show`, `config validate`, `config paths` | RST-B31, ROP-B1 to ROP-B13 | | P1 | ✓ | 2026-11-20 |
| 6.2.5 | `engine/src/tempergraph/durability/status.py` | The status row's `settings_digest`, `overridden_keys` and `settings_stale` (T7 owns the status row; handed over, built in T7) | RST-B27 | yes | P2 | ✓ | 2026-11-20 |

Release 1 notes: keys whose feature is release 2 (the audit judge, switch arms, council, contest, wait and ask keys, the `in_repo` and `path:` roots, the `default_branch` base, `cleanup: on_finish`) are refused with `setting_not_in_release` (RST-B32). The `ref:<name>` base is built for trial cases (plan T12.6): it resolves with `git rev-parse --verify` and an unresolvable or malformed name is `base_unresolved`, exit 2 before spend (WTR-B21). No key is refused with `setting_not_built` any more: `run.auto_reopen` (6.1.6) and the widening keys (T6.3) are built.

### T6.3 Tool grants

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 6.3.1 | `engine/tests/test_settings.py` | RST-B13 end to end (pause offers the grant, resume applies it, a later resume keeps it), the refusal rows of its table, AC-8 property (no judge view grant beyond read-only), `widening_by_agent` | RST-B28, RST-B29, RST-B30, RST-B1 to RST-B15 | yes | P1 | ✓ | 2026-11-20 |
| 6.3.2 | `engine/src/tempergraph/settings.py` | `tools.add`, `commands.add`, `views.add` in the catalog; grants widen the step, the allow-list and the judge view; `widening: true` rows; grants union on resume | RST-B28, RST-B29, RST-B30 | | P1 | ✓ | 2026-11-20 |
| 6.3.3 | `engine/src/tempergraph/run/tool_access.py`, `run/nodes.py`, `run/gate.py` | Refused and missing names with their class and fix on the attempt; the `tool_access` escalation payload and `pause` record | RST-B28, RST-B29, RST-B30, BUD-B1, BUD-B11, TSA-B7 | | P1 | ✓ | 2026-11-20 |
| 6.3.4 | `engine/src/tempergraph/run/runner.py`, `cli/main.py` | `--grant`, `--allow-command`; the `grant` record with `answers`; intervention and ledger `grants[]` with `used` | EVT-B10 to EVT-B16, HUM-B6 | | P1 | ✓ | 2026-11-20 |
| 6.3.5 | `engine/src/tempergraph/executors/claude.py` | `mcp-server-not-configured` and the skill-plugin check before spend need the executor's MCP and plugin listing (live probe); until then a missing server shows at run time as `missing_at_start` | RST-B13, B14 | yes | P2 | ○ | |

### T6.4 Feedback, rulings, rewind, rerun

`--feedback` and `--feedback-file` on `resume`, and `rewind:<unit>` decisions, work through the T5 human node.

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 6.4.1 | `engine/tests/test_feedback.py` | RRN-B1, B2, B4, B11; AC-2 on the two-step fixture; AC-6 canary; §4 refusals write nothing | RRN-B14, RRN-B15, RRN-B1 to RRN-B11 | yes | P1 | ✓ | 2026-11-20 |
| 6.4.2 | `engine/src/tempergraph/run/gate.py`, `run/nodes.py`, `run/runner.py`, `cli/main.py` | `--ruling`, `--ruling-for`, `--revoke-ruling`; rulings in state, shown to every later attempt and judge with the `ruling` blocker; the limits; feedback without a decision on an unfinished thread; the `ruling` record; one-time feedback now reaches the judge and is cleared at the gate | RRN-B14, RRN-B15, EVT-B10 to EVT-B16 | | P1 | ✓ | 2026-11-20 |
| 6.4.3 | `engine/src/tempergraph/run/rerun.py`, `engine/tests/test_rerun.py` | `rerun` as a linked fork (RRN-B17, RRN-B18): the fork point from the checkpoint history, the copy to `<task>~r<n>`, the trip back from the unit, fresh budgets and cost, the source's settings snapshot plus the rerun's flags, `--feedback` as the visit reason or `--ruling`, `--drop-rulings`, `--workspace current\|at-unit` on a new branch `<branch>-r<n>`, `rerun --check`, `lineage.json`, `run_started.rerun_of`; RRN-B6, B7, B8, AC-3, AC-4 | RRN-B16, RRN-B17, RRN-B18 | yes | P1 | ✓ | 2026-11-20 |
| 6.4.4 | `engine/src/tempergraph/run/rerun.py` | `--same-branch` on a finished source (its branch and kept worktree, `superseded_by` in `lineage.json`) ✓; the MIG-B15 tests beyond "units behind" and rerun of one map item are release 2 (MIG is X2-6; maps) | RRN-B17, RRN-B18 | yes | P2 | ✓ | 2026-11-20 |
| 6.4.5 | `engine/src/tempergraph/run/runner.py` | `rewind:<unit>` past external effects needs `--accept-external` | RRN-B16 | yes | P1 | ✓ | 2026-11-20 |

### T6.5 Caller provenance

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 6.5.1 | `engine/tests/test_provenance.py` | PRV-AC1 classification rows, AC-4 property (a marker never gives a person), the §4 refusals, PRV-B4 relay table, B5 `caller_conflict`, B9 and AC-5 (a relayed grant needs a named person turn) | PRV-B13, PRV-B14, PRV-B1 to PRV-B10 | yes | P1 | ✓ | 2026-11-20 |
| 6.5.2 | `engine/src/tempergraph/provenance.py` | `classify` (S2 to S6; S1 and S1s refused in release 1), `decide` with the person turns of the host session's journal, `may_widen` | PRV-B13, PRV-B14, PRV-B21, PRV-B22 | | P1 | ✓ | 2026-11-20 |
| 6.5.3 | `engine/src/tempergraph/cli/main.py`, `run/runner.py`, `run/rerun.py` | `--caller`, `--as-agent`, `--caller-app`, `--relayed` on `run`, `resume`, `rerun` and `stop`; the caller block on `run_started`, the human record and the intervention row; `relay_not_applicable`; widening needs `may_widen`; read-only verbs and `--check` never classify | PRV-B12, PRV-B16, PRV-B17, ROP-B1 to ROP-B13 | | P1 | ✓ | 2026-11-20 |
| 6.5.4 | `engine/src/tempergraph/run/supervision.py`, `engine/tests/test_supervision.py` | The `supervision` record before every `run_exit` and on the `run_segment` ledger row: touches by class and decider, waits, latency, sessions, level and `level_by`; a rerun counts as a steer on its source; cost fields and `observations` null until T7.6 | SUP-B10, SUP-B11, SUP-B1 to B3 | yes | P1 | ✓ | 2026-11-20 |
| 6.5.5 | — | P-SUP-1, P-SUP-2, P-SUP-4 on a signed-in Claude Code (PRV-AC6); the journal itself is written by the SCO hooks (T7.6) | PRV-AC6 | | P2 | ○ | |

## 3. Verification

From `plugins/tempergraph/engine/`: `python -m pytest`, `ruff check src tests` and `mypy` are clean. No test calls a model.
