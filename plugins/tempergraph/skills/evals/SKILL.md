---
name: evals
description: Check that a tempergraph workflow's checks, steps, judges and whole runs still do what they should. Use when someone asks to run evals, score or calibrate a judge, see whether a workflow is ready for stable mode, grade an eval result, or turn a judge's mistake into a test case. Never grades for the person and never writes a gold label itself.
---

# Evaluate a tempergraph workflow

The engine runs the suites and keeps the results. You choose what to run, say what it will cost before it
spends, read the report back in plain words, and hand every judgement call to the person. You know no
workflow: read the catalog with `tempergraph list`.

## Rules

- **Free first.** `tempergraph evals run <workflow> --kind check` and `tempergraph evals bar <workflow>` make
  no model call. Run them before anything that spends.
- **Say the cap before a live run.** Step, workflow and judge suites start model sessions. Name the cap and
  ask once; pass it as `--cap <usd>`. Without `--cap` a run stops at $20. A run that reached its cap is
  `partial`: say so and do not read its rates as final.
- **A person grades what no grader could.** A `needs_person` result waits for
  `tempergraph evals grade <result> --pass --reason '…'` or `--fail`. Show the person the case and ask; pass
  their words as the reason. Never choose pass or fail yourself.
- **A person writes gold labels.** `tempergraph evals label` records who reviewed a case. Ask for each
  expected status and its reason; a label you invent keeps the case a candidate and teaches the judge nothing.
- **Rates carry the judge's state.** When you quote a pass rate graded by a judge, say the judge's state from
  `evals bar` with it. An `unscored`, `stale` or `below_bar` judge makes the rate a raw count, not a result.

## Procedure

1. **Where it stands.** `tempergraph evals bar <workflow>` lists each judged gate (and each risk level) with
   its state and what it still needs. `tempergraph evals report <workflow>` lists each suite's latest run,
   results waiting for a person, cases ready to move from capability to regression, and cases that never
   passed (check those cases first: they are usually broken).
2. **Checks.** `tempergraph evals run <workflow> --kind check`. Every check fixture runs with both line-ending
   conventions. A failing case here blocks the workflow's stamp, so fix the check or the fixture first.
3. **Judges.** For a gate that is `unscored` or `stale`: `tempergraph evals score <workflow> <gate> --cap <usd>`,
   and `--level <name>` for each risk level `evals bar` lists. A judge needs reviewed cases first; when
   `evals bar` asks for more known-bad or known-good cases, help the person write them and label them with
   `tempergraph evals label <workflow>/<gate>/<case> --criterion <id> --expected <status> --reason '…'`.
4. **Steps and whole runs.** `tempergraph evals run <workflow> --kind step --cap <usd>` and
   `--kind workflow`. Add `--role regression` to run only what must keep passing. Report `pass^k` (every
   trial of a case passed) beside the plain pass rate: a step that passes once in three is not working.
5. **Misses.** When a run showed a judge was wrong, `tempergraph evals harvest <workflow> <gate>` writes a
   local case candidate for each recorded disagreement. For the `outcome` gate it also writes one for each
   escape (a `met` run a person sent back), holding the pull request's identity and counts and no text. A candidate holds no request text and is not in the
   package: the person reviews it, copies it into the package's calibration cases and labels it.
6. **Drift.** `tempergraph evals replay <workflow> --cap <usd>` reruns the judges on the kept cases and shows
   where today's statuses differ from the recorded score. A change means the judge moved: re-score it.

## Reading results

| Status | Means | Do |
|---|---|---|
| `passed`, `failed` | Decided by code, by an accepted judge, or by a person | Report it with who graded |
| `needs_person` | No grader could decide; counts in no rate | Ask the person, then `evals grade` |
| `paused` | The trial stopped for a person and the case recorded no answer | Say which case; the author adds an answer or fixes the case |
| `invalid` | The case cannot run (a missing base commit, a check without fixtures) | Report the reason |
| suite `incomplete` | A regression suite with a result still waiting | Not a pass: say what waits |
| suite `stale` | The prompt, model or judge changed since the run | Offer to run it again |
