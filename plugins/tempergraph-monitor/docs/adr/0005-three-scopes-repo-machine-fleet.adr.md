# MADR-0005 Three scopes: this repository, this machine, the fleet through a sink

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A monitor that asks for status once, from the session's directory, shows only one state root's runs, and leaves open how runs of other repositories or machines get in. The engine now keeps a machine index of state roots and can push metadata rows and heartbeats to a shared sink ([engine CST](../../../tempergraph/docs/specs/central-run-stats.spec.md)). Logs stay on the machine that ran a run.

## Decision

We will offer `repo` (default) and `machine` scopes for full views, and a fleet tab that reads a configured sink for numbers and live heartbeats only; a run on another machine opens as a read-only card, never a drill-down ([MDS](../specs/data-sources.spec.md), [MCF](../specs/cost-and-fleet.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Repo, machine, fleet-numbers (chosen) | Each scope shows what is honestly available there | Fleet rows cannot be entered |
| Repo only | Simplest | The owner's "all machines in one place" unmet inside Claude Code |
| Fleet with remote drill-down (logs shipped to the sink) | Full view anywhere | Ships commands and outputs off the machine, against the publish boundary |
| A list of extra roots typed by the person | No index needed | Manual; misses new repositories |

## Decision rationale

| Criterion | Three scopes | Repo only | Remote drill | Typed roots |
|---|---|---|---|---|
| Other repositories on this machine | yes | no | yes | yes |
| Other machines | numbers | no | full | no |
| Keeps logs local | yes | yes | no | yes |
| Needs setup | sink for fleet | none | sink + log shipping | per root |

## Consequences

- Positive: a person sees a gate waiting on their other laptop without leaving the session.
- Negative: hashed repository names on a shared sink read as hashes until an operator opts into names.

## Assumptions

- The owner's other machines can share a folder or an OTLP backend; with neither, the fleet tab shows this machine only.

## Revisit when

A team needs to diagnose other machines' runs from one place often enough to justify shipping logs under a separate decision.
