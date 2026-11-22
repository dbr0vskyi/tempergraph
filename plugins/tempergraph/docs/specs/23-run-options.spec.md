# Run options

## Purpose

The options that `run`, `resume` and `rerun` take: the generic setting options, the named options that are spellings of them, the task id and inputs, and how a request becomes a thread id when the workflow has no resolver. People, skills and CI depend on the exact option names; the settings they set are the catalog of [RST](80-run-settings-and-overrides.spec.md). Split from the engine CLI spec ([CLI](17-engine-cli.spec.md)) when the specs moved to temperspec's format.

## Behaviours

### ROP-B1 Generic setting options

WHEN `run`, `resume` or `rerun` is given `--set <key>=<value>` (repeatable), `--settings <file>` or `--profile <name>` (repeatable) THE engine CLI SHALL set those keys of the settings catalog on the `flag` and `profile` layers ([RST](80-run-settings-and-overrides.spec.md)), reading a settings file once and recording its keys as flags.

- GIVEN `--settings s.json` holding `{"steps.timeout_s": 900}` WHEN the run starts THEN the effective-settings record shows `steps.timeout_s` 900 from the `flag` layer
- GIVEN `--set steps.timeout_s=900 --profile slow` WHEN both set the key THEN the flag wins

### ROP-B2 Named options are spellings of `--set`

WHEN a named run option is given THE engine CLI SHALL set the catalog key it spells, exactly as `--set` would: `--executor` `steps.executor`, `--step-executor <step>=<name>` `<step>.executor`, `--judge-executor` `judges.executor`, `--model` `steps.model`, `--step-model <step>=<alias>` `<step>.model`, `--judge-model` `judges.model`, `--timeout` `steps.timeout_s`, `--judge-timeout` `judges.timeout_s`, `--idle` `steps.idle_s`, `--enforce-tools` `run.enforce_tools=true`, `--strict-permissions` `run.strict_permissions=true`, `--arm <switch>=<arm>` `<switch>.arm`, `--run-cost-cap` `run.run_cost_cap_usd`, `--daily-cap` `run.daily_cap_usd`, `--audit-rate` `run.audit_rate`, `--audit-executor` `run.audit_executor`, `--workspace auto|worktree|in_place` (and `--worktree`, `--in-place`) `run.workspace`, `--worktree-root`, `--worktree-base` and `--worktree-cleanup` `run.worktree.root`, `run.worktree.base` and `run.worktree.cleanup`, `--approve <step>` `<step>.approve=true`, and `--auto-reopen N` `run.auto_reopen`.

- GIVEN `run wf "x" --model small` and `run wf "x" --set steps.model=small` WHEN each is preflighted THEN both effective-settings records are the same
- GIVEN `--judge-executor antigravity` WHEN the run is preflighted THEN it is refused, because the judge executor must still declare `restricts_judge_tools`
- GIVEN `--auto-reopen 11` WHEN the options are checked THEN they are refused, because the range is 1 to 10
- GIVEN `--strict-permissions` and a step whose executor cannot enforce its declared tools WHEN the run is preflighted THEN it is refused ([EXI-B12](10-executor-interface.spec.md))
- GIVEN `--daily-cap 5` WHEN stable mode's self-improvement runs THEN its budget per day is 5 USD ([SIL §4](16-self-improvement.spec.md))

### ROP-B3 Tool grants

WHEN `run`, `resume` or `rerun` is given `--grant <unit>=<capability>[,…]` or `--allow-command <unit>=<prefix>` THE engine CLI SHALL add a person's grant for this run to `<unit>.tools.add` or `<unit>.commands.add`, or to `judge:<unit>.views.add` for a read-only view ([RST §2.8](80-run-settings-and-overrides.spec.md)).

- GIVEN `--grant code=shell` WHEN unit `code` starts THEN its session has the shell capability and the grant is recorded with the caller

### ROP-B4 Alias and label

WHEN `run` is given `--alias <name>` or `--label <text>` THE engine CLI SHALL record the run's alias and label ([DUR §2.2](09-durability-and-resume.spec.md)).

- GIVEN `--alias nightly` WHEN `status nightly` runs THEN it finds the thread

### ROP-B5 Caller options

WHEN a mutating verb is given `--caller person|agent|pipeline`, `--caller-app <name>`, `--as-agent` or `--relayed` THE engine CLI SHALL record the declared caller, which only lowers trust; `--as-agent` is `--caller agent`, and `--relayed` marks the decision as a person's carried by an agent ([PRV §2.3, §2.4](85-caller-provenance.spec.md)).

- GIVEN a marked agent session WHEN it runs `resume --caller person` THEN the command is refused
- GIVEN `--relayed` from an agent WHEN the host shows no person turn THEN the decision is not counted as the person's

### ROP-B6 Operator breakpoints

WHEN `run` or `resume` is given `--pause-before <unit>` THE engine SHALL pause before that unit starts ([FLX §2.5](74-flow-extensions.spec.md)).

- GIVEN `--pause-before code` WHEN the run reaches `code` THEN it pauses before the unit and exits 3
- GIVEN `--pause-before code.item1` WHEN the options are checked THEN they are refused `not_in_release`
- GIVEN `--pause-before nosuchunit` WHEN the options are checked THEN they are refused `breakpoint_unknown`

### ROP-B7 State root outside git

WHEN the global option `--state-root <dir>` is given before the verb outside a git repository THE engine CLI SHALL use that directory as the state root, and ignore it inside a git repository ([WSP §2.4](13-workspace-and-concurrency.spec.md)).

- GIVEN a folder outside git WHEN `tempergraph --state-root /tmp/s run wf "x"` runs THEN the thread is written under `/tmp/s`

### ROP-B8 Options set by the engine's own supervisors

WHEN `--schedule <fire_id>` or `--parent <orchestration>/<node>[/<item>]` is given THE engine CLI SHALL accept it only from the schedule tick with its fire token ([TCK §2.3](84-schedule-ticks-and-unattended-fires.spec.md)) or from the orchestration supervisor ([ORC §2.8](45-orchestration.spec.md)), and record it as `schedule` or `parent` with the run options.

- GIVEN `--schedule f1` without the fire token WHEN `run` starts THEN it is refused
- GIVEN the supervisor's `--parent o1/n2` WHEN the run's status is read THEN it shows `parent` `o1/n2`

### ROP-B9 Dry run

WHEN `run` is given `--dry-run` THE engine SHALL run every step and let self-improvement file nothing, recording `dry_run` on `run_started` and in the run's meta.

- GIVEN `--dry-run` WHEN the run's self-improvement child finds an issue THEN nothing is filed and the issue is in the run's records only

### ROP-B10 Task id and inputs

WHEN `run` is given `--task-id <id>` or `--input <k>=<v>` (repeatable) THE engine CLI SHALL use that task id, of 1 to 64 letters, digits, `.`, `_` or `-`, and pass each input to the workflow.

- GIVEN `--task-id T-12` WHEN the run starts THEN the thread's task id is `T-12`
- GIVEN `--task-id "a b"` WHEN the options are checked THEN they are refused

### ROP-B11 A request becomes a thread id without a resolver

WHEN a workflow has no resolver THE engine CLI SHALL resolve the request read-only by its declared input kind: `text` and `any` give `t-<first 10 hex of the SHA-256 of the whitespace-normalised request>`, `tracker_key` takes the key as the id, and `file` gives `f-<stem>-<6 hex of the path>`.

- GIVEN the request `fix  the bug` and later `fix the bug` WHEN each is resolved THEN both give the same `t-` id and find the same thread
- GIVEN an empty request WHEN it is resolved THEN the result is `needs` with the question `request`

### ROP-B12 Options are checked before spend

WHEN `run --check`, `run`, `resume` or `rerun` is given options THE engine CLI SHALL validate every option by the same rule before any spend ([RST §4](80-run-settings-and-overrides.spec.md)), and no typed text reaches a launch: an option value selects a constant or is a checked number ([SEC](14-security.spec.md)).

- GIVEN `--timeout abc` WHEN `run --check` runs THEN it refuses the option, and `run` refuses it in the same words

### ROP-B13 Self-improvement verb options

WHEN the self-improvement verbs are given THE engine CLI SHALL take these synopses ([JCL §2.6](50-judge-calibration.spec.md), [FBK §2.3, §2.4](41-feedback-and-judge-reliability.spec.md), [PRP §2.7](40-improvement-proposals.spec.md)): `evals score <workflow> <gate> [--executor <name>] [--repeat k] [--variants <kinds>|none] [--cap <usd>] [--level <risk level>] [--json]`, `evals bar [<workflow>] [--json]`, `evals run <workflow> --kind check|judge|step|workflow [--role regression|capability] [--trials k] [--executor <name>] [--cap <usd>] [--json]`, `evals report <workflow> [--json]`, `evals grade <result> --pass|--fail --reason <text> [--json]`, `evals harvest <workflow> <gate> [--json]`, `evals replay <workflow> [--executor <name>] [--cap <usd>] [--json]`, `evals label <workflow>/<gate>/<case> --criterion <id> --expected <status> --reason <text> [--reviewer <handle>] [--json]`, `labels queue|grades <workflow> [--json]`, `label <thread> <gate> [--criterion id] [--attempt n] --value agree|disagree`, `improve backlog [<workflow>]`, `improve propose <workflow> <cluster> [--patch <file> --rule <sentence>] [--executor <name>]`, `improve trial <proposal> [--target <metric>] [--cap <usd>] [--executor <name>]`, `improve aa <workflow> [--cap <usd>]`, `improve open <proposal>` and `improve show <proposal|trial>`, each with `--json` except `show`, which prints JSON.

- GIVEN `evals run wf --kind check` with a failed regression case WHEN it ends THEN it exits 1

## Acceptance criteria

- ROP-AC1 (ROP-B1, ROP-B2): For every named option, a run given the option and a run given the `--set` it spells have equal effective-settings records
- ROP-AC2 (ROP-B3): A grant given on `run`, `resume` or `rerun` reaches the named unit's session and is recorded with the caller
- ROP-AC3 (ROP-B4, ROP-B10): A run's alias, label and task id are found by `status` and `facts`
- ROP-AC4 (ROP-B5): `--caller person` from a marked agent session is refused, and a declared caller never raises trust above the classified one
- ROP-AC5 (ROP-B6): A breakpoint on a unit pauses before it; one on a map item is refused `not_in_release` and one on an unknown unit `breakpoint_unknown`
- ROP-AC6 (ROP-B7): `--state-root` outside git puts the thread under the given folder, and inside git changes nothing
- ROP-AC7 (ROP-B8): `--schedule` without its fire token is refused, and `--parent` is recorded and shown
- ROP-AC8 (ROP-B9): A dry run files no issue and records `dry_run` on `run_started`
- ROP-AC9 (ROP-B11): Two requests that differ only in whitespace resolve to the same thread id, and an empty request gives `needs`
- ROP-AC10 (ROP-B12): `run --check`, `run`, `resume` and `rerun` refuse the same invalid options in the same words, before any spend
- ROP-AC11 (ROP-B13): Every synopsis in ROP-B13 parses with the built CLI's argument definitions
