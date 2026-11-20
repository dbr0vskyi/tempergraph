# ADR-0096 Parse a fixed When grammar into one exact form and echo it back; ask on every ambiguity

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner wants human-readable dates: "tomorrow at 9", "every weekday", "every Monday". Words like "next Friday", "at 9" and "03/04" have more than one reading, and a wrong reading on a recurring schedule repeats every period with real spend. Input resolution must call no model (contract C13). Natural-language date libraries pick a reading by settings and locale without saying so ([R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) F26).

## Decision

We will parse a **fixed, table-tested English grammar** ([SCH §2.3](../specs/83-schedules.spec.md)) into one canonical form: a `once` local date-time or an RFC 5545 RECUR subset, each with an IANA zone. The engine prints an **echo** rendered from the canonical form (never from the phrase): a sentence, the rule, the zone and its offset, the next three slots in local and UTC time, and every assumption. A phrase with more than one reading is a `needs` (exit 3) with the readings; nothing is saved until the person confirms. The schedule skill may turn free words into a grammar phrase, but the person confirms the engine's echo, not the skill's paraphrase. Five-field cron is accepted as an input and shown beside its sentence.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Fixed grammar, canonical RFC 5545 form, echo and ask (chosen) | Deterministic; testable phrase by phrase; any reader computes the same slots | Fewer phrasings; English only |
| A natural-language date library | Many phrasings, many languages | Silent guesses; results move with library versions and locale |
| A model turns words into a rule | Most flexible | Breaks C13; non-deterministic; a model's reading needs the same echo anyway |
| Cron only | Standard, compact | Not human-readable; no zones or daylight-saving rules; no `once` |

## Decision rationale

| Criterion | Grammar + echo | NL library | Model | Cron |
|---|---|---|---|---|
| Never guesses silently | yes | no | no | yes |
| Readable by a non-expert | yes | yes | yes | no |
| Model-free (C13) | yes | yes | no | yes |
| Same slots in every reader | yes | yes | yes | yes, without zones |

## Consequences

- Positive: every saved schedule was shown to a person in exact form; the skill adds reach without adding trust.
- Negative: phrases outside the grammar are refused. Mitigation: the refusal shows the nearest phrases; the skill rewrites words into the grammar.
- Risk: the echo sentence and the rule disagree. Mitigation: the sentence is generated from the rule, and a test re-parses it (SCH-AC-1).

## Assumptions

- English words suffice for the first slice; another language is another grammar table, not a library.
- 09:00 is offered, never applied, when a recurrence names no time.
