# A judge reaches an MCP server only through the engine's filtering proxy, and `claude` declares `judge_mcp` once the proxy is tested

## Context

[ADR `first-release-ships-the-claude-executor-only`](first-release-ships-the-claude-executor-only.adr.md) item 3 set `judge_mcp = false` on `claude` until the judge's filtering MCP proxy ships in release 2. The owner moved the proxy to release 3 on 2026-11-21 ([ADR `release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing`](release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md)) and accepted release 3's scope on 2026-11-22 ([ADR `release-three-composes-runs-in-parallel-and-grades-in-the-pipeline`](release-three-composes-runs-in-parallel-and-grades-in-the-pipeline.adr.md)); [research `release-three-readiness-and-gaps`](../research/release-three-readiness-and-gaps.rsrch.md) F6 lists it as ready for implementation. This record replaces item 3 of ADR `first-release-ships-the-claude-executor-only` and leaves the rest of that record standing. ADR `first-release-ships-the-claude-executor-only` is not edited.

Facts read in the code before phase R3-T8.1 builds it:

- `plugins/tempergraph/engine/src/tempergraph/executors/claude.py` (`judge_argv`) sends `--disallowedTools "mcp__*"` on every judge launch and writes no MCP configuration. `ClaudeExecutor` takes a step's MCP configuration as a path from its caller, and nothing supplies one.
- `plugins/tempergraph/engine/src/tempergraph/executors/capabilities.py` declares `judge_mcp` false on `claude`.
- `plugins/tempergraph/engine/src/tempergraph/run/guard.py` (`view_set`) adds a step's own `mcp:` tool to its judge's views when the judge executor declares `judge_mcp`. It has no view catalog, so turning the flag on alone would hand a judge a step's write tool.
- No engine code reads an operator's MCP server definitions.

Facts about the CLI: [research `claude-code-cli-headless`](../research/claude-code-cli-headless.rsrch.md) F5 (`system/init` lists MCP servers and their errors), F12 (`--tools` does not restrict MCP tools) and F15 (`--mcp-config` with `--strict-mcp-config`). The public documentation (https://code.claude.com/docs/en/mcp) adds that `--strict-mcp-config` loads only the servers passed with `--mcp-config`, that an entry without a `type` is a stdio server, that remote servers use `http` or `sse` and keep their OAuth tokens in Claude Code, and that a skipped `--mcp-config` entry appears in `mcp_server_errors`. It does not say whether a server that fails to connect appears there too.

What the specs already state: the judge launch and its proxy ([ECC-B3](../specs/executor-claude-code.spec.md)), the view catalog and the derived views ([GRD-B1, GRD-B7](../specs/independence-guard.spec.md)), the out-of-reach rendering ([GRD-B5](../specs/independence-guard.spec.md)), private configurations ([WSP-B5](../specs/workspace-and-concurrency.spec.md), [SEC-B12](../specs/security.spec.md)) and that a repository's own files grant a judge no tool ([SEC-B3](../specs/security.spec.md)). They leave open which servers the proxy may front. The open question of [EXI](../specs/executor-interface.spec.md) says remote servers rest on probe facts nobody has run, and proxying a remote server that authenticates with OAuth would mean the engine holding the person's credentials.

## Decision

We will take option A: build the filtering proxy that ECC-B3 specifies and declare `judge_mcp` true on `claude` in the change that builds it and passes the offline tests against stand-in MCP servers ([ECC-AC7, ECC-AC8, ECC-AC9](../specs/executor-claude-code.spec.md)). The record rests on these assumptions, each of which the owner may overturn:

1. The proxy fronts only a local (stdio) server that the operator's own MCP configuration defines. A server found only in a repository, a server not configured on the machine and a remote server stay deferred, and so does a server whose proxy fails to start ([ECC-B15](../specs/executor-claude-code.spec.md)).
2. A judge's MCP views come from the view catalog and never from a step's own tool ([GRD-AC6](../specs/independence-guard.spec.md)). The catalog lists only names the specs state, none inferred from a pattern or a hint, so a tool it does not list gives the judge no view.
3. A pass against a stand-in proves the capability built, not live. A live check against the pinned CLI stays a separate owner check, as the readiness rule of the docs README says.

## Options considered

### A. An engine-shipped stdio proxy per local view server, run by the CLI from a private strict configuration (chosen)

For: the server's write tools are never listed to the model, and [GRD-B8](../specs/independence-guard.spec.md) ranks tools absent from the session above calls refused by rule; the engine never holds a connection or a credential of its own; the same private-folder rules as every other executor configuration apply. Against: a new process type to ship and test; the engine must read the operator's MCP definitions; a remote server is not covered.

### B. Pass the server's own entry through and allow only the viewed tools by rule

For: nothing to ship, and a remote server that the CLI has signed in to would work. Against: the write tools stay present and listed, so a model that tries one has its whole judgement voided by the guard ([GRD-B2](../specs/independence-guard.spec.md)); it rests on a permission fact about the real binary that no probe has confirmed, and GRD-B8 ranks refusal by rule below absence.

### C. Keep `judge_mcp` false

For: nothing to build and no new surface. Against: every criterion that reads an MCP system stays UNVERIFIABLE; ECC-B6 already declares the capability true, and the owner has put the item in release 3.

### D. The engine connects to the server itself and filters in process

For: it would cover remote servers. Against: the engine would hold the person's tokens.

## Consequences

- A judge can check a claim against a local MCP system, and a deferral now happens only when the proxy cannot be given, not for every MCP view.
- The view catalog becomes live data: every real server whose tools a judge should see needs entries beside the old ones ([GRD-B7](../specs/independence-guard.spec.md)), which is a data-only change. Until a name is listed, its artifact stays out of reach, which is the safe state.
- Risk: switching the flag on without the catalog hands a judge a step's write tool. Limit: GRD-AC6 is a criterion of the same change, and the code step must prove it before the flag is set.
- Risk: the proxy's behaviour inside the real CLI (the session lists exactly the offered tools, a proxied tool runs without a prompt under `dontAsk`, a failed server is reported) is proven only against stand-ins. Limit: the capability is recorded as built, not live-proven, and the engine does not rely on the CLI's report of a failed server alone, because the documentation does not state that it reports one.
- Risk: the private configuration may hold a server's environment values, tokens included. Limit: it is created and removed under the rules of WSP-B5 and SEC-B12 and appears in no argv, log or error text.

## Revisit when

An operator needs a judge to view a remote MCP server, or a live check against the pinned CLI shows a tool the proxy did not offer or no report for a proxy that failed to start.
