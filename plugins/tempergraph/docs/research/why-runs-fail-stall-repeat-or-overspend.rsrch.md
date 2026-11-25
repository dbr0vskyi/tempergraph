# Why runs fail, stall, repeat or overspend

## Problem statement

The owner asked for a mechanism, probably a CLI command, that audits a workflow and finds its issues before they cost a run. To aim it, this note answers one question: **what most often makes a run fail, get interrupted, retry, get stuck, or spend a lot of tokens or time?** It ranks the causes by their weight, and for each cause says whether it can be seen from the workflow definition alone (**static**), from the machine the run will use (**host**), or only from recorded runs (**history**). It also says which part of this design already owns a cure, so that the audit points at it instead of copying it.

The ranking feeds [AUD](../specs/workflow-audit.spec.md), [ARC](../specs/audit-rule-catalog.spec.md) and [TSA](../specs/tool-surface-audit.spec.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Workflow model, executor interface, workspace, self-improvement and lifecycle specs | Design | [WFM](../specs/workflow-model.spec.md), [EXI](../specs/executor-interface.spec.md), [WSP](../specs/workspace-and-concurrency.spec.md), [SIL](../specs/self-improvement.spec.md), [LIF](../specs/lifecycle-and-evals.spec.md) |
| Prior art for auditing workflow definitions | Research note | [research `prior-art-for-workflow-audits`](prior-art-for-workflow-audits.rsrch.md) |

The ranking below is a ranking of *weight*: it says which causes an audit should look for first, not how often each occurs in a population of runs.

## Key findings

### How the ranking is made

Each cause family is weighed on four axes: share of **spend**, share of **person interventions**, share of **wall time** and the **count** of runs or attempts hit. Rank 1 is the family with the largest weight on the most axes.

| Rank | Cause family | Spend | Interventions | Wall time | Static | Host | History |
|---|---|---|---|---|---|---|---|
| C1 | Gate send-back loops | most of the repeat share | spent retry budgets | part of the time lost to cut-off attempts | partly | no | yes |
| C2 | Environment and infrastructure | retries after checks that no retry fixes | infrastructure and permission | part of the time lost to cut-off attempts | partly | yes | yes |
| C3 | Timeouts, stalls and hangs | whole attempts paid and lost at their limit | (in infrastructure) | most of the time lost to cut-off attempts | yes | partly | yes |
| C4 | Tool access and permission friction | a wasted turn per refusal | permission and stalls | some | yes | yes | yes |
| C5 | Pauses that add nothing | none directly | verification and most budget pauses | a person's answer time | partly | no | yes |
| C6 | Cost shape: heavy steps, heavy judges, wrong model | early reading and planning steps; large judges | none | some | partly | no | yes |
| C7 | Prompt and template defects | attempts lost to wrong text | some | some | yes | no | partly |
| C8 | Engine-side defects | lost writes, orphaned sessions | some | some | no | partly | yes |

### C1 Gate send-back loops (the largest)

| # | Finding | Confidence |
|---|---|---|
| F1.1 | Repeats (a step or judge running again) are a large share of spend in every shape of workflow. The largest cause of repeat cost is a judge sending work back on a blocker; a person's send-back, a trip back to an earlier step and a failed check follow. | inferred |
| F1.2 | Splitting an oversized step is the strongest lever: a plan written in two passes, each with its own gate, passes its gate first time far more often than one written in a single pass. Cheaper judges move repeats less. | inferred |
| F1.3 | A step that expands a plan into reading sets retries on the shape of its own output: missing line ranges, files the plan itself creates, a large file named whole. Most of its judge's cost is then repeats. | inferred |
| F1.4 | A criterion a person has already ruled on, or whose own fix says "no change needed", keeps blocking: every attempt and every human retry fails on the same gap. | inferred |
| F1.5 | A request cut at a character limit can hide a criterion in its tail; the step then fails on it every time. | inferred |
| F1.6 | When a check and a judge compute one figure differently (CRLF line endings counted twice, for example), the judge fails every attempt. | inferred |
| F1.7 | Rule-like branching written as judge prose makes a verdict depend on how a long sentence is read. | inferred (design reasoning) |
| F1.8 | Retry counts mix "improved after feedback" with "the machine failed": a judge-driven retry that later passes and an infrastructure retry count alike. | inferred |

**Detectable.** Statically: a step whose gate carries many blockers or whose step produces several large artifacts (F1.2), a blocker with `no_change_policy: retry` (F1.4), a blocker on an `unverified_system` (always UNVERIFIABLE), rule-like branching in a brief (already a WFM warning). From history only: which criterion leads the RETRY verdicts of a gate, first-pass yield per gate, RETRYs whose unmet blockers were all `no_change`, a rendered `⟨missing:…⟩` marker, and repeated identical check evidence.

### C2 Environment and infrastructure

| # | Finding | Confidence |
|---|---|---|
| F2.1 | Retries and escalations of a code step often follow a deterministic check that failed for lack of a usable interpreter or permission to run tests, which no retry fixes; each reruns a full session. | inferred |
| F2.2 | A code step in a worktree can fall back to an interpreter with no test runner; the code gate then ends at a person on every run until the interpreter is fixed. | inferred |
| F2.3 | Infrastructure is a leading reason a person is needed. | inferred |
| F2.4 | In a repository with another toolchain the gate runs nothing ("not run: not declared"), the step is told not to build, and the run pauses. The loop then classes the pause as designed and files nothing. | inferred |
| F2.5 | On a saturated host (a login shell that takes tens of seconds to start), most step attempts time out, a run takes hours, and the loop files a workflow issue for a host problem. | inferred |
| F2.6 | The CLI's 3-second stdin window can lose an attempt, and a broken pipe can fail a step several times in a row and end the run as an infrastructure failure. | inferred |
| F2.7 | A worktree's tests can import the main checkout's stale engine, so a suite can be false green or fail at import. | inferred |

**Detectable.** Host: whether each declared command's program resolves on this machine, whether the declared interpreter imports its test runner, whether the target repository documents commands the workflow neither declares nor resolves, host-speed probes. History: checks that ran nothing, check FAILs repeated with the same evidence inside one visit, infrastructure tries per run.

### C3 Timeouts, stalls and hangs

| # | Finding | Confidence |
|---|---|---|
| F3.1 | Attempts cut off or stopped and restarted take a large share of wall time. | inferred |
| F3.2 | A timed-out attempt is paid in full and yields nothing, so timeouts on long steps such as code and release are among the costliest failures. | inferred |
| F3.3 | A stalled request is re-sent for a long time, then ends as a success-typed "Request timed out" after many turns. A stall is most likely on the largest response of a run, such as one write of a whole plan. | inferred |
| F3.4 | One global timeout fits nothing: steps and judges differ in length by an order of magnitude, so one limit cuts healthy long work and leaves short work loosely bound. | inferred |
| F3.5 | A step that declares no idle limit leaves the watchdog off; a hung session then holds the run until its wall limit on every try: at a 7,200 s limit with two retries, **3 × 7,200 s = 6 hours** before the timeout exit. | inferred |
| F3.6 | A timeout fits best near the 90th percentile of the same work; one set by reasoning alone is a guess. | inferred |
| F3.7 | Many timeouts spend most of their time in shell calls: on a loaded host each call is slow, and the session is slow, not hung. | inferred |

**Detectable.** Statically: a step or judge that relies on the engine default, an idle limit at or above its wall limit (does nothing), the worst-case hold time of a unit and of the whole order from `timeout_s × (retry_budget + 1)` plus infra tries. History: timeouts below the passing p90, attempts that end at their limit, tool share of timed-out attempts, request-timeout records and the largest response per step.

### C4 Tool access and permission friction

| # | Finding | Confidence |
|---|---|---|
| F4.1 | Refusals fall into a few classes: the shell used to read or search where file tools exist, git after a directory change, a path outside the worktree, a real command the step needs, an undeclared tool. **Most need no new permission**: a permitted form exists. | inferred |
| F4.2 | "Change directory, then run" is refused almost every time, while the same git call with an explicit directory passes. | inferred |
| F4.3 | Steps call tools they do not declare: a task-stop tool in a discovery or release step, a shell in a step that declares none. | inferred |
| F4.4 | A headless run can stall on an interactive permission prompt, and a step denied a tool it needs (the issue tracker in triage, for example) escalates in a loop. | inferred |
| F4.5 | A judge can call a tool that a user-level plugin registered (a run monitor's status tool, for example); the guard then voids a complete verdict and the run pauses after the judge's whole cost is spent. | inferred |
| F4.6 | A step that declares tool names the view catalog does not know (a newer tracker or wiki tool) gets no judge view for them, so dependent criteria become UNVERIFIABLE and a person checks instead. | inferred |
| F4.7 | A command rule written into the tool-name flag silently removes the shell: the session runs with no shell at all. | inferred (the engine builds the arguments) |
| F4.8 | Skills and agents preloaded by bare name: a same-named skill of another installed plugin can load instead. | inferred |
| F4.9 | Every loaded MCP server costs startup time and context and widens reach. | inferred |
| F4.10 | A workflow that cures refusals by writing the same lines into each prompt takes many releases to get there, and every other workflow repeats the cycle. | inferred |

**Detectable.** This family is the most visible statically: a prompt that names a tool or command its step does not declare (already a WFM warning), shell declared beside file tools with a prompt that reads files through it, `cd … &&` in commands or prompts, absolute or parent paths, an MCP tool the view catalog does not know, a step that declares a tool nothing asks for. Host: MCP servers and plugin tools a headless session would see, skill-name clashes across plugins. History: calls outside the grant, refusals by class, judge sessions that listed a tool outside their view set even when it was never called.

### C5 Pauses that add nothing

| # | Finding | Confidence |
|---|---|---|
| F5.1 | A person answering takes a real share of wall time; the number of asks per run falls as a workflow matures. | inferred |
| F5.2 | A spent retry budget is a common reason for an intervention; real design decisions are a minority. | inferred |
| F5.3 | Most pauses an agent answers are "verify and continue" (a denied write, tests not run, a judge that failed to start, a timeout); few are real decisions. | inferred |

**Detectable.** Statically: a gate with `retry_budget: 0` and `on_budget_spent: ask` (every RETRY asks a person), approval on most gates. History: pauses resolved by `proceed` with no feedback and no workspace change, interventions per run by kind.

### C6 Cost shape

| # | Finding | Confidence |
|---|---|---|
| F6.1 | In a delivery workflow the steps that read and plan (discovery and plan, with their judges) take more money than the code step. | inferred |
| F6.2 | Judges are large: a judge that verifies by reading can run as many turns as the step it grades, cost as much and time out. | inferred |
| F6.3 | A long code session's cost concentrates in its late turns, when the context is largest. | inferred |
| F6.4 | A small model misses most findings of a cross-file review, above all those that need another file; a large one finds nearly all at several times the cost. | inferred |
| F6.5 | On small plans, coding per phase costs more than one session; a long single session can time out. | inferred |
| F6.6 | Cost shapes are caught by model-free rules over finished runs (repeat share, retries after a deterministic check, a recurring blocker, judge against step cost, an expensive model on a step whose judge never blocked it, an unpriced gate); the cost lens of SIL owns them. | supported (SIL) |

**Detectable.** Statically only weakly: every step and judge on `large`, a `small` judge whose references span several artifacts, no run cost cap. Mostly history, and the cost lens ([SIL](../specs/self-improvement.spec.md)) already owns the rules: the audit should show their result, not restate them.

### C7 Prompt and template defects

| # | Finding | Confidence |
|---|---|---|
| F7.1 | One bad field can turn off every field: placeholders reach the model as literal text and nothing says so. | inferred (validation refuses it) |
| F7.2 | Prompts and skills go stale and grow: they name skills, agents, prompt files and tools that do not exist, and run to thousands of lines with single table cells of thousands of characters. | inferred |
| F7.3 | A skill's text that says "ask the person" or "wait for review" stalls an unattended run. | inferred (design reasoning) |
| F7.4 | A brief that tells the judge to accept what the step says about a system the judge cannot read cancels independence. | supported (design reasoning) |

**Detectable.** Statically. The template grammar is validation's ([WFM](../specs/workflow-model.spec.md)); the text rules are prompt lint's ([LIF](../specs/lifecycle-and-evals.spec.md)). F7.2 to F7.4 are not yet in prompt lint's list.

### C8 Engine-side defects (outside a workflow audit)

| # | Finding | Confidence |
|---|---|---|
| F8.1 | A short database busy timeout loses writes under many concurrent runs; append-mode ledger writes and concurrent log lines break on Windows. | inferred |
| F8.2 | An orphaned session can rewrite files after the engine has ended; a timeout that kills only the first process leaves its children. | inferred |

These are fixed in the engine ([WSP](../specs/workspace-and-concurrency.spec.md), [EXI](../specs/executor-interface.spec.md)), not in a workflow. A workflow audit can only report the engine and executor versions against the tested range.

### A constraint on what an audit reports

| # | Finding | Confidence |
|---|---|---|
| N1 | A friction signal that nearly every run raises (a retry burst, an undeclared tool) flags every run. "A signal every run raises ranks nothing." | inferred |
| N2 | Fingerprinting by signal set files many nearly identical issues, and a failed de-duplication search read as "no issue" files duplicates. | inferred |
| N3 | A judge's own confidence value carries little information: it clusters at a few values and rarely falls low. | inferred |

An audit that prints every possible finding repeats N1. It must rank, show a default view of high-confidence findings only, de-duplicate by rule and unit, and never file issues itself.

## Conclusions

1. The four families with the most weight are **gate send-back loops (C1)**, **environment and infrastructure (C2)**, **timeouts and stalls (C3)** and **tool access (C4)**. Together they account for most repeat spend, most interventions (infrastructure, spent budget, permission) and most of the wall time lost to cut-off attempts.
2. **Tool access is the family most catchable before any run.** Most refusals need no new permission, and their shapes (shell for reads, a directory change before a command, paths outside the workspace, undeclared tools) are visible in the definition.
3. **Environment causes need the host, not the definition.** No reading of the workflow tells whether its test runner is importable on this machine or whether the target repository's toolchain is covered.
4. **Loop causes need history.** The static view can flag shapes known to loop (an oversized step, a `no_change` blocker set to retry), but which criterion actually drives repeats is only in the judgements.
5. **Timeouts sit across all three.** The definition gives worst-case hold time; history gives the p90 the limits should follow; the host gives the slow-host warning.
6. **Several cures already have owners** (validation, prompt lint, the readiness report, judge calibration, the cost lens, the friction lens). The audit adds value by joining them per workflow and by owning only the rules no one owns: host checks, timeout fit, hold-time exposure, tool surface comparison and loop drivers from history.
7. The audit must be **quiet by default** (N1 to N3): a fixed rule catalog, a confidence per rule, a minimum sample per history rule, and no filing.

## Open questions

| Question | Owner |
|---|---|
| What share of refusals on tempergraph runs needs no new permission, with the tools block and the prompt check in place? | First runs of a tempergraph workflow |
| Are hung calls rare enough among timeouts that the idle-limit rules should stay warnings? | First runs |
| Does the ranking of cause families hold on runs across several repositories and machines? | Owner, once runs from several repositories exist |

## References

[research `prior-art-for-workflow-audits`](prior-art-for-workflow-audits.rsrch.md)
