# A check is given the tool calls of the attempt's session, read from the activity journal

## Context

A gate's check holds a step to what the session left in the workspace, but nothing in the context it receives says what the session did (CHK-B10, [spec](../specs/75-check-contract-and-command-runs.spec.md)). A workflow can need that: temperspec asks its checks to confirm that a session opened the rule file its prompt names, opened the files its plan rows name, and wrote a phase's tests before its source (issues 129 to 131, [triage note](../../../temperspec-tgraph/docs/tasks/i129.triage.md)). The engine names no workflow ([ADR-0129](0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md)), so the answer is a capability any check can use.

What the code holds today, read in the engine:

- The check runs in a child process that receives the context as one JSON document on standard input; `context_doc` and `_context_from` list its fields (`run/check_worker.py` lines 26-71). The engine builds the context after the session ended, from state and the workspace (`run/nodes.py` lines 1474-1504).
- Each session writes an activity journal, one line per normalized event. `tool_started` carries the tool name, its capability and a scrubbed one-line `input_summary`, and `tool_finished` carries `ok` (`run/log.py` lines 435-450; `executors/claude.py` lines 263-286; EVT-B17, EVT-B21 in [30](../specs/30-run-events.spec.md)). For a read, an edit, a write and a list the summary is the path relative to the workspace, or `<outside workspace>` (`executors/summary.py` lines 77-110). Under `observe.tool_inputs = off` every summary is null (EVT-B6). Tool lines are the last to be dropped at the journal's cap (EVT-B7).
- The session result keeps only `{name, ok, subagent}` for each call, with no path (SSN-B5 in [25](../specs/25-session-contract.spec.md)).
- A retry runs a fresh session under its own key, told what was rejected and not resumed ([PRM-B5](../specs/04-prompt-rendering.spec.md)). A session started again after an infra try builds a new sink on the same folder, which appends to the same journal and counts its lines from 1 (`run/nodes.py` lines 332-356; `run/log.py` lines 346-377, 402-412).
- The scripted stand-in of the engine's tests pushes `tool_started` with a name, a call id and the subagent flag, and no capability or summary (`executors/standins.py` line 84).
- The check preview runs the check from a context document stored when the attempt began, while the session is still running and its journal is written in batches (`run/selfcheck.py` lines 40-48, CHK-B17).

## Decision

We will take option A and give a check `session`, the attempt's tool calls in call order, each with `name`, `capability`, `target` (the call's input summary) and `ok`, read from the attempt's activity journal after the session ended and passed to the check worker in the context document. It holds the calls since the session last started, so an infra try never shows a check calls of a session that died. It is `None`, never an empty list, when the attempt ran no step session, when the executor reported no capability for any call (a stand-in that reports names only, or a session that made no call), when the journal dropped a tool line, and in the check preview. The record is a copy for the check: the engine writes it to no run-log record, ledger row, stats row, export or filed text, so EVT-B21 holds as written.

## Options considered

### A. Build the record from the activity journal and add it to the check context (chosen)

For: one place reads the journal, with its cap, its restarts and its privacy rule, for every workflow; the capability and the path are the normalized ones, so the same check reads a session on any executor that reports them; the record holds no model text; a check stays a function of its context, which the preview and the worker already pass as a document. Against: the engine reads a file at each check; the context grows by about 100 bytes a call; a session that reports names only gives no record.

### B. Give the check the path of the session's folder and let it read the journal

For: no new context field. Against: every workflow re-reads a file layout and a line format that are not a contract, re-implements the cap, restart and truncation rules, and can copy a summary into a record that EVT-B21 keeps clear of them.

### C. Give the check the executor's native transcript

For: the fullest record. Against: only executors that declare a native transcript have one, and its path is not always known (EVT-B20); the formats differ by executor; it holds the model's text, which a check does not need and must not copy.

### D. Give the check the session result's calls

For: already in memory. Against: a call has a name and `ok` but no path, so none of the three requests can be answered.

## Consequences

A check can hold a session to what it did, in any workflow, on any executor that reports capabilities. A check that reads `session` must handle `None`: the check preview never has the record, because the session is still running and its journal is not complete, so a step that previews its own check sees the criteria that need the record as not applicable, and the gate's check, which runs after the session, decides. CHK-B9 keeps its sameness for a check that does not read `session`.

Risks, each with what limits it:

- A false failure from a partial record: no record is given when the journal dropped a tool line, and the calls of an earlier start are left out.
- A summary copied into a finding or evidence reaches the run log's check record, which clips evidence to 200 characters and scrubs it (EVT-B12): the engine cannot see what a check copies, so a workflow's spec says what its findings name.
- A record with null targets, under `observe.tool_inputs = off`: a check that needs a path treats it as no record.

Taken without the owner, who is away, and open to change: the record is built at the check and not kept; a session that made no call gives `None`; the preview gives no record (the alternative is to refresh the record from the live journal at each preview call, as the preview refreshes the git facts).

## Revisit when

A workflow needs the model's text or the call's full input, or the preview should show the record (the journal would then be flushed at each call).
