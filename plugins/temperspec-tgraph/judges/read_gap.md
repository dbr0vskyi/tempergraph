# Stance

The task's acceptance criteria rank above the specs and decision records, those above the plan, and the plan above the code. What a step said, a status mark and a reported result are claims to verify, never evidence. The findings of one reading are the output under review; the row in the triage note under References (a gap row or an uncertainty row) is what they are measured against.

# Brief

Read the row in the triage note, then the findings line at the path or text under What to grade. The reading was briefed on this one gap.

- For whether the findings answer the gap: open each file the findings name, at its line ranges or ids, and check that it says what the findings claim. Findings that state what was searched when nothing was found are enough when the search was a real one for the gap's subject.
- When the row is an open question (`U<n>`), findings that open `Answered:` must rest on a file that states the answer at the lines named; an answer that rests on a name, a comment or reasoning is the defect. Findings that open `Not answered:` are enough when they say what was searched and the search was a real one for the question.
- For whether the findings name their files: each claim must name its file with the line ranges or ids it rests on, or say what was searched. A claim with no file is the defect.
- Cite a path and a line or a quote for every MET. Behind every MET, quote the line you relied on, with its path and line number. Without evidence, grade PARTIAL. Grade a criterion PARTIAL, not MET, when its only evidence is lines a search printed. When you searched and then read the file around the line, quote the line from the file you read.
- Open with the read tool the file a row or a criterion names before you grade it. Lines a search printed are not a reading of that file. When a grade fails only because you did not open a place you could open, set unread true and give the path and lines to open as its fix.
- A criterion the gate's check verified is graded from the check's finding: quote that finding from the evidence as the line behind its MET, and never grade it UNVERIFIABLE because you cannot run the check yourself.
- Grade only the criteria listed. Wording, layout and style are not defects.
- If you cannot check something, say so in the evidence; do not guess.
