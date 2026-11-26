# A step loads the method for each goal the run state names

## Context

A step that serves several goals carries one branch per goal in its prompt, and every session reads every branch, including those its task does not have (issue #222). This record settles how the engine chooses, delivers and checks a per-goal method before that feature is built; it touches prompt rendering, the executors, the gate and the improvement loop.

## Current state

- A step's prompt is one template rendered per attempt, with engine blocks appended ([PRM-B1, PRM-B4](../specs/prompt-rendering.spec.md); `engine/src/tempergraph/render/prompt.py`).
- A step declares skills as tools; on `claude` each declared skill is allowed and every other skill the CLI lists is denied, or all skills are removed when the step declares none ([ECC-B25](../specs/executor-claude-code.spec.md); `engine/src/tempergraph/executors/claude.py`).
- An executor with no route for a declared skill is refused before spend ([`plugin-content-reaches-each-executor-by-a-declared-route`](plugin-content-reaches-each-executor-by-a-declared-route.adr.md); PKG-B23, PKG-B24).
- Files a step is told to read are declared as `step_files`, which the improvement loop can trial ([PKG-B13](../specs/workflow-package.spec.md)).
- A check gets the attempt's tool calls with capability and target ([CHK-B24, CHK-B25](../specs/check-contract-and-command-runs.spec.md)).
- A step sends work back with an `UPSTREAM <unit>: <defect>` line (`engine/src/tempergraph/render/output.py`).
- Unattended sessions load a skill the prompt names, 3/3 on Claude Code 2.1.332; live check L-7 passed (research `step-methods-loaded-on-demand`, `plugins/temperspec-tgraph/docs/research/`, F3, F4).
- The audit measures each template's share of text under goal branches ([PRA-B12](../specs/prompt-audit.spec.md)).

## Forces

- C1 (constraint): the engine knows no workflow. Source: ADR `the-engine-names-no-workflow`
- C2 (constraint): what a step session can load is what the step declares. Source: ECC-B25, ADR `plugin-content-reaches-each-executor-by-a-declared-route`
- C3 (constraint): a step behaves the same on every executor it can run on, or is refused before spend. Source: PKG-B23
- F1: a session reads only the instructions for the goals its task has
- F2: a gate can tell which method should have been used, so a miss is a finding, not a guess
- F3: a method change can be trialled by the improvement loop like a prompt change
- F4: little new surface for an author to learn

## Options considered

### A. The engine chooses methods from run state (chosen)

How it works: a step declares `methods`, each a package skill with an optional `when: {<state key>: [values]}`. At each attempt the engine names the applying methods in a fixed prompt section, grants `skill:` for exactly those, inlines their bodies on an executor with no skill route, and a stock criterion fails an attempt that did not open one. A trip back names a defect kind the target declares, which selects the target's methods for that visit.
For: only the applying text is read (F1); the engine knows which method applied, so the record can be checked (F2); method files are `step_files` (F3); the grant reuses ECC-B25 (C2) and the inline route keeps every executor equal (C3). Against: a new declaration and a new prompt section (F4).

### B. The model picks methods from a listed toolbox

How it works: the step declares its skills and the prompt lists them; the session decides which to load.
For: nothing new in the engine (F4). Against: a gate cannot know which method should have loaded (F2); the model may load all of them (F1).

### C. Split each goal into its own step behind a route

How it works: a route picks one of several steps, one per goal.
For: uses existing routes and switches (F4). Against: a task with two goals runs two sessions or needs a third step for the mix; each step repeats the shared role text (F1).

### D. Keep one prompt with branches

How it works: no change; the audit's goal-branch share keeps the growth visible.
For: nothing to build (F4). Against: every session reads every branch (F1); research F1 and F2 measured prompts growing 32% and 50% from one change each.

## Decision

We will take option A, with the trip-back defect kind the owner chose on 2026-11-26.

## Decision rationale

F1 is met: a session gets the role text and the applying methods only. F2 is met: the engine renders the section, so the record must show each named method opened. F3 is met through `step_files`. F4 is given up in part: one declaration (`methods`, optional `defect_kinds`) and one prompt section; a step without methods is rendered as today. C1 holds because the feature is stated and tested with an engine fixture. C2 holds because the grant is exactly the applying methods. C3 holds through the inline route, which also lifts today's refusal for such a step.

## Consequences

Prompts shrink to the role and a shared skeleton; goal text moves into skills a person's session can use too. Rendering, the claude executor, the stock gate criteria, the output parser and the audit each change. A method nobody's state selects becomes visible as an unused method in the audit. A gate whose criteria all apply to every goal still repeats its whole work after one failure; that is #134, not this.

## Risks

- A condition names a state key no earlier unit produces, so its method never applies. Limited by: `validate` refuses such a condition. Noticed by: the audit's unused-method finding.
- The inlined body on another executor drifts from what a loaded skill gives. Limited by: the same file is the source of both. Noticed by: a method's criterion failing on one executor only.

## Assumptions

- A1: a skill named in the prompt is loaded by an unattended session, as L-7 and three probes showed. Check: the not-opened criterion on the first pilot runs. If wrong: every attempt fails that criterion and the inline route becomes the only route.

## Revisit when

- Issue #222 is closed.
- Claude Code version reaches 3.0.0.
