# Workspace and concurrency

## Purpose

Where a run's files live, how runs and writing units stay apart, and how many runs one machine drives. State lives outside the workspace: the workspace is disposable, the branch is not. Paths resolve inside the workspace, the state root is the main checkout, and there is one graph per process, so N runs are N processes sharing one checkpoint database per workflow ([ADR-0014](../adr/0014-sqlite-checkpointer.adr.md)). The worktree itself (the `run.workspace` parameter, roots, bases, names, lifecycle, cleanup, executor pointing and the `worktree` verb) is [WTR](82-worktree-mode.spec.md). Operators, workflow authors and every component that stores files depend on these rules.

## Behaviours

### WSP-B8 The state root

WHEN the engine starts inside a git repository THE engine SHALL use `<main checkout>/.tempergraph/`, found from git's common directory whatever directory it starts in, as the gitignored state root holding checkpoints, run logs, locks, the ledger, batch folders, every session's logs, the engine's code log and executor scratch in the layout of [LOS-B7, LOS-B8, LOS-B9](33-local-observability-store.spec.md), and ignore `--state-root` and `TEMPERGRAPH_STATE_ROOT`.

- GIVEN the engine started in a nested worktree WHEN it resolves the state root THEN it is the main checkout's `.tempergraph/`
- GIVEN `TEMPERGRAPH_STATE_ROOT=/tmp/s` inside a repository WHEN a run starts THEN the main checkout's `.tempergraph/` is used

### WSP-B9 Workspace and run lock

WHEN a run starts THE engine SHALL fix its workspace for the run, the main checkout (`in_place`) or an engine-owned git worktree on its own branch chosen by `run.workspace` (`auto` by default) and stored in state ([WTR-B18, WTR-B20, WTR-B24](82-worktree-mode.spec.md)), and hold a per-thread OS file lock under the state root while it runs.

- GIVEN `run.workspace auto` and a workflow that writes files WHEN the run starts THEN it runs in its own worktree on its own branch

### WSP-B1 Resume after worktree deletion

WHEN a paused run whose worktree was deleted resumes THE engine SHALL re-attach a worktree to the run's branch and continue, the state never having been in the worktree.

- GIVEN a paused run whose worktree folder was removed WHEN it resumes THEN a worktree on the same branch exists and the next unit runs

### WSP-B2 Bootstrap of a worktree

WHEN a worktree is created for a workflow whose `worktree.include` names untracked local files and setup commands ([WTR-B19](82-worktree-mode.spec.md)) THE engine SHALL copy those files and run the commands with list argv, and remove the new worktree and branch when the bootstrap fails.

- GIVEN `include: [".env.test"]` WHEN the worktree is made THEN `.env.test` is in it
- GIVEN a setup command that exits 1 WHEN the worktree is made THEN the worktree and its branch are gone

### WSP-B3 Interpreter in a worktree

WHEN a declared command that starts with `python` runs in a worktree THE engine SHALL resolve `python` to the workspace's virtual environment, else the main checkout's, else the engine's, never from PATH.

- GIVEN a worktree with `.venv` WHEN `python -m pytest` runs THEN the worktree's `.venv` interpreter runs it

### WSP-B10 Import roots

WHEN a workflow declares `import_roots` THE engine SHALL put those paths, relative to the workspace, first on the module path of a check or a declared Python command, so a test run in a worktree imports the branch's code and not the main checkout's or the engine's.

- GIVEN `import_roots: [src]` in a worktree WHEN a check imports the package THEN it imports the worktree's `src`

### WSP-B11 Shapes of parallel work

WHEN units work in parallel THE engine SHALL run a parallel branch read-only in the run worktree, failing one whose head or status fingerprint changed; a writer branch or writing map item in its own sibling worktree cut from the run's branch after a checkpoint commit ([WTR-B20](82-worktree-mode.spec.md)) and merged without fast-forward in declared order at the join; a sequential map one item at a time in the run worktree, item k seeing what earlier items left; and a batch child in its own process and worktree with no join.

- GIVEN a parallel branch that edits a file WHEN it ends THEN it fails
- GIVEN a sequential map of three items WHEN item 2 runs THEN it sees item 1's files

### WSP-B12 A merge conflict at a join

WHEN merging writer branches at a join conflicts THE engine SHALL reset the run branch and end the step blocked with the conflicting paths, with no model call, for a person to decide.

- GIVEN two writer branches that change the same line WHEN the join merges them THEN the run branch is as before the merge and the step is blocked listing that path

### WSP-B4 Batch

WHEN a batch runs THE engine SHALL run at most K child processes at once (K at most 16, at most 50 runs), each in its own worktree, list every paused child with its exact resume command, and run no graph in the batch parent; a batch is a one-node map orchestration ([ORC](45-orchestration.spec.md), [ADR-0038](../adr/0038-batch-is-a-one-node-orchestration.adr.md)).

- GIVEN 10 targets and K = 3 WHEN the batch runs THEN no more than 3 children run at any moment
- GIVEN two planned batch runs whose names collide after flattening WHEN the batch starts THEN it is refused with exit 2

### WSP-B13 Batch files

WHEN a batch is started THE engine SHALL read a batch file (JSON with `schema_version`, the workflow, K and one entry per target with its request and optional alias and label) and write beside it an append-only batch event file with one JSON line per child event (`started`, `paused`, `finished`, `failed`, `throttled`).

- GIVEN a running batch WHEN a child pauses THEN a `paused` line is appended to the event file

### WSP-B7 Batch re-run skips done targets

WHEN a batch file is run again THE engine SHALL not start afresh a target whose thread exists, listing it with its state and resume command, and start the others.

- GIVEN a batch of 10 whose parent crashed after 6 children started WHEN the same file is run again THEN the 6 are listed and only the 4 others start

### WSP-B14 Throttled batches slow down

WHEN a batch's children report `throttled` twice THE engine SHALL lower the batch's concurrency by one for the rest of the batch and record it.

- GIVEN K = 3 and two `throttled` children WHEN the next child would start THEN at most 2 run at once and the change is recorded

### WSP-B5 Executor scratch stays in the state root

WHEN a session needs a private config (an MCP config, an Antigravity session home, a worker request document) THE engine SHALL create it under the state root's scratch folder with owner-only permissions and remove it after the session, never in the operating system's temp folder, which a sandboxed child may not read.

- GIVEN a judge with a private MCP config WHEN it ends on any exit path THEN the config file is gone

### WSP-B6 Writes in place

WHEN a workflow that writes files is started with `run.workspace in_place` THE engine SHALL run it in the checkout with the warning `in_place_writes` on the start ([WTR-B18](82-worktree-mode.spec.md)).

- GIVEN a writing workflow and `--in-place` WHEN it starts THEN the start carries `in_place_writes`

### WSP-B15 The state root outside git

WHEN the engine starts in a folder outside any git repository THE engine SHALL take the state root from `--state-root` (a global option before the verb) or `TEMPERGRAPH_STATE_ROOT`, else the nearest folder upward holding `.tempergraph/manifest.json`, skipping the home folder, else `<start dir>/.tempergraph/`, and refuse `not_git` a start whose root would be the home folder itself ([R-131](../research/R-131-running-outside-a-git-repository.rsrch.md), [ADR-0127](../adr/0127-outside-git-the-state-root-is-found-by-walk-up-and-the-guard-hashes-files.adr.md)).

- GIVEN `~/notes/a/b` and a manifest in `~/notes/.tempergraph/` WHEN the engine starts in `b` THEN the state root is `~/notes/.tempergraph/`
- GIVEN a start in the home folder with no declared root WHEN it runs THEN it is refused `not_git`

### WSP-B16 Workspace outside git

WHEN a run starts outside git THE engine SHALL run it `in_place` (`auto` resolves to it and `worktree` is refused with exit 2), and run a workflow that declares `workspace: none` in `<state root>/work/<workflow>/<task_id>/`, kept for the thread's life.

- GIVEN `--worktree` outside git WHEN the run starts THEN it exits 2

### WSP-B17 The guard fingerprint outside git

WHEN a run outside git needs a workspace fingerprint THE engine SHALL take the file count and a SHA-256 over every file's path, size and `mtime_ns`, leaving out the state root, keep the thread's first manifest as `runs/<workflow>/<thread>/manifest.json`, give a check `changed_paths` as every path added, removed or with another size or time since then and `git` as none ([CHK-B10](75-check-contract-and-command-runs.spec.md)), write `head_commit: ""` and `dirty: null` on `unit_entered`, and refuse the start `workspace_too_large` above 20,000 files when the workflow has a judge.

- GIVEN a read-only judge that writes a file outside git WHEN the guard compares fingerprints THEN the write is caught
- GIVEN 25,000 files and a workflow with a judge WHEN the run starts THEN it is refused `workspace_too_large`

### WSP-B18 What needs git

WHEN a workflow or a verb needs git outside a repository THE engine SHALL refuse it with finding `needs_git` before anything is created: writer branches, worktree trials (`improve trial`, PRP), a finalizer's push or draft pull request, `--carry` and the verb `carry` ([CAR](96-run-state-on-a-branch.spec.md)), and a stock risk or complexity rule on changed paths or lines ([JRK](93-judge-model-by-risk.spec.md), [CXR](94-complexity-routing.spec.md)).

- GIVEN `run --carry` outside git WHEN it starts THEN it is refused `needs_git` and no thread exists
- GIVEN a workflow with a writer branch outside git WHEN it is validated THEN it fails with `needs_git`

## Acceptance criteria

- WSP-AC1 (WSP-B8): The state root resolves to the main checkout from any worktree, by a test with nested worktrees
- WSP-AC2 (WSP-B8): A test session fails if any test leaves state in the real state root
- WSP-AC3 (WSP-B11, WSP-B12): Each shape of WSP-B11 is tested with real git worktrees and scripted executors
- WSP-AC4 (WSP-B5): No executor scratch file outlives its session on any exit path
- WSP-AC5 (WSP-B15, WSP-B16, WSP-B17, WSP-B18): Outside git, the state root rule, the `in_place` rule, the fingerprint catching a write by a read-only session, and every `needs_git` refusal hold on fixtures in a plain folder
- WSP-AC6 (WSP-B1, WSP-B9): A paused run whose worktree was deleted resumes on its branch
- WSP-AC7 (WSP-B2, WSP-B3, WSP-B10): A worktree bootstrap copies the listed files, a failed one leaves no worktree or branch, and `python` and imports resolve inside the worktree
- WSP-AC8 (WSP-B4, WSP-B13, WSP-B7, WSP-B14): A batch never runs more than K children, writes its event lines, skips existing threads on a re-run, and lowers K after two throttled children
- WSP-AC9 (WSP-B6): An in-place start of a writing workflow carries `in_place_writes`
