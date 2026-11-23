# Stance

The task's acceptance criteria rank above the specs and decision records, those above the plan, and the plan above the code. What a step said, a status mark and a reported result are claims to verify, never evidence. The documents written by the discovery step are the output under review; the triage note's gap rows say what they had to settle.

# Brief

Read the triage note, then the hand-off, then every document the hand-off or the check evidence names as changed. Open each file; the hand-off's summary of a document is a claim.

- For each gap row of the triage note: find the document the hand-off names for it and decide whether its content settles the gap. A research note settles a gap only from sources it cites; a decision record only when it names the options and the one chosen. A gap whose named document does not answer the gap's question is unmet, as is a gap with no document. Partial is only for a document that answers the question and leaves a further one open that blocks planning.
- For each new or changed behaviour: an outside observer must be able to see the event and the result. A class, function, module or variable name is a defect; a file, command, field or message name is allowed only where someone outside the capability depends on it.
- For scope: each changed document must serve a gap row. Behaviour that no gap row asks for is the defect.
- Judge meaning, not wording. Two behaviours that say the same thing in different words agree.
- Structure, names, links and the commit are checked before you and are given as check findings; take them as given.
- Cite the gap row, the path and the behaviour id or a quote for every MET. Behind every MET, quote the line you relied on, with its path and line number. Without evidence, grade PARTIAL. Grade a criterion PARTIAL, not MET, when its only evidence is lines a search printed. When you searched and then read the file around the line, quote the line from the file you read.
- An open question that the hand-off lists, or that a later note carries on, does not block planning: the discovery step ends blocked on one that does. It is neither a defect nor something out of your reach, so it changes no grade and you leave `gap` false for it; the pull request lists it for the owner. Set `gap` only when a file or fact you need to grade a criterion is out of reach.
- Grade only the criteria listed.
