# Phases 7 to 9: approval, scaffold, verify

## Phase 7: one yes on three things together

1. `tempergraph author check <id>` has no error and an empty `sufficiency`.
2. `tempergraph blueprint draw <session folder>/blueprint.json --outcome <session folder>/outcome.json`, and show the printed Markdown as it is: the diagram, the units table, the outcome table, the verification table with its unverified section, and the defaults.
3. Ask for one yes on the drawing and both tables. Any change redraws and asks again.

On the yes, run `tempergraph author approve <id> 7`.

## Phase 8: scaffold

`tempergraph scaffold <id> --out <folder>`, where the folder is where the person keeps the workflow's source (empty, or new). Show `to_write`: each hand-written check and routing default the person or you must complete. Write them now, in the package, then continue.

## Phase 9: verify, register, stamp

`tempergraph author verify <folder> --json`. It runs, and stops at the first failing rung:

| Rung | When it fails |
|---|---|
| 1 Load and validate | Show each finding and fix the package. A criteria lint error means the outcome needs the guidance ladder again |
| 2 Blueprint comparison | Each difference says what moved. Fix the workflow, or change the blueprint with the person's yes and record the accepted difference as a decision |
| 3 Literals | A ticket id, URL, e-mail, path or a run of words from one case. Generalise it, or record a decision with its `literal_digest` |
| 4 Generated tests | Fix the package: a check fixture, a summary, a start example |
| 5 Coverage and trust | A final criterion uncovered, or a blocker nobody verifies, with no decision. Add a check with fixtures, a sign-off, or record the decision |
| 6 Audit | Fix each error. Show each warning with its remedy, for the person to fix or ignore with a reason |
| 7 Register | Show the refusal and follow it |
| 10 Stamp | Written when every rung passed |

Rungs 8 and 9 (judge seeds and a first trial run) need judge calibration, which arrives in a later release. `--judge-seeds` and `--trial` are refused for now: say so, and stop at the stamp.

Passing means "ready to run and be measured", never "trusted". The workflow stays in `dev` mode.
