# Implementation plans

Plans say **in what order** the specs are built. A release plan fixes a release's scope, its tracks (one per group of component specs), their phases and dependencies; each track then gets an expanded plan, `<track>.plan.md`, whose rows a coding session follows. Shape and rules: temperspec's [plan rule](../../../temperspec-tgraph/rules/plan.rule.md). A plan is written only against specs that are `ready-for-implementation`; the release plan states that as an entry condition per track.

| Plan | Covers | Status |
|---|---|---|
| [first-release.plan.md](first-release.plan.md) | Release 1: tracks T0 to T11 and the item-by-item feature list, scope from [ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md) | In Progress |
| [t1-foundations.plan.md](t1-foundations.plan.md) | T1: package, source rules, shared types, launch rules, store layouts | Completed |
| [t2-model-and-compiler.plan.md](t2-model-and-compiler.plan.md) | T2: builders, validation, rendering, compiler, diagram model | Completed |
| [t3-executors.plan.md](t3-executors.plan.md) | T3: registry, binding table, preflight, launcher, conformance, Claude Code executor | Completed |
| [t4-durability-and-workspace.plan.md](t4-durability-and-workspace.plan.md) | T4: checkpoints, thread states, lock, aliases, status, wait, worktree, stop | Completed |
| [t5-gate-funnel.plan.md](t5-gate-funnel.plan.md) | T5: run log and cost, checks, judge, guard, gate and human nodes, budgets, scripts, finalizer, runner, outcome gate and record | Completed (offline; live fixtures pending) |
| [t6-run-operations.plan.md](t6-run-operations.plan.md) | T6: CLI core verbs and exit codes (M1), settings, tool grants, feedback and reruns, caller provenance | Completed (offline; live probes pending) |
| [t7-observability.plan.md](t7-observability.plan.md) | T7: run events, detail document, session logs and the store, reports and attention, supervision record, supervision cost | Completed (offline; P-SUP-3 pending) |
| [t10-monitor.plan.md](t10-monitor.plan.md) | T10.1 to T10.4: team sinks, the monitor mod's sources, band, alerts, run view, drill-down, cost tab and prompt-fill actions | In progress (mod API check and live probes pending) |
| [t8-packages-and-install.plan.md](t8-packages-and-install.plan.md) | T8: workflow packages and the registry, first install, stamp, scenarios and lint, audit, blueprint and scaffold | In progress |
| [t9-shell-skills.plan.md](t9-shell-skills.plan.md) | T9: run driver and bootstrap, authoring verbs and the author skill, troubleshooter and install skills | In progress |
| [t12-self-improvement.plan.md](t12-self-improvement.plan.md) | T12: loop records, cause codes and lenses, filing and measurement, lessons; labels, calibration, proposals and trials after T7 and T8 | In progress |
| [live-checks.plan.md](live-checks.plan.md) | T11.2: every live check release 1 still needs on the owner's machine, the command for each, what a pass looks like, and the results table | Not run |
