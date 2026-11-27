---
name: troubleshoot
description: Diagnose a tempergraph problem read-only and report ranked hypotheses with next actions for the person to run. Use when a run fails, hangs, pauses unexpectedly, costs more than expected, a start or resume is refused, a gate verdict or trip back confuses, or a workflow will not load, register or install.
allowed-tools: Read, Grep, Glob, Bash(git status:*), Bash(git log:*), Bash(git diff:*), Bash(ls:*), Bash(cat:*), Bash(grep:*), Bash(ps:*), Bash(tempergraph status:*), Bash(tempergraph facts:*), Bash(tempergraph events:*), Bash(tempergraph logs:*), Bash(tempergraph attention:*), Bash(tempergraph list:*), Bash(tempergraph graph:*), Bash(tempergraph validate:*), Bash(tempergraph audit:*), Bash(tempergraph workflows list:*), Bash(tempergraph executors:*), Bash(tempergraph worktree list:*), Bash(tempergraph outcome show:*), Bash(tempergraph upgrade-check:*), Bash(tempergraph install --check:*), Bash(tempergraph author show:*)
---

# Troubleshoot tempergraph

You gather evidence, rank hypotheses and tell the person what to run next. **You fix nothing.**

## Read-only, with one exception

- Never write, commit, push, check out, reset, install, migrate, delete, start, resume or stop anything. Never run `tempergraph upgrade-check` with `--stamp`.
- The one exception is not yours to prevent: when `tempergraph status` finds a thread whose runner was killed or timed out and left no exit, the engine records it (a `runner_lost` ledger row, findings and a hand-off ticket) and may start the improvement loop for it, once per thread; that loop spends. Say so in the report when `status` showed an orphaned thread.
- The only output is your report, plus one file if the person names it.
- A hypothesis that only a mutating action can confirm is described for the person to run. A read that no rule above allows is not run: name it in the report, with what it would show.
- Report environment variables by presence and shape only. Never print a secret, a token or a credential.
- If this engine refuses a verb as unknown, list it under "not investigated" as a read this engine does not offer yet.

## Procedure

1. **Restate** the problem in one sentence, and what working would look like.
2. **Gather**, scoped to the problem:
   - `tempergraph status` and `tempergraph facts <thread>` for the run's state, exit code, reason and next step (`status` records a lost runner once, see above); a thread is named `<workflow>/<task id>` or by its alias
   - `tempergraph status <thread> --detail [--unit <unit>]` for each unit's attempts, verdicts, blockers and cost, and `tempergraph attention` for what waits on a person
   - `tempergraph events <thread>` for the run log in order, and `tempergraph logs <thread>` for the list of its logs, then `tempergraph logs <thread> --kind check|raw|stderr|engine` for one of them; never with `--follow`
   - only when those do not answer: the run folder `.tempergraph/runs/<workflow>/<thread>/` (`run.jsonl`, one record per line, oldest first, and `sessions/<unit>.<attempt>.<kind>/`)
   - a held lock under `.tempergraph/locks/<workflow>/` means the thread is still running somewhere
   - `git status`, `git log` and `git diff` where the workflow changes code; `tempergraph worktree list` when it runs in a worktree
   - `tempergraph validate <workflow>` and `tempergraph audit <workflow> --format json` for the definition
3. **Read the one reference** the symptom names, not all of them:

| Symptom | Read |
|---|---|
| A step failed, timed out, hung, cost too much, or the run ended with exit 5 | [references/steps-and-infra.md](references/steps-and-infra.md) |
| A gate verdict, a retry, a trip back or a pause confuses | [references/judge-and-gate.md](references/judge-and-gate.md) |
| The self-improvement loop did nothing, or an expected issue did not appear | [references/self-improvement.md](references/self-improvement.md) |
| Install, a workflow that will not load, register, audit or stamp | [references/install-and-workflows.md](references/install-and-workflows.md) |
| A start or resume is refused (exit 2), state looks wrong, or test state leaked | [references/run-state-and-refusals.md](references/run-state-and-refusals.md) |

4. **Rank** the hypotheses. Each one carries the evidence for it, the evidence against it, and a confidence (high, medium, low).
5. **Recommend** actions for the person, cheapest and highest-signal first, each as the exact command they run.

## Exit codes

| Exit | Means |
|---|---|
| 0 | Finished |
| 1 | Internal error in the engine |
| 2 | Refused: usage or preflight; nothing was spent or created |
| 3 | Paused for a person |
| 4 | Stopped |
| 5 | Budget spent, or an infrastructure failure |
| 6 | An advisory verb found issues at the level asked |
| 127 | The engine is not installed; hand over to the install skill |

## Older records are data

Run logs outlive the engine that wrote them. A record missing a key was written by an older engine: read it as written, never as a defect.

## Report

- **Expected and actual**
- **Context gathered**: the reads you ran, in one line each
- **Hypotheses**, ranked, with evidence for and against and a confidence
- **Next actions** the person runs, cheapest first
- **Not investigated**, and the read that would settle it
