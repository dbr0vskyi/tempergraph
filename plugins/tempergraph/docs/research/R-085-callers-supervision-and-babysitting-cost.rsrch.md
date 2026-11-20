# R-085 Who calls the engine, how much supervision a run needs, and what babysitting costs

## Problem statement

The owner wrote on 2026-11-20: "In most cases human will not directly call tempergraph but through agents or orchestrator which will be babysitting the run - we need to investigate how we could distinguish those cases and measure the amount of supervision, human in the loop or extra cost spent on agentic babysitting, this is also crucial metrics for a workflow."

The request is read as three questions:

1. **Caller provenance.** How does the engine tell who made each call and each intervention on a run (start, resume, decision, feedback, ruling, grant, override, rewind, rerun, approval, answer to an ask, stop)? The candidates are a person at a terminal, an agent acting for a person, the orchestration supervisor, a pipeline job and the engine itself. How reliable is each signal, how can it be missing or spoofed, and how is a person's decision relayed by an agent told apart from a decision the agent made on its own?
2. **Supervision measures.** Per run and per workflow: how many times and how long people touched a run, how many interventions agents made, how long runs waited on people, and what the supervising agent itself spent (tokens and money for polling, reading logs, diagnosing, resuming and relaying), given that this spend happens outside the engine and the supervising session may be any of several hosts.
3. **Where the measures land.** The run log, the ledger, the cross-machine stats, the monitor, the audit, the evals, the improvement loop, and the promotion of a workflow from local runs to a pipeline ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)), since the owner's lifecycle is that a workflow improves until it needs less human-in-the-loop and then moves to the pipeline.

The work was done standalone, without questions to the owner; assumptions are recorded in [ADR-0085](../adr/0085-classify-callers-by-the-strongest-signal.adr.md) to [ADR-0089](../adr/0089-supervision-is-a-promotion-and-improvement-measure.adr.md).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S2 | This design on `main` after PR 12: HUM-B6, CLI `--as-agent`, RCT-B5, FBK `source`, RST widening rules, EVT records, CST rows, ORC/OSK, ADR-0041, ARC `interventions-per-run` | Design set | [specs](../specs/00-overview.spec.md) |
| S3 | Claude Code environment variables: `CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_REMOTE` | Official docs | https://code.claude.com/docs/en/env-vars |
| S4 | Claude Code hooks: common input fields, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SessionEnd`, hooks inside subagents carry `agent_id` | Official docs | https://code.claude.com/docs/en/hooks |
| S5 | Claude Code status line input: `session_id`, `transcript_path`, `cost.total_cost_usd` (client-side estimate), `context_window.current_usage` | Official docs | https://code.claude.com/docs/en/statusline |
| S6 | Anthropic, "Measuring AI agent autonomy in practice" (2026-02-18) | First-party research | https://www.anthropic.com/research/measuring-agent-autonomy |
| S7 | Feng, McDonald, Zhang, "Levels of Autonomy for AI Agents" (arXiv 2506.12469v2, 2025-07-28) | Paper | https://arxiv.org/abs/2506.12469 |
| S8 | OpenTelemetry, "Environment Variables as Context Propagation Carriers" (spec 1.62.0, release candidate) and the stabilization post (2026-09-11) | Standard | https://opentelemetry.io/docs/specs/otel/context/env-carriers/ , https://opentelemetry.io/blog/2026/environment-variable-context-propagation/ |
| S9 | Research notes [R-001](R-001-claude-code-cli-headless.rsrch.md), [R-002](R-002-antigravity-cli-headless.rsrch.md), [R-004](R-004-anthropic-messages-api-executor.rsrch.md), [R-005](R-005-claude-agent-sdk-executor.rsrch.md): how each product reports usage | Design set | research/ |

## Key findings

### Part 1: what the design already has

| # | Finding | Confidence |
|---|---|---|
| D1 | The intervention row of every accepted resume records who resumed: `person`, `auto_reopen`, `event`, `deadline`, `rewind`, or `agent` "when the caller declares itself one" ([HUM-B6](../specs/07-gate-and-human.spec.md)). The only agent signal is the self-declared `--as-agent` flag ([CLI §2.1](../specs/17-engine-cli.spec.md)). An agent that omits it is recorded as a person. | confirmed (S2) |
| D2 | `stop --as-agent` is recorded on `stop_requested` ([RCT-B5](../specs/32-run-control.spec.md)); rulings record `by` ([CON §2.12](../specs/01-contracts.spec.md)); labels from an `--as-agent` answer get `source=agent` and are kept out of judge figures ([FBK-B2](../specs/41-feedback-and-judge-reliability.spec.md)); a declared agent cannot widen tools ([RST §2.8](../specs/80-run-settings-and-overrides.spec.md)). Each rests on D1's flag. | confirmed (S2) |
| D3 | Run origin (`cli`, `skill`, `batch`, `orchestration`, `ci`, …) is recorded once per thread ([DUR §2.2](../specs/09-durability-and-resume.spec.md)), and `parent` names the orchestration node ([EVT §2.2](../specs/30-run-events.spec.md)). Origin says how the thread started, not who made each later call. | confirmed (S2) |
| D4 | The orchestration supervisor is model-free and answers no gate (C16); every pause in an orchestration is answered by a person through `orchestrate answer`, recorded `by: person` ([ADR-0039](../adr/0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md)). The skill passes the person's word, but the engine cannot tell whether the word came from the person. | confirmed (S2) |
| D5 | The cross-machine run row carries `wall_s`, `agent_s` and `person_wait_s`; the heartbeat and the detail document carry `waiting_for_person_s` ([CST §2.2](../specs/34-central-run-stats.spec.md), [RDD §2.3](../specs/31-run-detail-document.spec.md)). There is no count of touches by kind, no agent-intervention count, no supervision cost. | confirmed (S2) |
| D6 | ADR-0041's promotion criteria count "person interventions per run (escalations and budget pauses, not approvals)" and the audit has `interventions-per-run` over 1.0 ([ARC §2.6](../specs/56-audit-rule-catalog.spec.md)). Both count person interventions only, so a run babysat by an agent looks autonomous. | confirmed (S2) |
| D7 | OSK-AC-4 asks that the orchestrating session's own cost be at most 3% of the runs' cost on a live orchestration, but no document says how that cost is measured. ADR-0037 cuts wakes; nothing records what a wake costs. | confirmed (S2) |
| D8 | Contract C13: read-only verbs (`status`, `events`, `facts`, `wait`, `logs`, `attention`) create nothing. The engine therefore cannot count an agent's polling from inside those verbs. | confirmed (S2) |

### Part 2: what babysitting costs and hides

| # | Finding | Confidence |
|---|---|---|
| B1 | One orchestrating session over five days (92 h, 1,372 calls) cost about $130, and its 19 helper agents about $147: roughly 15 to 18% on top of about $1.5K of run cost. Only 12 of 30 runs were fully priced. | supported (S1, one session) |
| B2 | 270 notifications woke that session; 148 calls came after five idle minutes and re-wrote its 117K-token context into the cache, about 62% of its own cost. The cost of babysitting is mostly re-reading context after a wake, not the calls themselves. | supported (S1) |
| B3 | With the person away, the orchestrating session answered all 16 pauses; 13 were "verify and continue" and 3 were real decisions about intent. The engine counted all 16 as a person's. | supported (S1) |
| B4 | A single session spent about 23 hours doing what the loop left undone (ordering issues, writing context, launching, resuming, verifying, merging). "None of it is in a run's record or cost, so the loop cannot learn from it." | supported (S1) |

### Part 3: signals a caller leaves

| # | Finding | Confidence |
|---|---|---|
| H1 | Claude Code sets `CLAUDECODE=1` in every subprocess it spawns (Bash and PowerShell tools, hook and status line commands, stdio MCP servers), and IDE extensions also set it in their integrated terminals. `CLAUDE_CODE_CHILD_SESSION=1` is set for Bash, PowerShell, Monitor, hook and status line children and, unlike `CLAUDECODE`, not by IDE terminals. So `CLAUDE_CODE_CHILD_SESSION` separates "a model's tool call" from "a person typing in an IDE terminal". | supported (S3, verbatim) |
| H2 | `CLAUDE_CODE_SESSION_ID` is exported to Bash, hook and stdio MCP children and matches the hook input's `session_id`. | uncertain (S3, read from a summary of the page; probe P-SUP-1) |
| H3 | Every hook receives `session_id`, `transcript_path`, `cwd`, `permission_mode` and `hook_event_name`; hooks inside a subagent also get `agent_id` and `agent_type`. Plugin hooks run with `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA`. | supported (S4) |
| H4 | `UserPromptSubmit` fires when a person submits a prompt, before the model sees it; the hook can block it or add context but not rewrite it. It is the only host event that marks a person's turn. Whether its input carries the prompt text was not read in full. | supported for the event (S4); uncertain for the `prompt` field (probe P-SUP-2) |
| H5 | `PostToolUse` fires after a tool call with the tool's input and response; a hook matching `Bash` can see that the command was a `tempergraph` call and how large its output was. | supported (S4, shape not read in full; probe P-SUP-3) |
| H6 | Hook input carries no token usage or cost. The session transcript at `transcript_path` holds each assistant message with its usage; the status line input carries `cost.total_cost_usd`, a client-side estimate at list price for the whole session. | supported (S4, S5) |
| H7 | The Agent SDK returns a result message with usage and `total_cost_usd`; the Messages API returns usage per response; Antigravity reports tokens, not cost. A supervising application on either library can report its own usage exactly; one on Antigravity reports tokens at best. | supported (S9) |
| H8 | OpenTelemetry defines environment variables (`TRACEPARENT`, `TRACESTATE`, `BAGGAGE`) to carry trace context into child processes, for command-line tools and CI among others; it is a release candidate, not stable, and says values are untrusted and not for secrets. | supported (S8) |
| H9 | A terminal on standard input and output is the usual mark of a person, and the Bash tool of an agent host usually has none; any process can fake one with a pseudo-terminal. CI systems set `CI=true` and their own variables (`GITHUB_ACTIONS`, `GITLAB_CI`, `BUILDKITE`, …). | inferred (common practice) |
| H10 | Every local signal (environment, terminal, flags, files under the user's home) can be set by any process of the same user. No signal proves a person; some prove an agent, because an honest host sets them without the model's help. | inferred |

### Part 4: public practice on measuring autonomy

| # | Finding | Confidence |
|---|---|---|
| P1 | Anthropic measured autonomy in practice by human-initiated stops (interrupts), agent-initiated stops (asking for clarification), auto-approve use and turn length, and found autonomy is "an emergent characteristic of a deployment", not a model property. Internal use saw human interventions per session fall from 5.4 to 3.3 while success on the hardest tasks doubled. | supported (S6) |
| P2 | In the same study, experienced users auto-approved more (from about 20% to over 40% of sessions) and also interrupted more (about 5% to 9% of turns): less approval does not mean less supervision. Counting only approvals undercounts supervision. | supported (S6) |
| P3 | Human involvement there was classified per tool call by a model and called an upper bound because the classifier overestimated involvement. Records written at the moment of the act beat a later classification. | supported (S6) |
| P4 | Feng, McDonald and Zhang define five levels by the user's role: operator, collaborator, consultant, approver, observer. The level is a design choice, separate from capability, and can be assessed by "assisted evaluations": run with no help, then add involvement (approvals first, then consultation) until the task succeeds, and assign the level from the successful round's logs. They propose autonomy certificates that cap the level and must be renewed when tools or environment change. | supported (S7; sections 4–5 from a summary) |
| P5 | P4's assessment is close to tempergraph's own promotion idea (ADR-0041): measured runs, a stamp, a void on change. What tempergraph adds is that its runs record each involvement as it happens, so the level is read from records, not from a separate evaluation round. | inferred |

## Conclusions

1. **Distinguishing callers is possible without trusting the model.** Claude Code, the most likely supervising host, marks its children (`CLAUDE_CODE_CHILD_SESSION`, H1) without the model's help, and tells IDE terminals apart. The engine can classify each call by the strongest signal present: an engine-issued supervisor token, a host marker, a CI marker, a terminal, then the caller's own declaration. A declaration may only lower trust (say "I am an agent"), never raise it over a host marker. With no signal the caller is `unknown`, never assumed a person. [PRV](../specs/85-caller-provenance.spec.md), [ADR-0085](../adr/0085-classify-callers-by-the-strongest-signal.adr.md).
2. **A relayed decision needs host evidence.** An agent saying "the person said proceed" is a claim. The host's `UserPromptSubmit` event (H4) shows that a person's turn happened after the pause was shown and before the call, and a local check can say whether that turn named the decision, keeping a boolean, never the text. Only then is the decision counted as the person's; a claim without it counts as the agent's own. [ADR-0086](../adr/0086-a-relayed-decision-counts-as-a-persons-only-with-host-turn-evidence.adr.md).
3. **Babysitting cost must be measured where it is spent, outside the engine.** The engine's read-only verbs must stay write-free (D8), and hook input carries no usage (H6). The plugin's host hooks can write a supervision journal of engine calls, person turns and per-message usage read from the transcript; library-based supervisors can report their own usage through one writing verb; the model-free supervisor and a scripted pipeline cost zero by construction; anything else is `unmeasured`, never zero. [SCO](../specs/87-supervision-cost.spec.md), [ADR-0087](../adr/0087-a-supervision-journal-written-by-the-host-not-by-read-only-verbs.adr.md).
4. **Attribution must count the re-read.** B2 shows most of the cost is the context re-write after a wake. Attribution therefore reports two figures per thread: the **marginal** tokens of the calls about it (the issuing output, the result read, and the cache re-write of a wake it caused) and the **turn total** of the turns involved, never summed. [ADR-0088](../adr/0088-attribute-supervision-spend-by-marginal-tokens-beside-turn-totals.adr.md).
5. **Supervision is measured on every decider, not only people.** D6 and B3 show that counting person interventions alone makes an agent-babysat run look autonomous. Every touch is counted, by kind (designed, such as an approval or an ask, against undesigned, such as an escalation, a grant or a rewind) and by decider. A run's supervision level is read from its records, on the five-role scale of P4. [SUP](../specs/86-supervision-metrics.spec.md).
6. **The measure belongs in promotion and in the improvement loop.** Promotion to `local-stable` and to `pipeline` gains criteria on undesigned touches by anyone, on the agent's own decisions, and on the supervision cost share; an agent's repeated "verify and continue" answers become findings the loop clusters, because B3's 13 of 16 were workflow faults a check could have settled. [ADR-0089](../adr/0089-supervision-is-a-promotion-and-improvement-measure.adr.md).

## Coverage table: the request against the design after specs 85 to 87

| Ask | Before | After |
|---|---|---|
| Tell a direct person from an agent | `--as-agent` only, self-declared (D1) | Caller kinds and the signal ladder ([PRV §2.1–2.3](../specs/85-caller-provenance.spec.md)) |
| Tell the orchestrator or a pipeline | Origin per thread (D3) | Per call: supervisor token, CI markers ([PRV §2.2](../specs/85-caller-provenance.spec.md)) |
| Relayed decision against the agent's own | Not possible | Decider with turn evidence ([PRV §2.4](../specs/85-caller-provenance.spec.md)) |
| Every intervention attributed | Resume, stop, ruling, grant (partly) | Every mutating call writes a `caller` block ([PRV §2.5](../specs/85-caller-provenance.spec.md)) |
| Human touches: counts and time | `person_wait_s` only (D5) | Touch counts by kind and decider, latency per pause ([SUP §2.2](../specs/86-supervision-metrics.spec.md)) |
| Agent interventions | Counted apart in reports (HUM-AC-4) | Counted per kind; agent's own decisions on undesigned pauses as a rate ([SUP §2.2](../specs/86-supervision-metrics.spec.md)) |
| Babysitting cost | Not measured (D7) | Supervision journal, attribution, two figures, share of run cost ([SCO](../specs/87-supervision-cost.spec.md)) |
| Across four executors and hosts | — | Per-host sources table ([SCO §2.3](../specs/87-supervision-cost.spec.md)) |
| Run log, ledger, stats, monitor | Partial (D5) | `caller` blocks, ledger `supervision{}`, CST `supervision` row, RDD and monitor blocks ([SUP §2.5](../specs/86-supervision-metrics.spec.md)) |
| Audit, evals, improvement loop | Person rate only (D6) | Rules on the agent's own decisions, polling and cost share; eval runs answered by fixtures; loop causes `agent_decided:<cause>` ([SUP §2.6](../specs/86-supervision-metrics.spec.md)) |
| Promotion | Person interventions (D6) | Supervision criteria ([SUP §2.7](../specs/86-supervision-metrics.spec.md), ADR-0089) |

## Open questions

| Question | Owner | Settles it |
|---|---|---|
| Is `CLAUDE_CODE_SESSION_ID` present in a Bash tool child of every Claude Code surface (CLI, IDE, desktop, cloud), and in the children of an Agent SDK session? | Implementer | Probe P-SUP-1 ([PRV §5](../specs/85-caller-provenance.spec.md)) |
| Does `UserPromptSubmit` input carry the prompt text, so the decision-word check can run locally? | Implementer | Probe P-SUP-2 |
| Does `PostToolUse` input carry the command and the response size for `Bash`? | Implementer | Probe P-SUP-3 |
| Does Antigravity mark its children or offer hooks with a session id, so an `agy` session supervising a run can be classified and costed? Until then it is `unknown` and `unmeasured`. | Implementer | Probe P-SUP-5 |
| Should an agent's own decision on an undesigned pause be refused once the delegation policy exists? This note keeps it allowed and recorded, as today. | Owner | Delegation policy (deferred, [R-006](R-006-planned-work-coverage.rsrch.md)) |
| Are the promotion thresholds on supervision right? They are defaults with no data behind them. | Owner | First 20 runs of one workflow version |
