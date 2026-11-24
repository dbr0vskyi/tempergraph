# ADR-0052 The tool audit compares each session's grant, need and use, judges first

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner named an audit of the tools defined for steps and judges as one thing the audit should do. Tool access is the cause family most catchable before a run: most refusals need no new permission, git calls after a directory change are refused, steps call undeclared tools, and one plugin tool in a judge session can void a complete verdict ([R-050 C4](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md)). Validation already refuses some shapes and warns when a prompt names an undeclared tool ([WFM](../specs/02-workflow-model.spec.md)). What it cannot see is what the host adds to a session and what sessions really called.

## Decision

We will audit tools as three views per session ([TSA](../specs/57-tool-surface-audit.spec.md)): **grant** (declared tools through the executor's map, commands, MCP tools, and for judges the view set, plus ambient tools the host adds), **need** (names in the model-facing text and tools implied by artifact kinds) and **use** (recorded calls, refusals by shape, and the tool list each session reported at start). A finding is a mismatch between views. Judge sessions are checked against their **reported start tool list**, so an exposed tool is found before it is ever called. Remedies that widen a grant are marked as widening.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Grant, need and use per session (chosen) | Finds missing, unused, exposed and refused tools; works on all four executors through `tool_map`; uses data executors already report | Needs history for the strongest rules |
| Static check of prompts against declarations only | Already exists in validation | Misses ambient tools and real refusals, the two costliest cases |
| Enforce declared tools everywhere instead | Prevents undeclared calls | Not every executor can enforce; enforcing before the logs are clean refuses calls a step needs; does not find over-grants or missing grants |
| Scan MCP tool descriptions as MCP-Scan does | Finds poisoned descriptions | Must start each server; sends or stores descriptions; out of a read-only, names-only verb |

## Decision rationale

| Criterion | Three views | Static only | Enforce | Description scan |
|---|---|---|---|---|
| Finds the judge-voiding case before it happens | yes | no | partly | no |
| Finds over-grants (start time, context, reach) | yes | partly | no | no |
| Read-only, names only | yes | yes | n/a | no |
| Same on four executors | yes | yes | no | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| T1 | Every executor's `session_started` event lists the tools the session holds, as [SSN-B7](../specs/25-session-contract.spec.md) requires. Where an executor lists none, the judge rule falls back to the host probe. | TSA-B1 |
| T2 | Refusal shapes can be classed from the tool name and a scrubbed input summary (spec 30, PR 7) without reading model text. | TSA-B7 |

## Consequences

- Positive: a judge exposure that voids a verdict is visible from the first run that shows the tool, or before any run where the probe can list plugin tools; least privilege becomes measurable.
- Negative: the strongest rules wait for history and, for refusal classes, for the activity journal.
- Risk: authors drop a tool the audit calls unused that a rare path needs. Mitigation: `granted-never-used` needs 10 runs and stays a warning.

## Revisit when

An executor can enforce grants by default, or the probe can list plugin tools on every executor.
