# Session logs are read model-free first, and by a model only on a plan

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — (amends the evidence rule of [SIL-B8](../specs/self-improvement.spec.md) and [SEC-B8 to SEC-B11](../specs/security.spec.md)) |

## Context

Every step and judge session keeps its full stream (`raw.jsonl`) and a normalized activity journal locally ([LOS-B7, LOS-B8, LOS-B9](../specs/local-observability-store.spec.md)), but the self-improvement loop reads only run-log records, the ledger and findings ([SIL-B17, SIL-B18](../specs/self-improvement.spec.md)). The owner asked when reading session logs would help and proposed conditional parts. Reading session logs belongs inside the engine, beside the runs it reads, not in a separate transcript pipeline, and most levers found by reading streams by hand are counts ([research `reading-session-logs-for-self-improvement`](../research/reading-session-logs-for-self-improvement.rsrch.md)). Classification rests on names and numbers, not text (B6), and a model's attribution of a failure to a step is unreliable (P3).

## Decision

We will read session logs in two layers ([SRV](../specs/session-review.spec.md)). A **session digest**, model-free, runs over every session at every exit in both modes and writes names, enums, counts and keyed digests only; its facts become cause codes that file through SIL like any other. A **session review**, by a model, runs only when a review plan names sessions or slices of them, and never classifies a cause on its own. The loop child, the recorder and the reviewer are the only readers of session logs; the review's text is evidence-class.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Digest on every exit, review on a plan (chosen)** | Half the useful observations at near-zero cost; the model reads only where code cannot see; publishes nothing new but codes | Two mechanisms; digest rules must be written and kept |
| Keep records only (today) | Simplest; no new privacy surface | Cannot see prompt misreads, dead ends or judges that do not look; the cases the owner named stay invisible (research `reading-session-logs-for-self-improvement` B9) |
| A model reads every session of every run | Sees everything | Cost scales with all spend; a flag nearly every run raises selects nothing (B10); model attributions are unreliable (P3) |
| Use the executor's native transcript store | No duplicate data | Four formats, may be off under judge isolation, none for `messages-api` ([ADR `one-local-store-layout-with-a-manifest`](one-local-store-layout-with-a-manifest.adr.md)) |

## Decision rationale

| Criterion | Chosen | Records only | Model reads all |
|---|---|---|---|
| Sees prompt and agent misuse | yes, on a plan | no | yes |
| Cost per run | digest ≈ 0, review capped | 0 | unbounded |
| Classifies from names and numbers (B6) | yes | yes | no |
| New text across the publish boundary | none | none | risk |

## Consequences

- Positive: new model-free causes (`tool_repeat`, `idle_burn`, `shell_for_files`, `context_bloat`, `timeout:<shape>`, `judge_unread_pass`, `retry_same_path`) file with the same rules as today's.
- Positive: a timeout sort and a record-only loop detector exist as digest fields.
- Negative: SEC-B8 to SEC-B11's evidence rule widens to session logs and review evidence; a second source test is needed (SRV-AC4).
- Risk: digest thresholds have no data. Mitigation: parameters with provenance `default_no_data` ([IMD-B23](../specs/improvement-data.spec.md)), and digest causes of class `designed` are recorded, not filed.

## Assumptions

| Id | Assumption | Where it binds |
|---|---|---|
| A1 | The activity journal's tool input summaries and the stream's turn usage are enough to compute every digest field without reading tool outputs | SRV-B11 |
| A2 | Reading local logs on the owner's machine by the owner's engine is acceptable, as the supervision journal already reads host transcripts for numbers ([ADR `a-supervision-journal-written-by-the-host-not-by-read-only-verbs`](a-supervision-journal-written-by-the-host-not-by-read-only-verbs.adr.md) C2) | SRV-B11 |

## Revisit when

The first live dev-mode runs show how many review observations a digest cause would have found anyway; if most, narrow the review further.
