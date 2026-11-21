---
title: Check contract and command runs
type: component
status: ready-for-implementation
prefix: CHK
adrs: [0075, 0077, 0067]
---

# Check contract and command runs

## 1. Overview

A gate's deterministic check is the cheap half of every gate: a FAIL retries the step with no judge call, and the judge reads what the check established instead of the step's claim ([JDG-B6](05-judge-and-verdict.spec.md)). This spec defines what a check receives, what it may do, how it runs a command and what it returns, so that a workflow's most valuable gate (temperspec's code gate, which runs the plan's own verification) can be written against the engine's public interface ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T24 to T31; R-011 U1).

It also owns the **check preview**: a step may run its own gate's check from inside its attempt, through one engine command, and repair what it finds before it ends ([ADR-0077](../adr/0077-a-step-previews-its-own-check-in-the-attempt.adr.md)).

"Pure" in contract C5 means, for a check: no write to run state, no model or executor call, and the same answer for the same workspace and state. Command runs inside the workspace are a check's only side effect ([ADR-0075](../adr/0075-checks-get-a-context-and-an-engine-command-runner.adr.md)).

## 2. Contract

```python
def check(ctx: CheckContext) -> CheckResult: ...           # the workflow's callable, GateSpec.check
def resolve_command(workflow: str, text: str, workdir: Path) -> ResolvedCommand | CommandRefusal: ...
                                                           # public: the one lookup a check and the tool host share
```

`CheckResult` and `CheckFinding` are shared types ([CON §2.8](01-contracts.spec.md)). The types below are used by this spec and by workflow checks only.

### 2.1 The context a check receives

| Field or method | Kind | Meaning |
|---|---|---|
| `unit`, `item`, `visit`, `attempt` | str, str \| None, int, int | Where the check runs; `item` for a mapped item ([MAP](77-map-unit.spec.md)) |
| `preview` | bool | True when the step runs the check through `self-check` (§2.5); a check needs no branch on it |
| `workdir` | path | The attempt's workspace (contract C10) |
| `main_checkout` | path, read-only | The repository's main checkout; for a resolver's decisions such as which interpreter to use |
| `request` | `{task_id, inputs}` | The resolved request ([CON §2.3](01-contracts.spec.md)) |
| `artifacts` | map key → pointer | Every artifact in state that the unit's path produced, by key, item-keyed for map items |
| `values` | map key → str | Step values ([VAL](76-step-values-and-template-keys.spec.md)) |
| `facts` | map unit → map key → str | Facts recorded by earlier checks on this path (§2.4) |
| `git` | `GitFacts` | Computed by the engine's git reader before the check starts |
| `settings` | map name → value | The workflow's resolved settings for this run (owned by the settings design; read-only here) |
| `criteria` | list of `{id, mechanical}` | The gate's criteria, so findings can name them |
| `deadline_s` | float | Seconds left of `GateSpec.check_timeout_s` |
| `read_text(path, max_bytes=1_000_000)` | str | Reads a file inside `workdir`; a path outside it is refused |
| `resolve(text)` | `ResolvedCommand` \| `CommandRefusal` | §2.2 |
| `run(cmd, timeout_s=None, reuse=False, min_start_s=0)` | `CommandRun` | §2.3 |

| Type | Field | Meaning |
|---|---|---|
| `GitFacts` | `branch`, `base`, `head`, `base_head` | Names and commit ids |
| | `clean` | No tracked change and no untracked file outside the state root |
| | `pushed` | The branch exists on any configured remote |
| | `changed_paths` | Paths changed since the base, at most 500, with a count beyond |
| | `commits_since_base` | Commit ids and subjects (scrubbed), at most 100 |

### 2.2 Command resolution

`resolve` is the same lookup the tool host and the step's commands block use, through the workflow's `command_resolver` ([WFM-B6](02-workflow-model.spec.md)). Because it is public, a check that validates commands written in an artifact (temperspec's plan check) gets the same answer the run will get.

| Input | Result |
|---|---|
| A declared prefix with plain-word arguments | `ResolvedCommand{argv, prefix, resolver}` |
| A command the resolver accepts as documented by the repository (it may read files under `workdir`) | `ResolvedCommand` with `documented: true` |
| A shell metacharacter, a parent path, an absolute path, or a leading change of directory outside the repository | `CommandRefusal{reason}`; never run |
| A leading `cd <relative folder inside the repository> &&` | `ResolvedCommand` with `cwd` set; the `cd` is not run as a command |
| Anything else | `CommandRefusal{reason: "not declared"}` |

The resolver receives `(text, workdir, main_checkout)` and must be pure over them and the files they contain.

### 2.3 Command runs

`run` starts the resolved argv through the engine's check launch site ([SEC §2.2](14-security.spec.md)):

| Rule | Detail |
|---|---|
| Launch | List argv, no shell, standard input closed, working directory `cwd` or `workdir`; the environment is the engine's with credentials removed, as for the tool host |
| Output | Written to a file under the attempt's folder (`<thread>/checks/<unit>/<attempt>/<n>.out`), never a pipe |
| Limit | `min(timeout_s, deadline_s)`; on expiry the whole process tree is ended (POSIX process group, Windows job object) |
| Start guard | When `deadline_s < min_start_s` the command is not started; the run returns `not_started: true` |
| Finished | An exit code listed in the prefix's `finished_exit_codes` (default: any code from a normal exit) is a result; a signal, a kill, the limit, or an unlisted code is `finished: false` |
| Reuse | With `reuse=True`, an earlier run in this thread with the same key returns its result marked `reused: true`. Key: digest of argv, resolved program path, `head`, the status listing and the content digest of changed and untracked files outside the state root. A run with `finished: false`, or an exit code in the prefix's `no_reuse_exit_codes`, is never stored |
| Evidence | `tail`: the last 40 lines and any line matching the prefix's `summary_pattern`, scrubbed, with the workspace, main checkout, home folder and interpreter prefix replaced by `<workdir>`, `<main>`, `<home>`, `<python>` |

| Type | Field | Meaning |
|---|---|---|
| `CommandRun` | `argv` | As run, scrubbed |
| | `program_path` | The resolved program, with the same placeholders: the environment evidence |
| | `exit_code`, `finished`, `timed_out`, `not_started`, `reused` | int \| None, bool ×4 |
| | `duration_s`, `output_path`, `tail` | float, path, text ≤ 8,000 chars |

`finished_exit_codes`, `no_reuse_exit_codes` and `summary_pattern` are optional fields of the workflow's command allow-list entry, per prefix.

### 2.4 What a check returns

| Field ([CON §2.8](01-contracts.spec.md)) | Rule |
|---|---|
| `result` | `PASS`, `MAYBE` or `FAIL`. When `findings` are given the engine uses the worse of `result` and the worst finding, and logs a mismatch |
| `findings[]` | One per checked requirement: `criterion` (id, optional), `status` (`pass`, `maybe`, `fail`, `n_a`), `place` (path, path and line, or field), `fix` (one line), `message` (one line). `n_a` needs a `message` saying why the rule cannot apply in this repository |
| `facts` | At most 20 entries, slug keys, values ≤ 200 chars, scrubbed. Stored for the unit (and item) on this visit; cleared with the unit's artifacts on a trip back to or past it ([BUD-B4](08-budgets-and-failures.spec.md)) |
| `runs[]` | The `CommandRun` records of this check, added by the engine |
| `evidence` | Bounded text for the judge, as today |
| `environmental` | The environment, not the work, failed (no interpreter, command refused, program missing); escalates with no judge and no retry ([BUD §2.2](08-budgets-and-failures.spec.md)) |

Facts are read by later checks (`ctx.facts`), by routes and switches, by the finalizer ([FIN](78-finalizer-contract.spec.md)), by the `facts` verb and by the run detail document. A step prompt never sees them.

### 2.5 The check preview

A step declares `self_check: true` ([CON §2.1](01-contracts.spec.md) `StepSpec`) on a unit whose gate has a check. Then:

| Part | Behaviour |
|---|---|
| Grant | The engine adds one command to the step's commands block, `tempergraph self-check <ticket>`, where the ticket is random and names thread, unit, item and attempt. It is granted as a command prefix on every executor (an allow rule on `claude` and `agent-sdk`, the tool host on `messages-api`, `command(tempergraph self-check)` on `antigravity`), even when the step declares no `shell` |
| Prompt | A fixed section "Check your work before you end" names the command and says it reports what the gate's check would find |
| Run | The verb runs the unit's check on the current workspace in the check worker with `preview = true`; it prints the result and the findings (status, criterion, place, fix, message) and at most 2,000 chars of evidence |
| Never | It writes no verdict, fact, artifact or state, runs no judge, and spends no budget; it is not the gate's check, which always runs after the session |
| Limit | `self_check_limit` per attempt (default 3); the next call prints that the limit is reached and exits 2 |
| Reuse | A preview's command runs are stored for reuse, so the gate's own check after the session reuses them when the tree has not changed |
| Record | One `self_check` run event per call: unit, item, attempt, result, finding counts, duration |

### 2.6 The check worker and its limit

A check runs in a child engine process (the check worker) that receives the context as a document on standard input, like the library executors' workers ([ADR-0019](../adr/0019-in-process-executors-run-in-a-worker-process.adr.md)). `GateSpec.check_timeout_s` (default 1800 s) bounds the whole check; at the limit plus 30 s the engine ends the worker and its process tree. The document carries the engine's import path and the map of workflow packages' private import names to their folders ([PKG §2.3](88-workflow-package.spec.md)), so the worker imports the check by its reference alone.

## 3. Behaviours

**CHK-B1 Mechanical failure costs no judge.** Given a gate whose criterion `reading-sets` is `mechanical` and whose check returns FAIL with finding `{criterion: reading-sets, place: "plan.md:212", fix: "add the line range of parse_row"}`, when the judge node runs, then no judge session starts, and the retry prompt lists that finding under the rejection reason with its place and fix.

**CHK-B2 Mechanical pass is given.** Given the same criterion and a check that passes it, when the judge runs, then the judge brief shows the criterion with the check's finding and the fixed sentence that the check verified it and its evidence is to be taken as given; the judge grades only what the check does not cover.

**CHK-B3 Not applicable.** Given a repository with no plan folder and a check finding `{criterion: plan-search, status: n_a, message: "no plan folder"}`, when the judge grades, then the criterion is shown as N/A with that reason, and an N/A from the judge on it counts as reasoned ([JDG §2.2](05-judge-and-verdict.spec.md)).

**CHK-B4 A test run.** Given a code gate's check that resolves the plan's three verification items and runs them with a 1,800 s budget:

| Item | Resolve | Run | Effect on the check |
|---|---|---|---|
| `python -m pytest tests/unit` | ok | exit 0 | pass |
| `go test ./...` (documented in the project-context file) | ok, `documented` | exit 1 | fail |
| `make lint && make docs` | refused: shell metacharacter | not run | finding `maybe`, "not run: shell metacharacter" |
| `python -m pytest tests/e2e` | ok | killed at the limit | `finished: false`, `timed_out`; the check decides (temperspec: FAIL "timed out after N s") |
| any command | ok | `deadline_s < min_start_s` | `not_started`; the check decides |

**CHK-B5 Reuse after a judge-only failure.** Given a code gate whose check ran a 25-minute suite with `reuse=True` and passed, and whose judge sent the step back, when the next attempt changes nothing in the tree and the check runs again, then the suite is not run, the run is `reused: true`, and the evidence says so; when one file changed, it runs again.

| Earlier run | Stored | Reused on the same key |
|---|---|---|
| exit 0 | yes | yes |
| exit 1 (tests failed) | yes | yes |
| exit 4, listed in `no_reuse_exit_codes` | no | no |
| killed at the limit | no | no |

**CHK-B6 A fact for a later gate.** Given a code gate's check that records `facts: {code_head: <commit>}`, when the release gate's check runs, then `ctx.facts["code"]["code_head"]` holds that commit; after a trip back to `code`, it is absent until the code gate records it again.

**CHK-B7 Preview inside the attempt.** Given an expand step with `self_check: true`, when its session runs `tempergraph self-check <ticket>` twice and edits the plan between the calls, then both calls print findings, neither changes state or budgets, the gate's check runs after the session as usual, and a fourth call in the same attempt is refused with exit 2.

**CHK-B8 Environment evidence.** Given a worktree with no virtual environment and a resolver that picks the main checkout's interpreter, when the check runs a test command, then `program_path` reads `<main>/.venv/bin/python` and the judge and the run detail document show it.

**CHK-B9 Same on every executor.** Given the same workflow with its steps on `claude` and on `antigravity`, when the same gate's check runs on the same workspace, then the context, the runs and the result are identical: checks never run through an executor.

## 4. Error conditions

| Condition | Result |
|---|---|
| The check raises | Check FAIL with the exception type only, `environmental: false`; a retry is spent (a raising check is a workflow fault for the self-improvement loop, [SIL](16-self-improvement.spec.md)) |
| The check worker passes its limit | Worker and tree ended; check FAIL with `environmental: true`; escalates |
| A finding names a criterion id the gate does not have | The finding is kept without its id; a validation-time fixture catches it ([EVS](51-eval-suites.spec.md)) |
| More than 20 facts, or a value over 200 chars | Extra entries dropped, values clipped, counted on the check record |
| `read_text` or a run's `cwd` outside the workspace | Refused; the check sees a `CommandRefusal` or an error value, never a path outside |
| `self-check` with an unknown, expired or other attempt's ticket | Exit 2, nothing run |
| `mechanical: true` on a gate with no check | Validation error ([WFM §2.1](02-workflow-model.spec.md)) |

## 5. Design notes

- Reuse extends the per-thread cache idea of [ADR-0067](../adr/0067-cache-only-model-free-script-results-per-thread.adr.md) to check commands: model-free, keyed by the tree, never a run that did not finish.
- A check worker costs about one interpreter start per gate. It is the only way to bound a check whose own code hangs, and it keeps workflow code off the engine's main thread.
- The preview is an engine command, not a resumed session: a resumed retry was measured dearer than a fresh one ([R-001 F20](../research/R-001-claude-code-cli-headless.rsrch.md)), while a preview lets the session repair a structural miss before it ends at no judge cost ([ADR-0077](../adr/0077-a-step-previews-its-own-check-in-the-attempt.adr.md)).
- Which commands a temperspec gate runs, how it splits a suite, how many workers it asks pytest for and how it reads the plan are temperspec's design; nothing here names a tool.
- **As built (R2-T7).** `run/selfcheck.py` keeps the ticket as `<state root>/tickets/<ticket>.json` for the length of the session and removes it after; the verb is `tempergraph self-check <ticket>` and only the `claude` grant ships (`Bash(<command>)` allow rule), the other executors with their own release. The preview sees the artifacts state held when the attempt began, so an artifact the session is still writing is read from the workspace by the check itself. `self_check_limit` is a run setting ([RST §2.2](80-run-settings-and-overrides.spec.md)). A repository declares its own commands in `tempergraph.commands.json` at its root (`{"commands": ["<prefix>", …]}`); a step or check that lists `@repository` among its commands gets them, each marked `documented`, and a missing or malformed file declares none. `GitFacts.pushed` is true when the head commit is on a remote-tracking ref.

## 6. Acceptance criteria

- [ ] CHK-AC-1 Every row of the CHK-B4 and CHK-B5 tables holds in an offline test with a real process tree and a scratch git repository.
- [ ] CHK-AC-2 A check that runs a child which outlives its parent is ended at the limit; no process of the tree remains (Linux, macOS, Windows).
- [ ] CHK-AC-3 `resolve_command` gives the same answer to a check, the tool host and the commands block for every fixture command (one shared function, source-scan test).
- [ ] CHK-AC-4 No `CommandRun.tail` or `program_path` in any record contains the workspace, main checkout or home path (canary test).
- [ ] CHK-AC-5 A FAIL with findings renders every finding's criterion, place and fix in the retry prompt, and starts no judge session.
- [x] CHK-AC-6 `self-check` writes no state, verdict, fact or budget change (state digest before and after), and its runs are reused by the gate's check on an unchanged tree.
- [ ] CHK-AC-7 Facts survive a resume and are cleared by a trip back exactly as artifacts are.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Should the check worker be kept warm across gates of one run to save the interpreter start? Measure first. | Engine implementer | No: one worker per check |

## References

