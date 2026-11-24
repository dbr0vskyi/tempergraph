# R-070 Workflow configuration overrides, reruns and resume with feedback: what exists, what is missing

## Problem statement

The owner asked on 2026-11-20 whether the engine design lets a person override a workflow's configuration "in all possible variations, starting from models for steps and judges, retries budget, per step time limits, cost cap etc", and whether the engine has ways to "retry, rerun, resume with feedback". This note answers three questions:

1. Which settings can be overridden today, at which levels, in which order, with what validation, and how is the effective value recorded?
2. Which ways to retry, rerun and resume exist today, and where can a person's feedback enter?
3. What do comparable public tools do, and which gaps follow?

"All possible variations" is read as: every value that changes how much a run may spend, how long it may take, how often it may repeat, which model or executor does the work, and which workflow-specific switch is taken, at every scope a workflow has (run, step, judge, council member and chair, contest slot, script, map item), from every place an operator can state it (a flag, a file, a profile, an orchestration node). It is not read as permission to change what verifies the work (criteria, checks, judge presence, judge tools, flow targets, prompts); that reading is assumption A2 of [ADR-0071](../adr/0071-overrides-never-change-what-verifies-the-work.adr.md).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S4 | This design on `main` after PR 10: CON-B4, CON-B5, CON-B6, CON-B7, CON-B3, SSN-B1 to SSN-B6; BUD; DUR; HUM; ROP-B1 to ROP-B13; EXI-B18; EVT-B10 to EVT-B16; ORC-B19, ORC-B20; MIG-B15; FLX; CNL; CTS; SCR | Design set | [specs](../specs/00-overview.spec.md) |
| S5 | LangGraph "Use time travel": replay from a `checkpoint_id`, fork with `update_state` | Official docs | https://docs.langchain.com/oss/python/langgraph/use-time-travel |
| S6 | LangGraph checkpointers: state history per thread, checkpoint ids | Official docs | https://docs.langchain.com/oss/langgraph/checkpointers |
| S7 | Claude Code settings: scopes and precedence (managed, command line, local project, shared project, user) | Official docs | https://code.claude.com/docs/en/settings |
| S8 | Temporal community answers on reset: a reset starts a new run of the same workflow id from a chosen workflow-task event; earlier history is kept | Vendor forum, staff answers | https://community.temporal.io/t/reset-workflow-to-a-particuylar-event-id/3294, https://community.temporal.io/t/is-it-possible-to-resume-from-a-failed-state-instead-of-starting-over/1182 |
| S9 | Argo Workflows retry against resubmit (`--memoized`) | Secondary article | https://oneuptime.com/blog/post/2026-08-02-argo-workflows-retry-vs-resubmit/view |

## Key findings

### Part 1: overrides today

| # | Finding | Confidence |
|---|---|---|
| F1 | Models have a full layered order for steps (operator per step, operator per run, the step's model or ladder rung, workflow default, `inherit`) and a separate one for judges, so a step override never reaches a judge (CON-B3). Every record carries alias, source layer and executor. | confirmed (S4) |
| F2 | Timeouts have the same layered order for steps and judges (BUD-B10), and the record carries the source layer. `idle_s` has a step field and a run flag (`--idle`) but no per-step operator layer and no judge layer. | confirmed (S4) |
| F3 | Executors can be overridden per run, per step and for judges (`--executor`, `--step-executor`, `--judge-executor`); DUR-B7 reapplies a per-step executor override across resume. | confirmed (S4) |
| F4 | Only one budget has an operator override: `--run-cost-cap`. The retry budget, loop budget, infra tries and backoff, attempt cap, human cap and `on_budget_spent` are workflow-only or engine constants. temperspec's operators need an iteration budget that grows for a long plan and a test budget switch. | confirmed (S4) |
| F5 | Session options (`effort`, `cost_cap_usd`, `turn_cap`, `fallback_alias`) are step data only; no operator layer exists, though nothing stops them resolving in the order models do. No subagent model setting exists, so an operator cannot choose the model of a step's subagent, such as a discovery step's survey. | confirmed (S4) |
| F6 | Council members, the chair, contest slots and scripts declare `executor`, `model`, `timeout_s`, `idle_s` and per-attempt `cost_cap_usd`, but no operator flag addresses them: `--step-model` names a unit, not a member or slot. | confirmed (S4) |
| F7 | Deadlines (`deadline_s`) and the audit judge rate have no layered resolution; `--audit-rate` is the only run flag. | confirmed (S4) |
| F8 | There is no machine or project configuration layer for run settings. An operator config exists under the state root and the home folder, but it holds hooks, observers, sinks, price overrides and `observe.*` only (LOS-B7, LOS-B8, LOS-B9). The binding table is per machine but maps aliases to models; it does not choose them. | confirmed (S4) |
| F9 | Workflow-specific switches have only one generic form: `--arm <switch>=<arm>` for a switch unit. temperspec needs a test budget, a single-session code mode, a publish base branch, PR opening off and filing off, and an operator diagnosing any workflow needs overrides too. Nothing lets a workflow declare a typed knob with a default that a check, route, script or template reads. | confirmed (S4) |
| F10 | There are no named profiles: an operator who wants "the cheap configuration" or "the thorough one" repeats a set of flags. | confirmed (S4) |
| F11 | `RunOptions` is named in DUR's signature and "stored with the run options" in DUR and ORC, but no type defines it; ORC-B19, ORC-B20 lists a "subset of run options" by prose. | confirmed (S4) |
| F12 | There is no one record of the effective configuration of a run. Each `attempt_start` carries its own alias and timeout with their sources, but budgets, caps and flags appear nowhere as resolved values, and no read-only verb shows what a run would use before it starts. `run --check` reports `ok`, `needs`, `error` or `broken` only. | confirmed (S4) |
| F13 | Validation of overrides is partial: an unknown alias, an unmapped tool, an unsupported session option and an unknown `--pause-before` unit are refused before spend; nothing refuses an override aimed at a unit that does not exist, or at a setting a unit kind does not have (`--step-model` on a script unit). | confirmed (S4) |
| F14 | Self-improvement cannot tell a failure caused by an operator's override (a smaller model, a shorter limit) from one the workflow owns, because findings and ledger rows carry no settings provenance. Counting a re-run of the same task as ground truth about a run, as FBK does, assumes a rerun is linked to its source. | supported (S4) |
| F15 | Claude Code orders settings as managed, command line, local project, shared project, user; arrays merge across scopes and permission denies win at any level (S7). A tool whose runs are shared across machines needs per-machine defaults and per-run flags at the top. | supported (S7) |

### Part 2: retry, rerun and resume today

| # | Finding | Confidence |
|---|---|---|
| F16 | Automatic retries are edges spent from a per-visit retry budget; infra failures rerun on their own counter with backoff; a model ladder steps up per attempt; automatic re-open is a person's retry given in advance (BUD). | confirmed (S4) |
| F17 | A person at a pause can `proceed`, `retry` with feedback, `back:<unit>` with feedback (only to the gate's `back_targets`), `stop`, deliver an event or answer an ask (HUM-B12). A `stopped` thread re-opens with `retry` or `back`; an `unfinished` one continues but refuses a decision or feedback; a `finished` one is refused (DUR-B9). | confirmed (S4) |
| F18 | Feedback reaches the retried step and its judge **once** (HUM-B12, PRM-B6). A workflow that wants a person's ruling to last must have a step copy it word for word into the next artifact for the judge to see, and nothing verifies that a person's earlier feedback reaches every later judge. A ruling that disappears after one attempt lets a later retry or a later unit's judge undo it. | confirmed (S4) |
| F19 | `proceed` takes no feedback, so a person who accepts work with a note for the next step has no form for it. | confirmed (S4) |
| F20 | There is no way to run again from a chosen unit of a finished run: the only options are a new thread from scratch or nothing. A person unhappy with the result of `release` must rerun triage, discovery, plan and code. LangGraph supports this directly: invoking a thread with a past `checkpoint_id` replays from it, and `update_state` on a past checkpoint forks a new branch of history (S5, S6). Temporal's reset makes a new run of the same id from a chosen point and keeps the old history (S8); Argo distinguishes retry (same workflow, failed nodes) from resubmit (a new workflow, optionally reusing memoized successes) (S9). | confirmed (S5, S6, S8, S9) |
| F21 | A person's `back` is limited to the gate's declared `back_targets`. That list exists to bound automatic attribution; a person who sees that the fault is two units earlier than any listed target has no way to say so short of a new thread. | confirmed (S4) |
| F22 | Resuming with changed settings exists only for executors (DUR-B7) and the run cost cap ("re-openable after the operator raises it", BUD-B8, BUD-B9), with no stated rule for how a raised budget meets a counter already spent. | confirmed (S4) |
| F23 | A map item, contest slot or council member is answered by unit and item at a pause, and a passed map item never runs again (HUM-B3, CTS, CNL). This covers "rerun one item" inside a live thread. | confirmed (S4) |
| F24 | The orchestration supervisor re-opens infra failures and re-runs by node identity (ORC-B9, ORC-B13); `orchestrate answer` passes a decision and feedback. It has no form for rerunning a finished node from a unit. | confirmed (S4) |
| F25 | Every retry starts a fresh session; a self-check that resumes the session would continue an agent's conversation instead. Session continuation is not declared by every executor (the Messages API executor owns its loop; Antigravity's resume is unprobed). | supported (S4; R-002, R-003) |
| F26 | Thread ids are `<workflow>/<task_id>` and a fresh start on a used id is refused (C7). A rerun therefore needs a new id with a stated link to its source, or it collides with the source thread. | confirmed (S4) |
| F27 | Declared tools cannot be widened for a run, and a failed attempt that met a refused tool spends a retry that meets the same refusal. Tool access is a leading cause of friction (R-050 C4), and without a run-level grant an operator can only widen permissions by hand. | confirmed (S4) |

## Conclusions

1. The design covers **models, executors and timeouts** with a layered, recorded order, and **retry, back, re-open and resume** at every thread state. It does not yet cover overrides "in all variations": budgets other than the run cost cap, session options, subagent models, idle limits for judges, the members, chair, slots and scripts of the PR 10 units, deadlines, and workflow-specific switches have no operator layer (F2, F4 to F7, F9).
2. There is **no configuration file layer** for run settings and **no profile**, so a machine-wide default (a slow host's longer limits, a team's cheaper model) is repeated as flags on every run (F8, F10).
3. Overrides need **one catalog** of settable keys with types, ranges, scopes and the layers that may set them, so that validation can refuse a misaimed or out-of-range override before spend (F13) and the order is the same for every key (F1, F2). That catalog is spec 80, RST.
4. The **effective configuration** must be one record per run segment, with each value's source, plus a read-only verb that shows it before a start; self-improvement and stats must carry a digest of it and the list of overridden keys (F12, F14). RST owns both.
5. `RunOptions` must be a defined type in CON, with the settings snapshot it carries and the rule for resume (F11, F22). Settings are snapshotted at start and reapplied on resume; a resume may change them (ADR-0072).
6. What verifies the work (criteria, checks, judge presence, judge tools, independence, flow targets, prompts) is **not a setting**; overrides may only change cost, time, repetition, model and executor choice, and declared workflow switches (ADR-0071).
7. Feedback needs a **lasting form**: a ruling a person gives at any resume, rendered to every later attempt of its unit and to the judges of the units it names, until revoked (F18, F19). Spec 81, RRN, owns it.
8. A **rerun from a unit** is needed in two forms: on a live thread, a person's **rewind** to any completed unit on the path, not only `back_targets` (F21); on any thread, finished included, a **rerun** that forks a new thread from the checkpoint before that unit, keeps every earlier verdict and links to its source (F20, F26). Both use LangGraph's checkpoint history; neither rewrites the source's history (ADR-0073).
9. Continuing an agent's session on retry stays out of the first release: every retry stays a fresh session (F25). It is recorded as an open question.
10. temperspec's levers are all expressible after RST and RRN: models with judge separation, a subagent model, run-wide and per-step timeouts kept on resume, an iteration budget, one phase resumed by instance, a test budget, code mode, publishing switches and filing off as workflow settings, and rulings shown to later judges.

## Coverage table: the owner's list against the design after specs 80 and 81

| Variation | Before | After |
|---|---|---|
| Step model, judge model, per step and per run | yes (CON-B3) | same order, now one catalog row each; per member, chair and slot added |
| Model ladder | workflow only | settable as a list on the step scope |
| Subagent model | no | `subagent_model` per step |
| Effort, session cost cap, turn cap, fallback model | workflow only | all layers |
| Executor per run, step, judge | yes | same; per member, chair, slot added |
| Retry budget, loop budget | workflow only | all layers, within ceilings |
| Infra tries and backoff, attempt cap, human cap | engine constants | all layers, within ceilings |
| On budget spent (`stop`, `ask`, `fallback`) | workflow only | operator may switch `stop` and `ask`; `fallback` only where declared |
| Step and judge timeouts, idle limits | step and judge timeouts layered; idle partly | timeouts and idle for every session kind and script |
| Run cost cap | flag and workflow | all layers, raise at resume defined |
| Per-attempt cost cap of a council or contest | workflow only | all layers |
| Approvals, breakpoints, auto re-open, audit rate, workspace mode, strict permissions | flags | flags and files; strictness tighten-only |
| Wait and ask deadlines | workflow only | all layers |
| Workflow-specific switches | switch arm only | declared typed `settings` and named `profiles` |
| Machine and project defaults | no | user and project files, `defaults` and `overrides` sections |
| Effective config record and preview | partial | `settings_resolved` record, `config show` |
| Retry with feedback | yes, once | once or as a ruling |
| Proceed with a note | no | `proceed` with feedback |
| Feedback on an unfinished resume | refused | accepted for the pending unit |
| Back to an unlisted earlier unit | no | `rewind:<unit>`, a person's decision |
| Rerun a finished run from a unit | no | `rerun --from <unit>`: a new linked thread |
| Rerun with other settings | executor only | any setting, at resume or rerun |
| Allow a tool, skill, MCP tool or command a step lacked | edit the package and start again | `--grant`, `--allow-command` on run, resume or rerun; a `tool_access` pause offers them (RST-B28, RST-B29, RST-B30, ADR-0080) |

## Open questions

| Question | Owner |
|---|---|
| Should a retry be allowed to continue the previous session (cheaper, keeps context) where an executor declares session resume, instead of a fresh session? Needs a measured comparison of first-pass yield and cost. | Owner |
| Should an organisation be able to impose a managed settings layer above the operator's (for example a hard cost ceiling), as Claude Code's managed settings do? First release has none. | Owner |
