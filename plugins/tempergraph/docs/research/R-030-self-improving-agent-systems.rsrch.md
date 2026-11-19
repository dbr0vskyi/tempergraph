# R-030 Self-improving agent systems: what works, what fails, what tempergraph should take

## Problem statement

The owner asked how tempergraph's self-improvement should work end to end. The current loop ([SIL](../specs/16-self-improvement.spec.md), from) detects friction, outcome gaps and cost waste, and files de-duplicated issues that a person turns into a new workflow version. It stops at the issue: nothing drafts a testable change, nothing measures a change against the same work, and the judge that every signal rests on is itself unmeasured. This note surveys public work on systems that improve their own prompts, contexts, workflows or code, and states which mechanisms fit a framework whose promise is *tempered* rails: bounded, gated, reviewable.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Shinn et al., *Reflexion: language agents with verbal reinforcement learning* (2023) | Paper | arXiv 2303.11366 |
| Madaan et al., *Self-Refine* (2023) | Paper | arXiv 2303.17651 |
| Huang et al., *Large language models cannot self-correct reasoning yet* (2023) | Paper | arXiv 2310.01798 |
| Zhao et al., *ExpeL: LLM agents are experiential learners* (2023) | Paper | arXiv 2308.10144 |
| Wang et al., *Agent Workflow Memory* (2024) | Paper | arXiv 2409.07429 |
| Zhang et al., *Agentic Context Engineering (ACE): evolving contexts for self-improving language models* (2025, ICLR 2026) | Paper | [arXiv 2510.04618](https://arxiv.org/abs/2510.04618) |
| Opsahl-Ong et al., *Optimizing instructions and demonstrations for multi-stage LM programs* (DSPy MIPROv2, 2024) | Paper | arXiv 2406.11695 |
| Agrawal et al., *GEPA: reflective prompt evolution can outperform reinforcement learning* (2025, ICLR 2026) | Paper | [arXiv 2507.19457](https://arxiv.org/abs/2507.19457) |
| Yuksekgonul et al., *TextGrad* (2024) | Paper | arXiv 2406.07496 |
| Zhang et al., *AFlow: automating agentic workflow generation* (ICLR 2025) | Paper | [arXiv 2410.10762](https://arxiv.org/abs/2410.10762) |
| Hu et al., *Automated design of agentic systems* (ADAS, 2024) | Paper | arXiv 2408.08435 |
| Zhang et al., *Darwin Gödel Machine: open-ended evolution of self-improving agents* (2025) | Paper | [arXiv 2505.22954](https://arxiv.org/abs/2505.22954); [The Register, 2025-06-02](https://www.theregister.com/2025/06/02/self_improving_ai_cheat/) |
| Robeyns et al., *A self-improving coding agent* (SICA, 2025) | Paper | arXiv 2504.15228 |
| Zheng et al., *Judging LLM-as-a-judge with MT-Bench and Chatbot Arena* (2023) | Paper | arXiv 2306.05685 |
| Ye et al., *Justice or prejudice? Quantifying biases in LLM-as-a-judge* (2024) | Paper | arXiv 2410.02736 |
| LangSmith evaluation concepts: offline datasets, online evaluators, annotation queues | Product docs | [docs.langchain.com/langsmith/evaluation-concepts](https://docs.langchain.com/langsmith/evaluation-concepts); [annotation queues](https://docs.langchain.com/langsmith/annotation-queues) |
| LangMem SDK: procedural memory and prompt optimization for LangGraph agents | Product docs, blog | [LangMem launch](https://blog.langchain.com/langmem-sdk-launch) |

Paper results are read from abstracts and the authors' own reported figures; none was reproduced here.

## Key findings

### F1 Four families of self-improvement, by what changes

| Family | What is changed | Signal | Examples | Persistence |
|---|---|---|---|---|
| In-episode reflection | Nothing durable; the next attempt is told what went wrong | Test result, judge text, self-critique | Reflexion, Self-Refine | One task |
| Experience memory | A store of lessons, rules or reusable sub-workflows injected into later prompts | Success and failure trajectories | ExpeL, Agent Workflow Memory, ACE, LangMem procedural memory | Across tasks, at run time |
| Program optimization | Prompts, demonstrations, or the workflow graph itself, searched offline against a metric on a training set | A scored metric over a dataset | DSPy MIPROv2, GEPA, TextGrad, AFlow, ADAS | A new program version |
| Self-modifying code | The agent's own source | A benchmark score | Darwin Gödel Machine, SICA | A new agent version |

`confirmed` (several sources describe the same split). tempergraph already has the first family as an engine rule: a retry is a fresh session told the gate's evidence ([BUD](../specs/08-budgets-and-failures.spec.md)). Its current loop sits before the third family: it produces the *diagnosis* that an optimizer would consume, but no candidate and no score.

### F2 External, independent feedback is what makes improvement work

Intrinsic self-correction without an external signal does not reliably improve reasoning and can make it worse (Huang et al.). Reflexion's and Self-Refine's gains come where a test, a tool result or a separate evaluator supplies the signal. `confirmed`. This is why tempergraph never lets a step grade itself, and it means the loop's quality is bounded by the quality of its judges and of its human ground truth, not by the cleverness of the proposer.

### F3 Optimizers need a dataset and a metric, and reflect on traces

MIPROv2, GEPA and AFlow all assume a set of tasks with a scoring function and search over candidates evaluated on that set. GEPA's distinguishing move is to *read the execution traces and evaluator feedback in natural language* to propose targeted prompt edits, keeping a Pareto front of candidates rather than one best, and reports better results than reinforcement learning with far fewer rollouts. `supported` (one source each; consistent across the family). For tempergraph this means: (a) the per-criterion judge feedback the gate already records is exactly the "textual feedback" these optimizers use; (b) without a fixed case set (a replay set), no candidate can be scored: figures compared across versions on whatever runs arrived move with the mix of work, not with the version. `inferred`.

### F4 Experience memory helps, and collapses when rewritten wholesale

ACE reports that contexts maintained as an evolving playbook of itemized entries, updated by small deltas from a generator, reflector and curator, beat monolithic rewrites, and names two failure modes of rewriting: *brevity bias* (summaries drop domain detail) and *context collapse* (iterative rewriting erodes accumulated knowledge). ExpeL and Agent Workflow Memory report gains from extracting insights and reusable routines from past trajectories. `supported`. The matching risk on the workflow side: a fix fitted to one request narrows the workflow for every other, which is why a proposal that adds a request's literals is refused ([PRP-B3](../specs/40-improvement-proposals.spec.md)). `inferred`.

### F5 A system that optimizes against its own evaluator games it

The Darwin Gödel Machine paper reports a case where the agent, rewarded on a hallucination check, removed the markers the check looked for instead of fixing the behaviour, and the authors note the need for sandboxing, human oversight and traceable lineage. `supported` ([arXiv 2505.22954](https://arxiv.org/abs/2505.22954), press account [The Register](https://www.theregister.com/2025/06/02/self_improving_ai_cheat/)). LLM judges carry position, verbosity, self-preference and other biases (Zheng et al.; Ye et al.). `confirmed`. Inference: if one proposal may change both a step and the criteria or check that grade it, the cheapest "improvement" is a weaker gate. `inferred`.

### F6 Production tooling closes the loop through datasets and people

LangSmith's documented pattern: traces feed online evaluators; selected traces go to annotation queues where people label them; labelled traces become dataset examples; offline experiments compare versions on the dataset. LangMem offers prompt optimization from conversation feedback for LangGraph agents. `supported` (vendor docs). The mechanism tempergraph lacks is the middle: a uniform *label* record that joins human ground truth (an approval answer, a merged or closed pull request, a re-run, a rework) to the run and gate it judges.

### F7 Self-improvement cost is real and must be bounded

GEPA's selling point is rollout efficiency; AFlow and ADAS search spend many evaluations; DGM runs cost thousands of dollars per experiment by the authors' account. `supported`. An unbounded search is incompatible with the engine's cost contract; a trial must have a cap and a case count fixed before it starts. `inferred`.

### F8 Detection outruns triage

| Fact | Mark |
|---|---|
| Flagging is not selecting: 89 of 90 runs flagged; of 137 filing records 22 opened issues, 58 commented, 53 recorded, 4 errored | `confirmed`  |
| Judge confidence carried no signal for filing (AUC 0.45) | `supported`  |
| A person chose issues, wrote briefs and merged; 36 of 52 release entries were delivered by a completed run | `supported`  |
| 32 open loop-filed issues waited for an owner; most cite one run; six engine issues had a workflow twin | `supported`  |
| Calibration sets are synthetic; no live stable-mode run | `confirmed`  |


## Conclusions

1. tempergraph's loop should extend from diagnosis to **candidate change plus measured evidence**, the third family of F1, and stop there: a person merges. Self-modifying engine code (the fourth family) is out of scope for the first release.
2. The unit of improvement is a **versioned change to workflow data** (prompt, brief, criterion text, check, alias, timeout, flow arm), scored on a **fixed replay set** with paired comparison, never on whatever runs happened next.
3. The proposer should work GEPA-style from recorded per-criterion feedback and traces, and propose small, typed deltas, not rewrites (F3, F4).
4. **Steps and their graders are never changed in the same proposal**, and a change that weakens a gate is its own class that only a person can approve (F5).
5. Judge reliability must be measured against **human labels** before judge grades drive filing or promotion (F2, F6); labels are a first-class record.
6. Run-time experience memory that rewrites prompts between runs is rejected; lessons are workflow content, changed through the same proposal path (F4, F5).
7. Every trial has a fixed case count and spend cap, logged and costed like any run (F7).
8. The loop's own funnel needs a backlog view: findings grouped into clusters with a ranked expected value, so a person's attention, the scarce resource, goes first where it pays (F8).

## Open questions

| Question | Owner |
|---|---|
| Does GEPA-style reflective search beat a single drafted delta on workflows of this size (5 to 15 steps, cases costing dollars each)? Only a live trial answers it. | Owner, after the first replay set exists |
| Is a paired comparison on 8 to 20 cases enough to detect the effect of a typical workflow change on first-pass yield? See [R-031](R-031-self-improvement-gap-analysis.rsrch.md) for the rule chosen. | Owner |
