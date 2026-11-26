# Stance

The task's acceptance criteria rank above the specs and decision records, those above the plan, and the plan above the code. What a step said, a status mark and a reported result are claims to verify, never evidence. The triage note is the output under review; the task text under References is the truth it is measured against.

# Brief

Read the task under References, then the triage note at the path under What to grade.

- For the acceptance criteria: put each numbered criterion of the note next to the sentence of the task it comes from. A criterion with no such sentence, or a statement of the task with no criterion, is the defect.
- For the gaps: take each concept the task needs, search the repository's spec folders for it yourself, and open what you find. A concept is covered only when a behaviour and an acceptance criterion of a spec state it. Do not trust the note's "Existing documents" list or the searches it reports; repeat them.
- For the open questions: read the task once for each category of the scan in `task-notes.rule.md` (goal, scope, actors, data, names, side effects, failures, limits, dependencies, existing behaviour, terms) and ask what the task leaves open there. A question whose answer would change which behaviours are written, and that neither the task nor a document the note names answers, must be an uncertainty row. A row marked `Detail` whose answer changes which behaviours are written is marked too low. A question the plan can settle and that the note does not list is not a defect.
- When the note's route is `quick`, a gap also exists if any behaviour or acceptance criterion of a spec would have to change for the task: open the specs that cover the code under the note's Change section and compare. Such a missed change is a defect of the gap list.
- Cite a path and a line or a quote for every MET. Behind every MET, quote the line you relied on, with its path and line number. Without evidence, grade PARTIAL. Grade a criterion PARTIAL, not MET, when its only evidence is lines a search printed. When you searched and then read the file around the line, quote the line from the file you read.
- A criterion the gate's check verified is graded from the check's finding: quote that finding from the evidence as the line behind its MET, and never grade it UNVERIFIABLE because you cannot run the check yourself.
- Grade only the criteria listed. Wording, layout and style are not defects.
- If you cannot check something, say so in the evidence; do not guess.
