# ADR-0096 Exact date formats are the deterministic path; an optional word grammar sits on top; both are model-free and echoed back

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for human-readable dates ("tomorrow at 9", "every weekday"), and then for as much determinism as possible, with no model needed, through an optional strict date format. Words like "next Friday", "at 9" and "03/04" have more than one reading, and a wrong reading on a recurring schedule repeats every period with real spend. Input resolution must call no model (OVR-B15). Natural-language date libraries pick a reading by settings and locale without saying so ([R-095](../research/R-095-scheduling-runs-prior-art-and-gaps.rsrch.md) F26). Standards exist for every form needed: ISO 8601 date-times and durations, RFC 5545 recurrence rules, five-field cron (F24).

## Decision

We will accept timing in **exact formats** that are never interpreted ([SCH-B15, SCH-B16, SCH-B17](../specs/83-schedules.spec.md)): `--at` (ISO 8601 date-time), `--rrule` (an RFC 5545 RECUR subset), `--every` (an ISO 8601 duration), `--cron` (five fields), with `--tz` (IANA), `--starts`, `--until`, `--count`. They never produce a `needs`; scripts, pipelines, packages and the skill use them.

On top, an **optional word grammar** (`--when "every weekday at 8:00"`): a fixed, table-tested English grammar, parsed with no model, where every ambiguity is a `needs` (exit 3) with its readings, never a guess.

Both paths end in one canonical form (a local date-time or an RFC 5545 rule, each with an IANA zone) and one **echo** rendered from that form, never from the input: a sentence, the rule, the zone and its offset, the next three slots in local and UTC time, and every assumption. The skill is optional; when used, it writes exact formats, and the person confirms the engine's echo, not the skill's paraphrase.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Exact formats first, optional fixed word grammar, one echo (chosen) | Fully deterministic path; standard formats any tool can produce; words still available to people | Two input paths to test |
| Word grammar only (the first draft) | One path | A script must write English; every word path can ask |
| Exact formats only | Smallest, strictest | Not human-readable, which the owner asked for |
| A natural-language date library | Many phrasings | Silent guesses that move with versions and locale |
| A model turns words into a rule | Most flexible | Breaks C13; non-deterministic |

## Decision rationale

| Criterion | Exact + optional words | Words only | Exact only | NL library | Model |
|---|---|---|---|---|---|
| A path with no interpretation at all | yes | no | yes | no | no |
| Readable by a non-expert | yes | yes | no | yes | yes |
| Model-free (C13) | yes | yes | yes | yes | no |
| Never guesses silently | yes | yes | yes | no | no |

## Consequences

- Positive: any caller can make a schedule with no model and no question; people keep plain words; every saved schedule was shown in exact form.
- Negative: phrases outside the grammar are refused. Mitigation: the refusal names the nearest phrases and the exact format that would express it.
- Risk: the echo sentence and the rule disagree. Mitigation: the sentence is generated from the rule and re-parsed in a test (SCH-AC1); each exact input equals its word twin (SCH-AC3).

## Assumptions

- English words suffice for the word grammar; another language is another grammar table.
- 09:00 is offered, never applied, when a phrase names no time.
