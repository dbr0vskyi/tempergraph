# Implementation plans

Plans say **in what order** the specs are built. A release plan fixes a release's scope, its tracks (one per group of component specs), their phases and dependencies; each track then gets an expanded plan, `<track>.plan.md`, whose rows a coding session follows. Shape and rules: temperspec's [plan rule](../../../temperspec-tgraph/rules/plan.rule.md). A plan is written only against specs that are `ready-for-implementation`; the release plan states that as an entry condition per track.

| Plan | Covers | Status |
|---|---|---|
| [first-release.plan.md](first-release.plan.md) | Release 1: tracks T0 to T11 and the item-by-item feature list, scope from [ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md) | In Progress |
| [t1-foundations.plan.md](t1-foundations.plan.md) | T1: package, source rules, shared types, launch rules, store layouts | Completed |
| [t2-model-and-compiler.plan.md](t2-model-and-compiler.plan.md) | T2: builders, validation, rendering, compiler, diagram model | Completed |
| [t3-executors.plan.md](t3-executors.plan.md) | T3: registry, binding table, preflight, launcher, conformance, Claude Code executor | Completed |
| [t4-durability-and-workspace.plan.md](t4-durability-and-workspace.plan.md) | T4: checkpoints, thread states, lock, aliases, status, wait, worktree, stop | Completed |
