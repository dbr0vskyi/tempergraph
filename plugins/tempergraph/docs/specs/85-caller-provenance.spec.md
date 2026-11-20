---
title: Caller provenance
type: component
status: review
prefix: PRV
adrs: [0085, 0086, 0099]
---

# Caller provenance

## 1. Overview

Most runs are not started or resumed by a person typing `tempergraph`. A Claude session using the run driver, the orchestrator skill, the orchestration supervisor, a pipeline job or an application on the Agent SDK or the Messages API makes the call, and a person is somewhere behind it, or nowhere ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md)). This spec owns how the engine tells these callers apart on **every** call that changes a thread, how much it trusts each signal, and how a person's decision relayed by an agent is told from the agent's own decision. It owns contract C17: every intervention on a run carries its caller and decider with the evidence for them, and a person is never inferred from a caller's word alone.

Provenance is accounting, not a security boundary: every signal here can be forged by a process of the same user (§2.2). It is built so that an honest host and an honest agent produce a true record without effort, a careless agent cannot pass as a person, and a refusal that rests on provenance only ever fails toward the more careful side. The supervision measures built on it are [SUP](86-supervision-metrics.spec.md); the cost of supervising sessions is [SCO](87-supervision-cost.spec.md).

## 2. Contract

### 2.1 Caller kinds

| Kind | Who made the call | Typical host |
|---|---|---|
| `person` | A person, directly, at a terminal | A shell outside any agent host; an IDE terminal |
| `agent` | A model session, for a person or on its own | Claude Code (CLI, IDE, desktop, cloud), an Agent SDK application, a Messages API application, an Antigravity session |
| `orchestrator` | The model-free orchestration supervisor (contract C16) | The engine itself, detached |
| `scheduler` | The model-free schedule tick firing a person's schedule (contract C18, [SCH](83-schedules.spec.md)) | The engine itself, started by the per-user OS trigger |
| `pipeline` | A scripted job with no model deciding | A CI runner, a cron job, a lifecycle hook command |
| `engine` | The engine on its own account: an infra re-open, an applied deadline, a self-improvement child | The running engine |
| `unknown` | No signal says which | Anything that leaves no mark |

`unknown` is a kind of its own, never folded into `person`. The earlier `who` words of the intervention row map onto these kinds: `auto_reopen` is `engine`, `event` is the kind of the caller that delivered the event, `deadline` is the kind of the caller that applied it, `rewind` is an action, not a caller ([HUM-B6](07-gate-and-human.spec.md)).

### 2.2 Signals

Read once per process, before any write, by one function shared by every mutating verb; read-only verbs read nothing of this (contract C13).

| # | Signal | Says | How it is read | Missing when | Forged by |
|---|---|---|---|---|---|
| S1 | Supervisor token | `orchestrator`, and which orchestration and node | `TEMPERGRAPH_SUPERVISOR_TOKEN` in the environment; its SHA-256 must equal the digest the supervisor wrote in the orchestration's state file, and `--parent` must name that orchestration ([ORC §2.8](45-orchestration.spec.md)) | Never, for a run the supervisor starts | A same-user process that reads the owner-only state file |
| S1s | Schedule fire token | `scheduler`, and which schedule, fire and slot | `TEMPERGRAPH_SCHEDULE_TOKEN`; its SHA-256 must equal the `token_digest` of the schedule entry that `--schedule <fire_id>` names ([TCK §2.3](84-schedule-ticks-and-unattended-fires.spec.md)) | Never, for a run or orchestration the tick starts | A same-user process that reads the owner-only entry |
| S2 | Host marker | `agent`, and the host and its session | Claude Code: `CLAUDE_CODE_CHILD_SESSION=1` (set for tool, hook and status-line children, not for IDE terminals), `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_REMOTE`; other hosts per §2.7 | A host that marks nothing (Antigravity until P-SUP-5; a plain application) | Any process that sets the variable; an agent that unsets it |
| S3 | IDE terminal marker | Not an agent tool call | `CLAUDECODE=1` without `CLAUDE_CODE_CHILD_SESSION` | Outside an IDE | As S2 |
| S4 | CI marker | `pipeline`, and the system | `CI=true` or one of `GITHUB_ACTIONS`, `GITLAB_CI`, `BUILDKITE`, `CIRCLECI`, `JENKINS_URL`, `TF_BUILD`, `TEAMCITY_VERSION` | A runner that sets none | Setting the variable |
| S5 | Terminal | Probably a person | Standard input and standard output are both terminals | Piped or backgrounded calls | A pseudo-terminal |
| S6 | Declaration | What the caller says it is | `--caller <kind>`, `--as-agent` (= `--caller agent`), `TEMPERGRAPH_CALLER`, and for an application `--caller-app <name>` | The caller does not say | Saying it |
| S7 | Trace context | Correlation only | `TRACEPARENT` ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md) H8): its trace id is kept on the `caller` block so a caller's own traces can be joined | The caller does not propagate it | Setting it; never used to classify |

A host that marks its children is described by a **host profile**: the variables that mark a tool child, the variable that holds its session id, and whether its plugin hooks can write person turns ([SCO §2.2](87-supervision-cost.spec.md)). Profiles ship with the engine; §2.7 lists them.

### 2.3 Classification

The first row that matches decides the kind; the `evidence` list keeps every signal seen, matched or not.

| Order | Condition | Kind | `confidence` |
|---|---|---|---|
| 1 | S1 valid | `orchestrator` | `attested` |
| 1s | S1s valid | `scheduler` | `attested` |
| 2 | The engine itself acts (no process call) | `engine` | `attested` |
| 3 | S2 present | `agent` | `marked` |
| 4 | S4 present and no S5 | `pipeline` | `marked` |
| 5 | S6 says `agent` or `pipeline` | as declared | `declared` |
| 6 | S5 present (with or without S3), no S2, no S6 other than `person` | `person` | `observed` |
| 7 | S6 says `person`, no S5 | `unknown` | `declared` |
| 8 | Nothing | `unknown` | `none` |

Rules:

- **A declaration only lowers trust.** S6 can turn a would-be `person` into `agent` or `pipeline`; it can never make an S2 caller a `person` (§4 `caller_conflict`). An agent that carries a person's word uses `--relayed` (§2.4), not `--caller person`.
- An invalid S1 (a token whose digest does not match) is refused before anything is written (§4), never downgraded silently.
- A call inside a Claude Code subagent is classified like its parent session; the subagent's id reaches the record only through the host hooks ([SCO §2.2](87-supervision-cost.spec.md)).
- The `caller_app` name from `--caller-app` is free text checked against `[a-z0-9-]{1,40}`, like an alias.

### 2.4 Decider and relay evidence

For a call that decides something a person may be needed for (a decision at a pause, an answer to an ask, an approval node's answer, a grant, a ruling, a rewind, a rerun with feedback, a stop), the engine records the **decider** apart from the caller.

| Caller | Relay claim | Host evidence (§2.4.1) | `decided_by` | `relay` |
|---|---|---|---|---|
| `person` | — | — | `person` | `direct` |
| `agent` | none | — | `agent` | `none` |
| `agent` | `--relayed` | a person turn that names the decision | `person` | `turn_named` |
| `agent` | `--relayed` | a person turn that does not name it, or the host cannot check the words | `person` | `turn_only` |
| `agent` | `--relayed` | no person turn since the pause was shown, or the host writes no turns | `agent` | `claimed` |
| `orchestrator` | carrying an `orchestrate answer` | the answer's own caller block | that block's `decided_by` | as that block |
| `pipeline`, `engine` | — | — | the caller kind | `none` |
| `unknown` | any | — | `unknown` | `none` or `claimed` |

#### 2.4.1 Person turns

The plugin's `UserPromptSubmit` hook on Claude Code appends a **person turn** to the host's supervision journal ([SCO §2.2](87-supervision-cost.spec.md)): host session id, time, and `names` (the decision words of the thread's open pauses that occur as whole words in the prompt, matched locally against the attention list). The prompt text is never stored. A monitor action fills the prompt for the person to send ([monitor MAC](../../../tempergraph-monitor/docs/specs/05-actions-and-safety.spec.md)), so a decision sent from the monitor is a person turn too.

A relay is backed when the journal holds a person turn of the same host session after the `pause` record's time (or after the approval node or ask failure became due) and before the call. `turn_named` needs the decision word (or, for an answer, the answer value's key) among `names`; any later turn is enough for `turn_only`.

### 2.5 The caller block

Every mutating call on a thread writes one `caller` block, the same shape everywhere:

| Field | Meaning |
|---|---|
| `kind`, `confidence` | §2.3 |
| `decided_by`, `relay` | §2.4, for deciding calls; null otherwise |
| `host` | `terminal`, `claude-code`, `agent-sdk`, `messages-api-app`, `antigravity`, `ci:<system>`, `orchestration`, `schedule`, `engine`, `unknown` |
| `host_session` | The host's session id (local records); an HMAC with the sink key in anything that leaves the machine ([CST §2.4](34-central-run-stats.spec.md)) |
| `caller_app` | From `--caller-app`, or null |
| `parent` | The orchestration, node and item, for `orchestrator` |
| `schedule` | `{schedule_id, fire_id, slot, created_by}` for `scheduler`; `{schedule_id, declared: true}` for a pipeline export ([SCH §2.8](83-schedules.spec.md)) |
| `trace_id` | From S7, or null |
| `evidence[]` | The signals seen: S-number and the value class (`set`, `unset`, `valid`, `invalid`), never a value other than the host and CI system names |
| `call_id` | A random id, so a host's journal entry for the same call can be joined ([SCO §2.4](87-supervision-cost.spec.md)) |

Where it is written:

| Call | Record |
|---|---|
| `run`, `rerun`, `resume` (any) | `run_started` gains `caller` ([EVT §2.2](30-run-events.spec.md)) |
| A decision, answer, event value, applied deadline | The `human` record and the ledger's intervention row ([HUM-B6](07-gate-and-human.spec.md)) |
| Settings changed on a resume or rerun | `settings_resolved` gains `caller` |
| A grant, a ruling given or revoked | `grant` and `ruling` records: `by` becomes the `caller` block |
| `stop` | `stop_requested`: requested by becomes the `caller` block ([RCT](32-run-control.spec.md)) |
| `orchestrate answer`, `edit`, `stop`, `resume` | The orchestration event log entry ([ORC §2.7](45-orchestration.spec.md)), and the child run's records with `parent` |
| `label` | The label's `source` follows `decided_by` ([FBK §2.1](41-feedback-and-judge-reliability.spec.md)) |

The `caller` block holds no request, prompt, feedback or command text ([SEC](14-security.spec.md)).

### 2.6 Options

| Option or variable | Effect |
|---|---|
| `--caller person\|agent\|pipeline` | S6. `orchestrator`, `scheduler` and `engine` cannot be declared |
| `--as-agent` | Kept: the same as `--caller agent` |
| `--caller-app <name>` | Names the application that called, for `agent` and `pipeline` |
| `--relayed` | The call carries a person's decision; checked per §2.4 |
| `TEMPERGRAPH_CALLER`, `TEMPERGRAPH_CALLER_APP` | The same as the flags, for callers that cannot change argv; a flag wins |
| `TEMPERGRAPH_SUPERVISOR_TOKEN` | Set by the supervisor for its children only; never documented for people |
| `TEMPERGRAPH_SCHEDULE_TOKEN`, `--schedule <fire_id>` | Set by the schedule tick for the runs it starts only; `--schedule` without a valid token is refused |

These are run options, not settings: they are not in the settings catalog and are not snapshot on the thread ([RST §2.2](80-run-settings-and-overrides.spec.md)); each call is classified on its own.

### 2.7 Host profiles

| Host | Tool-child marker | Session id | Person turns | Status |
|---|---|---|---|---|
| Claude Code CLI, IDE, desktop | `CLAUDE_CODE_CHILD_SESSION=1` | `CLAUDE_CODE_SESSION_ID` | plugin `UserPromptSubmit` hook | marker supported; session id P-SUP-1; prompt field P-SUP-2 |
| Claude Code cloud session | as above, plus `CLAUDE_CODE_REMOTE=true` | as above | as above | as above |
| Agent SDK application | the SDK's session children carry the Claude Code markers | as above | the application's own hook or `--relayed` with no turn | P-SUP-4 |
| Messages API application | none | none | none | declares `--caller agent --caller-app <name>` |
| Antigravity session | unknown | unknown | unknown | P-SUP-5; until then `unknown` unless it declares |
| CI runner | S4 | the job id variable of the system | none | supported |

A profile whose probe has not run is used only to read markers it lists; its rows are shown as projected in `executors --probe` beside the executor facts ([CLI-B3](17-engine-cli.spec.md)).

### 2.8 What provenance changes

| Use | Rule |
|---|---|
| Widening tools, commands or views ([RST §2.8](80-run-settings-and-overrides.spec.md)) | Refused (`widening_by_agent`) unless `decided_by` is `person`: a person at a terminal, or an agent relay with `turn_named`. `turn_only`, `claimed`, `unknown`, `pipeline` and `orchestrator` are refused. A workflow's own profile still widens on any caller |
| A decision at a pause | Never refused on provenance in the first release; recorded. A delegation policy is out of scope ([HUM §5](07-gate-and-human.spec.md)) |
| An answer in an orchestration | `orchestrate answer` is refused (`answer_not_by_person`) unless `decided_by` is `person`, because every pause in an orchestration stays with a person ([ORC-B6](45-orchestration.spec.md), [ADR-0039](../adr/0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md)) |
| Judge labels | Only `decided_by = person` makes a `person` label; everything else is `agent` or `unknown` and is kept out of judge figures ([FBK-B2](41-feedback-and-judge-reliability.spec.md)) |
| Rulings | Recorded with the block; the owner question of [RRN](81-reruns-and-feedback.spec.md) on agent rulings stays open |
| Supervision measures | Every touch counts, split by `kind` and `decided_by` ([SUP §2.2](86-supervision-metrics.spec.md)) |
| Creating or widening a schedule | `schedule add`, `edit`, `resume` and `fire` are refused (`schedule_not_by_person`) unless `decided_by` is `person`; a relay needs a person turn within 10 minutes ([TCK §2.6](84-schedule-ticks-and-unattended-fires.spec.md)) |

## 3. Behaviours

**PRV-B1 A person at a terminal.** Given a person who types `tempergraph resume fix 42 --decision proceed` in a plain shell, when the resume is applied, then the `human` record's `caller` is `{kind: person, confidence: observed, host: terminal, decided_by: person, relay: direct}`.

**PRV-B2 An agent that does not say so.** Given a Claude Code session whose Bash tool runs `tempergraph resume fix 42 --decision proceed` without `--as-agent`, when it is applied, then the caller is `agent` with confidence `marked` and host `claude-code`, `decided_by` is `agent`, and the intervention row counts as an agent's.

**PRV-B3 A person in an IDE terminal.** Given a person who types the same command in a VS Code terminal where `CLAUDECODE=1` and `CLAUDE_CODE_CHILD_SESSION` is unset, when it is applied, then the caller is `person` (`observed`), and the evidence lists S3 as `set`.

**PRV-B4 A relayed decision.** Given a run paused at 10:00 and a Claude Code session in which the person wrote "yes, proceed" at 10:05, when the session runs `resume … --decision proceed --relayed` at 10:06, then `decided_by` is `person` with `relay: turn_named`, and the person turn's time is kept beside the call.

| Person turn after the pause | Words | `--relayed` | `decided_by` | `relay` |
|---|---|---|---|---|
| 10:05 "yes, proceed" | `proceed` | yes | person | `turn_named` |
| 10:05 "go ahead" | none | yes | person | `turn_only` |
| none since 09:40 | — | yes | agent | `claimed` |
| 10:05 "yes, proceed" | `proceed` | no | agent | `none` |

**PRV-B5 A declaration cannot raise trust.** Given a Claude Code tool child that passes `--caller person`, when the call is checked, then it is refused with exit 2 `caller_conflict`, naming `--relayed` as the way to carry a person's decision, and nothing is written.

**PRV-B6 The supervisor's children.** Given an orchestration whose supervisor starts node `api` with its token and `--parent o7/api`, when the run starts, then `run_started.caller` is `orchestrator` (`attested`) with `parent` `o7/api`; when the person answers that run's pause through the orchestrator skill with the person's word, then the `human` record holds the `orchestrator` caller and `decided_by` from the answer's own block ([ORC §2.6](45-orchestration.spec.md)).

**PRV-B7 A pipeline job.** Given a GitHub Actions job that runs `tempergraph run triage …` with no terminal, when it starts, then the caller is `pipeline`, host `ci:github-actions`, confidence `marked`.

**PRV-B8 No signal.** Given a call from a detached script with no terminal, no marker and no declaration, when it is applied, then the caller is `unknown` (`none`); `status` and the reports show it as unknown, never as a person.

**PRV-B9 A relayed grant.** Given a step paused with cause `tool_access` and a person turn naming the grant in the agent's host session, when the agent resumes with `--grant triage=mcp:tracker/get_issue --relayed`, then the grant is applied with `decided_by: person, relay: turn_named`; without the person turn it is refused with `widening_by_agent`.

**PRV-B10 An application declares itself.** Given a Messages API application that resumes with `--caller agent --caller-app triage-bot`, when it is applied, then the caller is `agent` (`declared`), host `messages-api-app`, `caller_app` `triage-bot`.

## 4. Error conditions

| Condition | Result |
|---|---|
| `--caller person` (or `TEMPERGRAPH_CALLER=person`) from a caller with a host marker | Exit 2 `caller_conflict`, nothing written |
| `--caller orchestrator`, `--caller scheduler` or `--caller engine` | Exit 2 `caller_reserved` |
| A schedule token whose digest does not match the entry `--schedule` names | Exit 2 `schedule_token_invalid`, nothing written |
| A supervisor token whose digest matches no orchestration, or not the one `--parent` names | Exit 2 `supervisor_token_invalid`, nothing written |
| `--relayed` on a call that decides nothing (`run` without feedback, `status`) | Exit 2 `relay_not_applicable` |
| `--caller-app` outside `[a-z0-9-]{1,40}` | Exit 2 |
| A mutating verb other than `self-check` called from inside one of the engine's own sessions (`TEMPERGRAPH_SESSION_KEY` set, [EXI §2.3](10-executor-interface.spec.md)) | Exit 2 `engine_session_caller`: a step never drives the engine |
| The supervision journal cannot be read when checking a relay | `relay: claimed` with evidence `journal_unreadable`; the call goes on |

## 5. Design notes

- **Strongest signal first** ([ADR-0085](../adr/0085-classify-callers-by-the-strongest-signal.adr.md)). Claude Code sets its child markers without the model's help, so an agent that forgets `--as-agent` is still seen. Self-declaration stays useful for hosts that mark nothing and for honest applications, and it can only move the record toward "not a person".
- **Relay needs the host** ([ADR-0086](../adr/0086-a-relayed-decision-counts-as-a-persons-only-with-host-turn-evidence.adr.md)). The only event that proves a person typed something is the host's own prompt-submit event; the engine never sees the conversation and never stores its text.
- **Not a security control.** Every signal is forgeable by the same user (R-085 H10). Refusals built on provenance (widening) fail toward refusal; nothing grants more because of a signal except a backed relay, which needs a person turn in the host.
- **Probes.**

| Probe | Question | Gates | State |
|---|---|---|---|
| P-SUP-1 | `CLAUDE_CODE_SESSION_ID` is in the Bash tool environment on the CLI, IDE, desktop and cloud surfaces and equals the hook input's `session_id` | host session on the caller block; relay join | not run |
| P-SUP-2 | `UserPromptSubmit` input carries the prompt text to the hook | `names`, so `turn_named` | not run; without it relays are `turn_only` at best |
| P-SUP-4 | Bash children of an Agent SDK session carry the Claude Code markers, and which entry point is visible | Agent SDK host profile | not run |
| P-SUP-5 | Antigravity marks its tool children or exposes hooks with a session id | Antigravity host profile | not run |

## 6. Acceptance criteria

- [ ] PRV-AC-1 Every row of the §2.3 table and of the PRV-B4 table is reproduced by a fixture test over a stubbed environment, terminal and journal.
- [ ] PRV-AC-2 Every mutating verb of [CLI](17-engine-cli.spec.md) writes exactly one `caller` block per call where §2.5 says, and no read-only verb reads the signals or the journal (source test plus the hash test of CLI-AC-1).
- [ ] PRV-AC-3 No `caller` block in a canary run contains the canary, a prompt, a command or a feedback text ([SEC-B2](14-security.spec.md)).
- [ ] PRV-AC-4 A call with a host marker can never produce `kind: person`, whatever it declares (property test over all combinations of S2 to S6).
- [ ] PRV-AC-5 A widening on a resume is applied only when `decided_by` is `person` and, for an agent caller, `relay` is `turn_named`.
- [ ] PRV-AC-6 P-SUP-1, P-SUP-2 and P-SUP-4 each have a recorded result with date, machine and Claude Code version before the Claude Code and Agent SDK host profiles leave `projected`.

## Open questions

| Question | Owner |
|---|---|
| Should an agent's own decision at an undesigned pause be refused once a delegation policy exists? Kept allowed and recorded. | Owner |
| Should `turn_only` relays be enough for widening? Assumed no. | Owner |

## References

