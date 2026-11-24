# R-100 Native worktrees: what the design has, what git and the executors offer

## Problem statement

The owner asked on 2026-11-20: "Design a parameter which allows native worktree support." The request is read as: one run setting, with a flag, that makes a run work in its own git worktree instead of the person's checkout, with the engine creating and managing that worktree through git ("native" to the engine). Where an executor has a worktree feature of its own, the design must say how the two relate and which one is used. The note answers four questions:

1. What the design already says about workspaces, worktrees and isolation, and what is missing for a person-facing parameter.
2. Which git behaviours a worktree lifecycle must respect (branch names, removal, locking, submodules).
3. What each of the four executors offers natively for worktrees in its current public documentation.
4. Which choices follow, for the spec [WTR](../specs/82-worktree-mode.spec.md) and ADRs [0100](../adr/0100-the-engine-owns-the-run-worktree-executor-worktrees-are-not-used.adr.md) to [0104](../adr/0104-a-new-worktree-starts-from-the-main-checkouts-head.adr.md).

The work was done standalone, without questions to the owner; assumptions are recorded in those ADRs.

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S3 | This design on `main` after PR 13: WSP, CON-B4, CON-B5, CON-B6, CON-B7, RST-B18, RST-B19, RST-B20, RST-B21, ROP-B1 to ROP-B13, RRN-B17, RRN-B18, FIN, ECC-B8, ECC-B9, EAG-B10, EAG-B11, EAG-B5, EAS-B8, THS-B7, GRD-B3, CTS, MAP, WUP | Design set | [specs](../specs/00-overview.spec.md) |
| S4 | Claude Code, "Run parallel sessions with worktrees" | Official docs | https://code.claude.com/docs/en/worktrees.md |
| S5 | Antigravity features page, CLI and App tabs | Official docs | https://antigravity.google/docs/features?tab=cli |
| S6 | "Manage your worktrees with Antigravity 2.0" (2026-06-17) | Third-party blog | https://jeanphi-baconnais.gitlab.io/post/2026-antigravity-worktrees-en/ |
| S7 | Google AI forum, "[Feature Request] Support Git worktrees" (2026-03-02) and linked bug titles | Forum | https://discuss.ai.google.dev/t/feature-request-support-git-worktrees/128062 |
| S8 | "Antigravity agent swarm" guide (updated 2026-08-05) | Third-party vendor guide | https://www.codeagentswarm.com/en/guides/antigravity-agent-swarm |
| S9 | git documentation: `git-worktree`, `git-check-ref-format` | Official docs | https://git-scm.com/docs/git-worktree , https://git-scm.com/docs/git-check-ref-format |
| S10 | Research notes [R-001](R-001-claude-code-cli-headless.rsrch.md), [R-002](R-002-antigravity-cli-headless.rsrch.md), [R-004](R-004-anthropic-messages-api-executor.rsrch.md), [R-005](R-005-claude-agent-sdk-executor.rsrch.md) | Design set | research/ |

## Key findings

### F1 Why a run gets its own tree, and what the design already has

| # | Finding | Confidence |
|---|---|---|
| F1.1 | A run isolated in a git worktree beside the repository, on a branch named from the task id and the workflow, leaves the person's checkout untouched. The shape that serves it: a workflow declares the default mode, an operator switch and per-run options override it; the mode is fixed at the start and stored in state; a resume reuses or re-attaches the worktree; bootstrap copies an include list and runs setup commands; cleanup is never automatic; branches are never deleted. | inferred; WSP in S3 holds part of it |
| F1.2 | One Claude Code worktree per step does not fit, because gates run in the engine process and need one shared tree the engine knows. Worktrees inside the repository are a poor default, because repo-wide tools would index a duplicate tree. | inferred |
| F1.3 | A delivery workflow such as temperspec runs one task in its own git worktree on its own branch: the coding steps commit there and push nothing, and the final stage pushes that branch from the worktree and opens a draft pull request against the default branch or an operator's override. | inferred |
| F1.4 | The design has the mode as `WorkflowSpec.workspace` and `run.workspace` (`in_place` \| `worktree`), spelled `--worktree` / `--in-place`, a `worktree list\|prune` verb, writer worktrees for parallel writers, contest slots and writing map items, and per-executor permission modes that depend on "the engine's own worktree" (S3). | confirmed (S3) |
| F1.5 | Not specified anywhere in S3: where exactly a worktree is created; the base commit of a new run worktree; the writer worktree and branch names; what happens when the run branch already exists or is checked out elsewhere; what a person may do in a paused run's worktree; when and how a worktree may be removed; behaviour in a non-git target beyond "exit 2 if the workflow needs worktrees"; how an executor's own worktree feature is kept from creating a second tree; which workflow field holds the include list and setup commands (WSP passes them as arguments, CON-B4, CON-B5, CON-B6, CON-B7 has no field). | confirmed (search of S3) |
| F1.6 | Two defects in S3: RRN-B17, RRN-B18 names a rerun branch `<branch>~r<n>`, but `~` is not allowed in a git ref name (F2.1); and a writer branch named under the run branch (for example `tg/w/t/w/b` beside `tg/w/t`) cannot exist, because git stores loose refs as files, so a ref cannot also be a directory of refs. | supported (S9 for `~`); the directory/file conflict is inferred from how loose refs are stored and is not stated on the two pages read |

### F2 git behaviours a worktree lifecycle must respect

| # | Finding | Confidence |
|---|---|---|
| F2.1 | Ref names may not contain `~`, `^`, `:`, `?`, `*`, `[`, `\`, a space or a control character, two dots in a row, `@{`; a component may not start with `.` or end with `.lock`; the name may not end with `/` or `.`; `git check-ref-format --branch` checks a candidate. | supported (S9) |
| F2.2 | `git worktree add` refuses a branch that is already checked out in another worktree unless forced. | supported (S9) |
| F2.3 | `git worktree remove` removes only a clean worktree (no modified tracked files, no untracked files) unless forced. The page does not mention ignored files; that they do not block removal is read from its definition of clean. | supported (S9); ignored files `inferred` |
| F2.4 | A worktree can be locked with a reason (`git worktree lock --reason`), and `git worktree prune` never prunes a locked worktree's administrative data; `prune` removes the data of worktrees whose directory is gone; `git worktree repair` fixes links after a move. | supported (S9) |
| F2.5 | The page says a worktree with submodules can be removed only with `--force` and cannot be moved; it does not say that `git worktree add` initializes submodules, and in practice a new worktree's submodules are empty until `git submodule update --init` runs. | supported (S9) for remove and move; initialization `uncertain` |
| F2.6 | `git worktree list --porcelain` is stable across git versions; each record starts with `worktree <path>` and ends with an empty line, with `detached` and `locked [reason]` when true; `HEAD`, `branch` and `prunable` lines appear in its examples. The engine can find worktrees it did not create from it. | supported (S9) |

### F3 Native worktree features per executor

| # | Finding | Confidence |
|---|---|---|
| F3.1 | Claude Code has `--worktree` / `-w [name]`: it creates `.claude/worktrees/<name>/` at the repository root on a new branch `worktree-<name>`, based on the remote default branch by default (`worktree.baseRef`: `fresh`, or `head` for local HEAD; a branch name is not accepted). It works with `-p`; a `-p` run has no exit prompt, so its worktree is never removed and is left locked. Resume returns the session to its worktree. | supported (S4) |
| F3.2 | Claude Code copies gitignored files that match `.worktreeinclude` (gitignore syntax) into a new worktree; `WorktreeCreate` / `WorktreeRemove` hooks replace the git logic (and then `.worktreeinclude` is not processed). | supported (S4) |
| F3.3 | Inside a session, Claude Code has the tools `EnterWorktree` and `ExitWorktree`; subagents may declare `isolation: worktree` (or be asked to use worktrees), which gives each its own worktree from the same base as `--worktree`; a subagent worktree with changes is kept until a sweep governed by `cleanupPeriodDays`. Subagents in a default-location worktree do not load that worktree's own `CLAUDE.md` or rules. | supported (S4) |
| F3.4 | While a Claude Code session is in a worktree it created, isolation rules block edits and git commands that target the main checkout, including from subagents. | supported (S4) |
| F3.5 | The Agent SDK runs the same Claude Code runtime: resume returns a session to its worktree, and a refused resume ends with `startup_failure_reason` `worktree_unverified` or `worktree_resume_refused`. No SDK option to create a worktree is documented; `cwd` selects the directory. The tools of F3.3 are part of the SDK's tool set. | supported (S4, S10 R-005); SDK tool set inferred from the shared runtime |
| F3.6 | The Messages API has no workspace at all: the engine's tool host confines every path to the `workdir` it is given (S3 THS-B7). | confirmed (S3, S10 R-004) |
| F3.7 | Antigravity documents worktree support for the Antigravity App and IDE only ("agents operate in isolated background folders"); the CLI page names no worktree flag or setting. A third-party report places App worktrees under `~/.gemini/antigravity/worktrees` and says they are not removed. A March 2026 feature request asked for worktree support; later bug titles report a failure on repositories with `extensions.worktreeConfig`. A vendor guide for the CLI says worktree isolation is something the user sets up with git, not a CLI feature. | supported (S5); the App path and the `extensions.worktreeConfig` failure are `uncertain` (S6, S7 titles only) |
| F3.8 | `agy` takes its working directory and `--add-dir`; the design already checks `init.cwd` against the workspace and kills a session whose directory differs (S3 EAG). | confirmed (S3, S10 R-002) |

## Conclusions

1. The parameter exists in name (`run.workspace`) but not as a complete design: F1.5 lists what a person cannot predict today. A component spec for the worktree lifecycle closes it; WSP keeps the shapes and the state root.
2. The engine creates and owns the run's worktree with git on every executor. No executor offers what the engine needs: one tree for the whole run that the engine's checks, judges and finalizer share, at a base and branch the engine chooses, removed only when safe. Claude Code's worktree is per session, based on the default branch rather than a chosen commit, never removed under `-p`, and lives inside the repository (F3.1); Antigravity's is an App feature (F3.7); the Messages API has none (F3.6).
3. Executor worktree features must be kept from making a second tree under a step: `EnterWorktree` and `ExitWorktree` are never available to a step, a subagent's worktree request is refused where a gatekeeper can see it, and any worktree that appears during a session is detected from `git worktree list` and reported (F3.3, F2.6).
4. Claude Code's `.worktreeinclude` is a useful existing convention: the engine may read it as an extra include source, keeping its own gitignored-only rule (F3.2).
5. Branch names must be derived from the thread id by a ref-safe flattening, writer branches must not nest under the run branch, and the rerun suffix must change from `~r<n>` (F1.6, F2.1).
6. Removal can be made safe enough to offer as an opt-in: only a clean worktree, never its branch, never a locked or running one (F2.3, F2.4). Branch deletion stays a person's act.
7. Submodules need an explicit bootstrap step, and removal of a worktree with submodules is never forced by the engine (F2.5).

## Open questions

| Question | Owner | Resolution path |
|---|---|---|
| Does `claude -p` with `--disallowedTools EnterWorktree,ExitWorktree` remove both tools from `system/init`, and does a subagent with `isolation: worktree` still get a worktree? | Probe P-WTR-1, P-WTR-2 | Probe on the pinned CLI |
| What is the exact input field of the `Agent` tool that requests worktree isolation, as seen by a `PreToolUse` hook? | Probe P-WTR-3 | Probe on the Agent SDK |
| Does `agy` misbehave in a worktree of a repository with `extensions.worktreeConfig` set? | Probe P-WTR-4 | Probe on the pinned CLI |
