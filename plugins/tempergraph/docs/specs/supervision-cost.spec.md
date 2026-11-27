# Supervision cost

## Purpose

What the sessions that babysit runs spend: the Claude session that starts a run and waits on it, reads its status and logs, diagnoses a failure, shows a pause to a person and resumes; the orchestrator skill's session; their helper subagents; an application that drives the engine. This spend happens in a host the engine does not run, so the engine cannot meter it the way it meters its own sessions ([OBS](observability-and-cost.spec.md)); it adds to run cost, most of it context re-read after a wake, and is lost unless it is recorded per run ([research `callers-supervision-and-babysitting-cost`](../research/callers-supervision-and-babysitting-cost.rsrch.md) B1, B2, B4). This spec owns the supervision journal that hosts and callers write, the sources of usage per host, the attribution of a supervising session's spend to threads and orchestrations, the closing of a thread's supervision cost, and the `supervision` verbs. Read-only verbs still write nothing (OVR-B15): the journal is written by the host's hooks and by one writing verb ([ADR `a-supervision-journal-written-by-the-host-not-by-read-only-verbs`](../adr/a-supervision-journal-written-by-the-host-not-by-read-only-verbs.adr.md)). Unmeasured is never zero. Supervision metrics ([SUP](supervision-metrics.spec.md)), reports, sinks ([CST](central-run-stats.spec.md)) and the orchestrator skill's share ([OSK](orchestrator-skill.spec.md)) depend on it; design notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `caller-provenance.spec.md`: classification (PRV-B13); person turns (PRV-B15); the caller block (PRV-B16)
- `central-run-stats.spec.md`: central run stats
- `engine-cli.spec.md`: engine cli
- `executor-interface.spec.md`: executor interface
- `local-observability-store.spec.md`: home layout (LOS-B10)
- `observability-and-cost.spec.md`: observability and cost
- `orchestrator-skill.spec.md`: orchestrator skill
- `overview.spec.md`: the supervisor calls no model (OVR-B18); the schedule tick calls no model (OVR-B20)
- `plugin-shell.spec.md`: plugin shell
- `self-improvement.spec.md`: self-improvement loop
- `supervision-metrics.spec.md`: supervision record of a run (SUP-B10); workflow aggregates (SUP-B12)

## Behaviours

### SCO-B1 A run driver session

WHEN a run driver session's supervision of a thread closes THE engine SHALL fill the categories `start` (the `run --check` rounds and the start), `watch`, `rewake`, `relay` and `decide` with both figures, completeness `complete` when every supervising session had usage.

- GIVEN a Claude Code session that runs `run --check` twice, starts a run in the background, is woken by its exit 3 after 40 idle minutes, reads `facts`, shows the pause, gets "proceed" and resumes with `--relayed` WHEN the thread closes THEN `start` holds 3 calls, `watch` 1, `rewake` 1 wake message, `relay` 2 messages and `decide` 1, and completeness is `complete`

### SCO-B2 The re-read is named

WHEN the report prints a thread's supervision THE engine SHALL show `rewake` as its own line and count it in the marginal figure, so a polling habit is visible as cost ([research `callers-supervision-and-babysitting-cost`](../research/callers-supervision-and-babysitting-cost.rsrch.md) B2).

- GIVEN a wake message with 95K cache write tokens WHEN `supervision show` prints the thread THEN `rewake` shows 95K and is inside the marginal total

### SCO-B3 An orchestration

WHEN an orchestration ends THE engine SHALL split each of the skill session's calls about it equally over the runs live at that moment, keep the total on the orchestration, print the skill's marginal figure, the runs' estimated cost and the share against [OSK](orchestrator-skill.spec.md)'s 3%, and give the supervisor's own figure `measured_zero`.

- GIVEN the skill calling `orchestrate wait` four times while three runs are live WHEN the orchestration ends THEN each wait is split over three runs and the supervisor's figure is `measured_zero`

### SCO-B4 An application reports

WHEN an Agent SDK application pipes its `engine_call` and `usage` entries and its result message's cost to `supervision log` THE engine SHALL take the thread's figures from those entries and show the session's reported cost beside them.

- GIVEN such an application WHEN the thread closes THEN its figures come from the piped entries and the reported cost is shown beside them, not split onto the thread

### SCO-B5 An unmeasured supervisor

WHEN a thread touched by an `unknown` caller closes THE engine SHALL record completeness `incomplete` with null cost fields, and `report --supervision` SHALL count the run under "cost not measured".

- GIVEN a run resumed by an `unknown` caller WHEN its supervision closes THEN the cost fields are null and completeness is `incomplete`

### SCO-B6 The engine's own sessions

WHEN the plugin's hooks fire in a session whose environment holds `TEMPERGRAPH_SESSION_KEY` ([EXI](executor-interface.spec.md)) THE hooks SHALL write nothing, so the engine's own step and judge sessions are never supervising sessions and are not counted twice.

- GIVEN a step session on `claude` that loads the tempergraph plugin and calls `self-check` WHEN its hooks fire THEN no journal entry is written

### SCO-B7 Other work stays off the run

WHEN a supervising session also does other work THE engine SHALL put on the thread only the messages that attribution assigns to it and list the rest of the session's spend as `other` in `supervision show --session`.

- GIVEN a session that supervises one run and also edits code for an hour WHEN the thread closes THEN the editing spend is `other` and not on the thread

### SCO-B8 Helpers

WHEN a supervising session's subagent makes calls about a target THE engine SHALL put the subagent's whole usage in the thread's turn figure under the calls' category and its calls' marginal tokens in the marginal figure.

- GIVEN a subagent that calls `logs` and `status --detail` about a failed run WHEN the thread closes THEN its whole usage is in the turn figure under `diagnose`

### SCO-B9 Supervising session

WHEN a host session (a Claude Code session or its subagents, an Agent SDK or Messages API application session, an Antigravity session) makes an engine call about a thread or an orchestration THE engine SHALL treat it as a supervising session whose window runs from its first such call to its end, count as supervision only the spend inside the window that attribution assigns (SCO-B13), and count the rest as `other`, never on a run.

- GIVEN a session whose first engine call is at 10:00 WHEN its 09:30 messages are read THEN they are `other`

### SCO-B10 Supervision journal

WHEN supervision is journaled THE engine SHALL keep one owner-only, append-only JSON-lines file per host session at `~/.tempergraph/supervision/<host>/<host_session>.jsonl` in the home store ([LOS-B10](local-observability-store.spec.md)), because one session may supervise runs in several repositories, holding numbers, names from fixed lists, ids and times only, in the entries `session` (`host`, `host_session`, `started_at`, host version, `model`); `engine_call` (`at`, `tool_use_id`, `agent_id` or null, `verb` from a fixed list, `targets` resolved by the same selector function as the verbs, `mutating`, `background`, `exit_code`, `duration_s`, `output_bytes`, `call_id` when the verb printed one, [PRV-B16](caller-provenance.spec.md)); `person_turn` (`at`, `prompt_id`, `names`, [PRV-B15](caller-provenance.spec.md)); `usage` (`at`, `message_id`, `agent_id`, `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `tool_use_ids[]`); `reported` (`at`, `reported_cost_usd`, source `statusline` or `sdk_result`); and `end` (`at`, reason); keeping an entry whose target no state root knows yet, to attribute it if the thread appears; and keeping two hosts that claim the same `host_session` apart by host, the pair shown in `supervision show`.

- GIVEN a journal entry naming an unknown thread WHEN the thread appears later THEN the entry is attributed to it

### SCO-B11 Journal writers

WHEN a supervising host writes the journal THE plugin's Claude Code hooks ([SHL](plugin-shell.spec.md)) SHALL write `session` on `SessionStart`, `person_turn` on `UserPromptSubmit`, `engine_call` on `PostToolUse` of a `Bash` command that starts with the shim name, `usage` lines read from the transcript since the last offset on `Stop` and `SubagentStop` (numbers only) and `end` on `SessionEnd`; `supervision log` SHALL accept every entry but `person_turn` from an Agent SDK or Messages API application or a wrapper around another host; the orchestration supervisor, the schedule tick and a scripted pipeline call no model and SHALL have `measured_zero` with no journal (OVR-B18, OVR-B20); a hook's failure, a full disk or a malformed transcript line SHALL cost that entry only, never changing, delaying past 2 s or refusing the host call (C2), a skipped transcript line counted on the next entry and making that session `estimated`; and `observe.supervision = off` in the user config SHALL turn every write off, the next run recording once that supervision is not measured.

- GIVEN a transcript line the hook cannot parse WHEN `Stop` fires THEN the line is skipped, counted on the next entry and the session is `estimated`

### SCO-B12 Sources per host

WHEN usage is read for a supervising host, which need not be the step executor THE engine SHALL read Claude Code (CLI, IDE, desktop, cloud) engine calls from the `PostToolUse` hook, usage per message from the transcript via `Stop` and `SubagentStop`, the status line's `cost.total_cost_usd` as a session `reported` cross-check and person turns from `UserPromptSubmit`, tokens reported and cost estimated; an Agent SDK application from SDK hooks or `supervision log`, per-message usage and the result message's `total_cost_usd`, tokens and session cost reported; a Messages API application from `supervision log` and each response's `usage`, cost estimated; an Antigravity session as `unmeasured` until P-SUP-5; the supervisor, tick and scripted pipeline as `measured_zero`; and an `unknown` caller ([PRV-B13](caller-provenance.spec.md)) as `unmeasured`.

- GIVEN a run babysat by an Antigravity session WHEN its supervision closes THEN completeness is `incomplete`

### SCO-B13 Attribution

WHEN the journal is joined with the run logs by target and time THE engine SHALL count each assistant message at most once per thread, treat each engine call as about the targets its selector resolved to, split a call about an orchestration equally over its runs live at that moment, and assign categories `start` (`run`, `rerun`, `orchestrate start`, `batch` and the messages that prepared them after the session's first call), `watch` (`status`, `events`, `facts`, `wait`, `attention`, `orchestrate status`, `orchestrate wait`), `diagnose` (`logs`, `status --detail`, `audit`, `report`, `executors` about the target), `decide` (`resume`, `orchestrate answer`, `label`), `steer` (`stop`, `rerun --check`, `config`, `orchestrate edit`, a resume that only changes settings), `relay` (messages between the one that read a pause and the `decide` call that answered it, when a `person_turn` lies between) and `rewake` (the cache write of a wake message: the first assistant message after the session was idle at least `observe.wake_idle_s`, default 300 s, that follows the end of a background engine call or the arrival of its exit).

- GIVEN a message that issued `status` and `logs` about one thread WHEN it is attributed THEN its output tokens are split between `watch` and `diagnose` and it is counted once on the thread

### SCO-B14 Two figures

WHEN a call's spend is computed THE engine SHALL compute, never summing them ([ADR `attribute-supervision-spend-by-marginal-tokens-beside-turn-totals`](../adr/attribute-supervision-spend-by-marginal-tokens-beside-turn-totals.adr.md)), the marginal figure (the issuing message's output tokens divided by the calls it issued; the call's result read by the next message as `ceil(output_bytes / 4)` input tokens capped at that message's new input tokens; and for a wake message its cache write tokens) and the turn figure (the whole usage of the issuing and the next message, every `relay` message, and the whole usage of a subagent whose transcript holds a call about the target); price both with the engine's price table, cache reads and writes at their own rates ([OBS](observability-and-cost.spec.md)), as `estimated_usd`; and keep a session `reported` figure on the session beside the sum of its attributed and `other` spend, never split onto threads.

- GIVEN a call whose output was 4,000 bytes and whose next message had 600 new input tokens WHEN the marginal figure is computed THEN the result counts 600 input tokens

### SCO-B15 Closing a thread's supervision cost

WHEN every supervising session that touched a thread has ended or made no call about it for 24 h after the thread's last `run_exit` THE closer SHALL append a ledger line of kind `supervision` with the thread id and the cost fields of [SUP-B10](supervision-metrics.spec.md), joined by readers to the thread's row ([SIL](self-improvement.spec.md)), and a `supervision` row to each configured sink's outbox ([CST](central-run-stats.spec.md)), the fields being `marginal` and `turn` (`{tokens by kind, estimated_usd}` per category and in total), `sessions[]` (host, hashed host session, model, window, reported session figure) and `completeness` (`complete`, `estimated`, `incomplete`, `measured_zero` for only the supervisor or a pipeline, `none_known` for no supervising call seen, which is not zero); running from the next writing engine process on the machine, from `stats flush` and from the plugin's `SessionEnd` hook through `supervision close`, never from a read-only verb; the thread staying open before that.

- GIVEN a run started by a person who then did nothing WHEN it closes THEN completeness is `none_known` and no cost figure reads zero

### SCO-B16 Supervision verbs

WHEN a `supervision` verb runs THE engine CLI SHALL offer `supervision hook <event>` (the plugin hooks' entry, always exit 0); `supervision log --host <name> --session <id> [--caller-app <name>]`, appending JSON lines from standard input to that session's journal after schema checks (fixed fields, numbers in range, no free text beyond ids), exit 2 and nothing appended on a field outside the schema, free text or a negative number, spending nothing; `supervision close [--session <id>]`, closing what SCO-B15 allows into ledger lines and outbox rows; and `supervision show <selector> | --session <id> [--json]`, read-only, printing calls, person turns, categories, both figures and completeness; `report --supervision` and `stats --by level|decider|host` reading the closed figures ([SUP-B12](supervision-metrics.spec.md)).

- GIVEN `supervision log` input with a free-text field WHEN it runs THEN it exits 2 and the journal is unchanged

### SCO-B17 Privacy and retention

WHEN supervision data is kept or sent THE engine SHALL keep no prompt, command line, tool output or transcript text in the journal, only a verb word, resolved ids, counts, sizes and times; send host sessions and thread ids hashed in anything that leaves the machine ([CST](central-run-stats.spec.md)); keep journals 90 days like evidence ([LOS](local-observability-store.spec.md)), `store prune` removing a journal and its `.offsets.json` once its last entry is 90 days old and `--dry-run` listing them; and keep closed figures with the ledger.

- GIVEN a canary prompt and command WHEN the journal, ledger and sink rows are scanned THEN neither appears
- GIVEN a journal whose last entry is 91 days old and one with an entry from yesterday WHEN `store prune` runs THEN the first and its offsets file are removed and the second is kept

## Acceptance criteria

- SCO-AC1 (SCO-B1, SCO-B2, SCO-B3, SCO-B4, SCO-B7, SCO-B8, SCO-B9, SCO-B13, SCO-B14, SCO-B15): Fixture transcripts and journals reproduce the SCO-B1 categories and both figures by one attribution function, used by `supervision show`, `report --supervision` and the closer
- SCO-AC2 (SCO-B15, SCO-B16): Every read-only verb leaves the home store's journal and ledger unchanged (hash test, CLI-AC1)
- SCO-AC3 (SCO-B10, SCO-B17): A canary prompt, command and tool output appear in no journal entry, ledger line or sink row
- SCO-AC4 (SCO-B11): A hook failure injected at each entry kind leaves the host call's result and duration (within 2 s) unchanged
- SCO-AC5 (SCO-B5, SCO-B6, SCO-B12): Sessions with `TEMPERGRAPH_SESSION_KEY` write no journal entry, and `unknown` and unprobed hosts close `incomplete` with null cost
- SCO-AC6 (SCO-B3, SCO-B12): P-SUP-3 (`PostToolUse` input for `Bash` carries the command and the response size, and `Stop` and `SubagentStop` give a transcript path whose assistant lines carry usage) has a recorded result with date, machine and Claude Code version before the Claude Code row leaves `projected`, and on a live orchestration of three or more runs the share of [OSK](orchestrator-skill.spec.md) is computed by this spec
- SCO-AC7 (SCO-B17): `store prune` removes a journal and its offsets file whose last entry is 90 or more days old, keeps one with a newer entry, and with `--dry-run` lists them and removes nothing

## Open questions

- Should the `rewake` idle threshold follow the host's actual cache lifetime when the host reports it (the status line's `prompt_cache.ttl`)? Until answered: a fixed 300 s default. Owner: implementer.
- Should a team sink receive the session-level reported figure? Until answered: yes, hashed. Owner: owner.
- Not built yet: `measured_zero`, orchestration splits and the status line's `reported` entry wait for orchestrations and a status line; P-SUP-3 has not run. Owner: engine owner.
