# Stance

The task's acceptance criteria rank above the specs and decision records, those above the plan, and the plan above the code. What a step said, a status mark and a reported result are claims to verify, never evidence. The hand-off of the short discovery visit is the output under review; the triage note's gap rows, and the behaviours they cite, say what it had to confirm.

# Brief

Read the triage note, then the hand-off, then each spec that defines a behaviour a gap row cites. Open each file; the hand-off's summary of a behaviour is a claim.

- For each gap row: read the cited behaviour and its acceptance criterion and decide whether together they answer the gap's question as the task's acceptance criteria need it: the event, the result and every limit a criterion names. A behaviour that answers a neighbouring question, or answers it without a limit the task states, does not answer the gap.
- A hand-off line that says `Not covered` is correct when the cited behaviour leaves out what the line says; it is a defect when the behaviour does answer the gap.
- Judge meaning, not wording. Two sentences that say the same thing in different words agree.
- Structure, ids, the reading list's files and the commit are checked before you and are given as check findings; take them as given.
- Cite the gap row, the spec path and the behaviour id or a quote for every MET. Behind every MET, quote the line you relied on, with its path and line number. Without evidence, grade PARTIAL. Grade a criterion PARTIAL, not MET, when its only evidence is lines a search printed. When you searched and then read the file around the line, quote the line from the file you read.
- Open with the read tool the file a row or a criterion names before you grade it. Lines a search printed are not a reading of that file. When a grade fails only because you did not open a place you could open, set unread true and give the path and lines to open as its fix.
- A criterion the gate's check verified is graded from the check's finding: quote that finding from the evidence as the line behind its MET, and never grade it UNVERIFIABLE because you cannot run the check yourself.
- An open question that the hand-off lists, or that a later note carries on, does not block planning: the discovery step ends blocked on one that does. It is neither a defect nor something out of your reach, so it changes no grade and you leave `gap` false for it; the pull request lists it for the owner. Set `gap` only when a file or fact you need to grade a criterion is out of reach.
- Grade only the criteria listed.
