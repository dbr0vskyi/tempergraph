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
- **The first three runs did not run the installed engine.** The dev environment's editable install puts its own `tempergraph` in `.venv/bin`, and the launch put `.venv/bin` first on `PATH`, so runs i71, i7 and i141 execute the working tree of the main checkout, not `~/.tempergraph/engines/<build>`. The paused i71 went on after the fix because the working tree held the fix, not because of `tempergraph update` (which did reinstall the engine, same version, other content, and `workflows register` did pick up the package's new digest). Nothing in `status` tells the two apart: both report engine `0.2.0`. A status row that names the engine's build and path would have shown it at once. Later runs start through the shim.
- **`prepare` adds `tempergraph.commands.json` to every run's branch here**, because this repository has none. It arrives on the batch branch with the first merged run.

### i7 (2026-11-25): finished, outcome met, 8.03 USD, 21 minutes

Cost by session (reported USD): triage 1.02 + judge 0.08; three `read_gap` 0.56 + judges 0.23; discovery 2.78 + judge 0.10; plan 1.24 + judge 0.13; code 1.51 + judge 0.24; outcome judge 0.14. Discovery is 35 percent of the cost and 12 of the 21 minutes.

- **Step sessions carry about 160,000 tokens of MCP tool definitions that no step uses.** A step session's first turn holds about 174,000 tokens and 160 tools; a judge session holds about 10,000 to 14,000 tokens and 3 tools. The init record of a step lists eight `claude.ai` connectors of the signed-in account (Docs, Notion, Calendar, Gmail, Google Docs, Slides, Sheets, Drive). `step_argv` passes `--tools` and `--setting-sources project` but neither `--strict-mcp-config` nor a `mcp__*` deny unless the step declares an MCP tool; the judge launch denies `mcp__*`. Of the run's 20.5 million cache-read tokens, 20.2 million are step sessions', and four step sessions each wrote the 160,000 tokens to the cache again. Rough share of the run's cost: half. This is the live answer to #21 (the probe of user-scope MCP servers): servers from settings files do not leak, account connectors do. No cloud run could show it, because a container has no connectors.
- **The loop saw the symptom and named the wrong remedy.** Its session reviews kept `context_bloat` on triage, discovery, plan and code ("about 210k tokens were in context before the first write") with remedy `prompt` (read specs by heading range). The digest has `peak_context` but no first-turn context, so a session that starts at 174k looks like a session that read too much. A lens that compares the context of the first turn with the prompt's own size, or with a judge's, would have named the tool surface.
- **The last stage has never opened a pull request with a real `gh`** (#143, fixed by hand on the batch branch). The description file was passed by its absolute path and the engine's command resolver refuses absolute paths; the package's tests ran any string through a fake context. The fix writes the file into the workspace's `.tempergraph/` and the test now resolves every command of the last stage with the engine's resolver.
- **The loop ran 15 session reviews for about 0.45 USD and filed nothing**: 8 observations recorded, each finding `below_floor`. `improve backlog temperspec` lists 12 clusters, all with score 0.00. Nothing reaches a person unless the person asks for the backlog.
- **Notes went to the repository root** (`docs/plans/i7.plan.md`, `docs/tasks/i7.*`), where `CONTRIBUTING.md` asks for the owning package's `docs/`. The temperspec block of `CLAUDE.md` names `docs/plans/` and `docs/tasks/` with no package.
- The owner decision G3 was a good question: the task was silent on the daily cap and the default was the safe one.

### i71, code step (2026-11-25)

- **A step session cannot edit a file under `.claude/`**: Claude Code denies it where nobody can answer a permission prompt (`reason_type: asyncAgent`). The plan had a row to bring `.claude/rules/temperspec/plan.rule.md` in line with the package's rule, the Edit was denied, and the run paused with `tool_access`. The operator ran `install_rules.py --update` in the worktree and sent the step back with feedback. Every task that changes a rule file in this repository meets this. Remedies: the plan check refuses a row whose file is under `.claude/`, and the workflow syncs the installed rule files with a script after a step that changed a rule (no model).

### The monitor's list of identical runs (2026-11-25, sub-agent report)

- **Package tests started from the package's folder use the real home** (#144). The engine's isolation fixture lives in the engine's `tests/conftest.py`; a package has none. i71's code sessions ran `cd plugins/temperspec-tgraph && python -m pytest tests/...`, and the operator ran `python -m pytest ../../temperspec-tgraph/tests` once from the engine folder: 106 pytest folders in the machine index, 110 test rows of 115 in the month's stats, 34 `temperspec/P-1` threads in `status --all-roots`. Cost reports of this machine are wrong until the entries are removed; no verb removes them.
- **The monitor gives every run of another state root the same label** (#145): the word `repo` and a hash of the thread id only; nothing is folded.

### Baseline suite on `main` (2026-11-25, Python 3.12, macOS)

- 2944 passed, 19 skipped, 1 failed in 14 min 20 s on four workers. The failure is `test_a_run_on_workers_leaves_the_real_folders_as_they_were` (TST-AC7): it compares the real `~/.tempergraph` and the real state root before and after a nested run, and the engine update and two live runs wrote there meanwhile. It is skipped only for a suite a step session runs (`TEMPERGRAPH_SESSION_KEY`). **A gate that runs the suite itself gets no such variable**, so a code gate that has to run `python -m pytest` again (the tree changed after the session's preview) fails this test while its own run writes its log, and so does any suite a person runs beside a live run.
- **The full suite is 14 minutes of every code session and every code gate that cannot reuse it.** With three runs side by side that is most of the machine.
- **The monitor's run list looks frozen during a long session.** The mod polls `status` every 5 s, but the list row is built from the detail document, which it fetches again only when the run log grows, and a session writes no run-log record between `session_opened` and its end. A 15 minute discovery session shows the same unit and the same cost for 15 minutes; only the elapsed minutes move. The detail document's `health.silent_s` and the session's activity are there to show.

## Ideas for the improvement loop

(filled as runs end)
