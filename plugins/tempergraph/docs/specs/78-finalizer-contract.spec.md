---
title: Finalizer contract
type: component
status: review
prefix: FIN
adrs: [0015, 0075]
---

# Finalizer contract

## 1. Overview

A workflow's **finalizer** runs once after the last pass (and after an approval pause, when one is set) and calls no model (contract C1). For temperspec it is the final stage that pushes the branch and opens a draft pull request, the only thing a person reviews ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T51 to T53). [CON §2.1](01-contracts.spec.md) declares the field; this spec defines what the finalizer receives, what it may do, what it returns, and the rule that it can never fail a run that has passed every gate.

## 2. Contract

```python
def finalizer(ctx: FinalizerContext) -> FinalizerResult: ...   # WorkflowSpec.finalizer
```

### 2.1 What it receives

| Field or method | Meaning |
|---|---|
| `task_id`, `thread_id`, `workflow`, `branch`, `base`, `workdir` | As in the run ([VAL §2.3](76-step-values-and-template-keys.spec.md)) |
| `artifacts`, `values`, `facts` | Every artifact pointer, value and check fact in final state, by unit and item |
| `open_warnings` | The number of warnings left unmet by the final judgement of every unit; a count, never their text |
| `degraded` | True when a gate's `fallback` was taken ([FLX §2.4](74-flow-extensions.spec.md)) |
| `run_options` | The options recorded at start that a finalizer may read: `dry_run`, `in_place`, and the workflow's resolved settings |
| `git` | `GitFacts` ([CHK §2.1](75-check-contract-and-command-runs.spec.md)) |
| `resolve(text)`, `run(cmd, timeout_s)` | As for checks ([CHK §2.2, §2.3](75-check-contract-and-command-runs.spec.md)), through the finalizer's own allow-list entries |
| `scrub(text)`, `clip(text, n)` | The engine's scrubber ([SEC §2.3](14-security.spec.md)) and a clip that never splits a character |

It never receives the request text, a person's feedback, a step's final text, judge text or the evidence file; the publish boundary of [SEC §2.3](14-security.spec.md) holds by construction.

### 2.2 How its commands run

| Rule | Detail |
|---|---|
| Programs | Found by path lookup; a program found only in the current directory is refused |
| Prompts | Terminal credential prompts are disabled in the environment (`GIT_TERMINAL_PROMPT=0`, `GH_PROMPT_DISABLED=1` and the equivalent of each declared program), so a missing credential fails at once |
| Text arguments | A title or other text passes as one argv element after `scrub`; a body goes on standard input |
| Limit | `timeout_s` per command, default 120 s; the whole finalizer at most 600 s |

### 2.3 What it returns

| Field | Kind | Meaning |
|---|---|---|
| `outcome` | slug from the workflow's declared `finalizer_outcomes` | For temperspec: `opened`, `reused`, `pushed`, `skipped` |
| `reason` | one line, ≤ 200 chars, scrubbed | Why, for anything but the expected outcome |
| `url` | URL, optional | The published item, such as the pull request |
| `manual_steps` | list of ≤ 5 command lines | What a person runs by hand when it could not publish |

| Situation | Exit code of the run | Recorded |
|---|---|---|
| Returns any declared outcome | Unchanged by the finalizer (0 for a finished run) | `finalize` event: outcome, reason, url, duration, step count |
| Returns an undeclared outcome | Unchanged | Outcome `invalid`, the value clipped into `reason` |
| Raises, or passes its limit | Unchanged | Outcome `error`, the exception type or `timed_out` |

When `manual_steps` is not empty, or the outcome is `error`, one line goes to standard error and the status document shows the steps.

### 2.4 Once, and on resume

The engine writes `finalized` to state when the finalizer returns. A resume of a run that reached the finalizer but has no `finalized` mark runs it again, so a finalizer must be safe to repeat (temperspec reuses an open pull request for the branch). A finished run is never finalized twice.

## 3. Behaviours

**FIN-B1 Published.** Given a run that passed every gate, when the finalizer pushes and opens a draft, then the run exits 0, the `finalize` event holds `outcome: opened` and the URL, and the self-improvement loop's pull-request label reads that URL later ([FBK](41-feedback-and-judge-reliability.spec.md) `pr_state`).

**FIN-B2 Cannot publish.** Given no remote, when the finalizer returns `skipped` with reason `no origin` and two manual steps, then the run still exits 0, one line goes to standard error, and the status document lists both steps.

**FIN-B3 Raising is not failing.** Given a finalizer that raises, when it runs, then the run exits 0, the event records `outcome: error` and the exception type, and the committed branch is untouched by the engine.

**FIN-B4 Dry run.** Given a run started with a dry-run setting and resumed without it, when the finalizer runs, then `run_options.dry_run` is true, because options are read as recorded at start.

**FIN-B5 Nothing private reaches it.** Given a canary planted in the request, the feedback, a step's final text and a judge's evidence, when the finalizer builds its text from its context, then the canary cannot appear, because none of those is in the context ([SEC-B2](14-security.spec.md)).

## 4. Error conditions

| Condition | Result |
|---|---|
| A finalizer that imports an executor or the engine's model clients | Validation error (source-scan of the package, contract C1) |
| `finalizer_outcomes` empty while a finalizer is declared | Validation error |
| A command outside the finalizer's allow-list entries | `CommandRefusal`; the finalizer decides its outcome |

## 5. Design notes

- The run's exit code is a contract for callers ([ADR-0015](../adr/0015-exit-codes-as-caller-contract.adr.md)): a run that passed every gate has finished, whatever publishing does after. The work exists on a committed branch, and the manual steps say how to finish by hand.
- The finalizer reuses the check's command machinery ([ADR-0075](../adr/0075-checks-get-a-context-and-an-engine-command-runner.adr.md)) so there is one guarded launch site for workflow commands.
- What to publish, where, as a draft or not, and how to word it are the workflow's choices; the engine supplies context without private text, a scrubber, a guarded runner and a record.

## 6. Acceptance criteria

- [ ] FIN-AC-1 Every row of the §2.3 situation table holds in an offline test with a local bare remote.
- [ ] FIN-AC-2 FIN-B5's canary appears in no argv, standard input or record of a finalizer run.
- [ ] FIN-AC-3 A run killed during its finalizer and resumed runs the finalizer once more and then never again.
- [ ] FIN-AC-4 No finalizer run inherits an interactive credential prompt (test with a remote that asks for one).

## Open questions

None.

## References

