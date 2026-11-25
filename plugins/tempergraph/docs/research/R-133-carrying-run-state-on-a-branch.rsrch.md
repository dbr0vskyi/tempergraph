# R-133 Carrying a run's state on a git branch, and leaving no trace

## Problem statement

The owner decided on 2026-11-20 that CI pipelines go to a later release, and proposed a stopgap: "temporary we can push .tempergraph folder from project to branch which would have state/sqlite etc, and when workflow will be fully done we can remove the folder to leave no traces." Today a paused run resumes only on the machine that holds its state root ([WSP-B8, WSP-B9, WSP-B11](../specs/workspace-and-concurrency.spec.md)); the state root is gitignored by its own `.gitignore` ([LOS-B7, LOS-B8, LOS-B9](../specs/local-observability-store.spec.md)).

The questions: what of the state root a resume on another machine needs, what must never leave the machine, where on git it should live, how two machines are kept from driving one run, and how "no traces" can actually hold.

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S3 | This design: LOS-B7, LOS-B8, LOS-B9 layout (what each file holds, "local only" marks), SEC-B8 to SEC-B11 and OVR-B11 (published artefacts carry metadata only), DUR (checkpoints, locks, thread states), WTR-B18 (`WorkspaceRecord` paths), MIG (layout and checkpoint format versions), RRN (feedback and rulings) | Design set | [specs](../specs/overview.spec.md) |
| S4 | git documentation: an orphan branch (`git switch --orphan`) shares no history with other branches; `git push origin --delete <branch>` removes a remote branch; a commit stays reachable from a branch that contains it until that history is rewritten; a squash merge adds one commit holding the branch's final tree only | Tool documentation | [git-switch](https://git-scm.com/docs/git-switch), [git-push](https://git-scm.com/docs/git-push), [git-merge](https://git-scm.com/docs/git-merge) |
| S5 | LangGraph's SQLite checkpointer stores checkpoints and pending writes in tables keyed by `thread_id`, so one thread's rows can be copied apart | Library documentation | [langgraph-checkpoint-sqlite](https://pypi.org/project/langgraph-checkpoint-sqlite/) |

## Key findings

### F1 A CI path needs the same carrying `inferred`

A run in CI pauses on one runner and resumes on another, so a CI path saves a paused run's state on its branch, resumes it from there, and fails a required check while a branch still carries run state. It needs two engine changes: re-derive a worktree path recorded on another machine, and keep run state out of diff statistics.

### F2 A resume elsewhere needs a small, thread-scoped part of the state root `confirmed`

From LOS-B7, LOS-B8, LOS-B9 (S3):

| Needed to resume | Not needed, or must stay local |
|---|---|
| The thread's checkpoints and pending writes (copied out of `checkpoints/<workflow>.sqlite`, which holds every thread of that workflow, S3, S5) | Other threads' checkpoints in the same database |
| `runs/<workflow>/<task_id>/run.jsonl`, `findings.json`, `engine.json`, `lineage.json`, `exit.json` | `sessions/*/raw.jsonl`, `stderr.log`, `output/` and `evidence/prompts/` (full transcripts and prompts; marked local only) |
| `evidence/` request, outputs and feedback files the checkpoint points to | `scratch/` (session homes, private MCP configs), `config/` (operator config, may hold sink credentials), `locks/` |
| The thread's ledger rows, for reports on the other machine | `ledger.jsonl` of other threads, `authoring/`, `upgrades/`, `backups/`, `engine/` code logs |

Copying the whole folder, as the request literally reads, would publish transcripts, prompts, other runs and operator config: a breach of C9 and of the "local only" marks. The thread-scoped subset holds what a resume reads.

### F3 The subset still holds a person's words `confirmed`

Checkpoints carry feedback, rulings and answers verbatim (RRN), and artifacts may quote repository content. On a private repository this is the same exposure as the work itself; on a public one it is not acceptable. The engine cannot tell a private remote from a public one without a network call, so carrying must be an explicit opt-in per run or per workflow, scrubbed by the same scrubber as the run log (SEC-B8 to SEC-B11).

### F4 "No traces" depends on where the state is committed `confirmed`

| Where | After the run finishes | Trace left |
|---|---|---|
| Commits on the run's work branch, then a removal commit | The folder is gone from the branch's tip | The state stays in the branch's history and in its pull request until the branch is squash-merged or rewritten (S4) |
| Same, squash-merged | Main gets the final tree only | None on main; the work branch's history keeps it until deleted |
| **A separate state branch per run** (orphan, e.g. `tempergraph/state/<workflow>/<task_id>`) | The engine deletes the branch locally and on the remote | None reachable: the work branch never held it |

A separate branch also keeps state out of the work branch's diff statistics, the second engine change of F1, and out of the pull request a person reviews.

### F5 Two machines must not drive one run `inferred`

A pushed state is a copy; two machines resuming it fork the thread. A **lease** in the carried folder, written when a machine takes the run and cleared when that machine pauses or exits, with the pushing machine's id, lets a pull refuse a leased state unless the person forces it. Git's own non-fast-forward rejection on push catches the race that remains.

### F6 What changes on the other machine `confirmed`

`WorkspaceRecord` holds absolute paths (WTR-B18), and the checkpoint database format and layout carry versions (MIG). A pull must re-derive the worktree path for this machine from the recorded branch and the root rule, refuse a checkpoint format newer than the running engine, and re-attach the worktree to the branch, as resume after a deleted worktree already does.

## Conclusions

1. Carry a thread-scoped, scrubbed subset, never the whole state root: the thread's checkpoints, its run folder minus transcripts and prompts, its evidence and its ledger rows, with a manifest.
2. Commit it on a separate state branch per run, push it, and delete that branch locally and on the remote when the thread finishes; the work branch never holds state.
3. Opt in per workflow or run; scrub like the run log; never on by default.
4. A lease and git's push rejection keep one machine driving a run at a time.
5. A pull re-derives local paths and checks format versions before a resume.
6. This is the state-on-branch half of a CI path (F1); the pipeline itself waits for a later release.

## Open questions

| Question | Who answers | Default until answered |
|---|---|---|
| Separate state branch, or the work branch as first proposed? | Owner: separate state branch (decided 2026-11-21) | Separate state branch |
| Carry automatically at every pause, or only by a verb? | Owner | At every pause and exit when the setting is on, and by the `state push` verb |
| Keep the carried run log's text fields, or only metadata? | Owner | Keep the run log as written (already scrubbed and clipped); drop transcripts and prompts |
