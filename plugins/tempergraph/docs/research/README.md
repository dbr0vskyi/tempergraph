# Research notes

Background findings that answer an unknown, so a spec or decision record does not rest on assumption. Rules: [docs README](../README.md#research-rules).

| Note | Answers | Feeds |
|---|---|---|
| [R-001 Claude Code CLI as a headless executor](R-001-claude-code-cli-headless.md) | How `claude -p` behaves as a child process: I/O, events, cost, tools, permissions, sessions. | [ECC spec](../specs/11-executor-claude-code.md), [ADR-0007](../adr/0007-two-first-class-executors.md), [ADR-0010](../adr/0010-judge-isolation-per-executor.md) |
| [R-002 Antigravity CLI as a headless executor](R-002-antigravity-cli-headless.md) | How `agy -p` behaves as a child process, and what it cannot do per invocation. | [EAG spec](../specs/12-executor-antigravity.md), [ADR-0010](../adr/0010-judge-isolation-per-executor.md), [ADR-0011](../adr/0011-isolated-config-home-for-antigravity.md), [ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.md) |
| [R-003 Executor capability matrix](R-003-executor-capability-matrix.md) | Which capability each CLI provides, and what the engine must own. | [EXI spec](../specs/10-executor-interface.md), [ADR-0006](../adr/0006-executors-as-capability-adapters.md), [ADR-0008](../adr/0008-portable-model-aliases.md), [ADR-0013](../adr/0013-cross-executor-judging.md) |

The engine's earlier framework comparison (LangGraph against the alternatives) is not repeated here; it is in and is decided in [ADR-0002](../adr/0002-langgraph-graph-runtime.adr.md).
