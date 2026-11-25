---
goal: Build workflow packages and their registry, then first install, the stamp, scenarios and lint, audit, and the blueprint and scaffold
version: 1
date_created: 2026-11-20
last_updated: 2026-11-22
owner: dbr0vskyi
status: In progress
tags: [track-plan, tempergraph, T8]
tracker: none
spec: plugins/tempergraph/docs/specs/workflow-package.spec.md
spec_commit: 0a4f06b
task_id: first-release-t8
---

# T8 Packages, install, audit, scaffold

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T8 |
| Specs | [PKG](../specs/workflow-package.spec.md), [UPD](../specs/engine-update.spec.md), [VER](../specs/version-metadata.spec.md), [LIF](../specs/lifecycle-and-evals.spec.md), [AUD](../specs/workflow-audit.spec.md), [ARC](../specs/audit-rule-catalog.spec.md), [PRA](../specs/prompt-audit.spec.md), [SCF](../specs/blueprint-and-scaffold.spec.md) |

**Status: In progress.** T8.1 is built: a package on disk loads by every step of PKG-B15, PKG-B16, PKG-B17, step 5 through OUT's `read_outcome`, `gate_criteria` and `check_against` (plan T5.8.1), validates with the package rules, and registers, lists, unregisters and reinstalls through `tempergraph workflows`. T8.2 is built against a stand-in environment builder; a real `pip install` of the engine into a fresh environment waits on the owner's machine (it needs the package index). T8.3 is built, with the two calls in preflight and `executors` (8.3.5) added at the main build thread's request. T8.4 is built: prompt lint (LIF-B12), the structural readiness report (LIF-B13), and the stand-in scenario and diagram currency (LIF-B4, LIF-B3). T8.5 is built for the `definition` and `host` layers (R-150 AUD); the history layer and TSA moved to release 3. T8.6 has the blueprint check, draw and compare, the literal check, the scaffold and every rung of `author verify`; rungs 8 and 9, the trial report and the grades were built once T12.4 landed judge calibration.

Status pass: PKG, UPD, VER and WUP are `ready-for-implementation`, with release 1 defaults for their open questions. LIF, AUD, ARC, PRA and SCF get theirs in the first row of T8.4, T8.5 and T8.6.

Doc changes this track made:
- PKG-B15, PKG-B16, PKG-B17 step 3 says how the private import name works: relative imports inside the package, `own-module-absolute-import`, `undeclared-import` as a warning, a fresh import on every load, callables recorded under the private name.
- PKG-B18 defines the dependency gate, which SEC did not.
- PKG-B11, PKG-B13, PKG-B14, PKG-B17, PKG-B18, PKG-B19, PKG-B20, PKG-B23 adds the codes `pyproject-missing`, `pyproject-invalid`, `pyproject-name`, `outcome-missing`, `package-file-missing` (warning) and `manifest-field-unknown` (warning).
- PKG-B25 lists `issue_repository` (WFM requires it) and `author` and `license` (`claude plugin validate --strict` asks for `author`).
- UPD-B20 to UPD-B24 gives the `register` refusal codes, the scope of the live-thread check of `unregister`, and the release 1 `dependencies: pending` state.
- CHK-B16 says the check worker's context document carries the private-name map.
- UPD-B18, UPD-B19 gains a release 1 note: POSIX shim, the bootstrap import rule, the self-check module in place of `tempergraph --version --json` (the CLI has no `--version` flag yet), reconcile inside the new environment, no legacy manifest, `update` refused, the `PATH` files, and which cache folder reconcile takes.
- VER-B8 lists `loads_workflow_api_from` and says where `release.json` lives. SEC-B7 widens the Updater row.
- WUP-B10, WUP-B11, WUP-B12, WUP-B13 gains a release 1 note on the check and stamp. VER-B14, VER-B15 leaves `verified_engine` out of the content digest; VER-B16 adds `docs_digest` and `shape_digest` to the stamp; LIF-B7 to LIF-B16 says where the executor table lives.

Assumptions:
- A1. Missing required non-code files (README, docs, tests, diagram, the case set) warn rather than refuse, so a hand-written package can load while it is being finished. The scaffold writes them all.
- A2. `unregister` sees live threads in the current repository only, because the home keeps no index of repositories.
- A3. `release.json` `extras` is empty in release 1, since no extra executor ships (ADR-0091). `--with` is accepted and passed to pip, but nothing optional exists to install yet.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-33 | PKG | all | T8.1 |
| REQ-28 | UPD, VER | UPD AC-7, AC-8; VER AC-1, 2, 5, 6 | T8.1–T8.3 |
| REQ-7 | LIF | AC-2, 4, 6 | T8.4 |
| REQ-29 | AUD, ARC, PRA | AUD AC-2, 4–7 and AC-1 for definition and host rules; ARC same; PRA all | T8.5 |
| REQ-36 | SCF | all | T8.6 |

## 2. Phases

### T8.1 Packages and registry

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 8.1.1 | `engine/tests/test_package.py` | PKG-AC1 to AC-7, PKG-B2 to B7 and B9 on fixture packages; `claude plugin validate --strict` when `claude` is on `PATH` (model-free) | PKG-B1 to PKG-B10, PKG-AC1 | yes | P1 | ✓ | 2026-11-20 |
| 8.1.2 | `engine/src/tempergraph/package/manifest.py` | `read_manifest`, both manifests, `pyproject.toml`, the dependency gate | PKG-B13, PKG-B18 | | P1 | ✓ | 2026-11-20 |
| 8.1.3 | `engine/src/tempergraph/package/scan.py`, `importer.py` | The source scan before import; private import names with a meta-path finder; the map for the check worker | PKG-B15, PKG-B16, PKG-B17 step 3, CHK-B16 | | P1 | ✓ | 2026-11-20 |
| 8.1.4 | `engine/src/tempergraph/package/loader.py` | `load`, `load_package` (steps 1 to 4 and 6), interface levels, `package_findings` as the last step of WFM `validate` | PKG-B15, PKG-B16, PKG-B17 | | P1 | ✓ | 2026-11-20 |
| 8.1.5 | `engine/src/tempergraph/package/loader.py` | Step 5: attach `outcome.json` through OUT's `read_outcome` and `gate_criteria`, OUT-B22 unit rows by `check_against`; `criterion-declared-twice`; the package runs end to end through the outcome gate on stand-ins | PKG-B15, PKG-B16, PKG-B17 step 5, OUT-B13, OUT-B14 | yes | P1 | ✓ | 2026-11-20 |
| 8.1.6 | `engine/src/tempergraph/package/rules.py`, `docs_check.py` | Refused plugin parts, layout, `text-ref`, the docs check | PKG-B11, PKG-B12, PKG-B21, PKG-B22 | | P1 | ✓ | 2026-11-20 |
| 8.1.7 | `engine/src/tempergraph/package/inventory.py` | `package_files`, `content_digest`, `docs_digest`, `workflow_version` | VER-B14, VER-B15, PKG-AC7 | | P1 | ✓ | 2026-11-20 |
| 8.1.8 | `engine/src/tempergraph/package/registry.py`, `cli/workflows.py`, `engine/tests/test_registry.py` | `registry.json`; `workflows list\|register\|unregister\|reinstall`; `missing` and pin clearing; `version-not-bumped` | UPD-B20 to UPD-B24 | yes | P1 | ✓ | 2026-11-20 |
| 8.1.9 | `engine/src/tempergraph/package/registry.py` | Reconcile of `plugin` entries from Claude Code's plugin cache, run by `install` and `update` | UPD-B20 to UPD-B24, PKG-B1 | yes | P1 | ✓ | 2026-11-20 |
| 8.1.10 | `engine/src/tempergraph/package/loader.py`, `package/changelog.py` (`breaking_since_level`) | The compatibility warning `workflow_api_behind` for a package below the engine's level when the changelog has breaking `workflow` entries it has not met (PKG-B6 row 2) | PKG-B6, VER-B8, VER-B9 | yes | P2 | ✓ | 2026-11-20 |

Row 8.1.10 needs the changelog of T8.3.

### T8.2 First install

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 8.2.1 | `engine/tests/test_install.py` | Release record drift and version parity; the bootstrap import rule; first install, already current, a failed install changes nothing, `--check` read-only, no Python, `--add-to-path` once, `--repair`; the shim runs the current engine or exits 127; the launcher's verbs; reconcile registers, repoints, keeps `missing` | UPD-B11, UPD-B12, UPD-B13, UPD-B18, UPD-B19, UPD-B20 to UPD-B24; VER-B8 | yes | P1 | ✓ | 2026-11-20 |
| 8.2.2 | `engine/src/tempergraph/data/release.json`, `release.py` | The release record | VER-B8 | | P1 | ✓ | 2026-11-20 |
| 8.2.3 | `engine/src/tempergraph/install/` | `bootstrap`, `python` lookup, `environment` (folders, `.complete`, switch), `shim` and the `PATH` block, `selfcheck`, `reconcile`, the `launch` site | UPD-B11, UPD-B12, UPD-B13, UPD-B18, UPD-B19 | | P1 | ✓ | 2026-11-20 |
| 8.2.4 | `plugins/tempergraph/bin/tempergraph`, `engine/src/tempergraph/cli/install.py`, `__main__.py` | The plugin's launcher; `install` through the shim; `python -m tempergraph` | UPD-B18, UPD-B19 | | P1 | ✓ | 2026-11-20 |
| 8.2.5 | live, owner's machine | A real install from the plugin: venv, `pip install` of the staged engine, self-check, shim on `PATH`, `tempergraph executors --probe` | UPD-B18, UPD-B19 | | P1 | ○ | |

### T8.3 Stamp and compatibility

Status pass: WUP is `ready-for-implementation` (its open question has a release 1 default).

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 8.3.1 | `engine/tests/test_stamp.py` | VER-B2 table, B3, B4, B5; the shipped changelog validates and exists for the engine version; check read-only; stamp written on a clean check, refused (exit 4) on a validation error, refused on an installed copy; the compatibility table rows | VER-B1 to VER-B6, WUP-B10, WUP-B11, WUP-B12, WUP-B13, WUP-B19 | yes | P1 | ✓ | 2026-11-20 |
| 8.3.2 | `engine/src/tempergraph/package/changelog.py`, `data/changelog/0.0.1.json` | Entry schema check, range selection, detect rules (`field`, `symbol`, `finding`, `template_key`, `tool_ref`, `text`), the VER-B2, VER-B5 state; `compatibility` in `list` | VER-B9, VER-B2, VER-B5 | | P1 | ✓ | 2026-11-20 |
| 8.3.3 | `engine/src/tempergraph/package/stamp.py`, `cli/upgrade.py` | `upgrade --check [--stamp]`, `upgrade-check [--stamp]`; V1 to V7 with V4 and V6 skipped; `stamp.json`; `verified_engine` at load | WUP-B10, WUP-B11, WUP-B12, WUP-B13, WUP-B19, VER-B16 | | P1 | ✓ | 2026-11-20 |
| 8.3.4 | `engine/src/tempergraph/executor_compat.py`, `data/executor_compat.json` | The executor compatibility table, `row` and `finding` | LIF-B7 to LIF-B16 | | P1 | ✓ | 2026-11-20 |
| 8.3.5 | `executors/preflight.py`, `cli/main.py` (T6 owner) | Preflight warns `executor-version-untested`; `executors` shows the row (LIF-AC4); added on this branch at the main build thread's request | LIF-AC4 | yes | P1 | ✓ | 2026-11-20 |
| 8.3.6 | `engine/src/tempergraph/package/transforms.py` | The transforms of VER-B13 (VER-AC3) | VER-B13 | yes | P3 | ✓ | 2026-11-21, built in release 2 ([R2-T6](r2-t6-update-and-upgrade.plan.md) phase 3) |

### T8.4 Scenarios, lint and readiness

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 8.4.1 | `engine/tests/test_prompt_lint.py` | Each planted defect found once; clean fixtures raise nothing; skills and agents linted and resolved; the shared name reader | LIF-AC6, PRA-AC3 | yes | P1 | ✓ | 2026-11-20 |
| 8.4.2 | `engine/src/tempergraph/model/prompt_lint.py` | The rules of LIF-B12 as `validate` warnings | LIF-B12 | | P1 | ✓ | 2026-11-20 |
| 8.4.3 | `engine/src/tempergraph/package/readiness.py`, `engine/tests/test_readiness.py` | The structural judge readiness report; `gate-not-ready` in `stable` mode (LIF-B6); criteria lint joined in T9.2.1, scores join with T12 | LIF-B13, OUT-B11 | yes | P1 | ✓ | 2026-11-20 |
| 8.4.4 | `package/selftest.py` (`standin_run`), `tests/test_scaffold.py` | Deterministic scenarios on the scripted stand-ins (LIF-B4): the stand-in run plays `claude`, the reference; a step on a later release's executor is reported by name (LIF-B4, LIF-B3) | LIF-B7 to LIF-B16, LIF-B4, LIF-B3, EVS | yes | P1 | ✓ | 2026-11-20 |
| 8.4.5 | `package/selftest.py` (`diagram_current`), `tests/test_scaffold.py` | Package diagram currency: `diagram/model.json` digest against the spec; passes after CRLF, fails on a shape change (LIF-B3, LIF-AC2) | LIF-AC2 | yes | P2 | ✓ | 2026-11-20 |

### T8.5 Audit

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 8.5.0 | `docs/specs/workflow-audit.spec.md`, `audit-rule-catalog.spec.md`, `prompt-audit.spec.md` | Status pass: AUD, ARC and PRA `ready-for-implementation`, with the release 1 decisions in R-150 AUD, ARC-B6, ARC-B10, ARC-B16 and PRA-B7 to PRA-B11 | AUD, ARC, PRA | | P1 | ✓ | 2026-11-20 |
| 8.5.1 | `engine/tests/test_audit.py` | The catalog schema and owner source tests; each built rule raised by a fixture and quiet on a clean one; ARC-B2 table; PRA-B1, B2, B3; AUD-B1, B2, B4, B6 to B9; ignores; JSON, SARIF; refusals; V4 | AUD-AC1, ARC-AC1, PRA-AC1 | yes | P1 | ✓ | 2026-11-20 |
| 8.5.2 | `engine/src/tempergraph/audit/catalog.py` | The rule records and named parameters (ARC-B6, ARC-AC1 to AC-3) | ARC-B6 to ARC-B16 | | P1 | ✓ | 2026-11-20 |
| 8.5.3 | `audit/definition.py`, `audit/host.py`, `executors/launcher.py` (`shell_timing`) | The definition and host rules of ARC and PRA built in release 1 | ARC-B8, ARC-B9, ARC-B14, PRA-B7 to PRA-B10 | | P1 | ✓ | 2026-11-20 |
| 8.5.4 | `audit/report.py`, `audit/__init__.py`, `audit/prompts.py` | `AuditFinding`, `AuditReport`, order, the quiet view, ignores, summary, `--fail-on`, text, JSON and SARIF; owned checks rendered once; `audit prompts` rows | AUD-B12, AUD-B13, AUD-B14, AUD (moved), PRA-B11 | | P1 | ✓ | 2026-11-20 |
| 8.5.5 | `cli/audit.py`, `cli/main.py` (T6 owner) | `tempergraph audit` and `audit prompts`; `audit tools` and `--layer history` refused `not_in_release` | AUD-B11, AUD-B6, AUD-B9, AUD-B15, AUD-B2 | | P1 | ✓ | 2026-11-20 |
| 8.5.6 | `package/manifest.py`, `package/loader.py` | `audit.ignore` in `tempergraph.json`; `audit-ignore-invalid` | PKG-B13, AUD-AC7 | yes | P1 | ✓ | 2026-11-20 |
| 8.5.7 | `package/stamp.py` | V4 runs the definition layer against the last stamp's list | WUP-B19 | yes | P1 | ✓ | 2026-11-20 |
| 8.5.8 | `package/importer.py` | A package import writes no bytecode into the package (AUD-B6) | AUD-B6 | yes | P1 | ✓ | 2026-11-20 |
| 8.5.9 | | The history layer and its rules (X2-9), hot spots, ARC-B3 | AUD, ARC | yes | P2 | ○ | release 3 ([second-release plan §1.3](second-release.plan.md)) |
| 8.5.10 | | `audit tools` and TSA's rules (X2-10) | TSA | yes | P2 | ○ | release 3 ([second-release plan §1.3](second-release.plan.md)) |
| 8.5.11 | `run/outcome_trust.py`, `audit/definition.py` | OUT trust and coverage (computed, never stored) and the two outcome rules on them | ARC-B14, OUT-B13, OUT-B14 | yes | P1 | ✓ | 2026-11-20 |

### T8.6 Blueprint and scaffold

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 8.6.0 | `docs/specs/blueprint-and-scaffold.spec.md` | Status pass: SCF `ready-for-implementation`, release 1 decisions in SCF-B11, SCF-B13, SCF-B15, SCF-B16, SCF-B17, SCF-B18, SCF-B19, SCF-B20, SCF-B22 | SCF | | P1 | ✓ | 2026-11-20 |
| 8.6.1 | `engine/tests/test_blueprint.py` | SCF-B1, B2, B4, B5; the §4 blueprint rows; the outcome cross-check; draw formats; compare reports each compared field and none of the others; literals and a recorded hit | SCF-B9, SCF-B11, SCF-B13, SCF-AC1 | yes | P1 | ✓ | 2026-11-20 |
| 8.6.2 | `author/blueprint.py`, `author/draw.py`, `author/compare.py`, `author/literals.py`, `cli/author.py` | `blueprint check|draw|compare`, `literals` | SCF-B9, SCF-B11, SCF-B13 | | P1 | ✓ | 2026-11-20 |
| 8.6.3 | `author/scaffold.py`, `check_helpers.py` (`tempergraph.api.checks`), `package/selftest.py`, `executors/scripted.py`, `cli/author.py`, `tests/test_scaffold.py` | `scaffold` and `--update`, `--update-docs`, check helpers, the generated tests; SCF-B3, B7, AC-2, AC-4 | SCF-B14, SCF-B15, SCF-B16, SCF-B17 | yes | P1 | ✓ | 2026-11-20 |
| 8.6.4 | `author/verify.py`, `cli/author.py`, `tests/test_scaffold.py` | `author verify` rungs 1 to 7 and 10; SCF-B3 (rungs 1 to 7 pass with no edit), SCF-B4 at rung 2, SCF-AC5 for the model-free rungs | SCF-B18, SCF-B19, SCF-B20, SCF-B21, SCF-B22, SCF-B11, SCF-B13, SCF-B15, SCF-B16, SCF-B17 | yes | P1 | ✓ | 2026-11-20 |
| 8.6.5 | | Rungs 8 and 9: judge seeds and the consented, capped trial. Built after T12.4 (JCL's `judge_once`, FBK labels): `author/trial.py`, `author trial` and `author grade`, `tests/test_author_trial.py` (SCF-B6, B8, AC-5 to AC-7) | SCF-B18, SCF-B19, SCF-B20, SCF-B21, SCF-B22, SCF-B11, SCF-B13, SCF-B15, SCF-B16, SCF-B17 | yes | P1 | ✓ | 2026-11-20 |

## 3. Verification

From `plugins/tempergraph/engine/`: `python -m pytest`, `ruff check src tests` and `mypy` are clean. No test calls a model; the one test that runs `claude plugin validate` is model-free and skipped where `claude` is absent.
