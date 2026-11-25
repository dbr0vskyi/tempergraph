# ADR-0062 New node kinds keep the gated unit; LangGraph's self-routing stays out

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked that the engine support what LangGraph supports and add higher-level nodes such as a council. [R-060](../research/R-060-node-types-against-langgraph.rsrch.md) sets this design's units against LangGraph 1.2: most shapes are covered, seven are missing, and five LangGraph features conflict with engine contracts (a node that routes itself with `Command`, a child that routes its parent, `RetryPolicy` re-running a model node, `defer`, and the functional API).

The design's principle is that the unit stays closed: a new flow shape decides only where PROCEED goes. The question is how far new node kinds may change that.

## Decision

We will:

1. Add four unit kinds, **`script`**, **`council`**, **`contest`** and **`ask`**, and five flow extensions (selective parallel, map over a sub-workflow, deadlines, fallback target, operator breakpoints). Each kind compiles to the same four nodes per unit, step, judge, gate and human ([CMP](../specs/compiler-and-flow.spec.md)); only what runs **inside the step node** differs. For council and contest that is a compiled subgraph of sessions with an engine-owned barrier, so a crash resumes only unfinished sessions.
2. Keep every outcome **engine-derived**: a vote is tallied, a contest winner is picked, and an answer is validated by rule; no model decides a route, a winner or a verdict.
3. Offer LangGraph's capabilities as **declared workflow data**, not as its Python API. Expressive parity means a workflow can declare each shape LangGraph can build.
4. Leave out, on purpose: node self-routing (`Command(goto)`) and parent routing (`Command.PARENT`), `RetryPolicy` on model and judge nodes, `defer`, and the functional API. LangGraph features that serve as mechanism (per-node timeout, error handler, drain, static `interrupt_before`, caching) may implement the specified behaviour.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| New kinds inside the gated unit (chosen) | One verdict path, one interrupt, one diagram rule; every kind is judged, budgeted and logged the same way | Council and contest need a subgraph inside the step node |
| Expose LangGraph primitives directly (`Command`, `Send`, custom nodes) | Full LangGraph power | Breaks C5 (pure routing), C6 (one interrupt), C8 and ADR-0003; non-experts get the rope the product exists to remove |
| New kinds as free-standing nodes outside the unit | Simpler compiler | Each kind needs its own verdict, pause and budget rules; independence is easy to lose |
| No new kinds; patterns only | Nothing to build | Voting, best-of-n and mid-run input need hand-wired parallel blocks, extra steps and routes; authors get them wrong |

## Decision rationale

| Criterion | Inside the unit | Raw LangGraph | Free-standing nodes | Patterns only |
|---|---|---|---|---|
| Keeps C4, C5, C6 | yes | no | partly | yes |
| Expresses every R-060 shape | yes | yes | yes | no |
| Same validation, audit, diagram for all kinds | yes | no | no | yes |
| Works on all four executors | yes (sessions are ordinary step or judge sessions) | yes | yes | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | "Support what LangGraph supports" means expressive parity through workflow data, not access to LangGraph's API. | R-060, CON-B4, CON-B5, CON-B6, CON-B7 |
| A2 | A higher-level kind is worth adding only when a pattern would otherwise need three or more hand-wired units ([R-061](../research/R-061-councils-debate-and-voting.rsrch.md) K7, simplicity advice). | Future kinds |

## Consequences

- Positive: the four kinds inherit budgets, pauses, audit, evals, run events and the diagram rule with no special case. The excluded features are named, with the contract each would break.
- Negative: the compiler gains subgraph forms for the step node; the diagram model draws them as one unit with a member or candidate count.
- Risk: authors may expect LangGraph's `Command` idioms. Mitigation: the authoring skill maps each LangGraph idiom to its declared form (R-060 table) and validation names the form when a workflow tries a raw import.

## Revisit when

LangGraph ships a primitive that R-060 does not list, or a workflow needs a shape that takes three or more units to express.
