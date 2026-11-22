# ADR-0075 Checks get a defined context and an engine command runner

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

Every gate starts with a deterministic check, and the design leans on it: a FAIL costs no judge, and the judge reads the check's evidence rather than the step's claim. Yet what a check receives, what it may do and how it runs a command were never specified ([R-011](../research/R-011-design-gap-review.rsrch.md) U1). temperspec's code gate runs the plan's own verification commands under a time budget, kills hung process trees, treats a killed run as "not finished" rather than failed, reuses a result on an unchanged tree, records a commit the release gate later measures from, and names the criterion, place and change of each failure ([R-075](../research/R-075-temperspec-needs-against-the-engine.rsrch.md) T24 to T31). Each of those was an observed failure or a measured cost in the reference.

## Decision

We will give a check a typed **context** (workspace, main checkout, request, artifacts, values, earlier facts, engine-computed git facts, resolved settings, a deadline) and an engine **command runner** (`resolve` through the workflow's `command_resolver`, and `run` with list argv, output to file, process-tree kill, a start guard, "finished" exit codes per prefix, and reuse keyed by the tree), and let a check return per-criterion **findings** and bounded **facts**. Checks run in a check worker process with a whole-check limit. The engine owns the mechanics; the workflow owns which commands run and what their results mean ([CHK](../specs/75-check-contract-and-command-runs.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Context plus engine runner, worker process (chosen) | One audited launch site; timeouts and kills the engine enforces; reuse and evidence the same for every workflow; findings feed the retry and the audit | A new launch site and a process per check |
| Leave checks as free callables | No engine work | Every workflow re-solves process trees, pipes held open by children, path leaks in evidence; the gate and the plan check can disagree, as they did in the reference |
| Checks run only declared script units before the judge | Reuses SCR | A check needs results the script cannot judge (exit meaning, not-finished, facts); doubles the declarations |
| Run checks in-process with a cooperative deadline | No process start | A check whose own code hangs cannot be stopped |

## Decision rationale

| Criterion | Context and runner | Free callables | Script units | In-process |
|---|---|---|---|---|
| Hung command tree ended | yes | per workflow | yes | yes |
| Hung check code ended | yes | no | n/a | no |
| Plan check and gate agree on a command | yes, one function | no | partly | yes |
| Failure names criterion, place, fix | yes | no | no | yes |
| Cost | one interpreter start per gate | none | none | none |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| K1 | One interpreter start per gate (about a second) is small against a gate's judge session. | CHK-B16 |
| K2 | A workflow can state per command prefix which exit codes are results; without that, any normal exit is one. | CHK-B12, CHK-B13 |

## Consequences

- Positive: temperspec's test run becomes workflow policy over engine mechanics; every workflow's checks gain the same safety and evidence rules.
- Positive: findings with criterion ids let the self-improvement loop and the audit cluster check failures by criterion, not only judge failures.
- Negative: SSN-B8, SSN-B9, SSN-B10 grows (`findings`, `facts`), and SEC lists one more launch site.
- Risk: reuse returns a stale result when a command reads outside the tree. Mitigation: the key covers head, status and the digest of changed and untracked files; a workflow passes `reuse=False` for commands that read elsewhere.

## Revisit when

A measured workflow shows check worker starts above 5% of a run's wall time.
