# What the runs of this batch showed (temporary; becomes issues before the folder is deleted)

One entry per thing seen, with the run or command that showed it. An entry that deserves work becomes a GitHub issue and gets the number here.

## Setting up on the owner's machine (2026-11-25)

- **The run recipe is not where the guide says.** `CONTRIBUTING.md` section 4 says the recipe (worktree mode, separate virtual environments, rules installed globally) is in `plugins/temperspec-tgraph/README.md`; the README holds no such section. The working recipe is now in `QUEUE.md` of this folder.
- **`claude` 2.1.332 is outside the tested range.** `tempergraph executors --probe` reports `compat.state: outside` for range `>=2.1.329,<=2.1.329`. The install went on and said `claude: ok`.
- **`--worktree-base` takes no branch name.** `--worktree-base claude/issue-queue-2026-11-25` is refused: `worktree.base ... is not head, default_branch or ref:<name>`. The refusal is clear; `run --help` gives the option no help text.
- **`run --check` prints about 40 warnings on every call** (`criterion-overlap`, `template-key-not-on-every-path`), also when the status is `ok`. A caller has to read past them each time; they are authoring findings, not run findings.
- **One environment serves every worktree.** `tests/conftest.py` puts the `src` beside it first on the path, so the suite of a worktree tests that worktree's engine with one shared environment that holds only the dependencies. Earlier notes asked for a separate environment for each run.
- **The monitor shows no run when the engine is installed without the `PATH` change.** The mod runs `tempergraph status` from `PATH` unless its `engine_path` option is set, and an install that leaves `PATH` alone puts the shim only at `~/.tempergraph/bin/tempergraph`; a session that was open before the install has the old `PATH` in any case. The pane then says the engine is not installed while two runs are live. A fallback to the default shim path in the mod, or the install writing `engine_path`, would close it.

## Runs

### i71, first start (2026-11-25)

- **Every run paused at `prepare` on Apple's git 2.39.5** (#139, fixed by hand on the batch branch, since no run could start without it). `git add -A -- . ":(exclude).tempergraph"` exits 1 there when `.tempergraph/` is ignored. The engine's checkpoint commit had the same words. The suite could not have caught it: CI and the cloud container run a newer git.
- **A script unit's exception leaves no message anywhere.** The run log's `engine_error` record holds the exception's type only (`RuntimeError`, `run/nodes.py` `_run_script`), `logs --kind engine` says there is no engine log, and the pause shows `reason: environmental` with no detail. The commit step's own message (`git add: ...`) was lost; the cause was found by running the git words by hand. To file as an engine issue: a script callable's failure keeps a bounded, scrubbed detail in the local store and names it in the pause.
- **The first `retry` of an environmental pause repeats the same failure at no cost but counts as a rescue touch** (`agent_decided:escalation` was recorded as a finding of side `workflow`). The retry was the diagnosis step, not a fault of the workflow.
- **The update path worked on a paused thread.** After the fix, `plugins/tempergraph/bin/tempergraph update` reinstalled the engine (same version, other content), `workflows register` picked up the package's new content digest, and `resume --decision retry` carried the paused thread on with the new engine and package. Nothing was refused and nothing said the thread now runs on other code than it started with.
- **`prepare` adds `tempergraph.commands.json` to every run's branch here**, because this repository has none. It arrives on the batch branch with the first merged run.

### Baseline suite on `main` (2026-11-25, Python 3.12, macOS)

- 2944 passed, 19 skipped, 1 failed in 14 min 20 s on four workers. The failure is `test_a_run_on_workers_leaves_the_real_folders_as_they_were` (TST-AC7): it compares the real `~/.tempergraph` and the real state root before and after a nested run, and the engine update and two live runs wrote there meanwhile. It is skipped only for a suite a step session runs (`TEMPERGRAPH_SESSION_KEY`). **A gate that runs the suite itself gets no such variable**, so a code gate that has to run `python -m pytest` again (the tree changed after the session's preview) fails this test while its own run writes its log, and so does any suite a person runs beside a live run.
- **The full suite is 14 minutes of every code session and every code gate that cannot reuse it.** With three runs side by side that is most of the machine.

## Ideas for the improvement loop

(filled as runs end)
