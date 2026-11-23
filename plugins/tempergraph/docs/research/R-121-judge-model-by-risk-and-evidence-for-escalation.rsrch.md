# R-121 Judge model by risk, and what counts as evidence for escalation

## Problem statement

On 2026-11-20 the owner put "judges and ladders" into release 2, with one hard condition: "ladders should be bulletproof, I don't want to increase model or efforts on any failure." [R-120](R-120-effort-ladders-and-one-step-model-escalation.rsrch.md) already proposed an effort ladder and a one-step model escalation. It left two things open that a spec needs:

1. **Judge model by risk.** The judge's model and effort chosen by risk is named as a later use of the switch's choice layer ([R-120](R-120-effort-ladders-and-one-step-model-escalation.rsrch.md) F1), with no design. What would choose it, from what signals, and how does it stay calibrated?
2. **What counts as evidence.** R-120 says the effort ladder climbs on "a judge RETRY with an unmet blocker" or "a non-environmental check FAIL". For the owner's "not on any failure", each of those must be narrowed until a climb happens only when a stronger session is the likely fix and the signal that says so is itself trusted.

This note answers both. It reads "judges" in the owner's message as the judge model by risk, the only judge item that had no design; judge calibration and labels are already built in release 1 ([JCL](../specs/50-judge-calibration.spec.md), [FBK](../specs/41-feedback-and-judge-reliability.spec.md)).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S4 | This design: JCL binding and acceptance states, FBK grades per binding, BUD-B1, BUD-B11 cause table, JDG-B1 and B8, CHK findings and facts, RST judge scopes, CON-B3 judge resolution | Design set | [specs](../specs/00-overview.spec.md) |
| S5 | [R-045](R-045-evaluating-llm-judges-public-practice.rsrch.md) F2: judges pass bad work more often than they fail good work, so catch and clean rates are measured apart | Design set (public practice) | research/ |
| S6 | Chen, Zaharia and Zou, *FrugalGPT* (TMLR 2024): an LLM cascade sends a query to a cheaper model first and escalates only when a learned scorer rejects the answer; the scorer's quality bounds the cascade's | Paper | [arXiv 2305.05176](https://arxiv.org/pdf/2305.05176) |
| S7 | Ong et al., *RouteLLM* (ICLR 2025): routers between a strong and a weak model trained on preference data; routers are evaluated on held-out benchmarks for cost against quality | Paper | [arXiv 2406.18665](https://arxiv.org/abs/2406.18665v4) |
| S8 | Anthropic, *Building effective agents* (2024): routing classifies an input and sends it to a specialised follow-up, for example easy questions to smaller models; start with the simplest pattern and add complexity only when it measurably helps | Vendor guidance | [anthropic.com/engineering/building-effective-agents](https://anthropic.com/engineering/building-effective-agents) |
| S9 | [R-120](R-120-effort-ladders-and-one-step-model-escalation.rsrch.md) F1 to F5: the ladder climbs on any counted retry today; the repeat-cost split (49% judge blocker, 16% a person, 12% trip back, 10% check failure); vendor guidance to re-run failures at higher effort | Design set | research/ |

## Key findings

### F1 Judge-by-risk is named but never designed `supported`

- A judge model by risk is listed among later uses of the switch (S9). Per-arm options and judge options could reuse the same choice, record and override layer without a graph edge. Nothing says what risk is or how it is read.
- temperspec has a fixed version of it: one judge (code) is on the stronger tier because of what it judges, and calibration may move a judge up when it passes known-bad work (S2). The trigger in both cases is the **kind of work** or a **measurement**, never the outcome of one attempt.

### F2 A judge's alias is part of what calibration measured `confirmed`

- JCL's `binding` is `{executor, executor_version, alias, model_slug, brief_digest, criteria_digest, sampling}`; any change makes an `accepted` state `stale` (S4, JCL-AC3). FBK grades per binding (S4).
- So a judge whose model varies by risk is **several judges**, one per level, and each needs its own score. A level nobody scored is an unmeasured judge, whatever its tier.

### F3 A cascade is only as good as the signal that triggers it `supported`

- FrugalGPT escalates on a scorer's rejection, and the scorer is trained and checked on held-out data; a weak scorer escalates on false alarms and accepts wrong answers (S6). RouteLLM's routers are likewise judged by held-out cost against quality, and need preference data to be any good (S7).
- In this engine the scorer is the gate: the check and the judge. A RETRY from a judge with a low **clean rate** (it fails known-good work) is a false alarm; climbing on it spends more on work that was already fine. JCL measures that rate per binding (S4, S5). Hence an escalation trigger from a judge is only evidence when that judge's binding is `accepted`.

### F4 Most failure causes are not fixed by a stronger session `confirmed`

From BUD-B1, BUD-B11 and R-120 (S4, S9):

| Cause | Would more effort or a stronger model fix it? |
|---|---|
| Timeout, stall, turn cap, cost cap | No: more thinking runs longer and costs more |
| Infra, throttling, auth, refusal | No: the machine or the account, not the model |
| `tool_access`, environmental check FAIL | No: a grant or the environment |
| A judge blocker with `no_change`, or attributed upstream | No: the input or an earlier unit is wrong |
| Missing or malformed output (no artifact, value outside `choices`, no judgement block) | Rarely: instruction following, which a prompt or check fixes |
| A person's feedback | Unknown: new information, so the cheap rung gets its chance again |
| A judged blocker on substance, from a trusted judge, that persists | Possibly: the only cause with a plausible capability ceiling |
| A substantive check FAIL (a test failed, a rule violated) | Possibly, for effort; a repeat points to a missing instruction or tool more than a model |

### F5 Risk signals exist without a model `confirmed`

- Checks already return **facts** (engine-run command results, file facts) and findings (S4, CHK). The engine knows the attempt's diff (files, lines, paths) in the run worktree, the inputs, the item of a map and the declared settings.
- temperspec's lesson is that a route must not rest on the producing model's own word: the check ties the route to evidence (S3). The same applies to risk: a step that could lower its own judge's tier by what it writes would grade itself by proxy (OVR-B6).

### F6 Simple routing beats clever routing until measured `supported`

The vendor guidance is to start with the simplest pattern and add routing only when it measurably helps (S8). SWM holds the same rule for switches: shadow first, then route. Both apply to a risk rule: it raises cost on every attempt it raises, so it should be shown in shadow before it routes.

## Analysis

### Judge model by risk

A **risk rule** is a pure, model-free function the gate declares. It runs after the check and before the judge, reads only engine-observed facts (check facts, the attempt's diff, inputs, the item, settings), and returns one of two or three declared **levels**, each with a judge alias. Rules that make it trustworthy:

1. **Only up.** The lowest level is the gate's own judge. A rule can raise the judge, never lower it below the gate's alias or below the producer's tier for the attempt.
2. **Every level calibrated.** Each level is its own binding with its own JCL state. Stable mode and promotion need every level `accepted`, as they need every gate today (F2).
3. **No step claims.** The rule never reads the step's text or its unchecked values. A step value counts only once the check turned it into a fact (F5).
4. **Fault means the highest level.** As temperspec's unreadable route takes the longer path (S3).
5. **Shadow first.** The rule may run in shadow, recording the level it would pick (F6).
6. **Pinned by an operator.** An operator's judge model pins the level; recorded as such.

### Evidence that may raise a rung

Narrowing R-120's two triggers with F3 and F4:

- **Judge evidence** counts only when the judgement was parsed (not an engine placeholder), the judge's binding is `accepted` (or `provisional` in `local-dev`, where a person sees every climb), at least one unmet blocker is neither `no_change` nor attributed upstream, and the attempt itself ended normally (no timeout, stall, cap, infra or tool cause).
- **Check evidence** counts only for a FAIL that is not environmental and not an output-contract failure (missing artifact, malformed value), with a finding that names a criterion, from a command or a file fact the engine ran.
- **A model step** needs more: the same judged blocker, from a trusted judge, unmet on two consecutive attempts at the top effort rung; a check failure never escalates the model (F4, R-120).

### What not to build

- A judge alias that falls with risk. A cheaper judge on "low-risk" work is the agreeable-judge hazard of R-045 in a new form.
- A risk rule written as a model call. It would be one more unmeasured judge in front of the judge.
- Escalation triggered by a judge that is not `accepted`: its RETRYs are not known to be right (F3).

## Conclusions

1. Judge-by-risk is a named later use and judge tiers are fixed per kind of work; nothing chooses a judge from the outcome of one attempt.
2. A judge whose alias varies is several judges; each level must be calibrated on its own.
3. A risk rule fits the engine as a pure gate function over check facts and the diff, raising only, faulting to the highest level, with a shadow mode.
4. A climb is justified only by a parsed, trusted, substantive signal on an attempt that ended normally. A model escalation needs the same trusted judged blocker twice at the top effort rung.
5. Every other cause holds the rung. This includes timeouts, caps, infra, tool access, environmental and output-contract failures, no-change and upstream blockers, and judgements from judges that are not `accepted`.

## Open questions

| Question | Who answers | Default until answered |
|---|---|---|
| Should `provisional` judges count as evidence in `local-stable`, not only in `local-dev`? | Owner, then data | No. `accepted` only outside `local-dev`. |
| Is two the right number of repeated blockers before a model step? | Data | Two, as R-120. Revisit after 20 escalations are recorded. |
| Should a risk rule also pick the judge's effort, not only its model? | Owner | Yes, each level carries an alias and an optional effort; both are part of the level's binding. |
