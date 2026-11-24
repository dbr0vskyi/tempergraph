# Check contract and command runs

## Purpose

A gate's deterministic check is the cheap half of every gate: a FAIL retries the step with no judge call, and the judge reads what the check established instead of the step's claim ([JDG](05-judge-and-verdict.spec.md)). This spec defines what a check receives, what it may do, how it runs a command and what it returns, so that a workflow's most valuable gate, one that runs a plan's own verification, can be written against the engine's public interface ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T24 to T31; R-011 U1). It also owns the check preview: a step may run its own gate's check from inside its attempt, through one engine command, and repair what it finds before it ends ([ADR-0077](../adr/0077-a-step-previews-its-own-check-in-the-attempt.adr.md)). "Pure" in OVR-B7 means, for a check, no write to run state, no model or executor call, and the same answer for the same workspace, state and session record; command runs, in the workspace or at the run's base in a checkout the engine makes and removes (CHK-B18, CHK-B21), are its only side effect. The engine owns the mechanics (resolution rules, launch, limits, reuse, evidence); the workflow owns the policy (which commands, what exit means, what fails) ([ADR-0075](../adr/0075-checks-get-a-context-and-an-engine-command-runner.adr.md)). Workflow authors, the judge and the tool host depend on it; design and build notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### CHK-B10 The context a check receives

WHEN a gate's check, the callable `check(ctx: CheckContext) -> CheckResult` named by `GateSpec.check`, is called THE engine SHALL give it `unit`, `item` (for a mapped item, [MAP](77-map-unit.spec.md)), `visit` and `attempt`; `preview` (true under `self-check`, a check needing no branch on it); `workdir` (the attempt's workspace, OVR-B12); `main_checkout` (read-only, for a resolver's decisions such as which interpreter to use); `request` (`{task_id, inputs}`, [CON-B9](01-contracts.spec.md)); `artifacts` (every artifact the unit's path produced, by key, item-keyed for map items); `values` ([VAL](76-step-values-and-template-keys.spec.md)); `facts` (earlier checks' facts on this path, by unit and key); `git` (`GitFacts` from the engine's git reader before the check starts, or `None` outside git: `branch`, `base`, `head`, `base_head`, `clean` meaning no tracked change and no untracked file outside the state root, `pushed` meaning the head commit is on a remote-tracking ref, `changed_paths` since the base at most 500 with a count beyond, `commits_since_base` ids and scrubbed subjects at most 100); `changed_paths` (git's, or outside git the manifest's, [WSP-B15](13-workspace-and-concurrency.spec.md)); `session` (the attempt's session record, or `None`, CHK-B24, CHK-B25); `settings` (the workflow's resolved settings, read-only); `criteria` (the gate's `{id, mechanical}` list); `deadline_s` (seconds left of `GateSpec.check_timeout_s`); `read_text(path, max_bytes=1_000_000)`, refusing a path outside `workdir`; `resolve(text)`; and `run(cmd, timeout_s=None, reuse=False, min_start_s=0, at_base=False)`, `CheckResult` and `CheckFinding` being shared types ([SSN-B8](25-session-contract.spec.md)).

- GIVEN `read_text` on a path outside the workspace WHEN called THEN it is refused and the check sees an error value

### CHK-B24 The session record a check receives

WHEN a gate's check runs after an attempt whose step session reported the capability of at least one tool call and whose activity journal kept every tool line THE engine SHALL give the check `session`, the calls the session made since it last started (an infra try starts it again, [BUD-B1](08-budgets-and-failures.spec.md)) in call order, each with `name`, `capability` (`read`, `search`, `list`, `edit`, `write`, `shell` or another capability of [EVT-B21](30-run-events.spec.md), null for an unknown tool), `target` (the call's input summary of EVT-B21: the path relative to the workspace for `read`, `list`, `edit` and `write`, `<outside workspace>` for a path outside it, the pattern for `search`; null for a call that names none and for every call under `observe.tool_inputs = off`, [EVT-B6](30-run-events.spec.md)) and `ok` (true when the call finished without an error), as a copy that no run-log record, ledger row, stats row, export or filed text carries ([decision](../adr/a-check-is-given-the-tool-calls-of-the-attempts-session.adr.md)).

- GIVEN a session that opened `docs/a.md`, searched for `plan`, edited `src/b.py` and wrote `tests/c.py` WHEN its check runs THEN `session` lists the four calls in that order with the capabilities `read`, `search`, `edit` and `write` and the targets `docs/a.md`, `plan`, `src/b.py` and `tests/c.py`
- GIVEN a call that ended with an error WHEN its check runs THEN that call reads `ok` false
- GIVEN attempt 1 that opened `docs/a.md` and a retry attempt of the same visit that opened `docs/b.md` WHEN the check runs after the retry THEN `session` lists the one call on `docs/b.md`
- GIVEN a session that ended with `broken_pipe` after one call and started again WHEN the check runs THEN `session` lists the calls since the second start only
- GIVEN `observe.tool_inputs = off` WHEN the check runs THEN every call has its `capability` and a null `target`
- GIVEN a read of a file outside the workspace WHEN the check runs THEN its `target` is `<outside workspace>`

### CHK-B25 No session record

WHEN a gate's check runs for an attempt that ran no step session, whose session made no call or whose executor reported no capability for any call, or whose activity journal dropped a tool line ([EVT-B7](30-run-events.spec.md)), or runs as the preview of CHK-B17 THE engine SHALL give the check `session` as `None`, never an empty list.

- GIVEN a stand-in executor that reports tool names only WHEN the check runs THEN `session` is `None`
- GIVEN a session that made no tool call WHEN the check runs THEN `session` is `None`
- GIVEN a session whose journal reached its cap and dropped a tool line WHEN the check runs THEN `session` is `None`
- GIVEN a step with `self_check: true` that runs `tempergraph self-check <ticket>` WHEN the preview's check runs THEN `session` is `None`

### CHK-B11 Command resolution

WHEN a check, the tool host or a step's commands block resolves a command THE engine SHALL use the one public function `resolve_command(workflow, text, workdir)` through the workflow's `command_resolver` ([WFM](02-workflow-model.spec.md)), which receives `(text, workdir, main_checkout)` and is pure over them and their files, and give `ResolvedCommand{argv, prefix, resolver}` for a declared prefix with plain-word arguments; the same with `documented: true` for a command the resolver accepts as documented by the repository, including each prefix of `tempergraph.commands.json` at the repository root (`{"commands": ["<prefix>", …]}`) for a step or check that lists `@repository`, a missing or malformed file declaring none; the same with `cwd` set and no `cd` run for a leading `cd <relative folder inside the repository> &&`; and `CommandRefusal{reason}`, never run, for a shell metacharacter, a parent path, an absolute path, a leading change of directory outside the repository, or anything else (`not declared`).

- GIVEN `make lint && make docs` WHEN resolved THEN it is a `CommandRefusal` for a shell metacharacter

### CHK-B12 Command runs

WHEN `run` starts a resolved command through the engine's check launch site ([SEC-B7](14-security.spec.md)) THE engine SHALL launch the list argv with no shell, standard input closed, in `cwd` or `workdir` (at the base, the same folder of the base checkout, CHK-B18) and with the engine's environment less credentials, as for the tool host; write output to `<thread>/checks/<unit>/<attempt>/<n>.out`, never a pipe; limit it to `min(timeout_s, deadline_s)`, ending the whole process tree on expiry (POSIX process group, Windows job object); not start it, returning `not_started: true`, when `deadline_s < min_start_s`; count as a result an exit code in the prefix's `finished_exit_codes` (default any normal exit) and as `finished: false` a signal, a kill, the limit or an unlisted code; and return a `CommandRun` of the scrubbed `argv`, `program_path`, `exit_code`, `finished`, `timed_out`, `not_started`, `reused`, `at_base`, `duration_s`, `output_path` and `tail` (the last 40 lines and any line matching the prefix's `summary_pattern`, scrubbed, at most 8,000 characters), with the workspace, main checkout, home folder and interpreter prefix replaced by `<workdir>`, `<main>`, `<home>` and `<python>` in `tail` and `program_path`, the environment evidence; `finished_exit_codes`, `no_reuse_exit_codes` and `summary_pattern` being optional per-prefix fields of the command allow-list entry.

- GIVEN a child that outlives its parent WHEN the limit passes THEN no process of the tree remains

### CHK-B13 Reuse of command runs

WHEN `run` is called with `reuse=True` THE engine SHALL return an earlier run in this thread with the same key, marked `reused: true`, the key a digest of argv, working folder, resolved program path and the content of the tree, and SHALL never store a run with `finished: false` or an exit code in the prefix's `no_reuse_exit_codes`; the content of the tree is every file git tracks and every untracked file git does not ignore (every file, outside a git repository), outside the state root, each by path, bytes and executable bit, so that no commit, index or status listing is part of the key ([decision](../adr/a-stored-command-run-is-keyed-on-the-trees-content.adr.md)).

- GIVEN an earlier run that exited 0 or 1 WHEN the key matches THEN it is reused
- GIVEN an earlier run that exited 4 listed in `no_reuse_exit_codes`, or was killed at the limit WHEN the key matches THEN it was not stored and runs again
- GIVEN an earlier run made while files were not yet committed WHEN those files are committed with no other change and the same command runs with `reuse=True` THEN the earlier run is reused
- GIVEN an earlier run WHEN a tracked file changes, or an untracked file that git does not ignore is added or removed, and the same command runs with `reuse=True` THEN it runs again

### CHK-B18 A command run at the base

WHEN `run` is called with `at_base=True` and the run has a base commit (`git.base`, the commit its worktree started from, [WTR-B21, WTR-B24](82-worktree-mode.spec.md)) THE engine SHALL run the command, as it resolves for the workspace, in a clean checkout of that commit made outside the workspace and the main checkout, starting in the same folder of the repository as a run in the workspace would, with the launch, environment, limit, output file and record of CHK-B12, and return the run's record marked `at_base: true`.

- GIVEN a command that exits 1 in the workspace and exits 0 on the base commit WHEN `run` is called with `at_base=True` THEN the run reads `exit_code: 0` and `at_base: true` and no file of the workspace has changed
- GIVEN a commit and an uncommitted edit since the base WHEN a command that prints a changed file runs at the base THEN it prints the file as the base commit has it
- GIVEN `cd sub/engine && python -m pytest` WHEN run at the base THEN it starts in `sub/engine` of the base checkout

### CHK-B19 A run at the base that cannot start

WHEN `run` is called with `at_base=True` and the run has no base commit, or the base commit cannot be checked out, or the command's folder is not in the base commit THE engine SHALL not start the command, return `not_started: true` with `at_base: true` and change nothing in the repository.

- GIVEN a run with no base commit (outside git, or in place) WHEN `run` is called with `at_base=True` THEN the run is `not_started` and nothing is checked out
- GIVEN `cd newpkg && pytest` and a base commit that holds no `newpkg` folder WHEN run at the base THEN the run is `not_started`

### CHK-B20 Reuse of a run at the base

WHEN `run` is called with `at_base=True` and `reuse=True` THE engine SHALL return an earlier run at the base from the same visit of the same unit with the same key, marked `reused: true` and making no checkout, the key a digest of argv, resolved program path, the base commit, the unit and the visit and never of the workspace's head, status or files, and SHALL never store a run with `finished: false` or an exit code in the prefix's `no_reuse_exit_codes`.

- GIVEN a run at the base in attempt 1 of a visit WHEN attempt 2 of the same visit asks for the same command at the base after a file of the workspace changed THEN no process starts and the run is `reused: true`
- GIVEN the same command asked for at the base in the next visit of the unit WHEN the check runs THEN it starts again
- GIVEN a run at the base killed at the limit WHEN the same command is asked for again in the visit THEN it starts again

### CHK-B21 The base checkout leaves nothing behind

WHEN a check that ran a command at the base ends, whether it returned, raised or was ended at its limit, THE engine SHALL remove the base checkout and leave in the repository no worktree entry, branch, ref or changed file for it.

- GIVEN a check that ran a command at the base WHEN it returns THEN the checkout's folder is gone and the repository's worktree list, branch list and status are as before the check
- GIVEN a check worker ended at its limit while a command ran at the base WHEN the engine records the FAIL THEN the checkout's folder is gone

### CHK-B22 The base branch's head

WHEN a check's context is built in a git repository THE engine SHALL set `git.base_head` to the commit the run's base branch ([WTR-B21, WTR-B24](82-worktree-mode.spec.md)) points to at that moment, read from the repository's own refs (its local branch, else its remote-tracking branch on `origin`, with no fetch), or to the empty string when the run has no base branch or no ref names it, so that a check can tell what the base branch has gained since the run's base commit (`git.base`).

- GIVEN a worktree run started at commit A of `main` and a commit B added to `main` since WHEN a check runs THEN `git.base` is A and `git.base_head` is B
- GIVEN a run in place, which has no base branch WHEN a check runs THEN `git.base_head` is empty
- GIVEN a base branch `main` that exists only as `origin/main` at commit C WHEN a check runs THEN `git.base_head` is C

### CHK-B14 What a check returns

WHEN a check returns ([SSN-B8](25-session-contract.spec.md)) THE engine SHALL take `result` (`PASS`, `MAYBE` or `FAIL`; with findings, the worse of `result` and the worst finding, a mismatch logged); `findings[]`, one per checked requirement with an optional `criterion` id (a finding naming an id the gate lacks kept without it), `status` (`pass`, `maybe`, `fail`, `n_a`, an `n_a` needing a `message` saying why the rule cannot apply here), `place` (path, path and line, or field), `fix` and `message` (one line each); `facts` (at most 20 slug keys with scrubbed values of at most 200 characters, extras dropped and values clipped with the count on the check record), stored for the unit and item on this visit and cleared with its artifacts by a trip back to or past it ([BUD-B4](08-budgets-and-failures.spec.md)); `runs[]`, added by the engine; `evidence`, bounded text for the judge; and `environmental` (the environment, not the work, failed: no interpreter, command refused, program missing, or a failure the check shows was there before the run's change, such as a command that fails the same at the run's base, CHK-B18), which escalates with no judge and no retry ([BUD](08-budgets-and-failures.spec.md)); and SHALL give facts to later checks as `ctx.facts`, to routes and switches, the finalizer ([FIN](78-finalizer-contract.spec.md)), the `facts` verb and the run detail document, never to a step prompt.

- GIVEN 25 facts WHEN stored THEN 20 are kept and the count of dropped entries is on the check record
- GIVEN a command that exits 1 in the workspace and exits 1 at the base commit WHEN the check returns FAIL marked `environmental` with an evidence line naming both exits THEN the gate pauses as an escalation with no judge and no retry, and `runs` holds the workspace run and the base run, the base run `at_base: true`

### CHK-B15 Check failures

WHEN a check raises THE engine SHALL record a check FAIL with the exception type only and `environmental: false`, spending a retry (a workflow fault for the self-improvement loop, [SIL](16-self-improvement.spec.md)), and when the check worker passes its limit SHALL end the worker and its tree and record a FAIL with `environmental: true`, which escalates; and `mechanical: true` on a gate with no check SHALL be a validation error ([WFM](02-workflow-model.spec.md)).

- GIVEN a check that raises WHEN the gate runs THEN the check fails naming the exception type and a retry is spent

### CHK-B16 The check worker and its limit

WHEN a check runs THE engine SHALL run it in a child engine process, the check worker, that receives the context as a document on standard input like the library executors' workers ([ADR-0019](../adr/0019-in-process-executors-run-in-a-worker-process.adr.md)), carrying the engine's import path and the map of workflow packages' private import names to their folders ([PKG](88-workflow-package.spec.md)) so it imports the check by its reference alone; bound the whole check by `GateSpec.check_timeout_s` (default 1800 s); and end the worker and its process tree at the limit plus 30 s.

- GIVEN a check whose code hangs WHEN the limit plus 30 s passes THEN the worker and its tree are ended

### CHK-B1 Mechanical failure costs no judge

WHEN a check FAILs a `mechanical` criterion THE engine SHALL start no judge session and list each finding with its place and fix under the rejection reason in the retry prompt.

- GIVEN criterion `reading-sets` `mechanical` and a FAIL finding `{criterion: reading-sets, place: "plan.md:212", fix: "add the line range of parse_row"}` WHEN the judge node runs THEN no judge session starts and the retry prompt lists the finding with its place and fix

### CHK-B2 Mechanical pass is given

WHEN a check passes a `mechanical` criterion THE judge brief SHALL show the criterion with the check's finding and the fixed sentence that the check verified it and its evidence is to be taken as given, the judge grading only what the check does not cover.

- GIVEN a passed mechanical criterion WHEN the judge runs THEN its brief marks the criterion verified by the check

### CHK-B3 Not applicable

WHEN a check marks a criterion `n_a` with a reason THE judge SHALL be shown the criterion as N/A with that reason, and an N/A from the judge on it SHALL count as reasoned ([JDG](05-judge-and-verdict.spec.md)).

- GIVEN no plan folder and `{criterion: plan-search, status: n_a, message: "no plan folder"}` WHEN the judge grades THEN the criterion shows as N/A with that reason

### CHK-B4 A test run

WHEN a check resolves and runs a plan's verification items THE engine SHALL report each run's outcome for the check to decide.

- GIVEN `python -m pytest tests/unit` WHEN run THEN it exits 0 and the check passes it
- GIVEN `go test ./...` documented in the repository WHEN run THEN it resolves `documented`, exits 1 and the check fails it
- GIVEN `make lint && make docs` WHEN resolved THEN it is refused and not run, and the check records `maybe`, "not run: shell metacharacter"
- GIVEN `python -m pytest tests/e2e` killed at the limit WHEN run THEN it is `finished: false` and `timed_out`, and the check decides
- GIVEN any command with `deadline_s < min_start_s` WHEN run THEN it is `not_started` and the check decides

### CHK-B5 Reuse after a judge-only failure

WHEN a check runs again with `reuse=True` after a judge-only failure and nothing in the tree changed THE engine SHALL not run the command, mark it `reused: true` and say so in the evidence, and SHALL run it again when one file changed.

- GIVEN a 25-minute suite that passed and a judge RETRY WHEN the next attempt changes nothing THEN the suite is not run and the run is `reused: true`
- GIVEN one file changed WHEN the check runs THEN the suite runs again

### CHK-B6 A fact for a later gate

WHEN a check records a fact THE engine SHALL give it to later checks on the path and clear it on a trip back to or past its unit.

- GIVEN a code gate's check recording `facts: {code_head: <commit>}` WHEN the release gate's check runs THEN `ctx.facts["code"]["code_head"]` holds the commit, and after a trip back to `code` it is absent until recorded again

### CHK-B17 The check preview

WHEN a step declares `self_check: true` ([CON-B5](01-contracts.spec.md)) on a unit whose gate has a check THE engine SHALL add `tempergraph self-check <ticket>` to its commands block, the ticket random, naming thread, unit, item and attempt, and kept as `<state root>/tickets/<ticket>.json` for the session's length; grant it as a command prefix even when the step declares no `shell` (an allow rule `Bash(<command>)` on `claude`); add the fixed prompt section "Check your work before you end" naming the command and saying it reports what the gate's check would find, and on a step with no `shell` say in the tools section that there is no shell except this one command and name the tool that runs it; run the unit's check on the current workspace in the check worker with `preview = true`, the artifacts as state held them when the attempt began, printing the result, the findings (status, criterion, place, fix, message) and at most 2,000 characters of evidence; write no verdict, fact, artifact or state, run no judge and spend no budget, the gate's own check always running after the session; store its command runs for reuse; allow `self_check_limit` calls per attempt (default 3, a run setting of [RST](80-run-settings-and-overrides.spec.md)), the next printing that the limit is reached and exiting 2; exit 2 running nothing for an unknown, expired or other attempt's ticket; and record one `self_check` run event per call with unit, item, attempt, result, finding counts and duration.

- GIVEN a step with no `shell` and `self_check: true` WHEN prompted THEN the tools section names the one command it may run

### CHK-B7 Preview inside the attempt

WHEN a session runs its preview within the limit THE engine SHALL print findings each time, change no state or budget, and refuse the call after the limit.

- GIVEN an expand step with `self_check: true` that runs `tempergraph self-check <ticket>` twice with an edit between WHEN the session ends THEN both calls printed findings, state and budgets are unchanged, the gate's check runs as usual, and a fourth call is refused with exit 2

### CHK-B8 Environment evidence

WHEN a resolver picks an interpreter outside the workspace THE engine SHALL show it with placeholders as `program_path` to the judge and the run detail document.

- GIVEN a worktree with no virtual environment and a resolver picking the main checkout's interpreter WHEN a test command runs THEN `program_path` reads `<main>/.venv/bin/python`

### CHK-B9 Same on every executor

WHEN a gate's check runs on the same workspace in workflows whose steps use different executors THE engine SHALL give the same context, `session` apart, which follows what each executor's session did (CHK-B24), and the same runs and result, since checks never run through an executor.

- GIVEN steps on `claude` and on `antigravity` WHEN the same check, one that does not read `session`, runs on one workspace THEN the context other than `session`, the runs and the result are identical

## Acceptance criteria

- CHK-AC1 (CHK-B4, CHK-B5, CHK-B12, CHK-B13): Every scenario of CHK-B4 and CHK-B13 holds in an offline test with a real process tree and a scratch git repository
- CHK-AC2 (CHK-B12, CHK-B16, CHK-B15): A check that runs a child which outlives its parent is ended at the limit; no process of the tree remains (Linux, macOS, Windows)
- CHK-AC3 (CHK-B11, CHK-B9): `resolve_command` gives the same answer to a check, the tool host and the commands block for every fixture command (one shared function, source-scan test)
- CHK-AC4 (CHK-B8, CHK-B12): No `CommandRun.tail` or `program_path` in any record contains the workspace, main checkout or home path (canary test)
- CHK-AC5 (CHK-B1, CHK-B2, CHK-B3, CHK-B14): A FAIL with findings renders every finding's criterion, place and fix in the retry prompt, and starts no judge session
- CHK-AC6 (CHK-B17, CHK-B7): `self-check` writes no state, verdict, fact or budget change (state digest before and after), and its runs are reused by the gate's check on an unchanged tree
- CHK-AC7 (CHK-B6, CHK-B10, CHK-B14): Facts survive a resume and are cleared by a trip back exactly as artifacts are
- CHK-AC8 (CHK-B18, CHK-B19): In a scratch git repository with a commit and an uncommitted edit after the base, a command run at the base prints the base commit's files, starts in its folder of the base checkout, reads `at_base: true` and changes no file of the workspace; with no base commit, or with no such folder in the base commit, the run is `not_started`
- CHK-AC9 (CHK-B20): A command asked for at the base in two attempts of one visit starts once and the second run is `reused: true` although the workspace changed between them; it starts again in the next visit and after a run killed at the limit
- CHK-AC10 (CHK-B21): After a check that ran a command at the base returns, and after one whose worker was ended at its limit, the base checkout's folder is gone and the scratch repository's worktree list, branch list and status are as before
- CHK-AC11 (CHK-B14): A check FAIL marked `environmental` whose `runs` hold a workspace run and a run `at_base: true` escalates with no judge and no retry, and the check record holds its evidence and both runs
- CHK-AC12 (CHK-B13, CHK-B17): A command run by the check preview while a step's files are not yet committed is reused by the gate's check once those files are committed with no other change, and runs again at the gate when one file changed after the preview (a scratch git repository, offline)
- CHK-AC13 (CHK-B22): In a scratch git repository with a worktree run started at a commit of `main`, a commit added to `main` afterwards is `git.base_head` while `git.base` is still the starting commit; a run in place has an empty `git.base_head`; with only `origin/main` present it is that remote-tracking branch's commit (offline)
- CHK-AC14 (CHK-B10, CHK-B24): A check run after a stand-in session that reported a read, a search, an edit and a write, in that order, sees `session` with those four calls in that order, each with its name, capability, target and `ok`
- CHK-AC15 (CHK-B24): A call that ended with an error reads `ok` false; the check run after a retry attempt sees only the retry session's calls; the check run after a session that started twice sees only the calls since the second start
- CHK-AC16 (CHK-B24): Under `observe.tool_inputs = off` every call the check sees has its capability and a null target; a read outside the workspace has the target `<outside workspace>`; and the canary test of [SEC-B2](14-security.spec.md) finds a planted tool input, which the check saw as a target, only in activity journals and live files
- CHK-AC17 (CHK-B25): A check that reads `session` sees `None` after a stand-in session that reported tool names only, after a session that made no tool call, after a session whose journal dropped a tool line, and as a preview
- CHK-AC18 (CHK-B9): The same check, one that does not read `session`, run on one workspace after steps of two executors gets the same context other than `session`, the same runs and the same result

## Open questions

- Should the check worker be kept warm across gates of one run to save the interpreter start? Until answered: one worker per check; measure first. Owner: engine implementer.
- Not built yet: the preview's grant ships for `claude` only; the other executors get theirs with their own release. Owner: engine owner.
- Should a run at the base put the base checkout ahead of an installed copy of the code under test? A Python package installed in editable mode loads the tree it was installed from, so a command run at the base can exercise the workspace's code. Until answered: no, the run has the workspace's environment (CHK-B18), and a workflow that compares a run at the base with its own run allows for it. Owner: engine owner.
