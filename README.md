# tempergraph

Tempered rails for AI workflows: an opinionated, LangGraph-based Python framework that enforces AI engineering best practices, so people who are not AI-engineering experts can still build good workflows.

> Status: early concept.

## Idea

- Start from a definition of a good outcome.
- Enforce deterministic checks.
- Add LLM-as-judge checks for what rules cannot express.
- Wire in loopbacks and retries driven by the verdicts.
- Improve the workflow over time (self-improvement loop).
