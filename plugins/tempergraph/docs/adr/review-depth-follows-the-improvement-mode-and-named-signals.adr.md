# Review depth follows the improvement mode and named signals

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner's idea: newly created and dev-mode workflows read sessions to check that prompts and agents work efficiently and as expected; stable mode reads sessions only on signals, fully or partly. The design already splits the loop's triggers by `improvement_mode` ([SIL-B10](../specs/self-improvement.spec.md)), and its stable friction triggers include a new version's first five runs ([research `reading-session-logs-for-self-improvement`](../research/reading-session-logs-for-self-improvement.rsrch.md) B11). A signal can point at the part of a session worth reading, such as the end of a timed-out attempt (B5). Public practice summarizes first and samples (P5).

## Decision

We will set review depth per run by a plan ([SRV-B13, SRV-B14, SRV-B15, SRV-B16, SRV-B5](../specs/session-review.spec.md)) from one workflow setting, `improvement.session_review` (`auto`, `full`, `signals`, `off`; default `auto`):

- **Dev mode** reads `full`: every step and judge session of each final exit, condensed, under a per-run cap, and adds a per-instruction `conformance[]` table.
- **Probation** reads `full` for the units a new version changed, for its first 5 final exits, in either mode; an authoring trial reads `full`.
- **Stable mode** reads `signals`: only the sessions and turn slices a named signal points at (retry bursts and blocked criteria, spent retries, timeouts by shape, tool access and repeats, idle burn and context bloat, cost outliers, agent rescues, a person's pushback or outcome miss, a judge passing unread or at low confidence, unknown tool names), plus one audited session every 20th clean run.
- A signal whose cluster already holds 3 corroborated observations on the version is **saturated** and reads nothing until the version changes.
- Spend is capped per reviewer session in input tokens, per run as a share of the run's own cost and in dollars, and per day in stable mode with SIL's cap.

A person can always ask for a review with `improve review`.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Mode and signals set depth (chosen)** | Matches the owner's split and the existing mode axis; stable spend follows problems; dev authors see everything | Many parameters with no data |
| One sampling rate for every workflow | Simple | Dev authors miss the runs they care about; stable mode pays for clean runs |
| Signals only, in every mode | Cheapest | A new workflow's prompts that "work" but waste turns raise no signal |
| Full reading in every mode | Maximal coverage | Cost follows all spend; stable workflows are by definition the ones that need least |

## Decision rationale

| Criterion | Chosen | One rate | Signals only | Full always |
|---|---|---|---|---|
| Dev-mode coverage the owner asked for | yes | partial | no | yes |
| Stable-mode spend on clean runs | ~0 (audit only) | fixed | 0 | high |
| Follows what is already explained | yes (saturation) | no | no | no |

## Consequences

- Positive: an author building a workflow gets, after every run, which instructions, lessons, skills and subagents were followed.
- Positive: stable workflows pay for reading only where a signal says something went wrong, and stop paying once a cause is explained.
- Negative: dev-mode review roughly adds a judged session per session read, bounded by the share and dollar caps.
- Risk: slices miss the turn that matters. Mitigation: slices merge per session; a person can run `improve review --full`.

## Assumptions

| Id | Assumption | Where it binds |
|---|---|---|
| A1 | No workflow reaches stable mode in release 1, since stable mode needs every gate `ready` ([LIF-B6](../specs/lifecycle-and-evals.spec.md)); stable-mode plans can wait for release 2 | First-release plan X2-26 |
| A2 | The last 40 turns of an attempt usually hold why it failed or was sent back | SRV-B16, SRV-B5 |

## Revisit when

After 20 dev-mode reviews: compare spend to the caps and the share of observations per signal, and set the parameters from data.
