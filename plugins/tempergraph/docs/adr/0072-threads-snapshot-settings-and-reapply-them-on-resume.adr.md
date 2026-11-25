# ADR-0072 A thread snapshots its operator settings at start and reapplies them on every resume

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A thread may sit paused for days ([DUR](../specs/durability-and-resume.spec.md)). Settings now come from flags, profiles and two files ([ADR-0070](0070-one-catalog-of-run-settings-over-fixed-layers.adr.md)). An operator expects the values a run started with to hold across a resume. If files were read live, editing a user file for tomorrow's runs would change a paused run's model halfway.

## Decision

We will store the flag, profile and file layers' resolved values in the thread's `RunOptions` at start and reapply them on each resume. A resume changes them only by `--set`, `--unset`, `--profile` or `--reload-settings`. The workflow layers follow the workflow content the thread resumes on, as [MIG-B15](../specs/state-and-run-migration.spec.md) already decides. Each segment's `settings_resolved` record lists what changed. How a changed budget meets a counter already spent is fixed per key ([RST-B26](../specs/run-settings-and-overrides.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Snapshot, explicit reload (chosen) | A run's record explains its behaviour; a file edit never surprises a paused run | An operator who fixed a file must say `--reload-settings` |
| Read files live at each resume | No extra flag | Silent behaviour change across a pause |
| Freeze everything, workflow included | Fully reproducible | Contradicts MIG, which lets a fixed workflow apply to a paused thread |

## Decision rationale

| Criterion | Snapshot | Live | Freeze all |
|---|---|---|---|
| No silent change across a pause | yes | no | yes |
| A workflow fix reaches a paused thread | yes | yes | no |
| Effort for the operator | one flag when wanted | none | none |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | Operators edit files for future runs more often than to steer a paused one. | RST-B26 |

## Consequences

- Positive: `config show --thread` predicts a resume exactly.
- Negative: two runs started a minute apart around a file edit differ; the digest shows it.
- Risk: a stale snapshot keeps a value an operator meant to fix everywhere. Mitigation: `status` marks a thread whose snapshot differs from the files now, and `--reload-settings` is one flag.
