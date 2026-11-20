# Phases 3 and 4: work backwards, then find a verification for every criterion

## Phase 3: backwards to steps

From each deliverable ask: "what must be true just before this?" Each answer that is a checkable result of its own is a step boundary and an intermediate outcome, under `intermediate.<unit>` with a `statement` and `criteria`. Stop at the run's input.

- Every intermediate criterion lists in `serves` the final criteria it serves.
- A final criterion that nothing serves, and that the outcome gate cannot verify, is shown as uncovered. Say so; do not hide it.
- Each step is a fresh session that sees only its prompt. Data moves forward through named files.
- A step reachable by a trip back must pass again on a second visit. Widen a criterion bounded by upstream sources alone to "or the reason for this visit".

Approve with `tempergraph author approve <id> 3`.

## Phase 4: the search order

For each criterion, take these in turn. Prefer an earlier row, and say why when you take a later one.

| Order | Look for | `verified_by` | `source` |
|---|---|---|---|
| 1 | An inventory candidate that decides it: a test, a linter rule, a schema, a checklist item a script can test | `check` | `existing:<kind>` |
| 2 | A deterministic primitive: a file, heading, pattern or value; a git fact; a command fixed in the workflow | `check` | `created` |
| 3 | A part a check decides and a part that needs reading | split into a `check` and a `judge` criterion serving the same final one | |
| 4 | Reading and understanding, against named references the judge can open | `judge`, with `check_method`, `references` and a complete `scale` | `existing:<kind>` when the method comes from a review rule or checklist, else `created` |
| 5 | Authority or knowledge only a person has (safe to publish, fits the strategy) | `person`, with `role` and `question` | `interview` |
| 6 | Nothing trustworthy | `none`, with `reason` and `risk`; offer the cheapest way to make it verifiable later | |

A blocker you cannot place above row 6 is the person's decision: make it a `person` sign-off, accept it as `none` (a recorded decision), lower it to a warning, or drop it.

## Verifier shapes

| `verified_by` | `verifier` |
|---|---|
| `check` with a primitive | `{"primitive": "headings_in_order", "artifact": "<key>", "headings": [...]}`. The primitives are `file_present`, `headings_in_order`, `pattern_present`, `pattern_absent`, `value_in_choices`, `git_clean`, `git_pushed`. Pattern primitives take `pattern` (a regular expression, multiline); `value_in_choices` takes `artifact` (the reported value's name) and `choices`; the git ones take nothing |
| `check` with a command | `{"command": "<program> <args>"}`, a constant string fixed in the workflow; scaffold adds its program to the allowed commands. Nothing from the task input reaches it |
| `check`, hand-written | `{"check": "<name>"}`. Scaffold writes a stub that answers `maybe`, which the person completes |
| `judge` | `{"references": ["<key>", ...], "scale": {"met", "partial", "unmet", "evidence", "seeds"}}`. A blocker's `partial` is "no partial: any gap is UNMET" when there is no middle ground |
| `person` | `{"role": "release manager", "question": "Is this safe to publish?"}` |
| `none` | `{"reason": "...", "risk": "..."}` |

## Show the trust

`tempergraph author check <id>` returns `verification`: a row per criterion with its trust (`deterministic`, `uncalibrated`, `human`, `unverified`), the trust profile and the coverage of each final criterion. Show the table to the person with each criterion's class. A check is `deterministic` once a good example exists for its unit, because scaffold writes its fixtures from it. A judge stays `uncalibrated` until calibration accepts it, which is a later release.

Approve with `tempergraph author approve <id> 4` once every criterion has a class.
