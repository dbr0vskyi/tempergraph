# Check contract and command runs

## Purpose

A gate's deterministic check is the cheap half of every gate: a FAIL retries the step with no judge call, and the judge reads what the check established instead of the step's claim ([JDG](05-judge-and-verdict.spec.md)). This spec defines what a check receives, what it may do, how it runs a command and what it returns, so that a workflow's most valuable gate, one that runs a plan's own verification, can be written against the engine's public interface ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T24 to T31; R-011 U1). It also owns the check preview: a step may run its own gate's check from inside its attempt, through one engine command, and repair what it finds before it ends ([ADR-0077](../adr/0077-a-step-previews-its-own-check-in-the-attempt.adr.md)). "Pure" in contract C5 means, for a check, no write to run state, no model or executor call, and the same answer for the same workspace and state; command runs inside the workspace are its only side effect. The engine owns the mechanics (resolution rules, launch, limits, reuse, evidence); the workflow owns the policy (which commands, what exit means, what fails) ([ADR-0075](../adr/0075-checks-get-a-context-and-an-engine-command-runner.adr.md)). Workflow authors, the judge and the tool host depend on it; design and build notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### CHK-B10 The context a check receives

WHEN a gate's check, the callable `check(ctx: CheckContext) -> CheckResult` named by `GateSpec.check`, is called THE engine SHALL give it `unit`, `item` (for a mapped item, [MAP](77-map-unit.spec.md)), `visit` and `attempt`; `preview` (true under `self-check`, a check needing no branch on it); `workdir` (the attempt's workspace, contract C10); `main_checkout` (read-only, for a resolver's decisions such as which interpreter to use); `request` (`{task_id, inputs}`, [CON-B9](01-contracts.spec.md)); `artifacts` (every artifact the unit's path produced, by key, item-keyed for map items); `values` ([VAL](76-step-values-and-template-keys.spec.md)); `facts` (earlier checks' facts on this path, by unit and key); `git` (`GitFacts` from the engine's git reader before the check starts, or `None` outside git: `branch`, `base`, `head`, `base_head`, `clean` meaning no tracked change and no untracked file outside the state root, `pushed` meaning the head commit is on a remote-tracking ref, `changed_paths` since the base at most 500 with a count beyond, `commits_since_base` ids and scrubbed subjects at most 100); `changed_paths` (git's, or outside git the manifest's, [WSP-B15](13-workspace-and-concurrency.spec.md)); `settings` (the workflow's resolved settings, read-only); `criteria` (the gate's `{id, mechanical}` list); `deadline_s` (seconds left of `GateSpec.check_timeout_s`); `read_text(path, max_bytes=1_000_000)`, refusing a path outside `workdir`; `resolve(text)`; and `run(cmd, timeout_s=None, reuse=False, min_start_s=0)`, `CheckResult` and `CheckFinding` being shared types ([SSN-B8](25-session-contract.spec.md)).

- GIVEN `read_text` on a path outside the workspace WHEN called THEN it is refused and the check sees an error value

### CHK-B11 Command resolution

WHEN a check, the tool host or a step's commands block resolves a command THE engine SHALL use the one public function `resolve_command(workflow, text, workdir)` through the workflow's `command_resolver` ([WFM](02-workflow-model.spec.md)), which receives `(text, workdir, main_checkout)` and is pure over them and their files, and give `ResolvedCommand{argv, prefix, resolver}` for a declared prefix with plain-word arguments; the same with `documented: true` for a command the resolver accepts as documented by the repository, including each prefix of `tempergraph.commands.json` at the repository root (`{"commands": ["<prefix>", …]}`) for a step or check that lists `@repository`, a missing or malformed file declaring none; the same with `cwd` set and no `cd` run for a leading `cd <relative folder inside the repository> &&`; and `CommandRefusal{reason}`, never run, for a shell metacharacter, a parent path, an absolute path, a leading change of directory outside the repository, or anything else (`not declared`).

- GIVEN `make lint && make docs` WHEN resolved THEN it is a `CommandRefusal` for a shell metacharacter

### CHK-B12 Command runs

WHEN `run` starts a resolved command through the engine's check launch site ([SEC-B7](14-security.spec.md)) THE engine SHALL launch the list argv with no shell, standard input closed, in `cwd` or `workdir` and with the engine's environment less credentials, as for the tool host; write output to `<thread>/checks/<unit>/<attempt>/<n>.out`, never a pipe; limit it to `min(timeout_s, deadline_s)`, ending the whole process tree on expiry (POSIX process group, Windows job object); not start it, returning `not_started: true`, when `deadline_s < min_start_s`; count as a result an exit code in the prefix's `finished_exit_codes` (default any normal exit) and as `finished: false` a signal, a kill, the limit or an unlisted code; and return a `CommandRun` of the scrubbed `argv`, `program_path`, `exit_code`, `finished`, `timed_out`, `not_started`, `reused`, `duration_s`, `output_path` and `tail` (the last 40 lines and any line matching the prefix's `summary_pattern`, scrubbed, at most 8,000 characters), with the workspace, main checkout, home folder and interpreter prefix replaced by `<workdir>`, `<main>`, `<home>` and `<python>` in `tail` and `program_path`, the environment evidence; `finished_exit_codes`, `no_reuse_exit_codes` and `summary_pattern` being optional per-prefix fields of the command allow-list entry.

- GIVEN a child that outlives its parent WHEN the limit passes THEN no process of the tree remains

### CHK-B13 Reuse of command runs

WHEN `run` is called with `reuse=True` THE engine SHALL return an earlier run in this thread with the same key, marked `reused: true`, the key a digest of argv, resolved program path, `head`, the status listing and the content digest of changed and untracked files outside the state root, and SHALL never store a run with `finished: false` or an exit code in the prefix's `no_reuse_exit_codes`.

- GIVEN an earlier run that exited 0 or 1 WHEN the key matches THEN it is reused
- GIVEN an earlier run that exited 4 listed in `no_reuse_exit_codes`, or was killed at the limit WHEN the key matches THEN it was not stored and runs again

### CHK-B14 What a check returns

WHEN a check returns ([SSN-B8](25-session-contract.spec.md)) THE engine SHALL take `result` (`PASS`, `MAYBE` or `FAIL`; with findings, the worse of `result` and the worst finding, a mismatch logged); `findings[]`, one per checked requirement with an optional `criterion` id (a finding naming an id the gate lacks kept without it), `status` (`pass`, `maybe`, `fail`, `n_a`, an `n_a` needing a `message` saying why the rule cannot apply here), `place` (path, path and line, or field), `fix` and `message` (one line each); `facts` (at most 20 slug keys with scrubbed values of at most 200 characters, extras dropped and values clipped with the count on the check record), stored for the unit and item on this visit and cleared with its artifacts by a trip back to or past it ([BUD-B4](08-budgets-and-failures.spec.md)); `runs[]`, added by the engine; `evidence`, bounded text for the judge; and `environmental` (the environment, not the work, failed: no interpreter, command refused, program missing), which escalates with no judge and no retry ([BUD](08-budgets-and-failures.spec.md)); and SHALL give facts to later checks as `ctx.facts`, to routes and switches, the finalizer ([FIN](78-finalizer-contract.spec.md)), the `facts` verb and the run detail document, never to a step prompt.

- GIVEN 25 facts WHEN stored THEN 20 are kept and the count of dropped entries is on the check record

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

WHEN a gate's check runs on the same workspace in workflows whose steps use different executors THE engine SHALL give the same context, runs and result, since checks never run through an executor.

- GIVEN steps on `claude` and on `antigravity` WHEN the same check runs on one workspace THEN context, runs and result are identical

## Acceptance criteria

- CHK-AC1 (CHK-B4, CHK-B5, CHK-B12, CHK-B13): Every scenario of CHK-B4 and CHK-B13 holds in an offline test with a real process tree and a scratch git repository
- CHK-AC2 (CHK-B12, CHK-B16, CHK-B15): A check that runs a child which outlives its parent is ended at the limit; no process of the tree remains (Linux, macOS, Windows)
- CHK-AC3 (CHK-B11, CHK-B9): `resolve_command` gives the same answer to a check, the tool host and the commands block for every fixture command (one shared function, source-scan test)
- CHK-AC4 (CHK-B8, CHK-B12): No `CommandRun.tail` or `program_path` in any record contains the workspace, main checkout or home path (canary test)
- CHK-AC5 (CHK-B1, CHK-B2, CHK-B3, CHK-B14): A FAIL with findings renders every finding's criterion, place and fix in the retry prompt, and starts no judge session
- CHK-AC6 (CHK-B17, CHK-B7): `self-check` writes no state, verdict, fact or budget change (state digest before and after), and its runs are reused by the gate's check on an unchanged tree
- CHK-AC7 (CHK-B6, CHK-B10, CHK-B14): Facts survive a resume and are cleared by a trip back exactly as artifacts are

## Open questions

- Should the check worker be kept warm across gates of one run to save the interpreter start? Until answered: one worker per check; measure first. Owner: engine implementer.
- Not built yet: the preview's grant ships for `claude` only; the other executors get theirs with their own release. Owner: engine owner.
