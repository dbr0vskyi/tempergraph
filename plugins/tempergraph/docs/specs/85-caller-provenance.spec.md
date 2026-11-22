# Caller provenance

## Purpose

Most runs are not started or resumed by a person typing `tempergraph`. A Claude session using the run driver, the orchestrator skill, the orchestration supervisor, a pipeline job or an application on the Agent SDK or the Messages API makes the call, and a person is somewhere behind it, or nowhere ([R-085](../research/R-085-callers-supervision-and-babysitting-cost.rsrch.md)). This spec owns how the engine tells these callers apart on every call that changes a thread, how much it trusts each signal, and how a person's decision relayed by an agent is told from the agent's own decision. It owns OVR-B19: every intervention on a run carries its caller and decider with the evidence for them, and a person is never inferred from a caller's word alone. Provenance is accounting, not a security boundary: every signal can be forged by a process of the same user; it is built so that an honest host and an honest agent produce a true record without effort, a careless agent cannot pass as a person, and a refusal that rests on provenance only ever fails toward the more careful side ([ADR-0085](../adr/0085-classify-callers-by-the-strongest-signal.adr.md), [ADR-0086](../adr/0086-a-relayed-decision-counts-as-a-persons-only-with-host-turn-evidence.adr.md)). Supervision measures ([SUP](86-supervision-metrics.spec.md)), supervision cost ([SCO](87-supervision-cost.spec.md)), schedules ([TCK](84-schedule-ticks-and-unattended-fires.spec.md)) and judge labels ([FBK](41-feedback-and-judge-reliability.spec.md)) depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### PRV-B1 A person at a terminal

WHEN a person types a deciding command in a plain shell THE engine SHALL record the caller `{kind: person, confidence: observed, host: terminal, decided_by: person, relay: direct}`.

- GIVEN a person who types `tempergraph resume fix 42 --decision proceed` in a plain shell WHEN the resume is applied THEN the `human` record's `caller` is `person`, `observed`, `direct`

### PRV-B2 An agent that does not say so

WHEN a Claude Code tool child calls a deciding verb without `--as-agent` THE engine SHALL record the caller `agent` with confidence `marked` and host `claude-code`, `decided_by: agent`, the intervention row counting as an agent's.

- GIVEN a Claude Code Bash tool that runs `tempergraph resume fix 42 --decision proceed` WHEN it is applied THEN the caller is `agent` (`marked`) and `decided_by` is `agent`

### PRV-B3 A person in an IDE terminal

WHEN a person types a command in an IDE terminal where `CLAUDECODE=1` and `CLAUDE_CODE_CHILD_SESSION` is unset THE engine SHALL record the caller `person` (`observed`) with S3 listed as `set` in the evidence.

- GIVEN a VS Code terminal with `CLAUDECODE=1` WHEN the person resumes a thread THEN the caller is `person` and the evidence lists S3 `set`

### PRV-B4 A relayed decision

WHEN an agent passes `--relayed` on a deciding call THE engine SHALL record `decided_by: person, relay: turn_named` when a person turn after the pause names the decision, `decided_by: person, relay: turn_only` when a later person turn does not name it, `decided_by: agent, relay: claimed` when no person turn followed the pause, and without `--relayed` `decided_by: agent, relay: none`, keeping the person turn's time beside the call.

- GIVEN a run paused at 10:00 and a person turn "yes, proceed" at 10:05 WHEN the session runs `resume … --decision proceed --relayed` at 10:06 THEN `relay` is `turn_named`
- GIVEN a person turn "go ahead" at 10:05 WHEN the same call runs THEN `relay` is `turn_only`
- GIVEN no person turn since 09:40 WHEN the same call runs THEN `decided_by` is `agent` and `relay` is `claimed`

### PRV-B5 A declaration cannot raise trust

WHEN a caller with a host marker passes `--caller person` or sets `TEMPERGRAPH_CALLER=person` THE engine SHALL refuse the call with exit 2 `caller_conflict`, naming `--relayed` as the way to carry a person's decision, and write nothing.

- GIVEN a Claude Code tool child WHEN it passes `--caller person` THEN it exits 2 `caller_conflict` and nothing is written

### PRV-B6 The supervisor's children

WHEN the supervisor starts a node's run with its token and `--parent` THE engine SHALL record `run_started.caller` as `orchestrator` (`attested`) with that `parent`, and a pause of that run answered through the orchestrator skill SHALL hold the `orchestrator` caller with `decided_by` from the answer's own block ([ORC](45-orchestration.spec.md)).

- GIVEN an orchestration whose supervisor starts node `api` with `--parent o7/api` WHEN the run starts THEN its caller is `orchestrator` with `parent` `o7/api`

### PRV-B7 A pipeline job

WHEN a CI job calls the engine with no terminal THE engine SHALL record the caller `pipeline`, host `ci:<system>`, confidence `marked`.

- GIVEN a GitHub Actions job that runs `tempergraph run triage …` WHEN it starts THEN the caller is `pipeline`, host `ci:github-actions`

### PRV-B8 No signal

WHEN a call carries no terminal, no marker and no declaration THE engine SHALL record the caller `unknown` (`none`), and `status` and the reports SHALL show it as unknown, never as a person.

- GIVEN a detached script WHEN it resumes a thread THEN the caller is `unknown` and `report` lists it as unknown

### PRV-B9 A relayed grant

WHEN an agent resumes with a grant and `--relayed` THE engine SHALL apply it with `decided_by: person, relay: turn_named` when a person turn in the agent's host session names the grant, and refuse it `widening_by_agent` otherwise.

- GIVEN a step paused with cause `tool_access` and no person turn WHEN the agent resumes with `--grant triage=mcp:tracker/get_issue --relayed` THEN it exits 2 `widening_by_agent`

### PRV-B10 An application declares itself

WHEN an application resumes with `--caller agent --caller-app <name>` THE engine SHALL record the caller `agent` (`declared`), its host and `caller_app`.

- GIVEN a Messages API application WHEN it resumes with `--caller agent --caller-app triage-bot` THEN the caller is `agent`, host `messages-api-app`, `caller_app` `triage-bot`

### PRV-B11 Caller kinds

WHEN a call is classified THE engine SHALL give it one `CallerKind`: `person` (a person directly, at a terminal), `agent` (a model session, for a person or on its own, in Claude Code, an Agent SDK or Messages API application or Antigravity), `orchestrator` (the model-free supervisor, OVR-B18), `scheduler` (the model-free schedule tick, OVR-B20, [SCH](83-schedules.spec.md)), `pipeline` (a scripted job with no model deciding: a CI runner, a cron job, a lifecycle hook command), `engine` (the engine on its own account: an infra re-open, an applied deadline, a self-improvement child) or `unknown`, never folded into `person`; and map the earlier `who` words of the intervention row as `auto_reopen` to `engine`, `event` and `deadline` to the kind of the caller that delivered or applied them, `rewind` being an action, not a caller ([HUM-B6](07-gate-and-human.spec.md)).

- GIVEN an infra re-open WHEN its intervention row is written THEN its caller kind is `engine`

### PRV-B12 Signals

WHEN a mutating verb runs THE engine SHALL read, once per process before any write, by one function shared by every mutating verb, the signals S1 supervisor token (`TEMPERGRAPH_SUPERVISOR_TOKEN`, its SHA-256 equal to the digest in the orchestration's state file and `--parent` naming that orchestration, [ORC-B17](45-orchestration.spec.md)); S1s schedule fire token (`TEMPERGRAPH_SCHEDULE_TOKEN`, its SHA-256 equal to the `token_digest` of the entry `--schedule <fire_id>` names, [TCK-B17](84-schedule-ticks-and-unattended-fires.spec.md)); S2 host marker (on Claude Code `CLAUDE_CODE_CHILD_SESSION=1`, set for tool, hook and status-line children and not for IDE terminals, with `CLAUDE_CODE_SESSION_ID` and `CLAUDE_CODE_REMOTE`; other hosts per PRV-B20); S3 IDE terminal marker (`CLAUDECODE=1` without `CLAUDE_CODE_CHILD_SESSION`); S4 CI marker (`CI=true` or one of `GITHUB_ACTIONS`, `GITLAB_CI`, `BUILDKITE`, `CIRCLECI`, `JENKINS_URL`, `TF_BUILD`, `TEAMCITY_VERSION`); S5 terminal (standard input and output both terminals); S6 declaration (`--caller`, `--as-agent`, `TEMPERGRAPH_CALLER`, `--caller-app`); and S7 trace context (`TRACEPARENT`, its trace id kept for correlation and never used to classify); read-only verbs reading none of them (OVR-B15).

- GIVEN `status` WHEN it runs THEN no signal or journal is read

### PRV-B13 Classification

WHEN the signals are read THE engine SHALL take the first matching row of: S1 valid gives `orchestrator` (`attested`); S1s valid gives `scheduler` (`attested`); the engine acting itself gives `engine` (`attested`); S2 gives `agent` (`marked`); S4 without S5 gives `pipeline` (`marked`); S6 saying `agent` or `pipeline` gives that kind (`declared`); S5 with or without S3, no S2 and no S6 other than `person` gives `person` (`observed`); S6 saying `person` without S5 gives `unknown` (`declared`); nothing gives `unknown` (`none`); keep every signal seen, matched or not, in `evidence`; let a declaration only lower trust; refuse an invalid S1 or S1s before anything is written rather than downgrade it; classify a call inside a Claude Code subagent like its parent session, the subagent's id reaching the record only through the host hooks ([SCO](87-supervision-cost.spec.md)); and check `caller_app` against `[a-z0-9-]{1,40}`, exit 2 otherwise.

- GIVEN `TEMPERGRAPH_CALLER=person` with no terminal WHEN a call is classified THEN its kind is `unknown` (`declared`)

### PRV-B14 Decider

WHEN a call decides something a person may be needed for (a decision at a pause, an answer to an ask, an approval node's answer, a grant, a ruling, a rewind, a rerun with feedback, a stop) THE engine SHALL record `decided_by` and `relay` apart from the caller: `person` and `direct` for a person; for an agent as PRV-B4; for an `orchestrator` carrying an `orchestrate answer` the answer's own block; the caller kind and `none` for `pipeline` and `engine`; and `unknown` with `none` or `claimed` for `unknown`; refusing `--relayed` on a call that decides nothing (`run` without feedback, `status`) with exit 2 `relay_not_applicable`.

- GIVEN `run` without feedback WHEN it is called with `--relayed` THEN it exits 2 `relay_not_applicable`

### PRV-B15 Person turns

WHEN a person submits a prompt in a host with person-turn hooks THE plugin's `UserPromptSubmit` hook SHALL append a person turn to the host's supervision journal ([SCO](87-supervision-cost.spec.md)) with the host session id, the time and `names` (the decision words of the thread's open pauses that occur as whole words in the prompt, matched locally against the attention list), never storing the prompt text, a decision sent from the monitor ([monitor MAC](../../../tempergraph-monitor/docs/specs/05-actions-and-safety.spec.md)) being a person turn too; and THE engine SHALL count a relay backed when the journal holds a person turn of the same host session after the `pause` record's time (or after the approval node or ask failure became due) and before the call, `turn_named` needing the decision word or the answer value's key among `names`, and an unreadable journal giving `relay: claimed` with evidence `journal_unreadable` while the call goes on.

- GIVEN an unreadable journal WHEN a relayed decision is checked THEN `relay` is `claimed`, the evidence lists `journal_unreadable` and the decision is applied

### PRV-B16 The caller block

WHEN a mutating call on a thread is applied THE engine SHALL write one `Caller` block with `kind` and `confidence` (`attested`, `marked`, `observed`, `declared`, `none`); `decided_by` and `relay` (`direct`, `turn_named`, `turn_only`, `claimed`, `none`) for deciding calls, null otherwise; `host` (`terminal`, `claude-code`, `agent-sdk`, `messages-api-app`, `antigravity`, `ci:<system>`, `orchestration`, `schedule`, `engine`, `unknown`); `host_session` (an HMAC with the sink key in anything that leaves the machine, [CST](34-central-run-stats.spec.md)); `caller_app`; `parent` for `orchestrator`; `schedule` (`{schedule_id, fire_id, slot, created_by}` for `scheduler`, `{schedule_id, declared: true}` for a pipeline export, [TCK-B20](84-schedule-ticks-and-unattended-fires.spec.md)); `trace_id`; `evidence[]` (S-number and value class `set`, `unset`, `valid`, `invalid`, never a value other than the host and CI system names); and a random `call_id` for joining a host's journal entry ([SCO](87-supervision-cost.spec.md)); holding no request, prompt, feedback or command text ([SEC](14-security.spec.md)).

- GIVEN a canary run WHEN its caller blocks are scanned THEN none holds the canary

### PRV-B17 Where the block is written

WHEN a mutating call is recorded THE engine SHALL put the caller block in `run_started` for `run`, `rerun` and `resume` ([EVT](30-run-events.spec.md)); in the `human` record and the ledger's intervention row for a decision, answer, event value or applied deadline ([HUM-B6](07-gate-and-human.spec.md)); in `settings_resolved` for settings changed on a resume or rerun; as `by` in `grant` and `ruling` records for a grant or a ruling given or revoked; as requested-by in `stop_requested` ([RCT](32-run-control.spec.md)); in the orchestration event log entry and the child run's records with `parent` for `orchestrate answer`, `edit`, `stop` and `resume` ([ORC](45-orchestration.spec.md)); and let a label's `source` follow `decided_by` ([FBK-B2](41-feedback-and-judge-reliability.spec.md)).

- GIVEN a `stop` from an agent WHEN `stop_requested` is written THEN it carries the agent's caller block

### PRV-B18 Options

WHEN caller options are given THE engine SHALL read `--caller person|agent|pipeline` as S6, refusing `--caller orchestrator`, `scheduler` or `engine` with exit 2 `caller_reserved`; `--as-agent` as `--caller agent`; `--caller-app <name>` for `agent` and `pipeline`; `--relayed` as a claim checked per PRV-B14; `TEMPERGRAPH_CALLER` and `TEMPERGRAPH_CALLER_APP` as the flags, a flag winning; `TEMPERGRAPH_SUPERVISOR_TOKEN` set by the supervisor for its children only and never documented for people; and `TEMPERGRAPH_SCHEDULE_TOKEN` with `--schedule <fire_id>` set by the tick only; these being run options, not settings, absent from the settings catalog and never snapshot on the thread ([RST](80-run-settings-and-overrides.spec.md)), each call classified on its own.

- GIVEN `--caller scheduler` WHEN any verb runs THEN it exits 2 `caller_reserved`

### PRV-B19 Engine sessions never drive the engine

WHEN a mutating verb other than `self-check` is called from inside one of the engine's own sessions (`TEMPERGRAPH_SESSION_KEY` set, [EXI](10-executor-interface.spec.md)) THE engine SHALL refuse it with exit 2 `engine_session_caller` and write nothing.

- GIVEN a step session WHEN its shell runs `tempergraph resume …` THEN it exits 2 `engine_session_caller`

### PRV-B20 Host profiles

WHEN markers are read for a host THE engine SHALL use the host profile shipped with it (the variables that mark a tool child, the variable that holds its session id, and whether its plugin hooks can write person turns): Claude Code CLI, IDE and desktop marked by `CLAUDE_CODE_CHILD_SESSION=1` with session `CLAUDE_CODE_SESSION_ID` and person turns from the plugin `UserPromptSubmit` hook (P-SUP-1, P-SUP-2); a Claude Code cloud session the same plus `CLAUDE_CODE_REMOTE=true`; an Agent SDK application by the Claude Code markers on its session children, with its own hook or `--relayed` with no turn (P-SUP-4); a Messages API application by its declaration `--caller agent --caller-app <name>`; an Antigravity session `unknown` unless it declares (P-SUP-5); a CI runner by S4 with the system's job id variable; a profile whose probe has not run reading only the markers it lists and shown as projected in `executors --probe` ([CLI-B3](17-engine-cli.spec.md)).

- GIVEN an Antigravity session that declares nothing WHEN it resumes a thread THEN the caller is `unknown`

### PRV-B21 Widening and answers need a person

WHEN a call widens tools, commands or views on a resume ([RST](80-run-settings-and-overrides.spec.md)) or answers in an orchestration THE engine SHALL refuse it (`widening_by_agent`, `answer_not_by_person`) unless `decided_by` is `person`, a widening from an agent needing `relay: turn_named` and `turn_only`, `claimed`, `unknown`, `pipeline` and `orchestrator` being refused, a workflow's own profile still widening on any caller, every pause in an orchestration staying with a person ([ORC-B6](45-orchestration.spec.md), [ADR-0039](../adr/0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md)).

- GIVEN an agent relay with `turn_only` WHEN it widens a step's tools THEN it exits 2 `widening_by_agent`

### PRV-B22 Other uses of provenance

WHEN provenance is used elsewhere THE engine SHALL record, never refuse, a decision at a pause on provenance (a delegation policy is out of scope, [HUM](07-gate-and-human.spec.md)); make a `person` judge label only from `decided_by = person`, every other label being `agent` or `unknown` and kept out of judge figures ([FBK-B2](41-feedback-and-judge-reliability.spec.md)); record rulings with the block ([RRN](81-reruns-and-feedback.spec.md)); count every touch by `kind` and `decided_by` in supervision ([SUP](86-supervision-metrics.spec.md)); and refuse `schedule add`, `edit`, `resume` and `fire` `schedule_not_by_person` unless `decided_by` is `person` within the relay window ([TCK-B22](84-schedule-ticks-and-unattended-fires.spec.md)).

- GIVEN an agent's own decision at an undesigned pause WHEN it is applied THEN it is recorded with `decided_by: agent` and not refused

## Acceptance criteria

- PRV-AC1 (PRV-B1, PRV-B2, PRV-B3, PRV-B4, PRV-B6, PRV-B7, PRV-B8, PRV-B10, PRV-B11, PRV-B13, PRV-B14, PRV-B15): Every row of the classification and every relay case is reproduced by a fixture test over a stubbed environment, terminal and journal
- PRV-AC2 (PRV-B12, PRV-B17, PRV-B19): Every mutating verb of [CLI](17-engine-cli.spec.md) writes exactly one `caller` block per call where PRV-B17 says, and no read-only verb reads the signals or the journal (source test plus the hash test of CLI-AC1)
- PRV-AC3 (PRV-B16): No `caller` block in a canary run contains the canary, a prompt, a command or a feedback text ([SEC-B2](14-security.spec.md))
- PRV-AC4 (PRV-B5, PRV-B18): A call with a host marker can never produce `kind: person`, whatever it declares (property test over all combinations of S2 to S6)
- PRV-AC5 (PRV-B9, PRV-B21, PRV-B22): A widening on a resume is applied only when `decided_by` is `person` and, for an agent caller, `relay` is `turn_named`
- PRV-AC6 (PRV-B20): P-SUP-1 (`CLAUDE_CODE_SESSION_ID` is in the Bash tool environment on the CLI, IDE, desktop and cloud surfaces and equals the hook input's `session_id`), P-SUP-2 (`UserPromptSubmit` input carries the prompt text to the hook; without it relays are `turn_only` at best) and P-SUP-4 (Bash children of an Agent SDK session carry the Claude Code markers) each have a recorded result with date, machine and Claude Code version before the Claude Code and Agent SDK host profiles leave `projected`; P-SUP-5 (Antigravity marks its tool children or exposes hooks with a session id) before the Antigravity profile does

## Open questions

- Should an agent's own decision at an undesigned pause be refused once a delegation policy exists? Until answered: allowed and recorded. Owner: owner.
- Should `turn_only` relays be enough for widening? Until answered: no. Owner: owner.
- Not built yet: orchestrations and schedules do not exist yet, so S1 and S1s never match and any token is refused with its code; until the SCO hooks write a journal on a host, a relayed call there finds no person turns and records `relay: claimed`; probes P-SUP-1, P-SUP-2, P-SUP-4 and P-SUP-5 have not run. Owner: engine owner.
