# Install each engine release beside the current one and switch by one atomic pointer

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for a command that updates the engine, one part of which is updating the CLI installation. An update that installs into one managed environment in place ([LIF](../specs/lifecycle-and-evals.spec.md)) fails two ways: an interrupted install leaves a half environment, and on Windows the engine's loaded libraries are locked while the installer replaces them. Runs are long-lived, so at any update some process may be running on the environment being replaced, and nothing allows a rollback. The shim found the engine by sorting plugin cache folders, which change with every plugin version and are deleted 14 days later ([research `updating-a-tool-with-long-lived-runs`](../research/updating-a-tool-with-long-lived-runs.rsrch.md) U4).

## Decision

We will install every engine release into its own environment folder under `~/.tempergraph/engines/`, verify it there, and make it current by replacing one pointer file atomically ([UPD-B11, UPD-B12, UPD-B13](../specs/engine-update.spec.md)). The shim lives in `~/.tempergraph/bin/` and reads the pointer. The previous release stays as `previous` for rollback; a release a live process or a pinned thread uses is kept until neither needs it; others are removed only by `update --prune-engines`.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Side-by-side environments and an atomic pointer (chosen) | A failed install changes nothing; rollback is a switch; running processes keep their files; Windows locks never meet the installer; pins of [ADR `threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them`](threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them.adr.md) have somewhere to run | Disk for two or more environments (a few hundred MB each with the extras); one more folder to explain |
| In-place upgrade of one environment | Simplest; least disk | Half-installed environments; Windows locks; a live run's imports can change under it; no rollback |
| Refuse to update while any run is live | Keeps in-place safe | A paused thread or a long orchestration blocks every update for days; a person must drain runs across every repository |
| Leave installation to a package manager (pip, uv tool, pipx) | Familiar; less engine code | One environment per tool, replaced in place; no pinning of old threads; the plugin channel ships a staged copy, not an index release |

## Decision rationale

| Criterion | Side by side | In place | Refuse while live | Package manager |
|---|---|---|---|---|
| A failed install leaves the machine working | yes | no | no | partly |
| Live runs unaffected | yes | no | yes, by blocking | no |
| Rollback | yes | no | no | partly (reinstall an older version) |
| Room for pinned threads | yes | no | no | no |
| Disk cost | higher | lowest | lowest | low |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | "Update the CLI installation" means the shim, the managed environment and the optional executor packages, not the executor CLIs (`claude`, `agy`), which their own installers update and the executor compatibility table only checks. | UPD-B10 |
| A2 | A few hundred MB per kept environment is acceptable on a developer machine; CI images build one environment and skip this layout. | UPD-B11, UPD-B12, UPD-B13, UPD-B16 |
| A3 | Moving the shim out of the plugin cache is acceptable; the installer skill writes the `PATH` block once to `~/.tempergraph/bin/`. | UPD-B11, UPD-B12, UPD-B13, SHL |

## Consequences

- Positive: an update is safe at any moment; the update report can say exactly which processes stay on which engine.
- Negative: more disk, and a prune verb a person has to run.
- Risk: old environments pile up. Mitigation: the report shows their count and size; only unreferenced ones are candidates, and `store usage` lists them.

## Revisit when

A Python-package distribution channel ships and owns installation, or disk use of kept environments becomes a complaint.
