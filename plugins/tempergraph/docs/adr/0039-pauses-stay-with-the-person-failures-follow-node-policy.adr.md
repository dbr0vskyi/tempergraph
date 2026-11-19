# ADR-0039 In an orchestration, pauses stay with the person; failures follow a declared node policy

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

With many runs at once, pauses and failures overlap. An orchestrating session that may answer pauses can answer every one while the person is away, even a proceed on a gate whose judge never ran. Dynamic workflows have no mid-run input and turn a failed agent into a `null` slot the script may ignore ([R-035](../research/R-035-dynamic-workflows-as-orchestration-model.rsrch.md) D3, D4). tempergraph already records who answered a pause and defers a delegation policy ([HUM](../specs/07-gate-and-human.spec.md)).

## Decision

We will keep every pause, approval node and `ask` failure for a person, answered one at a time through `orchestrate answer`, recorded with `by: person`; `mode: unattended` and `--as-agent` are refused in an orchestration until a delegation policy exists. A failed node applies its declared `on_failure` (`skip_dependants` by default, `continue`, `halt` or `ask`). The supervisor itself re-opens a run only when it ended on an infra cause and only up to the node's `reopen_infra` count, the person's retry given in advance.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Person answers; failure by node policy; infra-only re-open (chosen) | C6 holds by construction; failures never pass silently; no paid rerun of a quality failure | A person must be reachable for every pause |
| Let the skill answer verification pauses | Fewer interruptions | Agent answers no person checked; needs calibrated judges and a C6 amendment first |
| One global policy: stop everything on any failure | Simple | One flaky run stops a day of independent work |
| Ignore failures as dynamic workflows' `null` slots | Never blocks | A report can call a failed graph done |

## Decision rationale

| Criterion | Chosen | Skill answers | Global stop | Ignore |
|---|---|---|---|---|
| C6 holds | yes | no | yes | yes |
| Independent work continues | yes | yes | no | yes |
| Failure visible in the outcome | yes | yes | yes | no |

## Assumptions

- `skip_dependants` is the safest default: it never feeds a dependant missing input and never stops unrelated work.

## Consequences

- Positive: an unattended stretch costs time, not wrong decisions; the outcome `finished_with_failures` is never exit 0.
- Negative: a long orchestration with the person away waits at its first pause on each branch. Mitigation: approvals are placed between waves by design, and the `orchestration_attention` hook can notify the person.

## Revisit when

A delegation policy is designed on calibrated judge data; then `unattended` can be defined against it.
