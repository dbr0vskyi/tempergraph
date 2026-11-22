# ADR-0118 The reviewer is tool-less and reads a condensed, scrubbed, datamarked view

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A session log holds the request, file contents, web pages and tool output: all of it can carry instructions aimed at the next model that reads it ([R-110](../research/R-110-reading-session-logs-for-self-improvement.rsrch.md) P7). Session content must never leave the machine except to the model provider that produced it, and nothing from it may cross the publish boundary ([SEC-B8 to SEC-B11](../specs/14-security.spec.md), IMD-B10). A gate judge must never see the producer's transcript (B3). Raw streams are large, dominated by tool output (B4, P6).

## Decision

We will have the reviewer read only a view the engine builds ([SRV-B17, SRV-B18, SRV-B19, SRV-B20](../specs/44-session-review.spec.md)): a header of declarations, the step's prompt or the judge's brief, one line per turn with clipped assistant text, tool names, input summaries, status, sizes and clipped error tails, and the digest; tool outputs left out; every part scrubbed; untrusted parts datamarked and fenced by a random per-review boundary; capped in tokens. The reviewer runs with no tools, no setting sources and no MCP servers, on an executor of the same provider as the session unless the operator allows another. Its output is a fixed block of enum categories, turn numbers, change classes and an anchored confidence; its one-sentence notes stay local. The engine checks every citation against the digest before it keeps an observation. The reviewer is never a gate judge, never runs inside the run it reads, and nothing it writes enters a step prompt or a judge view.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Tool-less reviewer on a condensed datamarked view (chosen)** | An injected instruction has nothing to act with; input bounded; output checkable | Loses detail in tool outputs; the view must be built and tested |
| Reviewer with read tools over the raw files | Can follow up on anything | Injection can steer reads; unbounded input; reads outside the session |
| Raw stream, truncated | No view builder | Tool output crowds out the turns; secrets and request text in bulk |
| Two-model pattern: a quarantined model summarizes, a privileged one decides | Strong isolation | Doubles cost; the reviewer has no privileges to protect in the first place |

## Decision rationale

| Criterion | Chosen | With tools | Raw truncated |
|---|---|---|---|
| Injection impact | none beyond a wrong category, caught by checks | reads and context steering | wrong category |
| Input bounded | yes | no | yes |
| Secrets and bulk text exposed | scrubbed, outputs elided | all | most |
| Output trusted by | engine-checked citations | model | model |

## Consequences

- Positive: the defence does not rely on the model resisting injection, as public practice advises (R-110 P7).
- Positive: free text never reaches filing; only categories and counts do.
- Negative: an environment fault visible only in a long tool output is seen through its 400-character error tail.
- Risk: datamarking reduces but does not remove injection success. Mitigation: no tools, fixed schema, citation check, and a `none_found` never clears a model-free finding (SRV-B8).

## Assumptions

| Id | Assumption | Where it binds |
|---|---|---|
| A1 | Sending a session's own content to a second session of the same provider is within that provider's terms and the owner's privacy expectations | SRV-B18, SRV-B19, SRV-B20 |
| A2 | `claude -p` can be started with no tools and no setting sources, as judges already are ([ECC](../specs/11-executor-claude-code.spec.md)) | SRV-AC6 |
