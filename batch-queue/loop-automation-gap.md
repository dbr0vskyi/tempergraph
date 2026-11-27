# What the loop saw of one night of operator touches, and what would make it report and solve them (temporary; becomes issues)

Owner's direction of 2026-11-27: the engine exists to raise automation, not to be babysat. The loop must notice what a person had to do and report it, and an analysis mechanism must take a reported item to a proposed solution. This file measures the night of 2026-11-26 to 27 on threads `temperspec/i204`, `i197a`, `i196` and `i206` (run records under `.tempergraph/runs/temperspec/<id>/`, the ledger at `.tempergraph/ledger.jsonl`) and stages a design. The design is engine-general: it names no workflow.

## Part 1: what was recorded

Facts that hold for all seven touches:

- Every run was started with `--dry-run` and the package declares autonomy `record`. At `record` the child writes `loop_result` with op `recorded` and reason `autonomy_record` for every finding (`improve/child.py`), so no decision reason and no `would_file` entry exists anywhere. The "would file?" column below is the rule of `filing.decide` applied by hand to the recorded answers.
- A loop child ran only for `i204` (three times, at the three false `stopped` exits) and `i197a` (once). `i196` and `i206` have no final exit yet, so none of their findings has been judged (SIL-B9, #170).
- The ledger holds 13 `intervention` rows for the four threads. Each has the decision, the pause kind, the pause reason (`cause`), `wait_s`, the caller and the touch class. None has `operator_reason` (0 of 13: `--reason` was never passed and nothing asks for it). None has the item, the failing criterion ids or a flag that the decision overrode a FAIL. `feedback` is `true` on all 13; the evidence file's feedback list is empty in all four threads, and by design no text reaches the loop (SIL-B38).
- The run was started and answered by the same agent session, so every `agent_decided:<pause kind>` finding is class `designed` (FRC-B6) and can never file. The rule that turns agent rescues into a workflow issue (SIL-B15, SUP-B7) needs another agent to answer.
- The answer facts (`improve/pause_facts.py`) reach the friction judge's prompt as a hint for attribution. They are not a signal of their own.
- A `check` record holds `result`, `environmental` and 200 characters of evidence. The failing criterion ids that the check returned (CHK-B14 `findings[]`) are not on it, so the cause is `check_fail:<unit>` and nothing finer.

| # | Touch | Recorded as | Would file with filing on? | Names the real cause? | What was missing |
|---|---|---|---|---|---|
| 1 | `i204` `read_gap.U1`: judge gap, answered `proceed` | pause `unresolved_gap`; `gap_escalation` (1 run, attributed 0.7), `judge_blocked:ts-rdg-answers` (6 runs), `agent_decided:escalation` (designed); kept review categories `judge_unread`, `judge_shallow` | `gap_escalation` no (`below_count`); `judge_blocked:ts-rdg-answers` yes by the count | No. The remedy says the step misses the criterion; the judge's reading was cut | That `proceed` answered a gap; the item; which tool call cut the reading; review observations never file alone (SIL-B16) |
| 2 | `i204`: the answer ended the thread `stopped`, three times | three segments with exit 4, 0 sessions, 0 cost; finding `agent_decided:escalation` only; ledger rows `steer` / `retry` on cause `stopped` | No (designed; the friction lens was off at 2 of 3 exits) | No | A cause for "a decision other than stop produced no session and the same or a stopped state"; the loop also spent 40 review sessions re-reading the same sessions at the false exits |
| 3 | `i197a` `code`: pause `environmental`, answered `proceed` | check FAIL with `environmental: true`; `environmental` (class infra, side host, recorded only); the friction judge gave no answer for it; `agent_decided:escalation` (designed) | No | No. The command chosen fails the same at the base; that is a plan or prompt fault, recorded as the host's | That a person proceeded over it; the command prefix; a count of the same override per unit |
| 4 | `i206` `phase` item `p6`: check FAIL on `ts-phs-proof`, answered `proceed` | pause `blocked`; `blocked` (designed), `check_fail:phase`, `retry_same_path` | Not judged yet. At a final exit: a "seen again" comment on loop issue #117 (`check_fail:phase`) | No. Symptom only, at unit level | The criterion id, the item, the override, the kind of file the criterion was applied to |
| 5 | `i206` `code`: loop budget spent, answered `back:plan` | pause `budget` / `loop_budget`; `loop_budget_spent`, `retries_spent`, `check_fail:code`; the judgement holds `claim: plan` | Not judged yet. `loop_budget_spent` would file by the count or at confidence 0.75 | Half. It names the budget; the recorded upstream claim and the person's `back:plan` that confirmed it are not used | A cause that joins the claim with the confirming decision; touches 4 and 5 share one root and would be two issues |
| 6 | `i196` `code`: suite killed at the 1800 s limit, `retry`, then `proceed` | pauses `tool_access` (one refused `Read`) then `blocked`; `tool_access:unclassified`, `check_fail:code`, `blocked_without_check`; `self_check` durations 1800.6 to 1801.0 s; one finished run of the same command at 1664.6 s; the killed runs have no row in `command_runs.jsonl` | Not judged yet. All three causes are workflow faults and could file | No, and two are wrong: "declare the tool" and "add a check" | A record that a command was ended at its limit, with the limit and the earlier duration; `retry` followed by the same failure; the override; the isolation test's failure beside a live run is in output text only (#161) |
| 7 | `i206` `phase` item `p6`: pause `guard:outside_call:Bash`, answered `retry` | judgement `guard: discarded`; `guard:discarded` and `guard:outside_call:Bash` (side engine); the session's tool list holds the tool name | Not judged yet. Would file to the engine's repository at confidence 0.75 | Partly. The tool is named; the refused call and why the judge made it are not | The command prefix on the pause and the finding; that an unchanged `retry` passed; whether the judge's tools or its brief caused the call |

Summary: 0 of 7 filed, 0 of 7 would name the real cause, 2 of 7 would file something misleading (touch 6, and touch 4 as a comment on a unit-level issue). Time to answer was recorded: 51 to 1784 s per touch.

## Part 2 (a): noticing and reporting

| Signal | Today | New | Why it is not noise |
|---|---|---|---|
| Operator-touch record per pause | Ledger `intervention` row: decision, pause kind, cause, `wait_s`, caller, touch class, optional `operator_reason` | Add the item and `answered{}`: the last check result, failing criterion ids, judge blockers, `environmental`, the judgement's `claim`, the guard word | A row exists only when someone answered; ids and enums only |
| A person or agent answered `proceed` over a failing check, an environmental FAIL, a gap or a spent budget | Only a hint in the friction judge's prompt | Cause `answer_overrode:<kind>` on the unit, with `criteria[]` and counts | Event-based, not a rate per run; one finding per unit and kind, the criteria listed inside, so one gate's criteria make one issue; files by the pattern rule without the friction judge (as SIL-B34), because the answer is the evidence |
| `back:<unit>` that matches the judge's upstream claim | Claim recorded, unused | Cause `upstream_confirmed:<unit>` on the claimed unit | Needs both the claim and the decision |
| `retry` with the workspace unchanged that then passes | Facts in `pause_facts`, hint only | Cause `retry_passed_unchanged:<pause reason>` | Blames the gate side, once per unit and reason |
| `retry` followed by the same pause | Not derived | Cause `retry_same_failure` | Counts decisions, not sessions |
| A resume that made no progress | Not derived | Cause `resume_no_progress`, side engine | Zero sessions and zero cost after a decision is never designed |
| A command ended at its limit | Not recorded | A `command_runs` row with `timed_out`, the limit and the last finished duration of the same key; cause `command_limit:<prefix>`; a warning before the run when the last duration is over 80 percent of the limit | One per command key per thread |
| A pause whose payload lacks the facts to answer it | Not derived | Cause `pause_without_facts:<reason>`, side engine, when the payload has no failing id, no blocker, no command prefix and no limit fact | Model-free, fixed per pause reason |
| The operator's reason | `--reason` enum, optional, never given | The resume line prints it; an agent caller must pass it; counted per finding | One of six words |

The class rule of FRC-B6 stays for `agent_decided`. The new causes are about the gate that was overridden, not about who supervised, so they are class `fault` whoever answered. Duplicates of issues a person filed are #196's subject; fixed-rate detectors (`context_bloat`, `idle_burn` in 18 runs) are not touched here.

## Part 2 (b): analysis, from a reported item to a proposed solution

What exists (`improve/proposals.py`, `autonomy.py`, `trials.py`, `suites.py`, `harvest.py`): clusters and a ranked backlog; a proposer session that edits package files in its own worktree on branch `improve/<id>`; the engine's classification of the change from the parsed workflow before and after; refusals (both sides at once, request literals, outside the package, `weakening` from the proposer, PRP-B2); an independent judge with three criteria; paired trials on `evals/cases.json`; a draft pull request and its state read back; model-free check suites over `evals/checks`; judge replay on kept cases.

Why it has never run (the state root has no `improve/proposals` or `improve/trials` folder):

1. The only package in use declares autonomy `record`; `autonomy.act` also needs stable mode, no `--dry-run` and a package root.
2. An engine-side cluster is refused (`engine_side`, PRP-B10). Touches 2, 6 and 7 are engine-side.
3. The proposer is given a cause code, a unit, counts and review notes. It is not given the failing criterion, the check's source, the answers or the evidence, so for `check_fail:phase` it cannot know what to change.
4. The fixes this night needed narrow a check (touches 1, 4, 6). A proposer may not weaken a gate, so the class the operator handled most is the class the proposer must refuse.
5. A trial needs reviewed cases (the package has 2), a judge graded `reliable` for a judged target (PRP-B20; live checks #41 are blocked) and whole runs per arm. Nothing validates a check change in seconds.

The mechanism, as a level `analyze` between `file` and `propose`:

- Inputs: the finding with its `answered{}` facts and reasons; the source it points at, resolved by the engine from the package (the check's module and callable, the criterion's text and check method, the prompt template, the judge brief, or for the engine side the spec behaviour ids named by the cause); the history of the fingerprint (runs, units, decisions, earlier proposals); local evidence (check output, the recorded check ticket, session digests), read on the machine and never published.
- Session: one read-only session on the loop's model with a fixed reply: a root-cause class (`check_scope`, `check_wrong`, `prompt_rule`, `plan_rule`, `environment`, `limit`, `tool_surface`, `engine_defect`, `request`), one to three candidates (side, files, kind of change, size), and for each a test that fails before and passes after. An independent judge grades it: names the source place, states a general rule, the test would fail today.
- Cheap validation, in this order: (1) check replay: run the candidate's check over the recorded check tickets of the cluster (the overridden attempts must flip, a sample of recorded PASS and true FAIL attempts must not), model-free; (2) the step or judge suites of `suites.py` and `harvest.replay` for a prompt or brief change; (3) a paired trial only for a flow change.
- Output: a small workflow-side change whose replay is green opens a draft pull request through `open_pr`; a narrowing of a check opens it as `author=person` material, labelled `weakens-gate`, for a person to accept; an engine-side or larger item becomes a request file in the format the repository declares (criteria, out of scope, likely files), attached to the issue. Nothing merges.

## Part 3: stages

| Stage | Adds | Touches it would have turned into a filed, actionable issue (or removed) | Size | Open issues that cover part |
|---|---|---|---|---|
| S1 Answers are findings | `answered{}` on the intervention row, failing ids on the `check` record, causes `answer_overrode`, `upstream_confirmed`, `retry_passed_unchanged`, `retry_same_failure`, `resume_no_progress`; the reason asked of an agent caller; an issue section of counts | Filed and named: 1, 3, 4, 5, 7; filed as an engine defect: 2; half: 6 (the override and the repeat, not the limit). Removed: none | M | #170 (base), #171, #172, #210 (item 4), #99, #246 |
| S2 Limits and pause facts | The limit row and `command_limit`; the warning at 80 percent; `pause_without_facts`; the pause payload names failing ids, the limit and the guard's command prefix | Named: 6, 7. The answer to 4, 6 and 7 needs no digging | S to M | #189, #211, #161, #22 |
| S3 Filing is on, shadow decisions | At `record` and `--dry-run` the child still writes the decision it would make (`would_file`, reason, counts) | Makes every row above measurable on real runs | S | #208, #196, #195 |
| S4 The run answers what needs no person | One re-ask after a discarded judgement; the judge's own re-read; a gate may declare that a FAIL that is the same at the base does not block; the map-item answer | Removed: 7, 1, 3, 2 | S each | #204 (in progress), #205 (part 2 fixed in `ea7645e8`), #203, #253, #207 |
| S5 Check replay | Recorded check tickets kept per attempt; `improve replay-check` over a cluster | Validates fixes for 1, 4, 6 in seconds | M | #27, #180, #182 |
| S6 Analysis session | Level `analyze`: inputs, session, judge, record under `improve/analyses/` | 1, 3, 4, 5, 6, 7 get a root cause and candidates | L | #209, #124, #234 |
| S7 Output | Draft pull request for a small green change; request file for the rest; `weakens-gate` path | A person reviews a fix instead of finding it | M | #41, #234, #197 |

No open issue covers: the override signal, `resume_no_progress`, the limit record, `pause_without_facts`, the analysis session or check replay.

Recommended order: S1, S3 (small, makes S1 visible), S2, S5, S6, S7. S4's items are already separate issues and run beside the rest; each one removes a touch, but only for the case already seen, while S1 makes the next unseen case report itself. The first request file is `tasks/i-loop-touches.md` (S1).
