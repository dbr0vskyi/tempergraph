---
title: Worktree mode
type: component
status: review
prefix: WTR
adrs: [0100, 0101, 0102, 0103, 0104, 0070]
---

# Worktree mode

## 1. Overview

A run works either **in place**, in the person's checkout, or in its own **git worktree** on its own branch, which the engine creates, records, re-attaches and, only when asked, removes, using git directly on every executor. One setting chooses it, `run.workspace`, with the values `auto`, `worktree` and `in_place`, spelled `--workspace`, `--worktree` and `--in-place`; a few `run.worktree.*` keys say where the worktree lives, which commit it starts from, how its branch is named and whether it is removed after a finished run. All are keys of the settings catalog ([RST §2.2](80-run-settings-and-overrides.spec.md)), so a flag, a profile, a project or user file and the workflow set them in the usual order, and the thread snapshots them.

This spec owns the person-facing parameter, the worktree's lifecycle, its names, how each executor is pointed at it, and how an executor's own worktree feature is kept from creating a second tree. [WSP](13-workspace-and-concurrency.spec.md) keeps the state root, the shapes of parallel work, batches and import roots. Findings and sources: [R-100](../research/R-100-native-worktrees-and-executor-worktree-features.rsrch.md).

The engine owns the run's worktree; an executor's native worktree is never used for a run ([ADR-0100](../adr/0100-the-engine-owns-the-run-worktree-executor-worktrees-are-not-used.adr.md)). Worktrees are optional: a workflow that only reads files or writes outside the repository (a wiki page, a tracker issue) runs in place under `auto` ([ADR-0101](../adr/0101-one-workspace-setting-with-an-auto-default.adr.md)).

## 2. Contract

```python
def resolve_workspace(spec: WorkflowSpec, settings: ResolvedSettings, target: Path) -> WorkspacePlan: ...   # pure, model-free
def prepare_workspace(thread: str, plan: WorkspacePlan, decl: WorktreeDecl) -> WorkspaceRecord: ...
def attach_workspace(record: WorkspaceRecord) -> WorkspaceRecord: ...      # on resume
def release_workspace(record: WorkspaceRecord, cleanup: str) -> WorkspaceRecord: ...   # after the finalizer
def scan_foreign_worktrees(record: WorkspaceRecord, before: list[str]) -> list[ForeignWorktree]: ...
```

### 2.1 Settings

| Key | Value | Engine default | Meaning |
|---|---|---|---|
| `run.workspace` | `auto` \| `worktree` \| `in_place` | the workflow's `workspace`, else `auto` | §2.2 |
| `run.worktree.root` | `sibling` \| `in_repo` \| `path:<absolute path>` | `sibling` | Where run worktrees are created (§2.4) |
| `run.worktree.base` | `head` \| `default_branch` \| `ref:<ref name>` | `head` | The commit a new run worktree starts from (§2.5) |
| `run.worktree.branch_prefix` | 1–3 ref-safe components joined by `/` | `tg` | First part of every engine branch (§2.4) |
| `run.worktree.cleanup` | `never` \| `on_finish` | `never` | Whether a finished run's clean worktree is removed (§2.7) |
| `run.worktree.read_worktreeinclude` | bool | `true` | Also copy what the repository's `.worktreeinclude` names (§2.3) |

| Flag on `run`, `rerun`, `batch`, `run --check` | Key |
|---|---|
| `--workspace auto\|worktree\|in_place` | `run.workspace` |
| `--worktree` / `--in-place` | `run.workspace=worktree` / `run.workspace=in_place` |
| `--worktree-root <sibling\|in_repo\|path:…>` | `run.worktree.root` |
| `--worktree-base <head\|default_branch\|ref:…>` | `run.worktree.base` |
| `--worktree-cleanup <never\|on_finish>` | `run.worktree.cleanup` |

Every key is fixed at the start: `resume` refuses `--set` of `run.workspace`, `run.worktree.root`, `run.worktree.base` and `run.worktree.branch_prefix` with exit 2 (`fixed_at_start`), because the record already names a path and a branch. `run.worktree.cleanup` may change at resume. A rerun resolves its own values (§2.6).

### 2.2 Resolving `auto`

| Target | Workflow | Resolves to | `resolved_by` |
|---|---|---|---|
| Not a git checkout | any | `in_place` | `not_git` |
| git checkout | has a writer branch, a writing map item or a writing contest ([WSP §2.1](13-workspace-and-concurrency.spec.md)) | `worktree` | `writers` |
| git checkout | a step, script or hybrid script declares `edit`, `write` or `shell`, or a script declares `side_effects: local` ([SCR](70-script-units-and-hybrid-steps.spec.md)) | `worktree` | `writes_files` |
| git checkout | none of the above | `in_place` | `read_only` |

An explicit `worktree` on a target that is not a git checkout, or with a bare repository, is refused with exit 2 before spend. An explicit `in_place` on a workflow with writers is refused with exit 2 ([WSP-B6](13-workspace-and-concurrency.spec.md)). An explicit `in_place` on a workflow that writes files is allowed, with one warning, and the executors keep their in-place permission modes ([ECC §2.3](11-executor-claude-code.spec.md), [EAS §2.4](21-executor-agent-sdk.spec.md)).

### 2.3 Workflow declaration

`WorkflowSpec` gains one optional field ([CON §2.1](01-contracts.spec.md)):

| `WorktreeDecl` field | Kind | Meaning |
|---|---|---|
| `include` | list of gitignore-style patterns, ≤ 50 | Untracked or ignored local files copied from the main checkout into a new worktree (environment files, local settings) |
| `setup` | list of argv lists, ≤ 10 | Commands run in the new worktree, in order, with the command runner of [CHK §2.3](75-check-contract-and-command-runs.spec.md), each covered by the workflow's allow-list |
| `submodules` | `auto` \| `skip` | `auto`: when `.gitmodules` exists, `git submodule update --init --recursive` runs before `setup` |
| `setup_timeout_s` | int 10–3600, default 600 | Limit for the whole bootstrap |

With `run.worktree.read_worktreeinclude`, the patterns of the main checkout's `.worktreeinclude` file (the Claude Code convention, [R-100](../research/R-100-native-worktrees-and-executor-worktree-features.rsrch.md) F3.2) are added to `include`. From either source only files that git reports as untracked or ignored are copied, never a tracked file, never a path outside the main checkout, never a link, and never anything under the state root or `.git`.

### 2.4 Locations and names

| Item | Rule |
|---|---|
| Flat name | `<workflow>--<task_id>`, where each part has every character outside `[A-Za-z0-9._-]` and every `..` replaced by `-`, runs of `-` collapsed to one, a leading `.` or `-` and a trailing `.` dropped, and a trailing `.lock` written `-lock`; at most 80 characters in all; a longer name is cut to 71 and gets `-` plus the first 8 hex digits of the SHA-256 of the full thread id. Two threads whose flat names collide are refused (the batch rule of [WSP §4](13-workspace-and-concurrency.spec.md), now for every start) |
| `sibling` root | `<parent of main checkout>/<main checkout's folder name>.worktrees/` |
| `in_repo` root | `<main checkout>/.claude/worktrees/`, Claude Code's location; the engine prefixes the folder `tg-` and adds the root to `.git/info/exclude` when git does not already ignore it, never to a tracked file |
| `path:` root | An absolute path that is not inside the main checkout's tracked tree, the state root or `.git`; created with owner-only permissions if missing |
| Run worktree | `<root>/<flat name>` |
| Run branch | `<branch_prefix>/<workflow>/<task part>`, where the task part is the flat form of `task_id` (so `/` becomes `-`); checked with `git check-ref-format --branch` before use |
| Writer, slot, item | Worktree `<run worktree>--w-<branch>`, `--s-<slot>`, `--i-<item>`; branch `<run branch>--w-<branch>` and so on. A suffix, never a child path: a ref cannot also be a folder of refs ([R-100](../research/R-100-native-worktrees-and-executor-worktree-features.rsrch.md) F1.6) |
| Rerun | Thread `<workflow>/<task_id>~r<n>` keeps its spelling; its flat name and branch carry `-r<n>`, since `~` is not allowed in a ref ([RRN §2.4](81-reruns-and-feedback.spec.md)) |

Names are derived, never typed: no option sets a path or branch name directly, so no text reaches git's argv unchecked ([SEC](14-security.spec.md)). Every git call puts `--end-of-options` before a ref or path.

### 2.5 Base

| `run.worktree.base` | The new run worktree starts at | `base_branch` (the pull request base, [FIN §2.1](78-finalizer-contract.spec.md) `base`) |
|---|---|---|
| `head` | The main checkout's `HEAD` commit at the start | The branch the main checkout is on; the remote's default branch when `HEAD` is detached |
| `default_branch` | `origin`'s default branch after `git fetch origin <that branch>` (30 s limit); if the fetch fails, the local copy, with a warning and `base_fetch: failed` | That branch |
| `ref:<name>` | The commit `<name>` resolves to (a local branch, a remote-tracking branch, a tag or a commit id), checked with `git rev-parse --verify` | `<name>` without a remote prefix, when it names a branch; else the default branch |

A main checkout with uncommitted changes under `head` gives one warning with the count of changed paths: they are not in the worktree. An orchestration that starts a node's run from an earlier node's branch sets `ref:<that branch>` in the node's options ([ORC](45-orchestration.spec.md)); an eval or trial case sets `ref:<case base>` ([EVS](51-eval-suites.spec.md)).

### 2.6 Lifecycle

| Moment | Engine does | Records |
|---|---|---|
| `run --check` | Resolves §2.2 to §2.5, checks the root is writable, the branch does not exist, the base resolves, setup commands are allowed; creates nothing (C13) | Prints the plan |
| Start | After the preflight and the thread lock, under a short repository lock: `git worktree add -b <branch> <path> <base commit>`, then `git worktree lock --reason "tempergraph <thread>"`, then bootstrap (§2.3). A failed bootstrap removes the new worktree and branch ([WSP-B2](13-workspace-and-concurrency.spec.md)) and exits 2 | `WorkspaceRecord` in state (§2.8); `workspace` run-log record, action `prepared` |
| Each unit | Works in the record's path; `unit_entered` carries `head_commit` and `dirty` ([EVT §2.2](30-run-events.spec.md)) | |
| Pause, stop, failure, crash | Nothing: the worktree, its lock and its branch stay; the pause payload names the worktree path so a person can open it | |
| Resume | Re-reads the record. Path present on the branch: reused. Path gone: `git worktree prune`, then `git worktree add <path> <branch>` and a new lock, then bootstrap again ([WSP-B1](13-workspace-and-concurrency.spec.md)). Commits or uncommitted changes made by a person since the segment ended are kept and recorded | `workspace` action `reused`, `attached` or `external_change` (commit count, changed-path count) |
| Rewind | Nothing: files are untouched ([RRN §2.3](81-reruns-and-feedback.spec.md)) | |
| Rerun | A new thread resolves its own settings from the source's snapshot and its own flags; on a worktree workflow it gets a new worktree and branch per [RRN §2.4](81-reruns-and-feedback.spec.md), named by §2.4 | `prepared` on the new thread |
| Finish | The finalizer runs with `workdir` = the run worktree, so a push of the run branch happens from it ([FIN](78-finalizer-contract.spec.md)); then `release_workspace` unlocks the worktree and applies `run.worktree.cleanup` (§2.7) | `workspace` action `released`, then `removed` or `kept` with the reason |

### 2.7 Cleanup

| Setting or verb | Removes | Never removes |
|---|---|---|
| `cleanup: never` (default) | Nothing | — |
| `cleanup: on_finish` | After a finished run's finalizer returns (any outcome but `error`), each of the run's worktrees (run, writer, slot, item) that is clean (`git status --porcelain` empty), has no submodules and is not locked by anyone else, by `git worktree remove` without `--force` | A dirty worktree, one with submodules, a branch, anything of a run that did not finish |
| `worktree prune` | What the list marks `removable`, with `--apply`; without it, only lists | Ditto, plus any worktree of a thread that is `running` |

Engine branches are never deleted by the engine ([ADR-0103](../adr/0103-worktree-removal-is-opt-in-clean-only-and-keeps-the-branch.adr.md)): unpushed commits stay reachable, and `git branch -d` is the person's act.

### 2.8 Records

| `WorkspaceRecord` field | Meaning |
|---|---|
| `mode` | `in_place` \| `worktree` |
| `requested`, `resolved_by` | The setting's value and layer, and the §2.2 row for `auto` |
| `path` | Absolute path of the run's workspace |
| `root_kind` | `sibling` \| `in_repo` \| `path` |
| `branch`, `base_ref`, `base_commit`, `base_branch` | §2.4, §2.5 |
| `children` | Writer, slot and item worktrees: `{name, path, branch, state}` |
| `state` | `active` \| `released` \| `removed` |
| `bootstrap` | Included file count, setup command results (exit code, duration), submodule step |

`facts`, the status document and the run detail document show `mode`, `path`, `branch` and `state` ([RDD](31-run-detail-document.spec.md)); a stats or ledger row carries `mode` and `resolved_by` only, never a path ([CON §2.10](01-contracts.spec.md)).

### 2.9 Executors

The workspace path is `SessionRequest.workdir` ([CON §2.6](01-contracts.spec.md)) for every step, judge, check, script and finalizer of the run; a writer's step and judge get the writer's path.

| Executor | Pointed at the worktree by | Its own worktree feature |
|---|---|---|
| `claude` | Child process working directory; `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`; `--permission-mode acceptEdits` only when `workdir` is the path of an engine `WorkspaceRecord` ([ECC §2.3](11-executor-claude-code.spec.md)) | `--worktree` / `-w` is never on argv (argv is constants, C3). Step launches add `EnterWorktree` and `ExitWorktree` to `--disallowedTools` (P-WTR-1); judges have neither under `--tools` |
| `agent-sdk` | `cwd = workdir` ([EAS §2.4](21-executor-agent-sdk.spec.md)) | `disallowed_tools` adds `EnterWorktree` and `ExitWorktree`; the gatekeeper hook denies an `Agent` call that asks for worktree isolation (P-WTR-3); `extra_args` never carries `worktree` |
| `messages-api` | The tool host's `workdir`; "known workspaces" are the state root's `WorkspaceRecord` paths ([EMA §2.3](20-executor-messages-api.spec.md), [THS §2.2](22-tool-host.spec.md)) | None |
| `antigravity` | Working directory and `--add-dir <workdir>`; `init.cwd` must equal it ([EAG §2.4](12-executor-antigravity.spec.md)) | The App's worktrees are not used; the isolated config home keeps App settings out. A repository with `extensions.worktreeConfig` set gets a preflight warning for `antigravity` sessions until P-WTR-4 passes |

### 2.10 Foreign worktrees

Before and after every step session the engine reads `git worktree list --porcelain`. A worktree that appears during the session and is not in the record (for example a Claude Code subagent with `isolation: worktree`, P-WTR-2) is a **foreign worktree**: a `workspace` record with action `foreign` (path relative to the repository's parent, branch, `session_key`), a warning on the attempt, and a `foreign_worktrees` fact the check and the judge can read. The engine never removes, merges or reads it; the step's work counts only if it is in the run's workspace.

### 2.11 The `worktree` verb

| Verb | Does | Writes |
|---|---|---|
| `worktree list [--all] [--json]` | Every engine worktree of this repository from the records and `git worktree list`: thread, thread state, path, branch, ahead and behind its base, dirty count, lock, and `removable` (thread not running, worktree clean, no submodules). `--all` adds foreign worktrees and git worktrees no record owns | no |
| `worktree path <thread>` | Prints the thread's workspace path, for `cd "$(tempergraph worktree path …)"` | no |
| `worktree prune [--thread <t>] [--finished] [--older-than <days>] [--apply]` | Lists the removable worktrees the selectors match; with `--apply` removes them per §2.7, then `git worktree prune` | with `--apply` |

`list` and `path` are read-only (C13). `prune --apply` is a mutating verb and records its caller ([PRV](85-caller-provenance.spec.md)).

## 3. Behaviours

**WTR-B1 Auto on a coding workflow.** Given a git checkout and a workflow whose `code` step declares `edit` and `shell`, when `run` starts with no workspace option, then the record reads `mode: worktree`, `resolved_by: writes_files`, the path is `<parent>/<repo>.worktrees/<workflow>--<task_id>`, the branch is `tg/<workflow>/<task_id>`, and the person's checkout is untouched.

**WTR-B2 Auto on a document workflow.** Given a workflow whose steps declare only `read`, `search` and an MCP tool that writes a wiki page, when it runs in a git checkout, then it runs in place with `resolved_by: read_only`; in a folder that is not a git checkout it runs in place with `resolved_by: not_git`.

**WTR-B3 Explicit worktree without git.** Given a folder that is not a git checkout, when `run --worktree` is given, then the start is refused with exit 2 before spend, naming the folder and the setting's source.

**WTR-B4 Names are ref-safe.** Given task id `PROJ-12: fix login`, when a worktree run starts, then the branch is `tg/<workflow>/PROJ-12-fix-login` and passes `git check-ref-format --branch`; a rerun of it uses `tg/<workflow>/PROJ-12-fix-login-r1`.

| Task id | Branch part |
|---|---|
| `PROJ-12` | `PROJ-12` |
| `a/b` | `a-b` |
| `x..y` | `x-y` |
| `.hidden` | `hidden` |
| `feat.lock` | `feat-lock` |

**WTR-B5 Branch exists.** Given a branch `tg/temperspec/PROJ-12` from an earlier thread, when a fresh run with the same task id starts, then it is refused with exit 2 by the fresh-run rule ([DUR-B1](09-durability-and-resume.spec.md)) if the thread exists, or with `branch_exists` naming the branch if only the branch does; nothing is created.

**WTR-B6 Base head with a dirty checkout.** Given a main checkout on `main` with 3 changed files, when a run starts with `base: head`, then the worktree starts at `main`'s commit, one warning says 3 changed paths are not in the worktree, and `base_branch` is `main`.

**WTR-B7 Base default branch offline.** Given no network, when `--worktree-base default_branch` is given, then the fetch fails within 30 s, the worktree starts at the local `main`, and the record holds `base_fetch: failed`.

**WTR-B8 Person edits a paused run.** Given a run paused at `code` whose person commits one fix in the run worktree, when it resumes with `retry`, then the commit is kept, a `workspace` record `external_change` shows 1 commit, and the next attempt sees the fix.

**WTR-B9 Worktree deleted while paused.** Given a paused run whose worktree folder a person deleted, when it resumes, then the engine prunes git's stale entry, attaches a new worktree at the same path on the run branch, locks it, bootstraps it and continues (`attached`).

**WTR-B10 Branch checked out elsewhere.** Given a paused run whose branch the person checked out in the main checkout, when it resumes and the worktree folder is gone, then the resume is refused with exit 2 naming the other checkout; nothing is forced.

**WTR-B11 Cleanup on finish.** Given `cleanup: on_finish` and a finished run whose finalizer pushed the branch, when the run ends, then the clean run worktree is removed, the branch stays, and `worktree list` no longer shows it; given one untracked file left in it, the worktree is kept and the record says `kept: dirty`.

**WTR-B12 No executor worktree.** Given a `claude` step, when it launches, then argv holds no `--worktree` or `-w`, `--disallowedTools` holds `EnterWorktree` and `ExitWorktree`, and the child's working directory is the run worktree.

**WTR-B13 Foreign worktree.** Given a step whose subagent created `.claude/worktrees/agent-x` during its session, when the session ends, then a `workspace` record `foreign` names it, the attempt carries a warning, and the engine leaves it in place.

**WTR-B14 Parallel runs.** Given three runs of one workflow on three task ids started at once, when they prepare their workspaces, then each gets its own worktree and branch, and the repository lock serializes only the `git worktree add` calls.

**WTR-B15 Fixed at start.** Given a paused worktree run, when `resume --set run.worktree.base=default_branch` is given, then it is refused with exit 2 (`fixed_at_start`); `resume --set run.worktree.cleanup=on_finish` is accepted and recorded.

**WTR-B16 Prune keeps work.** Given four engine worktrees (one running, one finished and clean, one finished and dirty, one paused and clean), when `worktree prune --apply` runs, then only the finished clean one and the paused clean one are removed, the paused thread can still resume (WTR-B9), and no branch is deleted.

## 4. Error conditions

| Condition | Result |
|---|---|
| `worktree` explicit, target not a git checkout or a bare repository | Exit 2 before spend |
| `in_place` explicit, workflow has writers | Exit 2 ([WSP-B6](13-workspace-and-concurrency.spec.md)) |
| Root not writable, or a `path:` root inside the main checkout, the state root or `.git` | Exit 2 before spend |
| Branch exists with no thread; flat names of two threads collide | Exit 2, `branch_exists` / `name_collision` |
| `ref:` base does not resolve, or fails `check-ref-format` | Exit 2 before spend |
| Bootstrap fails (copy, submodules, a setup command, its limit) | New worktree and branch removed; exit 2 with the failing step |
| Resume: run branch missing | Exit 2; the message offers `rerun --from start` |
| Resume: branch checked out in another worktree | Exit 2 naming it |
| `resume --set` of a key fixed at start | Exit 2, `fixed_at_start` |
| Removal refused by git | Worktree kept, `kept` with git's reason; never retried with `--force` |

## 5. Design notes

- Why the engine and not the executor: gates, checks, judges and the finalizer run in the engine and need one tree for the whole run, at a base the engine picks; Claude Code's `--worktree` is per session, starts from the default branch, is never removed under `-p` and is left locked; Antigravity's is an App feature; the Messages API has none ([ADR-0100](../adr/0100-the-engine-owns-the-run-worktree-executor-worktrees-are-not-used.adr.md)).
- `auto` keeps worktrees optional for non-coding workflows while making the safe choice the default for workflows that change files ([ADR-0101](../adr/0101-one-workspace-setting-with-an-auto-default.adr.md)). A workflow author who wants a fixed mode declares `workspace: worktree` or `in_place`.
- `head` as the default base keeps a run offline-safe and starts it from what the person sees; `default_branch` matches Claude Code's `fresh` ([ADR-0104](../adr/0104-a-new-worktree-starts-from-the-main-checkouts-head.adr.md)).
- The engine's lock with a reason keeps `git worktree prune` and other tools' sweeps from dropping the admin data of a paused run's worktree.
- Release split, for the first-release thread: `auto`/`worktree`/`in_place`, the `sibling` root, `head` base, names, start, resume and re-attach, executor pointing and the two disallowed tools, `worktree list` and `path` are first-release; `in_repo` and `path:` roots, `default_branch` and `ref:` bases, `cleanup: on_finish`, `prune --apply`, foreign-worktree scans and `.worktreeinclude` follow. Writer, slot and item worktrees arrive with the units that need them.

## 6. Acceptance criteria

- [ ] WTR-AC-1 `resolve_workspace` returns each row of §2.2 for a fixture workflow and target, with no git write and no model call.
- [ ] WTR-AC-2 Every name of §2.4, including WTR-B4's table and an 81-character task id, passes `git check-ref-format --branch`, and no writer branch has the run branch as a path prefix.
- [ ] WTR-AC-3 WTR-B5 to WTR-B11 and WTR-B14 to WTR-B16 pass against real git worktrees with scripted executors.
- [ ] WTR-AC-4 For each of the four executors, a scripted session records the working directory it was given, and it equals `WorkspaceRecord.path`; the `claude` and `agent-sdk` launches carry the two disallowed tools.
- [ ] WTR-AC-5 No code path calls `git worktree remove --force`, `git branch -D` or `git branch -d`.
- [ ] WTR-AC-6 `run --check`, `worktree list` and `worktree path` create nothing (test compares the repository's refs, worktree list and file tree before and after).
- [ ] WTR-AC-7 Probes P-WTR-1 to P-WTR-4 are recorded in the probe table below before the linked controls are marked `LIVE-PROVEN`.

### Probes

| Id | What | Gates | Result |
|---|---|---|---|
| P-WTR-1 | `claude -p --disallowedTools EnterWorktree,ExitWorktree` leaves neither tool in `system/init` | WTR-B12 | not run |
| P-WTR-2 | A subagent with `isolation: worktree` under `claude -p` creates a worktree, and where | §2.10 | not run |
| P-WTR-3 | The `Agent` tool input field that asks for worktree isolation, as a `PreToolUse` hook sees it | §2.9 `agent-sdk` | not run |
| P-WTR-4 | `agy -p` in a worktree of a repository with `extensions.worktreeConfig` | §2.9 `antigravity` | not run |

## Open questions

| Question | Owner |
|---|---|
| Should a merged writer branch be deleted at the join? The design keeps every branch. | Owner |

## References

