# Script units and hybrid steps

## Purpose

Model-free work in a workflow: a script unit runs a declared command or a workflow callable with no model session, and a hybrid step runs `before` and `after` scripts around its one model session in the same attempt ([ADR `take-script-steps-attention-and-composition-from-archon`](../adr/take-script-steps-attention-and-composition-from-archon.adr.md)). Both run through the engine, never through an executor, so they behave the same whichever executor a workflow's model steps use; executor capability flags do not apply to them, the command rules of [SEC](security.spec.md) do. A script unit is still a gated unit: its gate holds the engine's built-in check, an optional author check and an optional judge ([ADR `new-node-kinds-keep-the-gated-unit`](../adr/new-node-kinds-keep-the-gated-unit.adr.md)). This spec also owns the per-thread result cache for scripts ([ADR `cache-only-model-free-script-results-per-thread`](../adr/cache-only-model-free-script-results-per-thread.adr.md)). It is LangGraph's function node in this engine's form ([research `node-types-against-langgraph`](../research/node-types-against-langgraph.rsrch.md) L1, L16). Workflow authors and the compiler depend on it; design notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### SCR-B5 Script declaration

WHEN a workflow declares a script THE engine SHALL read `ScriptSpec` with exactly one of `run` (a list of argv parts, a declared command prefix then arguments, each part a constant or exactly one template field `{name}` rendered to one argv element, never a shell string) and `call` (a callable in the package, `(ctx: ScriptContext) -> ScriptResult`); `produces` (map of key to `ArtifactKind`, for a hybrid `before` the keys the session may read); `inputs` (artifact keys and workspace paths, or `workspace`, required with a cache); `side_effects` (`none`, `workspace` or `external` when it changes something outside the workspace such as publishing, posting or uploading; default `workspace`); `timeout_s` (default 600); `cache` (`off` or `thread`, default `off`); `environmental_exit_codes` (exit codes meaning the environment, not the work, failed); and `summary` (60 characters at most, for diagrams); give a callable a `ScriptContext` of read-only `workdir`, `inputs`, `artifacts` and `request` inside the workspace (OVR-B12) and take back a `ScriptResult` of `ok`, `produces`, `environmental` and `message`, a `run` result derived from the exit code and the produced paths; and take `script` on a unit of kind `script` and `before` and `after` lists on a `StepSpec`, run in declaration order ([CON](contracts.spec.md)).

- GIVEN a script with both `run` and `call` WHEN validated THEN it is refused

### SCR-B6 What is refused

WHEN a workflow with scripts is validated THE engine SHALL refuse with an `error` both or neither of `run` and `call`; a `run` part that is not a constant or a single field, a constant with a shell metacharacter or a prefix outside the allow-list ([SEC-B5](security.spec.md)); `cache: thread` with `side_effects` other than `none` or with no `inputs`, since a cached side effect would be skipped; a `before` script with `side_effects: external`, which would publish before any judge saw the content; and a script unit with a judge and no `produces` of a readable kind; and SHALL warn on an `after` script with `side_effects: external` on a step whose gate has no approval and on a callable that imports beyond the engine's public interface.

- GIVEN a `before` script with `side_effects: external` WHEN validated THEN it is refused with its own finding code

### SCR-B7 One script unit attempt

WHEN a script unit attempt runs THE engine SHALL render the arguments, look up the cache, run the command or callable under the command rules of [SEC-B5](security.spec.md) and record exit code and duration; then grade with the built-in check (exit 0 or `ok`, and every `produces` key exists), the author's check and the judge if declared; then gate as any unit ([HUM](gate-and-human.spec.md)), a RETRY re-running the script under the same budget rules; and record each script as a `script` run event with phase `unit`, `before` or `after` ([EVT](run-events.spec.md)).

- GIVEN a script unit WHEN its run event is read THEN it has phase `unit`, the exit code and the duration

### SCR-B1 Script unit, no model call

WHEN a script unit runs THE engine SHALL start no executor and pass the built-in check only when every `produces` key exists.

- GIVEN a script unit `export` running `["make", "docs"]` that produces `site` (kind `file`) WHEN it runs THEN no executor starts, the step record shows `model_calls = 0`, the duration and exit code, and the built-in check passes only if `site` exists

### SCR-B2 Hybrid order

WHEN a hybrid step attempt runs THE engine SHALL run its `before` scripts, then the model session, then its `after` scripts only if the session ended `ok`, all in one attempt, a failed script failing the attempt and charging the retry budget and an environmental failure escalating without charging it.

- GIVEN `before: [fetch]` and `after: [publish]` with `fetch` exiting 0 and the session `ok` WHEN it runs THEN the log reads `script(before, fetch)`, `session_opened(step)`, `result`, `script(after, publish)` and the attempt is judged as usual
- GIVEN `fetch` exiting 2 WHEN it runs THEN no session starts, `publish` does not run, and the attempt fails with the retry budget charged
- GIVEN `fetch` exiting 75 listed in `environmental_exit_codes` WHEN it runs THEN no session starts and the attempt escalates without charging the budget
- GIVEN `fetch` exiting 0 and the session timing out WHEN it runs THEN `publish` does not run and the attempt is a timeout attempt ([BUD](budgets-and-failures.spec.md))

### SCR-B8 Script failures

WHEN a script fails THE engine SHALL fail the attempt hard when the prefix's program is not found (audit rule `check-program-missing` covering it before a run, [ARC](audit-rule-catalog.spec.md)), fail it as a timeout and kill the process group when `timeout_s` passes, and fail it with the exception type only, never crashing the run, when a callable raises.

- GIVEN a callable that raises WHEN the unit runs THEN the attempt fails naming the exception type and the run goes on

### SCR-B9 Cache

WHEN a script with `cache: thread` runs THE engine SHALL key it by a digest of the resolved argv (after `command_resolver`) or the callable reference with the workflow's content digest, the rendered arguments, and the content digest of each declared input (for `workspace`, the tree hash of tracked and untracked files outside the state root); on a hit restore the recorded `produces` files from `<thread folder>/cache/` and the recorded result, write the `script` event with `cached: true` and run nothing; treat an unreadable cache folder as a logged miss; and keep the cache with the thread ([LOS](local-observability-store.spec.md)).

- GIVEN an unreadable cache folder WHEN the script runs THEN it runs as a miss and the miss is logged

### SCR-B3 Cache hit on a trip back

WHEN a gate sends a run back past a cached script unit THE engine SHALL restore its outputs on the new visit when its inputs did not change, and run it again when one changed.

- GIVEN unchanged inputs WHEN revisited THEN outputs are restored, `cached: true` is logged and no time is spent beyond the digest
- GIVEN one input file changed WHEN revisited THEN it runs again

### SCR-B4 Executor-neutral

WHEN a script unit runs in a workflow whose model steps use any executor THE engine SHALL run it with the same argv, environment rules and records.

- GIVEN one workflow run with every model step on `claude` and again on `antigravity` WHEN a script unit runs THEN its argv, environment rules and records are identical

## Acceptance criteria

- SCR-AC1 (SCR-B6, SCR-B5): Every refusal of SCR-B6 has a fixture workflow that fails validation with its own finding code
- SCR-AC2 (SCR-B1, SCR-B4): A script unit run starts no executor (scripted executor records zero calls)
- SCR-AC3 (SCR-B2, SCR-B7, SCR-B8): Every scenario of SCR-B2 holds in an offline test
- SCR-AC4 (SCR-B9, SCR-B3): A cache hit and a miss are told apart in the run log, and a changed input always misses
- SCR-AC5 (SCR-B7): The run detail document shows each script with phase, exit code, duration and `cached` ([RDD](run-detail-document.spec.md))
