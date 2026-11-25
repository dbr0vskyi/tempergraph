# What the runs of this batch showed (temporary; becomes issues before the folder is deleted)

Filed from this file on 2026-11-25: #139 (commit on git 2.39), #140 (a script's lost message), #141 and #145 and #142 (monitor), #143 (the last stage's pull request), #144 (package tests and the real home), #148 (the phase gate's scope), #149 (`ts-exp-opened` per session), #150 (the outcome gate back to triage for one line), #151 (`ts-traced` and a live criterion), #152 (`workflow_changed` after a trip back), #153 (the usage limit and the retry budget), #154 (a rerun's second plan), #155 (feedback points not accounted for), #156 (a plan row under `.claude/`), #157 (context at a session's start), #158 (`status` names the engine's build), #159 (notes at the repository root), #160 (worktree cleanup on merge), #161 (TST-AC7 beside a live run), #162 (the run recipe in CONTRIBUTING). #124 has a comment with the review evidence. Not filed: the 40 warnings of `run --check`, the 14 minute suite.

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

### Probe of the connector leak (2026-11-25, sub-agent, 0.93 USD)

- A step-like launch with no extra word: 8,800 tokens at the first turn, 174,123 at the second, 0.71 USD for two turns. With `--strict-mcp-config` (no `--mcp-config` needed), or `ENABLE_CLAUDEAI_MCP_SERVERS=false`, or the setting `disableClaudeAiConnectors`: about 9,000 tokens a turn, under 0.01 USD. A `mcp__*` deny removes the definitions but the connectors still connect, and it also removes a declared server's tools. A judge launch still connects to the connectors (about 1,350 tokens).
- The servers connect after `system/init`, so the init record lists none of them: the engine's own live probes, which read init, could not have seen this.
- The CLI's debug log says tool search is off because `--tools` leaves its tool out, so every MCP schema is inlined in full.
- Stopgap in use from run i21 on: the launch shell exports the variable. The fix is run i21.

### i71, code step (2026-11-25)

- **A step session cannot edit a file under `.claude/`**: Claude Code denies it where nobody can answer a permission prompt (`reason_type: asyncAgent`). The plan had a row to bring `.claude/rules/temperspec/plan.rule.md` in line with the package's rule, the Edit was denied, and the run paused with `tool_access`. The operator ran `install_rules.py --update` in the worktree and sent the step back with feedback. Every task that changes a rule file in this repository meets this. Remedies: the plan check refuses a row whose file is under `.claude/`, and the workflow syncs the installed rule files with a script after a step that changed a rule (no model).

### The monitor's list of identical runs (2026-11-25, sub-agent report)

- **Package tests started from the package's folder use the real home** (#144). The engine's isolation fixture lives in the engine's `tests/conftest.py`; a package has none. i71's code sessions ran `cd plugins/temperspec-tgraph && python -m pytest tests/...`, and the operator ran `python -m pytest ../../temperspec-tgraph/tests` once from the engine folder: 106 pytest folders in the machine index, 110 test rows of 115 in the month's stats, 34 `temperspec/P-1` threads in `status --all-roots`. Cost reports of this machine are wrong until the entries are removed; no verb removes them.
- **The monitor gives every run of another state root the same label** (#145): the word `repo` and a hash of the thread id only; nothing is folded.

### i141 (2026-11-25): finished, outcome met, 11.64 USD, 30 minutes; then blocked by review

- **Every gate passed and an independent reader found a blocking defect in three minutes.** The walk over the three places the engine may be in loops for ever when the option names the home shim and every place fails; the plan's own row said "without duplicates". Five smaller defects beside it (a rejected `process.run` is not handled, a state shape that changed without a new name, no second look after not-found, a shell probe where the host has an env call, two spec lines that disagree with the code). The code judge graded `ts-code-aligned` MET. This is what #124 (an independent reader of what a run delivered) describes; here the reader was a sub-agent given the diff, the criteria and nothing else, for about 120,000 tokens.
- **The fix went back through the workflow**: `rerun --from plan --feedback-file` with the review as feedback. If this holds, "review the diff with a reader that has not seen the run, send what it finds back as a rerun" is a unit the workflow could own: a `review` gate after `code` whose judge reads only the diff and the criteria.
- Three retries inside the run: two `read_gap` items and the plan. The mod's `bun` tests were edited and could not be run on this machine.
- **The rerun fixed the blocker and declined two findings on a false premise.** Re-review: the loop, the rejected verb and the state shape are fixed; the second look after not-found was declined in the plan, and the plan said the host has no environment call after searching only the repository (the host's types have one). A new defect came with the fix: a timeout now counts as a missing engine. Feedback is treated as optional by the plan step: nothing checks that each numbered point of a rerun's feedback is either built or refused with a reason the owner sees.
- **A rerun writes a second plan and report under its own id** (`i141~r1.plan.md`), though the feedback said to edit the first in place; the `~` breaks the slug rule of document names. The steps' templates take the rerun's task id.
- Cost of the loop "review, rerun, re-review": 11.58 USD for the rerun and about 260,000 sub-agent tokens for the two reviews, against 11.64 USD for the first run.

### i71 (2026-11-25): finished, outcome met, 11.06 USD

- **First real `opened`**: draft pull request #146, opened by the run's last stage after #143. The run was not hands-free: #139 at `prepare`, and the `.claude/` edit at `code`.

### The account's usage limit at 14:25 UTC (2026-11-25)

- **A usage limit spent the retry budget in two seconds.** Three live runs each had their session refused; the engine recorded `error_kind: model`, started the retry at once, was refused again, and after three refusals i21 ended with exit 5 (`budget`) and the rerun of i141 paused on `retry_budget`. The loop's own reviews already wait for the reset the executor reports (SIL, the review retry); a step does not. A refusal for the usage limit should be its own class that charges no retry and pauses the run with the reset time, so `resume` after the reset is all it needs. Earlier batches met the same ("three needed a retry after a usage-limit hit").
- Both threads went on with a plain `resume` after the limit was lifted.

### i21, first phase (2026-11-25)

- **The phase judge cannot tell the phase's own changes from the earlier steps'.** The plan took the `phases` arm. The judge of phase `p1` graded `ts-phs-scope` PARTIAL and set a gap: the changed paths it was given hold the triage note, the hand-off and the spec ("they look like earlier-step products but I could not confirm which commit changed them"), and the run paused on `unresolved_gap`. The phase's own commit changed three files, all named by its rows. The check hands the judge the paths changed since the run's base, not since the phase started; a read-only judge cannot run `git log`. Remedy in the workflow: the phase check lists the paths changed since the commit before the phase (it has the head at `unit_entered`), and says which earlier step's commit holds each other path. This is the family of the loop's issue #117 (`check_fail:phase`) and it cost one pause of a person.
- The operator checked the commits and answered `proceed` with the facts as feedback.

### i21, after its phases (2026-11-25)

- Phase `p2` paused the same way as `p1` (#148): every criterion MET, `gap: true`, because the judge "could not run git". Two pauses of a person in one run for one cause.
- **The outcome gate sent the run back to the plan for a criterion no test can carry.** `ts-traced` failed with "ECC-AC5 is named by no test"; ECC-AC5 says the probe results are recorded for the pinned CLI version, which is a live fact. The plan step answered by adding a row for a test of the runbook's text. The rule "an old criterion that proves a behaviour the run changed needs a test" has no way to say a criterion is proved by a live check.
- **After a trip back, `expand` spent its whole retry budget on `ts-exp-opened`.** The check counts only the files the current session opened. Each retry was a fresh session that opened the files the last finding named and not the rest, so the finding moved from one file to another three times, and the run paused on `retry_budget` with one file left. Remedies: count the files opened over all sessions of the visit, or name every missing file in one finding (the evidence was cut after the second), or let the retry prompt say that every row's file must be opened again.
- The trip back also met `ts-plan-form` once: rows marked earlier whose file "changed after its marking commit", because a later phase had touched the same file.

### Worktree cleanup (2026-11-25)

- Finished runs keep their worktree: `run.worktree.cleanup` is `never` unless set, and the spec's open question (should `on_finish` be the default) waits on a live removal. `worktree prune --thread <t> --apply` removed the four finished and merged worktrees (i7, i71, i141, i141~r1) on its first live use here; each was clean and unlocked, the branches stayed.
- `on_finish` removes at the run's exit, which is before a review of the diff and before a rerun; what the owner asked for is removal when the run's work is merged. A cleanup value such as `on_merge` (the branch is an ancestor of its base branch) would say that.

### i144 (2026-11-25): the outcome gate's trips back

- **A one-line wording fix sent the whole run back to triage.** At the second outcome gate the check passed and the judge wrote "all task criteria are achieved with tests"; it graded `ts-spec-sync` PARTIAL with the fix in one sentence (add "until `stats forget` removes it (CST-B17)" to a scenario of CST-B8) and no `defect_in`. The gate routed to `triage.step`: triage again, three reading sessions again, then discovery, plan and code again, for a line a discovery visit could add. The first trip back (to the plan) was the same `ts-traced` rule as in i21, for CST-AC5. Remedy: a PARTIAL of an outcome criterion with no `defect_in` goes to the latest step that owns the file it names (discovery's short visit for a spec line), never to triage.
- **The run then stopped at `attempt_cap`** (15 attempts in one invocation, exit 4): two trips back are enough to reach it. `resume` continues, so it is one more touch of a person and not a failure, but nothing in the exit says the run was in a loop of trips back.
- **The stopped thread could not be resumed.** `resume` exited 2 with `workflow_changed`: "cannot resume on workflow version 0.1.0+b1320bb6cfb4: 'discovery' now produces 'handoff', which a later unit reads and this thread never recorded ... Reinstall the version it ran on (0.1.0+aedbf93a44f5)". The package's content changed when run i71 was merged (two prompt files); the trip back to triage had cleared this thread's `handoff` and `plan`, so the check read a key both versions produce as new. Run i21, with its artifacts recorded, resumed across the same change. A merge into the checkout a package is registered from changes the package under every live run of it; the operator now merges package changes only when no run of that area is between a trip back and its next step, or accepts the branch as it stands. Here the branch was reviewed as it stood: its code had passed the code gate and the outcome judge had graded every task criterion met.
- Two of three runs of the day that reached the outcome gate with a spec change were sent back by `ts-traced` for an old criterion that names a live or recorded fact (ECC-AC5, CST-AC5).

### i144, the review of the stopped branch (2026-11-25)

- **A second run whose every passed gate hid a defect that blocks its use.** The pytest plugin is an entry point inside the engine's package; pytest imports entry-point plugins before any conftest, so the engine's name is bound to the installed copy before the suite's conftest puts the worktree's `src` first. A one-process suite run in a worktree would then test another checkout's code and say nothing. It does not bite yet only because the shared environment was installed before the entry point existed. Seven smaller points beside it (the fixture's scope, the order and locking of the verb's two writes, an option accepted and ignored, the spec line the judge had asked for). Sent back as a rerun from `plan` (`tasks/i144.review.md`).
- The reviewer's read-only count on this machine: 106 of 107 roots of the index are gone folders, 110 run rows and 1,152 session rows of the month would go.

### Baseline suite on `main` (2026-11-25, Python 3.12, macOS)

- 2944 passed, 19 skipped, 1 failed in 14 min 20 s on four workers. The failure is `test_a_run_on_workers_leaves_the_real_folders_as_they_were` (TST-AC7): it compares the real `~/.tempergraph` and the real state root before and after a nested run, and the engine update and two live runs wrote there meanwhile. It is skipped only for a suite a step session runs (`TEMPERGRAPH_SESSION_KEY`). **A gate that runs the suite itself gets no such variable**, so a code gate that has to run `python -m pytest` again (the tree changed after the session's preview) fails this test while its own run writes its log, and so does any suite a person runs beside a live run.
- **The full suite is 14 minutes of every code session and every code gate that cannot reuse it.** With three runs side by side that is most of the machine.
- **The monitor's run list looks frozen during a long session.** The mod polls `status` every 5 s, but the list row is built from the detail document, which it fetches again only when the run log grows, and a session writes no run-log record between `session_opened` and its end. A 15 minute discovery session shows the same unit and the same cost for 15 minutes; only the elapsed minutes move. The detail document's `health.silent_s` and the session's activity are there to show.

## Ideas for the improvement loop

(filled as runs end)
