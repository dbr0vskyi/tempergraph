# Finalizer contract

## Purpose

A workflow's finalizer runs once after the last pass (and after an approval pause, when one is set) and calls no model (contract C1). It is a workflow's final stage, such as pushing the branch and opening a draft pull request, often the only thing a person reviews ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T51 to T53). [CON-B4](01-contracts.spec.md) declares the field `WorkflowSpec.finalizer`, a callable `(ctx: FinalizerContext) -> FinalizerResult`; this spec defines what the finalizer receives, what it may do, what it returns, and the rule that it can never fail a run that has passed every gate, since the run's exit code is a contract for callers ([ADR-0015](../adr/0015-exit-codes-as-caller-contract.adr.md)). It reuses the check's command machinery ([ADR-0075](../adr/0075-checks-get-a-context-and-an-engine-command-runner.adr.md)), so there is one guarded launch site for workflow commands. What to publish, where and how to word it are the workflow's choices. Workflow authors and callers reading exit codes depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### FIN-B6 What it receives

WHEN the finalizer is called THE engine SHALL give it `task_id`, `thread_id`, `workflow`, `branch`, `base` and `workdir` as in the run ([VAL-B8](76-step-values-and-template-keys.spec.md); `base` the workspace record's `base_branch` and `workdir` the run worktree in worktree mode, [WTR](82-worktree-mode.spec.md)); `artifacts`, `values` and `facts`, every pointer, value and check fact in final state by unit and item; `open_warnings`, the count, never the text, of warnings left unmet by every unit's final judgement; `degraded`, true when a gate's fallback was taken ([FLX-B9](74-flow-extensions.spec.md)); `run_options`, the options recorded at start it may read (`dry_run`, the resolved workspace `mode` and the workflow's resolved settings); `git` (`GitFacts`, [CHK](75-check-contract-and-command-runs.spec.md)); `resolve(text)` and `run(cmd, timeout_s)` as for checks, through the finalizer's own allow-list entries; and `scrub(text)` and `clip(text, n)`, the engine's scrubber ([SEC-B8](14-security.spec.md)) and a clip that never splits a character; and never the request text, a person's feedback, a step's final text, judge text or the evidence file, so the publish boundary holds by construction.

- GIVEN a finalizer context WHEN its fields are listed THEN none holds request, feedback, step or judge text

### FIN-B5 Nothing private reaches it

WHEN the finalizer builds its text from its context THE engine SHALL keep out of every argv, standard input and record of the finalizer run a canary planted in the request, the feedback, a step's final text or a judge's evidence ([SEC-B2](14-security.spec.md)).

- GIVEN a canary in the request, the feedback, a step's final text and a judge's evidence WHEN the finalizer runs THEN the canary appears nowhere it wrote

### FIN-B7 How its commands run

WHEN the finalizer runs a command THE engine SHALL find the program by path lookup, refusing one found only in the current directory; disable terminal credential prompts (`GIT_TERMINAL_PROMPT=0`, `GH_PROMPT_DISABLED=1` and the equivalent of each declared program) so a missing credential fails at once; pass a title or other text as one argv element after `scrub` and a body on standard input; limit each command to `timeout_s` (default 120 s) and the whole finalizer to 600 s; and answer a command outside the finalizer's allow-list entries with `CommandRefusal`, the finalizer deciding its outcome.

- GIVEN a remote that asks for a credential WHEN the finalizer pushes THEN no prompt is inherited and the push fails at once

### FIN-B8 What it returns

WHEN the finalizer returns THE engine SHALL take `outcome` (a slug from the workflow's declared `finalizer_outcomes`, such as `opened`, `reused`, `pushed` or `skipped`), `reason` (one scrubbed line of at most 200 characters, why for anything but the expected outcome), an optional `url` (the published item) and `manual_steps` (at most 5 command lines a person runs by hand when it could not publish); record a `finalize` event with outcome, reason, url, duration and step count; record outcome `invalid` with the value clipped into `reason` for an undeclared outcome, and outcome `error` with the exception type or `timed_out` when it raises or passes its limit; leave the run's exit code unchanged in every case, 0 for a finished run; and when `manual_steps` is not empty or the outcome is `error`, write one line to standard error and show the steps in the status document.

- GIVEN an undeclared outcome WHEN returned THEN the event records `invalid` and the run exits 0

### FIN-B1 Published

WHEN a run that passed every gate is finalized and the finalizer publishes THE engine SHALL exit 0 with the `finalize` event holding the outcome and the URL.

- GIVEN a finalizer that pushes and opens a draft WHEN it returns `opened` THEN the run exits 0, the event holds `opened` and the URL, and the self-improvement loop's pull-request label reads that URL later ([FBK](41-feedback-and-judge-reliability.spec.md) `pr_state`)

### FIN-B2 Cannot publish

WHEN the finalizer returns `skipped` with manual steps THE engine SHALL exit 0, write one line to standard error and list the steps in the status document.

- GIVEN no remote and `skipped` with reason `no origin` and two manual steps WHEN returned THEN the run exits 0 and the status document lists both steps

### FIN-B3 Raising is not failing

WHEN the finalizer raises THE engine SHALL exit 0, record `outcome: error` and the exception type, and leave the committed branch untouched.

- GIVEN a finalizer that raises WHEN it runs THEN the run exits 0 and the event records `error` and the exception type

### FIN-B9 Once, and on resume

WHEN the finalizer returns THE engine SHALL write `finalized` to state, run the finalizer again on a resume of a run that reached it with no `finalized` mark, so a finalizer must be safe to repeat (for example by reusing an open pull request for the branch), and never finalize a finished run twice.

- GIVEN a run killed during its finalizer WHEN resumed THEN the finalizer runs once more and then never again

### FIN-B4 Dry run

WHEN a run started with a dry-run setting is resumed without it THE finalizer SHALL read `run_options.dry_run` as true, since options are read as recorded at start.

- GIVEN a dry-run start and a plain resume WHEN the finalizer runs THEN `run_options.dry_run` is true

### FIN-B10 What is refused

WHEN a workflow with a finalizer is validated THE engine SHALL refuse a finalizer that imports an executor or the engine's model clients (a source scan of the package, contract C1) and an empty `finalizer_outcomes` while a finalizer is declared.

- GIVEN a declared finalizer and no `finalizer_outcomes` WHEN validated THEN it is refused

## Acceptance criteria

- FIN-AC1 (FIN-B8, FIN-B1, FIN-B2, FIN-B3): Every case of FIN-B8 holds in an offline test with a local bare remote
- FIN-AC2 (FIN-B5, FIN-B6): FIN-B5's canary appears in no argv, standard input or record of a finalizer run
- FIN-AC3 (FIN-B9, FIN-B4): A run killed during its finalizer and resumed runs the finalizer once more and then never again
- FIN-AC4 (FIN-B7, FIN-B10): No finalizer run inherits an interactive credential prompt (test with a remote that asks for one), and each refusal of FIN-B10 has a fixture
