---
goal: Build workflow packages and their registry, then first install, the stamp, scenarios and lint, audit, and the blueprint and scaffold
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: In progress
tags: [track-plan, tempergraph, T8]
tracker: none
spec: plugins/tempergraph/docs/specs/88-workflow-package.spec.md
spec_commit: 0a4f06b
task_id: first-release-t8
---

# T8 Packages, install, audit, scaffold

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T8 |
| Specs | [PKG](../specs/88-workflow-package.spec.md), [UPD](../specs/60-engine-update.spec.md), [VER](../specs/61-version-metadata.spec.md), [LIF](../specs/18-lifecycle-and-evals.spec.md), [AUD](../specs/55-workflow-audit.spec.md), [ARC](../specs/56-audit-rule-catalog.spec.md), [PRA](../specs/58-prompt-audit.spec.md), [SCF](../specs/91-blueprint-and-scaffold.spec.md) |

**Status: In progress.** T8.1 is built: a package on disk loads by every step of PKG §2.3, step 5 through OUT's `read_outcome`, `gate_criteria` and `check_against` (plan T5.8.1), validates with the package rules, and registers, lists, unregisters and reinstalls through `tempergraph workflows`. T8.2 is built against a stand-in environment builder; a real `pip install` of the engine into a fresh environment waits on the owner's machine (it needs the package index). T8.3 is built, with the two calls in preflight and `executors` (8.3.5) added at the main build thread's request. T8.4 has prompt lint (LIF §2.1) and the structural readiness report (LIF §2.2). T8.5 is built for the `definition` and `host` layers (AUD §2.5); the history layer and TSA are release 2. The rest of T8.4 and T8.6 are not started.

Status pass: PKG, UPD, VER and WUP are `ready-for-implementation`, with release 1 defaults for their open questions. LIF, AUD, ARC, PRA and SCF get theirs in the first row of T8.4, T8.5 and T8.6.

Doc changes this track made:
- PKG §2.3 step 3 says how the private import name works: relative imports inside the package, `own-module-absolute-import`, `undeclared-import` as a warning, a fresh import on every load, callables recorded under the private name.
- PKG §2.3.1 defines the dependency gate, which SEC did not.
- PKG §4 adds the codes `pyproject-missing`, `pyproject-invalid`, `pyproject-name`, `outcome-missing`, `package-file-missing` (warning) and `manifest-field-unknown` (warning).
- PKG §2.7 lists `issue_repository` (WFM requires it) and `author` and `license` (`claude plugin validate --strict` asks for `author`).
- UPD §2.8 gives the `register` refusal codes, the scope of the live-thread check of `unregister`, and the release 1 `dependencies: pending` state.
- CHK §2.6 says the check worker's context document carries the private-name map.
- UPD §2.7 gains a release 1 note: POSIX shim, the bootstrap import rule, the self-check module in place of `tempergraph --version --json` (the CLI has no `--version` flag yet), reconcile inside the new environment, no legacy manifest, `update` refused, the `PATH` files, and which cache folder reconcile takes.
- VER §2.2 lists `loads_workflow_api_from` and says where `release.json` lives. SEC §2.2 widens the Updater row.
- WUP §2.1 gains a release 1 note on the check and stamp. VER §2.4 leaves `verified_engine` out of the content digest; VER §2.5 adds `docs_digest` and `shape_digest` to the stamp; LIF §2 says where the executor table lives.

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
| 8.1.1 | `engine/tests/test_package.py` | PKG-AC-1 to AC-7, PKG-B2 to B7 and B9 on fixture packages; `claude plugin validate --strict` when `claude` is on `PATH` (model-free) | PKG §3, §6 | yes | P1 | ✓ | 2026-11-20 |
| 8.1.2 | `engine/src/tempergraph/package/manifest.py` | `read_manifest`, both manifests, `pyproject.toml`, the dependency gate | PKG §2.2, §2.3.1 | | P1 | ✓ | 2026-11-20 |
| 8.1.3 | `engine/src/tempergraph/package/scan.py`, `importer.py` | The source scan before import; private import names with a meta-path finder; the map for the check worker | PKG §2.3 step 3, CHK §2.6 | | P1 | ✓ | 2026-11-20 |
| 8.1.4 | `engine/src/tempergraph/package/loader.py` | `load`, `load_package` (steps 1 to 4 and 6), interface levels, `package_findings` as the last step of WFM `validate` | PKG §2.3 | | P1 | ✓ | 2026-11-20 |
| 8.1.5 | `engine/src/tempergraph/package/loader.py` | Step 5: attach `outcome.json` through OUT's `read_outcome` and `gate_criteria`, OUT §4 unit rows by `check_against`; `criterion-declared-twice`; the package runs end to end through the outcome gate on stand-ins | PKG §2.3 step 5, OUT §2.3 | yes | P1 | ✓ | 2026-11-20 |
| 8.1.6 | `engine/src/tempergraph/package/rules.py`, `docs_check.py` | Refused plugin parts, layout, `text-ref`, the docs check | PKG §2.1, §2.5 | | P1 | ✓ | 2026-11-20 |
| 8.1.7 | `engine/src/tempergraph/package/inventory.py` | `package_files`, `content_digest`, `docs_digest`, `workflow_version` | VER §2.4, PKG-AC-7 | | P1 | ✓ | 2026-11-20 |
| 8.1.8 | `engine/src/tempergraph/package/registry.py`, `cli/workflows.py`, `engine/tests/test_registry.py` | `registry.json`; `workflows list\|register\|unregister\|reinstall`; `missing` and pin clearing; `version-not-bumped` | UPD §2.8 | yes | P1 | ✓ | 2026-11-20 |
| 8.1.9 | `engine/src/tempergraph/package/registry.py` | Reconcile of `plugin` entries from Claude Code's plugin cache, run by `install` and `update` | UPD §2.8, PKG-B1 | yes | P1 | ✓ | 2026-11-20 |
| 8.1.10 | `engine/src/tempergraph/package/loader.py` | The compatibility warning for a package one level behind when the changelog has breaking `workflow` entries (PKG-B6 row 2) | PKG-B6, VER §2.3 | yes | P2 | ○ | |

Row 8.1.10 needs the changelog of T8.3.

### T8.2 First install

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 8.2.1 | `engine/tests/test_install.py` | Release record drift and version parity; the bootstrap import rule; first install, already current, a failed install changes nothing, `--check` read-only, no Python, `--add-to-path` once, `--repair`; the shim runs the current engine or exits 127; the launcher's verbs; reconcile registers, repoints, keeps `missing` | UPD §2.2, §2.7, §2.8; VER §2.2 | yes | P1 | ✓ | 2026-11-20 |
| 8.2.2 | `engine/src/tempergraph/data/release.json`, `release.py` | The release record | VER §2.2 | | P1 | ✓ | 2026-11-20 |
| 8.2.3 | `engine/src/tempergraph/install/` | `bootstrap`, `python` lookup, `environment` (folders, `.complete`, switch), `shim` and the `PATH` block, `selfcheck`, `reconcile`, the `launch` site | UPD §2.2, §2.7 | | P1 | ✓ | 2026-11-20 |
| 8.2.4 | `plugins/tempergraph/bin/tempergraph`, `engine/src/tempergraph/cli/install.py`, `__main__.py` | The plugin's launcher; `install` through the shim; `python -m tempergraph` | UPD §2.7 | | P1 | ✓ | 2026-11-20 |
| 8.2.5 | live, owner's machine | A real install from the plugin: venv, `pip install` of the staged engine, self-check, shim on `PATH`, `tempergraph executors --probe` | UPD §2.7 | | P1 | ○ | |

### T8.3 Stamp and compatibility

Status pass: WUP is `ready-for-implementation` (its open question has a release 1 default).

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 8.3.1 | `engine/tests/test_stamp.py` | VER-B2 table, B3, B4, B5; the shipped changelog validates and exists for the engine version; check read-only; stamp written on a clean check, refused (exit 4) on a validation error, refused on an installed copy; the compatibility table rows | VER §3, WUP §2.1, §2.6 | yes | P1 | ✓ | 2026-11-20 |
| 8.3.2 | `engine/src/tempergraph/package/changelog.py`, `data/changelog/0.0.1.json` | Entry schema check, range selection, detect rules (`field`, `symbol`, `finding`, `template_key`, `tool_ref`, `text`), the VER §2.7 state; `compatibility` in `list` | VER §2.3, §2.7 | | P1 | ✓ | 2026-11-20 |
| 8.3.3 | `engine/src/tempergraph/package/stamp.py`, `cli/upgrade.py` | `upgrade --check [--stamp]`, `upgrade-check [--stamp]`; V1 to V7 with V4 and V6 skipped; `stamp.json`; `verified_engine` at load | WUP §2.1, §2.6, VER §2.5 | | P1 | ✓ | 2026-11-20 |
| 8.3.4 | `engine/src/tempergraph/executor_compat.py`, `data/executor_compat.json` | The executor compatibility table, `row` and `finding` | LIF §2 | | P1 | ✓ | 2026-11-20 |
| 8.3.5 | `executors/preflight.py`, `cli/main.py` (T6 owner) | Preflight warns `executor-version-untested`; `executors` shows the row (LIF-AC-4); added on this branch at the main build thread's request | LIF-AC-4 | yes | P1 | ✓ | 2026-11-20 |
| 8.3.6 | | The transforms of VER §2.3.4 (VER-AC-3) | VER §2.3.4 | yes | P3 | ○ | release 3, with phase 4 of WUP |

### T8.4 Scenarios, lint and readiness

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 8.4.1 | `engine/tests/test_prompt_lint.py` | Each planted defect found once; clean fixtures raise nothing; skills and agents linted and resolved; the shared name reader | LIF-AC-6, PRA-AC-3 | yes | P1 | ✓ | 2026-11-20 |
| 8.4.2 | `engine/src/tempergraph/model/prompt_lint.py` | The rules of LIF §2.1 as `validate` warnings | LIF §2.1 | | P1 | ✓ | 2026-11-20 |
| 8.4.3 | `engine/src/tempergraph/package/readiness.py`, `engine/tests/test_readiness.py` | The structural judge readiness report; `gate-not-ready` in `stable` mode (LIF-B6); criteria lint joins with T9.2, scores with T12 | LIF §2.2, OUT §2.2.1 | yes | P1 | ✓ | 2026-11-20 |
| 8.4.4 | | Deterministic scenarios on the scripted stand-ins (LIF-B4) | LIF §2, EVS | yes | P1 | ○ | |
| 8.4.5 | | Package diagram currency: `diagram/model.json` digest against the spec (LIF-AC-2) | LIF-AC-2 | yes | P2 | ○ | |

### T8.5 Audit

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 8.5.0 | `docs/specs/55-*`, `56-*`, `58-*` | Status pass: AUD, ARC and PRA `ready-for-implementation`, with the release 1 decisions in AUD §2.5, ARC §2.10 and PRA §2.5 | AUD, ARC, PRA | | P1 | ✓ | 2026-11-20 |
| 8.5.1 | `engine/tests/test_audit.py` | The catalog schema and owner source tests; each built rule raised by a fixture and quiet on a clean one; ARC-B2 table; PRA-B1, B2, B3; AUD-B1, B2, B4, B6 to B9; ignores; JSON, SARIF; refusals; V4 | AUD §6, ARC §6, PRA §6 | yes | P1 | ✓ | 2026-11-20 |
| 8.5.2 | `engine/src/tempergraph/audit/catalog.py` | The rule records and named parameters (ARC §2.1, ARC-AC-1 to AC-3) | ARC §2 | | P1 | ✓ | 2026-11-20 |
| 8.5.3 | `audit/definition.py`, `audit/host.py`, `executors/launcher.py` (`shell_timing`) | The definition and host rules of ARC and PRA built in release 1 | ARC §2.3 to §2.8, PRA §2.3 | | P1 | ✓ | 2026-11-20 |
| 8.5.4 | `audit/report.py`, `audit/__init__.py`, `audit/prompts.py` | `AuditFinding`, `AuditReport`, order, the quiet view, ignores, summary, `--fail-on`, text, JSON and SARIF; owned checks rendered once; `audit prompts` rows | AUD §2.2 to §2.4, CON §2.11, PRA §2.4 | | P1 | ✓ | 2026-11-20 |
| 8.5.5 | `cli/audit.py`, `cli/main.py` (T6 owner) | `tempergraph audit` and `audit prompts`; `audit tools` and `--layer history` refused `not_in_release` | AUD §2.1, §4 | | P1 | ✓ | 2026-11-20 |
| 8.5.6 | `package/manifest.py`, `package/loader.py` | `audit.ignore` in `tempergraph.json`; `audit-ignore-invalid` | PKG §2.2, AUD-AC-7 | yes | P1 | ✓ | 2026-11-20 |
| 8.5.7 | `package/stamp.py` | V4 runs the definition layer against the last stamp's list | WUP §2.6 | yes | P1 | ✓ | 2026-11-20 |
| 8.5.8 | `package/importer.py` | A package import writes no bytecode into the package (AUD-B6) | AUD-B6 | yes | P1 | ✓ | 2026-11-20 |
| 8.5.9 | | The history layer and its rules (X2-9), hot spots, ARC-B3 | AUD, ARC | yes | P2 | ○ | release 2 |
| 8.5.10 | | `audit tools` and TSA's rules (X2-10) | TSA | yes | P2 | ○ | release 2 |
| 8.5.11 | | `outcome-unverified-blocker`, `outcome-uncovered` once OUT trust and coverage exist | ARC §2.8, OUT §2.3 | yes | P1 | ○ | after plan T5.8.1 |

### T8.6 Blueprint and scaffold

Not started.

## 3. Verification

From `plugins/tempergraph/engine/`: `python -m pytest`, `ruff check src tests` and `mypy` are clean. No test calls a model; the one test that runs `claude plugin validate` is model-free and skipped where `claude` is absent.
