# R-126 Routing by task complexity between a simple and a detailed decomposition

## Problem statement

On 2026-11-20 the owner asked that release 2 include "switching between branches of workflow based on task complexity or other parameters, at least between simpler decomposition of workflow vs detailed decomposition with map and similar ideas".

The engine already has the parts: a switch with a pure predicate and a default arm ([CMP-B10 to CMP-B16](../specs/03-compiler-and-flow.spec.md)), shadow mode, per-arm overrides and re-arming ([SWM](../specs/79-measured-switches.spec.md)), and a sequential map with a join ([MAP](../specs/77-map-unit.spec.md)). What is missing is the method: how complexity is measured, who may decide it, where in a workflow the choice is made, what happens when the cheaper shape fails, how the two arms stay interchangeable for the units after them, and how the choice is measured. This note answers those from the design and public work.

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S5 | Prasad et al., *ADaPT: As-Needed Decomposition and Planning with Language Models* (NAACL Findings 2024): an executor tries the task first; only when it fails does a planner decompose it, recursively, so decomposition depth adapts to the task and to the executor's ability. Reported higher success than fixed plan-and-execute baselines on ALFWorld, WebShop and TextCraft | Paper | [arXiv 2311.05772](https://arxiv.org/pdf/2311.05772), [ACL Anthology](https://aclanthology.org/2024.findings-naacl.264) |
| S6 | Anthropic, *Building effective agents* (2024): the routing workflow (classify, then a specialised path) and orchestrator-workers (a planner splits work whose subtasks cannot be known in advance); start simple and add steps only when they measurably help | Vendor guidance | [anthropic.com/engineering/building-effective-agents](https://anthropic.com/engineering/building-effective-agents) |
| S7 | Ong et al., *RouteLLM* (ICLR 2025): routing by predicted query difficulty saves cost only with a router measured on held-out data | Paper | [arXiv 2406.18665](https://arxiv.org/abs/2406.18665v4) |
| S8 | This design: CMP-B10 to CMP-B16 switch (sticky arm, default on fault, operator `--arm`), SWM (shadow, `arm_overrides`, `rearm`), MAP (`items_from`, per-item gates, join, `on_empty`), VAL step values, CHK facts, RST layer 5, ADR-0071 (overrides never change what verifies the work), [R-121](R-121-judge-model-by-risk-and-evidence-for-escalation.rsrch.md) | Design set | [specs](../specs/00-overview.spec.md) |

## Key findings

### F1 A detailed decomposition is not free, and on small tasks it loses `confirmed`

Per-phase code cost 130% of one session on small plans, with all single-session code gates passing first time in the paired runs (S1). Later single-session samples were mixed: several missed the first code gate, and one long session timed out (S3). The two shapes trade cost for reliability, and the crossover depends on size.

### F2 The reference decides by measures it can count, and fails safe `confirmed`

- The planned code-mode rule reads two counts from the expanded plan (phases, rows) and compares them with thresholds in a rules file, with a repository override (S3).
- Triage writes a size class with a reason, but the route itself is tied by a **check** to a fact the check can verify (the gap list), "so the model cannot choose plan to save work" (S2).
- Every fault takes the longer, safer path (S2, S3).

### F3 Escalation runs one way, at one point `confirmed`

Escalation goes only from one session to per phase, at one point: SWM's `rearm` on a spent budget or a timeout (S8). Nothing moves a run from the detailed shape back to the simple one.

### F4 Public work favours "try simple, decompose when it fails" `supported`

ADaPT decomposes only after the executor fails, and recursively (S5). The vendor guidance says to start with the simplest pattern and add steps only when they measurably help (S6). Taken together, decomposition is a remedy to try **before** a stronger model, not after.

### F5 A prediction alone is not enough, a fallback alone is wasteful `inferred`

- Predict only: a wrong "simple" pick costs a failed long session and then a person (S3's timed-out session).
- Fallback only (ADaPT style): every complex task pays for one failed simple attempt first. On temperspec's plans (3 to 15 phases, median 7, S1) most tasks are complex, so this pays the failure on most runs.
- Both: predict from counted measures, take the detailed shape in the margin, and re-arm once from simple to detailed when the simple shape spends its budget on trusted evidence.

### F6 Complexity can be read at two points `inferred`

| Point | What is known | Typical choice |
|---|---|---|
| **Before planning** (after intake or triage) | Request size, acceptance criteria count, files or components named, labels on the input, a triage step's checked classification | `direct` (one step does the whole task) against `planned` (a plan step, then the work) |
| **After planning** | Plan phases, rows, files per phase, test rows | `single` (one session builds the plan) against `per_item` (a map over phases, then a join) |

A code-mode router is the second kind; skipping discovery for a small task is a route of the first kind. A design should serve both with the same rules.

### F7 Arms must be interchangeable for what follows `inferred`

A unit after the switch reads artifact keys. If `direct` produces `change` and `planned` produces `plan` plus per-item `change[<id>]`, the join and the outcome gate would see different inputs per arm. A join that reads the same plan in both modes avoids this. A switch over decompositions therefore needs a declared **arm contract**: the keys every arm must produce for the units after it, and the same final gates. ADR-0071 already forbids an override from changing what verifies the work (S8).

### F8 Measuring the choice needs size-adjusted figures and few mixed runs `confirmed`

Cost varies with task size, so a comparison of arms on size-adjusted cost needs far fewer samples per arm than one on raw cost. A run that re-armed must be reported apart, or it corrupts per-arm cost.

### F9 A learned router is out of reach for now `supported`

RouteLLM-style routers need preference data at a scale one workflow does not produce (S7). A threshold rule on counted measures, revised by measured proposals, fits the engine's model-free routing (C1, C5) and its improvement loop.

## Analysis

What a release 2 design needs, on top of SWM and MAP:

1. **Measures**: named, model-free functions that count things in inputs, artifacts, check facts or the workspace, each returning a number or a short label.
2. **A threshold rule as data**: per arm, the bounds on each measure that make it eligible, in a rules file inside the package with a per-repository override, and a **margin** where the detailed arm wins.
3. **Checked assessments only**: a model step may assess complexity, but its value counts only as a check fact (for example, "the size class agrees with the counted files named"). Otherwise a step could pick the cheap path for itself.
4. **Failsafe**: any fault, a missing measure or a margin result takes the detailed arm.
5. **One-way re-arm**: from the simpler arm to the more detailed one, once per run, on a spent budget or a timeout, and only on trusted evidence (R-121); never back.
6. **Remedy order**: re-arm to a more detailed decomposition comes before a model escalation on the same unit (F4), and after the effort ladder (R-120).
7. **Arm contract**: each arm produces the keys the units after the switch read, and the gates after the switch are the same whatever the arm.
8. **Measurement**: shadow first; a route report by arm and by zone with size-adjusted cost, first-pass yield and re-arm rate; mixed runs apart; an optional, deterministic, capped exploration in the margin, never in the pipeline.
9. **Other parameters**: the same machinery serves any parameter the predicate can read without a model: a declared setting, an input label, the operator's `--arm`, the stage.

## Conclusions

1. The engine has the switch, shadow mode, overrides, re-arming and the map; complexity routing needs measures, a threshold rule as data, a failsafe, an arm contract and a route report on top of them.
3. Complexity can be read before planning and after planning; both points use the same rules.
4. A model's assessment of complexity counts only as a check fact.
5. Decomposing is tried before a stronger model, after the effort ladder.
6. A learned router is out of scope; thresholds change through measured proposals.

## Open questions

| Question | Who answers | Default until answered |
|---|---|---|
| Should a switch in `route` mode be refused in `local-stable` until it has a shadow record? | Owner | Warned, not refused, in `local-stable`; required for `pipeline` by the promotion check. |
| Should the margin exploration ship in release 2? | Owner | Yes, off by default, never in the pipeline. |
| Should a map item be able to decompose further (a nested switch per item)? | Owner | No: a map inside a map is refused (MAP-B11); a per-item model stays `item_model`. |
