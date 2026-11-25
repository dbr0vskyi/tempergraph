# Issue queue of this batch (temporary; delete before merge)

One branch, `claude/issue-queue-2026-11-25`, and one pull request hold every change of the batch. Each issue is built by one temperspec run in its own worktree and branch (`tg/temperspec/<task id>`), based on the head of the batch branch; a finished run's branch is merged into the batch branch. This folder is the hand-over: a session that dies is picked up from here.

- `QUEUE.md` (this file): the order, the state of each item, and how to carry on.
- `state.json`: the same state for a program, with thread ids, branches and cost.
- `tasks/<task id>.md`: the exact request each run was started with.
- `observations.md`: what the runs showed about tempergraph, temperspec and the improvement loop.

## How a run is started

On the owner's machine the engine is installed from this checkout (`plugins/tempergraph/bin/tempergraph install`, shim `~/.tempergraph/bin/tempergraph`), temperspec is registered from `plugins/temperspec-tgraph` of this checkout, and a Python 3.12 environment with the engine's `dev` extra is in `.venv/` at the repository root (the suite imports the `src` beside it, so one environment serves every worktree).

```sh
export PATH="$PWD/.venv/bin:$HOME/.tempergraph/bin:$PATH"
git checkout claude/issue-queue-2026-11-25 && git pull
tempergraph run temperspec --check --task-id <id> --worktree --worktree-base head --carry --as-agent batch-queue/tasks/<id>.md
tempergraph run temperspec --json  --task-id <id> --worktree --worktree-base head --carry --as-agent batch-queue/tasks/<id>.md
```

In a cloud session: `cd plugins/tempergraph/engine && python -m pip install -e '.[dev]'`, then `tempergraph workflows register plugins/temperspec-tgraph`, then the same commands. A run started with `--carry` keeps its scrubbed state on a branch: `tempergraph carry pull temperspec <task id>`, then `tempergraph resume temperspec <task id>`. When the state cannot be pulled, start the item again under a new task id (`<id>b`) from the batch branch; the finished steps of the old run are on `tg/temperspec/<id>` if it was pushed.

## After a run ends

1. Exit 0: `git merge --no-ff tg/temperspec/<id>` into the batch branch, run the suite, ruff and mypy from `plugins/tempergraph/engine/`, push.
2. Update the local engine and workflow from the batch branch: `plugins/tempergraph/bin/tempergraph update --json`, then `tempergraph workflows register plugins/temperspec-tgraph`.
3. Post the `result` comment on the issue (cost, outcome), update the table and `state.json` here, add what the run showed to `observations.md`, commit and push.
4. Exit 3 (pause): answer what the local docs answer; a low-confidence owner decision goes to the owner as a `question` comment and the run continues on its default.

## Queue

State words: `queued`, `running`, `paused`, `merged`, `failed`, `skipped`.

| # | Task id | Issue | What | State | Thread | Cost USD | Note |
|---|---|---|---|---|---|---|---|
| 1 | i71 | #71 (and #51) | Code step marks a phase's rows in one edit; the run is also the real run of TS-L2 with a signed-in `gh` | queued | | | |
| 2 | i7 | #7 | Review cap floor: one review of the most signalled session | queued | | | |
| 3 | i134a | #134 | Split the discovery gate (extract pass, write pass) | queued | | | L: first of two runs |
| 4 | i134b | #134 | Code step: the join and the quick lane get prompts of their own | queued | | | L: second of two runs |
| 5 | i114 | #114, #117 | Loop findings: a judge that passes without opening a changed path; the phase check failing | queued | | | Triage the evidence first |
| 6 | i123 | #123 | Loop reads the person's review of a run's pull request as a later outcome signal | queued | | | needs: spec; spec comes first in the run |
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
