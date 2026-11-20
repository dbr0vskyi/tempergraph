# ADR-0102 Worktrees live beside the repository by default, with names derived ref-safe from the thread id

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The design said a run worktree sits "beside the repository" on branch `tg/<workflow>/<task_id>` but gave no path, no flattening rule and no names for writer worktrees. It also named rerun branches `<branch>~r<n>`, and `~` is not allowed in a git ref; and a writer branch nested under the run branch cannot coexist with it ([R-100](../research/R-100-native-worktrees-and-executor-worktree-features.rsrch.md) F1.6, F2.1). Some hosts allow writes only inside the project folder; Claude Code uses `.claude/worktrees/` there.

## Decision

We will place run worktrees under `<parent>/<repo>.worktrees/` by default, offer `in_repo` (`.claude/worktrees/tg-…`, excluded through `.git/info/exclude`) and an absolute `path:` root, and derive every folder and branch name from the thread id by one flattening rule checked with `git check-ref-format`. Writer, slot and item names add a suffix (`--w-<name>`) rather than a child path, and reruns use `-r<n>` ([WTR §2.4](../specs/82-worktree-mode.spec.md)). No option sets a path or branch name directly.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Sibling folder by default, two opt-in roots, derived names (chosen) | Repo-wide tools see no duplicate tree; works where only the project folder is writable; no typed text reaches git | Three roots to test |
| Inside the repository by default | One folder to find | Indexers and searches see a second copy  |
| Under the state root | Already gitignored | The tool host refuses writes inside the state root ([THS §2.2](../specs/22-tool-host.spec.md)) |
| Let the person name the branch | Familiar | Typed text on git's argv; collisions; names that git refuses |

## Decision rationale

| Criterion | Sibling + options | In repo | State root | Person names |
|---|---|---|---|---|
| No duplicate tree for repo tools by default | yes | no | no | — |
| Every name valid for git | yes | yes | yes | no |
| Works on a host that writes only in the project | with `in_repo` | yes | no | — |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | The parent folder of the main checkout is usually writable by the person. When it is not, `--worktree-root in_repo` or `path:` is the remedy, named in the refusal. | WTR §4 |
| A2 | Changing the rerun branch suffix from `~r<n>` to `-r<n>` breaks nothing, since no code exists. | RRN §2.4 |

## Consequences

- Positive: names are predictable from the thread id, so a person or a monitor finds a run's tree without reading state.
- Negative: an 80-character limit with a hash suffix makes the longest names less readable.
- Risk: two task ids flatten to the same name. Mitigation: the start is refused (`name_collision`).
