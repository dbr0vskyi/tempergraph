# tempergraph

Tempered rails for AI workflows: an opinionated, LangGraph-based Python framework that enforces AI engineering best practices, so people who are not AI-engineering experts can still build good workflows.

> Status: release 1 is built and tested offline on stand-in executors; its live checks on a signed-in Claude Code are pending ([live checks](plugins/tempergraph/docs/plans/live-checks.plan.md)).

## What is here

This repository is a Claude Code plugin marketplace (`.claude-plugin/marketplace.json`):

| Plugin | What it is |
|---|---|
| `tempergraph` | The engine: the `tempergraph` CLI, its skills and hooks, and the Python engine under `engine/` |
| `tempergraph-monitor` | A Claude Mod that shows runs as they happen |
| `release-notes-tgraph` | Example workflow: one judged step (release notes since the last tag) |
| `doc-refresh-tgraph` | Example workflow: a script, a route on a value, a trip back, an approval and a finalizer |

Start at [plugins/tempergraph/docs/README.md](plugins/tempergraph/docs/README.md) for the design, and at the release plan for what release 1 holds.

## Idea

- Start from a definition of a good outcome.
- Enforce deterministic checks.
- Add LLM-as-judge checks for what rules cannot express.
- Wire in loopbacks and retries driven by the verdicts.
- Improve the workflow over time (self-improvement loop).
