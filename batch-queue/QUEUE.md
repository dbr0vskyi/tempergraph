# Issue queue of this batch (temporary; delete before merge)

One branch, `claude/issue-queue-2026-11-25`, and one pull request (#138) hold every change of the batch. Each issue is built by one temperspec run in its own worktree and branch (`tg/temperspec/<task id>`), based on the head of the batch branch; a finished run's branch is merged into the batch branch. This folder is the hand-over: a session that dies is picked up from here.

- `QUEUE.md` (this file): the order, the state of each item, and how to carry on.
- `state.json`: the same state for a program, with thread ids, branches and cost.
- `tasks/<task id>.md`: the exact request each run was started with.
- `observations.md`: what the runs showed about tempergraph, temperspec and the improvement loop.

## How a run is started

On the owner's machine the engine is installed from this checkout (`plugins/tempergraph/bin/tempergraph install`, shim `~/.tempergraph/bin/tempergraph`), temperspec is registered from `plugins/temperspec-tgraph` of this checkout, and a Python 3.12 environment with the engine's `dev` extra is in `.venv/` at the repository root (the suite imports the `src` beside it, so one environment serves every worktree). That environment's editable install also puts a `tempergraph` in `.venv/bin` that runs the checkout's working tree: with `.venv/bin` first on `PATH` a run uses that one, not the installed engine. Runs i71, i7 and i141 were started that way; later ones use the shim.

```sh
export PATH="$HOME/.tempergraph/bin:$PWD/.venv/bin:$PATH"   # the shim first: `.venv/bin` holds a `tempergraph` of its own
git checkout claude/issue-queue-2026-11-25 && git pull
tempergraph run temperspec --check --task-id <id> --worktree --worktree-base head --carry --as-agent batch-queue/tasks/<id>.md
tempergraph run temperspec --json  --task-id <id> --worktree --worktree-base head --carry --as-agent batch-queue/tasks/<id>.md
```

Runs i21 to i144b were started with `ENABLE_CLAUDEAI_MCP_SERVERS=false` exported in the launch shell, a stopgap for the account's connectors. #21 is merged and installed (build `0.2.0-da9985a63404`), so a run started from now on needs no such variable; check that a step session's first turns stay near 10,000 tokens.

In a cloud session: `cd plugins/tempergraph/engine && python -m pip install -e '.[dev]'`, then `tempergraph workflows register plugins/temperspec-tgraph`, then the same commands. A run started with `--carry` keeps its scrubbed state on a branch: `tempergraph carry pull temperspec <task id>`, then `tempergraph resume temperspec <task id>`. When the state cannot be pulled, start the item again under a new task id (`<id>b`) from the batch branch; the finished steps of the old run are on `tg/temperspec/<id>` if it was pushed.

**At most three runs at once** (the owner, 2026-11-25): count live threads with `tempergraph status` before starting one; a rerun counts.

## After a run ends

1. Exit 0: `git merge --no-ff tg/temperspec/<id>` into the batch branch, run the suite, ruff and mypy from `plugins/tempergraph/engine/`, push.
2. Update the local engine and workflow from the batch branch: `plugins/tempergraph/bin/tempergraph update --json`, then `tempergraph workflows register plugins/temperspec-tgraph`.
3. When all work for the run is done (reviewed, any rerun merged, the branch an ancestor of the batch branch), remove its worktree: `tempergraph worktree prune --thread <thread> --apply --as-agent` (the owner, 2026-11-25). The branch stays.
4. Post the `result` comment on the issue (cost, outcome), update the table and `state.json` here, add what the run showed to `observations.md`, commit and push.
5. Exit 3 (pause): answer what the local docs answer; a low-confidence owner decision goes to the owner as a `question` comment and the run continues on its default.

## Built by hand

- #139: a run's commit failed on git 2.39 when the repository ignores `.tempergraph/`; no run could start without the fix (commit `19ac3d42`).
- #143: the last stage never opened the pull request, because the engine refuses the absolute path of its description file (commit `5e924254`).

## Queue

State words: `queued`, `running`, `paused`, `merged`, `failed`, `skipped`.

| # | Task id | Issue | What | State | Thread | Cost USD | Note |
|---|---|---|---|---|---|---|---|
| 1 | i71 | #71 (and #51) | Code step marks a phase's rows in one edit; the run is also the real run of TS-L2 with a signed-in `gh` | merged | temperspec/i71 | 11.06 | Outcome met; last stage `opened` draft pull request #146; not hands-free (#139 at `prepare`, a `.claude/` edit denied at `code`); review: no blocker, four small follow-ups listed on #71 |
| 2 | i7 | #7 | Review cap floor: one review of the most signalled session | merged | temperspec/i7 | 8.03 | Outcome met, 21 min, one pause (G3 answered with its default); last stage `pushed`, no pull request (#143) |
| 2a | i21 | #21 | Step and judge sessions are offered no MCP server they do not declare (the account's connectors cost about 165k tokens a step session) | merged | temperspec/i21 | 14.12 | Outcome met; review: launch paths correct, nothing blocking, five follow-ups (request `tasks/i21b.md`); installed as the local engine (build `0.2.0-da9985a63404`) |
| 2a' | i21b | #165 | The MCP isolation's live probe measures the leak, and its runbook row records what was run | queued | | | Must land before the pull request is ready: the runbook says `passed` for a test that never ran |
| 2b | i144, i144b | #144 | Package tests run directly write the real machine index and stats | merged | temperspec/i144 (stopped), temperspec/i144b | 9.69 + 7.80 | Merge `766e99de`. First run stopped at `attempt_cap` and could not resume (#152), its rerun crashed (#163); a review of its branch found a blocker; `i144b` ran on top of that branch with the review as its task (`opened` #164); re-review: merge with follow-ups (#167). The shared `.venv` is NOT reinstalled yet, so the plugin is not active on this machine |
| 2c | i148 | #148, #149 | The gates of the phases arm stop pausing for a person: a phase's gate grades the phase's own changes; `ts-exp-opened` counts every session of the visit | stopped | temperspec/i148 | 12.09 so far | Stopped by request at 17:39 on 2026-11-25 after phase `p1` passed; branch pushed (head `de5290b1`), worktree kept. Continue: `tempergraph resume temperspec i148 --decision retry` |
| 3 | i134a | #134 | Split the discovery gate (extract pass, write pass) | queued | | | L: first of two runs |
| 4 | i134b | #134 | Code step: the join and the quick lane get prompts of their own | queued | | | L: second of two runs |
| 5 | i114 | #114, #117 | Loop findings: a judge that passes without opening a changed path; the phase check failing | queued | | | Triage the evidence first |
| 6 | i123 | #123 | Loop reads the person's review of a run's pull request as a later outcome signal | stopped | temperspec/i123 | 24.15 so far | Stopped by request at 17:39 on 2026-11-25. Seven phases, code and join passed; the outcome gate sent it back to the plan (`ts-traced`: FIN-AC1, OUT-AC4, SIL-AC6, SIL-AC7 named by no test, #151) and the plan passed again. Branch pushed (head `96c4f980`), worktree kept. Continue: `tempergraph resume temperspec i123 --decision retry`, or review the branch as it stands |
| 6a | i141 | #141 | Monitor finds the engine at its default shim path when it is not on PATH | merged | temperspec/i141, rerun temperspec/i141~r1 | 23.22 | Review blocked the first run; rerun from `plan` with the review as feedback fixed the blocker (`opened` #147); re-review: merge with follow-ups, which are in `tasks/i145.md` |
| 6b | i145 | #142, #145 (and the rest of #141) | Monitor: a sign of life in a live row; rows of other state roots named and folded; the engine lookup recovers after not-found and a timeout | queued | | | Next in the monitor's files |
| 7 | i62 | #62 | Model-free drift check for pre-commit and CI | queued | | | |
| 8 | i103 | #103 | Commits and the draft pull request name the run | queued | | | Writes the format directly (#94 not built) |
| 9 | i130 | #130 | Score setup's extraction on a fixture repository | queued | | | Needs one live setup run |
| 10 | i104 | #104 | Security scanning at the code gate | queued | | | |
| 11 | i32 | #32 | Move PKG-B8 and AUT-B8 out of the engine specs | queued | | | |
| 12 | i76 | #76 | Repository setup as a sub-workflow | queued | | | |
| 13 | i136 | #136 | Component reading step checks the extraction rule was opened | queued | | | |
| 14 | i135 | #135 | Named text parts included by prompts and briefs | queued | | | |
| 15 | i22 | #22 | Run log records the layer each timeout came from | queued | | | |
| 16 | i10 | #10 | Pipeline stage and `promote-check --to pipeline` | queued | | | L |
| 17 | i14 | #14 | Complexity switch in an example, guides for release 3 | queued | | | |

## Not in the queue, and why

- Owner's own decision: #52, #11, #12, #34, #35, #37, #107, #108.
- Blocked on another issue: #13, #15, #33, #41, #49, #66, #77, #80, #83, #84, #87, #89, #90, #91, #93, #110, #111.
- Live checks that need a scratch repository, a desktop surface or Windows: #40 (watched while the runs of this batch file loop issues through the real `gh`), #42 to #47, #50.
- Release 4 tracks and `release: later` features with no priority above P3 come after the list above.

## Notes on the drafted requests (sub-agent, 2026-11-25)

- `i10.md` is a first slice of #10 (the `--to pipeline` check, the stamp, the stage of a run); the regressed watch and the `attention` listing need a second request.
- `i76.md`: the issue is thin (no "Done when"); its three criteria come from the summary and backlog row B11, and the docs-only workflow is left out. Read it against the issue before starting.
- `i32.md` leaves out the literal "no engine test names a workflow package" (about 20 engine tests use `release-notes` as a fixture name); it could run as `docs only`.
- `i130.md`, `i14.md`: the live setup run and the pull-request gate guide are left out.

## Where the session stopped (2026-11-25, 17:50 local, at the owner's word; the pull request stays a draft)

Nothing is running. Reported spend of the runs: about 117 USD (`tempergraph status`).

| State | Items |
|---|---|
| Merged into this branch | i7 (#7), i71 (#71), i141 with its rerun (#141), i21 (#21), i144 with i144b (#144); by hand #139 and #143 |
| Stopped, to continue | i123 (#123), i148 (#148, #149): the commands are in the table above; their worktrees and pushed branches are kept |
| Queued with a request file | i21b (#165), i145 (#142, #145 and the rest of #141), i134a and i134b (#134), i62, i103, i104, i130, i32, i76, i136, i135, i22, i10 (first slice), i14 |
| Queued without a request file | i114 (#114, #117): read the evidence of #148 and of the runs' `judge_unread_pass` findings first |
| Filed today and not queued | #140, #150 to #163, #166, #167, #169 to #176 (start with #150 and #153, which each cost a run a trip back or a stop, then #171, #170 and #169, which decide whether the loop files anything, and #173, the review unit) |

CI passed on `30e2e8f3` (suite, ruff and mypy on Python 3.11 and 3.12), which holds every merge of the batch. Every push cancels the CI run before it, so leave about twenty minutes between pushes when a CI result is wanted.

Before the pull request is ready:

1. Run i21b (#165): the runbook must not say `passed` for a test that never ran. Then the operator runs the live probe.
2. Run i145: the merged monitor fix marks the engine as not installed for the whole session after one timed-out verb.
3. Finish or review i123 and i148.
4. Restamp temperspec (`tempergraph author verify plugins/temperspec-tgraph`, model-free rungs): `stamp.json` is stale after #71, #143 and #139.
5. Reinstall the shared environment from this branch (`uv pip install --python .venv/bin/python -e 'plugins/tempergraph/engine[dev]'`) so the test isolation of #144 is active, then clean the machine index: `tempergraph stats forget --check`, then without `--check` (106 pytest folders and about 1,260 rows; back up `~/.tempergraph/index.json` and `~/.tempergraph/stats/` first).
6. Decide where the runs' notes live: they are at the repository root (`docs/plans/i*.plan.md`, `docs/tasks/i*`), where `CONTRIBUTING.md` asks for the owning package's `docs/` (#159).
7. Write the TS-L2 row and the measured cost per step into temperspec's docs (#51).
8. Delete this folder.

Owner decisions taken by the agent, to confirm: #7 G3 (in stable mode the review-cap floor is limited to what the daily cap leaves).

## Second session (2026-11-25 evening to 2026-11-26, on the Raspberry Pi; the owner is away, the agent orchestrates)

The table above is as the first session left it; this section is the newer truth until the table is rewritten.

Owner's words for this session: at most three runs at once, fewer when the machine is loaded; **runs open no pull request of their own** (#184 and #164 are closed; everything is in #138); **a finished run is merged into this branch straight away**, its independent review follows the merge and its findings become issues or a follow-up run; the agent delegates and does not build.

### Launching on this machine

`~/tg-runs/launch.sh <name> <tempergraph arguments>` starts a run detached (log and exit code in `~/tg-runs/`). It puts `~/tg-runs/bin` first on `PATH` (a `gh` shim: `pr create` is refused, and **every write through `gh api` is refused, which holds the loop's filing**), and sets `TMPDIR=/var/tmp/tg-runs` (on disk, outside the home folder: `/tmp` is an 8 GB memory volume that three suites fill, and a temporary folder under the home folder fails `tests/test_outside_git.py`). Never export `TEMPERGRAPH_AUTONOMY` for a run whose base is older than `f15cfa1d`. `~/tg-runs/watch.sh` waits for a run's exit and removes old pytest folders. A stopped thread takes a plain `resume`; a thread that a stale stop request ended as `stopped` takes `--decision retry`. Python 3.13, engine build `0.2.0-3d01d61d4214`.

A restamp in a worktree: `PATH=<repo>/.venv/bin:$PATH PYTHONPATH=plugins/tempergraph/engine/src TEMPERGRAPH_HOME=<a throwaway folder> python -m tempergraph author verify plugins/temperspec-tgraph` (the name is registered from the main checkout, so the register rung needs another home); diagrams: `python -m tempergraph upgrade-check plugins/<package> --stamp`.

### State

| Item | State | Cost USD | Note |
|---|---|---|---|
| i123 (#123) | merged `525cf6ad` | 28.85 | Review blocked it; i123b repaired it |
| i123b (#123) | merged `ade5bd09` | 18.11 | Review: follow-ups (#193). Also #186, #187, #188 from the first review |
| i21b (#165) | merged `feb20fe3` | 13.35 | Stopped at the outcome gate's trip back. Review: follow-ups (#190). The operator's live probe (L-43) is still to run |
| i148 (#148, #149) | merged `b0dbb317` | 16.5 | Stopped at the code gate (#185, #191). Review: follow-ups (#192) |
| i171 (#171) | merged `b546268e` | 9.08 | One owner question. Review: criteria met, **filing held** (`tasks/i171.review.md`); #194, #195, #196 |
| i150 (#150) | merged `3bce7089` | 9.49 | One pause (a restamp row). Review: follow-ups (#197) |
| i169 (#169) | merged `aca69138` | 10.11 | No touch of a person. Review: follow-ups (#201) |
| i153 (#153) | merged `a6f86113` | 18.23 | Stopped at the outcome gate's trip back. Review: follow-ups (#202); recognition of a real refusal unproven live |
| i170 (#170) | merged `fba4993c` | 14.40 | Review running |
| i173 (#173) | running | | The review unit, without its live run |
| i172 (#172, first slice) | running | | Cause codes |
| i171b (#171) | running | | Makes the pattern rule safe to switch on (`tasks/i171b.md`) |
| i114 (#114, #117) | queued | | Last; cut to the #117 half unless #201 lands first |
| By hand (sub-agents) | on the branch | | #185 (`a880075b`, `685fc407`, `f15cfa1d`), #191 (`3726bc35`) |
| Research | #189 | | Heavy commands apart from the session that needs them; the draft note is a comment on the issue |

**Order from here (owner, 2026-11-26: the loop first, so it can run on its own).** Requests are in `tasks/`. At most three at once; a wave starts when the runs it names are merged.

1. In the first free slot: `i205` with its criteria 7 to 9 cut (the attempt cap and the stale stop request; engine only).
2. When i172 and i171b are merged: `i170b` (the judge's facts about pauses) beside `i201` (judge read counts; engine only).
3. When i173 is merged: `i203a` (stamps and diagrams regenerated by a script step, in a worktree too). Until it lands, **every run that changes a package pauses for the operator's stamp**; the requests `i204` and `i197a` say so.
4. When i203a is merged: `i197a` (the outcome gate pauses, and sends nothing back, for a fact no step can change) beside `i170c` (the outbox, the operator's reason).
5. Then `i204` (a judge that did not read is asked again once), alone among package requests.
6. Then `i203b` (the plan and expand checks refuse a row a session cannot build; a phase goes back to the plan), then `i114`.
7. `i205` part 3 (a stop by request records and files nothing) after i170c.

Do not run side by side: i203a with i203b or i197a; i203b with i204, i197a or i205; i205 part 3 with i171b.

After those, from the first session's table: i145, i134a, i134b, i62, i103, i130, i104, i32, i76, i136, i135, i22, i10, i14.

### Owner decisions taken by the agent, to confirm

1. i148 row 4.4: PHC-AC13 outranks the plan row (the early return of `code_check` runs no command).
2. i123 accepted at the outcome gate with two blockers open, then merged though its review blocked it (the owner's word: merge straight away); i123b repaired it.
3. #184 and #164 closed (runs open no pull request).
4. i123b: a lasting ruling for its phase gates (specs and notes changed before any phase are not counted against `ts-phs-scope`).
5. i171 G2: a count-met finding the friction judge did not answer stays `not_judged`.
6. i153: the rerun clause of plan row 1.3 moved to a phase 4 test row; the fix of `tests/test_workflow_packages.py` added to its phase 4.
7. i21b, i148, i153 stopped at a gate and merged as they stood (each gate's failures were environmental or a false finding).
8. **The loop's filing is held** on this machine. Three issues were filed before the hold took effect (#198, #199, #200, at the stop exit of i170); each has an operator note and is left for the owner's triage. Whether the loop may file unattended after i171b is the owner's.
9. #196 default: closing a loop issue as duplicate binds the cause to the target.

### Before the pull request is ready (added to the first session's list)

- Remove the `gh` shim's hold only after i171b and i170b are merged and reviewed. **Empty or review `.tempergraph/filing-outbox.jsonl` first**: the filings the shim refused are queued there (five creates and one comment on 2026-11-26 03:50, more with every exit), and the next filing that is not a dry run sends them all with no fresh dedup (`improve/filing.py:369-374`).
- The operator's live checks: L-43 (#165), a real usage-limit refusal (#202).
- Triage #198, #199, #200.
