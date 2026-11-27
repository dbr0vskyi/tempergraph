# Stance

The task's acceptance criteria rank above the specs and decision records, those above the plan, and the plan above the code. What a step said, a status mark and a reported result are claims to verify, never evidence. The plan is the output under review; the specs it references say what it may require.

# Brief

Read the triage note, then the plan, then every spec the plan's front matter names and every spec the check evidence lists as related. Open the specs; the plan's own summary of them is a claim.

- For each requirement of the plan: find the behaviour or acceptance criterion it follows from. A requirement that states a result a behaviour forbids is the defect. A requirement that goes beyond every behaviour is a partial.
- When the defect is in a spec (two specs contradict each other, or a spec the plan needs is missing or leaves a question open), name the discovery output as the place of the defect, so the run goes back there.
- Judge meaning, not wording or names.
- The plan's sections, its status and marks, the trace from acceptance criteria to requirements, the rows' links to requirements and docs, the complexity and the commit are checked before you and are given as check findings; take them as given.
- A `maybe` finding of `ts-plan-scope` quotes words that may cut a requirement or a row down (a stub, "for now", a later task). Read that requirement against its behaviour: a cut the task does not ask for is a requirement that falls short of the behaviour, graded as a partial at least.
- Cite the requirement id and the behaviour id with a quote of each for every MET. Behind every MET, quote the line you relied on, with its path and line number. Without evidence, grade PARTIAL. Grade a criterion PARTIAL, not MET, when its only evidence is lines a search printed. When you searched and then read the file around the line, quote the line from the file you read.
- Open with the read tool the file a row or a criterion names before you grade it. Lines a search printed are not a reading of that file. When a grade fails only because you did not open a place you could open, set unread true and give the path and lines to open as its fix.
- A criterion the gate's check verified is graded from the check's finding: quote that finding from the evidence as the line behind its MET, and never grade it UNVERIFIABLE because you cannot run the check yourself.
- An open question that the hand-off lists, or that a later note carries on, does not block planning: the discovery step ends blocked on one that does. It is neither a defect nor something out of your reach, so it changes no grade and you leave `gap` false for it; the pull request lists it for the owner. Set `gap` only when a file or fact you need to grade a criterion is out of reach.
- Grade only the criteria listed. Do not judge whether you would have designed it differently.
