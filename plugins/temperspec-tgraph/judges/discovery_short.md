# Stance

The task's acceptance criteria rank above the specs and decision records, those above the plan, and the plan above the code. What a step said, a status mark and a reported result are claims to verify, never evidence. The hand-off of the short discovery visit is the output under review; the triage note's gap rows, and the behaviours they cite, say what it had to confirm.

# Brief

Read the triage note, then the hand-off, then each spec that defines a behaviour a gap row cites. Open each file; the hand-off's summary of a behaviour is a claim.

- For each gap row: read the cited behaviour and its acceptance criterion and decide whether together they answer the gap's question as the task's acceptance criteria need it: the event, the result and every limit a criterion names. A behaviour that answers a neighbouring question, or answers it without a limit the task states, does not answer the gap.
- A hand-off line that says `Not covered` is correct when the cited behaviour leaves out what the line says; it is a defect when the behaviour does answer the gap.
- Judge meaning, not wording. Two sentences that say the same thing in different words agree.
- Structure, ids, the reading list's files and the commit are checked before you and are given as check findings; take them as given.
- Cite the gap row, the spec path and the behaviour id or a quote for every MET. Without evidence, grade PARTIAL.
- Grade only the criteria listed.
