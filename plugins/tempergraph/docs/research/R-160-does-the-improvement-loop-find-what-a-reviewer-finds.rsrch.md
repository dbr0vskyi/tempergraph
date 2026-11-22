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

## Conclusions

- The loop can see what goes wrong inside sessions (H1, H2, F2) at a low cost: 0.66 USD for 13 sessions at max effort. It cannot see faults that sit in the environment or in files a step wrote outside its view (H5, H6), and it does not explain causes it only counts (H3, H4).
- For it to "simply happen", four changes follow from the findings, each stated without any workflow:
  1. Review order by signal, not by age: sessions after a failed check, a trip back or an escalation are read first, the money cap is checked against the reported spend of the reviews so far, and no count cap drops a target that the money allows (F3).
  2. A cross-session merge: the same observation category on the same unit in several sessions of one run counts as corroboration for filing, as a model-free repeat does (F2, F4).
  3. A one-paragraph loop summary in the run's exit output and in `attention`, naming the top observations, so a person sees them without asking (F4).
  4. An environment lens: a check FAIL whose evidence is the same before and after the step's change is classed environmental and named as such in the finding (H1, H6), and a write outside the declared folders is a finding (H5).
- Each is a follow-up for the engine's self-improvement specs (SIL, SRV, PRP); none is built here.

## Open questions

- Should a dev review's budget be a share of the run's spend rather than a fixed figure? Until answered: the fixed cap, ordered by signal once change 1 is built. Owner: engine owner.
- Is one run enough to file a cross-session observation, or should it wait for a second run? Until answered: wait for a second run, as filing rules do today. Owner: engine owner.
