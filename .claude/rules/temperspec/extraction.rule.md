# Extracting behaviours from existing code

Code that no spec describes still holds rules that someone depends on. This rule says how a session finds them, decides which are behaviours and records where each came from. Setup follows it for every component, a reading session for its folder, discovery for an `existing behaviour` gap, and a person through the `extract` skill. The behaviours it yields follow `spec.rule.md`, including its `General rules, not cases`.

## Survey the outside first

Start where someone outside meets the code: commands and their options, endpoints, files read and written, exported functions, configuration keys, messages and exit codes. A capability is what someone outside depends on, not a folder.

## Where rules live

Look for rules in:

- guards that refuse or return early, and validation;
- status and state changes, and what moves an item from one to the next;
- calculations, defaults, limits and retries;
- permission checks;
- asserts, schema and database constraints;
- side effects and what undoes them on failure;
- the assertions of the tests, which say what the authors meant.

## Evidence, ranked

Every candidate rule carries one basis:

- `tested`: a test asserts it.
- `read`: the code that produces it was read on its whole path, from the entry point to the result.
- `stated`: only a name, a comment, a docstring or a document says so.

Only `tested` and `read` become behaviours. A `stated` rule is unconfirmed: it goes to the anomalies with the place that states it. Comments and documents are claims to cross-check, never sources to copy.

## Keep or drop

Keep a rule that someone outside can observe and would notice if it changed. Drop an accident of the implementation: call order, internal caching, log wording that nobody parses. The test: would this wording change if the implementation changed and nobody outside noticed? Then it is not a behaviour.

## One rule, written once

One behaviour per rule, not one per branch or per caller. A rule several capabilities share is written once, in the one that owns it, and linked from the others. Scenarios illustrate what a test means; they never copy its fixture names or values. Nothing comes from commit messages or from comments about history.

## Invariants

An invariant is written in the fixed pattern as the event that would break it: `WHEN a transfer would leave an account below zero THE ledger SHALL refuse the transfer`. A scenario shows the boundary: one case that keeps the invariant, one that would break it.

## Suspected bugs

Flag a suspected bug; do not fix it and do not bless it. A rule that looks wrong (it contradicts a test, a document or another path) is written as the code does it only when a test pins it. Otherwise it stays out of the behaviours and goes to the anomalies with its evidence, as a candidate issue.

## Budget

Sample and expand: entry points first, then one level down each path; stop at an outside boundary or when the next files add nothing new. Name what you did not read as partly covered. A later task that touches a partly covered part extracts its rules then, as an `existing behaviour` gap.

## Where the evidence goes

The evidence goes with the note of the step that extracted the rules, never into the spec: the setup note's `Evidence` and `Anomalies` sections (`task-notes.rule.md`), the hand-off's `Inferred behaviours` for discovery, and an evidence note beside the spec for the `extract` skill. A spec states the rule only.
