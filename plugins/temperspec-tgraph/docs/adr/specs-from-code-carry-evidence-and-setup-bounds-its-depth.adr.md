# Specs from existing code carry their evidence, and setup bounds its depth

## Context

The research notes [spec extraction from existing code](../research/spec-extraction-from-existing-code.rsrch.md) and [spec craft in tools with long-lived specs](../research/spec-craft-long-lived-specs.rsrch.md) recommend how temperspec turns code into behaviours and how it words a spec. Each leaves questions for the owner with a default to take until they are answered. The owner asked for the recommendations to be built (2026-11-25) without answering the questions, so this record states the defaults taken and what each one costs if it is wrong.

What the package does after the change, read in it:

- `rules/extraction.rule.md` ranks evidence `tested` above `read` above `stated` and turns only the first two into behaviours; setup, discovery and the component reading sessions are told to open it.
- The setup note has `Evidence` and `Anomalies` sections; the setup check fails a behaviour with no Evidence row or with code lines outside its file (`ts-set-evidence`).
- Triage has the gap kind `existing behaviour`; discovery closes it by extracting the capability's rules before it writes the task's change.
- `spec.rule.md` caps the `WHEN … SHALL` sentence at 500 characters and bans vague words and placeholders in behaviours; the discovery and setup checks report these as leads (`ts-dis-wording`, `ts-set-wording`), never failures.

## Decision

We will take each note's default:

1. Setup covers every component in breadth and bounds its depth by the extraction rule's sample-and-expand budget. A part it read only in part is named as partly covered, and a later task that touches it gets an `existing behaviour` gap.
2. The spec rule keeps one requirement pattern, `WHEN … THE … SHALL`. An invariant is written as the event that would break it; no `WHILE` or `SHALL always` pattern is added.
3. A suspected bug that no test pins stays out of the spec and goes to the setup note's `Anomalies`, because a behaviour is a promise the code gate enforces.
4. Anomalies stay in the setup note for the owner to file; nothing is filed as an issue at the end of setup.
5. The behaviour sentence limit is 500 characters, warned on lines a run adds or changes only; the engine's existing longer sentences are left to a separate cleanup.
6. The recommendations are built together with the general-rules changes, not after them.

## Options considered

### A. Take the notes' defaults now (chosen)

For: the work is built and checked now; every default is the option that changes the least and is cheapest to undo. Against: a default the owner would not have chosen ships until they say so.

### B. Wait for the owner's answers before building

For: no default to undo. Against: the recommendations stay notes, which is what the owner asked to end.

### C. Full-depth setup, a second pattern for invariants, anomalies filed automatically

For: more complete specs at setup and no invariant bent into an event. Against: a setup run costs more and goes stale sooner, `specfmt`, the rule, the template and every check that reads the pattern change, and a setup run would open issues nobody has reviewed.

## Consequences

Setup and discovery record where every extracted behaviour came from, so the judge and the owner can see what was inferred and what was tested. A rule only stated in a comment never becomes a promise. Bending a state rule into an event is a little awkward; option C's second pattern stays available. A wrong default costs one edit to a rule file and its check.

## Revisit when

The owner answers any of the notes' open questions, or a real setup run shows the bounded depth leaves a task without the rules it needed.
