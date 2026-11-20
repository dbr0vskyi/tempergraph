---
title: Security posture
type: component
status: ready-for-implementation
prefix: SEC
adrs: [0006, 0010, 0011]
---

# Security posture

## 1. Overview

How the engine keeps operator input, model output and secrets away from process launches, file paths and published text. Nothing a person typed reaches a process launch; every child dies with the engine; anything published is metadata, scrubbed. This spec owns contract C9 and the launch rules that contract C3 relies on.

## 2. Contract

### 2.1 Launch rules

| Rule | Applies to |
|---|---|
| Argv is a list built from constants and checked values; no shell | Every launch |
| The prompt and any person-typed value travel on stdin or through a hand-off ticket, never argv or environment | Every launch |
| Every launch site is listed and pinned by a source-scan test (the call and the keywords it must not pass) | Every module |
| A detached child receives a random ticket naming a hand-off file; it re-validates every value | Self-improvement, batch judge, schedule, lifecycle hooks |
| A worker receives its request document on stdin and re-validates every value against the same rules | SDK and API workers ([ADR-0019](../adr/0019-in-process-executors-run-in-a-worker-process.adr.md)) |

### 2.2 Sanctioned launch sites

| Site | Launches |
|---|---|
| Session launcher | `claude`, `agy`, and the engine interpreter with the constant worker modules `tempergraph.executors.sdk_worker` and `tempergraph.executors.api_worker` ([EXI](10-executor-interface.spec.md)) |
| Agent SDK | The SDK's bundled or pinned Claude Code CLI, started by the SDK inside the SDK worker; options built from constants |
| Tool host command runner | A declared command prefix as list argv, inside the API worker ([THS §2.5](22-tool-host.spec.md)) |
| Tool host MCP client | Local MCP servers from the engine's MCP file, inside the API worker |
| Antigravity gatekeeper | Started by `agy` itself from an engine-written hooks file; constant path |
| Filtering MCP proxy | Started by the judge's CLI from an engine-written config; constant entry point |
| Git reader | `git` with constant arguments and refs on stdin |
| Detached child launcher | The engine CLI with a ticket; the schedule tick's `run` and `orchestrate start` among them ([TCK §2.2](84-schedule-ticks-and-unattended-fires.spec.md)) |
| Schedule trigger writer | The optional `os` adapter's one per-user entry (LaunchAgent, systemd user unit, crontab line, Task Scheduler task) and the plugin hook's loop start, holding the shim's absolute path and `schedule loop` or `schedule tick` only ([TCK §2.1](84-schedule-ticks-and-unattended-fires.spec.md)) |
| Updater | `pip` with constants only |
| Wait notification | The operator's own command, a named, bounded exception with its own test |
| Check worker | The engine interpreter with the constant module `tempergraph.checks.worker`; the context document on stdin ([CHK §2.6](75-check-contract-and-command-runs.spec.md)) |
| Workflow command runner | A command a check or finalizer resolved through the workflow's allow-list, as list argv, stdin closed, output to a file, process tree ended at its limit ([CHK §2.3](75-check-contract-and-command-runs.spec.md), [FIN §2.2](78-finalizer-contract.spec.md)) |

### 2.3 Scrubbing and the publish boundary

- Persisted and published text passes a pattern scrubber first; patterns are a floor, not the control.
- **The publish boundary is a file boundary.** The request, a person's feedback and step outputs go to a local evidence file. No filing or publishing code may import or open it.
- Findings, ledger rows, issue bodies and pull-request text carry names, counts, hashes and words from fixed lists only.

### 2.4 Executor configuration secrets

| Item | Rule |
|---|---|
| Judge-only credentials | An operator file of name-value lines laid over a judge's environment only; records show names, never values |
| Private MCP configs and Antigravity session homes | Owner-only folder under the state root, one per session, removed in a `finally` block; never in argv, a log or an error text |
| Antigravity API key | Placed into the session home's settings or environment from the credentials profile; never argv |
| Copied sign-in files (if P-AG-1 needs them) | Copied into the session home only, owner-only, removed after the session |
| Anthropic API keys and cloud credentials for the library executors | Read by the client library from the worker's environment; never in the request document, a log, an error text or the checkpoint. The tool host removes them from the environment of every command it runs |

## 3. Behaviours

**SEC-B1 Typed alias stops at a lookup.** Given an operator who types `--model large`, when a session launches, then the typed text selects a binding-table entry and only that entry's constant value reaches argv.

**SEC-B2 Canary.** Given a distinctive string planted in every free-text field (request, feedback, step output, environment, a remote URL), when a run completes and files, then the string appears in no argv, issue body, ledger row, finding, hand-off, report or overlay.

**SEC-B3 Project files cannot widen reach.** Given a repository that commits `.agents/hooks.json`, `.agents/mcp_config.json`, `.claude/settings.json` or `.mcp.json`, when a judge session runs, then none of those files grants the judge a tool: the Claude Code and Agent SDK judges load no setting source, the Messages API judge reads no configuration file at all, and the Antigravity judge (once allowed) is checked by the guard, with project-scope hooks treated as untrusted input.

**SEC-B4 Paths stay inside.** Given a check that resolves a relative path, when it runs, then it resolves against the workspace in the state it was given, and a git ref must match a strict pattern and travels on stdin.

## 4. Error conditions

| Condition | Result |
|---|---|
| A launch site not in §2.2 | Source-scan test fails |
| Scrubber raises | The text is dropped and replaced by a fixed word; the run continues (contract C2) |

## 5. Design notes

- Antigravity's configuration surface includes workspace files a repository controls (`.agents/`). Because the engine cannot point `agy` away from them by flag, the guard, not the configuration, is what the judge's independence rests on ([ADR-0010](../adr/0010-judge-isolation-per-executor.adr.md)).
- The terminal sandbox of `agy` and Claude Code's permission rules are defence in depth, never the only control.

## 6. Acceptance criteria

- [ ] SEC-AC-1 Every launch site is enumerated and pinned by a source-scan test.
- [ ] SEC-AC-2 The canary test of SEC-B2 passes for runs on every executor.
- [ ] SEC-AC-3 No filing module imports or opens the evidence file (source test).
- [ ] SEC-AC-4 A command run by the tool host sees none of the executor's credential variables (planted-key test).
- [ ] SEC-AC-5 Private configs and session homes are owner-only and removed on every exit path, including a raised error.

## Open questions

| Question | Owner | Release 1 default |
|---|---|---|
| Do workspace `.agents/hooks.json` files of the repository run inside an Antigravity session whose home is isolated? Their effect on a judge must be known before Antigravity hosts judges. | Executor implementer (P-AG-1) | Not reached: `antigravity` ships in release 3 ([ADR-0091](../adr/0091-first-release-ships-the-claude-executor-only.adr.md)) and hosts no judge until P-AG-1 passes |

## References

