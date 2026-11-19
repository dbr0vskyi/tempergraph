---
title: Executor interface
type: component
status: review
prefix: EXI
adrs: [0006, 0007, 0008, 0009, 0010, 0012, 0013]
---

# Executor interface

## 1. Overview

The executor layer is the only part of the engine that knows how a model session is started. The engine hands an executor a `SessionRequest` ([CON §2.6](01-contracts.spec.md)) as data: a rendered prompt, a workspace, an alias, declared tools, limits and options. The executor starts one headless CLI session, translates its stream into normalized events ([CON §2.7](01-contracts.spec.md)), and returns a `SessionResult` with typed usage. Executors **declare** what they can enforce; the preflight refuses, before any spend, what a workflow needs and its executor cannot do (contract C15).

Two concrete executors ship: [Claude Code](11-executor-claude-code.spec.md) (`claude`) and [Antigravity](12-executor-antigravity.spec.md) (`agy`). Both share one **session launcher** that owns everything the engine must not delegate to a CLI: argv building from constants, prompt delivery, the wall-clock timeout, the idle watchdog, process-tree lifetime and the start record ([R-003 §What the engine must own](../research/R-003-executor-capability-matrix.rsrch.md)).

## 2. Contract

### 2.1 Registry

```python
def register(executor: Executor) -> None: ...       # engine start-up only; constant names
def get(name: str) -> Executor: ...                 # raises UnknownExecutor at preflight
def available() -> list[str]: ...
```

Only modules of the executor package import a concrete executor. The names `claude` and `antigravity` are constants; workflow data selects one by name and never supplies a path or a command.

### 2.2 Binding table

A per-machine operator file maps aliases to model identifiers for each executor. It is read by the executor, never copied into argv as typed text: a typed alias only selects an entry.

| Field | Meaning |
|---|---|
| `executor` | `claude` or `antigravity` |
| `tiers` | `small`, `medium`, `large` → executor model name (for example `haiku`/`sonnet`/`opus`, or Gemini slugs from `agy models`) |
| `aliases` | executor-qualified names → model name or gateway deployment id |
| `prices` | optional per-model token prices for the engine estimate ([OBS](15-observability-and-cost.spec.md)) |

### 2.3 Session launcher

```python
class LaunchSpec:          # built only from executor constants and checked values
    argv: list[str]        # list form; no shell
    env_overlay: dict[str, str]  # constant names; values from constants or engine-owned paths
    stdin_payload: bytes   # the prompt, framed as the executor requires
    workdir: Path
    timeout_s: int
    idle_s: int | None
    idle_floor_tool_s: int # default 900

def launch(spec: LaunchSpec, parse_line: Callable[[bytes], list[Event]], sink: EventSink) -> RawOutcome: ...
```

`RawOutcome` holds the exit code, whether the process tree was killed and why (`timeout`, `idle`, `signal`), the receive time of each line, and the parsed events.

### 2.4 Judge executor selection

```python
def judge_executor(step_executor: str, gate_judge_executor: str | None,
                   operator_override: str | None) -> str: ...
```

Order: operator override, the gate's judge executor, the step's executor if it declares `restricts_judge_tools`, else the workflow's designated judge executor, else the first registered executor that declares it. No candidate is a preflight refusal.

## 3. Behaviours

**EXI-B1 Refuse before spend.** Given a workflow, when a start, resume, batch or check is preflighted, then every rule below is checked with no model call and the first miss exits 2 naming the step, the executor and the missing capability.

| Need in workflow data | Required declaration | Miss |
|---|---|---|
| Any step on executor E | E registered, `probe()` succeeds | exit 2 |
| Alias A on executor E | `A ∈ binds_aliases` | exit 2 |
| Tool capability T on a step | `T ∈ tool_map` | exit 2 |
| A gated step | its judge executor declares `restricts_judge_tools` and `prompt_off_argv` | exit 2 |
| `cost_cap_usd`, `fallback_alias`, `turn_cap` | option in `session_options` | exit 2 |
| `effort` | option in `session_options` | warning, recorded |
| Enforced step tools (operator opt-in) | `enforces_step_tools` | exit 2 |
| A judge MCP view of server S | `judge_mcp` | the view is deferred, recorded, and the criterion renders as out of reach |
| `idle_s` | always available (engine-owned) | — |

**EXI-B2 Prompt delivery.** Given a rendered prompt, when the launcher starts the session, then the prompt reaches the CLI on stdin, never on argv or in the environment, and the writer starts immediately after the process starts, before the stream parser and progress writer are attached.

**EXI-B3 Timeout.** Given a session with `timeout_s = 600`, when no `result` event arrives within 600 s of spawn, then the launcher kills the whole process tree and returns `timed_out = true` with the partial usage seen so far; the record names the limit and its source layer.

**EXI-B4 Idle watchdog.** Given `idle_s = 300`, when no stream line arrives for 300 s while no tool call is open, or for max(300, 900) s while one is open, then the tree is killed and the result carries `stalled = true`. Judges never receive an idle limit.

| State | Last line age | Open tool | Action |
|---|---|---|---|
| model working | 299 s | — | wait |
| model working | 301 s | — | kill, `stalled` |
| tool in flight | 600 s | `shell` | wait (floor 900 s) |
| tool in flight | 901 s | `shell` | kill, `stalled` |

**EXI-B5 Lifetime.** Given any running session, when the engine receives SIGTERM, SIGHUP or Ctrl+C, or a timeout fires, then every process in the session's tree ends (POSIX process group; Windows job object with kill-on-close), the attempt is recorded as interrupted and the thread stays resumable. A session that ends by itself is released, and what it left running is left alone.

**EXI-B6 No raise.** Given a spawn error, a broken pipe or an unparsable stream, when the executor returns, then it returns a `SessionResult` with `ok = false` and an `infra_cause` from [CON §2.6](01-contracts.spec.md), never an exception, and the result carries whatever usage was seen.

**EXI-B7 Cause from structure.** Given a failed session, when the cause is classified, then it is read from structured facts only (exception type, exit code, presence of a `result` event, the CLI's typed retry category, an exact-equality text match listed by the executor spec) and never from prose.

**EXI-B8 Version stamp.** Given any session, when it is recorded, then the record carries `cli_version` from the executor's probe, so a behaviour change between CLI releases can be told from a workflow change.

**EXI-B9 Fresh judge.** Given a judge session, when its result reports a `session_id` equal to the step attempt's, then the judgement is discarded as an unresolved gap ([GRD](06-independence-guard.spec.md)).

**EXI-B10 Cross-executor judge.** Given step S on `antigravity` whose capabilities say `restricts_judge_tools = false` and a registered `claude` executor that says `true`, when the judge executor is selected, then S's judge runs on `claude` with the judge model resolved on the judge's own layer, and the step record and judge record name their executors.

**EXI-B11 Conformance.** Given a new executor, when it is registered in a release, then it has passed the conformance suite against a recorded stand-in of its CLI: prompt on stdin, list argv, tree kill on timeout and signal, no raise on every infra cause, usage never 0 when unknown, tool names reported in order, and every declared capability exercised.

## 4. Error conditions

| Type | Raised where | Handling |
|---|---|---|
| Unknown executor | Registry, at preflight | Exit 2 |
| Executor probe failed (CLI missing, not signed in) | Preflight | Exit 2 with the probe's reason word |
| Capability missing | Preflight | Exit 2, per EXI-B1 |
| Spawn failure | Launcher | `infra_cause = spawn_failed`, retried outside the retry budget ([BUD](08-budgets-and-failures.spec.md)) |
| Prompt not accepted within the CLI's stdin window | Launcher | `infra_cause = prompt_not_delivered` |
| Stream ends with no result event | Executor | `infra_cause = no_result` |
| Session ended by a cost or turn cap | Executor | `ok = false`, `error_kind = cap_reached` or `turn_cap`; not infra |

## 5. Design notes

- Executors are adapters over CLIs, not over model APIs, so each step can use the CLI's own agent loop, tools, skills and MCP support ([ADR-0006](../adr/0006-executors-as-capability-adapters.adr.md)). An SDK or hosted executor can be added later behind the same protocol.
- Timeouts, idle limits and process lifetime are engine-owned because the two CLIs offer unequal limits ([R-003](../research/R-003-executor-capability-matrix.rsrch.md)).
- Capabilities that rest on an unconfirmed fact about a real binary are declared `false` until a probe result is recorded in the executor spec; a refuted fact costs a refusal, not a safety property ([ADR-0010](../adr/0010-judge-isolation-per-executor.adr.md)).
- The normalized event stream is the single feed for the live progress file, the idle watchdog and the time profile ([ADR-0009](../adr/0009-normalized-session-event-stream.adr.md)).

## 6. Acceptance criteria

- [ ] EXI-AC-1 No module outside the executor package imports a concrete executor (source-scan test).
- [ ] EXI-AC-2 Every preflight rule of EXI-B1 refuses with exit 2 and nothing created (state root unchanged).
- [ ] EXI-AC-3 The prompt never appears in argv or the environment of any launch (planted-canary test against both executors).
- [ ] EXI-AC-4 A timeout and each signal kill the whole tree, including a grandchild process (stand-in test on POSIX and Windows).
- [ ] EXI-AC-5 The idle watchdog follows the table of EXI-B4 with a replaced clock.
- [ ] EXI-AC-6 Every `InfraCause` value can be produced by the stand-in and is classified without reading prose.
- [ ] EXI-AC-7 A judge whose reported session id equals its step's is discarded.
- [ ] EXI-AC-8 A step on an executor without `restricts_judge_tools` gets its judge on a capable executor, or the start is refused.
- [ ] EXI-AC-9 Both shipped executors pass the conformance suite.

## Open questions

| Question | Owner |
|---|---|

## References

