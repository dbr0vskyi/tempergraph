---
title: Workspace and concurrency
type: component
status: review
prefix: WSP
adrs: [0014]
---

# Workspace and concurrency

## 1. Overview

Where a run's files live, how runs and writing units stay apart, and how many runs one machine drives. State lives outside the workspace; the workspace is disposable, the branch is not. This spec owns contracts C10 (paths resolve inside the workspace; the state root is the main checkout) and C11 (one graph per process).

## 2. Contract

| Concept | Definition |
|---|---|
| State root | `<main checkout>/.tempergraph/`, found from git's common directory, whatever directory the engine starts in. Holds checkpoints, run logs, locks, the ledger, batch folders and executor scratch (session homes, private MCP configs). Gitignored. |
| Workspace | The main checkout (`in_place`) or an engine-owned git worktree beside the repository on branch `tg/<workflow>/<task_id>`, fixed for the run and stored in state. |
| Writer worktree | A sibling worktree for a writer branch or writing map item, cut from the run's branch after a checkpoint commit. |
| Run lock | Per-thread OS file lock under the state root. |

```python
def state_root(start_dir: Path) -> Path: ...
def prepare_workspace(thread: str, mode: str, include: list[str], setup: list[list[str]]) -> Path: ...
def merge_writers(run_branch: str, writers: list[str]) -> MergeResult: ...   # --no-ff, declared order
```

### 2.1 Shapes

| Shape | Where it works | Kept apart or joined by |
|---|---|---|
| Parallel branch (default) | Run worktree, read-only | Head and status fingerprint before and after; a branch that changed it fails |
| Writer branch, writing map item | Own worktree | Merged without fast-forward at the join; a conflict resets the run branch and ends the step blocked with the conflicting paths, no model call |
| Sequential map | Run worktree, one item at a time | Nothing to merge; item k sees what earlier items left |
| Batch child | Own process and worktree | No join; one report from the children's logs |

## 3. Behaviours

**WSP-B1 Resume after worktree deletion.** Given a paused run whose worktree was deleted, when it resumes, then the engine re-attaches a worktree to the run's branch and continues; the state was never in the worktree.

**WSP-B2 Bootstrap of a worktree.** Given a workflow include list naming untracked local files and setup commands, when a worktree is created, then those files are copied and the commands run with list argv; a failed bootstrap removes the new worktree and branch.

**WSP-B3 Interpreter in a worktree.** Given a step whose declared command starts with `python`, when it runs in a worktree, then `python` resolves to the workspace's virtual environment, else the main checkout's, else the engine's, never PATH.

**WSP-B4 Batch.** Given a batch of 10 targets with K = 3, when it runs, then at most 3 child processes run at once (K ≤ 16, at most 50 runs), each in its own worktree; every paused child is listed with its exact resume command; the batch parent runs no graph.

**WSP-B5 Executor scratch stays in the state root.** Given a judge on either executor that needs a private config (an MCP config, an Antigravity session home), when it is created, then it lives under the state root's scratch folder with owner-only permissions and is removed after the session, never in the operating system's temp folder, which a sandboxed child may not read.

**WSP-B6 Writes in place.** Given a workflow with writing branches, when it is started `in_place`, then the start is refused with exit 2.

## 4. Error conditions

| Condition | Result |
|---|---|
| Two planned batch runs whose names collide after flattening | Batch refused (exit 2) |
| Merge conflict at a join | Run branch reset; step blocked; person decides |
| Not inside a git repository, workflow needs worktrees | Exit 2 |

## 5. Design notes

- One graph per process: branches of a fork are threads of one graph, so run-log and console writes hold locks; N runs are N processes sharing one checkpoint database per workflow ([ADR-0014](../adr/0014-sqlite-checkpointer.md)).
- The default concurrency of three is a guess for both executors: neither model gateway's concurrent-session limit was measured. It is marked projected.
- A merge is textual; two branches that merge cleanly but contradict each other are caught only by the join's judge or a check.
- Cleanup is never automatic: a list verb and a prune verb; branches are never deleted.

## 6. Acceptance criteria

- [ ] WSP-AC-1 The state root resolves to the main checkout from any worktree (test with nested worktrees).
- [ ] WSP-AC-2 A test session fails if any test leaves state in the real state root.
- [ ] WSP-AC-3 Each shape of §2.1 is tested with real git worktrees and scripted executors.
- [ ] WSP-AC-4 No executor scratch file outlives its session on any exit path.

## Open questions

None.

## References

