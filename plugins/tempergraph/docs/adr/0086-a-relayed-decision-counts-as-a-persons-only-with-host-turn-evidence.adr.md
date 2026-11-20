# ADR-0086 A relayed decision counts as a person's only with turn evidence from the host

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Contract C6 says only a person decides a pause, and the run driver and orchestrator skills only relay the person's word (SHL-B2, OSK §2.3). Once agent callers are seen as agents ([ADR-0085](0085-classify-callers-by-the-strongest-signal.adr.md)), every relayed answer would look like an agent's own decision, which is as wrong as the reverse. The engine never sees the conversation, and must not store its text ([SEC](../specs/14-security.spec.md)).

Claude Code's `UserPromptSubmit` hook fires each time a person submits a prompt, before the model reads it ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) H4). The tempergraph plugin already ships in that host. The distinction matters: an agent that relays pauses can answer a "verify and continue" alone, while another pause carries the requester's decision.

## Decision

We will record a **decider** apart from the caller on every deciding call ([PRV §2.4](../specs/85-caller-provenance.spec.md)). An agent marks a relayed decision with `--relayed`. The engine then looks in the host session's supervision journal for a **person turn** after the pause was shown and before the call. The plugin's hook writes that turn with its time and, matched locally, which of the open pauses' decision words it contains; never the text. With a turn that names the decision, the decider is `person` (`turn_named`). With a turn that names nothing checkable, it is `person` (`turn_only`). With no turn, it is the agent's own (`claimed`). Widening tools needs `turn_named`. Nothing else is refused on this basis in the first release.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Relay backed by the host's person-turn event (chosen) | No extra step for the person; uses an event only a person's action produces; stores no text | Needs the plugin's hook; hosts without such an event cannot back a relay |
| Trust `--relayed` as given | Simple | An agent's own answer passes as the person's under a new flag |
| Store the prompt text and compare later | Strong evidence | Stores what a person wrote; against SEC; a reader could reconstruct conversations |
| A one-time code shown in the pause and typed back by the person | Proves the person read this pause | A chore on every decision; an agent that shows the code and asks "type it" adds nothing |
| Let the model classify the conversation later | No hook | Public measurement found such classification overestimates human involvement ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) P3) |

## Decision rationale

| Criterion | Host turn | Trust flag | Store text | Code |
|---|---|---|---|---|
| Tells B3's 13 from its 3 | yes | no | yes | yes |
| Stores no person's text | yes | yes | no | yes |
| No new step for the person | yes | yes | yes | no |
| Works without the plugin | no (falls to `claimed`) | yes | no | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| B1 | The hook's input carries the prompt, so the word match can run locally (probe P-SUP-2). Without it relays are `turn_only` at best, and widening by relay is unavailable. | PRV §2.4.1 |
| B2 | A person turn between the pause and the call is good enough evidence that the person saw the pause; the skills show the pause before asking (SHL-B2). | PRV §2.4 |
| B3 | A monitor action fills the prompt for the person to send, so it is a person turn like any other ([monitor MADR-0003](../../../tempergraph-monitor/docs/adr/0003-actions-fill-the-prompt.adr.md)). | PRV §2.4.1 |

## Consequences

- Positive: a person's decision relayed through a conversation keeps counting as the person's, and an agent's quiet "verify and continue" is counted as the agent's.
- Negative: decisions relayed through hosts without a prompt-submit event count as the agent's own.
- Risk: an agent asks "ok?" and treats any reply as consent. Mitigation: `turn_only` is recorded apart, does not allow widening, and is shown in relay quality ([SUP §2.4](../specs/86-supervision-metrics.spec.md)).

## Revisit when

A delegation policy is designed, or a host offers its own record of who approved a tool call.
