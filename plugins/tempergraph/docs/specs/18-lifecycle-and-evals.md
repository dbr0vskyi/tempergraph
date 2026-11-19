---
title: Lifecycle and evals
type: component
status: review
prefix: LIF
adrs: [0003, 0007]
---

# Lifecycle and evals

## 1. Overview

The model-free tooling around the runtime: how the engine and its workflows are installed, upgraded, checked against each other and against the two CLIs, drawn and tested. Decisions are made by content and data, never by a version string or prose.

## 2. Contract

| Capability | Rule |
|---|---|
| Install | One managed Python 3.11+ virtual environment per machine, outside the plugin cache; the CLI on PATH through a shim |
| Update | The `update` verb installs from the invoked package's staged copy with constants-only argv; currency is a hash of the engine's source files; it refuses a downgrade |
| Manifest reconcile | Repoints stale entries, registers installed workflow packages, never deletes an entry |
| Compatibility changelog | Plain data per engine release: breaking flag, migrate steps, detect rules (patterns over code and prompts) |
| Workflow stamp | The engine release a workflow was last verified against; written only by `upgrade-check --stamp` after every check passes |
| CLI compatibility | A table per executor: the CLI version range its probe facts were recorded for; outside it, a warning and projected capabilities ([EAG-B7](12-executor-antigravity.md)) |
| Diagram model | Versioned JSON with a digest, generated from the spec and verified against the compiled graph; renderers are pure |
| Evals | Deterministic scenarios (shell assert, no model) and rubric scenarios (input and rubric; pass only from a recorded score whose digests match) |
| Judge readiness report | Per gate: criteria without method, vague words, severity balance, calibration cases, last score; grades `ready`, `needs cases`, `needs work` |

## 3. Behaviours

**LIF-B1 Same version, different code.** Given an installed engine with the same version string as the plugin but different source, when `update` runs, then it reinstalls, because the hash differs.

**LIF-B2 Stamp only when clean.** Given a workflow whose detect rules match code a breaking release changed, when `upgrade-check --stamp` runs, then it prints each hit with its changelog entry and writes no stamp.

**LIF-B3 Diagram currency by digest.** Given a committed diagram after a CRLF checkout, when the currency test runs, then it passes, because digests, not bytes, are compared.

**LIF-B4 Executor conformance in the eval set.** Given a workflow package, when its evals run, then its scenarios run against scripted stand-ins of both executors, so a workflow that only works on one is visible before a live run.

**LIF-B5 Rubric score goes stale.** Given a rubric scenario scored last week, when its judge brief changes, then the scenario reads `stale` and is manual until re-scored.

**LIF-B6 Stable mode needs ready gates.** Given a workflow declaring `stable`, when validated, then every gate must grade `ready` in the readiness report; otherwise validation refuses it.

## 4. Error conditions

| Condition | Result |
|---|---|
| No Python 3.11+ found, or an alias stub | Installer stops and says how to install one |
| Package installer interrupted | Exit 1, nothing stamped |
| A manifest entry pointing at a missing folder | Reported; nothing removed |

## 5. Design notes

- Both CLIs change between releases (Claude's `-p` permission default; `agy`'s permission matching and self-update), so CLI versions are part of compatibility, not an afterthought ([ADR-0007](../adr/0007-two-first-class-executors.md)).
- Skills are evaluated with Claude Code's plugin eval; no harness for Antigravity skills is assumed.

## 6. Acceptance criteria

- [ ] LIF-AC-1 `update` decides currency by content hash (test with equal versions, different files).
- [ ] LIF-AC-2 The diagram-currency test fails on a shape change and passes on a line-ending change.
- [ ] LIF-AC-3 A rubric scenario passes only from a score whose digests match.
- [ ] LIF-AC-4 The CLI compatibility table is read by preflight and shown by `executors`.

## Open questions

None.

## References

