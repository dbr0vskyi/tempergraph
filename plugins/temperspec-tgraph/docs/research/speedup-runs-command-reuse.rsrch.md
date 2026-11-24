# Does the engine already reuse a verification result across a retry and a later visit?

## Problem statement

Criterion 3 of the task `speedup-runs` wants the code gate to reuse a recorded verification result for an unchanged tree, in a retry and in a later visit of the code step. If the engine already does this, the change is a statement in the code spec and a test; if it does not, the missing case is an engine capability. The triage note could not tell (gap G5). The unknown is whether the engine's command reuse covers both cases, and what it leaves out.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Command runs, reuse by key, reuse after a judge-only failure, the check preview (CHK-B12, CHK-B13, CHK-B5, CHK-B17) | spec | `plugins/tempergraph/docs/specs/75-check-contract-and-command-runs.spec.md` |
| Order inside a hybrid step's attempt (SCR-B2) | spec | `plugins/tempergraph/docs/specs/70-script-units-and-hybrid-steps.spec.md` |
| The reuse store, the key and `run` | code | `plugins/tempergraph/engine/src/tempergraph/run/checks.py` lines 88-178 |
| Where the store lives, and the scripts that run after a session | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` lines 397-398 and 797-816 |
| The store path handed to the check's worker process | code | `plugins/tempergraph/engine/src/tempergraph/run/check_worker.py` lines 39 and 61 |
| The code gate's and the outcome gate's verification | code | `plugins/temperspec-tgraph/workflow/temperspec/checks.py` lines 575-587, 590-637 and 702-716 |
| The commit that follows each step | code | `plugins/temperspec-tgraph/workflow/temperspec/routing.py` lines 127-142 |
| The code step's declaration | code | `plugins/temperspec-tgraph/workflow/temperspec/__init__.py` lines 123-131 |
| Reuse tested at the check-context level | test | `plugins/tempergraph/engine/tests/test_checks.py` lines 92-106 |

## Key findings

### F1 One store of command runs serves a whole run `confirmed`

Every check context of a run is built with the same store file, `runs/<workflow>/<task id>/command_runs.jsonl` under the state root (`nodes.py` line 816), and the path travels to the worker process that runs the check (`check_worker.py` lines 39 and 61). `_stored` reads the latest row with the key and nothing prunes the file (`checks.py` lines 149-178). A check of any unit, attempt or visit of the same run reads and writes the same store. CHK-B13 says the same: an earlier run "in this thread".

### F2 The key names the tree, not the attempt or the visit `confirmed`

`reuse_key` hashes the command's argv and working folder, the resolved program and the content of the tree: every file git tracks and every untracked file git does not ignore (every file outside a git repository), outside the state root, each by path, bytes and executable bit, with no `HEAD` and no status listing (`checks.py`, issue 69; before it the key held `HEAD` and the status listing, which made a commit move it). Nothing in it names a unit, an attempt, a visit or a commit. A run is reused when the key matches and is stored only when it finished and its exit code is not listed as not reusable (`checks.py` lines 117-128). A finished failing run is stored too, so a failure on an unchanged tree is not run again either.

### F3 The code gate and the outcome gate ask for reuse over the same commands `confirmed`

`_verify` runs each command of the plan with `reuse=True` (`checks.py` line 580), and both `code_check` (line 633) and `outcome_check` (line 713) call it. The outcome gate therefore reuses the code gate's result when the tree did not change in between.

### F4 A commit leaves the key, and a changed file gets a new key `confirmed`

The engine runs a step's `after` scripts only after a session that ended `ok` (SCR-B2; `nodes.py` lines 397-398), and the check runs after that. The commit script returns without committing when nothing is staged (`routing.py` lines 127-142), so a retry that changes nothing leaves the tree as it was and its key matches (CHK-B5 states this for a judge-only failure). A retry that edits a file changes the tree's content, the key differs, and the commands run again, as they must. A commit of the same content leaves the key as it was, because the key holds no `HEAD` (CHK-B13, CHK-AC12; it held `HEAD` before issue 69, and then a commit moved it).

### F5 Only the engine's own runs are recorded `confirmed`

The store is written only by `CheckContext.run` (`checks.py`; no other writer in `plugins/tempergraph/engine/src`). A command the session runs in its own shell is not recorded. The code step now declares the check preview (`self_check=True`, `__init__.py`, issue 69), and a run the session makes through it is recorded.

### F6 A preview gives the code gate a run to reuse across the commit `confirmed`

A step that declares `self_check: true` gets a preview whose command runs are stored for reuse, and the gate reuses them on an unchanged tree (CHK-B17, CHK-AC6). On the code step a commit comes between (F4): the workflow's commit script, an `after` script of the step, commits the session's files before the gate's check. With the key as it was, the gate saw a new `HEAD` and a clean status where the preview saw the old `HEAD` and a dirty one, and the keys differed. With the key naming the tree's content they are equal when no file changed, and the gate takes the preview's run (CHK-AC12, proved offline in `tests/test_reuse_key_content.py`; the package's tests prove the same on the code gate). A file changed after the preview, or added, changes the key, and the gate runs the command again.

### F7 Reuse is tested at the check-context level only `confirmed`

`test_command_runs_are_reused_while_the_tree_is_unchanged` builds two check contexts over one store, expects the second to reuse and a changed file to run again (`test_checks.py` lines 92-106). No test runs the code gate twice over one tree, in the package or in the engine (a search of both test folders for `reuse`, `reused` and `command_runs` finds that test, a docstring of the scrubber tests, and tests about pull requests, workspaces and the preview's state).

## Conclusions

1. The engine already reuses a verification result across a retry and across a later visit, and across the code gate and the outcome gate, whenever the tree did not change and the caller passes `reuse=True`, which the package does (F1, F2, F3, F4). Criterion 3 needs no engine change.
2. What is missing is a statement in temperspec's code spec, `ts-code-reuse`, and a test at the gate level that runs the code gate twice over one tree and shows the second run reused (F7).
3. The gate cannot reuse a result the session got in its own shell (F5), but it reuses one the session got through the check preview, across the commit, as long as no file changed after that run (F6). A clean visit then pays the suite once, in the session's last run through the preview, and the gate takes it. The session must therefore make its run last, with the plan marked and the report written, and change no file after it; on an executor without the preview the old cost remains (the gate runs the suite again), never a wrong answer.
4. A retry that edits a file runs the commands again, which is right (F4).

## Open questions

- Answered by issue 69: the session's own end-of-visit run counts as the gate's result when it goes through the engine's preview and the tree's content is the same. The two things it took are built: the code step runs the plan's commands through the preview, and the reuse key holds the tree's content instead of `HEAD` and the status listing.
- Open: what the content key costs on a large repository. The key reads each file of the tree once on every command that asks for reuse; the code report of issue 69 says that the step had no way to time it, so the figure is still to be taken (a run's `command_runs.jsonl` and the check's duration show it in the first runs).
- Open: whether a real session's preview run is reused by the gate (the resolved program is part of the key and is found on the `PATH` of the process that runs the check). The `reused` or `run` word in the code gate's evidence shows it in the first runs.
