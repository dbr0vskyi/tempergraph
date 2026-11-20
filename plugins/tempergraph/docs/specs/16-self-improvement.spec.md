---
title: Self-improvement loop
type: component
status: ready-for-implementation
prefix: SIL
adrs: [0003, 0005, 0021, 0030, 0031, 0033, 0080, 0116, 0119]
---

# Self-improvement loop

## 1. Overview

A built-in workflow that reads every finished run's record, judges it with an independent judge, and files, comments on or only records a finding in the repository that owns the fault: the engine's or the workflow's. It runs as a detached child, is gated and judged like any workflow, and never pauses. The loop closes through people: an issue is evidence, not an order. This spec owns contract C14 (a measurement call never writes code). It is the first half of the loop: clusters of its findings become measured proposals in [PRP](40-improvement-proposals.spec.md), human ground truth becomes labels and judge grades in [FBK](41-feedback-and-judge-reliability.spec.md), its data needs are stated in [IMD](43-improvement-data.spec.md), and what it reads from the step and judge sessions themselves is [SRV](44-session-review.spec.md).

## 2. Contract

### 2.1 Records on every exit (both modes, no model call)

| Record | Holds | Published |
|---|---|---|
| Findings | Signal and step names, cause codes, counts, executor names | Yes, as metadata |
| Evidence | Request, outputs, scrubbed feedback | Never; local only |
| Ledger row | Names, counts, hashes, executor and CLI versions; no text | Never as text |
| Session digest | Per session: names, enums, counts and keyed digests from its activity journal and stream ([SRV §2.1](44-session-review.spec.md)) | Its causes, as findings metadata |

### 2.2 Lenses

| Lens | Question | Dev mode trigger | Stable mode trigger |
|---|---|---|---|
| Friction | Where did the process hurt, and whose fault? | Every flagged final exit | A `tool_access` pause or a tool grant; spent retries or a stop; an uncleared failed step; a gap escalation; repeated blockers; a retry burst; cost above the version's p90; a new version's first five runs; a person pushing back |
| Outcome | Did the result meet the workflow's good outcome? Read from the run's outcome record ([OUT §2.5](90-run-outcome.spec.md)); a second judge starts only when the outcome gate's judge did not run | Every final exit | A person pushing back; a pass at judge confidence ≤ 0.5; every 20th clean run |
| Cost | Where does money repeat? | Every 10th final exit of a version | Same |
| Session (process) | Did the sessions work as their prompts, lessons, skills and subagents intend? Digest causes on every exit; a model review only on a plan ([SRV §2.3](44-session-review.spec.md)) | `full` review of every final exit, within a per-run cap | Review only of the sessions and slices a signal names ([SRV §2.4](44-session-review.spec.md)); saturated causes read nothing |
| Quality (per gate) | Does each version score better on a fixed scorecard? | Scorecard reported for every gate | A gate's rows may file only while its judge binding is graded `reliable` ([FBK-B5](41-feedback-and-judge-reliability.spec.md)); other gates are reported only ([ADR-0021](../adr/0021-scope-of-planned-work.adr.md)) |

### 2.3 Fault sides

Cause codes come from run-log and session-digest names and numbers only ([SRV §2.2](44-session-review.spec.md)), each classed `fault`, `infra` or `designed`. A fault is attributed to `engine`, `workflow`, `executor:<name>` (new in tempergraph) when the cause is an executor behaviour (an unknown event or message shape, a tool name outside the catalog, a refused flag or option, an API error type the classifier does not list), or `host` when the host-speed preflight warned or timeouts are sorted `slow_host` ([OBS](15-observability-and-cost.spec.md)). Executor-side issues go to the engine's repository with an executor label; host findings are recorded only, never filed.

### 2.4 What a finding carries

| Item | Rule |
|---|---|
| Drafted remedy | A friction issue body carries a drafted remedy: the cause code's fixed remedy text and, where the fault is in a prompt or check, the file and the kind of change. A person decides; the loop never opens a pull request in the first release |
| Git facts | Outcome evidence includes the run branch's commits, changed paths and diff stat, so the outcome judge grades what landed, not what the step said |
| Retry burst | Three or more retries of one unit in one visit is cause `retry_burst`, with the blockers' criterion ids; a judge-sent-back retry also carries cause `judge_blocked:<criterion id>`, so repeats cluster by criterion ([PRP §2.2](40-improvement-proposals.spec.md)) |
| Blocked pause with an empty check | A pause on `BLOCKED:` whose check ran no command and read no file is a workflow fault (`blocked_without_check`), not a designed pause |
| Tool access and grants | A `tool_access` pause is a friction finding with cause `tool_access:<refusal class>` ([TSA §2.2](57-tool-surface-audit.spec.md)). Every tool grant and allowed command of the run ([RST §2.8](80-run-settings-and-overrides.spec.md)) is one entry of the ledger row's `grants[]`: unit, capability or prefix, the refusal class it answered, `via` (`cli`, `orchestration`, `profile`), whether a later attempt called it, and the unit's outcome after it. A grant that a passing attempt used is a workflow-side finding with cause `grant_missing`, its fixed remedy the declaration; a grant never called is recorded as `grant_unused` and not filed. Both cluster by (workflow, unit, capability), so the pattern rule files one issue for a grant given on many runs and machines ([PRP §2.2](40-improvement-proposals.spec.md)) |
| Agent rescues and supervision | Each `rescue` touch decided by an agent on its own ([SUP §2.1](86-supervision-metrics.spec.md), [PRV §2.4](85-caller-provenance.spec.md)) is a friction finding with cause `agent_decided:<pause cause>`, clustered by (workflow, unit, pause cause) across runs and machines; a cluster whose decisions were mostly `proceed` with no workspace change files a workflow issue whose remedy is a check or an environmental cause. The ledger row carries `supervision{}`, and the cost lens shows supervision cost as its own figure, never in run cost ([SCO](87-supervision-cost.spec.md)) |
| Session review | A kept review observation never files on its own: it is local, and adds `review:<category>` and `review_weight` to a model-free finding on the same unit and run that it corroborates ([SRV §2.8](44-session-review.spec.md), [ADR-0119](../adr/0119-review-observations-are-candidates-corroborated-before-they-file.adr.md)); release 1 does not file from reviews |
| Uncalibrated judge | An outcome finding whose judge has no calibration score for this gate ([LIF](18-lifecycle-and-evals.spec.md)) is recorded with state `uncalibrated` and not filed |

## 3. Behaviours

**SIL-B1 Detached and best effort.** Given a run that exits, when recording finishes, then the self-improvement child starts detached through a hand-off ticket; its failure never changes the parent's exit code.

**SIL-B2 De-duplication by cause.** Given a finding whose fingerprint (side, workflow, leading cause, step) matches an open issue, when filed, then a "seen again" comment is added instead of a new issue; a failed search is retried once, then files anyway and records why.

**SIL-B3 Pattern rule.** Given an outcome gap on the workflow side, when deciding to file, then at least three runs with three distinct requests in 30 days are required; one clear engine fault is enough.

**SIL-B4 Executor drift is visible.** Given runs on `antigravity` (or on a library executor after an SDK update) whose sessions show a tool name absent from the view catalog after a CLI update, when friction is judged, then the cause `unknown_tool_name` is attributed to `executor:antigravity` with the CLI version, and the workflow is not blamed.

**SIL-B5 Measurement writes nothing.** Given a cost-fix comparison between two workflow versions, when it runs, then it makes no model call, writes no file, ledger row or code, and its only writes are one issue comment and, after a regression, one reopen.

**SIL-B6 Dry run files nothing.** Given the operator's dry-run switch, when the child runs, then it shows what it would file and files nothing; every step of the parent still ran and spent.

**SIL-B7 Uncalibrated stays local.** Given an outcome gap from a judge that has no calibration score, when the filing rule runs, then the finding is recorded `uncalibrated` and no issue or comment is made; once a score exists, the next matching finding files normally.

## 4. Error conditions

| Condition | Result |
|---|---|
| Code host unreachable | Payload kept and redelivered by the next filing |
| Daily cap reached (stable mode, default $50) | Judges skipped; records still written |
| Evidence file or review evidence opened by filing code | Source test fails |

## 5. Design notes

- The loop is a workflow inside the engine so every run is analyzed without an optional install ([ADR-0003](../adr/0003-workflows-as-data.adr.md)).
- Its friction and outcome judges follow the same executor selection as any gate ([JDG](05-judge-and-verdict.spec.md)); by default they run on a mid-tier alias for 1800 s.
- Thresholds (audit 1 in 20, 30-day pattern window, confidence floor) are defaults with no data behind them; they are parameter records with provenance `default_no_data` ([IMD §2.5](43-improvement-data.spec.md)) and revisited with real runs.
- The pattern rule and the cost windows count runs from the shared store when one is reachable, so a pattern spread over several machines fires; otherwise they read the local ledger and say so ([IMD-B1](43-improvement-data.spec.md)).
- Release 1 layout: findings are `runs/<workflow>/<task>/findings.json` (one document per thread, each segment appends), the evidence file is `runs/<workflow>/<task>/evidence/record.json`, both owner-only ([LOS §2.1](33-local-observability-store.spec.md)); each exit writes a `finding_recorded` run-log record (causes, sides, and the lenses at a final exit). Cause codes, classes, sides and remedies are one table in `improve/causes.py`; thresholds are parameter records in `improve/params.py` ([IMD §2.5](43-improvement-data.spec.md)).
- Release 1 filing (`improve/filing.py`): an issue body opens with the hidden line `<!-- tempergraph:fp=<fingerprint> -->`, and SIL-B2 matches that exact line. Engine and `executor:<name>` findings go to the engine repository, workflow findings to the workflow's issue repository, host findings nowhere. A friction finding files only when its judge attributed it at or above `friction.file_confidence`. Payloads a code host refused wait in the state root's `filing-outbox.jsonl` ([LOS §2.1](33-local-observability-store.spec.md)) for the next filing. Executor causes carry the CLI version from the session's `agent_run` record, and a tool name the executor's view catalog does not map is `unknown_tool_name:<name>` (SIL-B4).
- Release 1 measurement (`improve/measure.py`) compares cost per run, repeat share, gate first-try pass rate and outcome mix of two versions; a quality drop above parameter `measure.quality_drop` (5 points) reopens the issue before its one comment.
- Release 1 loop child (`improve/child.py`): after a final exit whose friction lens fired on at least one fault, the run writes a hand-off ticket (ids, enums, the state root path and the fingerprints; never request text) to `improve/tickets/` under the home and starts `tempergraph.improve.child drain` through the detached child launcher ([SEC §2.2](14-security.spec.md)). The child claims each ticket, runs one friction judge session on the run's judge executor (alias `medium`, 1800 s) over the findings' metadata and the segment's record kinds, then decides and files each finding. It writes `loop_started`, `loop_judged`, `issue_filed` and `issue_commented` to the thread's `loop.jsonl`, and adds one `loop` ledger row with its cost. `TEMPERGRAPH_LOOP=inline|off` runs it in-process or not at all.
- The SIL-B5 comparison also runs, unasked, on the first 10 final exits after a merged proposal ([PRP-B9](40-improvement-proposals.spec.md)).

## 6. Acceptance criteria

- [ ] SIL-AC-1 Every exit writes findings, evidence and one ledger row, with no model call.
- [ ] SIL-AC-2 The canary test shows no request text in any issue, comment or ledger row.
- [ ] SIL-AC-3 A repeated cause produces one issue and comments, never a duplicate issue.
- [ ] SIL-AC-4 An executor-attributed cause is filed with the executor label and CLI version, never against the workflow.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Which exits are final? Assumed every exit that is not a pause (exit 0, 4 or 5); a re-opened thread has several, and filing still happens once per fingerprint (SIL-B2). | Engine owner | Not a pause |
| Is the loop a compiled built-in workflow? Release 1 runs it as a fixed engine program with one judged session per ticket, so it gets no gate of its own. The friction judge sees metadata only: the evidence file stays with the recorder (SIL §2.1). The outcome lens is judged only once JCL gives the outcome gate a calibration score, because until then SIL-B7 records the result `uncalibrated` whatever the judge says. | Engine owner | A fixed program; the friction judge on metadata; no outcome judge before calibration |
| Which fixed cost rules? Release 1 has six, each a finding per unit over 30 days of one version with at least 5 runs: `repeat_share` (retries ≥ 30% of the unit's cost), `retry_after_check` (retries after a failed deterministic check), `judge_over_step`, `expensive_unblocked` (a `large` step whose judge never blocked in the window), `recurring_blocker` (one criterion blocking on 3 or more runs), `unpriced_gate`. The saving assumes a lever removes at most half; under $10 a month is recorded, not filed. | Engine owner | These six |

## References

