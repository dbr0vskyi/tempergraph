# Steps, timeouts, cost and infrastructure failures

Read `run.jsonl` for the unit: `unit_entered`, then per attempt `attempt_start`, the session's result, `check`, `judgement`, `gate`, and at the end `run_exit` with its `reason`.

| Look at | It tells you |
|---|---|
| The session folder `sessions/<unit>.<attempt>.step/` | What the step was given and what it answered; the session result's exit, usage and cost |
| `run_exit` `reason` with exit 5 | A spent budget (retries, cost, time) or an infrastructure failure (the executor did not start, lost its sign-in, the network failed) |
| `engine_error`, `write_failed` | The engine itself failed; exit 1, a bug to report with the record |
| `settings_resolved` | The effective timeouts, caps and models of this run, and where each value came from |

## Slow, hung or killed

Compare the attempt's duration with the timeout of earlier passing attempts of the same step. A step that passes in 495 s and is killed at 600 s has a limit that is too short. A step that always runs to its limit is hung or loops. An idle limit ends a session that printed nothing for that long.

## Cost

Cost comes from the executor's own report where `tempergraph executors` shows `reports_cost`; otherwise it is an estimate. A cost cap ends the session at the cap; the record says so.

## A different model than asked

`settings_resolved` names the model alias of each step and judge and the layer that set it. An alias is bound by the executor; a fallback model, if allowed, shows in the session result.

## Infrastructure

`tempergraph executors --probe` shows whether `claude` is installed, signed in and at a tested version (`compat`). Exit 5 after an infrastructure failure never offers "proceed": the person fixes the cause, then resumes.
