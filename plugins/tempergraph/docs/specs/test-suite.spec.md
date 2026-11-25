# Engine test suite

## Purpose

The engine's own tests, started with `python -m pytest` in the engine folder, are what every change to the engine must pass and what a gate runs again after each change, so the suite's wall time is paid by every run that edits the engine. By default the suite spreads its tests over a few worker processes, at most four; it runs in one process when asked or when the parallel runner is missing; it keeps each test to its own folders so that workers share no file; and the engine's `dev` extra installs the runner. Developers and every workflow that changes the engine depend on it. A suite result a gate already holds for the same tree is reused, not run again ([CHK-B13](check-contract-and-command-runs.spec.md)); a test session fails if any test leaves state in the real state root ([WSP-AC2](workspace-and-concurrency.spec.md)).

## Behaviours

### TST-B1 Parallel by default

WHEN a developer runs `python -m pytest` in the engine folder with no worker option THE suite SHALL spread its tests over one worker process per processor the machine offers, at most four.

- GIVEN a machine with eight processors WHEN the command runs THEN four workers run the tests and the summary counts every test once
- GIVEN a machine with two processors WHEN the command runs THEN two workers run the tests

### TST-B2 One process on request

WHEN a developer runs the command with `-n 0` THE suite SHALL run every test in the one process that pytest started.

- GIVEN `python -m pytest -n 0 -v` WHEN the suite runs THEN no test line carries a worker prefix and the summary counts the same tests as the default run

### TST-B3 One process when the runner is missing

WHEN `pytest-xdist` is not installed THE suite SHALL run every test in one process, with a line in its output that names the missing runner and the `dev` extra that installs it.

- GIVEN an environment without `pytest-xdist` WHEN `python -m pytest` runs THEN no test is stopped by an unknown option, the tests run in one process, and the output names `pytest-xdist` and the `dev` extra

### TST-B4 The same result however the tests are spread

WHEN the suite runs on workers THE suite SHALL pass and skip the same tests as a run in one process.

- GIVEN a tree on which `-n 0` passes WHEN the default run starts THEN it passes and skips the same live tests
- GIVEN any one test file WHEN it runs alone THEN every test of it passes

### TST-B5 Each test keeps to its own folders

WHEN a test runs on any worker THE suite SHALL give it a temporary folder, a home folder and a state root that no other test shares.

- GIVEN two tests running at the same time on two workers, each starting a run in its own state root WHEN both finish THEN each finds only its own run record
- GIVEN a full run WHEN it ends THEN no file of the repository outside cache folders, of the real home folder or of the real state root differs from before the run

### TST-B6 The runner comes with the dev extra

WHEN a developer installs the engine with its `dev` extra THE install SHALL provide `pytest-xdist` beside pytest.

- GIVEN `python -m pip install -e '.[dev]'` in the engine folder WHEN it ends THEN `python -m pytest` starts its workers with no further install

## Acceptance criteria

- TST-AC1 (TST-B1): `python -m pytest -v` with no worker option prints test lines from as many workers (`gw0`, `gw1`, …) as the machine has processors, and from no more than four
- TST-AC2 (TST-B2): `python -m pytest -n 0 -v` prints no worker prefix on any test line and counts the same tests as the default run
- TST-AC3 (TST-B3): `python -m pytest -p no:xdist --collect-only -q` is not stopped by an option error, and its output names `pytest-xdist` and the `dev` extra
- TST-AC4 (TST-B4): The full suite passes, with the same skipped tests, in one process and on workers
- TST-AC5 (TST-B4): Each test file passes when it runs alone. The test that proves it runs the suite again file by file, so it runs only with `TEMPERGRAPH_SUITE_AUDIT=1` and is skipped otherwise, as `live` tests are
- TST-AC6 (TST-B5): Two tests running at the same time on two workers get different temporary folders, home folders and state roots
- TST-AC7 (TST-B5): After a full run, no file of the repository outside cache folders, of the real home folder or of the real state root differs from before the run
- TST-AC8 (TST-B6): The engine's `dev` extra lists `pytest-xdist`
