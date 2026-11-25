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

From run i21 on, the launch shell also exports `ENABLE_CLAUDEAI_MCP_SERVERS=false`, which keeps the account's connectors out of every session until #21 is merged and installed (a step session then starts at about 9,000 tokens instead of 174,000).

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
| 2a | i21 | #21 | Step and judge sessions are offered no MCP server they do not declare (the account's connectors cost about 165k tokens a step session) | running | temperspec/i21 | | Biggest cost lever found; probe facts are in the request |
| 2b | i144 | #144 | Package tests run directly write the real machine index and stats | running | temperspec/i144 | | Found in this batch |
| 2c | i148 | #148, #149 | The gates of the phases arm stop pausing for a person: a phase's gate grades the phase's own changes; `ts-exp-opened` counts every session of the visit | queued | | | Next in temperspec's files; before the gate split, which adds phases |
| 3 | i134a | #134 | Split the discovery gate (extract pass, write pass) | queued | | | L: first of two runs |
| 4 | i134b | #134 | Code step: the join and the quick lane get prompts of their own | queued | | | L: second of two runs |
| 5 | i114 | #114, #117 | Loop findings: a judge that passes without opening a changed path; the phase check failing | queued | | | Triage the evidence first |
| 6 | i123 | #123 | Loop reads the person's review of a run's pull request as a later outcome signal | running | temperspec/i123 | | needs: spec; spec comes first in the run |
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
