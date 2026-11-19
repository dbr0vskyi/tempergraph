---
title: Lifecycle and evals
type: component
status: review
prefix: LIF
adrs: [0003, 0007, 0018, 0021]
---

# Lifecycle and evals

## 1. Overview

The model-free tooling around the runtime: how the engine and its workflows are installed, upgraded, checked against each other and against the executors' CLIs and libraries, drawn and tested. Decisions are made by content and data, never by a version string or prose.

## 2. Contract

| Capability | Rule |
|---|---|
| Install | One managed Python 3.11+ virtual environment per machine, outside the plugin cache; the CLI on PATH through a shim |
| Update | The `update` verb installs from the invoked package's staged copy with constants-only argv; currency is a hash of the engine's source files; it refuses a downgrade |
| Manifest reconcile | Repoints stale entries, registers installed workflow packages, never deletes an entry |
| Compatibility changelog | Plain data per engine release: breaking flag, migrate steps, detect rules (patterns over code and prompts) |
| Workflow stamp | The engine release a workflow was last verified against; written only by `upgrade-check --stamp` after every check passes |
| Executor compatibility | A table per executor: the version range its probe facts or contract tests were recorded for (the CLI for `claude` and `antigravity`; the SDK package and its bundled CLI for `agent-sdk`; the client library and API version header for `messages-api`); outside it, a warning and projected capabilities ([EAG-B7](12-executor-antigravity.spec.md)) |
| Diagram model | Versioned JSON with a digest, generated from the spec and verified against the compiled graph; renderers are pure |
| Evals | Deterministic scenarios (shell assert, no model) and rubric scenarios (input and rubric; pass only from a recorded score whose digests match) |
| Judge readiness report | Per gate: criteria without method, vague words, severity balance, calibration cases, last score per judge executor; grades `ready`, `needs cases`, `needs work` |
| Harvest | `evals harvest <gate>` turns a recorded judge miss (a gate escape, a person's pushback, an audit disagreement) into a calibration case: subject paths, the criterion and the expected status; local only, scrubbed, reviewed by a person before it is committed |
| Live judge scoring | `evals score <gate> --executor <name>` runs the gate's judge on its calibration cases against a fixed subject and records the score per executor and alias, so a judge moved to another executor is scored before a gate relies on it |
| Replay batch | `evals replay <workflow>` reruns the judges of past cases (kept subjects, no step session) and reports agreement with the recorded verdicts; spends judge calls only |
| Prompt lint | A model-free check over templates, judge briefs and skills: vague words, self-grading requests, rule-like branching, tool names that are not the step's mapped names, instructions to ask or wait for a person in an unattended step, briefs that tell the judge to accept the step's word about a system it cannot read, references to skills, agents, files or tools that do not exist, and model-facing files or table cells over a size limit; part of `validate`, and shown by `audit` ([AUD](55-workflow-audit.spec.md)) |
| Update output | `update --json` prints one JSON object per line, one thing per line (step, result, path), so a skill reads it without parsing prose |

## 3. Behaviours

**LIF-B1 Same version, different code.** Given an installed engine with the same version string as the plugin but different source, when `update` runs, then it reinstalls, because the hash differs.

**LIF-B2 Stamp only when clean.** Given a workflow whose detect rules match code a breaking release changed, when `upgrade-check --stamp` runs, then it prints each hit with its changelog entry and writes no stamp.

**LIF-B3 Diagram currency by digest.** Given a committed diagram after a CRLF checkout, when the currency test runs, then it passes, because digests, not bytes, are compared.

**LIF-B4 Executor conformance in the eval set.** Given a workflow package, when its evals run, then its scenarios run against scripted stand-ins of every executor the workflow names, plus `claude` as the reference, so a workflow that only works on one is visible before a live run.

**LIF-B5 Rubric score goes stale.** Given a rubric scenario scored last week, when its judge brief changes, then the scenario reads `stale` and is manual until re-scored.

**LIF-B6 Stable mode needs ready gates.** Given a workflow declaring `stable`, when validated, then every gate must grade `ready` in the readiness report for the judge executor it will run on; otherwise validation refuses it.

## 4. Error conditions

| Condition | Result |
|---|---|
| No Python 3.11+ found, or an alias stub | Installer stops and says how to install one |
| Package installer interrupted | Exit 1, nothing stamped |
| A manifest entry pointing at a missing folder | Reported; nothing removed |

## 5. Design notes

- Every executor changes between releases (Claude's `-p` permission default; `agy`'s permission matching and self-update; the Agent SDK's bundled CLI; the Messages API's tool and parameter versions), so their versions are part of compatibility, not an afterthought ([ADR-0007](../adr/0007-two-first-class-executors.adr.md), [ADR-0018](../adr/0018-add-messages-api-and-agent-sdk-executors.adr.md)).
- Skills are evaluated with Claude Code's plugin eval; no harness for Antigravity skills is assumed.

## 6. Acceptance criteria

- [ ] LIF-AC-1 `update` decides currency by content hash (test with equal versions, different files).
- [ ] LIF-AC-2 The diagram-currency test fails on a shape change and passes on a line-ending change.
- [ ] LIF-AC-3 A rubric scenario passes only from a score whose digests match.
- [ ] LIF-AC-4 The executor compatibility table is read by preflight and shown by `executors`.
- [ ] LIF-AC-5 A harvested case contains no request text and is never written outside the state root until a person commits it.
- [ ] LIF-AC-6 Prompt lint finds each planted defect of its fixture set and nothing in the shipped workflows.

## Open questions

None.

## References

