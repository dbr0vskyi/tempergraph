# ADR-0050 Audit a workflow with an advisory, read-only, model-free verb over three layers

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked for a mechanism, maybe a CLI command, that audits a workflow and analyzes it for issues, aimed at the most common reasons runs fail, are interrupted, retry, get stuck or spend much. [R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) ranks those causes and finds that they need three kinds of evidence: the workflow definition, the host and target repository, and recorded runs. The design already has `validate` ([WFM](../specs/02-workflow-model.spec.md)), which refuses before spend, and several model-free analyses with their own owners. Nothing puts them together for one workflow or covers the host and the run history of a workflow as a whole.

## Decision

We will add `tempergraph audit <workflow>` ([AUD](../specs/55-workflow-audit.spec.md)):

1. **Advisory.** It never refuses a start or a resume and is never called by them. `validate` stays the only gate.
2. **Read-only and model-free** (contract C13). Its only child processes are the read-only executor probes and a host-speed probe under a 30 s budget.
3. **Three layers**, `definition`, `host` and `history`, each rule declaring the one it needs; a layer whose inputs are missing is reported as skipped, never as clean.
4. **Exit 0** by default; `--fail-on` makes it exit 6 for CI. JSON and SARIF output.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| A separate advisory verb over three layers (chosen) | Reads host and history without slowing or loosening the start gate; one place for an author or CI to look | One more verb |
| Extend `validate` with more rules | No new verb | Validation guards every start; host probes and history reads would make starts slow and non-deterministic, and a ranked, sometimes wrong finding cannot refuse a run |
| A model-driven review workflow | Can judge prose (stale docs, criteria that fail on a second visit) | Spends money on every audit, breaks C13, and its own judge needs calibration |
| Leave it to the troubleshooter skill | Exists; no new verb | Run-level and after the fact; its findings are prose, not ids CI can gate on |

## Decision rationale

| Criterion | Advisory verb | Extend validate | Model review | Troubleshooter |
|---|---|---|---|---|
| Catches host and history causes (R-050 C2, C3) | yes | no | partly | yes |
| Keeps the start gate fast and deterministic | yes | no | yes | yes |
| Free to run often | yes | yes | no | no |
| Machine-readable for CI | yes | yes | partly | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | "Audit the workflow" means one workflow package and its runs, not the engine. Engine defects found in runs are shown but not diagnosed. | AUD, ARC |
| A2 | Starting a login shell and the executor probes counts as read-only, as `executors --probe` does today ([CLI-AC-1](../specs/17-engine-cli.spec.md)). | AUD §2.1 |
| A3 | A new exit code 6 is acceptable for an advisory verb, rather than reusing 4 or 5, which mean a run ended. | CON §2.9 |

## Consequences

- Positive: an author sees, before the first run, most of the shapes that cost a run attempts, pauses and hours; CI can gate a workflow change on it.
- Negative: a second place where findings appear next to `validate`; the report must say which is which.
- Risk: authors treat a clean audit as proof of quality. Mitigation: the report lists skipped layers and rules, and judge quality stays with the readiness report and calibration.

## Revisit when

A model-assisted review is wanted as a separate built-in workflow (AUD open question), or the first 20 runs of a real workflow show which rules fire falsely.
