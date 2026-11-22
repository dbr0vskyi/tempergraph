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

`reuse_key` hashes the command's argv and working folder, the resolved program, `HEAD`, the status listing and the content of changed and untracked files outside the state root (`checks.py` lines 132-146). Nothing in it names a unit, an attempt or a visit. A run is reused when the key matches and is stored only when it finished and its exit code is not listed as not reusable (`checks.py` lines 117-128). A finished failing run is stored too, so a failure on an unchanged tree is not run again either.

### F3 The code gate and the outcome gate ask for reuse over the same commands `confirmed`

`_verify` runs each command of the plan with `reuse=True` (`checks.py` line 580), and both `code_check` (line 633) and `outcome_check` (line 713) call it. The outcome gate therefore reuses the code gate's result when the tree did not change in between.

### F4 An attempt that changes nothing keeps its key, and one that changes a file gets a new key `confirmed`

The engine runs a step's `after` scripts only after a session that ended `ok` (SCR-B2; `nodes.py` lines 397-398), and the check runs after that. The commit script returns without committing when nothing is staged (`routing.py` lines 127-142), so a retry that changes nothing leaves `HEAD` and the status as they were and its key matches (CHK-B5 states this for a judge-only failure). A retry that edits a file is committed, `HEAD` moves, the key differs, and the commands run again, as they must.

### F5 Only the engine's own runs are recorded `confirmed`

The store is written only by `CheckContext.run` (`checks.py` line 128; no other writer in `plugins/tempergraph/engine/src`). A command the session runs in its own shell is not recorded, and the code step declares no check preview (`__init__.py` lines 123-131).

### F6 A check preview would not give the code gate a run to reuse `inferred`

A step that declares `self_check: true` gets a preview whose command runs are stored for reuse, and the gate reuses them on an unchanged tree (CHK-B17, CHK-AC6). On the code step the engine's commit comes between (F4): a session that changed files has them committed before the gate's check, so the gate sees a new `HEAD` and a clean status where the preview saw the old `HEAD` and a dirty one, and the keys differ. The sources state the stored runs, the order and the key's content; the consequence is reasoned from them.

### F7 Reuse is tested at the check-context level only `confirmed`

`test_command_runs_are_reused_while_the_tree_is_unchanged` builds two check contexts over one store, expects the second to reuse and a changed file to run again (`test_checks.py` lines 92-106). No test runs the code gate twice over one tree, in the package or in the engine (a search of both test folders for `reuse`, `reused` and `command_runs` finds that test, a docstring of the scrubber tests, and tests about pull requests, workspaces and the preview's state).

## Conclusions

1. The engine already reuses a verification result across a retry and across a later visit, and across the code gate and the outcome gate, whenever the tree did not change and the caller passes `reuse=True`, which the package does (F1, F2, F3, F4). Criterion 3 needs no engine change.
2. What is missing is a statement in temperspec's code spec, `ts-code-reuse`, and a test at the gate level that runs the code gate twice over one tree and shows the second run reused (F7).
3. The gate cannot reuse a result the session got by itself (F5, F6), so a clean visit still pays the suite twice: once in the session, once in the gate. The first gate run on a tree is not avoidable with the engine as it is.
4. A retry that edits a file runs the commands again, which is right (F4).

## Open questions

- Whether the session's own end-of-visit run should count as the gate's result. It would take two things: the session runs the plan's commands through the engine's preview, so that the run is recorded, and the reuse key holds the working tree's content instead of `HEAD` and the status listing, so that it survives the engine's commit. The second is an engine capability nobody has asked for. Until answered: the gate runs each command once per tree.
