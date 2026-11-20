---
title: Engine CLI
type: component
status: ready-for-implementation
prefix: CLI
adrs: [0015, 0021, 0022, 0027, 0028, 0040, 0070, 0073, 0085, 0087, 0095, 0096]
---

# Engine CLI

## 1. Overview

The `tempergraph` command line is the engine's public interface for people, skills and CI. Its verbs are plain words; its exit codes are the caller contract ([CON §2.9](01-contracts.spec.md)). Input resolution and every read-only verb call no model and create nothing (contract C13). A shim picks the engine's interpreter and exits 127 if none has the engine.

## 2. Contract

| Verb | Does | Writes | Spends |
|---|---|---|---|
| `run <workflow> <request…> [options]` | Resolve, preflight, start | yes | yes |
| `run --check …` | Resolve and preflight only; prints one status | no | no |
| `resume <workflow> <thread> [--decision …] [--feedback …\|--feedback-file <path>] [--ruling] [--ruling-for <units>] [--revoke-ruling <id>] [--accept-external] [--set k=v] [--unset k] [--profile p] [--reload-settings] [--input k=v] [--answers <file>] [--apply-deadline]` | Resume per thread state; feedback, rulings and `rewind:` per [RRN](81-reruns-and-feedback.spec.md); settings per [RST §2.6](80-run-settings-and-overrides.spec.md); `--answers` and `answer:` decisions for an ask ([ASK](73-ask-unit.spec.md)); `--apply-deadline` for an overdue wait or ask ([FLX §2.3](74-flow-extensions.spec.md)) | yes | yes |
| `rerun <workflow> <thread> --from <unit>[.<item>]\|start [--check] [--feedback …] [--ruling] [--set k=v] [--profile p] [--task-id <id>] [--workspace current\|at-unit] [--same-branch] [--drop-rulings] [--accept-external]` | A new thread forked from the checkpoint before that unit, linked to its source ([RRN §2.4](81-reruns-and-feedback.spec.md)) | yes, except `--check` | yes, except `--check` |
| `config show <workflow> [--thread <t>] [--set …] [--profile …] [--key <glob>] [--json]`, `config validate [--file <path>]`, `config paths` | The resolved settings with their sources; validation of the settings files ([RST §2.9](80-run-settings-and-overrides.spec.md)) | no | no |
| `status [selector] [--detail [--unit <name>] [--no-live]] [--all-roots]` | Status document; `--detail` gives one thread's detail document ([RDD](31-run-detail-document.spec.md)); `--all-roots` reads every state root in the machine index ([CST §2.1](34-central-run-stats.spec.md)) | no | no |
| `events <selector> [--since <seq>] [--follow] [--activity <session_key>] [--json]` | Run-log records and activity lines in order ([EVT §2.6](30-run-events.spec.md)) | no | no |
| `logs <selector> [--session <key>] [--kind …] [--follow] [--json]` | One log of a run from the local store ([LOS §2.4](33-local-observability-store.spec.md)) | no | no |
| `wait <selector> [--timeout s]` | Block until an outcome | no | no |
| `attention [--all-roots] [--json]` | Every item waiting on a person under the state root, oldest first: pauses of every thread and, when present, orchestration attention items (CLI-B6, [ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)) | no | no |
| `list` | The catalog (versioned JSON or a table) | no | no |
| `graph <workflow> [--format mermaid|svg|md] [--overlay <thread>]` | Diagram from the model; `--overlay` adds a thread's counts and verdicts ([OBS §2.4](15-observability-and-cost.spec.md)); release 1 draws `mermaid`, `md` and `json`, not `svg` | no | no |
| `report [window] [--by unit|executor|version] [--json]` | Cost and friction reports | no | no |
| `validate <workflow>` | Validation, view deferrals, prompt-tool check | no | no |
| `audit <workflow> [--layer …] [--target <path>] [--window <days>] [--all] [--format text\|json\|sarif] [--fail-on …]`, `audit tools <workflow>`, `audit prompts <workflow>` | Advisory audit of a workflow's definition, host and run history; exit 6 only with `--fail-on` ([AUD](55-workflow-audit.spec.md)) | no | no |
| `executors [--probe]` | Registered executors, capabilities, CLI versions, probe facts | no | no |
| `batch <workflow> <targets…> [-k N]` | Many child runs, as a one-node orchestration ([ADR-0038](../adr/0038-batch-is-a-one-node-orchestration.adr.md)) | yes | yes |
| `orchestrate validate\|plan\|start\|status\|wait\|answer\|edit\|stop\|resume\|list\|report …` | A graph of runs ([ORC §2.6](45-orchestration.spec.md)) | start, answer, edit, stop, resume | start, answer, resume |
| `schedule parse\|add\|list\|show\|history\|runs\|edit\|pause\|resume\|skip\|fire\|remove\|tick …`, `schedule loop [--detach\|--stop]`, `schedule trigger install\|status\|remove`, `schedule export <id> --for <system>` | Run a workflow or a saved orchestration once or on a recurrence, given in an exact format (ISO 8601, RFC 5545, cron) or optionally in words, echoed back in exact form before it is saved ([SCH §2.7](83-schedules.spec.md)); the OS-agnostic tick, its portable loop and optional trigger adapters, pipeline export ([TCK](84-schedule-ticks-and-unattended-fires.spec.md)) | all but `parse`, `list`, `show`, `history`, `runs`, `trigger status`, `export` | `tick` and `fire` only |
| `attention [--json]` | Every item waiting on a person under the state roots of the machine index, oldest first, with its answering command; schedule items included ([ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md), [TCK §2.7](84-schedule-ticks-and-unattended-fires.spec.md)) | no | no |
| `stop <selector> [--drain\|--now] [--caller …] [--relayed]` | Drain a running run (no new attempt or unit; ends `unfinished`, exit 4) or, with `--now`, end its open session at once; resumable either way. Owned by spec 32 (RCT §2) of the run-control design; needed by [ORC §2.8](45-orchestration.spec.md) N3 | yes | no |
| `worktree list [--all] [--json]`, `worktree path <thread>`, `worktree prune [--thread <t>] [--finished] [--older-than <days>] [--apply]` | Engine worktrees: list, a thread's path, removal of clean ones ([WTR §2.11](82-worktree-mode.spec.md)) | `prune --apply` only | no |
| `update [--check] [--dry-run] [--json] [--with …] [--rollback] [--prune-engines]` | Install a release beside the current engine and switch to it; extras, shim, home layout, manifest reconcile; `--check` is read-only ([UPD](60-engine-update.spec.md)) | yes, except `--check` | no |
| `install [--check] [--with …] [--add-to-path] [--repair]` | First install from the plugin's launcher: home folder, first environment, shim, `PATH` block, registry ([UPD §2.7](60-engine-update.spec.md)) | yes, except `--check` | no |
| `workflows list\|register <path>\|unregister <name>\|reinstall [<name>\|--all]` | The workflow registry: entries, pins, dependencies reinstalled into the current environment ([UPD §2.8](60-engine-update.spec.md)) | all but `list` | no |
| `upgrade <workflow> [--check] [--no-assist] [--trial] [--stamp] [--bump] [--open-pr] [--continue <id>]` | Bring a workflow's source up to the running engine on a branch: plan, transforms, the gated upgrade workflow, verification, stamp ([WUP](63-workflow-upgrade.spec.md)) | branch, upgrade record, stamp; nothing with `--check` | the upgrade workflow only |
| `upgrade-check <workflow> [--stamp]` | Kept as `upgrade --check`; `--stamp` on a clean check | stamp only | no |
| `facts <selector> [--json]` | Read-only facts about a run for other tools (state, branch, artifacts by key, pending gates, cost figures, alias, label, origin) | no | no |
| `stats [--month YYYY-MM\|--since <date>] [--source <sink>\|--local] [--sync] [--by …] [--projection] [--live] [--json]` | Per-user monthly run rows ([OBS §2.4](15-observability-and-cost.spec.md)); across machines from a sink ([CST §2.5](34-central-run-stats.spec.md)) | no | no |
| `stats flush` | Delivers outbox rows to the configured sinks ([CST §2.3](34-central-run-stats.spec.md)) | sink and outbox only | no |
| `stats sync` | Pulls every directory sink into the fleet copy under the home folder ([CST §2.3](34-central-run-stats.spec.md)) | fleet copy only | no |
| `store usage\|prune\|export` | Size, retention and export of the local store; `prune` takes `--older-than <days>`, `--keep-failed` or `--no-keep-failed` and `--dry-run` ([LOS §2.4](33-local-observability-store.spec.md)) | prune and export only | no |
| `hooks add|list|remove|test` | Run lifecycle hooks (§2.2) | add and remove only | no |
| `improve backlog|propose|trial|aa|open|show` | Proposals and trials ([PRP §2.7](40-improvement-proposals.spec.md)) | per [PRP](40-improvement-proposals.spec.md) | `propose`, `trial`, `aa` |
| `improve review <selector> [--session <key>…] [--full] [--dry-run] [--json]`, `improve review show <selector>`, `improve review summary [workflow] [--version <v>]` | Session review of a run, its result, and observations over a window ([SRV §2.9](44-session-review.spec.md)) | `review` only | `review` without `--dry-run` |
| `label <thread> <gate> [--criterion id] [--attempt n] --value agree|disagree`, `labels queue\|grades <workflow>` | Enter a label; list judgements to label ([FBK](41-feedback-and-judge-reliability.spec.md)) | `label` only | no |
| `evals run\|report\|grade …`, `evals score\|bar\|label …`, `evals harvest\|replay …` | Eval suites ([EVS](51-eval-suites.spec.md)), judge calibration ([JCL §2.6](50-judge-calibration.spec.md)), harvest and replay ([LIF §2](18-lifecycle-and-evals.spec.md)); owned there | per owner spec | live kinds and `score`, `replay` only |
| `report --loop [window]` | The loop's own metrics ([IMD §2.4](43-improvement-data.spec.md)) | no | no |
| `supervision hook <event>` | The plugin's Claude Code hooks: one event's JSON on standard input to the journal ([SHL §2.2](19-plugin-shell.spec.md)); always exit 0 | the journal | no |
| `supervision log --host <h> --session <id>`, `supervision close [--session <id>]`, `supervision show <selector>\|--session <id> [--json]` | Append a host's or application's supervision entries; close threads' supervision cost; show a thread's or session's supervision ([SCO §2.6](87-supervision-cost.spec.md)) | `log`: the journal; `close`: ledger lines and outbox rows; `show`: no | no |
| `report --supervision [window] [--by workflow\|version\|unit\|host\|level]` | Touches, levels, waits and supervision cost per workflow ([SUP §2.4](86-supervision-metrics.spec.md)) | no | no |
| `author start <name> --from solution\|sources\|chat [<path>…]`, `author start <workflow> --revise`, `author intake <id> <path>… [--kind …] [--artifact <key>] [--unit <unit>] [--outside]`, `author check\|show [--json]\|drop <id>`, `author list`, `author approve <id> <phase>` | An authoring session: sources, inventory, draft checks, phase approvals ([AUT §2.1, §2.8](89-workflow-authoring.spec.md)) | session folder only | no |
| `blueprint check\|draw <file> [--outcome <file>]`, `blueprint compare <workflow>`, `literals <workflow> [--cases]`, `scaffold <session> --out <dir> [--update] [--update-docs]`, `author verify <workflow> [--judge-seeds] [--trial --case <id>] [--cap <usd>] [--json]`, `author trial <workflow> [--json]`, `author grade <workflow> [--unit <unit>] --criterion <id> --status <status> --reason <text> [--reviewer <handle>] [--json]` | The blueprint, the scaffold and the checks of an authored workflow, the first trial's report and the person's grades ([SCF §2.6](91-blueprint-and-scaffold.spec.md)) | `scaffold`: the package; `verify`: registry, stamp, trial; `grade`: a ledger label and a calibration case candidate | `verify --judge-seeds`, `--trial` only |
| `outcome show <workflow> [--runs [window]] [--json]`, `outcome candidates <workflow> [--window <days>]` | The good outcome with trust and coverage, the workflow's outcome measures, revision candidates ([OUT §2.5, §2.6](90-run-outcome.spec.md)) | no | no |
| `self-check <ticket>` | Run one unit's check on the current workspace for the step session that holds the ticket; prints findings; granted to a step by `self_check` only ([CHK §2.5](75-check-contract-and-command-runs.spec.md)) | command-run records only | no |

### 2.1 Run options

`--set <key>=<value>` (repeatable), `--settings <file>` (a JSON map of keys to values, read once, recorded as flags) and `--profile <name>` (repeatable) set any key of the settings catalog on the `flag` and `profile` layers ([RST](80-run-settings-and-overrides.spec.md)). The named flags below are spellings of `--set`; the right column gives the key.

| Option | Effect |
|---|---|
| `--executor <name>` / `--step-executor <step>=<name>` | `steps.executor` / `<step>.executor` |
| `--judge-executor <name>` | `judges.executor` (still must declare `restricts_judge_tools`) |
| `--model <alias>` / `--step-model <step>=<alias>` / `--judge-model <alias>` | `steps.model` / `<step>.model` / `judges.model` |
| `--timeout`, `--judge-timeout`, `--idle` | `steps.timeout_s`, `judges.timeout_s`, `steps.idle_s` |
| `--enforce-tools` | `run.enforce_tools=true`: hard tool enforcement on executors that declare it |
| `--strict-permissions` | `run.strict_permissions=true`: enforce declared tools on every step and refuse a step whose executor cannot ([EXI-B12](10-executor-interface.spec.md)) |
| `--alias <name>`, `--label <text>` | Run alias and label ([DUR §2.2](09-durability-and-resume.spec.md)) |
| `--grant <unit>=<capability>[,…]`, `--allow-command <unit>=<prefix>` | `<unit>.tools.add`, `<unit>.commands.add` (or `judge:<unit>.views.add` for read-only views): a person's tool grant for this run, on `run`, `resume` and `rerun` ([RST §2.8](80-run-settings-and-overrides.spec.md)) |
| `--arm <switch>=<arm>` | `<switch>.arm`: operator pick of a switch arm ([CMP](03-compiler-and-flow.spec.md)) |
| `--run-cost-cap <usd>` | `run.run_cost_cap_usd` ([BUD](08-budgets-and-failures.spec.md)) |
| `--daily-cap <usd>` | `run.daily_cap_usd`: stable mode's self-improvement budget per day ([SIL §4](16-self-improvement.spec.md)) |
| `--audit-rate <0..1>`, `--audit-executor <name>` | `run.audit_rate`, `run.audit_executor`: sampled audit judge ([JDG-B7](05-judge-and-verdict.spec.md)) |
| `--workspace auto\|worktree\|in_place`, `--worktree` / `--in-place` | `run.workspace` ([WTR §2.1](82-worktree-mode.spec.md)) |
| `--worktree-root`, `--worktree-base`, `--worktree-cleanup` | `run.worktree.root`, `run.worktree.base`, `run.worktree.cleanup` |
| `--approve <step>` | `<step>.approve=true`: approval pause after that step passes |
| `--auto-reopen N` | `run.auto_reopen`, 1–10 |
| `--caller person\|agent\|pipeline`, `--caller-app <name>` | Declares the caller on any mutating verb; a declaration only lowers trust, and `--caller person` from a marked agent is refused ([PRV §2.3](85-caller-provenance.spec.md)) |
| `--as-agent` | The same as `--caller agent` |
| `--relayed` | The decision is a person's, carried by an agent; counted as the person's only with a person turn in the host ([PRV §2.4](85-caller-provenance.spec.md)) |
| `--pause-before <unit>[.<item>]` | Run and resume: an operator breakpoint before that unit ([FLX §2.5](74-flow-extensions.spec.md)); release 2, so release 1 refuses it with exit 2 `not_in_release` |
| `--schedule <fire_id>` | Set by the schedule tick only, with its fire token; recorded as `schedule` ([TCK §2.3](84-schedule-ticks-and-unattended-fires.spec.md)) |
| `--parent <orchestration>/<node>[/<item>]` | Set by the orchestration supervisor only; recorded with the run options and shown as `parent` ([ORC §2.8](45-orchestration.spec.md) N1) |
| `--dry-run` | Self-improvement files nothing; every step still runs; recorded as `dry_run` on `run_started` and in the run's meta |

`run` also takes `--task-id <id>` (1 to 64 letters, digits, `.`, `_` or `-`) and `--input <k>=<v>` (repeatable). Without a resolver the request resolves by the declared input kind, read-only: `text` and `any` give `t-<first 10 hex of the SHA-256 of the whitespace-normalised request>`, so the same request finds the same thread; `tracker_key` takes the key as the id; `file` gives `f-<stem>-<6 hex of the path>`. An empty request is `needs` with the question `request`. `run --check` prints one JSON document and exits 0 on `ok`, 2 on `needs` or `error`, 1 on `broken` (the workflow or its resolver does not load). Machine output of every verb is JSON with `schema_version`; a run's one-line outcome and its resume command go to standard error.

The self-improvement verbs of release 1 (plan T12.3 to T12.6) take: `evals score <workflow> <gate> [--executor <name>] [--repeat k] [--variants <kinds>|none] [--cap <usd>] [--json]`; `evals bar [<workflow>] [--json]`; `evals label <workflow>/<gate>/<case> --criterion <id> --expected <status> --reason <text> [--reviewer <handle>] [--json]` with the caller options; `labels queue|grades <workflow> [--json]`; `improve backlog [<workflow>]`, `improve propose <workflow> <cluster> [--patch <file> --rule <sentence>] [--executor <name>]`, `improve trial <proposal> [--target <metric>] [--cap <usd>] [--executor <name>]`, `improve aa <workflow> [--cap <usd>]`, `improve open <proposal>` and `improve show <proposal|trial>`, each with `--json` but `show`, which prints JSON ([JCL §2.6](50-judge-calibration.spec.md), [FBK §2.3, §2.4](41-feedback-and-judge-reliability.spec.md), [PRP §2.7](40-improvement-proposals.spec.md)).

Option values select constants or are checked numbers; typed text never reaches a launch ([SEC](14-security.spec.md)). Every option is validated before spend by the same function on `run --check`, `run`, `resume` and `rerun` ([RST §4](80-run-settings-and-overrides.spec.md)). Every mutating verb classifies its caller once, before any write, and records the `caller` block ([PRV](85-caller-provenance.spec.md), contract C17); read-only verbs do not.

### 2.2 Lifecycle hooks

A hook is an operator-registered command run on a run event (`started`, `unit_entered`, `gate_verdict`, `paused`, `resumed`, `stop_requested`, `stalled`, `finished`, `failed`; [EVT §2.6](30-run-events.spec.md)) or an orchestration event (`orchestration_attention`, `orchestration_finished`; [ORC](45-orchestration.spec.md)), or a schedule event (`schedule_fired`, `schedule_missed`, `schedule_refused`, `schedule_paused`; [SCH §2.8](83-schedules.spec.md)), so a notifier can reach a person about an unattended run. `hooks add <event> -- <argv…>` stores the argv list in the operator's config under the state root; the engine runs it as a detached child with a hand-off ticket naming a facts file, never with run text on argv ([SEC §2.1](14-security.spec.md)). A hook's failure is recorded and never changes the run or its exit code (contract C2). `hooks test <event>` runs it once against a fixture facts file. The engine ships no hook; a tracker integration is a separate plugin that registers one.

## 3. Behaviours

**CLI-B1 Check before spend.** Given a request, when `run --check` runs, then it returns `ok`, `needs` (questions with choices), `error` or `broken`, exits accordingly and creates nothing; the full start refuses in exactly the cases the check does.

**CLI-B2 Reserved verbs.** Given a request whose first word is a verb name (for example `update`), when an older shim passes it to `run`, then it is refused, never treated as workflow input.

**CLI-B3 Executors verb.** Given `executors --probe`, when it runs, then it lists each executor's capabilities, its CLI version, and each probe fact with its recorded state (`confirmed`, `refuted`, `not run`), and calls no model.

| Executor | `restricts_judge_tools` | Version | Facts not run |
|---|---|---|---|
| claude | true | from `claude --version` | P-CC-1 … P-CC-8 |
| agent-sdk | true | SDK package version plus its CLI's | P-AS-1 … P-AS-4 |
| messages-api | true (by construction) | client library version and API version header | none (contract tests) |
| antigravity | false | from `agy --version` | P-AG-1 … P-AG-9 |

**CLI-B4 Background-friendly.** Given a caller that starts `run` in the background, when the run pauses, then the process exits 3 so the caller learns of the pause by its exit, with no polling.

**CLI-B5 Facts are read-only.** Given a live run, when `facts` runs, then it reads the status document and the run log only, creates nothing and calls no model (contract C13), and its JSON carries `schema_version`.

**CLI-B6 One list of what waits on a person.** Given three paused threads under the state root (an approval, an escalation and, with its orchestration, a paused node), when `attention` runs, then it prints one item each, oldest first, with the thread, workflow, unit and item, pause kind, age, a one-line reason and the exact command that answers it; it reads the status documents and orchestration status documents only, calls no model and creates nothing (contract C13); `--all-roots` reads every state root in the machine index ([CST §2.1](34-central-run-stats.spec.md)) and `--json` carries `schema_version`.

## 4. Error conditions

| Condition | Exit |
|---|---|
| Unknown verb, workflow or option | 2 |
| Engine not installed (shim) | 127 |
| Unhandled exception after an engine-error record | 1 |

## 5. Design notes

- Exit codes rather than prose are the stable contract, so a skill or CI job can tell waiting from stopped from budget spent ([ADR-0015](../adr/0015-exit-codes-as-caller-contract.adr.md)).
- The `executors` verb makes the honest-maturity rule visible: a capability resting on an unrun probe is shown as projected.
- Tables of verbs, options and exit codes in the docs stay written by hand and are checked against the argument definitions and constants by drift tests: the verb words equal `VERBS`, every built long option is named here, in RST or in PRV, and the exit codes equal [CON §2.9](01-contracts.spec.md).

## 6. Acceptance criteria

- [ ] CLI-AC-1 Every read-only verb leaves the state root unchanged (hash test) and starts no process except the probes of `executors --probe`, which are read-only.
- [ ] CLI-AC-2 `run --check` and `run` agree on every refusal in a corpus of requests.
- [ ] CLI-AC-3 Verb words are reserved and refused as input.
- [ ] CLI-AC-4 Exit codes match [CON §2.9](01-contracts.spec.md) by a generated-table drift test.
- [ ] CLI-AC-5 `attention` lists every pause of a fixture state root exactly once, oldest first, each with a resume command that `resume` accepts, and leaves the state root unchanged.

## Open questions

None.

## References

