# R-010 tempergraph against existing solutions: what is good, what is bad, and whether it has a future

## Problem statement

The owner asked for an honest comparison of the tempergraph concept with existing solutions: what is good and why, what is bad and why, whether it has a future, and whether it reinvents the wheel. The concept is the README's ("start from a definition of a good outcome, deterministic checks, LLM-as-judge for what rules cannot express, loopbacks and retries driven by verdicts, self-improvement") as designed in this set: workflows as data, compiled to a durable LangGraph graph, a check-then-independent-judge gate after every step, engine-derived routing, every model call costed, four executors that wrap existing agent harnesses, and a built-in loop that files issues from finished runs ([overview](../specs/00-overview.spec.md)).

[ADR-0002](../adr/0002-langgraph-graph-runtime.adr.md) already compares graph runtimes. This note does not redo that. It compares the **whole product** against what a team could use instead in November 2026, and it is written to be candid rather than kind. The gap review of the design itself is [R-011](R-011-design-gap-review.rsrch.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| This design set | Specs, ADRs, research | [specs](../specs/00-overview.spec.md), [adr](../adr/README.md) |
| Claude Code dynamic workflows | Official docs | https://code.claude.com/docs/en/workflows.md |
| LangGraph durable execution and functional API | Official docs | https://docs.langchain.com/oss/python/langgraph/functional-api, https://docs.langchain.com/oss/python/langgraph/durable-execution |
| LangGraph task-caching gotcha in HITL nodes (Dec 2025) | Practitioner post | https://dev.to/rigby_/langgraph-hitl-the-task-caching-gotcha-that-cost-me-3-days-1g0j |
| Archon, a YAML workflow engine over Claude Code, Codex and Pi | Project README; secondary guide | https://raw.githubusercontent.com/coleam00/Archon/dev/README.md, https://betterstack.com/community/guides/ai/archon-ai/ |
| Microsoft Agent Framework 1.0 (3 Apr 2026), workflow checkpoints | Vendor blog, official docs | https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/, https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints |
| CrewAI task guardrails | Official docs | https://docs.crewai.com/edge/en/concepts/tasks.md |
| Temporal integration with the OpenAI Agents SDK | Vendor docs | https://docs.temporal.io/develop/python/integrations/openai-agents-sdk |
| Pydantic AI durable execution (Temporal, DBOS) | Official docs | https://pydantic.dev/docs/ai/integrations/durable_execution/overview/ |
| Spec Kit, Kiro, BMAD, OpenSpec, Tessl comparisons (Mar–Nov 2026) | Practitioner and analyst posts | https://dev.to/willtorber/spec-kit-vs-bmad-vs-openspec-choosing-an-sdd-framework-in-2026-d3j, https://particula.tech/blog/spec-driven-development-tools-spec-kit-vs-kiro-vs-tessl, https://paulanunes85.github.io/sdd-market-analysis-2026/03-sdd-comparison.html |
| GEPA reflective prompt optimizer, DSPy | Paper, official docs | https://arxiv.org/abs/2507.19457, https://dspy.ai/api/optimizers/GEPA/overview/ |
| Self-preference bias in LLM-as-a-judge; MT-Bench judge study | Papers | https://arxiv.org/abs/2410.21819, https://arxiv.org/abs/2306.05685 |

Vendor and practitioner posts are marked `supported` at most. Where two independent sources agree, a finding is `confirmed`.

## Key findings

### The landscape, by what each kind of tool owns

tempergraph claims to own five things at once. The table shows who else owns each.

| Concern | Who already owns it | How well | Confidence |
|---|---|---|---|
| **Graph, durable state, human pause** | LangGraph (checkpointer, `interrupt`), Microsoft Agent Framework workflows (checkpoints per superstep, pause and resume, GA April 2026), Temporal and DBOS under Pydantic AI and the OpenAI Agents SDK, CrewAI Flows | Mature and commoditized. Microsoft's and Temporal's durability is at least as strong as LangGraph's. | confirmed |
| **Gate after a step with retry** | CrewAI task guardrails (a function or an LLM guardrail, failure fed back, `guardrail_max_retries` default 3); Archon `loop_group` with `until_bash` and a max iteration count; dynamic workflows' `schema` validation with up to 5 retries | Common, but shallow: the guardrail is usually the same model family, often the same agent, with no independence, no typed verdict and no budget per cause. | confirmed |
| **Orchestrating coding-agent CLIs as nodes** | Archon (YAML nodes over Claude Code, Codex and Pi, bash nodes for validation, approval waits, a worktree per run, SQLite or Postgres event store, a web UI with run detail and graph); Claude Code dynamic workflows (a JS script spawning up to 1,000 subagents, positional replay, `/workflows` view); Microsoft Agent Framework (Claude Code SDK as an agent harness, preview) | Real and growing. Archon is the nearest neighbour to tempergraph's engine; dynamic workflows are the nearest neighbour to its shell. | supported |
| **Spec-driven delivery** | GitHub Spec Kit (constitution → specify → plan → tasks → implement, 30+ agents), Kiro (EARS requirements, design, tasks; checkpoints and hooks in an IDE), BMAD (persona hand-offs), OpenSpec (change deltas), Tessl (spec as source, beta) | Popular, but verification is human review or a persona prompt. None measures cost per run, none has resumable run state, none has an independent judge. Spec drift and markdown bloat are the common complaints. | supported |
| **Evaluation, calibration, self-improvement** | LangSmith and similar tracing and eval services; DSPy optimizers, GEPA (reflective prompt evolution from traces, reported to beat RL with far fewer rollouts) | Strong for prompt programs and offline evals; weak for long, tool-heavy agent sessions on a real repository. | supported |

### What tempergraph does that the others do not

| # | Strength | Why it is a real advantage | Confidence |
|---|---|---|---|
| S1 | **Independence is enforced, not requested.** The judge is a fresh read-only session whose tool set is derived from what the step could change, and a guard voids a verdict when the judge called anything else ([GRD](../specs/06-independence-guard.spec.md)). | Every guardrail found above is a prompt or a function in the producer's process. Self-preference bias is measured in the literature: a model rates its own kind of output higher. Cross-executor judging ([ADR-0013](../adr/0013-cross-executor-judging.adr.md)) is a cheap, direct counter that no surveyed tool offers. | confirmed (bias), inferred (uniqueness) |
| S2 | **The verdict is derived by rule, and the cause picks the counter.** A model failure costs a retry, an infra failure an infra try, an `auth` or `refused` error goes straight to a person ([BUD](../specs/08-budgets-and-failures.spec.md)). | Generic retry loops spend the budget on failures no retry can fix: a broken environment, a missing credential or a refusal ends the same way on every try. | inferred |
| S3 | **Honest cost.** Every model call is a logged executor run; reported and estimated cost stay apart; unknown is never zero ([OBS](../specs/15-observability-and-cost.spec.md)). | Dynamic workflows show tokens per agent, not dollars; Archon's cost appears only in telemetry; the SDD tools show nothing. "45% of all spend is a repeat" is the kind of finding only this discipline produces. | supported |
| S4 | **Refuse before spend.** Validation and preflight are model-free and refuse an executor that cannot enforce what a step asks for ([EXI-B1](../specs/10-executor-interface.spec.md)). | Most frameworks discover a missing capability mid-run, after spend. | inferred |
| S5 | **Lessons with numbers behind them.** Two-pass planning (gate passed first time 14 of 15 against 5 of 52), check-before-judge, retries as edges. | Rare in this space, where claims are mostly vendor-reported. Caveat: one repository, one laptop, mostly the engine's own plugins. | supported |
| S6 | **Harness-agnostic by capability, not by lowest common denominator.** Executors declare capabilities; a step that needs something its executor lacks is refused, never silently downgraded (contract C15). | Archon and Spec Kit support many agents by treating them alike. tempergraph's model is more honest about what each harness can enforce. | inferred |

### What is weak, and why

| # | Weakness | Why it matters | Confidence |
|---|---|---|---|
| W1 | **The concept says "framework", the design is an engine plus a CLI.** There is no specified Python authoring API, and the declaration format of a workflow package is undefined ([R-011 G2](R-011-design-gap-review.rsrch.md)). | "A LangGraph-based Python framework" sets an expectation (import it, compose graphs in code, use LangChain models and tools) that the design does not meet. Users comparing it with LangGraph, Pydantic AI or Microsoft's framework will find a different product. | confirmed (from the specs) |
| W2 | **LangGraph is used thinly.** Nodes call subprocesses; no LangChain model, tool, store, Studio or Platform feature is used. LangGraph supplies a scheduler, a SQLite checkpointer and `interrupt`. Its replay-from-top semantics force the four-node unit ([ADR-0004](../adr/0004-four-nodes-per-unit.adr.md)). | The dependency is justified by the README, not by the design's needs. Temporal, DBOS or a small hand-written state machine over SQLite would carry the same load. This is not a reason to switch now; it is a reason not to let LangGraph types leak beyond the compiler, so the choice stays cheap to reverse. | supported |
| W3 | **The "for non-experts" goal is in tension with the design's size.** 23 specs, 15 engine contracts, about 30 run options, seven flow primitives, ladders, audit rates, two improvement modes. | The design is built by and for experts and promises to hide that behind an authoring skill that is not yet specified in depth. Spec Kit and Kiro won users by being small first. | inferred |
| W4 | **Four executors on day one.** Each executor is a spec, a stand-in, a conformance suite and a probe table; Antigravity cannot host a judge, has no turn or cost cap, and its terms for scripted use are an open owner question. | The breadth multiplies test and maintenance cost before one workflow has run. The hard requirement is the owner's, but its order is not ([R-011 G4](R-011-design-gap-review.rsrch.md)). | confirmed (from the specs) |
| W5 | **The core value rests on judges whose reliability is unmeasured.** "How often a judge is wrong" has no number yet. | A gate that is wrong 20% of the time in either direction is worse than a person reading the diff. Until judge agreement is measured, the main claim of the product is an argument, not a fact. | confirmed |
| W6 | **Self-improvement stops at filing issues.** No optimizer changes a prompt or a criterion; a person must. | That is the safe choice, and the right default. It is also where DSPy- and GEPA-style optimizers are ahead: they turn traces into candidate prompt changes and measure them. tempergraph already records exactly the traces such an optimizer needs. | supported |
| W7 | **Local-only observability.** Run logs, ledgers and stats stay on one machine; there is no trace export and no aggregation across machines. | Fine for one developer, insufficient for a team. Microsoft's framework ships OpenTelemetry dashboards (preview); Archon has a web UI. This is the subject of a parallel thread and is noted only. | supported |
| W8 | **The interaction model is batch.** A pause is a process exit 3 and a CLI resume. | Correct and durable, but slower to use than dynamic workflows, which run in the session the person already has open. The planned monitor plugin is the answer; it does not exist yet. | inferred |

### Is it reinventing the wheel?

| Part | Verdict | Why |
|---|---|---|
| Graph, checkpointer, interrupt | **No**: taken from LangGraph | As decided in [ADR-0002](../adr/0002-langgraph-graph-runtime.adr.md). |
| Agent loop, tools, skills, MCP for steps | **No**: taken from the harnesses | Claude Code, the Agent SDK and Antigravity bring their own loop. |
| Messages API loop and tool host | **Partly yes** | A minimal agent loop and ten tools re-implement what the harnesses and the SDK's tool runner already do ([ADR-0020](../adr/0020-engine-owned-tool-loop-for-the-messages-api.adr.md)). The reason (a judge that holds exactly its views, a light CI executor) is sound but narrow; this executor is the best candidate to defer. |
| Session launcher, timeouts, idle watchdog, tree kill | **Necessary** | No harness offers equal limits, and Antigravity has none of the caps ([R-003](R-003-executor-capability-matrix.rsrch.md)). |
| Gate funnel, guard, verdict derivation, budgets by cause | **No: this is the product** | Nothing surveyed does it. |
| Run log, cost rules, reports | **Partly** | Tracing tools exist, but none keeps reported and estimated cost apart over four executors or classes repeats by cause. A thin export to OpenTelemetry would avoid building dashboards. |
| Workflow orchestration over agent CLIs | **Overlaps Archon and dynamic workflows** | The overlap is real. The difference is the gate funnel and durability: Archon gates with bash and loops; dynamic workflows have positional replay, no mid-run human input and no independent judge. |
| Spec-driven method (temperspec) | **Overlaps Spec Kit, Kiro, BMAD, OpenSpec** | The method is similar; the enforcement is not. temperspec's gates, measured cost and judged hand-offs are what those tools lack, and their weak point (spec drift, waterfall risk, ignored rules) is exactly what a judged gate catches. |

### Does it have a future?

| Argument for | Argument against |
|---|---|
| The industry is converging on "agents need verification and durable runs": Microsoft's framework, Temporal's agent integrations, CrewAI guardrails, Archon's validation nodes and dynamic workflows' schema retries all move that way. tempergraph is early on the strongest form of it. | The convergence also means the big frameworks will add judges and evals. Microsoft already lists evaluation dashboards; LangGraph has LangSmith. The independent-judge idea is easy to copy once shown. |
| Harness-agnostic orchestration of coding-agent CLIs is a gap the model vendors do not fill for each other. | Each harness vendor ships its own orchestrator (dynamic workflows for Claude Code, and the others in kind). A third-party orchestrator must keep up with four moving CLIs. |
| Measured cost and first-pass yield per gate are exactly what a team lead needs to justify agent spend. | None of the numbers come from a second team or repository yet. |

## Conclusions

1. tempergraph is **not** reinventing the wheel where it matters: the graph, durability and agent loops come from LangGraph and the harnesses. Its own code is the gate funnel, the guard, cause-based budgets and honest cost, and **no surveyed product offers that combination**.
2. Its **unique, defensible core** is enforced judge independence (fresh, read-only, derived views, guarded, optionally another model family) plus verdicts derived by rule. That is where design and build effort should concentrate.
3. It **overlaps** Archon (engine) and Claude Code dynamic workflows (shell experience) more than ADR-0002's comparison admits; neither appears there. The monitor and orchestrator work should borrow their interaction model rather than compete with it.
4. The biggest risks are **scope** (four executors, seven flow primitives, batch, audit judges and the improvement loop before one workflow has run), the **unmeasured judge**, and the **framework-or-engine identity**. All three are fixable by sequencing, not by redesign; [R-011](R-011-design-gap-review.rsrch.md) proposes the cut.
5. Verdict: **it has a future as a verification-first orchestrator for coding-agent CLIs**, provided the first release is small, the judge's agreement with people is measured early and published, and the product is described as what it is (an engine and CLI with a Python authoring API), not as a general LangGraph framework.

## Open questions

| Question | Owner | How to settle |
|---|---|---|
| Is the product a library people import (framework) or an engine people run (CLI)? The answer changes the authoring API, packaging and the comparison set. | Owner | Decide; [R-011 G2](R-011-design-gap-review.rsrch.md) recommends "engine first, with a typed Python authoring API". |
| Should Archon and dynamic workflows be added to ADR-0002's options considered as positioned neighbours, with a stated difference? | Owner | Amend ADR-0002's context or write a positioning ADR when the owner reviews this note. |
| How does a judge's agreement with a person compare with a second person's? Without it the core claim stays argued. | Engine owner | A calibration study on real runs ([R-011 G7](R-011-design-gap-review.rsrch.md)). |
