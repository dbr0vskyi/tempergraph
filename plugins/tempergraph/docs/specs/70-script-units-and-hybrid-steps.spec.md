---
title: Script units and hybrid steps
type: component
status: ready-for-implementation
prefix: SCR
adrs: [0040, 0062, 0067]
---

# Script units and hybrid steps

## 1. Overview

Model-free work in a workflow: a **script unit** runs a declared command or a workflow callable with no model session, and a **hybrid step** runs `before` and `after` scripts around its one model session in the same attempt ([ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)). Both run through the engine, never through an executor, so they behave the same whichever of the four executors a workflow's model steps use. A script unit is still a gated unit: its gate holds the engine's built-in check, an optional author check and an optional judge. This spec also owns the per-thread result cache for scripts ([ADR-0067](../adr/0067-cache-only-model-free-script-results-per-thread.adr.md)). It is LangGraph's function node in this engine's form ([R-060](../research/R-060-node-types-against-langgraph.rsrch.md) L1, L16).

## 2. Contract

### 2.1 Script declaration

| Type | Field | Kind | Meaning |
|---|---|---|---|
| `ScriptSpec` | `run` | list of argv parts, optional | A declared command prefix followed by arguments. Each part is a constant or exactly one template field (`{name}`), rendered to one argv element; never a shell string. |
| | `call` | callable ref, optional | A function in the workflow package: `(ctx: ScriptContext) -> ScriptResult`. Exactly one of `run` and `call`. |
| | `produces` | map key → `ArtifactKind` | What it writes; for a hybrid `before`, keys the session may read. |
| | `inputs` | list of artifact keys and workspace paths, or `workspace` | What it reads; required when `cache` is set. |
| | `side_effects` | `none` \| `workspace` \| `external`, default `workspace` | `external` means it changes something outside the workspace (publishes, posts, uploads). |
| | `timeout_s` | positive int, default 600 | Wall-clock limit. |
| | `cache` | `off` \| `thread`, default `off` | §2.3. |
| | `environmental_exit_codes` | list of int, optional | Exit codes that mean "the environment, not the work, failed" (escalate, as a check's environmental FAIL). |
| | `summary` | text ≤ 60 chars | For diagrams. |
| `ScriptContext` | `workdir`, `inputs`, `artifacts`, `request` | read-only views | Paths are inside the workspace (contract C10). |
| `ScriptResult` | `ok`, `produces`, `environmental`, `message` | bool, map key → pointer, bool, one line | A callable's answer; for `run`, derived from the exit code and the produced paths. |
| `StepSpec` (CON §2.1) | `before`, `after` | list of `ScriptSpec`, optional | Hybrid step scripts, run in declaration order. |
| `UnitSpec` (CON §2.1) | `script` | `ScriptSpec`, for kind `script` | |

### 2.2 One script unit attempt

| Order | Node | Does |
|---|---|---|
| 1 | step | Renders the arguments, looks up the cache, runs the command or callable under the command rules of [SEC §2.1](14-security.spec.md), records exit code and duration |
| 2 | judge | Built-in check (exit 0 or `ok`; every `produces` key exists), then the author's check, then the judge if declared |
| 3 | gate, human | As for any unit ([HUM](07-gate-and-human.spec.md)); RETRY re-runs the script with the same budget rules |

A hybrid step attempt runs `before` scripts, then the model session, then `after` scripts (only if the session ended `ok`). A failed script fails the attempt and charges the retry budget; an environmental failure escalates. Each script is recorded as a `script` run event with phase `unit`, `before` or `after` ([EVT](30-run-events.spec.md)).

### 2.3 Cache

The key is a digest of: the resolved argv (after `command_resolver`) or the callable reference with the workflow's content digest; the rendered arguments; and the content digest of each declared input (for `workspace`, the tree hash of tracked and untracked files outside the state root). A hit restores the recorded `produces` files from `<thread folder>/cache/` and the recorded result, writes the `script` event with `cached: true`, and runs nothing. The cache lives and dies with the thread ([LOS](33-local-observability-store.spec.md)).

### 2.4 What is refused

| Refused before a run (`error`) | Why |
|---|---|
| Both or neither of `run` and `call` | One source of work |
| A `run` part that is not a constant or a single field; a constant with a shell metacharacter; a prefix outside the allow-list | [SEC §2.1](14-security.spec.md) |
| `cache: thread` with `side_effects` other than `none`, or with no `inputs` | A cached side effect would be skipped |
| A `before` script with `side_effects: external` | Publishing before any judge has seen the content ([ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md) risk) |
| A script unit with a judge and no `produces` of a readable kind | The judge would have nothing to read |

Warnings: an `after` script with `side_effects: external` on a step whose gate has no approval; a callable that imports anything beyond the engine's public interface.

## 3. Behaviours

**SCR-B1 Script unit, no model call.** Given a script unit `export` running `["make", "docs"]` that produces `site` (kind `file`), when it runs, then no executor is started, the step record shows `model_calls = 0`, the duration and exit code, and the built-in check passes only if `site` exists.

**SCR-B2 Hybrid order.** Given a step with `before: [fetch]` and `after: [publish]`, when its session ends `ok`, then the order in the run log is `script(before, fetch)`, `session_opened(step)`, `result`, `script(after, publish)`, all in one attempt.

| Event | `fetch` exit | Session | `publish` runs | Attempt result |
|---|---|---|---|---|
| A | 0 | ok | yes | judged as usual |
| B | 2 | — (not started) | no | failed, retry budget charged |
| C | 75 in `environmental_exit_codes` | — | no | escalation, budget not charged |
| D | 0 | timed out | no | timeout attempt ([BUD](08-budgets-and-failures.spec.md)) |

**SCR-B3 Cache hit on a trip back.** Given a cached script unit whose inputs did not change, when a later gate sends the run back past it, then the new visit restores its outputs, logs `cached: true` and spends no time beyond the digest; when one input file changed, it runs again.

**SCR-B4 Executor-neutral.** Given the same workflow run once with every model step on `claude` and once on `antigravity`, when a script unit runs, then its argv, environment rules and records are identical.

## 4. Error conditions

| Type | Result |
|---|---|
| Program of the prefix not found | Hard failure of the attempt; audit rule `check-program-missing` covers it before a run ([ARC](56-audit-rule-catalog.spec.md)) |
| Timeout | Attempt failed as a timeout; the process group is killed |
| Callable raises | Attempt failed with the exception type only; never a crash of the run |
| Cache folder unreadable | Treated as a miss; logged |

## 5. Design notes

- Scripts run under the engine, so executor capability flags do not apply to them; the command rules of SEC do.
- A judge on a script unit is for human-readable output (a generated report); a script whose output a check can grade needs none.
- Caching is limited to model-free work so that a judge always runs fresh on each subject and a step never replays a failed answer ([ADR-0067](../adr/0067-cache-only-model-free-script-results-per-thread.adr.md)).

## 6. Acceptance criteria

- [ ] SCR-AC-1 Every row of §2.4 has a fixture workflow that fails validation with its own finding code.
- [ ] SCR-AC-2 A script unit run starts no executor (scripted executor records zero calls).
- [ ] SCR-AC-3 Every row of the SCR-B2 table holds in an offline test.
- [ ] SCR-AC-4 A cache hit and a miss are told apart in the run log, and a changed input always misses.
- [ ] SCR-AC-5 The run detail document shows each script with phase, exit code, duration and `cached` ([RDD](31-run-detail-document.spec.md)).

## Open questions

None.

## References

[CON](01-contracts.spec.md) · [CMP](03-compiler-and-flow.spec.md) · [SEC](14-security.spec.md) · [ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md) · [R-012](../research/R-012-lessons-from-archon.rsrch.md) · [R-060](../research/R-060-node-types-against-langgraph.rsrch.md)
