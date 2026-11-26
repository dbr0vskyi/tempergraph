# Gate and human nodes

## Purpose

The gate only routes. The human node is the single place a run pauses, and only a person answers it. Escalations, spent budgets that ask, approval pauses after a pass, event waits and asks for a person's input all pause in that node, so a resume replays only it under the graph runtime's replay-from-top rule ([ADR `four-nodes-per-unit`](../adr/four-nodes-per-unit.adr.md)); the one other pause is an operator's breakpoint before a step node ([FLX-B10](flow-extensions.spec.md)). People answering pauses, skills and CI depend on the pause kinds, the payload, the decision words and exit 3, which means "a person is needed", never failure ([ADR `exit-codes-as-caller-contract`](../adr/exit-codes-as-caller-contract.adr.md)). Callers are classified from host and CI markers, and a relayed decision counts as a person's only with a person turn in the host ([ADR `classify-callers-by-the-strongest-signal`](../adr/classify-callers-by-the-strongest-signal.adr.md), [ADR `a-relayed-decision-counts-as-a-persons-only-with-host-turn-evidence`](../adr/a-relayed-decision-counts-as-a-persons-only-with-host-turn-evidence.adr.md)).

## Behaviours

### HUM-B1 Interrupt first

WHEN a paused run is resumed THE human node SHALL re-execute from its top, with nothing before the interrupt logging, spending or writing.

- GIVEN a paused run WHEN it is resumed THEN no record is written and no session starts before the decision is applied

### HUM-B2 Exit 3 with payload

WHEN the human node interrupts THE engine SHALL print the payload (`kind`, `unit`, `item`, `reason`, the produced and missing artifacts, the `rubric`, the allowed `decisions` and the exact `resume_command`) and exit 3.

- GIVEN an escalation WHEN the human node interrupts THEN the process prints the payload with a resume command that `resume` accepts and exits 3

### HUM-B7 What pauses as an escalation

WHEN a gate meets an unresolved gap (a blocker UNVERIFIABLE, the gap flag, an unparsed or discarded judgement), a workflow escalation rule, a check FAIL marked environmental, a failed or blocked attempt with cause `tool_access`, an upstream claim the judge could neither confirm nor refute ([JDG-B9](judge-and-verdict.spec.md)) or one on a gate with no judge, a defect attributed outside the allowed targets, a council with no decision and `on_no_decision: escalate` ([CNL-B13](council-unit.spec.md)), or a wait or ask past its deadline applied with `escalate` ([FLX-B8](flow-extensions.spec.md)) THE gate SHALL pause with kind `escalation`.

- GIVEN an attempt that was refused the `shell` tool WHEN its gate decides THEN the run pauses with kind `escalation` and the payload lists the refused names and the `--grant` or `--allow-command` that fixes each ([RST-B28, RST-B29, RST-B30](run-settings-and-overrides.spec.md))
- GIVEN a check FAIL marked environmental WHEN the gate decides THEN no retry runs and the run pauses with kind `escalation`

### HUM-B8 What pauses as budget

WHEN a gate set to `ask` has its retry or loop budget spent, or a model escalation's conditions hold at a stage that offers it ([LAD-B12](effort-ladder-and-model-escalation.spec.md)) THE gate SHALL pause with kind `budget`.

- GIVEN `on_budget_spent: ask` and retries spent WHEN the gate decides THEN the run pauses with kind `budget`
- GIVEN an escalation offer WHEN the run pauses THEN the payload carries the evidence and `resume --escalate`

### HUM-B9 What pauses for approval

WHEN a gate with `approval`, or a step the operator named with the approval option, passes, or a gate with criteria verified by `person` passes THE gate SHALL pause with kind `approval`; for a sign-off the payload's `rubric` lists those criteria with each `role` and `question`, and `resume --criterion <id>=signed|declined` records a status per criterion ([OUT-B10, OUT-B12](run-outcome.spec.md)).

- GIVEN a sign-off criterion `c7` WHEN its gate passes THEN the run pauses and `resume --criterion c7=signed` records `c7` signed

### HUM-B10 Waits, asks and breakpoints

WHEN a `wait` unit, an `ask` unit ([ASK](ask-unit.spec.md)) or an operator's `--pause-before` ([FLX-B10](flow-extensions.spec.md)) is reached THE engine SHALL pause with kind `event_wait`, `input` or `breakpoint`.

- GIVEN an `ask` unit WHEN it is reached THEN the run pauses with kind `input`

### HUM-B14 What pauses for a usage limit

WHEN a session of an attempt ends not ok with `usage_limit` true ([BUD-B17](budgets-and-failures.spec.md)) THE gate SHALL pause with kind `escalation` and reason `usage_limit`, giving the payload `usage_limit_resets_at` as the session returned it (null when it reported none) and a resume command that carries no `--decision`.

- GIVEN a step session that ends not ok with `usage_limit` true and a reset instant WHEN its gate decides THEN the process exits 3 and the payload has kind `escalation`, reason `usage_limit` and that instant as `usage_limit_resets_at`
- GIVEN a session ended by the usage limit whose executor reported no reset instant WHEN its gate decides THEN the payload's `usage_limit_resets_at` is null
- GIVEN a thread paused for a usage limit WHEN its payload is printed THEN its resume command names the thread and carries no `--decision`

### HUM-B11 What never pauses

WHEN an infra failure ends an attempt, or the self-improvement workflow runs THE engine SHALL not pause ([BUD](budgets-and-failures.spec.md)).

- GIVEN infra tries spent WHEN the run ends THEN it exits 5 and no pause is recorded

### HUM-B12 Decisions

WHEN a resume carries a decision THE human node SHALL apply `proceed` (accept and go on without rerunning step, judge or gate; feedback reaches the next unit once as notes), `retry` (the step runs again with a fresh retry budget; feedback reaches the step and its judge once), `back:<unit>` (to a listed earlier unit; feedback becomes that visit's reason; the pair's loop budget resets), `rewind:<unit>` (to any unit completed on the path, cleared as a trip back, no loop budget charged, counted against the human cap, [RRN-B16](reruns-and-feedback.spec.md)), `stop` (exit 4, feedback recorded locally as the cause), `event:<name>=<value>` (only at a wait) or `answer:<name>=<value>` (only at an ask or a council's no-decision pause, validated by the question's kind, [ASK-B8](ask-unit.spec.md)).

- GIVEN `resume --decision back:plan --feedback "wrong api"` WHEN applied THEN `plan` runs with "wrong api" as its visit reason
- GIVEN `--feedback x --ruling` WHEN applied THEN the ruling is shown to every later attempt of the units it applies to and to their judges until revoked ([RRN-B14, RRN-B15](reruns-and-feedback.spec.md))
- GIVEN a resume with `--set` WHEN applied THEN the run settings change for the rest of the run ([RST-B26](run-settings-and-overrides.spec.md))

### HUM-B3 Several pending gates

WHEN a resume names no unit while two gates of a parallel block are pending THE engine CLI SHALL refuse it with exit 2, listing each gate and its exact command; a resume with `--unit <name>` answers that gate and the other stays pending.

- GIVEN two pending gates WHEN `resume --decision proceed` runs THEN it exits 2 listing both
- GIVEN `--unit a` WHEN it runs THEN `a` is answered and `b` is still pending
- GIVEN two `--decision` options that are not both `answer:` words WHEN they are given THEN the resume is refused

### HUM-B4 Wait is not passable by word

WHEN a run paused at a wait is resumed THE engine SHALL accept only an `event:<name>=<value>` that the wait's pure `check(value)` accepts, storing the value as an artifact, or `stop`; anything else exits 2, writes nothing and leaves the run waiting.

- GIVEN a wait on `approved` WHEN `proceed` is sent THEN it exits 2 and the run still waits
- GIVEN that wait WHEN `event:approved=yes` passes the check THEN the value is stored and the run continues
- GIVEN that wait WHEN `event:approved=maybe` fails the check THEN it exits 2 and the run still waits
- GIVEN that wait WHEN `stop` is sent THEN the run exits 4

### HUM-B5 Approval is not friction

WHEN a passing gate pauses for approval THE engine SHALL keep the recorded verdict PROCEED, not count the pause as an escalation, and not count a rework there as a retry burst for self-improvement.

- GIVEN a passing gate with `approval` WHEN the run pauses THEN the verdict is PROCEED and the escalation count is unchanged

### HUM-B6 Intervention row

WHEN a resume is accepted THE engine SHALL append one ledger row before the graph runs, with a random id, the `Caller` of the resume with its kind, decider and relay evidence ([PRV-B16, PRV-B17](caller-provenance.spec.md)), the touch classes it counts as ([SUP-B9](supervision-metrics.spec.md)), the pause kind, the decision, the seconds the pause waited, whether feedback was given and whether as a ruling, the setting keys changed, the grants given (unit and capability names) and a cause word from metadata only.

- GIVEN an infra re-open WHEN its row is written THEN its caller kind is `engine`
- GIVEN an event value delivered by a pipeline WHEN its row is written THEN it carries the pipeline's caller
- GIVEN an agent's resume WHEN reports count interventions THEN it is counted apart from a person's

### HUM-B13 Refused decisions

WHEN a decision is not valid for the thread state ([DUR](durability-and-resume.spec.md)), names `back` to a unit the gate does not list, would take a person's retries and rewinds above the human cap (default 100), or rewinds to a unit not completed on the path ([RRN-B16, RRN-B17, RRN-B18, RRN-B14, RRN-B15](reruns-and-feedback.spec.md)) THE engine CLI SHALL exit 2 and write nothing.

- GIVEN `back:deploy` where the gate lists only `plan` WHEN resumed THEN it exits 2
- GIVEN 100 retries by a person WHEN the 101st is sent THEN it exits 2

### HUM-B15 A failed check goes back when the gate declares it

WHEN a gate that has no judge and declares `on_fail: back` meets a check FAIL that carries findings and is not marked environmental THE gate SHALL send the run back to its one back target with no retry, giving the target the findings as the reason of its visit.

- GIVEN a script unit whose gate has no judge, `on_fail: back` and the back target `a` WHEN its check fails with two findings THEN the run goes back to `a`, the visit of `a` has the two findings as its reason and the script unit is not retried
- GIVEN the same gate WHEN its check fails with a result marked environmental THEN the run is not sent back and pauses with kind `escalation` ([BUD-B11](budgets-and-failures.spec.md))
- GIVEN the same gate WHEN its check fails with no finding THEN the unit retries as a gate with `on_fail: retry` does

### HUM-B16 The reason of the visit holds the findings, numbered

WHEN a gate sends the run back with the findings of its check THE engine SHALL give the target one line for each failing finding as the reason of its visit, numbered from 1 in the order the check returned them, holding the finding's criterion, place, message and fix and nothing else.

- GIVEN a first finding with a criterion, a place, a message and a fix, and a second with a criterion and a message only WHEN the gate sends the run back THEN the reason holds two numbered lines, the first with all four parts and the second with its two
- GIVEN a check that returned one passing finding and one failing finding WHEN the gate sends the run back THEN the reason holds the failing finding alone, numbered 1

### HUM-B17 The loop budget bounds the trips back

WHEN a gate that declares `on_fail: back` meets a failing check after the run has gone back to its target as many times as the gate's loop budget allows THE gate SHALL apply its `on_budget_spent` instead of sending the run back, the pause of an `ask` showing the findings left ([BUD-B8](budgets-and-failures.spec.md)).

- GIVEN `loop_budget: 1`, `on_budget_spent: ask` and a check that fails on both passes WHEN the second failure is decided THEN the run pauses with kind `budget` and the pause lists the findings of the second failure
- GIVEN `on_budget_spent: stop` and the same failures WHEN the second failure is decided THEN the run stops with exit 5
- GIVEN `loop_budget: 1` and a check that fails on the first pass and passes after the trip back WHEN the second pass is decided THEN the run goes on and nothing pauses

### HUM-B18 What is refused

WHEN a workflow is validated THE engine SHALL refuse `on_fail: back` on a gate that has a judge, on a map's gate ([MAP-B11](map-unit.spec.md)), and on a gate that lists no back target or more than one.

- GIVEN `on_fail: back` on a gate with a judge WHEN the workflow validates THEN it is refused with its own finding code
- GIVEN `on_fail: back` on a map's gate WHEN the workflow validates THEN it is refused with its own finding code
- GIVEN `on_fail: back` on a gate with no judge and no back target, or two back targets, WHEN the workflow validates THEN it is refused with its own finding code, and with one back target that is an earlier unit it validates

## Acceptance criteria

- HUM-AC1 (HUM-B1): A source test asserts the interrupt is the first statement of the human node
- HUM-AC2 (HUM-B2, HUM-B7, HUM-B8, HUM-B9, HUM-B10): Each pause kind exits 3 with a payload holding a working resume command
- HUM-AC3 (HUM-B4): Every scenario of HUM-B4 holds
- HUM-AC4 (HUM-B6): Agent resumes, by caller kind and decider, are counted apart from a person's in every report ([SUP-B10](supervision-metrics.spec.md))
- HUM-AC5 (HUM-B11): No infra failure and no self-improvement run produces a pause
- HUM-AC6 (HUM-B12): Each decision word has the effect HUM-B12 states, tested on a fixture run
- HUM-AC7 (HUM-B3): A resume without `--unit` at two pending gates exits 2 listing both, and with `--unit` answers only that gate
- HUM-AC8 (HUM-B5): An approval pause leaves the verdict PROCEED and adds no escalation
- HUM-AC9 (HUM-B13): Each refused decision of HUM-B13 exits 2 and leaves the thread unchanged
- HUM-AC10 (HUM-B14): A fixture run whose stand-in executor ends a step session not ok with `usage_limit` true and a reset instant exits 3 with a payload of kind `escalation`, reason `usage_limit` and that instant as `usage_limit_resets_at`, whose resume command carries no `--decision`; a fixture whose judge session ends the same way pauses with the same kind and reason; and a fixture whose executor reported no reset instant has `usage_limit_resets_at` null
- HUM-AC11 (HUM-B15, HUM-B16): An engine fixture with a script unit whose check fails once with two findings sends the run back to the declared target with the two findings, numbered, as the reason of its visit, and does not retry the script unit; a check marked environmental pauses with kind `escalation` and sends nothing back; a check that fails with no finding retries
- HUM-AC12 (HUM-B17): The same fixture with a check that fails on both passes pauses with kind `budget` showing the findings of the second failure under `ask` and stops with exit 5 under `stop`, and a check that passes after the trip back leaves the run unpaused
- HUM-AC13 (HUM-B18): Each refusal of HUM-B18 has a fixture that fails validation with its own finding code, and a gate with no judge and one earlier back target validates
