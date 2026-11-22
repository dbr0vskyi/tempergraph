# R-061 Councils: debate, voting and conformity among models

## Problem statement

The owner asked for "something like a council node". A council puts one question to several model sessions and combines their answers. This note collects what public work says about how to combine them: whether rounds of debate add over independent answers and a vote, what makes members conform, whether member identity should be hidden, and how diverse members should be. The answers set the defaults of the council unit ([CNL](../specs/71-council-unit.spec.md), [ADR-0063](../adr/0063-council-is-a-gated-step-with-engine-tallied-outcomes.adr.md)).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| C1 | Karpathy, *llm-council* README | Open-source project; the author calls it a weekend hack he will not support | https://github.com/karpathy/llm-council |
| C2 | Choi, Zhu, Li, "Debate or Vote: Which Yields Better Decisions in Multi-Agent LLMs?" (arXiv 2508.17536v2, 2025-10-23; NeurIPS 2025 poster) | Peer-reviewed paper | https://arxiv.org/html/2508.17536v2 |
| C3 | Wu, Li, Li, "Can LLM Agents Really Debate?" (arXiv 2511.07784v1, 2025-11-11) | Preprint | https://arxiv.org/html/2511.07784v1 |
| C4 | Choi et al., "An Empirical Study of Group Conformity in Multi-Agent Systems" (arXiv 2506.01332v1, 2025-06-02) | Preprint | https://arxiv.org/html/2506.01332v1 |
| C5 | Mansuri et al., "Multi-agent discussion gains less when dissent is withheld" (arXiv 2609.38324; runs August–September 2026; posting date not confirmed) | Preprint | https://arxiv.org/pdf/2609.38324 |
| C6 | Anthropic, "Building effective agents" (2024-12-19) | Vendor engineering guidance | https://www.anthropic.com/research/building-effective-agents |
| C7 | [R-045](R-045-evaluating-llm-judges-public-practice.rsrch.md) F3, F6, F9 (majority-vote judge ensembles, same-family errors, cross-family panels) | Earlier research note in this set | this folder |

The papers' later sections were read partly through extracted summaries; numbers taken from those parts are marked `supported`, not `confirmed`.

## Key findings

| # | Finding | Confidence |
|---|---|---|
| K1 | *llm-council* runs three stages: every member answers alone; each member ranks the others' answers with identities hidden "so that the LLM can't play favorites"; a separate chairman model writes the final answer from all of them. It does not say how rankings are aggregated and makes no quality claim (C1). | confirmed |
| K2 | Majority voting over independent answers accounts for most of the gain attributed to multi-agent debate; "in most cases, majority voting without any debate performs on par" with it. Debate alone does not raise expected correctness in the paper's model (C2). | supported (abstract and introduction verbatim; theory part through summary) |
| K3 | Debate does help on verifiable puzzles, but gains shrink as tasks get harder; member reasoning strength and **group diversity** drive success, while order and showing confidence add little (C3). | supported |
| K4 | Majority pressure suppresses correction: members facing a wrong majority self-corrected 3.6% to 34.4% of the time depending on the model (C3, summary). Agents align with numerically dominant or "more intelligent" peers, and conformity grows with the majority ratio (C4). | supported |
| K5 | Discussion overturns a wrong initial majority only when members withhold dissent rarely; telling agents not to withhold raises the gain (C5). | supported (one preprint) |
| K6 | Agreement between models is consistency, not correctness; same-family members share errors; a panel across families reduces single-family bias (C7). | supported |
| K7 | Voting (running one task several times for diverse outputs) is one of the two parallelization patterns in Anthropic's guidance, with the advice to add complexity only when it demonstrably helps (C6). | supported |

## Conclusions

1. The default council has **no debate rounds**: members answer independently and blind, and the outcome is a vote or a synthesis (K2, K7). Rounds are opt-in, capped at three, and their value is measured per workflow by the audit (K2, K3).
2. When rounds run, peers are shown **anonymized** (K1, K4), and every member must state where it still disagrees and whether it changed its position and why (K5). The engine records changes per round, so conformity is visible.
3. Members should differ in **model family or stance**; a council whose members bind to one family is flagged (K3, K6).
4. A vote is **tallied by the engine** by a declared rule, never by a model; a tie or a missed rule is a pause for a person, not a guess (K2; OVR-B6's rule that the engine derives outcomes).
5. A council's output is graded by the gate's **one independent judge**, like any step. The council does not replace calibrated judging (K6; [ADR-0045](../adr/0045-judges-accepted-on-labelled-error-rates.adr.md)).

## Open questions

| Question | Owner |
|---|---|
| Do rounds ever pay for themselves on delivery-pipeline questions (design choices, risk calls), which have no ground truth? Measured by the `council-rounds-no-gain` audit rule once 10 visits exist. | Owner, after first council workflows |
| Does a ranking stage (K1) beat a plain chair synthesis? No source measures it. | Owner, by a paired trial ([PRP](../specs/40-improvement-proposals.spec.md)) |
