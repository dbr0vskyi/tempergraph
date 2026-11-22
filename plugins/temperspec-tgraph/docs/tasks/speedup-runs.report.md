# Code report: speedup-runs

Plan: `plugins/temperspec-tgraph/docs/plans/speedup-runs.plan.md`. Status left `in-progress`: rows are unmarked (see below).

## Verification, as seen

| Command | Result |
|---|---|
| `cd plugins/tempergraph/engine && python3 -m pytest` | 1422 passed, 12 skipped in 370.92 s (0:06:10) on the default workers; exit 0. The 12 skips are the `live` checks. |
| `cd plugins/tempergraph/engine && ruff check src tests` | All checks passed. |
| `cd plugins/tempergraph/engine && mypy` | **1 error**: `src/tempergraph/improve/harvest.py:37: Need type annotation for "ws" [var-annotated]`. That file is not changed by this run (`git status` lists no change to it), so the error was there before. No file this run changed has a mypy error. Not fixed: the file is not named by a row. |
| `cd plugins/temperspec-tgraph && python3 -m pytest tests` | The last run, made with `-p no:cacheprovider -o addopts= -q` after `outcome.json` was finished: 63 passed in 5.35 s. |

Wall time of the engine suite (row 6.5 asks for serial and parallel):

- Default workers: 370.92 s, measured on this machine. The processor count was not recorded (workers are capped at four).
- One process (`-n 0`): **not measured in this session.** The only serial figure is from the earlier review of main on this machine: 553 s serial against 189 s with `-n auto`. That figure is not mine and is for a tree without this run's new tests. The new `test_suite_same_result.py` runs every other test file alone (about 212 s with four at a time), which is why the default run here is slower than 189 s.

## Deviations

1. **Rows 1.9, 1.10, 1.11 (path-length fixes): nothing changed.** No test failed only under workers: the full default run passed, and every test file passes alone with `-n 0` (TST-AC5 test). I found no assertion that depends on a scratch path length in the three files. These rows are unmarked because no file changed.
2. **Row 1.7 not marked.** `tests/conftest.py` changed: the session-level guard is there (runs once on the controller, skipped on workers by `PYTEST_XDIST_WORKER`, fails the session when a tracked file, the real `.tempergraph` or the real state root changed), and the unused `real_state_root_guard` fixture was removed. The part of the row that points `TEMPERGRAPH_STATE_ROOT` at a per-test folder was **not** done: `_isolated_home` is unchanged. TST-AC6 (distinct tmp, home and state folders per test) passes without it. Extra helper code for the nested runs (`nested_pytest`, snapshots, counts) lives in this file too, which the row does not describe.
3. **Row 3.4 not marked.** The fixture `evals/checks/discovery/must-pass/1-no-document/docs/specs/config-file.spec.md` exists, but it is in the earlier spec layout and not "the same spec as in `2-new-spec`". With a normal-layout spec the stand-in run copied it as a new spec and the outcome gate failed (`ts-traced`: criteria named by no test). Plan at fault for row 3.4: the fixture cannot be the same spec as `2-new-spec` and still leave the stand-in run alone.
4. **`-vv` in the runner tests.** `-q` is in `addopts`; `-v` gives verbosity 0, so the tests that look for worker prefixes use `-vv`. The plan says `-n 0 -v`.
5. **Extra files / values the rows do not name:** the triage unit's `produces` gained `covered` (optional, choices `no`, `yes`) in `workflow/temperspec/__init__.py` and `blueprint.json`; both are needed for the `covered` value of rows 2.7 and 2.8 to exist. `Triage.covered_claimed` was added beside `covered` and `covered_rows`.
6. **Phase 4 (rows 4.1 to 4.8) not built. Plan at fault.** A second step `discovery_short` (row 4.5) cannot be added by the files the rows name:
   - the engine's generated stand-in run answers each unit from a FIFO of replies and needs every unit of `order` visited; a unit that the route skips breaks `standin_run` (engine change needed, and the engine may not name the workflow);
   - `docs_check` needs a `NN-discovery_short.spec.md` and an `outcome.json` intermediate entry with its own criterion ids for the new step, and the eval fixtures under `evals/checks/discovery_short`; none is a row;
   - the diagram digest (`diagram/`) and `stamp.json` change with the unit shape; both are written only by `tempergraph author verify` / `upgrade-check --stamp`, which I may not run.
   So `ts-dis-short` and `ts-dis-full` in `outcome.json` and the spec describe a visit that does not exist yet. Their judges would score a run on a claim the workflow does not meet.
7. **Row 6.1 not done.** Its assertions on `ts-dis-short`, `ts-dis-full` and on B21 depend on Phase 4 and row 6.4.
8. **Row 6.3 not done (BLOCKED).** `stamp.json` and the diagram can be written only by `tempergraph author verify plugins/temperspec-tgraph`, which is outside the commands I may run. No audit line was written by hand, so none is quoted. Someone must run it after Phase 4 exists.
9. **Row 6.4 not done.** Backlog row B21 stays until the short visit exists.
10. **Row 6.5:** this report.
11. **Test-first order was not strictly kept.** Some code and tests were written in the same stretch, and I did not run a red state before the green one for row 1.1 and for the package tests. The tests do fail without their code (for example `test_generated[docs]` failed until `outcome.json` carried the new criteria, and the `COVERED` pattern matched `CFG-AC1x` until a test caught it).
12. `CLAUDE.md` is the only document with a changed test line. `README.md` and `getting-started.guide.md` already say `python -m pytest` and stay true.

## Rows marked

1.1 to 1.6, 1.8, 2.1 to 2.9, 3.1 to 3.3, 3.5 to 3.17, 5.1 to 5.3, 6.2, 6.5.

## Rows not marked

1.7 (partial, item 2), 1.9 to 1.11 (nothing to change, item 1), 3.4 (item 3), 4.1 to 4.8 (item 6), 6.1 (item 7), 6.3 (item 8), 6.4 (item 9).

## Plan defects

- Phase 4: see item 6. The plan chose a second step without checking the engine's stand-in run, the docs self-test and the stamp.
- Row 3.4: see item 3.
- Verification command `mypy` fails on a file this task does not touch.
