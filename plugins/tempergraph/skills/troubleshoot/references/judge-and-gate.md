# Judge, gate, retries, trips back and pauses

Each gated unit runs in order: the step, then the check (no model), then the judge (a fresh read-only session), then the gate, which derives the verdict.

| Record | Holds |
|---|---|
| `check` | The check's result (`PASS`, `FAIL`, `MAYBE`) and its findings, each naming a criterion. A failing check skips the judge |
| `judgement` | One status per criterion (`MET`, `PARTIAL`, `UNMET`, `N/A`, `UNVERIFIABLE`) with evidence, the confidence, and whether there was a gap |
| `gate` | The verdict and why: proceed, retry, back to an earlier unit, or ask a person |
| `pause`, `human` | What the run asks the person, and the decision given on resume, with its caller |

## Reading a verdict

- A blocker `PARTIAL` or `UNMET` fails the gate. `MET` without evidence counts as `PARTIAL`.
- An unmet warning passes, with a note the next step sees.
- A blocker `UNVERIFIABLE` goes to a person.
- A failed step never proceeds. A proceed straight after a failed step record is a defect to report, not a fact to explain.

## Retries and trips back

A retry starts the step again with the gate's findings. A trip back replays every unit from the target, so a wrong attribution costs a whole replay. A revisited step starts with no earlier verdict; its files stay. The retry budget is per unit; when it is spent the unit's `on_budget_spent` policy decides (stop, or ask a person).

## A judge that seems wrong

Compare the judge's evidence with the artifact it names. A judge is `uncalibrated` until calibration accepts it, so its grade is a strong hint, not proof. `tempergraph outcome show <workflow> --runs` shows how often each criterion was met and where people disagreed. Suggest the person record the disagreement; never change the criteria yourself.
