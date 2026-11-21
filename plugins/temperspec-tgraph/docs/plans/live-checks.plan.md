# Live checks for temperspec

What temperspec still has to confirm on the owner's machine against a signed-in Claude Code. The offline suite covers the same package on stand-ins. A result is written into the table only from a run on the machine. It is never inferred, and a failure is kept as a finding. The engine's own list is its [live checks](../../../tempergraph/docs/plans/live-checks.plan.md); its row L-26 points here.

## Before you start

- The engine installed and its offline suite passing, as the engine's list says under "Before you start".
- `tempergraph workflows register plugins/temperspec-tgraph`.
- Run from a plain terminal, not from inside a Claude Code session.

## Rows

| Row | What | How | Passes when |
|---|---|---|---|
| TS-L1 | Judge seeds (`author verify` rung 8) | `tempergraph author verify plugins/temperspec-tgraph --judge-seeds --cap 10` | rung 8 `passed`: each of the 32 seeds under `evals/calibration/` is graded as its `case.json` expects, twice. A seed graded otherwise is a defect of the judge brief, the criterion's scale or the seed, and is fixed before any run |
| TS-L2 | Trial run (`author verify` rung 9), then a real run | In a scratch Python repository with `pytest` and `ruff` on PATH: `tempergraph author verify <path to plugins/temperspec-tgraph> --trial --case missing-config --cap 15`; then `tempergraph run temperspec "<a small task with its acceptance criteria>"` | the trial reaches the outcome gate; the real run sets the repository up when it has no overview spec, commits after every step, opens its pull request with the description of what to read, and its last stage reports `opened`, `reused`, `pushed` or `skipped` |

Until TS-L1 passes, every judged criterion is at uncalibrated trust.

## Results

| Row | Date | CLI version | Result | Notes |
|---|---|---|---|---|
| TS-L1, TS-L2 | | | not run | |
