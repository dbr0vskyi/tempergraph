# ADR-0085 Classify every caller by the strongest signal it leaves; a declaration may only lower trust

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner expects that most calls to the engine come from an agent or the orchestrator babysitting a run, not from a person typing ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md)). The design tells an agent from a person by one self-declared flag, `--as-agent` (R-085 D1, D2). An agent that forgets it is recorded as a person: an orchestrating session that answers pauses without the flag has every answer counted as a person's (R-085 B3). Judge labels, widening refusals and every intervention count rest on that flag.

Claude Code marks the processes its tools start, without the model's help: `CLAUDE_CODE_CHILD_SESSION=1` on tool, hook and status-line children, and not on an IDE's integrated terminal (R-085 H1). CI systems mark their jobs. The orchestration supervisor is the engine's own process and can carry a secret. A terminal is a weaker sign of a person. Every one of these can be forged by a process of the same user (H10).

## Decision

We will classify every mutating call into one of `person`, `agent`, `orchestrator`, `pipeline`, `engine` or `unknown`, by the first matching signal of a fixed ladder: an engine-issued supervisor token, the engine's own act, a host marker, a CI marker without a terminal, the caller's declaration of `agent` or `pipeline`, a terminal, and otherwise `unknown` ([PRV-B13](../specs/85-caller-provenance.spec.md)). A declaration can move a caller toward "not a person" but never over a host marker: `--caller person` from a marked agent is refused, and carrying a person's decision has its own path ([ADR-0086](0086-a-relayed-decision-counts-as-a-persons-only-with-host-turn-evidence.adr.md)). Every mutating call writes one `caller` block with the kind, the confidence and the signals seen ([PRV-B16, PRV-B17](../specs/85-caller-provenance.spec.md)); read-only verbs read none of it. `--as-agent` stays as a spelling of `--caller agent`.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Strongest signal, declarations only lower trust (chosen) | An agent that forgets the flag is still seen; honest hosts need no change; refusals fail toward refusal | A host profile per host to keep; `unknown` appears where nothing marks the caller |
| Self-declaration only (today) | Simple | Silent miscounting whenever an agent omits the flag (B3) |
| Terminal means person, else agent | No host knowledge | IDE and pipe cases wrong both ways; a pseudo-terminal passes |
| A signed person token (a person types a code shown at the pause) | Proves a person was at a terminal | A step a person must take on every decision; breaks relayed answers from a conversation, the main way people work |
| Ask the host over a socket | Strong | No host offers it; contradicts the files-and-verbs rule of [ADR-0022](0022-observers-read-files-not-sockets.adr.md) |

## Decision rationale

| Criterion | Ladder | Declaration only | Terminal rule | Person token |
|---|---|---|---|---|
| Catches an agent that says nothing | yes | no | mostly | yes |
| No new step for a person | yes | yes | yes | no |
| Works for the four products as hosts and for CI | yes, `unknown` where unmarked | yes | partly | yes |
| Never upgrades a caller on its own word | yes | no | n/a | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | Provenance is accounting, not security: the operator controls every process on the machine, and the design defends against careless agents, not against the operator. | PRV |
| A2 | Claude Code's child markers stay stable enough to key a host profile on; a change is caught by probe P-SUP-1 and shows callers as `unknown`, never as people. | PRV-B20 |
| A3 | Applications on the Agent SDK or the Messages API that drive the engine are honest enough to declare themselves; an undeclared one is `unknown`. | PRV-B20 |

## Consequences

- Positive: agent interventions are counted as such without relying on skill prose, so judge labels and supervision figures stop absorbing agent answers as a person's.
- Negative: a person driving the engine from a pipe or a detached script is `unknown`, not `person`; they can pass nothing to change that except running it at a terminal.
- Risk: a host changes its markers. Mitigation: probes, and the `callers-unknown` audit rule shows the drop.

## Revisit when

Another host becomes common as a supervisor (Antigravity, P-SUP-5), or a host offers an attested caller identity.
