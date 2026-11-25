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

WHEN units work in parallel THE engine SHALL run a parallel branch that declares neither `write` nor `edit`, or an item of a concurrent map whose step declares neither, read-only in the run worktree, failing one whose head or status fingerprint changed; a writer branch (a parallel branch that declares `write` or `edit`) or writing map item (an item of a concurrent map whose step declares `write` or `edit`) in its own sibling worktree cut from the run's branch after a checkpoint commit ([WTR-B20](82-worktree-mode.spec.md), WSP-B19) and merged without fast-forward in declared order at the join, a block's branches in the order its parallel unit names them and a map's items in the order of its list once every item has passed; a sequential map one item at a time in the run worktree, item k seeing what earlier items left; and a batch child in its own process and worktree with no join.

- GIVEN a parallel branch that declares neither `write` nor `edit` and changes a file in the run worktree WHEN it ends THEN it fails
- GIVEN a sequential map of three items WHEN item 2 runs THEN it sees item 1's files
- GIVEN two writer branches that each write one file WHEN the join merges them THEN the run branch holds both files and one merge commit per writer branch, in the order the parallel unit names them
- GIVEN a block of a writer branch and a read-only branch that changes nothing WHEN it runs THEN the read-only branch passes in the run worktree while the writer works in its own sibling worktree
- GIVEN a concurrent map whose step declares neither `write` nor `edit` and an item that changes a file in the run worktree WHEN the item ends THEN it fails
- GIVEN a concurrent map whose step declares `write` and whose list names p1, p2 and p3 WHEN the join merges the items THEN the run branch holds one merge commit per item in that order, whichever item ended first

### WSP-B19 The checkpoint before writers start

WHEN a parallel block that has a writer branch, or a concurrent map whose step declares `write` or `edit`, is entered THE engine SHALL commit the run worktree's uncommitted changes, new files included, on the run's branch before any branch of the block or item of the map starts.

- GIVEN a file an earlier unit left uncommitted WHEN a block with a writer branch is entered THEN the run's branch holds a commit with that file before any branch of the block starts, and each writer worktree holds the file
- GIVEN a run worktree with no uncommitted change WHEN a block with a writer branch is entered THEN the run's branch gets no new commit
- GIVEN a block of read-only branches only WHEN it is entered THEN the run's branch gets no new commit
- GIVEN a file an earlier unit left uncommitted WHEN a concurrent map whose step declares `write` is entered THEN the run's branch holds a commit with that file before any item starts, and each item's worktree holds the file

### WSP-B12 A merge conflict at a join

WHEN merging writer branches at a join, or the items of a writing map once every item has passed, conflicts THE engine SHALL reset the run branch and end the step blocked with the conflicting paths, with no model call, for a person to decide.

- GIVEN two writer branches that change the same line WHEN the join merges them THEN the run branch is as before the merge and the step is blocked listing that path
- GIVEN two items of a concurrent map whose step declares `write` that change the same line WHEN the join merges them THEN the run branch is as before the merge and the map is blocked listing that path

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

### WSP-B20 Each pass of a writing unit has writers of its own

WHEN a writing unit (a concurrent map whose step declares `write` or `edit`, or a contest with `writes: true`) runs a pass after its first, on a retry or a new entry ([BUD-B4](08-budgets-and-failures.spec.md)), THE engine SHALL run each item or slot of that pass in a worktree and on a branch cut for the pass from the run branch's head after the checkpoint commit (WSP-B19), under names that no earlier pass holds ([WTR-B20](82-worktree-mode.spec.md)).

- GIVEN a writing map whose first pass ran items `a` and `b` and was merged, and a trip back after which its list names `a` and `c` WHEN the map runs again THEN `a` and `c` each run in a worktree and on a branch that the first pass did not make, each holding the files the run branch held when the pass started, `b`'s file among them
- GIVEN a writing contest whose first attempt's winner `s1` got RETRY under `retry_scope: best` WHEN the retry runs THEN `s1` alone runs, in a worktree and on a branch that the first attempt did not make
- GIVEN a later pass of a writing map paused at an item on a spent budget WHEN it is resumed with retry THEN the item runs again in its worktree of that pass

### WSP-B21 Earlier passes' writers are kept

WHEN a writing unit runs a pass after its first THE engine SHALL leave every worktree and branch of its earlier passes as it is, still listed among the run's worktrees ([WTR-B24](82-worktree-mode.spec.md)).

- GIVEN a first pass whose branch of `a` is at commit C WHEN the second pass has run to its end THEN that branch is still at C, its worktree still exists and the run's workspace record lists it in the state it had

### WSP-B22 A pass merges only its own writers

WHEN a later pass of a writing unit is merged THE engine SHALL merge into the run branch only the branches that pass cut: a map's items in the order of that pass's list (WSP-B11), a contest's winner of that attempt ([CTS-B5](72-contest-unit.spec.md)).

- GIVEN a second pass of a writing map whose list names `a` and `c`, each writing one file WHEN it is merged THEN the run branch gains one merge commit per item, `a` then `c`, each with that pass's branch as second parent, and none with a branch of the first pass
- GIVEN a retry of a writing contest under `retry_scope: all` whose winner is `s2` WHEN it is picked THEN the run branch gains one merge commit, with `s2`'s branch of the retry as second parent, and no other

### WSP-B18 What needs git

WHEN a workflow or a verb needs git outside a repository THE engine SHALL refuse it with finding `needs_git` before anything is created: writer branches, a concurrent map whose step declares `write` or `edit` (a writing map, WSP-B11), worktree trials (`improve trial`, PRP), a finalizer's push or draft pull request, `--carry` and the verb `carry` ([CAR](96-run-state-on-a-branch.spec.md)), and a stock risk or complexity rule on changed paths or lines ([JRK](93-judge-model-by-risk.spec.md), [CXR](94-complexity-routing.spec.md)).

- GIVEN `run --carry` outside git WHEN it starts THEN it is refused `needs_git` and no thread exists
- GIVEN a workflow with a writer branch outside git WHEN it is validated THEN it fails with `needs_git`
- GIVEN a workflow of a step followed by a concurrent map whose step declares `write` WHEN it starts outside git THEN it is refused `needs_git` naming the map, the first step starts no session and nothing is created
- GIVEN the same workflow WHEN `run --check` runs outside git THEN it reports `needs_git` naming the map
- GIVEN a concurrent map whose step declares neither `write` nor `edit` WHEN a run starts outside git THEN it is not refused `needs_git` for the map

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
- WSP-AC10 (WSP-B11): In a block of two writer branches, each writer branch works on its own branch in its own sibling worktree, never the run worktree, and each of those branches starts at the head the run's branch held before the block's first session
- WSP-AC11 (WSP-B11): After a block of two writer branches that each write one file passes, the run branch holds both files and one merge commit per writer branch, each with the writer's branch as second parent, in the order the parallel unit names its branches
- WSP-AC12 (WSP-B11): In a block of a writer branch and a read-only branch, the read-only branch's step runs in the run worktree, passes when it changes nothing and fails with `branch_changed_the_workspace` when it changes a file
- WSP-AC13 (WSP-B19): A file an earlier unit left uncommitted is in a commit on the run's branch before any session of a block with a writer branch starts, and is in each writer worktree
- WSP-AC14 (WSP-B19): A block of read-only branches adds no commit to the run's branch
- WSP-AC15 (WSP-B12): Two writer branches that change one line leave the run's branch at the commit it held before the join's first merge, end the join's step blocked with the pause listing that path, and start no model session for the join
- WSP-AC16 (WSP-B11): In a concurrent map of two items whose step declares `write`, each item works on its own branch in its own sibling worktree, never the run worktree, and each of those branches starts at the head the run's branch held before the map's first item session
- WSP-AC17 (WSP-B11): After a concurrent map whose step declares `write` and whose items each write one file passes, the run branch holds every file and one merge commit per item, each with the item's branch as second parent, in the order of the map's list whichever item ended first
- WSP-AC18 (WSP-B11): In a concurrent map whose step declares neither `write` nor `edit`, an item that changes a file in the run worktree fails with `branch_changed_the_workspace`
- WSP-AC19 (WSP-B19): A file an earlier unit left uncommitted is in a commit on the run's branch before any item session of a concurrent map whose step declares `write` starts, and is in each item's worktree
- WSP-AC20 (WSP-B12): Two items of a concurrent map whose step declares `write` that change one line leave the run's branch at the commit it held before the first merge, end the map blocked with the pause listing that path, and start no model session after the items have ended
- WSP-AC21 (WSP-B18): Started outside git, a workflow of a step followed by a concurrent map whose step declares `write` or `edit` is refused `needs_git` naming the map, with no session started and nothing created
- WSP-AC22 (WSP-B18): `run --check` outside git reports `needs_git` naming the map for that workflow
- WSP-AC23 (WSP-B18): A concurrent map whose step declares neither `write` nor `edit` adds no `needs_git` refusal outside git
- WSP-AC24 (WSP-B20): In a writing concurrent map entered a second time by a trip back and run by a scripted executor, each item of the second pass runs in a worktree and on a branch that the first pass did not make, the branch starting at the head the run branch held before the pass's first item session, and its worktree holds the files the run branch held when the pass started, among them those of the first pass's merge
- WSP-AC25 (WSP-B20): A later pass of a writing map paused at an item on a spent budget and resumed with `retry` runs that item again in its worktree of that pass
- WSP-AC26 (WSP-B20): In a writing contest of two slots under `retry_scope: best`, the retry of the first attempt's winner runs that slot in a worktree and on a branch that the first attempt did not make, starting at the head the run branch held before the retry's first session, and the run records no `workspace_refused`
- WSP-AC27 (WSP-B20): Under `retry_scope: all` every slot of a writing contest's retry, and after a BACK to the unit before it every slot of its next attempt, runs in a worktree and on a branch that no earlier attempt made, and the run records no `workspace_refused`
- WSP-AC28 (WSP-B21): After a later pass of a writing map or a writing contest, every branch of the earlier pass is at the commit it held when that pass ended, every worktree of it is still present and the run's workspace record lists the worktrees of both passes
- WSP-AC29 (WSP-B22): After a later pass whose writers each write one file, the run branch has gained one merge commit per item of that pass's list in its order, or one for the contest's winner of that attempt, each with that pass's branch as second parent, and none whose second parent is a branch of an earlier pass
