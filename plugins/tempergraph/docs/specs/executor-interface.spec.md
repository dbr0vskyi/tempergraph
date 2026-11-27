# Executor interface

## Purpose

The executor layer is the only part of the engine that knows how a model session is started. The engine hands an executor a session request as data ([SSN](session-contract.spec.md)); the executor starts one headless session (a CLI, or a library inside an engine worker process, [ADR `in-process-executors-run-in-a-worker-process`](../adr/in-process-executors-run-in-a-worker-process.adr.md)), translates its stream into normalized events and returns a result with typed usage. Executors declare what they can enforce, and preflight refuses before any spend what a workflow needs and its executor cannot do. Four executors are designed: [Claude Code](executor-claude-code.spec.md) (`claude`), the [Agent SDK](executor-agent-sdk.spec.md) (`agent-sdk`), the [Messages API](executor-messages-api.spec.md) (`messages-api`, whose loop the engine owns, [ADR `engine-owned-tool-loop-for-the-messages-api`](../adr/engine-owned-tool-loop-for-the-messages-api.adr.md)) and [Antigravity](executor-antigravity.spec.md) (`antigravity`); release 1 registers `claude` only ([ADR `first-release-ships-the-claude-executor-only`](../adr/first-release-ships-the-claude-executor-only.adr.md)). All share one session launcher that owns what the engine must not delegate: argv from constants, prompt delivery, the timeout, the idle watchdog, process-tree lifetime and the start record, because executors offer unequal limits ([research `executor-capability-matrix`](../research/executor-capability-matrix.rsrch.md), [ADR `executors-as-capability-adapters`](../adr/executors-as-capability-adapters.adr.md)). Workflow authors, operators and every executor spec depend on these rules.

## Depends on

- `budgets-and-failures.spec.md`: budgets, failures and timeouts
- `caller-provenance.spec.md`: a declaration cannot raise trust (PRV-B5); classification (PRV-B13); decider (PRV-B14); person turns (PRV-B15); where the block is written (PRV-B17); options (PRV-B18); engine sessions never drive the engine (PRV-B19)
- `executor-messages-api.spec.md`: worker request document (EMA-B8)
- `independence-guard.spec.md`: independence guard and judge views
- `observability-and-cost.spec.md`: observability and cost
- `run-events.spec.md`: common record envelope (EVT-B8); segment and sequence from the log (EVT-B9)
- `schedule-ticks-and-unattended-fires.spec.md`: unattended credential kinds (TCK-B18); credential check per executor (TCK-B19)
- `security.spec.md`: sanctioned launch sites (SEC-B7)
- `session-contract.spec.md`: session result (SSN-B5)
- `supervision-cost.spec.md`: supervising session (SCO-B9)

## Behaviours

### EXI-B16 Registry

WHEN the engine starts THE engine SHALL register the executors by the constant names `claude`, `agent-sdk`, `messages-api` and `antigravity`, in that order, let workflow data select one by name only (never a path or a command), let no environment variable select or substitute one, and let only the executor package import a concrete executor.

- GIVEN a step naming `claude` WHEN it is bound THEN the registered `claude` executor runs it
- GIVEN a step naming `my-agent` WHEN the run is preflighted THEN it exits 2 as an unknown executor

### EXI-B17 Probe report

WHEN an executor is probed THE executor SHALL report `ok`, a reason word (`missing`, `signed_out`, `version_unreadable` or `probe_failed`), the version, the resolved path and the facts it read, with no model call.

- GIVEN a machine without the `claude` binary WHEN preflight probes it THEN the run exits 2 with reason `missing`

### EXI-B18 Binding table

WHEN an alias is bound THE executor SHALL read the operator file `<home>/config/bindings.json`, let a typed alias only select an entry and never copy it into argv, and refuse a bound value that is not a plain model name.

- GIVEN a row binding `large` to `opus; rm -rf /` WHEN it is read THEN it is refused

### EXI-B28 Binding file rows

WHEN the bindings file is read THE executor SHALL take `schema_version` and `bindings[]`, one row per executor with `executor`, `provider` for library executors (`anthropic`, `bedrock`, `vertex` or `foundry`), `tiers`, `aliases`, `prices`, `model_params` for `messages-api` and `cli_path` for `agent-sdk`.

- GIVEN a row for `messages-api` with `provider` `bedrock` WHEN an alias of it is bound THEN its sessions go to that provider

### EXI-B29 Default bindings

WHEN no bindings file or row binds an alias of `claude` THE executor SHALL bind `small`, `medium` and `large` to `haiku`, `sonnet` and `opus` and pass no model for `inherit`.

- GIVEN no bindings file WHEN `medium` is bound on `claude` THEN the session runs on `sonnet`
- GIVEN `inherit` WHEN it is bound THEN no model is passed

### EXI-B1 Refuse before spend

WHEN a start, resume, batch or check is preflighted and a rule of EXI-B26 or EXI-B27 is not met THE engine SHALL exit 2 at the first miss, with no model call, naming the step, the executor and the missing capability.

- GIVEN `turn_cap` on an executor without it WHEN preflighted THEN it exits 2 and the state root is unchanged

### EXI-B26 Executors hold what each step needs

WHEN a run is preflighted THE engine SHALL require that every step's executor is registered and probes ok, every alias is in its executor's `binds_aliases` and every tool capability in its `tool_map`, every gated step's judge executor declares `restricts_judge_tools` and `prompt_off_argv`, `cost_cap_usd`, `fallback_alias` and `turn_cap` are in `session_options`, and enforced step tools have `enforces_step_tools`.

- GIVEN a step whose alias is not in its executor's `binds_aliases` WHEN preflighted THEN it exits 2 naming the alias
- GIVEN every step on a registered executor that holds its aliases and tools WHEN preflighted THEN the start goes on

### EXI-B27 Provider tools, permissions and unattended credentials

WHEN a run is preflighted THE engine SHALL require that `subagent`, `web_fetch` and `web_search` on `messages-api` are in its `tool_map` for the bound provider, that `--strict-permissions` finds no undeclared-tool finding, and that every binding of a scheduled start accepts the credential kind the profile provides unattended ([TCK-B18, TCK-B19](schedule-ticks-and-unattended-fires.spec.md)).

- GIVEN a scheduled start whose judge binding needs an interactive sign-in WHEN preflighted THEN it exits 2 with `judge_credential`

### EXI-B19 Preflight warnings and deferrals

WHEN preflight finds `effort` outside `session_options`, or a step whose template names a skill, agent or instruction file on an executor without `hosts_authoring_surface`, or a judge MCP view on an executor without `judge_mcp` THE engine SHALL record a warning, or for the MCP view defer it and render its criterion as out of reach, and let the run start.

- GIVEN a judge view of MCP server `jira` and a judge executor that declares `judge_mcp` false WHEN preflighted THEN the view is deferred and recorded, and the criterion renders as out of reach

### EXI-B2 Prompt delivery

WHEN the launcher starts a session THE launcher SHALL deliver the prompt on standard input, never on argv or in the environment, starting the write immediately after the process starts, before the stream parser and progress writer are attached.

- GIVEN a planted canary in a prompt WHEN any executor launches THEN the canary is in no argv and no environment value

### EXI-B20 Library executors run as workers

WHEN a library executor runs a session THE launcher SHALL start `[<engine interpreter>, "-m", <constant worker module>]` with the worker's request document, which holds the prompt, on standard input ([EMA-B8](executor-messages-api.spec.md)), and the worker SHALL re-validate every field before use.

- GIVEN a request document with an alias that is not bound WHEN the worker reads it THEN it refuses the session

### EXI-B21 Prompt window

WHEN the prompt is not taken within 30 s of spawn THE launcher SHALL stop the session with cause `prompt_not_delivered`, and a write that fails because the CLI closed its standard input SHALL be `broken_pipe`.

- GIVEN a stand-in CLI that never reads standard input WHEN launched THEN after 30 s the result's `infra_cause` is `prompt_not_delivered`

### EXI-B13 Prompt write measured

WHEN the prompt write ends THE launcher SHALL record the gap from spawn, and a gap above 1 s SHALL be a warning on the attempt record.

- GIVEN a prompt write that ends 1.4 s after spawn WHEN the attempt is recorded THEN it carries the gap and a warning

### EXI-B22 Caller variables

WHEN the launcher starts a session THE launcher SHALL set `TEMPERGRAPH_SESSION_KEY` to the session's key ([EVT-B8, EVT-B9](run-events.spec.md)) and remove `TEMPERGRAPH_SUPERVISOR_TOKEN`, `TEMPERGRAPH_CALLER` and `TEMPERGRAPH_CALLER_APP` from the session's environment, so a step can neither pose as the orchestration supervisor nor be counted as a supervising session ([PRV-B5, PRV-B18, PRV-B17, PRV-B14, PRV-B13, PRV-B19, PRV-B15](caller-provenance.spec.md), [SCO-B9](supervision-cost.spec.md)).

- GIVEN an engine started with `TEMPERGRAPH_CALLER=person` WHEN a step session reads its environment THEN the variable is absent and `TEMPERGRAPH_SESSION_KEY` is set

### EXI-B23 One launch site

WHEN an executor's model-free probe (`--version`, `--help`, `auth status`) or the host-speed timing runs THE engine SHALL start it through the launcher, so every executor process starts at one site ([SEC-B7](security.spec.md)).

- GIVEN a source scan WHEN it looks for process starts in executor code THEN it finds only the launcher

### EXI-B3 Timeout

WHEN no `result` event arrives within `timeout_s` of spawn THE launcher SHALL kill the whole process tree and return `timed_out = true` with the partial usage seen so far, recording the limit and its source layer.

- GIVEN `timeout_s = 600` WHEN no result arrives by 600 s THEN the tree is killed and the record names 600 and its layer

### EXI-B4 Idle watchdog

WHEN no stream line arrives for `idle_s` while no tool call is open, or for the larger of `idle_s` and the tool floor (default 900 s) while one is open THE launcher SHALL kill the tree and return `stalled = true`; judges never get an idle limit.

- GIVEN `idle_s = 300` and the model working WHEN the last line is 299 s old THEN the session goes on, and at 301 s it is killed as `stalled`
- GIVEN a `shell` tool in flight WHEN the last line is 600 s old THEN the session goes on, and at 901 s it is killed as `stalled`

### EXI-B15 Graceful stop

WHEN a stop (timeout, idle, signal or a drain request) runs THE launcher SHALL send a graceful stop to the session's process group, wait the grace period (default 10 s), and only then kill the tree, keeping what the session wrote as partial output and usage.

- GIVEN a session that ends by itself within the grace period WHEN the period ends THEN nothing is killed and the result is read normally
- GIVEN a session still running at the end of the grace period WHEN it ends THEN the tree is killed and the result is `partial`

### EXI-B5 Lifetime

WHEN the engine receives SIGTERM, SIGHUP or Ctrl+C, or a timeout fires THE launcher SHALL end every process in the session's tree (a POSIX process group, a Windows job object with kill-on-close), record the attempt as interrupted and keep the thread resumable; a session that ends by itself is released and what it left running is left alone.

- GIVEN a session with a grandchild process WHEN the engine receives SIGTERM THEN the grandchild is gone and the thread is resumable

### EXI-B6 No raise

WHEN a spawn error, a broken pipe or an unparsable stream occurs THE executor SHALL return a result with `ok = false`, an `infra_cause` ([SSN-B5](session-contract.spec.md)) and the usage seen, never an exception.

- GIVEN a stream ending with no result event WHEN the executor returns THEN `infra_cause` is `no_result`
- GIVEN a spawn failure WHEN the gate reads it THEN `spawn_failed` is retried outside the retry budget ([BUD](budgets-and-failures.spec.md))
- GIVEN a session ended by a cost or turn cap WHEN it returns THEN `error_kind` is `cap_reached` or `turn_cap` and it is not infra

### EXI-B7 Cause from structure

WHEN a failed session's cause is classified THE executor SHALL read it from structured facts only (exception type, exit code, presence of a `result` event, the CLI's typed retry category, an exact-equality text match listed by the executor spec), never from prose; `slow_host` is assigned by the gate from the host-speed record, never by an executor.

- GIVEN a stream whose last text says "rate limited" with no typed category WHEN classified THEN it is not `throttled`

### EXI-B8 Version stamp

WHEN a session is recorded THE engine SHALL record the `cli_version` from the executor's probe.

- GIVEN two runs on CLI versions 2.1.329 and 2.1.330 WHEN their records are compared THEN each names its version

### EXI-B9 Fresh judge

WHEN a judge's result reports a `session_id` equal to the step attempt's THE engine SHALL discard the judgement as an unresolved gap ([GRD](independence-guard.spec.md)).

- GIVEN a judge reporting the step's session id WHEN the gate reads it THEN the judgement is discarded and the run escalates

### EXI-B24 Judge executor selection

WHEN a judge executor is chosen THE engine SHALL take, in order, the operator override, the gate's judge executor, the step's executor if it declares `restricts_judge_tools`, the workflow's designated judge executor, then the first registered executor that declares it, and refuse at preflight when none does.

- GIVEN no override and no gate judge executor on a `claude` step WHEN selected THEN the judge runs on `claude`

### EXI-B10 Cross-executor judge

WHEN a step's executor cannot restrict judge tools and another registered executor can THE engine SHALL run the judge there, with the judge model resolved on the judge's own layer, and name both executors in the step and judge records ([ADR `cross-executor-judging`](../adr/cross-executor-judging.adr.md)).

- GIVEN step S on `antigravity` and a registered `claude` WHEN S's judge is selected THEN it runs on `claude` and both records name their executors

### EXI-B11 Conformance

WHEN a new executor is registered in a release THE executor SHALL have passed the conformance suite against a recorded stand-in of its CLI: prompt on standard input, list argv, tree kill on timeout and signal, no raise on every infra cause, usage never 0 when unknown, tool names reported in order, and every declared capability exercised.

- GIVEN the `claude` executor WHEN the conformance suite runs against its recorded stand-in THEN every check passes

### EXI-B25 Unconfirmed facts are not declared

WHEN a capability rests on a fact about a real binary that no probe has confirmed THE executor SHALL declare it `false` until the probe result is recorded ([ADR `judge-isolation-per-executor`](../adr/judge-isolation-per-executor.adr.md)).

- GIVEN `antigravity` with probes P-AG-1 and P-AG-2 not run WHEN its capabilities are read THEN `restricts_judge_tools` is false

### EXI-B12 Strict permissions

WHEN a start has `--strict-permissions`, or a workflow's validation reports no undeclared-tool finding THE engine SHALL apply `enforces_step_tools` to every step and refuse a step whose executor does not declare it, and never run an executor in an automatic-approval mode (Claude Code's or the SDK's `auto` or `bypassPermissions`).

- GIVEN `--strict-permissions` and a step on an executor without `enforces_step_tools` WHEN preflighted THEN it is refused
- GIVEN a step that calls an undeclared tool under enforcement WHEN the call is made THEN it is refused, not approved by a classifier

### EXI-B14 Host speed

WHEN a start is preflighted THE engine SHALL time one interpreter spawn and a walk of at most 2000 workspace entries with no model, and warn, naming the total, when it is above the floor (default 3 s), recording it so timeouts on that run can be sorted as `slow_host` ([OBS](observability-and-cost.spec.md)).

- GIVEN a host whose timing totals 4.2 s WHEN preflight runs THEN a warning names 4.2 s and the run starts

### EXI-B30 Launcher-owned workspace paths

WHEN an executor route declares `launcher_owned_paths` THE engine SHALL exclude those paths from the workspace fingerprint and from `changed_paths` before and after each session, and remove any that did not exist before the session once it ends.

- GIVEN a route that declares `launcher_owned_paths: [".codemie/"]` and a launcher that creates `.codemie/` WHEN the judge guard compares fingerprints THEN the path is excluded and the judgement is not discarded for it

## Acceptance criteria

- EXI-AC17 (EXI-B30): A declared launcher-owned path that changes during a judge session does not cause the guard to discard the judgement, and a path that did not exist before the session is removed after it ends

- EXI-AC1 (EXI-B16): No module outside the executor package imports a concrete executor, by a source scan
- EXI-AC2 (EXI-B1, EXI-B17, EXI-B26, EXI-B27): Every preflight rule of EXI-B1 refuses with exit 2 and leaves the state root unchanged
- EXI-AC3 (EXI-B2, EXI-B20): The prompt never appears in argv or the environment of any launch, by a planted-canary test against every executor, worker request documents included
- EXI-AC4 (EXI-B5): A timeout and each signal kill the whole tree, a grandchild included, on POSIX and Windows stand-ins
- EXI-AC5 (EXI-B4): The idle watchdog follows the scenarios of EXI-B4 with a replaced clock
- EXI-AC6 (EXI-B6, EXI-B7, EXI-B21): Every infra cause an executor reports can be produced by the stand-in and is classified without reading prose
- EXI-AC7 (EXI-B9): A judge whose reported session id equals its step's is discarded
- EXI-AC8 (EXI-B10, EXI-B24): A step on an executor without `restricts_judge_tools` gets its judge on a capable executor, or the start is refused
- EXI-AC9 (EXI-B11): Every registered executor passes the conformance suite
- EXI-AC10 (EXI-B13, EXI-B14, EXI-B15): The stop contract, the prompt-gap warning and the host-speed warning follow their scenarios with a replaced clock
- EXI-AC11 (EXI-B18, EXI-B29): With no bindings file the default tiers bind, and a bound value that is not a plain model name is refused
- EXI-AC12 (EXI-B19): Each warning or deferral of EXI-B19 is recorded and the run starts
- EXI-AC13 (EXI-B22, EXI-B23): Every launch sets the session key and strips the three caller variables, and a source scan finds no executor process started outside the launcher
- EXI-AC14 (EXI-B3, EXI-B8): A timed-out record names its limit and layer, and every session record carries its CLI version
- EXI-AC15 (EXI-B12, EXI-B25): No executor is started in an automatic-approval mode, and no capability resting on an unrun probe is declared true
- EXI-AC16 (EXI-B28): A bindings file with one row per executor in the stated fields binds each alias of that executor to its row's entry

## Open questions

- Should a running tool's CPU and IO growth count as activity for the idle watchdog ? Deferred until stalls are classified on real runs. Owner: engine owner. Until answered: only stream lines count, with the 900 s floor while a tool is open.
- May a step's filtered tool set include remote MCP servers? It rests on probe facts not yet run on any executor ([ADR `scope-of-planned-work`](../adr/scope-of-planned-work.adr.md)). Owner: engine owner. Until answered: no; a judge's view of a remote MCP server is deferred and recorded ([ECC-B15](executor-claude-code.spec.md)).
