# Engine test suite

## Purpose

The engine's own tests, started with `python -m pytest` in the engine folder, are what every change to the engine must pass and what a gate runs again after each change, so the suite's wall time is paid by every run that edits the engine. By default the suite spreads its tests over a few worker processes, at most four; it runs in one process when asked or when the parallel runner is missing; it keeps each test to its own folders so that workers share no file; it hides the sign-in of whoever started it from every test; and the engine's `dev` extra installs the runner. Developers and every workflow that changes the engine depend on it. Where the engine is installed, the tests of any package that imports the engine, and the code that runs outside the tests, start with a home folder of their own and the self-improvement loop off, wherever pytest starts; `-p no:tempergraph.pytest_plugin` switches that off. A suite result a gate already holds for the same tree is reused, not run again ([CHK-B13](check-contract-and-command-runs.spec.md)); a test session fails if any test leaves state in the real state root ([WSP-AC2](workspace-and-concurrency.spec.md)).

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

### TST-B7 A home folder of its own wherever a test starts

WHEN pytest runs a test that imports the engine, in an environment where the engine is installed, from whatever folder pytest was started in, THE engine SHALL start the test with a home folder that no other test uses and that is not the real home folder, with nothing written in the test's own package.

- GIVEN an environment where the engine is installed and a package folder holding one test that reads the engine's home folder, and no conftest WHEN `python -m pytest` starts in that folder THEN the test reads a temporary folder, not `~/.tempergraph/`
- GIVEN two tests of that folder WHEN each reads its home folder THEN the two folders differ
- GIVEN the same test WHEN `python -m pytest` starts in another folder and names the test's path THEN it reads a temporary folder there too

### TST-B8 The self-improvement loop is off wherever a test starts

WHEN pytest runs a test that imports the engine, in an environment where the engine is installed, from whatever folder pytest was started in, THE engine SHALL start the test with the self-improvement loop off ([SIL-B1](self-improvement.spec.md)), with nothing written in the test's own package.

- GIVEN an environment where the engine is installed and a package folder holding one test that imports the engine, and no conftest WHEN `python -m pytest` starts in that folder THEN the test finds `TEMPERGRAPH_LOOP` set to `off`
- GIVEN a test that sets `TEMPERGRAPH_LOOP` to `inline` itself WHEN a run ends in it THEN the loop runs in the test's process ([SIL-B1](self-improvement.spec.md))

### TST-B9 A home folder of its own for code outside the tests

WHEN pytest runs code that imports the engine outside any test (module code at import time, a fixture of session, module or class scope), in an environment where the engine is installed, from whatever folder pytest was started in, THE engine SHALL start that code with a home folder that no other pytest run and no test uses and that is not the real home folder, with nothing written in the package.

- GIVEN a package folder holding a test module that reads the engine's home folder at import time, and no conftest WHEN `python -m pytest` starts in that folder THEN it reads a temporary folder, not `~/.tempergraph/`
- GIVEN a session-scoped fixture that reads the engine's home folder WHEN the tests start THEN it has read a temporary folder, not `~/.tempergraph/`
- GIVEN code at import time that reads the engine's home folder and a test that reads its own WHEN pytest ends THEN the two folders differ

### TST-B10 The self-improvement loop is off for code outside the tests

WHEN pytest runs code that imports the engine outside any test (module code at import time, a fixture of session, module or class scope), in an environment where the engine is installed, from whatever folder pytest was started in, THE engine SHALL start that code with the self-improvement loop off ([SIL-B1](self-improvement.spec.md)), with nothing written in the package.

- GIVEN a package folder holding a test module that reads `TEMPERGRAPH_LOOP` at import time, and no conftest WHEN `python -m pytest` starts in that folder THEN it finds `off`
- GIVEN a session-scoped fixture that reads `TEMPERGRAPH_LOOP` WHEN the tests start THEN it has found `off`

### TST-B11 The isolation is switched off by blocking its plugin

WHEN pytest is started with `-p no:tempergraph.pytest_plugin` THE engine SHALL apply none of the isolation of TST-B7, TST-B8, TST-B9 and TST-B10.

- GIVEN an environment where the engine is installed and a package folder holding one test that reads the engine's home folder, and no conftest, with `TEMPERGRAPH_HOME` unset WHEN `python -m pytest -p no:tempergraph.pytest_plugin` starts in that folder THEN the test reads `~/.tempergraph/`
- GIVEN the same folder with `TEMPERGRAPH_LOOP` unset WHEN the same command runs THEN the test finds `TEMPERGRAPH_LOOP` unset
- GIVEN the same environment and folder WHEN `python -m pytest` starts with no option THEN the test reads a temporary folder

### TST-B12 The suite tests the checkout it runs from

WHEN a developer runs the suite in the engine folder of a checkout THE suite SHALL test the engine code of that checkout, in one process and on workers, whatever other copy of the engine the environment has installed.

- GIVEN an environment where another copy of the engine is installed WHEN `python -m pytest -n 0` runs in the engine folder of this checkout THEN every test imports the engine from this checkout
- GIVEN the same environment WHEN `python -m pytest` runs on workers THEN every test imports the engine from this checkout

### TST-B13 The caller's sign-in is out of sight

WHEN a test of the suite runs THE suite SHALL give it a user home folder that is a temporary folder and an environment with no credential variable of the caller and no variable that moves the sign-in folder, so that a test that needs a sign-in creates it. A `live` test keeps the caller's home folder and credentials: it runs the signed-in `claude`.

- GIVEN a caller whose home folder holds a cached sign-in file of an executor WHEN a test asks the credential check which kinds that executor holds THEN it finds none
- GIVEN a caller whose environment sets `CLAUDE_CODE_OAUTH_TOKEN`, an API key name or `CLAUDE_CONFIG_DIR` WHEN a test reads its environment THEN none of the names is set
- GIVEN a test that writes a sign-in file under its own home folder WHEN it asks the credential check THEN the check finds that sign-in

## Acceptance criteria

- TST-AC1 (TST-B1): `python -m pytest -v` with no worker option prints test lines from as many workers (`gw0`, `gw1`, …) as the machine has processors, and from no more than four
- TST-AC2 (TST-B2): `python -m pytest -n 0 -v` prints no worker prefix on any test line and counts the same tests as the default run
- TST-AC3 (TST-B3): `python -m pytest -p no:xdist --collect-only -q` is not stopped by an option error, and its output names `pytest-xdist` and the `dev` extra
- TST-AC4 (TST-B4): The full suite passes, with the same skipped tests, in one process and on workers
- TST-AC5 (TST-B4): Each test file passes when it runs alone. The test that proves it runs the suite again file by file, so it runs only with `TEMPERGRAPH_SUITE_AUDIT=1` and is skipped otherwise, as `live` tests are
- TST-AC6 (TST-B5): Two tests running at the same time on two workers get different temporary folders, home folders and state roots
- TST-AC7 (TST-B5): After a full run, no file of the repository outside cache folders, of the real home folder or of the real state root differs from before the run
- TST-AC8 (TST-B6): The engine's `dev` extra lists `pytest-xdist`
- TST-AC9 (TST-B7): In a package folder with no conftest, two tests started by `python -m pytest` in that folder read two different temporary home folders, and neither is the real home folder
- TST-AC10 (TST-B8): In the same folder, a test finds `TEMPERGRAPH_LOOP` set to `off`
- TST-AC11 (TST-B7): After the tests of that folder have run, no file of the real home folder, the machine index included, differs from before the run
- TST-AC12 (TST-B9): In a package folder with no conftest, module code at import time and a fixture of each scope (session, module, class) each read a temporary folder as the engine's home folder, not the real home folder, and a test of that folder reads a different one
- TST-AC13 (TST-B9): Two pytest runs of that folder started at the same time read two different home folders in module code at import time
- TST-AC14 (TST-B10): In the same folder, module code at import time and a fixture of each scope (session, module, class) each find `TEMPERGRAPH_LOOP` set to `off`
- TST-AC15 (TST-B7, TST-B8): In an environment where the engine is installed, `python -m pytest` with no option, started in a package folder with no conftest, gives a test a temporary home folder and `TEMPERGRAPH_LOOP` set to `off`
- TST-AC16 (TST-B11): With `-p no:tempergraph.pytest_plugin` and neither `TEMPERGRAPH_HOME` nor `TEMPERGRAPH_LOOP` set, a test of that folder reads `~/.tempergraph/` and finds `TEMPERGRAPH_LOOP` unset
- TST-AC17 (TST-B12): In an environment where another copy of the engine is installed, `python -m pytest -n 0` in the engine folder of a checkout makes every test import the engine from that checkout
- TST-AC18 (TST-B12): In the same environment, the default run on workers makes every test import the engine from that checkout
- TST-AC19 (TST-B13): In a suite run whose caller has a cached sign-in file for each executor that keeps one, a config folder with one more and every credential variable set, a test finds a temporary user home folder, none of those variables, and no credential kind held for any executor; a test that writes a sign-in file under its own home folder finds it
