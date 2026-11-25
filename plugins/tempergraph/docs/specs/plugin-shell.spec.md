# Plugin shell

## Purpose

The `tempergraph` plugin wraps the engine CLI in skills a person uses from a conversation. A skill drives the engine; it never decides a gate. The skills ship in the engine plugin and know no workflow: they read the catalog; workflow-specific agents, skills and rules ship with each workflow ([ADR-0003](../adr/0003-workflows-as-data.adr.md)). The live monitor is the separate `tempergraph-monitor` plugin, which reads the observer documents and read-only verbs only ([EVT](run-events.spec.md), [RDD](run-detail-document.spec.md), [monitor docs](../../../tempergraph-monitor/docs/specs/overview.spec.md)). The shell is a Claude Code plugin; an operator may also drive the CLI directly or from CI. People using the skills, and the supervision measures that read the plugin's host hooks, depend on what the skills and hooks do. Each skill is a core file plus references read on demand, so its always-loaded text stays small.

## Behaviours

### SHL-B5 The skills and what they never do

WHEN the plugin is installed THE plugin SHALL ship the run driver `tempergraph:run` (turn a request into CLI calls, start in the background, report outcomes by exit code, walk the person through each pause; never answer a pause, default a value the workflow asks for or edit run state), the orchestrator ([OSK](orchestrator-skill.spec.md)), the optional schedule skill ([TCK-B21, TCK-B22](schedule-ticks-and-unattended-fires.spec.md); never fire runs from Claude Code's own scheduled tasks, save a schedule the person did not confirm or schedule a tool grant), the project bootstrap `tempergraph:bootstrap` (the state-root ignore rule only; never stage, commit or delete), the install, update and upgrade skills ([LSK](lifecycle-skills.spec.md)), the authoring skill `tempergraph:author` ([AUT](workflow-authoring.spec.md), [AUT-B12, AUT-B15, AUT-B19, AUT-B24, AUT-B25](workflow-authoring.spec.md); never edit the engine or draw a diagram by model), the troubleshooter `tempergraph:troubleshoot` (read-only diagnosis with ranked hypotheses and next actions; never write, commit, install or run a mutating command) and the eval skill `tempergraph:evals` (never call a model from the runner, never grade, never label).

- GIVEN any shipped skill WHEN the structure test reads it THEN it has frontmatter, its links resolve and it names no shipped workflow
- GIVEN a backticked `tempergraph …` call in a skill WHEN the structure test reads it THEN it is a verb of the CLI with options the parser builds

### SHL-B1 Ask, never guess

WHEN the run driver prepares a start whose request lacks a value the workflow needs THE run driver SHALL ask the person, in at most four rounds through `run --check`, and never fill the value from an example.

- GIVEN a workflow that needs `ticket` and a request without it WHEN the run driver prepares the start THEN it asks the person for `ticket`

### SHL-B2 Pauses go to the person

WHEN a run exits 3 THE run driver SHALL show the payload and the decisions and resume only with the person's explicit decision, passing `--relayed` so the person turn backs it ([PRV-B14](caller-provenance.spec.md)), and never resume on its own.

- GIVEN a run that exits 3 WHEN the person has not answered THEN no `resume` is run

### SHL-B6 Exit codes guide the skills

WHEN a verb a skill ran exits 127, 2 or 5 after an infra failure THE skill SHALL send the person to the installer for 127, find the refusal's message and follow it for 2, and never offer `proceed` for 5 after an infra failure.

- GIVEN `run` exiting 127 WHEN the run driver reports it THEN it points to the installer

### SHL-B7 Run driver verbs

WHEN the run driver calls the engine THE run driver SHALL use only `list`, `graph`, `run --check`, `run`, `resume --relayed`, `wait`, `status`, `facts`, `outcome`, `config show`, `executors` and `worktree`.

- GIVEN the run driver's skill files WHEN scanned THEN they name no other verb

### SHL-B8 The ignore rule

WHEN the bootstrap skill runs THE bootstrap skill SHALL ask git (`check-ignore` on the state folder) whether an outer rule already ignores `.tempergraph/`, else append `/.tempergraph/` to the root `.gitignore` with the file's own line endings, leave a person's negation standing, and report tracked state files with the untrack command without running it; the state folder's own `.gitignore` does not count as the rule ([LOS-B4](local-observability-store.spec.md)).

- GIVEN a root `.gitignore` with CRLF line endings WHEN the rule is appended THEN the new line ends with CRLF
- GIVEN tracked files under `.tempergraph/` WHEN bootstrap runs THEN it prints `git rm --cached` for them and runs nothing

### SHL-B9 Authoring writes nothing before approval

WHEN the authoring skill leads a session THE authoring skill SHALL follow the entry paths, phases, verification search and revise mode of [AUT](workflow-authoring.spec.md), write the outcome first ([OUT](run-outcome.spec.md)), write nothing before the person approves the engine-drawn blueprint and the tables, check the result as [SCF](blueprint-and-scaffold.spec.md) says (including `audit --layer definition --layer host` and a first trial), and in upgrade mode hand over to the upgrade skill ([LSK-B13](lifecycle-skills.spec.md)).

- GIVEN a session before blueprint approval WHEN the package folder is read THEN nothing exists

### SHL-B3 Executor choice with consequences

WHEN an author chooses an executor for a step THE authoring skill SHALL state its consequences, read from `executors` and not from skill prose: `claude` reported cost, cost cap, turn cap and fallback, judge on `claude`; `agent-sdk` the same with API or cloud credentials only, judge on `agent-sdk`; `messages-api` estimated cost only, caps enforced by the engine, no skills, agents or subagents so the template must carry what the step needs, web tools only where the provider offers them, judge on `messages-api`; `antigravity` estimated cost only, effort only, judge on `claude` until P-AG-1 to P-AG-3 are confirmed.

- GIVEN an author choosing `antigravity` for a step WHEN the skill records it THEN it says the judge runs on `claude`, the cost is estimated and no cost cap or turn cap is available

### SHL-B4 Prefer a check

WHEN the authoring skill drafts criteria for a requirement that is a file, a git fact or a test result THE authoring skill SHALL propose a deterministic check, not a judged criterion.

- GIVEN "the tests pass" WHEN criteria are drafted THEN the criterion is verified by a check

### SHL-B10 Newer unit kinds where they fit

WHEN the interview points to model-free work, several perspectives or a vote, best-of-n, or input only a person has THE authoring skill SHALL offer a script, a council, a contest or an ask, and answer a request phrased in graph-runtime terms (`Command`, `Send`, `interrupt`) with its declared form ([R-060](../research/R-060-node-types-against-langgraph.rsrch.md), [ADR-0062](../adr/0062-new-node-kinds-keep-the-gated-unit.adr.md)).

- GIVEN "three reviewers vote" WHEN steps are drafted THEN the skill offers a council

### SHL-B11 Skills named by plugin path

WHEN a skill or agent is named THE shell SHALL name it by plugin path (`<plugin>:<skill>`), never by bare name, so a same-named user skill cannot shadow a workflow's.

- GIVEN a user skill named `review` WHEN a workflow names `wf-tgraph:review` THEN the workflow's skill is the one used

### SHL-B12 Troubleshooter stays read-only

WHEN the troubleshooter runs THE troubleshooter SHALL be granted, through its `allowed-tools`, only file read, search and glob and one `Bash(<prefix>:*)` rule per read (git status, log and diff; `ls`, `cat`, `grep`; `ps`; the engine's `status`, `facts`, `list`, `graph`, `validate`, `audit`, `workflows list`, `executors`, `worktree list`, `outcome show`, `upgrade-check`, `install --check`, `author show`), forbid `upgrade-check --stamp` in its text, keep one reference per symptom group (steps, timeouts and infra; judge and gate; self-improvement; install and workflow checks; run state and refused starts), and list a verb the engine refuses as unknown as a read not available.

- GIVEN the troubleshooter's frontmatter WHEN read THEN no rule grants a mutating command

### SHL-B13 Eval skill order

WHEN the eval skill runs THE eval skill SHALL run the free checks first (`evals run --kind check`, `evals bar`, `evals report`), state a cap before any live suite, and ask a person for every `needs_person` grade and for gold labels ([EVS](eval-suites.spec.md), [JCL](judge-calibration.spec.md)).

- GIVEN a live suite WHEN the skill would start it THEN it has stated the cap first

### SHL-B14 Host hooks write the supervision journal

WHEN Claude Code fires `SessionStart`, `UserPromptSubmit`, `PostToolUse` on `Bash`, `Stop`, `SubagentStop` or `SessionEnd` THE plugin's hooks in `plugins/tempergraph/hooks/hooks.json` SHALL run `tempergraph supervision hook <Event> >/dev/null 2>&1 || true` with a 2 s timeout, writing the supervision journal ([SCO-B10, SCO-B11](supervision-cost.spec.md)): person turns with matched decision words and never the text ([PRV-B15](caller-provenance.spec.md)), engine commands, usage numbers read from the transcript, and `supervision close` at `SessionEnd`.

- GIVEN a machine with no engine WHEN a hook fires THEN the host call goes on unchanged
- GIVEN a person's turn "proceed please" WHEN `UserPromptSubmit` fires THEN the journal holds the matched word and not the text

### SHL-B15 Hooks stay out of the engine's own sessions

WHEN a host hook fires inside an engine session (`TEMPERGRAPH_SESSION_KEY` set) or with `observe.supervision = off` THE hook SHALL do nothing, and no host hook SHALL block or change a tool call; these hooks are not the engine's run lifecycle hooks ([HOK](lifecycle-hooks.spec.md)).

- GIVEN a step session WHEN its `PostToolUse` fires THEN nothing is written to the journal

### SHL-B16 Integrations are separate plugins

WHEN a tracker integration (issue states, autonomy levels, rollout) is wanted THE engine SHALL leave it to a separate plugin that reads `facts` and registers lifecycle hooks ([HOK](lifecycle-hooks.spec.md)), shipping none itself.

- GIVEN the engine plugin WHEN its hooks registry is read THEN it holds no tracker hook

## Acceptance criteria

- SHL-AC1 (SHL-B5): No shell skill names a shipped workflow
- SHL-AC2 (SHL-B1, SHL-B2): A rubric scenario per skill covers ask-before-guess and never-answer-a-pause
- SHL-AC3 (SHL-B3): The authoring skill's executor phase shows each consequence of SHL-B3, read from `executors`, not from skill prose
- SHL-AC4 (SHL-B5, SHL-B7, SHL-B12): The structure test passes on every skill, the run driver names only its verbs, and the troubleshooter's grant holds no mutating command
- SHL-AC5 (SHL-B8): The ignore rule is added once with the file's line endings, and tracked state files are reported and not untracked
- SHL-AC6 (SHL-B14, SHL-B15): The hooks run with a 2 s timeout, never fail the host call, and write nothing inside an engine session or with supervision off
- SHL-AC7 (SHL-B4, SHL-B6, SHL-B9, SHL-B10, SHL-B11, SHL-B13, SHL-B16): A rubric scenario covers each skill rule these behaviours state

## Open questions

- Should an Antigravity-native shell (skills in `.agents/skills/`) ship too? Deferred: the engine CLI is enough for Antigravity users today. Owner: owner.
