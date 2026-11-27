# What would make the CI pipeline faster

## Problem statement

A CI run (`.github/workflows/ci.yml`: the offline suite, ruff and mypy on Python 3.11 and 3.12) takes about a quarter of an hour, and longer on the long-lived trunk branch. The owner asked whether it can be faster, for example by testing one Python version, and which other changes would shorten it. The unknown is where the time goes, so that a change to the pipeline or the suite ([TST](../specs/test-suite.spec.md)) targets the part that costs it.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| The CI workflow | code | `.github/workflows/ci.yml` |
| Package metadata and tool settings | code | `plugins/tempergraph/engine/pyproject.toml` |
| Default worker count of the suite | code | `plugins/tempergraph/engine/conftest.py` |
| The test that runs each workflow package's own tests | code | `plugins/tempergraph/engine/tests/test_workflow_packages.py` (`test_package_own_tests_pass`) |
| The 3.11 argparse workaround | code | `plugins/tempergraph/engine/src/tempergraph/cli/main.py` (`_parse`) |
| Every CI run of this repository, 2026-11-24 21:06Z to 2026-11-27 10:12Z: 180 runs, 358 jobs, their steps and the logs of every failed job | other (GitHub Actions API) | `GET /repos/dbr0vskyi/tempergraph/actions/runs`, `/runs/{id}/jobs`, `/jobs/{id}/logs` |
| The files of each run's head commit | other (GitHub API) | `GET /repos/dbr0vskyi/tempergraph/commits/{sha}` |
| Local runs of the suite on `main` at `4ab27784` (Python 3.12.3, 4 processors, like a standard GitHub runner): per-test durations (JUnit XML), and a per-worker timeline of start and end times | other (measurement) | this note's findings F3 to F5 |
| Local runs of the largest package's tests alone, serial and on 4 workers, on `main` and on `dbr0vskyi/trunk` at `ed8e9e83` | other (measurement) | finding F5 |
| GitHub-hosted runners for public repositories (4 processors, no charge for minutes) | docs | docs.github.com, "About GitHub-hosted runners" and "About billing for GitHub Actions" |

## Key findings

### F1 The suite is 97% of a job; setup, install, ruff and mypy are about 35 seconds `confirmed`

Median over the 186 successful jobs (3.11 / 3.12): job 945 s / 884 s; `python -m pytest` 916 s / 856 s; `pip install -e '.[dev]'` 11 s / 12 s (the pip cache of `setup-python` is already on); mypy 9 s / 10 s; checkout 2 s; setup-python 2 s; ruff under 1 s. The median successful run, from creation to its slower job's end, took 17.6 min (90th percentile 23.7 min, longest 27.6 min).

### F2 Runs do not wait for a runner, and the matrix jobs run side by side `confirmed`

Queue time (job created to job started) has a median of 2 s and a maximum of 28 s over all 358 jobs. The two matrix jobs start together, so a run lasts as long as its slower job, not the sum. The repository is public, and GitHub charges public repositories nothing for standard runner minutes.

### F3 One test is the critical path: the largest workflow package's own tests, run serially in one subprocess `confirmed`

`test_package_own_tests_pass` starts `python -m pytest -o addopts= <package>/tests` in a subprocess. That subprocess has no root conftest of the engine, so it runs on one process. For the largest package (704 tests) it took 525 s of the local suite's 887 s. The per-worker timeline of a local run on `main` (880 s wall):

| Worker | Tests | Busy | Last test ends |
|---|---|---|---|
| gw0 | 970 | 417 s | 422 s |
| gw1 | 710 | 383 s | 387 s |
| gw2 | 673 | 875 s | 880 s (the package test started at 373 s and ran 506 s) |
| gw3 | 947 | 383 s | 388 s |

Three workers are idle for the last eight minutes. The sum of all test time is about 2,060 s, so four evenly loaded workers need about 515 s.

### F4 The other slow tests are each under 80 seconds `confirmed`

The next slowest tests on `main`: `test_every_owner_criterion_of_the_contract_is_carried_by_a_test_that_runs` 69 s, `test_sch_ac2_five_thousand_random_rules_equal_dateutil_over_two_years` 56 s, `test_workers_and_one_process_pass_and_skip_the_same_tests` 49 s, two `test_sch_ac3_*` corpus tests 37 s and 28 s. 44 tests take 5 s or more (1,046 s together), 350 take 1 s or more (1,659 s). They sit on workers that end at about 400 s, so while F3 holds they add nothing to the wall time.

### F5 The package test grows faster than the rest, and trunk shows it `confirmed`

The largest package's tests alone: on `main` 524 s serial, 240 s on 4 workers (`-n 4`), all 704 passing; on `dbr0vskyi/trunk` 810 s serial (25 test files on `main`, 34 on trunk; the engine has 239 and 255). Trunk's CI suite took a median of 14.7 min on 2026-11-26 and 18.1 min on 2026-11-27 (longest 23.3 min). `ci.yml`, `conftest.py` and the test settings in `pyproject.toml` are the same on both branches; trunk differs from `main` only in `.github/labels.yml` and the pull request template under `.github/`.

### F6 The package's tests are safe on workers `supported`

The 704 tests passed on 4 workers (F5), and the engine suite already runs on 4 workers by default ([TST](../specs/test-suite.spec.md), `conftest.py`). One of the package's tests is timing-sensitive and failed once in CI (`test_never_more_than_three_reading_sessions_are_open_at_once`, F8), so running it beside more processes may make it fail more often.

### F7 Both Python versions are needed: the matrix caught one real 3.11-only defect `confirmed`

Six runs failed on one version only. Five were flaky tests (F8). One was real: on 3.11 `author start x --from sources templates` failed with `unrecognized arguments: templates` (run 45490936476, 2026-11-24), because 3.11's argparse fills a `*` positional at the first option. The fix is in `cli/main.py` `_parse`, whose docstring names the 3.11 behaviour. `requires-python = ">=3.11"`, mypy checks with `python_version = "3.11"` and ruff targets `py311`, so mypy and ruff give the same answer on both jobs. A mypy failure seen only on 3.12 (run 45555764773) came from a run whose 3.11 job was cancelled before reaching mypy.

### F8 Flaky tests caused most failed runs `confirmed`

Of 11 failed runs, 6 failed only on tests that passed on the other version or on the next push, with timing or folder-state assertions:

| Test | Failure |
|---|---|
| `test_schedule_cli.py::test_sch_ac6_every_refusal_exits_with_its_code_and_writes_nothing` (3 cases) and `test_settings.py::test_refused_setting_creates_nothing` | a `.git/objects/maintenance.lock/` appeared (before the CI step turned git maintenance off) |
| `test_contest_settings.py::test_without_flags_the_declared_values_stand_CTS_AC6` | `assert 2 == 3` on a peak count of parallel slots |
| `test_council_caps.py::test_bud_ac12_a_council_member_reserves_the_share_of_the_remaining_cap` | 1.966667 against 2.0 |
| `test_self_check.py::test_a_preview_writes_no_state_and_spends_no_budget` | `{'same': 'False'}` |
| the largest package's `test_parallel_reading.py::test_never_more_than_three_reading_sessions_are_open_at_once` | `assert 1 == 2` |

Each such failure costs a push and a full run (F1). No run was re-run by hand (`run_attempt` is 1 for all 180).

### F9 Cancelling superseded runs already works `confirmed`

`ci.yml` has `concurrency: ci-${{ github.ref }}` with `cancel-in-progress: true`. 82 of 180 runs (46%) were cancelled by a newer push, after a median of 2.5 min per job. 3 of 20 pushes to `main` were cancelled this way, so those `main` commits have no full result of their own.

### F10 A path filter would skip few runs safely `confirmed`

61 of 179 head commits changed only `.md` files, but 159 test files read documents (specs, rule files, READMEs, plans): a criterion id, a rule copy or a link checked by a test can break with a Markdown-only change. Only 3 head commits touched only paths no test reads (images, issue forms, labels), and even the monitor plugin's fixtures are read by an engine test (`test_detail.py`).

## Conclusions

Ranked by the wall time saved per run.

1. **Take the largest package's tests off the critical path** (F3, F5). Expected saving on `main` about 6 min of 15 (inferred: 2,060 s of test time over 4 workers is about 515 s, against 880 s), and more on trunk, where that one test is already 810 s and grows with the package. Three ways, simplest first:
   - a. Start that test first: order the long `test_package_own_tests_pass` cases to the front in `pytest_collection_modifyitems`, so it runs from second 0 beside the rest. It still bounds the run at its own length (525 s on `main`, 810 s on trunk), so it helps `main` now and trunk little. A trial that put the file first on the command line did not change the wall time (878 s), so the order has to be set in the hook and measured.
   - b. Run each package's own tests on workers inside the subprocess (`-n <workers>` when `pytest-xdist` is present). 240 s alone on 4 workers; beside the engine's 4 workers the processors are shared, so the expected wall is near the even split above. Risk: the timing-sensitive test of F6 under more load.
   - c. A second CI job for the package tests on workers, with the engine job skipping `test_package_own_tests_pass` when an environment variable is set (the test still runs locally, so the engine's guarantee that a change which breaks a package fails its suite holds). Expected: engine job about 390 s of tests, package job about 240 s, in parallel. It costs one more job and a setting the CI passes. The variable and the job name a step of the suite, not a workflow, so ADR `the-engine-names-no-workflow` holds.
2. **Fix the flaky tests of F8.** No time saved per run, but 6 of the 11 failed runs, each a full re-run of about 15 min, came from them.
3. **Move ruff and mypy to their own job on one version** (F1, F7). Saves about 10 s per matrix job; the larger gain is that a lint or type error shows in under a minute instead of after the suite.
4. **Keep both Python versions** (F2, F7). Testing one version saves no wall time (the jobs run side by side, queue time is seconds, minutes cost nothing on a public repository), and the 3.11 job caught a real defect. If runner minutes ever matter, keep 3.11 (the oldest declared version, where the defect was) on pull requests and both on `main`.
5. **Not worth doing now:** more dependency caching (install is 11 s with the pip cache on; a faster installer saves a few seconds), path filters (F10), cancelling more (F9 already does), and shortening the slow tests of F4 (they finish long before the package test; they matter only after conclusion 1, and then little).

## Open questions

- Whether conclusion 1a's ordering actually starts the test at second 0 under `pytest-xdist`'s load scheduling: the hook order has not been measured.
- The wall time of conclusion 1b with the engine's workers and the package's workers sharing 4 processors: not measured, only bounded (between about 515 s and 880 s).
- Whether `main` commits whose run was cancelled by the next merge (F9) need a full result of their own: a choice for the owner (`cancel-in-progress` could be limited to pull requests).
- The largest package's tests failed on trunk in a local run made with `main`'s installed engine environment; that run was used only for its time (810 s) and says nothing about trunk's correctness.
