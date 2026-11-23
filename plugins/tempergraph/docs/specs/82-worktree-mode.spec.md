# Worktree mode

## Purpose

A run works either in place, in the person's checkout, or in its own git worktree on its own branch, which the engine creates, records, re-attaches and, only when asked, removes, using git directly on every executor. One setting chooses it, `run.workspace`, with a few `run.worktree.*` keys for where the worktree lives, which commit it starts from, how its branch is named and whether it is removed after a finished run; all are keys of the settings catalog ([RST-B20](80-run-settings-and-overrides.spec.md), [RST-B21](80-run-settings-and-overrides.spec.md)), so a flag, a profile, a project or user file and the workflow set them in the usual order and the thread snapshots them. This spec owns the person-facing parameter, the worktree's lifecycle, its names, how each executor is pointed at it, and how an executor's own worktree feature is kept from creating a second tree; [WSP](13-workspace-and-concurrency.spec.md) keeps the state root, the shapes of parallel work, batches and import roots ([R-100](../research/R-100-native-worktrees-and-executor-worktree-features.rsrch.md)). The engine owns the run's worktree and never uses an executor's native one ([ADR-0100](../adr/0100-the-engine-owns-the-run-worktree-executor-worktrees-are-not-used.adr.md)); worktrees are optional, and a workflow that only reads files or writes outside the repository runs in place under `auto` ([ADR-0101](../adr/0101-one-workspace-setting-with-an-auto-default.adr.md)); worktrees sit beside the repository with derived names ([ADR-0102](../adr/0102-worktrees-beside-the-repository-with-derived-ref-safe-names.adr.md)), start from the main checkout's `HEAD` ([ADR-0104](../adr/0104-a-new-worktree-starts-from-the-main-checkouts-head.adr.md)) and are removed only on request, clean, keeping the branch ([ADR-0103](../adr/0103-worktree-removal-is-opt-in-clean-only-and-keeps-the-branch.adr.md)). Operators, every executor and the finalizer depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### WTR-B17 Settings and flags

WHEN a run's workspace is set THE engine SHALL read `run.workspace` (`auto`, `worktree` or `in_place`, default the workflow's `workspace` else `auto`), `run.worktree.root` (`sibling`, `in_repo` or `path:<absolute path>`, default `sibling`), `run.worktree.base` (`head`, `default_branch` or `ref:<ref name>`, default the workflow's `worktree.base` else `head`), `run.worktree.branch_prefix` (1 to 3 ref-safe components joined by `/`, default `tg`), `run.worktree.cleanup` (`never` or `on_finish`, default the workflow's `worktree.cleanup` else `never`) and `run.worktree.read_worktreeinclude` (default `true`); take on `run`, `rerun`, `batch` and `run --check` the flags `--workspace auto|worktree|in_place`, `--worktree` and `--in-place`, `--worktree-root`, `--worktree-base` and `--worktree-cleanup`; fix every key at the start, refusing at `resume` a `--set` of `run.workspace`, `run.worktree.root`, `run.worktree.base` or `run.worktree.branch_prefix` with exit 2 `fixed_at_start` because the record already names a path and branch, `run.worktree.cleanup` alone changeable at resume; and let a rerun resolve its own values.

- GIVEN a paused worktree run WHEN `resume --set run.worktree.cleanup=on_finish` is given THEN it is accepted and recorded

### WTR-B15 Fixed at start

WHEN a resume sets a key fixed at start THE engine SHALL refuse it.

- GIVEN a paused worktree run WHEN `resume --set run.worktree.base=default_branch` is given THEN it exits 2 `fixed_at_start`

### WTR-B18 Resolving auto

WHEN `run.workspace` is `auto` THE function `resolve_workspace(spec, settings, target) -> WorkspacePlan`, pure and model-free, SHALL resolve it to `in_place` with `resolved_by: not_git` when the target is not a git checkout; to `worktree` with `writers` when the workflow has a writer branch, a writing map item or a writing contest ([WSP-B11](13-workspace-and-concurrency.spec.md)); to `worktree` with `writes_files` when a step, script or hybrid script declares `edit`, `write` or `shell` or a script has `side_effects: workspace`, the default ([SCR](70-script-units-and-hybrid-steps.spec.md)); and otherwise to `in_place` with `read_only`; and SHALL refuse with exit 2 before spend an explicit `worktree` on a target that is not a git checkout or is bare, and an explicit `in_place` on a workflow with writers ([WSP-B6](13-workspace-and-concurrency.spec.md)), allowing an explicit `in_place` on a workflow that writes files with one warning, the executors keeping their in-place permission modes ([ECC](11-executor-claude-code.spec.md), [EAS-B8](21-executor-agent-sdk.spec.md)).

- GIVEN a fixture workflow and target for each case WHEN resolved THEN no git write and no model call happen

### WTR-B1 Auto on a coding workflow

WHEN a workflow whose steps write files runs in a git checkout with no workspace option THE engine SHALL run it in a worktree and leave the person's checkout untouched.

- GIVEN a `code` step declaring `edit` and `shell` WHEN `run` starts THEN the record reads `mode: worktree`, `resolved_by: writes_files`, the path is `<parent>/<repo>.worktrees/<workflow>--<task_id>` and the branch `tg/<workflow>/<task_id>`

### WTR-B2 Auto on a document workflow

WHEN a workflow whose steps only read and write outside the repository runs THE engine SHALL run it in place.

- GIVEN steps declaring only `read`, `search` and an MCP tool that writes a wiki page WHEN run in a git checkout THEN it runs in place with `resolved_by: read_only`
- GIVEN the same WHEN run in a folder that is not a git checkout THEN it runs in place with `resolved_by: not_git`

### WTR-B3 Explicit worktree without git

WHEN `run --worktree` is given on a folder that is not a git checkout THE engine SHALL refuse the start with exit 2 before spend, naming the folder and the setting's source.

- GIVEN a plain folder WHEN `run --worktree` is given THEN it exits 2 naming the folder and the source

### WTR-B19 Workflow declaration

WHEN a workflow declares `worktree` (`WorktreeDecl`, an optional `WorkflowSpec` field, [CON-B4](01-contracts.spec.md)) THE engine SHALL read `include` (at most 50 gitignore-style patterns of untracked or ignored local files copied from the main checkout, such as environment files), `setup` (at most 10 argv lists run in order in the new worktree with the command runner of [CHK-B12](75-check-contract-and-command-runs.spec.md), each covered by the allow-list), `submodules` (`auto` runs `git submodule update --init --recursive` before `setup` when `.gitmodules` exists; `skip`), `setup_timeout_s` (10 to 3600, default 600, for the whole bootstrap), and `base` and `cleanup` as defaults on the `workflow:default` layer ([RST-B22](80-run-settings-and-overrides.spec.md)), a workflow setting no root or branch prefix; add with `read_worktreeinclude` the patterns of the main checkout's `.worktreeinclude`; and copy from either source only files git reports untracked or ignored, never a tracked file, a path outside the main checkout, a link, or anything under the state root or `.git`.

- GIVEN an `include` pattern matching a tracked file WHEN bootstrapped THEN that file is not copied

### WTR-B20 Locations and names

WHEN a worktree is placed THE engine SHALL derive the flat name `<workflow>--<task_id>`, each part's characters outside `[A-Za-z0-9._-]` and every `..` replaced by `-`, runs of `-` collapsed, a leading `.` or `-` and a trailing `.` dropped and a trailing `.lock` written `-lock`, at most 80 characters (a longer name cut to 71 plus `-` and the first 8 hex digits of the SHA-256 of the thread id), refusing two threads whose flat names collide (`name_collision`, [WSP-B16](13-workspace-and-concurrency.spec.md)); put it under the `sibling` root `<parent of main checkout>/<main checkout's folder name>.worktrees/`, the `in_repo` root `<main checkout>/.claude/worktrees/` (folder prefixed `tg-`, the root added to `.git/info/exclude` when git does not already ignore it, never to a tracked file) or a `path:` root (absolute, not inside the main checkout's tracked tree, the state root or `.git`, created owner-only if missing), refusing an unwritable or misplaced root with exit 2 before spend; name the run branch `<branch_prefix>/<workflow>/<task part>`, the task part the flat form of `task_id`, checked with `git check-ref-format --branch`; name writer, slot and item worktrees and branches with the suffixes `--w-<branch>`, `--s-<slot>` and `--i-<item>`, never a child path, since a ref cannot also be a folder of refs; give a rerun's flat name and branch `-r<n>` ([RRN-B18](81-reruns-and-feedback.spec.md)); and derive every name, no option setting a path or branch directly, with `--end-of-options` before every ref or path given to git ([SEC](14-security.spec.md)).

- GIVEN an 81-character task id WHEN named THEN the branch passes `git check-ref-format --branch` and no writer branch has the run branch as a path prefix

### WTR-B4 Names are ref-safe

WHEN a task id holds characters a ref refuses THE engine SHALL write its branch part in flat form.

- GIVEN task id `PROJ-12: fix login` WHEN a worktree run starts THEN the branch is `tg/<workflow>/PROJ-12-fix-login`, and its rerun's `tg/<workflow>/PROJ-12-fix-login-r1`
- GIVEN task ids `PROJ-12`, `a/b`, `x..y`, `.hidden` and `feat.lock` WHEN named THEN the parts are `PROJ-12`, `a-b`, `x-y`, `hidden` and `feat-lock`

### WTR-B21 Base

WHEN a new run worktree's start commit is chosen THE engine SHALL start it, for `head`, at the main checkout's `HEAD` commit with `base_branch` the branch it is on (the remote's default branch when detached), warning once with the count of uncommitted changed paths not in the worktree; for `default_branch`, at `origin`'s default branch after `git fetch origin <that branch>` within 30 s, falling back to the local copy with a warning and `base_fetch: failed`; and for `ref:<name>`, at the commit `<name>` resolves to by `git rev-parse --verify` (a local or remote-tracking branch, a tag or a commit id), with `base_branch` `<name>` without a remote prefix when it names a branch, else the default branch, an unresolvable or ill-formed ref refused with exit 2 before spend; `base_branch` being the pull request base the finalizer reads ([FIN-B6](78-finalizer-contract.spec.md)), and an orchestration node started from an earlier node's branch or an eval or trial case setting `ref:` ([ORC](45-orchestration.spec.md), [EVS](51-eval-suites.spec.md)).

- GIVEN `ref:nosuch` WHEN the run starts THEN it exits 2 before spend

### WTR-B6 Base head with a dirty checkout

WHEN a run starts with `base: head` and the main checkout has changes THE engine SHALL start at the checkout's commit and warn with the count.

- GIVEN a checkout on `main` with 3 changed files WHEN a run starts THEN the worktree starts at `main`'s commit, one warning names 3 paths and `base_branch` is `main`

### WTR-B7 Base default branch offline

WHEN `default_branch` cannot be fetched THE engine SHALL start from the local copy and record the failure.

- GIVEN no network and `--worktree-base default_branch` WHEN the run starts THEN the fetch fails within 30 s, the worktree starts at local `main` and the record holds `base_fetch: failed`

### WTR-B22 Lifecycle

WHEN a worktree run moves through its life THE engine SHALL at `run --check` resolve the plan, check the root is writable, the branch does not exist, the base resolves and setup commands are allowed, and print the plan creating nothing (C13); at start, after preflight and the thread lock and under a short repository lock, run `prepare_workspace`: `git worktree add -b <branch> <path> <base commit>`, `git worktree lock --reason "tempergraph <thread>"` and the bootstrap, a failed copy, submodule step, setup command or limit removing the new worktree and branch ([WSP-B2](13-workspace-and-concurrency.spec.md)) and exiting 2 with the failing step, recording a `workspace` record `prepared`; at each unit work in the record's path, `unit_entered` carrying `head_commit` and `dirty` ([EVT](30-run-events.spec.md)); at a pause, stop, failure or crash leave worktree, lock and branch, the pause payload naming the path; at resume run `attach_workspace`, reusing a present path on the branch (`reused`), or after `git worktree prune` adding it again with a new lock and bootstrap (`attached`, [WSP-B1](13-workspace-and-concurrency.spec.md)), keeping and recording a person's commits and changes since the segment (`external_change` with commit and changed-path counts), exiting 2 offering `rerun --from start` when the run branch is missing and naming the other checkout when the branch is checked out elsewhere; at a rewind touch no file ([RRN-B16](81-reruns-and-feedback.spec.md)); at a rerun prepare a new worktree and branch ([RRN-B18](81-reruns-and-feedback.spec.md)); and at finish run the finalizer with `workdir` the run worktree, then `release_workspace` unlocking it and applying cleanup, recording `released` and then `removed` or `kept` with the reason; an in-place run started inside a linked worktree working in that worktree, not the main checkout.

- GIVEN a failing setup command WHEN the run starts THEN the new worktree and branch are removed and it exits 2 naming the step

### WTR-B5 Branch exists

WHEN a fresh run's branch already exists THE engine SHALL refuse it with exit 2 by the fresh-run rule ([DUR-B1](09-durability-and-resume.spec.md)) if the thread exists, or with `branch_exists` naming the branch if only the branch does, creating nothing.

- GIVEN a branch `tg/wf/PROJ-12` from an earlier thread WHEN a fresh run with that task id starts THEN it exits 2 and nothing is created

### WTR-B8 Person edits a paused run

WHEN a person commits in a paused run's worktree THE engine SHALL keep the commit on resume and record it.

- GIVEN a run paused at `code` and one commit by a person WHEN resumed with `retry` THEN the commit is kept, `external_change` shows 1 commit and the next attempt sees the fix

### WTR-B9 Worktree deleted while paused

WHEN a paused run's worktree folder is gone at resume THE engine SHALL prune git's stale entry, attach a new worktree at the same path on the run branch, lock and bootstrap it and continue.

- GIVEN a deleted worktree folder WHEN resumed THEN it is `attached` at the same path and the run continues

### WTR-B10 Branch checked out elsewhere

WHEN a paused run's branch is checked out in another worktree and its folder is gone THE engine SHALL refuse the resume with exit 2 naming the other checkout and force nothing.

- GIVEN the branch checked out in the main checkout WHEN resumed THEN it exits 2 naming that checkout

### WTR-B14 Parallel runs

WHEN several runs of one workflow start at once THE engine SHALL give each its own worktree and branch, the repository lock serializing only the `git worktree add` calls.

- GIVEN three runs on three task ids started at once WHEN they prepare THEN each has its own worktree and branch

### WTR-B23 Cleanup

WHEN cleanup applies THE engine SHALL remove nothing under `cleanup: never`; under `cleanup: on_finish`, after a finished run's finalizer returns any outcome but `error`, remove each of the run's worktrees (run, writer, slot, item) that is clean (`git status --porcelain` empty), has no submodules and is locked by no one else, by `git worktree remove` without `--force`, keeping a dirty one, one with submodules and anything of a run that did not finish; keep a worktree git refuses to remove, recorded `kept` with git's reason, never retried with `--force`; and never delete an engine branch, `git branch -d` being the person's act.

- GIVEN any code path WHEN scanned THEN none calls `git worktree remove --force`, `git branch -D` or `git branch -d`

### WTR-B11 Cleanup on finish

WHEN a finished run with `cleanup: on_finish` ends THE engine SHALL remove its clean worktree, keep the branch, and keep a dirty worktree.

- GIVEN a finalizer that pushed the branch WHEN the run ends THEN the clean worktree is removed, the branch stays and `worktree list` no longer shows it
- GIVEN one untracked file left WHEN the run ends THEN the worktree is kept with `kept: dirty`

### WTR-B24 Records

WHEN a workspace is prepared THE engine SHALL keep in state a `WorkspaceRecord` of `mode` (`in_place` or `worktree`), `requested` and `resolved_by` (the setting's value and layer, and the auto case), `path`, `root_kind` (`sibling`, `in_repo` or `path`), `branch`, `base_ref`, `base_commit` and `base_branch`, `children` (writer, slot and item worktrees as `{name, path, branch, state}`), `state` (`active`, `released` or `removed`) and `bootstrap` (included file count, setup results with exit code and duration, submodule step); show `mode`, `path`, `branch` and `state` in `facts`, the status document and the run detail document ([RDD](31-run-detail-document.spec.md)); and put `mode` and `resolved_by` only, never a path, on a stats or ledger row ([CON-B14](01-contracts.spec.md)).

- GIVEN a worktree run WHEN its stats row is read THEN it holds no path

### WTR-B25 Executors

WHEN a session of a run starts THE engine SHALL give every step, judge, check, script and finalizer the workspace path as `SessionRequest.workdir` ([SSN](25-session-contract.spec.md)), a writer's step, judge, check and script the writer's path; point `claude` at it by the child's working directory, `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` and `--permission-mode acceptEdits` only when `workdir` is the path of an engine `WorkspaceRecord` or of one of its children ([ECC](11-executor-claude-code.spec.md)), never putting `--worktree` or `-w` on argv (C3), adding `EnterWorktree` and `ExitWorktree` to a step's `--disallowedTools` (P-WTR-1) and leaving both out of a judge's `--tools`; `agent-sdk` by `cwd = workdir` ([EAS-B8](21-executor-agent-sdk.spec.md)), `disallowed_tools` adding both tools, the gatekeeper hook denying an `Agent` call that asks for worktree isolation (P-WTR-3) and `extra_args` never carrying `worktree`; `messages-api` by the tool host's `workdir`, its known workspaces being the state root's `WorkspaceRecord` paths ([EMA-B8](20-executor-messages-api.spec.md), [THS-B7](22-tool-host.spec.md)); and `antigravity` by its working directory and `--add-dir <workdir>` with `init.cwd` equal to it ([EAG-B12](12-executor-antigravity.spec.md)), the App's worktrees unused and a repository with `extensions.worktreeConfig` getting a preflight warning until P-WTR-4 passes.

- GIVEN a scripted session per executor WHEN run THEN the working directory it records equals `WorkspaceRecord.path`

### WTR-B12 No executor worktree

WHEN a `claude` step launches THE engine SHALL keep `--worktree` and `-w` off argv, put `EnterWorktree` and `ExitWorktree` in `--disallowedTools`, and set the child's working directory to the run worktree.

- GIVEN a `claude` step WHEN it launches THEN argv holds neither flag and `--disallowedTools` holds both tools

### WTR-B26 Foreign worktrees

WHEN a step session starts and ends THE engine SHALL read `git worktree list --porcelain` before and after through `scan_foreign_worktrees`, and record a worktree that appeared and is not in the record (such as a subagent's with `isolation: worktree`, P-WTR-2) as a `workspace` record `foreign` with its path relative to the repository's parent, branch and `session_key`, a warning on the attempt and a `foreign_worktrees` fact the check and the judge can read, never removing, merging or reading it, the step's work counting only in the run's workspace.

- GIVEN no worktree appearing during a session WHEN it ends THEN no `foreign` record is written

### WTR-B13 Foreign worktree

WHEN a subagent creates a worktree during a session THE engine SHALL record it and leave it in place.

- GIVEN `.claude/worktrees/agent-x` created during a session WHEN the session ends THEN a `foreign` record names it, the attempt carries a warning and it stays

### WTR-B27 The worktree verb

WHEN `worktree list [--all] [--json]`, `worktree path <thread>` or `worktree prune [--thread <t>] [--finished] [--older-than <days>] [--apply]` runs THE engine SHALL list every engine worktree of this repository from the records and `git worktree list` (thread, thread state, path, branch, ahead and behind its base, dirty count, lock, and `removable` when the thread is not running, the worktree is clean and has no submodules), `--all` adding foreign worktrees and git worktrees no record owns; print the thread's workspace path, for `cd "$(tempergraph worktree path …)"`; or list the removable worktrees the selectors match and with `--apply` remove them by the cleanup rule then run `git worktree prune`, never one of a `running` thread; `list` and `path` writing nothing (C13), and `prune --apply` recording its caller ([PRV](85-caller-provenance.spec.md)).

- GIVEN `run --check`, `worktree list` and `worktree path` WHEN run THEN the repository's refs, worktree list and file tree are unchanged

### WTR-B16 Prune keeps work

WHEN `worktree prune --apply` runs THE engine SHALL remove only removable worktrees and no branch.

- GIVEN four worktrees (running, finished and clean, finished and dirty, paused and clean) WHEN `prune --apply` runs THEN only the finished clean and paused clean ones are removed, the paused thread can still resume, and no branch is deleted

## Acceptance criteria

- WTR-AC1 (WTR-B18, WTR-B1, WTR-B2, WTR-B3): `resolve_workspace` returns each case of WTR-B18 for a fixture workflow and target, with no git write and no model call
- WTR-AC2 (WTR-B20, WTR-B4): Every name of WTR-B20, including WTR-B4's cases and an 81-character task id, passes `git check-ref-format --branch`, and no writer branch has the run branch as a path prefix
- WTR-AC3 (WTR-B5, WTR-B6, WTR-B7, WTR-B8, WTR-B9, WTR-B10, WTR-B11, WTR-B14, WTR-B15, WTR-B16, WTR-B17, WTR-B19, WTR-B21, WTR-B22): WTR-B5 to WTR-B11 and WTR-B14 to WTR-B16 pass against real git worktrees with scripted executors
- WTR-AC4 (WTR-B25, WTR-B12, WTR-B24): For each of the four executors, a scripted session records the working directory it was given, and it equals `WorkspaceRecord.path`; the `claude` and `agent-sdk` launches carry the two disallowed tools
- WTR-AC5 (WTR-B23): No code path calls `git worktree remove --force`, `git branch -D` or `git branch -d`
- WTR-AC6 (WTR-B27): `run --check`, `worktree list` and `worktree path` create nothing (test compares the repository's refs, worktree list and file tree before and after)
- WTR-AC7 (WTR-B26, WTR-B13, WTR-B25): Probes P-WTR-1 (`claude -p --disallowedTools EnterWorktree,ExitWorktree` leaves neither tool in `system/init`), P-WTR-2 (a subagent with `isolation: worktree` under `claude -p` creates a worktree, and where), P-WTR-3 (the `Agent` tool input field that asks for worktree isolation, as a `PreToolUse` hook sees it) and P-WTR-4 (`agy -p` in a worktree of a repository with `extensions.worktreeConfig`) are recorded before the controls they gate are marked `LIVE-PROVEN`
- WTR-AC8 (WTR-B25): A writer branch's step, judge and check, run by a scripted executor, record the writer's worktree as their working directory, never the run worktree
- WTR-AC9 (WTR-B24, WTR-B27): While a run is paused after its block of writer branches was entered, the run's workspace record lists each writer worktree among its `children` with name, path, branch and state, and `worktree list` shows each beside the run's worktree
- WTR-AC10 (WTR-B23): Under `cleanup: never`, every writer worktree and writer branch of a finished run is still present after the run ends
- WTR-AC11 (WTR-B27): While a run's writer worktrees exist, `worktree path <thread>` prints the run worktree's path, never a writer worktree's

## Open questions

- Should `cleanup: on_finish` become the default once removal has run live for a release? Until answered: `never`. Owner: owner.
- Should a merged writer branch be deleted at the join? Until answered: keep every branch. Owner: owner.
- Not built yet: the `in_repo` and `path:` roots, the `default_branch` base, `cleanup: on_finish`, `prune --apply` and foreign-worktree scans are release 3 and refused `setting_not_in_release`; writer, slot and item worktrees arrive with the units that need them; probes P-WTR-1 to P-WTR-4 have not run. Owner: engine owner.
