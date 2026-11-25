# R-160 Does the improvement loop find, on its own, what a reviewer of the same run finds?

## Problem statement

On 2026-11-22 the owner ran release 3's first task (R3-T1.1, cost cap reservations) through temperspec and asked that the extra reviews of that run also show whether self-improvement works: "so I and any user of it in future would not need such discussions — it simply would happen on its own." This note scores the loop's own output for that run against the list of defects the operating agent found by hand, and names what the loop must do differently to find them unaided.

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S1 | Run `temperspec/r3-t1-1` (in place, stopped at triage) and run `temperspec/r3-t1-1b` (worktree, 13.84 USD reported, stopped after the outcome gate sent it back) | Run logs | the state root's `runs/temperspec/<task>/run.jsonl` |
| S2 | The loop child of `r3-t1-1b`: one friction judge and 12 session reviews in dev mode, all at `loop_effort` `max` on `medium` (0.66 USD) | Loop log, review records | `loop.jsonl`, `tempergraph improve review show` |
| S3 | `tempergraph improve backlog temperspec` after both runs | Finding clusters | the state root |
| S4 | The hand-found list, written before the loop ran (thread "Build release three with temperspec") | Reviewer's notes | the run's pull request |
| S5 | The review planner and its budget check | Code | `plugins/tempergraph/engine/src/tempergraph/improve/review.py` (`plan`, `run`) |
| S6 | The loop records of eleven release 3 runs of the night of 2026-11-22 to 2026-11-23 (`r3-t2-1`, `r3-t2-1a`, `r3-t2-2`, `r3-t2-3`, `r3-t3-1`, `r3-t5-1`, `r3-t5-2`, `r3-t8-1` to `r3-t8-4`), read without starting any new review | Loop logs, review records, findings | each run's `loop.jsonl`, `findings.json`, `improve review show`, `improve backlog`, `attention` |
| S7 | The defects found by hand in those runs (temperspec backlog rows B22, B23, B24, B40 to B44 and the B19 family) | Reviewers' notes | `plugins/temperspec-tgraph/docs/plans/backlog.plan.md` and its history |
| S8 | The citation check | Code | `plugins/tempergraph/engine/src/tempergraph/improve/review.py` (`CATALOG`, `check`) |
| S9 | The batch of runs behind pull request #113 (2026-11-24/25), the defect its reviewer found in the specs those runs wrote, and what the loop filed for the same runs (#114, #117) | Pull request, issues | github.com/dbr0vskyi/tempergraph |
| S10 | The friction judge's input, the outcome lens and the reviewer's view | Code | `improve/child.py` (`prompt`), `improve/lenses.py` (`decide`), `improve/review.py` (`BRIEF`); specs [SIL-B10, SIL-B13](../specs/self-improvement.spec.md), [SRV-B17, SRV-B19](../specs/session-review.spec.md), [EVT-B21](../specs/run-events.spec.md) |
| S11 | Where a person's verdict enters the loop | Specs, code | [OUT-B18](../specs/run-outcome.spec.md), [FBK](../specs/feedback-and-judge-reliability.spec.md) open question on `pr_state`, `improve/causes.py` (`pushback`) |
| S12 | The proposal class check | Code, spec | `improve/proposals.py` (`classify`, `record`), [PRP-B14](../specs/improvement-proposals.spec.md) |

## Key findings

### F1 Of six hand-found defects, the loop found two, recorded two as bare causes, and missed two `confirmed`

| Hand-found defect | Loop result | How |
|---|---|---|
| H1 The code gate retried four times on an environment fault no code change could fix (about 2 USD) | Found | Review of `code.3.retry`: `wasted_turns`, "re-diagnosing an environment fault that needs a person to fix" (confidence 0.55); clusters `retries_spent`, `check_fail:code` |
| H2 Discovery ran 16 minutes and 4 USD for a behaviour that was already specified | Found | Review of `discovery.1.step`: `context_bloat` 362k tokens, first write at turn 135 (0.7); about 40 turns re-checking form by reading checker code (0.5) |
| H3 An in-place run denies every write of a headless step | Cause only | Cluster `escalation:tool_access` on triage, score 0, no explanation of the workspace mode |
| H4 The outcome gate made the run tag every old criterion of each spec it edited, which sent it back to plan | Cause only | Clusters `check_fail:outcome`, `outcome_unmet:*`, score 0; the sessions after the trip back were not reviewed (F3) |
| H5 The `CLAUDE.md` block that `prepare` writes names root folders this repository does not have | Missed | No signal: the operator's task text worked around it in `r3-t1-1b`; in `r3-t1-1` the triage step's first write went to the wrong folder, and that run's review did not flag it |
| H6 The engine's suite fails inside an engine session because `TEMPERGRAPH_SESSION_KEY` leaks into the tests | Missed | The code step found and fixed it itself; no review or cause names it |

### F2 The loop found three things the reviewer missed `confirmed`

- Every code session broke the command limits (pipes, `;` chains, `env` prefixes, `sleep`), and each refusal cost a turn: five sessions, confidence 0.45 to 0.7. The prompt or the allowed shapes are wrong for how the model works.
- Read-only steps (triage, discovery) called `Bash` although their prompt says there is no shell (0.8).
- Executor-side causes `unknown_tool_name:Monitor`, `ReadNotifications`, `TaskStop` and `ToolSearch`: step sessions launched from inside a host session saw the host's tools. That is ECC-B14 observed live, which is release 3 phase R3-T1.2.

### F3 The review budget ran out before the sessions that mattered most `confirmed`

The dev review lists its targets in run order and keeps the first 12 (`review.max_sessions.full`, in `plan` of S5), marking every later one `skipped: budget` before any review runs. Six targets were skipped that way: `code.5.judge`, `plan.3.step`, `plan.4.retry`, `plan.4.judge`, `code.6.step` and `code.6.judge`, so the trip back from the outcome gate (H4) and the judge that escalated were never read. The money cap of this run (3.46 USD, a quarter of its 13.84 USD) was never reached: the 12 reviews that ran cost 0.66 USD reported. The check in `run` that compares the spend with that cap prices the next review from the size of its view and, on a miss, goes on to the next target, so it can read a later session after skipping an earlier one.

### F4 Nothing reached a person or a proposal `confirmed`

Every loop result was `recorded` (`designed`, `below_floor`, `uncalibrated`). Each cluster has one run, so ranking ties at the same score across 14 clusters. Review observations stay local candidates until a model-free finding corroborates them (SRV), and the default autonomy `file` drafts no fix. A user who does not read `improve review show` sees none of F1 or F2.

### F5 The work after the trip back found two gaps between specs and code, not taken `supported`

The second code visit (commits after `2d8787a` on the run's branch `tg/temperspec/r3-t1-1b`, not merged) tagged old tests with criterion ids and, doing so, found that `attempt_start` records carry no timeout source although BUD-AC4 says every step and judge record carries it, and that the run log's `human` record lacks the touch classes and `wait_s` that OBS-B9 names (they are on the `intervention` ledger row, and `observe/rows.py` reads `human.wait_s`, which is never written). Its judge escalated on alignment, so the change was left on that branch. Both are open engine defects.

### F6 After the fixes, the same run's review reads every session and records repeats `supported`

The loop fixes (run `temperspec/loop-fixes`, SRV-B24 to SRV-B28, BUD-B16, SIL-B22, SIL-B23) were rerun over the sessions of `r3-t1-1b` with `tempergraph improve review`: all 18 sessions were read, the failed and later ones first, none skipped, for 0.80 USD at max effort. Three `review_repeat` findings reached `improve backlog` on their own: `instruction_ignored` on `code` and on `plan`, and `wasted_turns` on `code`. The sessions after the trip back were read this time but named its symptoms (context, rows marked one by one), not its cause (H4). H3, H5 and H6 stay out of sight of a session review. The rerun wrote into the thread's own state root although `--state-root` named another one.

### F7 Overnight, the loop read 81 sessions in five of eleven runs and missed most hand-found defects by not running `confirmed`

Across the eleven runs of S6 (about 131 USD of runs), the loop reviewed 81 sessions with none skipped by budget, in `r3-t2-1a`, `r3-t2-2`, `r3-t2-3`, `r3-t3-1` and `r3-t5-2`, for 3.47 USD reported (about 2.7% of the runs' spend, 0.49 to 0.95 USD a run against caps of 2.1 to 4.1 USD). In the other six it read nothing:

| Run | Loop | Why |
|---|---|---|
| `r3-t5-1`, `r3-t8-1`, `r3-t8-2`, `r3-t8-3` | Never started | Left paused at a gate, or the runner was killed after a timeout; the loop starts only on a final exit |
| `r3-t8-4` | Started, every review failed | All 16 targets (32 reviewer sessions, cost 0) ended with `429 usage_limit_reached`: four parallel runs had spent the account's five-hour allowance. `loop_summary` said `18 recorded, 0 filed` with an empty top list, and nothing said the reviews had failed |
| `r3-t2-1` | One target, skipped | Stopped at triage; the review cap was a quarter of 0.05 USD, below the price of one review |

Scored against S7 as F1 scores:

| Hand-found defect | Loop result |
|---|---|
| Compound shell commands refused (B24) | Found, kept in every reviewed run |
| A trip back to plan rewrote finished work (B23) | Found: `r3-t3-1`, `plan.3.step` "discarded the built state of phases 1-4" |
| The code judge of a 2,100-line change read one file and escalated (B44) | Raised, then dropped: `judge_unread` at 0.9 on `code.2.judge` of `r3-t5-2`, rated `unsupported` by the citation check (F8) |
| The outcome gate asked for every old criterion of an edited spec (B22) | Cause only: `check_fail:outcome`, `outcome_unmet:*` in `r3-t8-4` |
| An escaped pipe in a table cell broke the expand check (B40) | Cause only: `check_fail:expand`, `retry_same_path` |
| Judges paused on questions marked not blocking (B41) | Cause only: `gap_escalation`, `agent_decided:escalation` |
| A spec over the budget, caught only at the code gate (B42); ids moved by the split (B43) | Missed: `r3-t5-1` had no loop |
| The folders `prepare` writes into (B19 family) | Missed: no signal |

Two found and one raised of nine, against two and two of six in F1. The difference is in which runs got a loop, not in how well a review reads. The loop also kept, in several runs each, things no reviewer had listed: plan rows marked with one edit per row (30 to 44 edits a code session; ten failed edits in a row in `r3-t5-2`), rule files a prompt names left unopened, expand rows naming files never opened, code written before its tests in five phases of `r3-t5-2`, verification commands run two or three times, and judges grading MET from grep lines (`judge_shallow` kept 19 times).

The fixes of F6 held: no target was skipped by budget, the failed and later sessions were read first, and SRV-B26 recorded three `review_repeat` findings on its own (`instruction_ignored` on `code` and on `plan` in `r3-t3-1`, on `expand` in `r3-t2-3`). The loop summary reached `attention`. Nothing was filed, proposed or trialled, as SRV-B28 and the default autonomy `file` intend.

### F8 The citation check drops judge observations that a person confirmed `confirmed`

`check` (S8) keeps `judge_unread` and `judge_trusts_report` only when the judge read none of the changed files (`changed_read == 0`); the judge of `r3-t5-2` read one of many, so a correct observation at 0.9 was `unsupported`. `judge_shallow` allows only the remedies `brief` and `criterion`, so the same review's `judge_shallow` with remedy `judge_model` was dropped on its remedy class alone. All nine judge observations of `r3-t5-2` were dropped; in the other four runs 19 of 57 were kept.

### F9 A defect in what a workflow produced, found by its reviewer in minutes, is outside what the loop reads `confirmed`

In the runs of S9 a delivery workflow's spec-writing step wrote behaviour specs as a literal account of each task (what changed, which fixture, which unit of the workflow) instead of the general rule. The cause was in the workflow's own text: its spec standard never asked for a general rule, its step prompt pushed toward restating the task's criteria, and no criterion of its judge graded it. Every gate passed, so the runs were clean by every measure the loop has. For the same runs the loop filed process findings (a judge that passed without reading, a repeated check failure) and nothing about the specs.

Reading S10, nothing in the loop looks at the content of what a step wrote:

- The friction judge sees findings and record kinds only (`child.prompt`), never the evidence file.
- The outcome lens spends no session (SIL-B13): its candidates are the criteria the workflow's own outcome judge graded `UNMET` or `PARTIAL`. A defect that no criterion names cannot be a candidate.
- The session reviewer sees the step's prompt, assistant text clipped to 600 characters and one input summary per tool call, which for a write is the path only (EVT-B21); "other tool output [is] left out" (SRV-B17). It can see that a step did not follow its prompt (`instruction_ignored`, the dev-mode `conformance[]`), not that a prompt the step followed produced a poor artifact.
- The catalog (SRV-B19) has producer categories about process (misreading, ignoring, thrashing, wasted turns, bloat) and grader categories about reading (`judge_unread`, `judge_shallow`). None says "the output is below a standard" or "a standard the step was given is graded by no criterion".
- The prompt audit ([PRA](../specs/prompt-audit.spec.md)) checks names, references, tool names, consistency and sizes, not whether a prompt or a standard asks for the right thing.

So the loop measures a workflow against the workflow's own definition of good. When that definition has a hole, the loop has the same hole.

### F10 A person's verdict on the delivered change does not reach the loop `confirmed`

The signals that a `met` run was wrong are a person's ruling, rewind or rerun through the engine (`causes.py`, `pushback`), a person's `label <thread> outcome`, and a finalizer fact that the pull request was closed unmerged (OUT-B18). Even the last is not derived today: FBK's open question records that no run records the pull request it led to (S11). Review comments, requested changes and a person's follow-up commits on the run's pull request are read by nothing. The reviewer's finding on #113 was a textbook escape (a `met` run a later signal contradicts, [OUT-B19](../specs/run-outcome.spec.md)) and the loop had no way to see it.

### F11 A proposal cannot change the files a step reads besides its template `confirmed`

The class check (S12) compares the workflow before and after a patch for step template text, limits, model, declared tools, flow, judge brief and model, check code, criteria, the outcome file and lessons. A package also ships files its steps are told to read at run time: standards, rule files, skill bodies, reference documents. A patch to one of those has none of the classes, so `record` refuses it `no_change`. A fix of the kind F9 needed (a sentence in a standard) is out of the proposer's reach even with a cluster behind it; only the criterion half (a new criterion, class `criterion`) is reachable. Skill decomposition is visible only as use counts (`declared_unused`, `skill_not_used`, `subagent_misused`), never as whether the split itself is right.

## Conclusions

- The loop can see what goes wrong inside sessions (H1, H2, F2) at a low cost: 0.66 USD for 13 sessions at max effort. It cannot see faults that sit in the environment or in files a step wrote outside its view (H5, H6), and it does not explain causes it only counts (H3, H4).
- For it to "simply happen", four changes follow from the findings, each stated without any workflow:
  1. Review order by signal, not by age: sessions after a failed check, a trip back or an escalation are read first, the money cap is checked against the reported spend of the reviews so far, and no count cap drops a target that the money allows (F3).
  2. A cross-session merge: the same observation category on the same unit in several sessions of one run counts as corroboration for filing, as a model-free repeat does (F2, F4).
  3. A one-paragraph loop summary in the run's exit output and in `attention`, naming the top observations, so a person sees them without asking (F4).
  4. An environment lens: a check FAIL whose evidence is the same before and after the step's change is classed environmental and named as such in the finding (H1, H6), and a write outside the declared folders is a finding (H5).
- Each is a follow-up for the engine's self-improvement specs (SIL, SRV, PRP); none is built here.
- The loop judges how a run went, not what it made (F9). Its idea of good is the workflow's criteria, so a hole in them is a hole in the loop, and a proposal could not fill a hole in a standard file even if one were found (F11). Three general changes follow, in order of yield:
  5. (#123) Read the person's verdict on the delivered change: record the pull request a run led to, and read its review state, review comments and the person's follow-up commits as later outcome signals (an escape), kept as local evidence and harvested as a labelled case (F10). It costs no model and turns the cheapest reviewer there is, the person who merges, into input.
  6. (#124) An artifact lens: in dev mode and probation, and on an escape, an independent tool-less reader of the change a run delivered (the diff and the files written, scrubbed and datamarked) against the standards the package gives its steps, with two new categories, "output below a stated standard" and "a standard graded by no criterion". Like every review it files nothing alone (ADR-0119); an escape or a cross-run repeat corroborates it, and its remedy is a criterion (grader side) or a standard (producer side).
  7. (#125) Let proposals reach the files steps read: a package declares its standard and skill files, and a patch to one is classed as a producer change and trialled like a prompt (F11).
- Overnight (F7, F8), the loop's reach, not its reading, limited it: a run that never reaches a final exit gets no loop, a loop whose reviews all fail reports like one that found nothing, and the check drops the judge observations that matched the worst hand-found defect. The rows that follow are in the engine's [backlog](../plans/backlog.plan.md); what the reviews found about the workflow's steps is in the workflow's own backlog.

## Open questions

- May an artifact-lens observation that a person's review later confirms file on its own, without a model-free finding? Until answered: no; it corroborates the escape finding, which files by the pattern rule. Owner: owner.
- Should a dev review's budget be a share of the run's spend rather than a fixed figure? Until answered: the fixed cap, ordered by signal once change 1 is built. Owner: engine owner.
- Is one run enough to file a cross-session observation, or should it wait for a second run? Until answered: wait for a second run, as filing rules do today. Owner: engine owner. Overnight the same category on the same unit (`instruction_ignored` on `code`) was kept in five runs and filed nowhere, which is evidence for a cross-run count (engine backlog E5).
