# ADR-0100 The engine owns the run's worktree; executor-native worktrees are not used

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for "a parameter which allows native worktree support". The design already ran a run in an engine worktree ([WSP](../specs/workspace-and-concurrency.spec.md)), but did not say how this relates to worktree features the executors now ship. Claude Code has `--worktree` / `-w`, `.worktreeinclude`, `EnterWorktree` / `ExitWorktree` tools and subagent `isolation: worktree`; the Agent SDK runs the same runtime; Antigravity has worktrees in its App, not its CLI; the Messages API has no workspace ([R-100](../research/R-100-native-worktrees-and-executor-worktree-features.rsrch.md) F3). "Native" could mean either "built into the engine" or "the executor's own feature".

## Decision

We will read "native" as built into the engine: the engine creates, records, re-attaches and removes the run's worktree with git, the same way on all four executors, and points each executor at it through its working directory ([WTR-B25](../specs/worktree-mode.spec.md)). The engine never passes an executor's worktree option, makes `EnterWorktree` and `ExitWorktree` unavailable to steps, denies a subagent's worktree request where a gatekeeper sees it, and reports any worktree that appears during a session as foreign without touching it. The engine reads Claude Code's `.worktreeinclude` as an extra include source.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Engine-owned worktree, executor features blocked (chosen) | One tree for the whole run that checks, judges and the finalizer share; same on four executors; base and names chosen by the engine | The engine keeps its own git code; two probes needed to confirm the block |
| Use Claude Code's `--worktree` per session on `claude` and `agent-sdk` | No engine git code for those executors | One tree per session, not per run; based on the default branch; never removed under `-p`; nothing equivalent on Antigravity's CLI or the Messages API |
| Let the executor choose (native where available, engine elsewhere) | Uses each product's feature | Two behaviours for one setting; the gate's tree differs by executor; resume differs |
| Leave executor features alone | Simplest | A step can move its work into a tree the check never sees |

## Decision rationale

| Criterion | Engine-owned | Claude `--worktree` | Mixed | Leave alone |
|---|---|---|---|---|
| One tree per run, shared by gates | yes | no | partly | yes, unless a step leaves it |
| Same on four executors | yes | no | no | yes |
| Base and branch chosen by the run | yes | no (default branch, `worktree-<name>`) | partly | yes |
| Safe cleanup | yes | no under `-p` | partly | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | "Native worktree support" means the engine supports worktrees itself, switched by one parameter; it does not require the executor's own feature. | WTR |
| A2 | `--disallowedTools` removes `EnterWorktree` and `ExitWorktree` from a `claude -p` session (probe P-WTR-1). | WTR-B25 |
| A3 | A step that needs several trees is a writer branch or a contest, never a subagent worktree. | WSP-B11, WSP-B12 |

## Consequences

- Positive: a run's workspace means the same thing on every executor, and no step works in a Claude Code worktree of its own.
- Negative: projects that already rely on `.claude/worktrees` see a second convention; `in_repo` places engine worktrees there to soften it ([ADR-0102](0102-worktrees-beside-the-repository-with-derived-ref-safe-names.adr.md)).
- Risk: an executor adds a new way to create a worktree. Mitigation: the foreign-worktree scan reports it on the first run.

## Revisit when

An executor offers a per-run worktree at a chosen base with a programmatic remove, on every executor the engine supports.
