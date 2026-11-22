# R-120 Effort ladders and a one-step model escalation

## Problem statement

The owner asked on 2026-11-20 what the reference says about switching models dynamically in different contexts. After reading the first findings, the owner narrowed the question: "We could have model ladder only for +1 level but we should have very strict and specific criteria per environment. Most likely I would implement effort ladder. We don't need implement it but rather research."

This note is read as four questions:

1. What does this design say about choosing or changing the model and the effort of a session during a run?
2. What does public guidance say about raising effort, or the model, after a failure?
3. For an **effort ladder** (effort rises on retries, the model stays), what must hold so it fits the engine's rules: budgets, causes, judges, calibration, trials, records?
4. For a **one-step model escalation** (at most one tier up, `small` to `medium` or `medium` to `large`), which criteria are strict enough, and how should they differ **per environment**?

"Environment" is read as the workflow's stage of [ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md): `local-dev`, `local-stable` and `pipeline`. It could also mean the binding environment that maps an alias to a deployment ([ADR-0008](../adr/0008-portable-model-aliases.adr.md)). Where that reading changes a finding, the finding says so.

This is research only. No spec, decision record or code changes with this note. On 2026-11-20 the owner put ladders into release 2 with the condition that they never climb on just any failure; the follow-up is [R-121](R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md) and spec [LAD](../specs/92-effort-ladder-and-model-escalation.spec.md). Only the Claude Code executor is in scope through release 2 ([ADR-0091](../adr/0091-first-release-ships-the-claude-executor-only.adr.md)).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S6 | This design on `main` after PR 27: BUD-B1, BUD-B11 and BUD-B7, RST-B17, RST-B22, RST-B23, ECC-B8, ECC-B9, EXI, JDG, JCL `binding`, FBK-B4, PRP kinds, SWM `arm_overrides`, MAP `item_model`, ADR-0041 | Design set | [specs](../specs/00-overview.spec.md), [adr](../adr/README.md) |
| S7 | Engine code on `main`: `run/nodes.py` (rung chosen by the retry counter), `run/gate.py` (counter resets), `executors/claude.py` (`_EFFORTS`, `--effort`, `--fallback-model`), `contracts.py` (`SessionOptions.effort`), `settings.py`, `improve/child.py` and `improve/review.py` (loop alias) | Code | `plugins/tempergraph/engine/src/tempergraph/` |
| S8 | [R-001](R-001-claude-code-cli-headless.rsrch.md) F10: `--effort` takes `low`, `medium`, `high`, `xhigh`, `max`, with availability per model | Design set | research/ |
| S9 | Anthropic's guidance on effort and cost: what effort controls, levels per model, defaults per model, "sweep effort before touching the model", "re-run failures at higher effort", "price in cost per completed task", "switch models between conversations, not inside one" | Vendor guidance (Claude API skill reference, cached 2026-11-03) | Claude API documentation, Effort and Cost Optimization pages |

## Key findings

### F1 The reference has fixed tiers, one retry ladder and no context router `confirmed`

- Every temperspec step has a fixed tier chosen by how hard its work is. Triage, expand, the phases and the code join run on Sonnet. Discovery and the plan's design pass run on Opus. The release step runs on Haiku. Judges run on Sonnet, except the code judge, which runs on Opus so that code is judged by a stronger model than the one that wrote it (S5, 7 and 8).
- The **model ladder** is the only switch inside a run. It holds up to eight aliases, and attempt n of the current budget uses the n-th alias, with the last one repeating. A person's retry, an automatic re-open or a trip back starts again at the first alias. An infra attempt or a cut-off one reruns the same alias. An operator pin overrides the ladder. The judge takes the ladder's last alias, so it is never weaker than the alias the step ends on (S6, S7).
- The ladder climbs on **any** retry the budget counts. No rule ties it to the cause of the failure beyond infra and cut-offs (S6, S7).
- A ladder wastes an attempt whenever the cheap rung fails, so its benefit has to be measured before it is relied on.
- The planned items that choose by context are a switch whose arms carry their own model, effort and timeout; a model per mapped item, read from the item; and a judge's model chosen "by risk", named only as a later use (S2). None of them changes the model **because an attempt failed**.

### F2 The reference has no effort ladder, but it has measured evidence on effort `confirmed`

- Effort is a session option, resolved in the order models are. An effort the executor cannot apply is a warning, not a refusal (S1).
- "Effort and turn count move cost more than the model does", from one runaway attempt that cost about $24 (S1, `MEASURED`).
- temperspec runs its phase step on Sonnet at **low** effort (`PARTLY BUILT`). The early quality watch found that phase-by-phase code with low-effort phases passed the first code gate in 0 of 3 runs, confounded by defects in the plans. The planned remedy is to report first-try pass rates by arm and to revert the low-effort default if it stays below the others after five or more samples (S2, S5 14 b).

### F3 What this design and the code have today `confirmed`

| Capability | Where | State |
|---|---|---|
| Model ladder of 1 to 8 aliases on steps, a judge on the last rung, reset on a person's retry, a re-open or a trip back, infra on the same rung | BUD-B7, RST-B17, `run/nodes.py` (rung = `min(retries, len - 1)`), `run/gate.py` (counter resets), test `test_model_ladder_climbs_and_a_person_retry_resets_it` | Built in release 1 |
| `effort` as one value per scope: steps, a unit, judges, a switch arm | RST-B17 and layer 5, ECC-B8, ECC-B9 | Built in release 1, arms in release 2 |
| `fallback_alias` on an overload, never sent to a judge | RST-B17, ECC-AC4, `executors/claude.py` | Built in release 1 |
| Judge binding includes `sampling` (temperature and effort), so a changed judge effort is a changed binding | JCL `binding`, FBK `binding` | Built in release 1 |
| A new model slug behind a judge's alias makes it `unmeasured` | FBK-B4, JCL-B3 | Built in release 1 |
| Per-item model on a map, per-arm model and effort on a switch | MAP `item_model`, SWM `arm_overrides` | Release 2 |
| Effort ladder, cause-gated escalation, per-stage escalation rules | none | Not designed |

Two gaps in what exists today:

- **`xhigh` is missing.** The CLI accepts `low`, `medium`, `high`, `xhigh` and `max` (S8). The setting catalog (RST-B17), `SessionOptions.effort` in `contracts.py` and `_EFFORTS` in `executors/claude.py` know only `low`, `medium`, `high` and `max`. The vendor guidance names `xhigh` as the best setting for most coding and agentic work on several current models (S9). An effort ladder without it would skip the most useful rung.
- **The rung follows the retry count, not the cause.** In `run/nodes.py` the rung is chosen from the retry counter alone. Every cause that spends the retry budget (BUD-B1, BUD-B11: a judge blocker, a check failure, a timeout, a stall, a turn cap, a cost cap, a `model` error) climbs the ladder alike.

### F4 Public guidance favours effort over model, and raising effort only on failures `supported`

These points come from one vendor source (S9), so they stay `supported`:

- Effort controls how deeply the model thinks and how many tool calls it makes, within one model. It is "the first quality-trading lever", and the guidance is to sweep effort before changing the model.
- **Re-run failures at higher effort.** When a workload has a usable failure signal (tests, a checker), run everything at a low setting and re-run only the failures at a higher one. In Anthropic's coding runs this held the pass rate of running everything at the higher setting, or slightly beat it, for a little over half the cost, counting the failed cheap attempts. The price is the checker and the doubled wall-clock time on failures.
- Before building a cascade across models, measure the most capable model at lower effort on the same tasks. Lower effort on a newer model often matches an older one at high effort.
- Judge cost **per completed task**, not per request: "a cheaper request that needs more turns or retries to finish the job isn't cheaper".
- Switch models between conversations, not inside one, since caches are per model. Every engine attempt is a fresh session, so this applies only as a note: a rung change never breaks a cache within a session.
- Effort levels and defaults differ by model and change between releases. For example, Claude Opus 5.5 defaults to `medium`, Claude Sonnet 5.5 to `high`, and some older models have no `xhigh`. An unset effort can therefore run a level higher or lower after the alias is rebound.

### F5 The engine already has the signals strict criteria need `confirmed`

- BUD-B1, BUD-B11 classifies every failure into a counter: infra, the retry budget, or an escalation with no retry. Judgements carry blocker criterion ids, and a check FAIL names its criterion (S6).
- A judge blocker is the largest cause of repeat cost, ahead of a person, a trip back and a failed check ([R-050](R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) F1.1).
- Cut-off attempts are already kept on the same rung, because "the machine is not the model's fault" (S1, BUD-B1).
- The ledger and run log record the alias and its source per attempt (RST, `settings_resolved`), so a rung that came from escalation can be told apart from a declared one.

## Analysis

### An effort ladder

What an effort ladder would be: a step declares an ordered list of effort levels, such as `[medium, high, xhigh]`, and attempt n of the current budget uses the n-th level. This mirrors BUD-B7 with the model held fixed.

Why it fits better than a model ladder (F2, F4):

- One model means one binding. Retries share the model, its tool habits and its prompt behaviour, so a lesson or a prompt fix measured at one rung mostly carries to the next.
- The vendor's measured pattern of low effort first and higher effort on a failure is exactly a retry-driven effort ladder (F4).
- The judge is untouched. A judge's effort is part of its calibrated binding (F3), so an effort ladder must **never reach a judge**. This is the same rule as "the step overrides never reach a judge" (S5 11) and RST's "judges apart". There is no "judge on the last rung" question, since the judge's model does not change.

Rules it would need to fit the engine:

1. **It climbs only on causes that more thinking can fix.** These are a judge RETRY with at least one unmet blocker that is not `no_change`, and a check FAIL that is not environmental. Together they are most of repeat cost (F5).
2. **It holds the rung on causes that more thinking makes worse or cannot fix.** These are a timeout or a stall, a turn cap, a cost cap, infra, and `tool_access`. A timed-out attempt at higher effort runs longer, and a capped attempt costs more. These causes stay on the same rung, as infra does today. The `auth` and `refused` causes and the no-change escalations already spend no retry (BUD-B1, BUD-B11).
3. **It resets where the model ladder resets:** on a person's retry, a re-open and a trip back. A person's feedback is new information, so the cheap rung gets a fresh chance with it.
4. **It starts from an explicit level, never from "unset".** The defaults differ by model and change between releases (F4), so a ladder whose first rung is "the model's default" would move when the binding changes.
5. **Preflight checks every rung.** Each level must be one the executor applies for the bound model. Today an unapplied effort is only a warning (EXI). For a ladder, a rung the model cannot apply would silently merge two rungs, so it should be a validation error.
6. **Records carry the rung.** Each attempt records its effort and the source, for example `ladder:effort[2]`. The cost lens, the gate scorecard and PRP trials must group by rung. Otherwise, a run that climbed would corrupt first-pass yield and cost per arm, the same hazard as a run that mixes switch arms.
7. **`xhigh` joins the effort enum first** (F3).
8. **It stays inside the budgets.** A ladder adds no attempt. It changes only the effort of attempts the retry budget already allows, and the run cost cap is checked before each attempt as today (BUD-B8, BUD-B9).

What it costs, unmeasured: one cheap attempt that fails is wasted (F1). The vendor figure of "a little over half the cost" (F4) is from coding benchmarks with a test signal, not from this engine's gates. Until runs exist, it is a hypothesis to measure per workflow, with a watch like the one in F2.

### A one-step model escalation

What it would be: a step on tier `small` or `medium` may run **one** further attempt on the next tier up, and only when strict criteria hold. Tier `large` and qualified aliases do not escalate. This is a ladder of at most two rungs that is reached by a rule, not by the retry count.

Criteria strict enough to be worth the cost:

1. **The effort ladder for the current tier is spent first.** This follows F4: sweep effort before the model.
2. **The same blocker repeats.** The same criterion id stays unmet on two consecutive judged attempts at the top effort rung. A different blocker each time points to a moving target (the prompt or the criteria), not a capability ceiling.
3. **The cause is a judge blocker on a judged criterion.** A check FAIL that repeats points to a missing instruction or tool, which the friction lens and a `tools` or `prompt` proposal handle better.
4. **The workflow declares escalation for the step.** It is never on by default.
5. **The judge stays where it is, and is not weaker than the escalated producer.** The model ladder puts the judge on the last rung (F1). With a declared escalation, that rule means the judge is bound to the +1 tier on every attempt, and is calibrated there. A judge that is calibrated only on the base tier must not grade the escalated attempt. In that case the attempt pauses for a person instead (`ask`), as a spent budget does.
6. **Cost headroom.** Before the attempt starts, the run's remaining cost cap must cover the estimate for a +1 attempt (from the price table and the step's recorded median usage). Otherwise the run pauses rather than drains mid-escalation.
7. **Recorded as its own source.** For example, `escalation:+1`, with the triggering criterion id. Runs with an escalation are excluded from per-version cost and yield figures, or reported apart, as in rule 6 of the effort ladder.

Per environment, read as the ADR-0041 stage:

| Stage | Effort ladder | One-step model escalation |
|---|---|---|
| `local-dev` | Allowed where declared | Allowed where declared. A person is at every escalation in dev mode, so the alternative is offered as a choice on the pause ("retry on the next tier"), not taken automatically. This produces labelled evidence for whether the escalation helps. |
| `local-stable` | Allowed where declared, and measured by rung | Automatic only if the escalated path has its own measured record: enough escalated attempts that passed the gate, with the judge `ready` on the +1 tier. Otherwise it is a pause, as in `local-dev`. |
| `pipeline` | Allowed only as promoted. `promote-check` must have seen the ladder in the runs it measured. | Only if `promote-check` covered escalated runs and the run has a cost cap. Otherwise there is no escalation: the attempt pauses (exit 3) and reaches a person through `attention`. A pipeline never spends on a path its promotion did not measure. |

If "environment" means the binding environment instead (see the problem statement), the only difference is that the +1 tier must resolve to a deployment on that machine. Preflight already refuses an alias no executor binds (CON-B3). The escalated alias must be included in that preflight, so a pipeline never learns at the second attempt that `large` is not installed.

### What not to build

- A model switch when the budget runs low. Budgets stop or pause a run (BUD-B8, BUD-B9). Switching down mid-run would make the producer weaker exactly when the work has already failed.
- Automatic judge escalation after a failed calibration. A judge on a new model is a new, unmeasured judge (FBK-B4). Moving it, for example to a stronger model when calibration shows the current one passing known-bad work, stays a `judge_model` proposal that a trial measures (PRP).
- An effort ladder or escalation on judges, members or slots: their binding is what calibration measures.
- Escalation on throttling. That is `fallback_alias` within the session, and never on a judge (S1, RST).

## Conclusions

1. The reference has fixed tiers per step, one retry ladder that climbs on any counted retry, and planned context choices (arms, items, judge by risk). It has no effort ladder and no cause-gated escalation.
2. Release 1 already builds the model ladder, a single effort per scope, the overload fallback and calibrated judge bindings that include effort.
3. An effort ladder fits the engine with the fewest new rules. Its strictness comes from the existing cause table: it climbs on a judge blocker or a non-environmental check failure, and holds the rung on timeouts, stalls, caps, infra and tool access.
4. An effort ladder never reaches a judge, starts from an explicit level, checks every rung at preflight, records its rung, and needs `xhigh` added to the effort enum.
5. A one-step model escalation is defensible only after the effort ladder is spent, on a repeated blocker on the same judged criterion, where declared, with the judge calibrated on the +1 tier and cost headroom checked.
6. Per stage, escalation is a person's choice in `local-dev`, automatic in `local-stable` only with a measured record, and in `pipeline` only when `promote-check` measured it, otherwise a pause.
7. The benefit of both is unmeasured on this engine. The vendor evidence comes from coding benchmarks.

## Open questions

| Question | Who answers | Default until answered |
|---|---|---|
| Does "environment" mean the ADR-0041 stage, the binding environment, or both? | Owner | Both. The stage table carries the rules, and the escalated alias is also preflighted. |
| Should the effort ladder ship in release 2 with SWM's per-arm effort, or before? | Owner | Release 2, next to SWM, so both share the effort record and the rung grouping in the lenses. |
| Does the CLI apply `xhigh` and `max` on every alias a binding table uses today? Needs a live probe per alias. | Live check | Treated as `uncertain`. Preflight should refuse a rung the bound model cannot apply. |
| How many escalated attempts make a "measured record" in `local-stable`? | Owner, then data | No number yet. Reuse the JCL acceptance bar's labelled-case logic once runs exist. |
| Should the self-improvement loop's alias (`medium`, hard-coded in `improve/child.py` and `improve/review.py`) become a setting, with one override pair for model and time? | Owner | Unchanged. It is a divergence noted in the thread, outside this note's question. |
