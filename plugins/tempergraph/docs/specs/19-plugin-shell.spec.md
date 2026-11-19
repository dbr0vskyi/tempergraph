---
title: Plugin shell
type: component
status: review
prefix: SHL
adrs: [0003, 0016]
---

# Plugin shell

## 1. Overview

The `tempergraph` plugin wraps the engine CLI in skills a person uses from a conversation. **A skill drives the engine; it never decides a gate.** The skills ship in the engine plugin and know no workflow: they read the catalog. Workflow-specific agents, skills and rules ship with each workflow ([ADR-0003](../adr/0003-workflows-as-data.adr.md)). The live monitor is the separate `tempergraph-monitor` plugin and reads the status document only.

The shell is a Claude Code plugin. Running steps on another executor does not require the shell to run there; an operator may also drive the CLI directly or from CI, where the `agent-sdk` and `messages-api` executors need no interactive sign-in.

## 2. Contract

| Skill | Purpose | Never |
|---|---|---|
| Run driver | Turn a request into CLI calls, start in the background, report outcomes by exit code, walk the person through each pause | Answer a pause, default a value the workflow asks for, edit run state |
| Orchestrator | Plan a graph of runs with the person, start it after approval, sleep until a person is needed, walk them through each pause, report ([OSK](46-orchestrator-skill.spec.md)) | Answer a pause, start an orchestration's runs itself, poll |
| Project bootstrap | Add the state-root ignore rule to a repository; nothing workflow-shaped | Stage, commit or delete |
| Installer | Put the CLI on PATH and create the managed environment; hand over to `update`; check that the chosen executors are installed and have credentials (`executors --probe`); install the optional `agent-sdk` and `messages-api` extras into the managed environment when asked | Install a CLI or store a credential |
| Authoring | Lead a person from a process they run to a registered, tested, stamped workflow | Edit the engine; draw a diagram by model |
| Troubleshooter | Read-only diagnosis with ranked hypotheses and next actions | Write, commit, install, or run a mutating command |
| Eval | Run scenarios, record and compare scores, calibrate judges | Call a model from the runner |

### 2.1 Authoring phases

Intake → outcome → steps → criteria and judges → policies, **executors** and models → start and routing → blueprint approval → scaffold → verify (including `audit --layer definition --layer host`, each finding shown with its remedy for the person to accept, fix or ignore with a reason, [AUD](55-workflow-audit.spec.md)), register, stamp, calibrate. Nothing is written before the person approves the engine-drawn blueprint and the tables. The executor phase asks, per step, which executor runs it and where its judge runs, stating each consequence from the capability matrix.

## 3. Behaviours

**SHL-B1 Ask, never guess.** Given a workflow that needs `ticket` and a request without it, when the run driver prepares the start, then it asks the person (at most four rounds via `run --check`) and never fills the value from an example.

**SHL-B2 Pauses go to the person.** Given a run that exits 3, when the run driver reports it, then it shows the payload and the decisions, and resumes only with the person's explicit decision; with `--as-agent` it never resumes on its own.

**SHL-B3 Executor choice with consequences.** Given an author choosing `antigravity` for a step, when the authoring skill records it, then it states that the step's judge will run on `claude` until Antigravity's judge restriction is confirmed, that cost is estimated, not reported, and that a cost cap and turn cap are unavailable for that step.

| Choice for a step | Stated consequence |
|---|---|
| claude | reported cost; cost cap, turn cap, fallback available; judge on claude |
| agent-sdk | as claude; API or cloud credentials only; judge on agent-sdk |
| messages-api | estimated cost only; cost and turn caps enforced by the engine; no skills, agents or subagents, so the template must carry what the step needs; web tools only where the provider offers them; judge on messages-api |
| antigravity | estimated cost only; effort only; judge on claude until P-AG-1..3 confirmed |

**SHL-B4 Prefer a check.** Given a requirement that is a file, a git fact or a test result, when the authoring skill drafts criteria, then it proposes a deterministic check, not a judged criterion.

## 4. Error conditions

| Condition | Skill behaviour |
|---|---|
| Exit 127 | Send the person to the installer |
| Exit 2 | Find the refusal's message and follow it |
| Exit 5 after an infra failure | Never offer proceed |

## 5. Design notes

- The authoring surface of a workflow (agents, skills, rules) may need two forms, one per executor; that is a workflow decision ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)). `claude` and `agent-sdk` share one form.
- Skills and agents are always named by plugin path (`<plugin>:<skill>`), never by bare name, so a same-named user skill cannot shadow a workflow's.
- A tracker integration (issue states, autonomy levels, rollout) is a separate plugin that reads `facts` and registers lifecycle hooks ([CLI §2.2](17-engine-cli.spec.md)); the engine ships none.

## 6. Acceptance criteria

- [ ] SHL-AC-1 No shell skill names a shipped workflow.
- [ ] SHL-AC-2 A rubric scenario per skill covers ask-before-guess and never-answer-a-pause.
- [ ] SHL-AC-3 The authoring skill's executor phase shows each consequence in SHL-B3's table, read from `executors`, not from skill prose.

## Open questions

| Question | Owner |
|---|---|
| Should an Antigravity-native shell (skills in `.agents/skills/`) ship too? Deferred: the engine CLI is enough for Antigravity users today. | Owner |

## References

