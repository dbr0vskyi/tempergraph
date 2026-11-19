# ADR-0010 Judge isolation is a declared, probe-gated capability per executor

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A judge must be read-only: it reads the workspace and allowed views but cannot change files or external systems ([ADR-0005](0005-independent-judge-engine-verdict.md)). Claude Code restricts a session by documented flags (`--tools`, `--disallowedTools "mcp__*"`, `--strict-mcp-config`, `--setting-sources`, `--permission-mode dontAsk`) ([R-001](../research/R-001-claude-code-cli-headless.md)). Antigravity has no per-invocation restriction flag; plan mode is not an enforcement boundary; restriction can only come from config files and hooks under its config home, and whether that holds in headless mode is not documented ([R-002](../research/R-002-antigravity-cli-headless.md)). The independence guard ([GRD](../specs/06-independence-guard.md)) checks after the fact; it cannot undo a write to an external system.

## Decision

We will make judge isolation a capability each executor declares (`restricts_judge_tools`), backed by named probes. A capability that rests on an unconfirmed fact is declared **false** until its probe result is recorded for the installed CLI version. Preflight refuses a gated step whose judge executor does not declare it (contract C15). The guard runs on every judge session regardless, as a second line.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Declared capability, false until probed (chosen) | No judge runs with an unproven boundary; honest per executor | Antigravity cannot host judges until its probes pass |
| Trust the guard alone | Works on both today | Detects after the fact; an external write cannot be undone |
| Trust prompt instructions ("do not edit") | Zero setup | Not a boundary; models comply unevenly |
| Run judges in an OS sandbox (container, read-only mount) | Strong, CLI-independent | Heavy setup per machine; MCP and network access still need rules; out of scope for the first release |

## Decision rationale

| Criterion | Probe-gated | Guard alone | Prompt | OS sandbox |
|---|---|---|---|---|
| Prevents external writes | yes | no | no | partly |
| Works on Claude today | yes | yes | yes | yes |
| Works on Antigravity today | no (until probes) | yes | yes | yes |
| Setup cost | low | none | none | high |

## Consequences

- Positive: a pass always means a read-only judge, whichever executor ran it.
- Negative: probe facts expire with CLI versions. Mitigation: the engine keeps the CLI versions each fact was recorded for and warns outside that range ([ADR-0007](0007-two-first-class-executors.md)).
- Risk: a probe passes but a later code path (for example a subagent) escapes. Mitigation: P-AG-3 covers subagents; the guard still compares workspace state before and after each judge session.

## Revisit when

An OS-level sandbox becomes cheap to require on every operator machine, or Antigravity documents tool restriction per invocation.
