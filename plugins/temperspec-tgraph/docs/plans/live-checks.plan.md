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
| TS-L1 | 2026-11-21 | 2.1.330 | failed | Rung 8 failed with no session and no spend: 32 findings `seed-unlabelled`. Each seed's `case.json` states its expectation under `seed` (`criterion_id`, `expected`, `reason`) and has `labels: []`; the engine's rung 8 reads the expected status from `labels` only. The owner's ruling the same day: rung 8 reads the `seed` block when a seed has no label for the criterion (engine SCF §2.5). Not run again since the change. Run in the project's cloud container, engine 0.0.1 |
| TS-L2 trial | | | not run | `--trial` implies rung 8, which fails as above |
| TS-L2 real run | 2026-11-21 | 2.1.330 | passed in part | Cloud container, engine 0.2.0, scratch Python repository with no overview spec and no remote, task "add a multiply function" with three acceptance criteria. The run finished with exit 0 and no pause for 2.01 USD reported: `prepare`, `setup` (overview spec and one component spec written), `triage`, `discovery`, `plan`, `code`, outcome gate, every judgement all `MET` (or `N/A`) with `gap: false`; one commit after each step; `pytest` 5 passed and `ruff` clean on the run's branch. The last stage reported `skipped` ("no remote named origin"), so the push and the draft pull request are not run |
