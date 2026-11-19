# R-050 Why runs fail, stall, repeat or overspend

## Problem statement

The owner asked for a mechanism, probably a CLI command, that audits a workflow and finds its issues before they cost a run. To aim it, this note answers one question: **what most often makes a run fail, get interrupted, retry, get stuck, or spend a lot of tokens or time?** It ranks the causes by their weight, and for each cause says whether it can be seen from the workflow definition alone (**static**), from the machine the run will use (**host**), or only from recorded runs (**history**). It also says which part of this design already owns a cure, so that the audit points at it instead of copying it.

The ranking feeds [AUD](../specs/55-workflow-audit.spec.md), [ARC](../specs/56-audit-rule-catalog.spec.md) and [TSA](../specs/57-tool-surface-audit.spec.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|


## Key findings

### How the ranking is made

Each cause family is weighed on four axes: share of **spend**, share of **person interventions**, share of **wall time** and the **count** of runs or attempts hit. Rank 1 is the family with the largest weight on the most axes.

| Rank | Cause family | Spend | Interventions | Wall time | Static | Host | History |
|---|---|---|---|---|---|---|---|
| C1 | Gate send-back loops | most of the 45% repeat share | 31 (spent budget) | part of the 34% | partly | no | yes |
| C2 | Environment and infrastructure | retries after checks that no retry fixes | 36 + 7 permission | part of the 34% | partly | yes | yes |
| C3 | Timeouts, stalls and hangs | ≥ $145 on 28 attempts; $2.5 to $10 per stalled plan attempt | (in infrastructure) | most of the 34% | yes | partly | yes |
| C4 | Tool access and permission friction | a wasted turn per refusal | 7 (permission) and stalls | some | yes | yes | yes |
| C5 | Pauses that add nothing | none directly | 10 (verification) and most budget pauses | 13% | partly | no | yes |
| C6 | Cost shape: heavy steps, heavy judges, wrong model | discovery + plan 61%; judges up to 39% of a run | none | some | partly | no | yes |
| C7 | Prompt and template defects | attempts lost to wrong text | some | some | yes | no | partly |
| C8 | Engine-side defects | lost writes, orphaned sessions | some | some | no | partly | yes |

### C1 Gate send-back loops (the largest)

| # | Finding | Confidence |
|---|---|---|
| F1.1 | Repeats (a step or judge running again) are **45% of spend**; by shape 51%, 48%, 44% and 34% across profiles. Half of repeat cost is a judge sending work back: 49% judge blocker, 16% a person, 12% back to an earlier step, 10% a failed check. | confirmed (earlier runs) |
| F1.2 | Splitting an oversized step is the strongest lever measured: first-pass yield rose from 29% to **62%** when the plan was written in two passes; the plan gate passed first time in 14 of 15 runs against 5 of 52 before. Cheaper judges moved repeats less. | confirmed |
| F1.3 | The expand step retried in 38 of the latest 40 runs; over 15 runs its judge cost at least $69.55, **79.4% of it repeats**. Reading sets failed three attempts in four recorded runs: missing line ranges, files the plan itself creates, a 58.6 KB file named whole. | supported (temperspec 3.7, 13) |
| F1.4 | A criterion a person had already ruled on, or whose own fix said "no change needed", kept blocking: **six attempts and two human retries** on one gap. | supported (temperspec 13, 14 C) |
| F1.5 | A request cut at 4,000 characters hid a criterion in its tail; the step failed **three times** on it. | supported (earlier runs) |
| F1.6 | A check and a judge disagreed on a figure (CRLF line endings counted twice), so the judge **failed every attempt**. | supported (temperspec 13) |
| F1.7 | Rule-like branching written as judge prose makes a verdict depend on how a long sentence is read. | supported (design reasoning, temperspec 14 C) |
| F1.8 | Retry counts mix "improved after feedback" with "the machine failed": in one window 15 retries were judge-driven and all later passed, about 11 were infrastructure or verification. | supported (earlier runs) |

**Detectable.** Statically: a step whose gate carries many blockers or whose step produces several large artifacts (F1.2), a blocker with `no_change_policy: retry` (F1.4), a blocker on an `unverified_system` (always UNVERIFIABLE), rule-like branching in a brief (already a WFM warning). From history only: which criterion leads the RETRY verdicts of a gate, first-pass yield per gate, RETRYs whose unmet blockers were all `no_change`, a rendered `⟨missing:…⟩` marker, and repeated identical check evidence.

### C2 Environment and infrastructure

| # | Finding | Confidence |
|---|---|---|
| F2.1 | **46 of 58** retries and escalations of the code step came after the deterministic check failed for lack of a usable interpreter or permission to run tests, which no retry fixes; each reran a full session. | confirmed (earlier runs) |
| F2.2 | Every worktree code step fell back to an interpreter with no test runner: the code gate ended at a person in **17 of 20** runs before the fix, 2 of 70 after. | confirmed |
| F2.3 | Infrastructure is the largest single reason a person was needed: **36 of 103**. | confirmed |
| F2.4 | In a repository with another toolchain the gate ran nothing ("not run: not declared"), the step was told not to build, and the run paused: about $1.5, two attempts, one pause. The loop then classed the pause as designed and filed nothing. | confirmed (earlier runs) |
| F2.5 | A saturated host (login shell 50 to 101 s): **8 of 13** step attempts timed out and a run took about 6 h 40 min; the loop filed a workflow issue for a host problem. | supported (earlier runs) |
| F2.6 | The CLI's 3-second stdin window: once in 41 logs a plan attempt was lost; later a code step failed four times in a row on a broken pipe and the run ended as an infrastructure failure. | supported |
| F2.7 | A worktree's tests imported the main checkout's stale engine (371 commits behind), so a suite could be false green or fail at import. | supported (earlier runs) |

**Detectable.** Host: whether each declared command's program resolves on this machine, whether the declared interpreter imports its test runner, whether the target repository documents commands the workflow neither declares nor resolves, host-speed probes. History: checks that ran nothing, check FAILs repeated with the same evidence inside one visit, infrastructure tries per run.

### C3 Timeouts, stalls and hangs

| # | Finding | Confidence |
|---|---|---|
| F3.1 | Attempts cut off or stopped and restarted are **34% of wall time**. | confirmed |
| F3.2 | **22 of 194** code attempts timed out across 82 threads; 28 code and release timeouts cost about **$145** (lower bound). | supported (earlier runs) |
| F3.3 | A stalled request is re-sent for about **52 minutes**, then ends as a success-typed "Request timed out" at $2.5 to $10 and 48 to 81 turns; **19 of 122** plan steps stalled. The cause was one write of the whole plan, the largest response of a run (87.6 KB). | confirmed |
| F3.4 | One global timeout fit nothing: a healthy step took 495 s against a 300 s rule; a judge was killed at 600 s after 47 tool calls; friction judges were cut at 180 s on 31 to 47 KB inputs; a judge timed out in 2 of 6 runs. | confirmed |
| F3.5 | No step declares an idle limit, so the built watchdog is off; at a 7,200 s limit a hung session can hold a run for **3 × 7,200 s = 6 hours** before the timeout exit. | supported |
| F3.6 | Timeouts are set "about the 90th percentile of the same work"; a few are reasoned, not measured. | supported (temperspec 13) |
| F3.7 | Of 19 profiled timeouts, 12 spent more than half their time in Bash; one session's 41 git calls took 67 s each on a loaded host: slow, not hung. | supported |

**Detectable.** Statically: a step or judge that relies on the engine default, an idle limit at or above its wall limit (does nothing), the worst-case hold time of a unit and of the whole order from `timeout_s × (retry_budget + 1)` plus infra tries. History: timeouts below the passing p90, attempts that end at their limit, tool share of timed-out attempts, request-timeout records and the largest response per step.

### C4 Tool access and permission friction

| # | Finding | Confidence |
|---|---|---|
| F4.1 | Of **190 refusals** on one machine (68 exits, two workflows): 43% shell used to read or search where file tools exist, 18% git after a directory change, 11% a path outside the worktree, 19% a real command the step needs, 9% an undeclared tool. **72% needed no new permission.** | supported (earlier runs) |
| F4.2 | "Change directory, then run": **58 of 59** git calls from a subfolder were refused; git with an explicit directory 0 of 121. | confirmed |
| F4.3 | **43 undeclared-tool cases** in 14 days (rate 0.75 per run): a task-stop tool in discovery and release; a shell in triage and expand, which do not declare one. | confirmed |
| F4.4 | The first live run stalled about 300 s on an interactive permission prompt, then the tracker tool was not granted and triage escalated in a loop. | supported (temperspec 13) |
| F4.5 | A judge called a tool a user-level plugin registered (the run monitor's status tool) once; the guard voided a complete verdict and the run paused at **$24.37**. The call happened once in four judge passes. | supported |
| F4.6 | A step declaring the newer tracker and wiki tool names got no judge view for them, so dependent criteria became UNVERIFIABLE and a person checked instead. | supported |
| F4.7 | A command rule written into the tool-name flag silently removed the shell: sessions ran with no shell at all. | supported (engine-built arguments now) |
| F4.8 | Skills and agents preloaded by bare name: a same-named skill of another installed plugin can load instead. | supported (temperspec 14 D) |
| F4.9 | Every loaded MCP server costs startup time and context and widens reach. | supported (earlier runs) |
| F4.10 | The delivery workflow needed about ten releases to reach few refusals by writing the same lines into six prompts; other workflows repeat the cycle. | supported |

**Detectable.** This family is the most visible statically: a prompt that names a tool or command its step does not declare (already a WFM warning), shell declared beside file tools with a prompt that reads files through it, `cd … &&` in commands or prompts, absolute or parent paths, an MCP tool the view catalog does not know, a step that declares a tool nothing asks for. Host: MCP servers and plugin tools a headless session would see, skill-name clashes across plugins. History: calls outside the grant, refusals by class, judge sessions that listed a tool outside their view set even when it was never called.

### C5 Pauses that add nothing

| # | Finding | Confidence |
|---|---|---|
| F5.1 | A person answering is **13% of wall time**; at first 2.4 asks per run, about 1 later. | confirmed |
| F5.2 | A spent retry budget is 31 of 103 interventions; real design decisions are about a fifth. | confirmed |
| F5.3 | Of 16 pauses an agent answered in one session, **13 were "verify and continue"** (a denied write, tests not run, a judge that failed to start, timeouts) and 3 were real decisions. | supported (earlier runs) |

**Detectable.** Statically: a gate with `retry_budget: 0` and `on_budget_spent: ask` (every RETRY asks a person), approval on most gates. History: pauses resolved by `proceed` with no feedback and no workspace change, interventions per run by kind.

### C6 Cost shape

| # | Finding | Confidence |
|---|---|---|
| F6.1 | Discovery and plan, with their judges, take **61%** of money; code 22%. | confirmed |
| F6.2 | Judges are large: **39%** of a release-page run; one verify judge ran 95 to 96 turns at about $2.1 to $2.2 and timed out in 2 of 6 runs. | confirmed |
| F6.3 | The code step's median peak context is 150 thousand tokens and **65%** of its cost is in turns above 200 thousand. | supported (temperspec 13) |
| F6.4 | The small model found 5 of 19 known findings of a cross-file review and none of the 10 that need another file; the large one found 18 of 19 at about 5.6 times the cost. | confirmed |
| F6.5 | Per-phase code cost 130% of one session on small plans; a long single session can time out. | supported |
| F6.6 | The cost lens's eight model-free rules (repeat share, retries after a deterministic check, a recurring blocker, judge against step cost, an expensive model on a step whose judge never blocked it, an unpriced gate) exist and run after every N exits. | supported (earlier runs) |

**Detectable.** Statically only weakly: every step and judge on `large`, a `small` judge whose references span several artifacts, no run cost cap. Mostly history, and the cost lens ([SIL](../specs/16-self-improvement.spec.md)) already owns the rules: the audit should show their result, not restate them.

### C7 Prompt and template defects

| # | Finding | Confidence |
|---|---|---|
| F7.1 | One bad field turned off every field: placeholders reached the model as literal text and nothing said so. | confirmed (now refused by validation) |
| F7.2 | A review found references to a skill, an agent, a prompt file and two tool names that do not exist; skills of 695 to 2,037 lines with one table cell of 8,291 characters. | supported (earlier runs) |
| F7.3 | A skill's text that says "ask the person" or "wait for review" stalls an unattended run. | supported (temperspec 13, design reasoning) |
| F7.4 | A brief that tells the judge to accept what the step says about a system the judge cannot read cancels independence. | supported (design reasoning) |

**Detectable.** Statically. The template grammar is validation's ([WFM](../specs/02-workflow-model.spec.md)); the text rules are prompt lint's ([LIF](../specs/18-lifecycle-and-evals.spec.md)). F7.2 to F7.4 are not yet in prompt lint's list.

### C8 Engine-side defects (outside a workflow audit)

| # | Finding | Confidence |
|---|---|---|
| F8.1 | A 5 s database busy timeout lost writes under 16 concurrent runs; append-mode ledger writes and concurrent log lines broke on Windows. | confirmed |
| F8.2 | An orphaned session rewrote files after the engine ended; a timeout that killed only the first process left its children. | supported |

These are fixed in the engine ([WSP](../specs/13-workspace-and-concurrency.spec.md), [EXI](../specs/10-executor-interface.spec.md)), not in a workflow. A workflow audit can only report the engine and executor versions against the tested range.

### A constraint from the loop's own history

| # | Finding | Confidence |
|---|---|---|
| N1 | **89 of 90** runs were flagged by the friction lens; in seven days 30 of 30 delivery runs were flagged (retry bursts 100%, undeclared tool 87%). "A signal every run raises ranks nothing." | confirmed |
| N2 | Fingerprinting by signal set filed about 21 nearly identical issues in 1.5 days; a failed dedup search read as "no issue" and filed 8 duplicates. | confirmed |
| N3 | The judge's confidence value carried almost no information (0.80 in 26% of 478 judgements; none below 0.60). | confirmed |

An audit that prints every possible finding repeats N1. It must rank, show a default view of high-confidence findings only, de-duplicate by rule and unit, and never file issues itself.

## Conclusions

1. The four families with the most recorded weight are **gate send-back loops (C1)**, **environment and infrastructure (C2)**, **timeouts and stalls (C3)** and **tool access (C4)**. Together they account for most of the repeat share of spend, 74 of 103 interventions (infrastructure, spent budget, permission) and most of the 34% of wall time lost to cut-off attempts.
2. **Tool access is the family most catchable before any run.** 72% of refusals needed no new permission, and their shapes (shell for reads, a directory change before a command, paths outside the workspace, undeclared tools) are visible in the definition.
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
| Do the cause shares hold outside one repository and one laptop? | Owner, once runs from another repository exist |

## References

