# Rationale carried from the engine specs

## Problem statement

The engine's specs moved to temperspec's spec format on 2026-11-22 ([spec-migration plan](../plans/spec-migration.plan.md)). That format keeps only what the system does: no design notes, no release history, no "as built" notes, no probe tables and no maturity flags. Much of what those parts said is already held by the decision record or research note the spec links. This note keeps the rest, unchanged in substance, so that no reason or recorded observation is lost: one finding per spec prefix, in spec number order. A spec's Purpose links here; an old reference `PREFIX §5` (design notes) resolves to the finding for that prefix.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| The engine specs as they stood on `main` before the migration (design notes, release and "as built" notes, probe tables, error tables) | Design set | `plugins/tempergraph/docs/specs/*.spec.md` at the migration's base commit |
| The decision records and research notes those specs link | Design set | `plugins/tempergraph/docs/adr/`, `plugins/tempergraph/docs/research/` |
| The engine source, read where a note claimed something was or was not built | Code | `plugins/tempergraph/engine/src/tempergraph/` |
| The POSIX `crontab` utility description, as mirrored by the Arch Linux manual pages (read through a search result excerpt; the page could not be fetched) | Standard | https://man.archlinux.org/man/crontab.1p |
| GNU Micron manual, "Day Field Semantics" (read through a search result excerpt) | Documentation | https://gnu.org.ua/software/micron/manual/Day-Field-Semantics.html |
| RFC 5545 erratum 4271, section 3.3.10 against section 3.3.5 (read through a search result excerpt) | Standard erratum | https://www.rfc-editor.org/errata/eid4271 |

## Key findings

Each finding is `supported`: its one source is the spec's own text before the migration, checked against the code where it claims what is built.

### F1 OVR System overview `supported`

From [overview.spec.md](../specs/overview.spec.md).

- Ecosystem for mechanism, bespoke for policy: the graph, checkpointer and interrupt come from LangGraph (ADR `langgraph-graph-runtime`); the gate funnel, executors, registry and input resolution are tempergraph's own.
- Rules taken as requirements: no self-grading, retries as edges, unmeasured never zero, constants-only argv, one interrupt per gate.
- The engine-wide contracts C1 to C18 were a table owned per row by one spec, and a change that cannot keep one is a design change. They are now behaviours OVR-B3 to OVR-B20 in order (C<n> is OVR-B<n+2>); the owner spec named in each still holds the detail.
- The layer diagram (a mermaid flowchart) was dropped; the layers are prose in Purpose. Shell skills and the read-only monitor sit above the engine CLI; the engine reaches `claude -p`, `agy` stream-json, an SDK worker and an API worker with its own loop and tool host.
- Origin of each spec block: C15 states the preflight rule for four executors with unequal capabilities. Specs `executor-messages-api`, `executor-agent-sdk` and `tool-host` are numbered after the existing set so no earlier link changes. C16 and specs `orchestration` and `orchestrator-skill` come from the owner's request for an orchestrator of runs (ADR `orchestration-is-data-run-by-a-model-free-supervisor`). Specs `improvement-proposals`, `feedback-and-judge-reliability`, `workflow-lessons` and `improvement-data` extend the self-improvement loop (ADR `improvement-closes-through-measured-proposals`). Specs `judge-calibration` and `eval-suites` come from a block reserved for the judge and eval work. Specs `engine-update`, `version-metadata`, `state-and-run-migration`, `workflow-upgrade`, `upgrade-workflow` and `lifecycle-skills` come from the owner's requests of 2026-11-20 for an engine install and update command, a workflow upgrade command and skills that drive them (research `engine-update-and-workflow-upgrade-gaps`). Specs `script-units-and-hybrid-steps`, `council-unit`, `contest-unit`, `ask-unit` and `flow-extensions` come from the owner's request of 2026-11-20 to support what LangGraph supports and to add a council node and similar units (research `node-types-against-langgraph`, ADR `new-node-kinds-keep-the-gated-unit`). Specs `check-contract-and-command-runs`, `step-values-and-template-keys`, `map-unit`, `finalizer-contract` and `measured-switches` come from the owner's request of 2026-11-20 to verify that the engine holds everything a delivery workflow needs (research `temperspec-needs-against-the-engine`). Specs `run-settings-and-overrides` and `reruns-and-feedback` come from the owner's request of 2026-11-20 to override workflow configuration in every variation and to retry, rerun and resume with feedback (research `config-overrides-and-reruns-gaps`, ADR `one-catalog-of-run-settings-over-fixed-layers`, ADR `rewind-on-the-thread-rerun-as-a-linked-fork`). Spec `worktree-mode` comes from the owner's request for native worktree support (research `native-worktrees-and-executor-worktree-features`, ADR `the-engine-owns-the-run-worktree-executor-worktrees-are-not-used`). Specs `caller-provenance`, `supervision-metrics` and `supervision-cost` and C17 come from the owner's request to tell a person from an agent or the orchestrator babysitting a run and to measure supervision and its cost (research `callers-supervision-and-babysitting-cost`, ADR `classify-callers-by-the-strongest-signal`, ADR `supervision-is-a-promotion-and-improvement-measure`). Specs `schedules` and `schedule-ticks-and-unattended-fires` and C18 come from the owner's request for a schedule command with human-readable dates (research `scheduling-runs-prior-art-and-gaps`, ADR `a-model-free-tick-behind-os-agnostic-triggers`, ADR `a-scheduled-fire-is-an-attested-caller-with-capped-spend`). Specs `workflow-package`, `workflow-authoring`, `run-outcome` and `blueprint-and-scaffold` come from the owner's direction that creating a workflow produces a Claude plugin with its own prompts, agents, skills, Python code and specs, and that authoring centres on a run-level good outcome (research `workflow-packages-authoring-and-good-outcomes`, ADR `a-workflow-package-is-one-claude-plugin`, ADR `the-good-outcome-is-one-data-file-of-final-and-intermediate-outcomes`). Specs `run-events`, `run-detail-document`, `run-control`, `local-observability-store`, `central-run-stats` and `telemetry-export` hold the observability design asked for on 2026-11-19 (research `observer-needs-against-engine-documents`). Specs `effort-ladder-and-model-escalation`, `judge-model-by-risk`, `complexity-routing`, `promotion-check`, `run-state-on-a-branch` and `windows-support` are release 2 (ADRs `ladders-climb-only-on-trusted-substantive-evidence`, `a-judge-is-raised-by-a-model-free-risk-rule`, `complexity-chooses-a-decomposition-through-a-measured-switch`, `promotion-is-a-model-free-stamp-per-workflow-version`, `release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing`, `a-run-carries-scrubbed-thread-state-on-its-own-branch`, `outside-git-the-state-root-is-found-by-walk-up` and `windows-is-supported-natively-with-job-objects`) and 99 release 3 (ADR `a-sub-workflow-runs-inside-its-parents-thread-workspace-and-cap`).
- Engine naming removed (ADR `the-engine-names-no-workflow`): goal G12 named temperspec as its example delivery workflow; it now says "a delivery workflow". Specs `run-options` ROP and `lifecycle-hooks` HOK were split out of `engine-cli` CLI, and `session-contract` SSN out of `contracts` CON, by this migration to keep each under the cap; Purpose lists them.
- The old acceptance criterion "follows the six-section layout" now reads "follows the spec rule" (temperspec's `rules/spec.rule.md`).

### F2 WFM Workflow model and validation `supported`

From [workflow-model.spec.md](../specs/workflow-model.spec.md).

- Routing metadata sits on the spec so a classifier can pick a workflow without the engine naming one (ADR `workflows-as-data`).
- Workflows declare neutral tiers and capabilities so a team can move a step between executors by changing one field (ADR `portable-model-aliases`).
- A workflow package is imported into the engine's process. Isolation is by rule and review, not a sandbox: workflows import the engine's public interface only, and new dependencies pass the dependency gate.
- Why some findings only warn: an undeclared tool named in a prompt and a `none` blocker become errors in `stable`; `effort` an executor cannot apply changes cost, not safety; a missing `check_method` is judge quality, graded by readiness; a qualified alias is a portability matter; a prompt naming a skill on an executor with no authoring surface may still work if the template carries the content; a judge brief branching on computable facts belongs in a check or a route.
- As built (R2-T7): kinds `ask`, `wait` and `parallel` entered the release; `council`, `contest` and `subworkflow` stayed `not_in_release`.

### F3 CMP Compiler and flow `supported`

From [compiler-and-flow.spec.md](../specs/compiler-and-flow.spec.md).

- Edges are static so the engine never pays for work the author did not choose; position in `order` is never a fallback.
- An engine-owned join replaces LangGraph's deferred node, which cannot tell a stopped branch from a finished one.
- LangGraph features left out on purpose: a node routing itself or its parent with `Command`, `RetryPolicy` on model and judge nodes, `defer`, and the functional API; each conflicts with the engine-wide rules on self-grading, pure gates, one interrupt per gate or workflows as data ([research `node-types-against-langgraph`](node-types-against-langgraph.rsrch.md)).

### F4 JDG Judge and verdict `supported`

From [judge-and-verdict.spec.md](../specs/judge-and-verdict.spec.md).

- Self-grading passes well-formatted, wrong output; a fresh read-only session and a derived verdict prevent that (ADR `independent-judge-engine-verdict`).
- A judge on a different model family than its producer is a feature, not a fallback: a model tends to rate its own kind of output well. Cross-executor judging makes that cheap (ADR `cross-executor-judging`).
- A panel of voting judges is deferred. A council (CNL) is a step whose combined output one judge grades; it is not a panel. Sampled audit judging is a measurement, recorded only, never routing; its agreement rates feed calibration (LIF) and the confidence-against-outcome study (SIL).
- Whether a judge's grades can be trusted is measured outside the judge spec (JCL). Acceptance never changes a verdict. An audit judge's agreement measures consistency, not correctness, so it never counts as a gold label (ADR `judges-accepted-on-labelled-error-rates`).
- The `no_change` flag is the judge's claim; a workflow that finds it misused sets `no_change_policy: retry` on that criterion.
- The brief's last two rules (only the given tools; each criterion on its own) were added after live judge sessions tried a shell for git and lowered one criterion for another's missing evidence. The check-evidence labelling and the exclusion of `person` and `none` criteria come from live check L-25, where a judge that graded a sign-off answered UNVERIFIABLE for it.

### F5 GRD Independence guard and judge views `supported`

From [independence-guard.spec.md](../specs/independence-guard.spec.md).

- Absent beats denied: where an executor can, a write tool is not in the session at all. On `messages-api` the engine offers the tools, so absence is a fact of the request, tested by contract. Antigravity cannot remove tools by flag, so it sits on the rule and guard layers until probes confirm the absence layer (ADR `judge-isolation-per-executor`, ADR `isolated-config-home-for-antigravity`).
- The open edge of a judge calling a plugin-registered tool is closed on Claude Code by `--bare` once P-CC-1 passes; the guard remains the backstop and still voids such a verdict.
- The guard does not depend on any executor's permission layer.

### F6 HUM Gate and human nodes `supported`

From [gate-and-human.spec.md](../specs/gate-and-human.spec.md).

- Recording an `agent` resume apart keeps an orchestrating session's answers from being counted as a person's.
- A delegation policy for which pauses an agent may answer is out of scope for the first release.

### F7 BUD Budgets, failures and timeouts `supported`

From [budgets-and-failures.spec.md](../specs/budgets-and-failures.spec.md).

- Infra failures outside the retry budget, and never a pause: if a failed judge paused the gate, a person's proceed could pass a step no judge had seen.
- The idle watchdog is executor-neutral because it reads normalized events (EXI); Antigravity has no turn cap, so the engine's limits are its only bounds (research `executor-capability-matrix`).
- Text is never classified, except the one exact-equality match each executor spec lists.
- The run cost cap reads the same figure the run line shows, so an operator sees why a run drained.
- `run.auto_reopen` counts per thread (assumption recorded as an owner question, now stated as behaviour): every automatic re-open of the thread counts toward N, and a person's retry does not reset it.

### F8 EXI Executor interface `supported`

From [executor-interface.spec.md](../specs/executor-interface.spec.md).

- Executors are adapters over agent harnesses by default, so each step can use the harness's own agent loop, tools, skills and MCP support ([ADR `executors-as-capability-adapters`](../adr/executors-as-capability-adapters.adr.md)); the Messages API executor is the one exception ([ADR `engine-owned-tool-loop-for-the-messages-api`](../adr/engine-owned-tool-loop-for-the-messages-api.adr.md)).
- The normalized event stream is the single feed for the live progress file, the idle watchdog and the time profile ([ADR `normalized-session-event-stream`](../adr/normalized-session-event-stream.adr.md)).
- A refuted probe fact costs a refusal, not a safety property ([ADR `judge-isolation-per-executor`](../adr/judge-isolation-per-executor.adr.md)).

### F9 ECC Claude Code executor `supported`

From [executor-claude-code.spec.md](../specs/executor-claude-code.spec.md).

- `--bare` is the cleanest answer to the open edge of a judge reaching a plugin-registered tool. It is gated on P-CC-1 because it changes authentication and loads nothing the user configured (ADR `judge-isolation-per-executor`).
- The permission mode is always passed explicitly because the `-p` default has changed between releases (research `claude-code-cli-headless` F14).
- A resumed session is never used for a retry: a fresh session told the last report costs less than one that carries the whole conversation (research `claude-code-cli-headless` F20).
- P-CC-1 observation on 2.1.330 in the cloud container (2026-11-21): with a plugin installed at user scope, `system/init` under `--bare` still listed it, with the session's tools unchanged, so `isolates_user_config` stays false. Plugins the CLI build carries itself (source `@builtin`) stay listed and are not user configuration.
- Model-free checks on 2.1.329 (2026-11-20, argument parsing only, in the engine's cloud build container): `--help` lists the permission modes `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk` and `plan`; `default` is no longer listed but is still accepted. `--max-turns` is accepted though not listed. `--permission-prompts` takes `host` or `none`. `-p` with an empty stdin and no positional prompt fails with "Input must be provided either through stdin or as a prompt argument", which shows stdin is read as the prompt but does not confirm P-CC-5. `auth status` prints JSON with `loggedIn`. No live probe was run there: a nested session inherits the host session's environment, so its result would not stand for the owner's machine.
- Step reach inside a host session (ECC-B14) comes from a live run on 2.1.330 inside a Claude Code session: a step was offered the host's tools and additional directories and one step read a file outside the workspace (research `release-three-readiness-and-gaps` F4). The allow rules held, but reach was wider than the declaration.

### F10 EAG Antigravity executor `supported`

From [executor-antigravity.spec.md](../specs/executor-antigravity.spec.md).

- Plan mode is only a prompt prefix in the docs, so the executor never relies on it for a read-only judge ([research `antigravity-cli-headless`](antigravity-cli-headless.rsrch.md) A12).
- An isolated home is inferred from the documented fixed paths, not documented as supported; that is why it is a probe-gated capability ([ADR `isolated-config-home-for-antigravity`](../adr/isolated-config-home-for-antigravity.adr.md)).
- The gatekeeper answers only `deny`: an `allow` from a hook was reported ignored in print mode, while `deny` was honoured (research `antigravity-cli-headless` A16).
- The engine's timeout is the bound; `--print-timeout` is set slightly above it only as a second stop if the engine dies.

Probes, to be run by the owner on the pinned version with a throwaway workspace; none has run.

| Id | Fact to confirm | Unlocks | Result |
|---|---|---|---|
| P-AG-1 | With `HOME` pointed at a session home, `agy` reads settings, hooks and MCP config only from there, and authenticates (API-key mode or copied sign-in) | isolated mode | not run |
| P-AG-2 | A PreToolUse hook runs in headless stream mode and its `deny` blocks every tool, subagent tools included | gatekeeper | not run |
| P-AG-3 | A subagent inherits the session's rules and hooks, and cannot be given write tools by the model | `restricts_judge_tools` | not run |
| P-AG-4 | Default and behaviour of `--print-timeout`; status and exit of a timed-out turn | timeout layering | not run |
| P-AG-5 | A stream-json session never continues an earlier conversation of the workspace | `fresh_session` | not run |
| P-AG-6 | The tool name `agy` reports for an MCP tool, in `init.tools` and `step_update.tool_name` | MCP view catalog | not run |
| P-AG-7 | The values of `result.error.type` for auth, quota and model errors | classification | not run |
| P-AG-8 | `permissions.allow` `command(<prefix>)` entries are honoured in stream mode on the pinned version | `step_allow_rules` | not run |
| P-AG-9 | The tool that loads a skill from `.agents/skills/`, and whether a permission rule can scope it to one skill | `skill:` capability | not run |
| P-AG-10 | Whether `agy` loads a plugin folder placed under the isolated config home (`~/.gemini/config/plugins/<plugin>/skills/`) | workflow skills on `antigravity` (PKG) | not run |

### F11 WSP Workspace and concurrency `supported`

From [workspace-and-concurrency.spec.md](../specs/workspace-and-concurrency.spec.md).

- The default concurrency of three is a guess for every executor: no gateway's or API organization's concurrent-session or rate limit was measured. On `messages-api` and `agent-sdk` a 429 with `retry-after` is `throttled` (infra).
- A merge is textual; two branches that merge cleanly but contradict each other are caught only by the join's judge or a check.
- Cleanup is never automatic unless a run sets `run.worktree.cleanup: on_finish`, which removes only clean worktrees; branches are never deleted (WTR).
- As built (R2-T7): parallel branches run on the graph runtime's own threads in one workspace; the run log's writer takes a lock, and a state write asked for while several nodes are pending is deferred to the segment's end.
- As built (R2-T8): `workspace: none` is not built yet; a finalizer's push cannot be refused ahead outside git, since a finalizer declares nothing, so it receives `git = None`; `upgrade` refuses outside a repository by its own rule. A single file's SHA-256 is kept for reports and is not part of the fingerprint.

### F12 SEC Security posture `supported`

From [security.spec.md](../specs/security.spec.md).

- Antigravity's configuration surface includes workspace files a repository controls (`.agents/`). Because the engine cannot point `agy` away from them by flag, the guard, not the configuration, is what the judge's independence rests on ([ADR `judge-isolation-per-executor`](../adr/judge-isolation-per-executor.adr.md)).
- The launch sites name these constant modules on the engine interpreter's argv: `tempergraph.executors.sdk_worker`, `tempergraph.executors.api_worker`, `tempergraph.checks.worker`, `tempergraph.observe.sinks flush`, `tempergraph.improve.child drain`, `tempergraph.observe.hooks drain`, `tempergraph.install.selfcheck`, `tempergraph.install.reconcile`; detached starts go through `tempergraph.detach` and the updater's through `tempergraph.install.launch`.

### F13 OBS Observability and cost `supported`

From [observability-and-cost.spec.md](../specs/observability-and-cost.spec.md).

- Antigravity and the Messages API report no cost; Claude Code and the Agent SDK report a client-side estimate. One engine price table gives every executor a comparable estimate without trusting any as billing truth (ADR `cost-when-executor-reports-tokens-only`).
- The live file and metrics come from normalized events, so they work the same on every executor (ADR `normalized-session-event-stream`).
- Self-improvement children log to their own run logs; a daily cap sums them, and reports join them to the parent's line as a separate figure.
- Export is off by default. An operator may configure sinks of metadata-only rows and OTLP telemetry (CST, TEL); content never leaves the machine.
- The report rows on first visits, arms, criteria, prompt digests, stalls and timeouts, and the loop signal were added from the planned capabilities of research `planned-work-coverage`.
- Release 1 build (T7.4): `report` and `stats` read the run logs and the home stats rows. Deviations then recorded: the timeout classes use the `agent_run` record's `slow_host` (at least 60% of wall time in tool calls); each unit row adds `agent_s`; the time profile counts the activity journal's `duration_s`; a repeat's cause is the visit's `entered_from` or the gate that sent it back; `attempt_start` carries `prompt_digest`. The overlay is built in `observe/overlay.py`; `--format svg` is not built. The stats row's supervision fields come from the segment's `supervision` record (T7.5).
- As built (R2-T7): record kinds `answers` and `self_check` were added; `run_exit` carries `degraded: true` after a fallback, and a `pause` record `deadline_at` when the unit has a deadline (both kinds owned by EVT).

### F14 SIL Self-improvement loop `supported`

From [self-improvement.spec.md](../specs/self-improvement.spec.md).

- Release 1 code layout, kept for readers of older notes: cause codes, classes, sides and remedies are one table in `improve/causes.py`; thresholds are parameter records in `improve/params.py`; filing is `improve/filing.py`, measurement `improve/measure.py`, the loop child `improve/child.py`, started as `tempergraph.improve.child drain`.
- The friction judge sees metadata only: the evidence file stays with the recorder.

### F15 LIF Lifecycle and evals `supported`

From [lifecycle-and-evals.spec.md](../specs/lifecycle-and-evals.spec.md).

- A cached plugin copy whose version did not move is never refreshed; a repository check fails a package that changed without a version bump.
- Skills are evaluated with Claude Code's plugin eval; no harness for Antigravity skills is assumed.
- Release 1 records `claude` 2.1.329 only in the executor compatibility table, from the model-free argument checks of the Claude Code executor spec. The package's stand-in run is `tempergraph.package.selftest`.
- Judge scores arrived with JCL (plan T12); until a binding is `accepted` no gate grades `ready`, so a `stable` workflow is refused until its judges are accepted.

### F16 SHL Plugin shell `supported`

From [plugin-shell.spec.md](../specs/plugin-shell.spec.md).

- The authoring surface of a workflow (agents, skills, rules) may need two forms, one per executor; that is a workflow decision ([ADR `portable-authoring-surface`](../adr/portable-authoring-surface.adr.md)). `claude` and `agent-sdk` share one form.
- The bootstrap skill's helper `scripts/ignore_rule.py` is the only writer of the root `.gitignore`. A docs scaffold, project context and overview spec belong to the delivery workflow's own bootstrap layer, not the engine's.
- SHL-AC2's rubric scenarios run the skills with a model, on the owner's machine (live).

### F17 EAS Agent SDK executor `supported`

From [executor-agent-sdk.spec.md](../specs/executor-agent-sdk.spec.md).

- Steps load project settings only, so a repository's CLAUDE.md and skills work as on `claude` while the operator's user settings stay out of CI.
- The executor never uses `ClaudeSDKClient`: one `query()` per session matches the fresh-session rule, and a retry is a new session told the last report.
- Because the SDK's own CLI is a child of the worker, the launcher's tree kill ends it with the worker ([EXI-B5](../specs/executor-interface.spec.md)).

Probes, none run:

| Id | Fact to confirm | Used by | Result |
|---|---|---|---|
| P-AS-1 | `setting_sources=[]` keeps user-level plugin tools, hooks and MCP servers out of the session (seen in the init message) | `isolates_user_config` | not run |
| P-AS-2 | The session's `PreToolUse` hook sees and can deny a subagent's tool calls | gatekeeper on steps that declare `subagent` | not run |
| P-AS-3 | The SDK hands the prompt to its CLI off argv on the pinned version | `prompt_off_argv` | not run |
| P-AS-4 | Whether the SDK's session keeps a native transcript with `setting_sources=[]`, and at which path | transcript locator ([EVT](../specs/run-events.spec.md)) | not run |
| P-AS-5 | A step session with `setting_sources=[]` and `plugins=[{"type": "local", "path": <package root>}]` lists the workflow plugin and its skills in the init message, and no user plugin | workflow skills on step sessions ([PKG](../specs/workflow-package.spec.md)) | not run |

### F18 EVT Run events `supported`

From [run-events.spec.md](../specs/run-events.spec.md).

- The live progress file stays the cheap "now" view and the activity journal the "so far" view. Both come from one writer thread, so the stream pump never waits on disk ([ADR `normalized-session-event-stream`](../adr/normalized-session-event-stream.adr.md)).
- The `judgement` record and the `gate` record linked to it by `judgement_seq` together hold what improvement data asks of a gate ([IMD](../specs/improvement-data.spec.md)); the loop's events reach observers through the same record path and hook events.
- The `judgement` record carries statuses and ids, never evidence text; evidence is in the local evidence file and is shown by the detail document from there.
- Release 1 shipped the `events` verb and the observer interface with no observer enabled; lifecycle hooks came in release 2 (R2-T7) and are read off the run log's own records.

### F19 LOS Local observability store `supported`

From [local-observability-store.spec.md](../specs/local-observability-store.spec.md).

- `raw.jsonl` is the engine's own copy; an executor's native transcript, when there is one, is only linked. This matters because judge sessions run with isolation flags that may turn the native store off.
- Command output is the bulkiest data; it gets the shortest life and its own cap.
- Release 1 build (T7.3) deviations: `raw.jsonl` holds the executor's stream lines verbatim, without a receive time on each line, so a stream-json reader can parse it as it is; receive times are in the activity journal's `t`. A check's commands write `checks/<unit>/<attempt>/<n>.out`, standard output and error together, and its result lives in the `check` record and the checkpoint rather than a `result.json`. The 2 GB warning is given by `store usage` rather than `status`, which the monitor calls every few seconds and which must stay cheap.

### F20 CST Central run stats `supported`

From [central-run-stats.spec.md](../specs/central-run-stats.spec.md).

- No tempergraph server: an OTLP sink covers teams that already run a telemetry backend ([ADR `cross-machine-stats-through-opt-in-sinks`](../adr/cross-machine-stats-through-opt-in-sinks.adr.md)). Appends from two machines to one file are what break a synced folder, so each machine writes only in its own folder.
- The heartbeat makes the sink a monitoring surface, not only a ledger.
- Release 1 build (T7.4, T10.1): `repo_id` was null until the sink key landed with the sinks; the outbox holds a reference to the local row so it carries no names; `TEMPERGRAPH_FLUSHER` exists for tests and hosts that forbid detached children; the `session` row went opt-in (default `include` is `run`, `heartbeat`, `supervision`) where the design said "default all four"; per-capability counts in the `session` row are not built; the fleet copy does not copy `supervision` rows yet; the `otlp` kind is not built; two sinks with one name are refused by the `stats` verbs and skipped by a run rather than at preflight.

### F21 TEL Telemetry export `supported`

From [telemetry-export.spec.md](../specs/telemetry-export.spec.md).

- OTLP reaches the most backends with one exporter; the engine needs no vendor client ([ADR `telemetry-export-as-otel-genai-without-content`](../adr/telemetry-export-as-otel-genai-without-content.adr.md)).
- The GenAI conventions are in Development status and renamed attributes three times in a year, so every name lives in a behaviour and the pinned version travels on the resource.
- A CLI session is a span, not a set of `chat` spans: only the Messages API executor sees individual requests.
- Cost has no convention; it is exported in the engine's namespace with reported and estimated apart.
- This spec was migrated by a temperspec run (triage, discovery, outcome gate) as a dogfood trial of the migration; see the migration plan.

### F22 PRP Improvement proposals `supported`

From [improvement-proposals.spec.md](../specs/improvement-proposals.spec.md).

- The proposer is reflective in the sense of research `self-improving-agent-systems` F3: it reads the cluster's evidence and proposes one small delta. A search over many candidates is not in the first release; a later one may keep several drafts per cluster and trial the best two.
- The engine classifies from the parsed workflow, so a proposer cannot hide a weakening in a reformatted file. A check weakened only through its fixture data is not detected.
- Release 1 build (T12.5, T12.6, T12.8): the proposer is a fixed engine program rather than a packaged workflow; trial cases run one at a time because `batch` does not exist; `proposal_state` and `trial_progress` are not emitted as events, the records are the source.

### F23 FBK Feedback labels `supported`

From [feedback-and-judge-reliability.spec.md](../specs/feedback-and-judge-reliability.spec.md).

- Confidence is studied against labels rather than used as a filing floor; the open question on SIL's 0.75 floor is answered from `confidence_bands` once labels exist.
- Release 1 build (T7.5, T12.3): only `explicit` labels at first, then `approval`, `override`, `pushback`, `audit` and `rerun` derived at every exit; `pr_state` not derived; the label's own kind is the field `label_kind` because `kind` names the ledger row's kind; `label_recorded` and `binding_shift` are not separate events. All thresholds are parameter rows (`labels.*`, `reliability.*`, `shift.*`).

### F24 SRV Session review `supported`

From [session-review.spec.md](../specs/session-review.spec.md).

- Fixed categories with citations, because model attribution to a step is unreliable (research `reading-session-logs-for-self-improvement` P3) and a fixed catalog agrees across readers (P4).
- `conformance[]` is the dev-mode answer to "do the prompts and agents work as intended": it lists every instruction section, lesson, skill and subagent type and whether the session followed it.
- Graduation ([ADR `graduate-a-workflow-from-local-to-pipeline-by-measured-criteria`](../adr/graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md)) may read `improve review summary`: a version whose last dev-mode runs leave no corroborated observation open is a candidate for stable mode. The rule is not set.
- Release split: release 1 built the digest and its causes, `full` reviews in dev mode, probation and authoring trials, the citation check, the local report and the verbs. Stable-mode `signals` plans, saturation, corroborated filing and the proposer's use of observations (X2-26) moved to release 3, since no workflow reaches stable mode before its gates are calibrated ([LIF-B6](../specs/lifecycle-and-evals.spec.md)). Release 3 builds the `signals` plans, saturation and the stable caps (R3-T8.2); corroborated filing and the proposer's use of observations stay in spec `session-review`'s Not built yet line.

### F25 ORC Orchestration `supported`

From [orchestration.spec.md](../specs/orchestration.spec.md).

- No LangGraph graph for the supervisor: its state is a set of independent child processes with their own checkpoints and many pauses at once; one interrupt per gate and one graph per process fit runs, not a supervisor of runs.
- Shared resources: `exclusive` names stop concurrent runs from colliding on counters and version fields (research `dynamic-workflows-as-orchestration-model` B3). Engine-managed claims and deterministic integration of branches with a judged conflict step are deferred; an integration step is a workflow node today.
- Several repositories, one machine: a node may run in another local repository; its run uses that repository's state root and the orchestration's folder stays in the home state root. Several machines, CI hosts and a hosted runner are out of scope.
- Scheduled orchestrations: a schedule may target a saved `*.orch.json`; the tick runs `orchestrate start` and exits, and the supervisor runs it as usual (contracts C16 and C18, ADR `a-model-free-tick-behind-os-agnostic-triggers`).
- Assumptions (owner unavailable): K defaults to 3 as for batches; 50 runs per orchestration matches the batch limit; the settle window defaults to 30 s; an orchestration runs on one machine; templates are saved by the skill under `tempergraph/orchestrations/` in the repository.
- The needs N1 to N8 on the rest of the engine were requests on the observability design, which took them: `--parent` and `origin` (DUR, EVT, CST), the run-log stream with `seq` and `cost_so_far` (EVT), `stop` (RCT), `facts` with pending gates (CLI), process groups, the orchestration hook events (HOK), `stats --projection` (CST) and the monitor's drill-down.

### F26 OSK Orchestrator skill `supported`

From [orchestrator-skill.spec.md](../specs/orchestrator-skill.spec.md).

- Why a separate skill: the run driver's core is near its size budget; orchestration adds drafting, approval and multi-pause walk-throughs.
- Borrowed from dynamic workflows: planning in data with a runtime that drives it, approval with the plan visible, labels and phases, a size warning, saved templates with arguments (research `dynamic-workflows-as-orchestration-model` conclusions 1 to 5). The skill does not write a Claude Code workflow script: a workflow agent per run would put a model session in front of every start and wait, and a script cannot take a person's decision mid-run.
- Between wakes the person watches the monitor, which renders the orchestration status document like the `/workflows` view.

### F27 JCL Judge calibration `supported`

From [judge-calibration.spec.md](../specs/judge-calibration.spec.md).

- Offline and online measure different errors: production labels see mostly what reached a person, so they observe false passes only after harm and false fails only when a person overrides. A gold set with planted defects measures the catch rate directly (research `eval-and-judge-gap-analysis` E3).
- Per-criterion findings are not independent: two findings of one case share a fixture. The distinct-case minimums temper this; a case-clustered bound is a later refinement.
- Self-preference is reported, not barred: the authoring rule (a judge of another family where stakes are high) and cross-executor judging remain the control.
- Variants are templated, not model-written, so a score repeats exactly; a model-written persuasive variant is a later option.
- The bar is asymmetric on purpose: a missed defect ships, a false fail costs a retry and is visible.
- Panels stay deferred: a gate that cannot meet the bar on one judge may try a stronger model or another family first. A council or contest feeds the gate's one judge, which is calibrated as usual.

### F28 EVS Eval suites `supported`

From [eval-suites.spec.md](../specs/eval-suites.spec.md).

- Code first: a check that decides costs nothing and cannot be argued with; a judge decides only where it has been shown to grade well; a person decides the rest (research `evaluating-llm-judges-public-practice` F10).
- pass^k for gates: a gate that passes once in three is not a working gate; `pass_hat_k` exposes it where `pass_at_1` averages it away.
- One case, two uses: workflow cases are PRP case-set entries, written once for a release check and a version trial.
- Corrected, never replaced: the corrected rate is an estimate whose error bars depend on a small gold set, so it is a reading aid; an interval that carries the gold set's own uncertainty is a later refinement.
- Built in release 2 (R2-T4), suites and harvest and replay.

### F29 AUD Workflow audit `supported`

From [workflow-audit.spec.md](../specs/workflow-audit.spec.md).

- Advisory, separate from `validate`. Validation is a gate: the same function guards every start and must stay fast, deterministic and free of the host and of history. The audit reads more, may be wrong in a ranked way, and must never block a start (ADR `advisory-read-only-audit-verb-in-three-layers`).
- A fixed catalog keyed to causes: each rule carries a cause code shared with the self-improvement loop, so a static finding and a history finding about the same defect group together, and a proposal (PRP) can cite both (ADR `audit-rules-are-a-fixed-catalog-keyed-to-causes`).
- Quiet by default because of research `why-runs-fail-stall-repeat-or-overspend` N1: a signal raised on every run ranks nothing. The default view, the per-rule confidence and the minimum samples exist for that.
- The three layers map to research `why-runs-fail-stall-repeat-or-overspend` families: `definition` finds shapes known to loop (C1), timeout and hold-time exposure (C3), tool-grant defects (C4), pauses that cannot help (C5), cost shape (C6) and prompt defects (C7); `host` finds environment causes (C2), tool exposure (C4) and engine and executor versions (C8); `history` finds what actually drove repeats, timeouts, refusals, pauses and cost (C1 to C6). Here C1 to C8 are research `why-runs-fail-stall-repeat-or-overspend`'s cause families, not the overview's contracts.
- History sources: the run log (OBS) and the ledger (SIL); the activity journal (EVT) adds input summaries for refusal classes; a `--source` for the shared run store (CST) may be added later.
- Exit 6 is new: an advisory verb must not reuse a code that means a run ended, so CI can tell "the audit found something" from "the audit could not run" (2).
- Release 1 build (T8.5, ADR `first-release-is-simple-trusted-workflows-on-one-machine` item I-62): the `definition` and `host` layers, the prompt audit and `audit prompts`, ignores, the three formats and `--fail-on`; `tests/test_audit.py` holds AC2 and AC4 to AC7 and AC1 for those layers' rules. The history layer and `audit tools` were planned for release 2 (X2-9, X2-10) and moved to release 3 (I3-12, R3-T8.3). `AuditFinding.owner` was added in that build. Probes run through the registry, and tests inject both the probe and the login-shell timing.
- Known code drift kept for the engine owner: the per-rule skip reason for a layer not built reads "not in release 1", and `unbounded-wait` still reads "wait and ask are release 2", though both kinds were built in release 2.

### F30 ARC Audit rule catalog `supported`

From [audit-rule-catalog.spec.md](../specs/audit-rule-catalog.spec.md).

- Several research `why-runs-fail-stall-repeat-or-overspend` findings stay engine work and get no rule: concurrent writer limits, orphaned sessions, how a retry resumes. A workflow cannot change them.
- Release 1 ran the `definition` and `host` rules; history rules were listed as skipped. The kinds of ARC-B15 were not built in release 1 (validation refused them); `unbounded-wait` waits on `wait` and `ask`.
- The `slow-host` floor exists because a login shell is always several times a plain one in milliseconds.
- `judge-not-ready` renders as `readiness:needs-cases` on every gate before calibration, because no judge is `accepted` yet; that is the true state.

### F31 UPD Engine install and update `supported`

From [engine-update.spec.md](../specs/engine-update.spec.md).

- Side-by-side environments follow from the two failure classes of an in-place update, a half-installed environment and Windows locks on replaced libraries (research `updating-a-tool-with-long-lived-runs` U9), and give rollback and pinning for the cost of disk.
- The shim lives in `~/.tempergraph/bin/`, not the plugin cache: a shell block that resolves the newest plugin folder by a version sort breaks easily, since plugin folders change with every version and are deleted 14 days later (research `updating-a-tool-with-long-lived-runs` U4).
- The verb updates no workflow and no repository's store: a machine may hold many repositories, some not checked out at update time; each store moves when the new engine first writes to it.
- A later Python-package channel (pip, uv tool) would replace the source and install steps only (research `engine-update-and-workflow-upgrade-gaps` open question).
- Release 1 shipped `install` only; `update` came in release 2 (R2-T6.1). The environment builder is a parameter, so tests create no environment. No earlier release wrote a legacy manifest, so nothing is merged.

### F32 VER Version metadata `supported`

From [version-metadata.spec.md](../specs/version-metadata.spec.md).

- Version facts are kept apart because each answers a different question; the install stamp and the workflow stamp are easily conflated.
- The changelog is typed because an upgrade needs to know, per hit, whether a rule, a model or a person handles it (ADR `typed-version-metadata-on-both-sides`, research `automated-and-model-assisted-migrations` conclusion 2).
- `workflow_api` exists apart from the engine major so a release that breaks only the CLI or a document does not ask every workflow owner to upgrade.
- `workflow_version` closes gap G5 of research `design-gap-review`: a declared version for people and a digest for measurement.
- `version-not-bumped` exists because the plugin cache is keyed by the version string (research `updating-a-tool-with-long-lived-runs` U3).
- As built (R2-T6.3): `package/transforms.py` holds the transforms as pure text edits found by Python's own parser. The release 2 changelog entry that carries the model-list transform ships with the version bump (release 2 plan R2-T9).

### F33 MIG State and run migration `supported`

From [state-and-run-migration.spec.md](../specs/state-and-run-migration.spec.md).

- LangGraph applies the latest graph to every thread (research `updating-a-tool-with-long-lived-runs` U12), which is the default here; pinning, taken from Temporal's model (U15), is kept for the one case LangGraph cannot handle, a checkpoint the new code cannot read (ADR `threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them`).
- The engine names compiled nodes after unit names (CMP); renaming that scheme is a checkpoint-format change by definition, so it pins rather than breaks.
- A workflow change is never blocked for what a checkpoint does not hold: a person who improves a prompt while a run waits for their decision gets the improved prompt on resume, recorded.
- Migrations run on first write, not in `update`, because `update` cannot reach repositories that are not checked out, and a store must never be half-moved under a live run of an older engine.
- As built (R2-T6.2): `durability/engine_file.py` holds the engine file, the resume decision as a pure function and the four workflow-change tests; `store/migrate.py` holds the layout steps. The engine file travels with a carried thread (CAR). Live check L-27 found a thread from before the engine file recorded as started on the resuming engine; MIG-B16 states the fix.

### F34 WUP Workflow upgrade `supported`

From [workflow-upgrade.spec.md](../specs/workflow-upgrade.spec.md).

- Real breaks need the owner's answers (research `automated-and-model-assisted-migrations` M10), so this design keeps those answers the owner's (owner items, protected paths, V5) and uses a model only where public practice shows it does most of the edits under deterministic validation (M3 to M5) (ADR `upgrade-by-transforms-first-and-a-gated-model-workflow-for-the-rest`).
- The model work is a tempergraph workflow, not a loose session, so it inherits the engine's own rails: an independent judge, a deterministic check first, budgets, pauses and records (UWF).
- "Done" is relative to the baseline, because a workflow that already had findings must not be blocked by them and must not gain new ones (ADR `an-upgrade-is-done-when-model-free-checks-pass`).
- The shares by transform, model and person in every report are the measurement research `automated-and-model-assisted-migrations`'s open question asks for.
- Release history: release 1 built `upgrade --check` and `upgrade-check [--stamp]` only; phases 4 to 7 came in release 2 (ADR `release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing`, moved from release 3 by the owner on 2026-11-20). As built (R2-T6.3): `package/upgrade.py` holds phases 1 to 7 and `cli/upgrade.py` the verb.

### F35 UWF Built-in upgrade workflow `supported`

From [upgrade-workflow.spec.md](../specs/upgrade-workflow.spec.md).

- Running the model's part as a workflow is the engine's own thesis applied to itself: a model edit is a step, an independent judge grades it, a rule decides (ADR `independent-judge-engine-verdict`). It also makes the upgrade visible to `status`, the monitor and the cost reports with no new mechanism.
- The judge's criteria follow the failure modes measured in public practice: unrelated reformatting and invented edits (research `automated-and-model-assisted-migrations` M8), and an invented rubric, the case against a model rewrite (M10).
- Like every workflow, this one is evaluated: its check and step suites hold fixture packages with planted upgrade items, and its judge is calibrated before the workflow is `stable` (JCL).
- As built (R2-T6.4): `builtin/upgrade.py` builds the workflow; the `builtin` field's value is `true` (self-improvement) or a name (`upgrade`).

### F36 LSK Lifecycle skills `supported`

From [lifecycle-skills.spec.md](../specs/lifecycle-skills.spec.md).

- One plan and one yes answers the owner's "simply say update tempergraph". Asking once per command would turn a routine update into a dozen prompts. Asking again for money and for pauses keeps the two consents the design never folds away (ADR `lifecycle-skills-drive-plugin-commands-then-engine-verbs`).
- Reinstalling workflows is the engine's job, not the skill's (ADR `registered-workflows-are-reinstalled-and-pinned-never-lost`): an update from CI or a terminal must keep workflows working too, with no conversation.
- The skills never pull or commit in a person's repository. An upgrade works on its own branch, and a stale checkout is pointed out, not fixed.
- The update order (marketplace, plugin, then the engine verb from the new copy) comes from where the update code lives: only the updated plugin carries the new staged engine.
- Release history: release 1 shipped `tempergraph:install` (I-72); release 2 shipped the update skill with `update` (X2-8) and the upgrade skill with `upgrade` beyond `--check` (ADR `release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing`). As built (R2-T6.4): the `update` and `upgrade` skills ship in `skills/`, held by the structure tests.

### F37 SCR Script units and hybrid steps `supported`

From [script-units-and-hybrid-steps.spec.md](../specs/script-units-and-hybrid-steps.spec.md).

- Scripts run under the engine, so executor capability flags do not apply to them; the command rules of SEC do.
- A judge on a script unit is for human-readable output (a generated report); a script whose output a check can grade needs none.
- Caching is limited to model-free work so that a judge always runs fresh on each subject and a step never replays a failed answer (ADR `cache-only-model-free-script-results-per-thread`).
- A `before` script may not publish because nothing has judged the content yet (ADR `take-script-steps-attention-and-composition-from-archon` risk).

### F38 CNL Council unit `supported`

From [council-unit.spec.md](../specs/council-unit.spec.md).

- Round 0 blind and rounds opt-in follow research `councils-debate-and-voting` K2 and K4: most of the benefit of debate comes from independent answers combined, and rounds invite conformity.
- Members are asked for dissent explicitly because withheld dissent removes the gain of discussion (research `councils-debate-and-voting` K5).
- The engine records per round how many members changed position, so the audit can show whether rounds pay (ARC `council-rounds-no-gain`).
- Judge panels stay deferred (JCL); a council feeds one calibratable judge.
- Built: the council (third-release plan I3-6, R3-T4.1). The contest is release 3 work (R3-T4.2); validation already knows its kind.

### F39 CTS Contest unit `supported`

From [contest-unit.spec.md](../specs/contest-unit.spec.md).

- Using the gate's own judge per candidate means no new grader needs calibration (JCL); a pairwise judge was rejected for its position and length biases (research `evaluating-llm-judges-public-practice`).
- Costs grow with slots, so preflight shows the projected range from the stats projection (CST).
- As built (R3-T4.2): `run/contest.py` holds the pick, a pure function over each slot's verdict and keys, and the `contest` record's rows; the unit's own step node runs the slots in a pool of `concurrency` threads, each on the item view of the state, and its judge node grades them and picks, so a contest compiles to the unit's four nodes. A writing contest cuts one `--s-<slot>` worktree per slot after a checkpoint commit and merges the winner only; an attempt after the first cuts fresh `--s<n>-<slot>` worktrees from the run branch's head, leaves the earlier attempts' slot branches as they are and merges its own winner only. Preflight shows no projected cost range for a contest until the owner answers the open question of the spec.

### F40 ASK Ask unit `supported`

From [ask-unit.spec.md](../specs/ask-unit.spec.md).

- One interrupt per gate holds: the ask's only pause is its human node, and a partial answer re-enters the same node.
- An ask differs from an approval (a decision on work) and from a wait (a value from an outside system, checked); its answers are data for later steps.
- As built (R2-T7): `run/asking.py` holds the question rules and the answers file; in Python the `from` field is `questions_from`.

### F41 FLX Flow extensions `supported`

From [flow-extensions.spec.md](../specs/flow-extensions.spec.md).

- Every target stays a declared name, so validation checks reachability and the diagram draws every edge (ADR `new-node-kinds-keep-the-gated-unit`).
- Deadlines need no resident process: the engine still exits at a pause, and an owner who wants deadlines to act on time schedules `resume --apply-deadline` from their own scheduler; the schedule tick is the engine's candidate for that job in a later slice (TCK).
- Breakpoints fit the local stage of a workflow's life, when a person still reviews each step before it spends (ADR `graduate-a-workflow-from-local-to-pipeline-by-measured-criteria`).
- As built (R2-T7): deadlines, the fallback target and breakpoints are built; selective parallel and a map over a sub-workflow stay in release 3. A breakpoint is a marker file `breakpoint.json` beside the run log plus LangGraph's `interrupt_before`.

### F42 CHK Check contract and command runs `supported`

From [check-contract-and-command-runs.spec.md](../specs/check-contract-and-command-runs.spec.md).

- One public resolution function, because a plan check and a gate that resolve commands apart can disagree in a repository with another toolchain, and the gate then runs nothing. The engine owns the mechanics; the workflow owns the policy (ADR `checks-get-a-context-and-an-engine-command-runner`). Which commands a workflow's gate runs, how it splits a suite and how it reads the plan are the workflow's design; nothing in CHK names a tool.
- Reuse extends the per-thread cache idea of ADR `cache-only-model-free-script-results-per-thread` to check commands: model-free, keyed by the tree, never a run that did not finish.
- A check worker costs about one interpreter start per gate. It is the only way to bound a check whose own code hangs, and it keeps workflow code off the engine's main thread.
- The preview is an engine command, not a resumed session: a resumed retry carries the whole conversation and costs more than a fresh one (research `claude-code-cli-headless` F20), while a preview lets the session repair a structural miss before it ends at no judge cost (ADR `a-step-previews-its-own-check-in-the-attempt`).
- Live check L-29 (2026-11-22): the plain "no shell" line alone made a real session skip the preview, so the tools section names the one command it may run.
- As built (R2-T7): `run/selfcheck.py` keeps the ticket file for the session's length; only the `claude` grant ships.

### F43 VAL Step values and template keys `supported`

From [step-values-and-template-keys.spec.md](../specs/step-values-and-template-keys.spec.md).

- A value is an artifact, not a new channel of trust: the step's word for a value is a claim like any other, which is why a workflow ties a route value to its evidence with a check. The engine only parses and bounds it. The need came from temperspec's first step, which hands four values to the run and routes on two (research `temperspec-needs-against-the-engine` T13, T14); the capability is stated without the workflow (ADR `the-engine-names-no-workflow`).
- Pointers, not content, keep the rule that the engine pastes no earlier artifact into a prompt (PRM); the step reads what the pointer names with its own tools.
- The grammar stays the plain `{name}` field (plus `settings.<name>`); no other dotted path or expression is added, so templates stay checkable by the same validation and prompt audit (PRA).

### F44 MAP Map unit `supported`

From [map-unit.spec.md](../specs/map-unit.spec.md).

- Per-item gates rather than one gate over all items, because a narrow judge per item is cheap and immediate, and one wide judgement belongs to the join.
- A sequential map is not a bounded self-route nor a branch per item: a route cannot target its own unit, and a branch per item would need a worktree and a merge per item.
- The list is read once per visit so a step cannot change the plan under the map mid-visit; changing it takes a trip back.
- As built (R2-T1.2, sequential mode): items run through the unit's own four nodes, one at a time, with a `maps` state channel. As built (R3-T3.2, concurrent mode): the unit's own step node reads the list and sends up to `concurrency` items at a time to item nodes, each item keeping its attempt, judgement, feedback, counters, route and pause under its slot `<unit>.<item id>`; a writing map's items each run in their own worktree and are merged in list order, and the map's check runs once on the merged result.
- Per-item work costs more on small plans, so a delivery workflow may route between a map arm and a single-session arm (SWM, CXR); that choice is the workflow's, not the engine's.

### F45 FIN Finalizer contract `supported`

From [finalizer-contract.spec.md](../specs/finalizer-contract.spec.md).

- The run's exit code is a contract for callers (ADR `exit-codes-as-caller-contract`): a run that passed every gate has finished, whatever publishing does after. The work exists on a committed branch, and the manual steps say how to finish by hand.
- The finalizer reuses the check's command machinery (ADR `checks-get-a-context-and-an-engine-command-runner`) so there is one guarded launch site for workflow commands.
- What to publish, where, as a draft or not, and how to word it are the workflow's choices; the engine supplies context without private text, a scrubber, a guarded runner and a record. The need came from temperspec's publishing stage (research `temperspec-needs-against-the-engine` T51 to T53), whose outcomes are `opened`, `reused`, `pushed` and `skipped`.

### F46 SWM Measured switches `supported`

From [measured-switches.spec.md](../specs/measured-switches.spec.md).

- A router is a cost bet. Shadow mode makes it measurable on real runs before it moves money (research `temperspec-needs-against-the-engine` T46).
- Overrides belong to the arm because the reason for them (a longer limit for a whole-plan session) belongs to the arm, not to the unit; they are workflow data below every operator layer.
- Re-arming is a trip back, not a new edge kind, so budgets, clearing and records stay the ones every other trip back uses.
- As built (R2-T1.1): a listed timeout re-arms at once; a switch re-arms at most once per run.

### F47 RST Run settings and overrides `supported`

From [run-settings-and-overrides.spec.md](../specs/run-settings-and-overrides.spec.md).

- One catalog, fixed layers. A free-form map of overrides would let anything be changed and nothing be validated; per-key ad hoc orders, which the design had for models and timeouts only, leave every new key to choose its own (ADR `one-catalog-of-run-settings-over-fixed-layers`). The order puts the operator above the workflow above defaults, and adds per-machine files that hold an operator's engine defaults.
- Files above and below the workflow. `overrides` serve an operator who must change a workflow's value on this machine (a slow host's longer limit, a team's model choice); `defaults` serve every workflow that states nothing. Both are per machine: a committed repository file is not a layer in the first release, so a pull request cannot raise anyone's cost cap.
- Snapshot, not live files. A paused thread resumes days later with the settings it started with unless the operator says otherwise, so a run's record explains its behaviour (ADR `threads-snapshot-settings-and-reapply-them-on-resume`).
- Provenance is data for the loop. Settings digests let reports compare like with like and stop the loop blaming a workflow for an operator's cheaper model (IMD).
- The shared types `SettingKey`, `SettingDecl`, `RunOptions`, `ResolvedSettings` and `UnitRef` moved here from the old contracts section 2.12; `Feedback` and `Ruling` moved to RRN.

### F48 RRN Reruns, rewinds and feedback `supported`

From [reruns-and-feedback.spec.md](../specs/reruns-and-feedback.spec.md).

- Same thread for a correction, a new thread for a do-over. A rewind keeps one run's story in one thread while it is still live. A finished thread's finalizer has run, its stats row and its improvement record exist, and a pull request may be open; reopening it would rewrite what was reported. A rerun leaves it as it was and links to it, as Temporal's reset starts a new run and keeps the old history, and as Argo's resubmit makes a new workflow (research `config-overrides-and-reruns-gaps` F20; ADR `rewind-on-the-thread-rerun-as-a-linked-fork`).
- LangGraph does the forking. The checkpointer keeps each thread's history; reading the checkpoint before a unit and writing its values to a new thread id is the public time-travel mechanism, so no engine-owned history is needed (ADR `langgraph-graph-runtime`).
- Rulings close a gap. A workflow that has a step copy a person's ruling into the next artifact for the judge depends on that step, and nothing verifies that a person's earlier feedback reaches every later judge (research `config-overrides-and-reruns-gaps` F18). A ruling is state the engine renders, so it does not depend on a step copying it.
- Fresh sessions stay the rule; continuing an agent's own conversation is an open question.
- `Feedback` and `Ruling` moved here from the old contracts section 2.12.

### F49 WTR Worktree mode `supported`

From [worktree-mode.spec.md](../specs/worktree-mode.spec.md).

- Why the engine and not the executor: gates, checks, judges and the finalizer run in the engine and need one tree for the whole run, at a base the engine picks; Claude Code's `--worktree` is per session, starts from the default branch, is never removed under `-p` and is left locked; Antigravity's is an App feature; the Messages API has none (ADR `the-engine-owns-the-run-worktree-executor-worktrees-are-not-used`).
- `auto` keeps worktrees optional for non-coding workflows while making the safe choice the default for workflows that change files (ADR `one-workspace-setting-with-an-auto-default`). A workflow author who wants a fixed mode declares `workspace: worktree` or `in_place`.
- `sibling` is the default so repo-wide tools do not index a duplicate tree; `in_repo` exists for hosts that only allow writes inside the project folder, and uses Claude Code's own folder so that tool treats it as a known worktree location (ADR `worktrees-beside-the-repository-with-derived-ref-safe-names`).
- `head` as the default base keeps a run offline-safe and starts it from what the person sees; `default_branch` matches Claude Code's `fresh` (ADR `a-new-worktree-starts-from-the-main-checkouts-head`).
- The engine's lock with a reason keeps `git worktree prune` and other tools' sweeps from dropping the admin data of a paused run's worktree.
- Release split: the first release built `auto`/`worktree`/`in_place`, the `sibling` root, `head` and `ref:` bases, names, start, resume and re-attach, executor pointing and the two disallowed tools, `worktree list` and `path`; the rest moved to release 3 (second-release plan I2-20, X2-23). As built (R2-T6.4): an in-place run started from inside a linked worktree works in that worktree; the built-in upgrade workflow depends on it (UWF).

### F50 SCH Schedules `supported`

From [schedules.spec.md](../specs/schedules.spec.md).

- One mechanism. A person at a terminal, the schedule skill and a pipeline export produce the same entry; only the tick fires it (ADR `a-model-free-tick-behind-os-agnostic-triggers`).
- A grammar, not a guesser: a wrong reading on a recurrence repeats every period (ADR `exact-formats-first-and-an-optional-word-grammar-echoed-back`). Zones and daylight saving: ADR `schedules-keep-an-iana-zone-and-rfc-5545-daylight-saving-rules`. Missed and overlapping slots: ADR `missed-slots-catch-up-latest-and-a-live-run-skips-the-next`. Unattended spend and pauses: ADR `a-scheduled-fire-is-an-attested-caller-with-capped-spend`.
- Declared programs are reserved as target kind `program` until a package can declare programs, a WFM change; due rule, catch-up and fire log would apply unchanged.
- Release slice. Scheduling rests on unattended credentials, cost caps, `attention` and caller provenance, so it was recommended for the release after the first: `once` and calendar `recur` for workflow targets, `catch_up: latest|none`, `overlap: skip`, both caps, every verb but `export`, and the portable loop with the `host` adapter. Later: the `os` adapter, orchestration and program targets, `catch_up: all`, `overlap: queue|parallel`, `cron` input, pipeline export. Release 2 moved it to release 3 (second-release plan I2-19).
- Assumptions (owner unavailable): per-user, per-machine schedules; 15-minute minimum interval; 09:00 offered as the default time; English only; 64 schedules per machine; 3 failures before a pause; a catch-up window of one period capped at 24 hours.
- Release 3 slice (R3-T5). ADR `release-three-composes-runs-in-parallel-and-grades-in-the-pipeline` puts SCH and TCK in release 3 together, so the "Later" list of the release slice above (`cron` input, `catch_up: all`, `overlap: queue|parallel`) is built in release 3 as well. The first phase, R3-T5.1, builds the exact formats (`--at`, `--rrule`, `--every`, `--cron`), the word grammar, the canonical form and echo, slots with daylight saving, the entry and its fire log, the verbs `parse`, `add` for a workflow target, `list`, `show`, `history`, `edit`, `pause`, `resume`, `skip` and `remove`, and the catch-up, overlap, failure, budget and fire-identity rules as functions that read an entry, its fire log, the live runs and a clock and write nothing. The second, R3-T5.2 (TCK), builds `fire`, `tick`, `loop`, `trigger`, `runs`, `export`, the credential check, the fire token and the ledger. Orchestration targets wait for release 4 (ADR `release-three-composes-runs-in-parallel-and-grades-in-the-pipeline`).
- Cron (R3-T5.1). POSIX `crontab` runs a command on a day that either the day-of-month field or the day-of-week field names when both are restricted, GNU Micron joins them with AND by default and lets a setting choose the either-field reading, and an RFC 5545 rule can only intersect them; implementations differ, so `--cron` refuses a rule that restricts both (`rule_unsupported`) rather than pick a reading that would repeat wrongly every period (ADR `exact-formats-first-and-an-optional-word-grammar-echoed-back`). A restricted month has no stored form, since SCH-B18 has no `BYMONTH`. Steps, ranges, lists and names expand to lists of values and never to `INTERVAL`, because a cron step is aligned to the clock (`*/15` is minutes 0, 15, 30 and 45) while `INTERVAL` counts from `starts`. A macro such as `@daily` is not five fields and is `when_malformed`. The two day-field readings come from the sources above, each read through a search excerpt.
- Daylight saving (R3-T5.1). RFC 5545 section 3.3.10 says recurrence instances with a nonexistent local time are ignored, section 3.3.5 says such a local time takes the offset before the gap, and erratum 4271 (verified) calls the two a contradiction. SCH-B20 and ADR `schedules-keep-an-iana-zone-and-rfc-5545-daylight-saving-rules` take section 3.3.5 for every slot, so a daily 02:30 still fires on the spring-forward day, at 03:30. An interval rule is `FREQ=MINUTELY` or `FREQ=HOURLY` with `INTERVAL` and no other `BY` part, and steps elapsed UTC time from `starts`; every other rule is a calendar rule and steps local clock times (so `every 2 hours between 9am and 5pm`, whose `BYHOUR` is on the local clock, is one). For SCH-AC2 the reference is `dateutil.rrule` with a zone-aware start for a calendar rule and with a UTC start for an interval rule (dateutil steps date and time fields without the zone's offsets; the SCH-AC2 test settled it: 5,000 random rules in 20 zones agree over two years, `COUNT` counting local times as dateutil counts them, and two local times that land on one instant after a gap shift being one slot).
- Assumptions, parsing and slots (R3-T5.1, owner unavailable). Times are whole minutes: seconds in a given time are dropped and the echo names that as assumed; now is the current whole minute, so a slot in the current minute is due and not past; `starts` defaults to now and an interval rule's first slot is `starts`. An `--at` with an offset or `Z` is stored as the local date-time in the schedule's zone at that instant. The machine's zone is read from `TZ`, else the `/etc/localtime` link, else `/etc/timezone`, else `UTC`, and the echo says which. `--every` takes weeks, days, hours and minutes (`PT2H`, `PT90M`, `P1D`, `P1DT12H`), a day being 24 elapsed hours, and stores the total as `FREQ=HOURLY;INTERVAL=n` when it is whole hours and `FREQ=MINUTELY;INTERVAL=n` otherwise, `INTERVAL=1` not written, so `--every PT2H` and `every 2 hours` store one rule; years, months and seconds are `when_malformed`. An `--rrule` value may start with `RRULE:`; `COUNT` or `UNTIL` in it together with `--count` or `--until`, or `COUNT` with `UNTIL`, is `when_malformed`; `UNTIL` is stored as a UTC instant. `when_in_past` means no slot at or after now and `when_too_far` a first slot more than 400 days ahead. Two slots that land on one instant after a gap shift are one slot. Echo sentences are fixed templates over the canonical form, patterned on the SCH-B18 example; the SCH-AC1 fixtures own the exact wording.
- Assumptions, entry and verbs (R3-T5.1, owner unavailable). `token_digest` is written null and `executors_checked` empty until R3-T5.2; `add`, `edit` and `resume` classify their caller (SCH-B27) but refuse one that is not a person only when TCK-B22 is built, and nothing fires before the tick exists. The 64-schedule limit counts schedules that are not `removed`. A `schedule_id` takes four random hex digits, drawn again until unused; a verb takes an id or a name, and a name that matches several schedules or none exits 2 and lists the ids. `description` is the request cut to 200 characters after scrubbing, and a `--reason` text is scrubbed and cut the same way. `list` shows `active` and `paused` schedules and `--all` adds `done` and `removed`; with no tick no fire starts, so a fire log holds no `started` event and live runs, failures and period spend read 0 (period spend `-` without a `budget`) and last fire reads none, computed from the fire log and the runs' status as SCH-B13 and SCH-B24 define, so a fire log the tick writes later reads the same way. `skip` alone is `--next`, and `--until <date>` skips every slot before 00:00 local on that date. `resume` records the slots passed during the pause as `missed` itself, unless `--catch-up`. `edit` and `remove` ask for a yes in a terminal and exit 3 with no terminal and no `--yes`, as SCH-B1 does for `add`. `schedule parse --count n` bounds the recurrence as `add --count` does (an open question in SCH).
- Assumptions, fire-decision functions (R3-T5.1, owner unavailable). They take an entry, its fire log, the live runs (each a fire with its thread's state, `running` or `paused`), a clock and the interval the trigger declares (60 s for the loop), and return what to record and raise; they read and write nothing. A slot is on time when found no later than one tick interval after its instant, and then fires under every `catch_up`; a later find is a catch-up, subject to the policy and the window (inferred: this reads SCH-B21's "no tick between a slot and its window" so that `none` still fires a slot the loop found on time). The default window is the period of `FREQ` times `INTERVAL` capped at 24 hours, so a `DAILY`, `WEEKLY` or `MONTHLY` rule and a `once` get 24 hours; it is stored in `catch_up_window_s`, `--catch-up` takes `latest`, `none` or `all`, and no option sets the window in this release. Under `queue` a pending slot that a later one replaces is recorded `skipped` with `overlap`, and a pending slot has no window. The `blocking_schedule` count is the `overlap` skips recorded since the oldest paused live run started, raised when it reaches 3 and on each further skip. A slot decided while the schedule is not `active` is `skipped` with `paused`. Only `ended` events (exit 0 resets, exits 4 and 5 fail) and `refused` events (fail) change the failure count, and `resumed` resets it; other exits, `skipped` and `missed` change nothing. A budget period is the calendar day, the ISO week (from Monday) or the calendar month in the schedule's zone; a fire belongs to the period of its `started` event and counts its `ended` estimated cost, or the run cap (the entry's `run_cost_cap_usd` now) when its cost is `incomplete` or it has not ended; the sum is read from the fire log, which SCH-AC7 keeps equal to the stats rows. In a thread id and an orchestration id the slot is UTC, written `yyyymmddThhmm`, the fire id's slot without its `Z`; `{fire.slot}` and `{fire.previous_slot}` are local ISO date-times to the minute in the schedule's zone, `{fire.date}` the local ISO date and `{fire.schedule}` the `schedule_id`. A slot with a `started`, `skipped`, `missed` or `refused` event is handled, and no function decides it again.
- Assumptions, word grammar and verbs (R3-T5.1, found while coding, owner unavailable). Stored rule: `BYMONTHDAY` lists sort numerically (so `-1` comes first) and `BYDAY` lists by weekday, then ordinal; a rule that mixes weekdays with and without an ordinal, or gives `FREQ=MINUTELY` a `BY` part, is `rule_unsupported`; an `--until` given as a date alone ends at 23:59 local that day; `UNTIL` is stored in UTC. `HOURLY` with no `BY` part is an interval rule, so `hourly` and `every hour` store `FREQ=HOURLY`; `every N hours between A and B` is `HOURLY` with `INTERVAL` and `BYHOUR`, whole hours only, with N dividing 24 (else `rule_unsupported`, since the hours would drift from day to day), and its `starts` is the first hour on the day it starts (today, or the `from` date). Words: a bare hour 13 to 23 or 0 is a 24-hour time and is not asked; `this <weekday>` is the day of this ISO week and a bare weekday the next such day (today when its time is still ahead, else a week later); `in N minutes` and `in N hours` add elapsed time, `in N days` and `in N weeks` add days on the local clock; a day or a date with no time is a `needs` offering 09:00; a numeric date other than ISO is `date_ambiguous` naming each valid reading as an ISO date; a time that has passed today offers tomorrow or a refusal, and the refusal answers `when_in_past`; `every weekend` is `SA,SU`; each reading of a `needs` is a phrase that parses without a question (`…, skipping short months` and `on the last day` for a late day of the month), so `--choose` re-parses it; `--choose` on a phrase with one reading is `choose_invalid`; a time-zone abbreviation is one of a fixed list (`EST`, `CET`, `PST`, …), read as the last word or after ` in `. Verbs: more reasons, each an exit 2: `workflow_unregistered`, `schedule_unknown`, `schedule_ambiguous`, `schedule_state` (pausing or editing a schedule that is done or removed, resuming one that is not paused, removing a removed one; pausing a paused schedule or resuming an active one changes nothing and exits 0), `no_slot`, `nothing_to_edit`, `budget_invalid`, `option_invalid`, `input_invalid`, `repo_unusable`, `choose_invalid` and `not_in_release`. The check's `needs` (a missing request) exits 3 as SCH-B25 says, though `run --check` itself exits 2 for it. `add --check` parses, checks and echoes and saves nothing. `repo` is the main checkout, or outside git the parent of the state root. `list` counts a live run as a `started` event with no `ended` event for its fire, because a thread's state is read only where a tick exists. A slot in the minute a schedule is created is due then, so `next_slot` can be that slot. A paused, done or removed schedule decides nothing in a tick. The fire keys go through the template grammar as the fields `fire_slot`, `fire_date`, `fire_previous_slot` and `fire_schedule`, because the grammar has no dotted engine key; any other `{fire.x}` is an invalid field.
- Assumptions, ticks and unattended fires (R3-T5.2, found while coding, owner unavailable). The fire token is kept in `schedules/<id>/token` (0600) beside the entry, and its SHA-256 is `token_digest`. The hand-off ticket is `schedules/<id>/tickets/<fire id>.json` (0600), read once and removed by the run: it carries the rendered request, inputs, options, profiles and label, so the child's argv is only `run <workflow> --schedule <fire id> --task-id <id>`, started in the target repository with the token in its environment (which `run` removes at once, so no step session inherits it). The credentials profile is `config/credentials/default`; the kinds are read as presence from its names and the environment (`apiKeyHelper` counts as `api_key`), and `interactive_login` from a cached sign-in file of the product (`~/.claude/.credentials.json`, `~/.gemini/oauth_creds.json`), so a macOS Keychain sign-in reads as no credential until P-SCH-2 is run. The fire-time check re-resolves the executors recorded in `executors_checked` at `add` and `edit`, not a catalog, and `antigravity` declares only `api_key` until P-SCH-3 (the plan's row text for `interactive_login` is read against TCK-B19). A missing credential refuses at a fire only; at `add` it is saved (`result: none`). A `started` fire whose thread never appears 10 minutes after the start is settled `lost` (exit 5, a failure). The tick reads a thread's state through the target repository's state root `<repo>/.tempergraph`, with no git process. A person gives `add`, `edit`, `resume` and `fire` a yes first and is then checked, so a script with no terminal and no `--yes` still gets exit 3; an unknown caller is refused `caller_unknown` for `pause`, `skip` and `remove`. The ledger is append-only (a `fire` row, then an `ended` row that `schedule runs` lays over it) and `store prune --schedules` rewrites it. The `schedule_paused` hook fires through the target repository's state root with facts under `runs/<workflow>/schedule-<id>/hooks/`. The loop ends on a stop marker `schedules/loop.stop`, sleeps in 5 s slices, and calls a gap of 10 s between wall and monotonic time a clock jump; the host adapter is the hook entry `schedule loop --if-autostart`, and `schedule.loop_autostart` is read from the user settings file only. The `os` adapter writes files and starts no process: a LaunchAgent and a systemd user unit (with its `default.target.wants` link) take effect at the next login, a Task Scheduler definition and a crontab line are written under `~/.tempergraph/triggers/` for the person to import. The Windows shim is `bin/tempergraph.cmd`, which no release writes yet, so that entry reads `broken`. Export names `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` secrets only, labels the run `schedule-<id>`, reads the request from `.tempergraph/schedules/<id>.request.md`, and states the `origin: ci` tie in a comment: the run does not yet record it. The skill's eval cases are `skills/schedule/references/eval-cases.md`, one block per case with its words, verbs and outcome. A schedule's `report --by schedule` is read from the fire logs, whose `ended` rows carry each run's cost.

### F51 TCK Schedule ticks and unattended fires `supported`

From [schedule-ticks-and-unattended-fires.spec.md](../specs/schedule-ticks-and-unattended-fires.spec.md).

- OS-agnostic core, optional adapters. Every rule is in the tick and reads files only; the portable loop calls it the same way on every OS. OS schedulers differ in catch-up, sleep and logout behaviour (research `scheduling-runs-prior-art-and-gaps` F12 to F16), so they are used, when the owner wants, only to start the loop at login; they never decide a slot (ADR `a-model-free-tick-behind-os-agnostic-triggers`).
- A loop with no state is not a daemon to look after. Killing it, an update or a crash loses nothing: the next tick reads the same files. One trigger for all schedules, never one per schedule, so nothing drifts from the store.
- Sleep and power-off are the trigger's limit, not the tick's; whether an `os` entry runs while the user is logged out is per platform (P-SCH-1, P-SCH-4).
- Supervisor and tick stay apart. The supervisor lives as long as its orchestration; the tick lives for seconds. Merging them would make every orchestration a resident process or every tick a supervisor.
- Credentials are a capability. A fire that would stall on a sign-in nobody can answer is refused before spend, like any undeclared capability (C15). The Claude Code CLI's `/login` is allowed with a warning because it often works on a desktop that stays signed in; the token made for scripts is the recommended path. A judge launched with `--bare` does not read `CLAUDE_CODE_OAUTH_TOKEN` (research `scheduling-runs-prior-art-and-gaps` F18).
- Deadlines. The tick is the scheduler that FLX assumed the owner would bring: a later slice may let it apply overdue deadlines with `resume --apply-deadline`, recorded with caller `scheduler`. Not in the first slice.
- Assumptions (owner unavailable): a 60 s loop ceiling is enough to settle ended fires promptly; a 5-minute cron interval for the crontab fallback; four starts and 20 s per tick bound a burst after a long sleep; the 10-minute window for a relayed person turn matches the time a person takes to read an echo and say yes.

### F52 PRV Caller provenance `supported`

From [caller-provenance.spec.md](../specs/caller-provenance.spec.md).

- Strongest signal first (ADR `classify-callers-by-the-strongest-signal`). Claude Code sets its child markers without the model's help, so an agent that forgets `--as-agent` is still seen. Self-declaration stays useful for hosts that mark nothing and for honest applications, and it can only move the record toward "not a person".
- Relay needs the host (ADR `a-relayed-decision-counts-as-a-persons-only-with-host-turn-evidence`). The only event that proves a person typed something is the host's own prompt-submit event; the engine never sees the conversation and never stores its text.
- Not a security control. Every signal is forgeable by the same user (research `callers-supervision-and-babysitting-cost` H10): the supervisor token by a same-user process that reads the owner-only state file, the schedule token by one that reads the entry, host and CI markers by setting the variable, a terminal by a pseudo-terminal. Refusals built on provenance (widening) fail toward refusal; nothing grants more because of a signal except a backed relay, which needs a person turn in the host.
- Release 1 shipped with no orchestrations and no schedules, so the S1 and S1s rows never match; that still holds after release 2.

### F53 SUP Supervision metrics `supported`

From [supervision-metrics.spec.md](../specs/supervision-metrics.spec.md).

- Count every decider (ADR `supervision-is-a-promotion-and-improvement-measure`). The owner's lifecycle is "less human-in-the-loop, then the pipeline". In the pipeline no agent babysits a run, so a workflow that today needs an agent's rescues is not ready even if no person was touched.
- Designed touches are the job. An approval the workflow asks for is not supervision debt; counting it would push authors to remove approvals (HUM). It is counted, shown, and kept out of the undesigned figures.
- Levels describe a run, not a workflow. A workflow's autonomy is the distribution of its runs' levels, which is what public measurement found: autonomy is a property of a deployment (research `callers-supervision-and-babysitting-cost` P1). The scale is the user's-role scale of Feng, McDonald and Zhang (research `callers-supervision-and-babysitting-cost` P4).
- No active time. How long a person spent reading a pause cannot be measured from records; only waiting time and turn counts are. The design does not estimate it.
- Promotion thresholds are defaults with no data behind them.
- As built in release 1 (T7.5): the record is built by `run/supervision.py` and read by the stats row, the sink row, the detail document and `report --supervision` (`observe/supervision_report.py`). A run is a thread and its figures are the thread's last record; `--by unit` counts touches from the ledger's intervention rows; waits per pause kind are read from the ledger's intervention rows decided by a person (p50, p90 and the number of pauses per kind); supervision cost, share and observations are joined from SCO's closed ledger lines (T7.6), so a thread counts as not measured until its supervision closes; the share is null while the run has no estimated cost. `promote-check` came in release 2 (PRO).

### F54 SCO Supervision cost `supported`

From [supervision-cost.spec.md](../specs/supervision-cost.spec.md).

- Measured where it is spent (ADR `a-supervision-journal-written-by-the-host-not-by-read-only-verbs`). The supervising session's host is the only place that sees its usage. The plugin already ships in that host, so the measurement comes with it and needs nothing from the person.
- Two figures (ADR `attribute-supervision-spend-by-marginal-tokens-beside-turn-totals`). A turn's input holds the whole conversation, so its total overstates what a run cost the session; the marginal figure understates the context a run makes the session carry. Showing both brackets the truth; promotion uses the marginal figure with `rewake` in it.
- The 300 s wake threshold is the shortest prompt-cache lifetime.
- As built in release 1 (T7.6): `observe/supervision_cost.py`, the plugin's `hooks/hooks.json` and the `supervision` verbs. The Claude Code payload fields used (`session_id`, `cwd`, `prompt`, `tool_name`, `tool_input.command`, `tool_input.run_in_background`, `tool_use_id`, `agent_id`, `tool_response.stdout|stderr|exit_code`, `transcript_path`, `agent_transcript_path`, `reason`) are the documented shape, not yet probed (P-SUP-3). Deviations: the hook reads the printed output only for its size and a `thread_id` or `call_id` in it, and keeps neither text; an engine call's `duration_s` is null; `relay` in `calls` counts messages; the relay window starts at the read call; `observations` on the closed line counts `watch` and `diagnose` calls.

### F55 PKG Workflow package `supported`

From [workflow-package.spec.md](../specs/workflow-package.spec.md).

- Why one folder. The owner's product form is a workflow that is itself a Claude plugin with a Python part (research `design-gap-review` G2); one folder means one version, one install and one digest. Alternatives in ADR `a-workflow-package-is-one-claude-plugin`.
- Why a second manifest. Claude Code strips unknown keys from `plugin.json` (research `workflow-packages-authoring-and-good-outcomes` A1), so engine fields cannot live there.
- Why builders. Typed builders give an error at the misspelt field, keep callables as real functions the check worker can import, and let the later `tempergraph` Python package expose the same surface (ADR `declare-workflows-with-typed-python-builders-and-text-in-files`). Long text lives in files so prompt audit, lessons and the improvement loop edit text, not code.
- Isolation is by rule. A package is imported into the engine process (WFM); the import scan and the dependency gate are the controls, not a sandbox. `undeclared-import` is only a warning because a distribution's import name may differ from its project name.
- Release 1. The minimal package passed `claude plugin validate --strict` on Claude Code 2.1.329 (model-free, 2026-11-20); `--strict` asks for `author`, so the scaffold writes it. `claude` only (ADR `first-release-ships-the-claude-executor-only`). The docs half and its check shipped in release 1, the check as a warning.
- Removed from the engine spec by the migration (ADR `the-engine-names-no-workflow`): the old PKG-B8 described temperspec itself (plugin `temperspec-tgraph`, workflow `temperspec`, rule sets as skills, architecture, planning and coding agents, plan and git checks in `workflow/temperspec/checks.py`, its outcome "a draft pull request whose code meets the task's acceptance criteria, with the plan's verification passing"), and PKG-B7's example named its `spec-authoring` skill. The behaviour now states the general capability; temperspec's own docs hold the rest.

### F56 AUT Workflow authoring `supported`

From [workflow-authoring.spec.md](../specs/workflow-authoring.spec.md).

- Backwards, as backward design does (research `workflow-packages-authoring-and-good-outcomes` B1): the evidence is fixed before the activities, so a step exists because an intermediate outcome needs it, not the other way round. Steps, prompts and models come after the outcome, because they serve it.
- The skill drafts, the engine decides what is well-formed. Every check of a draft is a model-free verb, so a different authoring host (another agent, a person by hand) gets the same refusals. This spec replaced the phase list of SHL.
- Graded drafts for the chat path. When a person cannot list criteria, comparing two outputs is easier than naming rules, and the criteria found that way are what they will grade by later (research `workflow-packages-authoring-and-good-outcomes` B2, B3).
- Release 1 shipped `new` and `revise` modes for workflows of model steps, scripts, routes and switches; trust in `author check` is as it will be once scaffolded (a check is `deterministic` when a good example exists for its unit).
- Removed from the engine spec by the migration (ADR `the-engine-names-no-workflow`): the old AUT-B8 described authoring temperspec itself (temperspec's method as the solution, its rule sets and gates as sources, nine mechanical criteria as `check` with `existing:review_rule`, the plan and code judges' criteria as `judge`, "the change is the right one for the product" as `none` reviewed in the pull request, research `temperspec-needs-against-the-engine`). The behaviour now states the general case.

### F57 OUT Run-level good outcome `supported`

From [run-outcome.spec.md](../specs/run-outcome.spec.md).

- One file, one bar. Step gates, the outcome gate, the outcome lens, eval trials (EVS) and promotion read the same criteria, so a revision moves all of them together (ADR `the-good-outcome-is-one-data-file-of-final-and-intermediate-outcomes`).
- Why the outcome gate is mandatory. research `design-gap-review` recommended it; without it, a run whose every step passed can still miss the request, and the loop has nothing to grade against. Its cost is one judge session per run in `dev`; `stable` may sample (ADR `a-run-is-measured-at-a-final-outcome-gate`).
- Why show, not hide. An unverifiable requirement left out of the file looks verified to everyone who reads the reports. Keeping it as `none` with a reason makes the gap a number the owner can watch and the promotion rule can refuse.
- Criteria drift is expected: people find new criteria after grading outputs (research `workflow-packages-authoring-and-good-outcomes` B2).
- Release 1 built the file, classes, trust, gate, record, sign-off, the measures without correction where no judge is calibrated, `outcome show`, `outcome candidates` and revise mode; calibration, corrected rates and `outcome` proposals from the loop came after the core in the same release (ADR `first-release-is-simple-trusted-workflows-on-one-machine`).
- As built (R2-T7): a deliverable is required only on a path that produces it; the outcome gate takes the units the run passed and skips a deliverable whose producing unit is on no path the run took (a switch arm not taken); the same rule makes a judge reference to an off-path artifact optional.
- Removed from the engine spec by the migration (ADR `the-engine-names-no-workflow`): the old OUT-B3 example was "a temperspec run"; the example now names no workflow.

### F58 SCF Blueprint, scaffold and authoring checks `supported`

From [blueprint-and-scaffold.spec.md](../specs/blueprint-and-scaffold.spec.md).

- Blueprint first is the strongest authoring rule: the person approves a drawn shape and the tables before any file exists, and the built workflow is compared with what was approved, so a scaffold or a later edit cannot drift silently.
- Model-free, then one real run. A model-free ladder catches what is wrong with the package; only a live run on a real case shows whether the outcome and its verifications grade the way the person grades (ADR `check-an-authored-workflow-model-free-then-by-one-consented-trial`). The person's grades on that run are the first labels and calibration cases, which is where criteria drift shows first (research `workflow-packages-authoring-and-good-outcomes` B2).
- Coverage reading (release 1). A final criterion is covered when the outcome gate verifies it at `deterministic`, `calibrated` or `human` trust, or when every gated unit in `order` has a serving intermediate criterion at such trust, whatever the outcome gate's own verifier. Release 1 flows are routes and switches over `order`, so every gated unit stands in for "every unit on every path". Without the second reading no workflow with a judged final criterion could be covered before its judge is calibrated (plan T12), and SCF-B3 could not hold.
- `outcome_ref.digest` leaves out the `revisions` history because scaffold adds the `authored` revision entry, and the history says how the outcome changed, not what it says.
- The `seed` block serves rung 8 only: scoring and acceptance (JCL) read labels alone, so seeds never count toward acceptance. The bar per seed stays two right gradings in a row (live check L-26, 2026-11-22).
- As built: trust and coverage in `tempergraph.run.outcome_trust`; the throwaway spec in `tempergraph.author.blueprint`; generated tests call `tempergraph.package.selftest`; `author verify` in `tempergraph.author.verify`; rung 8 in `tempergraph.author.trial.seeds` through JCL's `judge_once`; rung 9 `start_trial`. The stand-in run queues one step reply per step of `order`, so the first choice of each routing value has to lead the run through every unit; a fixture file replaces the workspace's copy of an earlier unit's file, as a step that edits it does; release 1's runner has no dry-run switch. Literals of an authoring session's sources are scanned by `author check` (plan T9.2). Check helpers cover the listed primitives; the test runner is the one set up by first-release track T1.1.

### F59 LAD Effort ladder and one-step model escalation `supported`

From [effort-ladder-and-model-escalation.spec.md](../specs/effort-ladder-and-model-escalation.spec.md).

- Strictness comes from the cause table the engine already keeps, narrowed by trust: a RETRY counts only from a judge whose clean rate was measured ([research `judge-model-by-risk-and-evidence-for-escalation`](judge-model-by-risk-and-evidence-for-escalation.rsrch.md) F3).
- Judges stay fixed per attempt; a stronger producer is graded only by a judge at least as strong and calibrated there (condition E4). That replaces release 1's "judge on the ladder's last rung".
- E4 reads the gate judge's declared alias until JRK resolves it by risk.

### F60 JRK Judge model by risk `supported`

From [judge-model-by-risk.spec.md](../specs/judge-model-by-risk.spec.md).

- Why: temperspec judges code on a stronger model than the one that wrote it, by a fixed rule; JRK makes the rule data, per attempt, as a general capability (ADR `the-engine-names-no-workflow` keeps the workflow out of the spec).
- Only up: a cheaper judge for "low-risk" work is the agreeable-judge hazard in a new form (research `evaluating-llm-judges-public-practice` F2).
- A risk rule is a cost bet like a switch (SWM), so it has the same shadow mode, and moving a threshold is a `judge_model` proposal of class `grader` measured by a trial (PRP). The rule shares the switch's choice, record and override layer, but makes no graph edge.
- `risk` on a council member, chair, contest slot or the audit judge cannot be declared: a council's members and chair are built and have no `risk` field, contest slots are not built, and their specs fix their bindings.
- Stock `when` rules answered the open question "should the engine ship stock rules (paths by glob, lines changed) so a workflow declares only thresholds?": yes; a workflow may still write its own `rule`.
- As built (R2-T3): `run/risk.py` runs the rule under a one-second guard and resolves the level in the judge node; the builder gives `Risk`, `Level` and `When`; per-level reliability grades from R2-T4.

### F61 CXR Complexity routing between decompositions `supported`

From [complexity-routing.spec.md](../specs/complexity-routing.spec.md).

- Evidence: per-phase code costs more than one session on small plans, while long single sessions time out on large ones (research `routing-by-complexity-between-decompositions` F1); the after-planning example rule (`single` when phases ≤ 3 and rows ≤ 30) is a delivery workflow's choice. The spec states the capability without the workflow (ADR `the-engine-names-no-workflow`).
- Predict, then fall back once: neither alone suits a mix where most tasks are complex but some are trivial (research `routing-by-complexity-between-decompositions` F5).
- Thresholds are data so the improvement loop can move them: a change to a rules file is a producer proposal of kind `flow` (PRP), measured by a trial on the case set; a repository override is the person's own, recorded on every route record.
- Per-item choice inside a map stays `item_model`.
- Remedy order across specs for one unit: the effort ladder, a re-arm, one model step, a person (LAD).
- The old spec drew both shapes as a Mermaid diagram (before planning: triage, then `direct` do_all or `planned` plan, map, join, then verify; after planning: plan, then `single` code_all or `per_item` map over phases and a code join, then review); the format allows no code blocks, so CXR-B8 states them in words.
- As built (R2-T1.3): the switch's step node evaluates the measures and the rules once per run and keeps the result on its attempt record; the gate's pick reads it.

### F62 PRO Promotion check and workflow stages `supported`

From [promotion-check.spec.md](../specs/promotion-check.spec.md).

- Scope (owner, 2026-11-20; ADR `promotion-is-a-model-free-stamp-per-workflow-version`): release 2 built the stages, the check and the stamp for `local-stable`; `--to pipeline`, the `pipeline` stage, the regressed watch and pipeline runs are designed and built with CI pipelines in a later release.
- When pipelines arrive, the pipeline's executor is `claude` with an API key, an `apiKeyHelper` or cloud credentials, or `agent-sdk` (ADR `graduate-a-workflow-from-local-to-pipeline-by-measured-criteria` C1); each executor's stamp is a separate entry.
- P9 to P11 exist because a ladder, an escalation or a router is a path the pipeline must not take unmeasured (research `effort-ladders-and-one-step-model-escalation`, research `routing-by-complexity-between-decompositions`).
- As built (R2-T5.1): `improve/promotion.py` holds the stage of a run, the window, the criteria and the stamp; the bars are `data/promotion.json` (`share_measured` included). `content_version` on `run_started` makes a change inside the digest empty the window and void the stamp in one step. For `local-stable`, P7 counts the engine and executor fault findings of the window's runs, P8 the states of the latest eval suites, and P9 to P11 are reported with `ladder_unseen` units named. Release 2 status of the acceptance criteria: PRO-B1, B2 and B4 hold for `local-stable`; B3 and B5 need the `pipeline` stage.

### F63 CAR Run state carried on a branch `supported`

From [run-state-on-a-branch.spec.md](../specs/run-state-on-a-branch.spec.md).

- A separate orphan branch keeps state out of the work branch, its pull request and its diff statistics, and is deleted whole; a removal commit on the work branch would leave the state in its history (research `carrying-run-state-on-a-branch` F4). The owner chose the state branch over the work branch on 2026-11-21.
- The subset is what a resume reads; transcripts and prompts stay local by LOS's marks and contract C9.
- Plumbing commits touch no checkout, so a carry never disturbs the person's working tree or the run's worktree.
- This is the state half of a CI path; the pipeline half waits for a later release (ADR `release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing`).
- As built (R2-T5.2): `durability/carry.py`; the parent of each new commit is the fetched tip, so the branch stays a line of engine commits; a stopped thread is pushed and ends with `carry drop`.

### F64 WIN Windows support `supported`

From [windows-support.spec.md](../specs/windows-support.spec.md).

- Most rules answer known Windows failure modes (research `running-on-windows` F1); the job object replaces release 1's `taskkill /T`, which cannot act when the engine dies first.
- Refusing judges until the probes pass follows contract C15: a capability not shown is a refusal, never a silent downgrade.
- The owner question "native Windows, or WSL only?" was settled as native, with WSL as Linux (ADR `windows-is-supported-natively-with-job-objects`). Windows moved from release 2 to release 3 (second-release plan I2-22, third-release plan I3-13).

### F65 SWF Sub-workflow unit `supported`

From [subworkflow-unit.spec.md](../specs/subworkflow-unit.spec.md).

- A subgraph in the parent's thread keeps one checkpoint, one lock, one log and one cap per run, so `status`, `stop`, carrying (CAR) and the monitor need nothing new. A separate child run per unit (the batch shape) was rejected: two threads to resume, two caps, and a parent that cannot pause on the child's question (ADR `a-sub-workflow-runs-inside-its-parents-thread-workspace-and-cap`).
- The child's finalizer is skipped because the parent's finalizer is the one place a run leaves a trace outside its branch (FIN).
- The child keeps its own calibration and findings so that the same workflow, run alone or inside a parent, learns in one place.

## Conclusions

1. Every design note, release note, probe observation and removed workflow name of the engine specs is kept here or in the record the spec links; none was dropped silently.
2. Where an engine spec named a workflow package (ADR `the-engine-names-no-workflow`), the behaviour was restated as a general capability and the finding for that prefix records what was removed.
3. What a spec says is built or not built is now its own "Not built yet" line under Open questions; the findings here record how it came to be so.

## Open questions

- Should the findings here move into the decision records they explain, so this note can shrink over time? Until answered: they stay here, and a new decision record cites the finding it absorbs. Owner: engine owner.
