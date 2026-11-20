---
title: Workspace and concurrency
type: component
status: ready-for-implementation
prefix: WSP
adrs: [0014, 0100]
---

# Workspace and concurrency

## 1. Overview

Where a run's files live, how runs and writing units stay apart, and how many runs one machine drives. State lives outside the workspace; the workspace is disposable, the branch is not. The worktree itself (the `run.workspace` parameter, roots, bases, names, lifecycle, cleanup, executor pointing and the `worktree` verb) is [WTR](82-worktree-mode.spec.md). This spec owns contracts C10 (paths resolve inside the workspace; the state root is the main checkout) and C11 (one graph per process).

## 2. Contract

| Concept | Definition |
|---|---|
| State root | `<main checkout>/.tempergraph/`, found from git's common directory, whatever directory the engine starts in; outside git, §2.4. Holds checkpoints, run logs, locks, the ledger, batch folders, every session's logs, the engine's code log and executor scratch (session homes, private MCP configs), in the layout of [LOS §2.1](33-local-observability-store.spec.md). Gitignored. |
| Workspace | The main checkout (`in_place`) or an engine-owned git worktree on its own branch, chosen by `run.workspace` (`auto` by default), fixed for the run and stored in state as a `WorkspaceRecord` ([WTR §2.2, §2.4, §2.8](82-worktree-mode.spec.md)). |
| Writer worktree | A sibling worktree for a writer branch or writing map item, cut from the run's branch after a checkpoint commit, named by the suffix rule of [WTR §2.4](82-worktree-mode.spec.md). |
| Run lock | Per-thread OS file lock under the state root. |

```python
def state_root(start_dir: Path) -> Path: ...
def prepare_workspace(thread: str, plan: WorkspacePlan, decl: WorktreeDecl) -> WorkspaceRecord: ...   # WTR §2
def merge_writers(run_branch: str, writers: list[str]) -> MergeResult: ...   # --no-ff, declared order
```

### 2.1 Shapes

| Shape | Where it works | Kept apart or joined by |
|---|---|---|
| Parallel branch (default) | Run worktree, read-only | Head and status fingerprint before and after; a branch that changed it fails |
| Writer branch, writing map item | Own worktree | Merged without fast-forward at the join; a conflict resets the run branch and ends the step blocked with the conflicting paths, no model call |
| Sequential map | Run worktree, one item at a time | Nothing to merge; item k sees what earlier items left |
| Batch child | Own process and worktree | No join; one report from the children's logs |

### 2.2 Batch files

A batch is started from a **batch file**: JSON with `schema_version`, the workflow, K, and one entry per target (request, optional alias and label). The parent writes an append-only **batch event file** beside it, one JSON line per child event (`started`, `paused`, `finished`, `failed`, `throttled`), so a crashed parent can be re-run with the same file and skips targets whose thread already exists, and a monitor can follow the batch without reading checkpoints. A batch is a one-node map orchestration: its file and event file are the orchestration file and event log of [ORC](45-orchestration.spec.md) ([ADR-0038](../adr/0038-batch-is-a-one-node-orchestration.adr.md)).

### 2.3 Import roots

A workflow may declare `import_roots`: paths, relative to the workspace, that a check or a declared Python command puts first on its module path. In a worktree they resolve inside that worktree, so a test run there imports the branch's code and not the main checkout's or the engine's.

### 2.4 Outside a git repository (release 2)

A folder that is not inside a git repository may hold runs ([R-131](../research/R-131-running-outside-a-git-repository.rsrch.md), [ADR-0127](../adr/0127-outside-git-the-state-root-is-found-by-walk-up-and-the-guard-hashes-files.adr.md)). Inside a repository the rules above always apply.

| Rule | Outside git |
|---|---|
| State root | `--state-root` or `TEMPERGRAPH_STATE_ROOT`, else the nearest folder from the start dir upward holding `.tempergraph/manifest.json`, else `<start dir>/.tempergraph/`; never the home folder itself |
| Workspace | `in_place` only: `auto` resolves to it, `worktree` is refused with exit 2. A workflow that declares `workspace: none` runs in `<state root>/work/<workflow>/<task_id>/`, kept for the thread's life |
| Guard fingerprint | A manifest of `(path, size, mtime_ns)` of every file under the workspace except the state root, with a SHA-256 of each file whose size or time changed; more than 20,000 files and a read-only branch or judge to guard is a refusal at start |
| `GitFacts` | `None` in the check context ([CHK §2.1](75-check-contract-and-command-runs.spec.md)); `changed_paths` comes from the manifest |
| Refused at validation, with finding `needs_git` | Writer branches, worktree trials (PRP), finalizer push or draft pull request, `--carry` ([CAR](96-run-state-on-a-branch.spec.md)), git-based risk or complexity measures ([JRK](93-judge-model-by-risk.spec.md), [CXR](94-complexity-routing.spec.md)) |

## 3. Behaviours

**WSP-B1 Resume after worktree deletion.** Given a paused run whose worktree was deleted, when it resumes, then the engine re-attaches a worktree to the run's branch and continues; the state was never in the worktree.

**WSP-B2 Bootstrap of a worktree.** Given a workflow `worktree.include` list ([WTR §2.3](82-worktree-mode.spec.md)) naming untracked local files and setup commands, when a worktree is created, then those files are copied and the commands run with list argv; a failed bootstrap removes the new worktree and branch.

**WSP-B3 Interpreter in a worktree.** Given a step whose declared command starts with `python`, when it runs in a worktree, then `python` resolves to the workspace's virtual environment, else the main checkout's, else the engine's, never PATH.

**WSP-B4 Batch.** Given a batch of 10 targets with K = 3, when it runs, then at most 3 child processes run at once (K ≤ 16, at most 50 runs), each in its own worktree; every paused child is listed with its exact resume command; the batch parent runs no graph.

**WSP-B5 Executor scratch stays in the state root.** Given a judge on any executor that needs a private config (an MCP config, an Antigravity session home, a worker request document), when it is created, then it lives under the state root's scratch folder with owner-only permissions and is removed after the session, never in the operating system's temp folder, which a sandboxed child may not read.

**WSP-B6 Writes in place.** Given a workflow with writing branches, when it is started `in_place`, then the start is refused with exit 2.

**WSP-B7 Batch re-run skips done targets.** Given a batch file of 10 targets whose parent crashed after 6 children started, when the same file is run again, then the 6 existing threads are not started afresh (each is listed with its state and resume command) and the 4 others start.

## 4. Error conditions

| Condition | Result |
|---|---|
| Two planned batch runs whose names collide after flattening | Batch refused (exit 2) |
| Merge conflict at a join | Run branch reset; step blocked; person decides |
| Not inside a git repository, workflow needs worktrees | Exit 2; `auto` resolves to `in_place` when the workflow has no writers ([WTR §2.2](82-worktree-mode.spec.md)); the other rules of §2.4 |

## 5. Design notes

- One graph per process: branches of a fork are threads of one graph, so run-log and console writes hold locks; N runs are N processes sharing one checkpoint database per workflow ([ADR-0014](../adr/0014-sqlite-checkpointer.adr.md)).
- The default concurrency of three is a guess for every executor: no gateway's or API organization's concurrent-session or rate limit was measured. It is marked projected. On `messages-api` and `agent-sdk` a 429 with `retry-after` is `throttled` (infra), and a batch whose children report `throttled` twice lowers its concurrency by one for the rest of the batch, recorded.
- A merge is textual; two branches that merge cleanly but contradict each other are caught only by the join's judge or a check.
- Cleanup is never automatic unless a run sets `run.worktree.cleanup: on_finish`, which removes only clean worktrees; `worktree list` and `worktree prune` cover the rest; branches are never deleted ([WTR §2.7](82-worktree-mode.spec.md)).

## 6. Acceptance criteria

- [ ] WSP-AC-1 The state root resolves to the main checkout from any worktree (test with nested worktrees).
- [ ] WSP-AC-2 A test session fails if any test leaves state in the real state root.
- [ ] WSP-AC-3 Each shape of §2.1 is tested with real git worktrees and scripted executors.
- [ ] WSP-AC-4 No executor scratch file outlives its session on any exit path.
- [ ] WSP-AC-5 Outside git: the state root rule, the `in_place` rule, the manifest fingerprint catching a write by a read-only session, and every `needs_git` refusal of §2.4 hold on fixtures in a plain folder.

## Open questions

None.

## References

