# Walking a person through a pause (exit 3)

Read the JSON the run printed (`payload`). Show, in this order:

1. **Which unit paused and why**: `payload.kind` and `payload.reason`. Tell apart the common kinds, because most
   pauses are not judgement calls:
   - a review or approval gate: the person judges the output;
   - a spent retry or loop budget: the step could not satisfy its gate; say what kept failing;
   - a tool or permission refusal: the workflow did not declare what the step needed;
   - a `BLOCKED` line: only a person can provide what the step asks for.
2. **The blockers**, one line each, with the criterion they fail, as the payload gives them.
3. **Where the output is**: the workspace path and the artifact keys.
4. **The decisions** the payload lists in `payload.decisions`, and only those:
   - `proceed`: accept the output and go on;
   - `retry`: run the step again, optionally with `--feedback '…'` from the person;
   - `back:<unit>`: send the run back to an earlier unit;
   - `stop`: end the run.

Then wait for the person's word. Do not recommend `proceed` for a pause that follows an infra failure: nothing
was judged.

When they decide, resume with their word and `--relayed`:

```
tempergraph resume <workflow> <thread> --decision <word> --relayed
```

Feedback for the next attempt goes in `--feedback '…'` (or `--feedback-file <path>` for long text). A ruling
that should hold on every later attempt is `--ruling`. Pass the person's text as one quoted word.

If the resume exits 3 again, start over from the top of this page for the new pause.
