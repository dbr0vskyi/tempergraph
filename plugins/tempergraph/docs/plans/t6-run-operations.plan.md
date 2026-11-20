---
goal: Build run operations — the CLI's core verbs and exit codes, then settings, tool grants, feedback and reruns, and caller provenance
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: In progress
tags: [track-plan, tempergraph, T6]
tracker: none
spec: plugins/tempergraph/docs/specs/17-engine-cli.spec.md
spec_commit: 41ca415
task_id: first-release-t6
---

# T6 Run operations

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T6 |
| Specs | [CLI](../specs/17-engine-cli.spec.md), [RST](../specs/80-run-settings-and-overrides.spec.md), [RRN](../specs/81-reruns-and-feedback.spec.md), [PRV](../specs/85-caller-provenance.spec.md) |

**Status: In progress.** T6.1 is built, so milestone M1 holds on stand-ins: a two-step workflow defined in Python test code runs end to end through `tempergraph run`, pauses with exit 3, and finishes through `tempergraph resume`. M1 on a signed-in `claude` waits for the owner's machine (T0.1). T6.2 to T6.5 are built but for the rows marked ○ below. The live probes P-SUP-1, P-SUP-2 and P-SUP-4 wait on the owner's machine.

Status pass: CLI, RST, RRN and PRV are `ready-for-implementation`. RST, RRN and PRV have release 1 defaults for their open questions.

Doc changes this track made:
- CLI §2.1 adds `--task-id` and `--input` on `run`.
- CLI §2.1 gives the resolution rule for a workflow with no resolver, so the same request finds the same thread.
- CLI §2.1 gives the exit codes of `run --check` and says where machine output goes.

The catalog reads the home registry and loads each package by the first steps of PKG §2.3 (both manifests, the entry import from `workflow/`, the build). The rest of PKG §2.3 is T8.1: the private import name, the source scan, the interface level, `outcome.json` and the package rules.

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
| 6.1.1 | `engine/tests/test_cli.py` | M1 through the CLI; pause exit 3 and resume; `run --check` creates nothing and agrees with `run` on refusals; usage refusals exit 2; read-only verbs leave the state root unchanged (hash test); `executors` shows live facts as `not run`; exit codes and reserved words against the spec text | CLI §3, §6 | yes | P1 | ✓ | 2026-11-20 |
| 6.1.2 | `engine/src/tempergraph/catalog.py` | `Catalog`, `load_package` (PKG §2.3 steps 1, 3, 4), `from_registry`, `resolve_request` | CLI §2.1, CON §2.3, UPD §2.8 | | P1 | ✓ | 2026-11-20 |
| 6.1.3 | `engine/src/tempergraph/cli/main.py` | `run`, `run --check`, `resume`, `status`, `list`, `validate`, `executors [--probe]`, `facts`, `graph`, `wait`, `stop`, `worktree list` and `path`; reserved words; exit codes; `entry` for the `tempergraph` script | CLI §2, §4 | | P1 | ✓ | 2026-11-20 |
| 6.1.4 | `engine/src/tempergraph/cli/main.py` | Generated verb, option and exit code tables in the docs with a drift test (CLI §5) | CLI §5 | yes | P2 | ○ | |
| 6.1.5 | — | `attention` (CLI-B6, AC-5): moved to T7.4, which builds it with the reports | CLI-B6 | | | moved | |
| 6.1.6 | `engine/src/tempergraph/cli/main.py`, `run/runner.py` | The other run options of CLI §2.1: executor and model overrides, timeouts, `--approve` (spellings of `--set`, T6.2); `--auto-reopen` (BUD-B6: a retry by the `engine` caller after a `budget` or `infra` stop, at most N per thread, also after a resume or rerun); `--pause-before` refused `not_in_release` (FLX is X2-13); `--dry-run` recorded on `run_started` and in the run's meta for the loop (T12) | CLI §2.1, RST, BUD-B6 | yes | P1 | ✓ | 2026-11-20 |

### T6.2 Settings

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 6.2.1 | `engine/tests/test_settings.py` | RST-B1, B2, B5 to B11 on the resolver; AC-2 (refusals create nothing), AC-3 (property: no step key reaches a judge, tighten-only stays true), AC-5 (snapshot on resume), AC-7 (text canary); `config show` equals `settings_resolved` | RST §3, §6 | yes | P1 | ✓ | 2026-11-20 |
| 6.2.2 | `engine/src/tempergraph/settings.py` | The catalog of RST §2.2, key parsing with the nearest name, the layers of §2.3 (no `arm:` layer: measured switches are release 2), both files, profiles first found whole, the snapshot, `resolve`, `validate_overrides`, the digest, and `effective_spec`: resolved values written into the spec the run executes, judges' models resolved on the judge chain | RST §2.1–2.6 | | P1 | ✓ | 2026-11-20 |
| 6.2.3 | `engine/src/tempergraph/run/runner.py` | `settle_start` and `settle_resume` (`--set`, `--unset`, `--profile`, `--reload-settings`); the snapshot in `run.options`; `settings_resolved` after `run_started`; `run_started` and the ledger row carry `settings_digest` and `overridden_keys`; run values reach the context (attempt cap, infra tries and backoff, human cap, enforcement, workspace, branch prefix, `.worktreeinclude`); workflow settings reach checks | RST §2.6, §2.7 | | P1 | ✓ | 2026-11-20 |
| 6.2.4 | `engine/src/tempergraph/cli/main.py` | `--set`, `--settings`, `--profile` on `run`, `resume` and `config show`; `--unset`, `--reload-settings` on `resume`; the named spellings of CLI §2.1; `config show`, `config validate`, `config paths` | RST §2.9, CLI §2.1 | | P1 | ✓ | 2026-11-20 |
| 6.2.5 | `engine/src/tempergraph/durability/status.py` | The status row's `settings_digest`, `overridden_keys` and `settings_stale` (T7 owns the status row; handed over) | RST §2.7 | yes | P2 | moved | |

Release 1 notes: keys whose feature is release 2 (the audit judge, switch arms, council, contest, wait and ask keys, the `in_repo` and `path:` roots, the `default_branch` and `ref:` bases, `cleanup: on_finish`) are refused with `setting_not_in_release` (RST §4). No key is refused with `setting_not_built` any more: `run.auto_reopen` (6.1.6) and the widening keys (T6.3) are built.

### T6.3 Tool grants

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 6.3.1 | `engine/tests/test_settings.py` | RST-B13 end to end (pause offers the grant, resume applies it, a later resume keeps it), the refusal rows of its table, AC-8 property (no judge view grant beyond read-only), `widening_by_agent` | RST §2.8, §3 | yes | P1 | ✓ | 2026-11-20 |
| 6.3.2 | `engine/src/tempergraph/settings.py` | `tools.add`, `commands.add`, `views.add` in the catalog; grants widen the step, the allow-list and the judge view; `widening: true` rows; grants union on resume | RST §2.8 | | P1 | ✓ | 2026-11-20 |
| 6.3.3 | `engine/src/tempergraph/run/tool_access.py`, `run/nodes.py`, `run/gate.py` | Refused and missing names with their class and fix on the attempt; the `tool_access` escalation payload and `pause` record | RST §2.8, BUD §2.2, TSA §2.2 | | P1 | ✓ | 2026-11-20 |
| 6.3.4 | `engine/src/tempergraph/run/runner.py`, `cli/main.py` | `--grant`, `--allow-command`; the `grant` record with `answers`; intervention and ledger `grants[]` with `used` | EVT §2.2, HUM-B6 | | P1 | ✓ | 2026-11-20 |
| 6.3.5 | `engine/src/tempergraph/executors/claude.py` | `mcp-server-not-configured` and the skill-plugin check before spend need the executor's MCP and plugin listing (live probe); until then a missing server shows at run time as `missing_at_start` | RST-B13, B14 | yes | P2 | ○ | |

### T6.4 Feedback, rulings, rewind, rerun

`--feedback` and `--feedback-file` on `resume`, and `rewind:<unit>` decisions, work through the T5 human node.

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 6.4.1 | `engine/tests/test_feedback.py` | RRN-B1, B2, B4, B11; AC-2 on the two-step fixture; AC-6 canary; §4 refusals write nothing | RRN §2.2, §3 | yes | P1 | ✓ | 2026-11-20 |
| 6.4.2 | `engine/src/tempergraph/run/gate.py`, `run/nodes.py`, `run/runner.py`, `cli/main.py` | `--ruling`, `--ruling-for`, `--revoke-ruling`; rulings in state, shown to every later attempt and judge with the `ruling` blocker; the limits; feedback without a decision on an unfinished thread; the `ruling` record; one-time feedback now reaches the judge and is cleared at the gate | RRN §2.2, EVT §2.2 | | P1 | ✓ | 2026-11-20 |
| 6.4.3 | `engine/src/tempergraph/run/rerun.py`, `engine/tests/test_rerun.py` | `rerun` as a linked fork (RRN §2.4): the fork point from the checkpoint history, the copy to `<task>~r<n>`, the trip back from the unit, fresh budgets and cost, the source's settings snapshot plus the rerun's flags, `--feedback` as the visit reason or `--ruling`, `--drop-rulings`, `--workspace current\|at-unit` on a new branch `<branch>-r<n>`, `rerun --check`, `lineage.json`, `run_started.rerun_of`; RRN-B6, B7, B8, AC-3, AC-4 | RRN §2.3, §2.4 | yes | P1 | ✓ | 2026-11-20 |
| 6.4.4 | `engine/src/tempergraph/run/rerun.py` | `--same-branch` and `superseded_by` (refused `same_branch_not_built` until then); the MIG §2.5 tests beyond "units behind"; rerun of one map item (release 2 with maps) | RRN §2.4 | yes | P2 | ○ | |
| 6.4.5 | `engine/src/tempergraph/run/runner.py` | `rewind:<unit>` past external effects needs `--accept-external` | RRN §2.3 | yes | P1 | ✓ | 2026-11-20 |

### T6.5 Caller provenance

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 6.5.1 | `engine/tests/test_provenance.py` | PRV-AC-1 classification rows, AC-4 property (a marker never gives a person), the §4 refusals, PRV-B4 relay table, B5 `caller_conflict`, B9 and AC-5 (a relayed grant needs a named person turn) | PRV §2.3, §2.4, §3 | yes | P1 | ✓ | 2026-11-20 |
| 6.5.2 | `engine/src/tempergraph/provenance.py` | `classify` (S2 to S6; S1 and S1s refused in release 1), `decide` with the person turns of the host session's journal, `may_widen` | PRV §2.3, §2.4, §2.8 | | P1 | ✓ | 2026-11-20 |
| 6.5.3 | `engine/src/tempergraph/cli/main.py`, `run/runner.py`, `run/rerun.py` | `--caller`, `--as-agent`, `--caller-app`, `--relayed` on `run`, `resume`, `rerun` and `stop`; the caller block on `run_started`, the human record and the intervention row; `relay_not_applicable`; widening needs `may_widen`; read-only verbs and `--check` never classify | PRV §2.2, §2.5, CLI §2.1 | | P1 | ✓ | 2026-11-20 |
| 6.5.4 | `engine/src/tempergraph/run/supervision.py`, `engine/tests/test_supervision.py` | The `supervision` record before every `run_exit` and on the `run_segment` ledger row: touches by class and decider, waits, latency, sessions, level and `level_by`; a rerun counts as a steer on its source; cost fields and `observations` null until T7.6 | SUP §2.2, §2.3, SUP-B1 to B3 | yes | P1 | ✓ | 2026-11-20 |
| 6.5.5 | — | P-SUP-1, P-SUP-2, P-SUP-4 on a signed-in Claude Code (PRV-AC-6); the journal itself is written by the SCO hooks (T7.6) | PRV-AC-6 | | P2 | ○ | |

## 3. Verification

From `plugins/tempergraph/engine/`: `python -m pytest`, `ruff check src tests` and `mypy` are clean. No test calls a model.
