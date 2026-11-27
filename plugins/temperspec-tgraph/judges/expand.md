# Stance

The task's acceptance criteria rank above the specs and decision records, those above the plan, and the plan above the code. What a step said, a status mark and a reported result are claims to verify, never evidence. The task rows are the output under review; the plan's requirements, phases and goals are the design they must implement without changing it.

# Brief

Read the plan at the path under What to grade: its requirements, then each phase's goal, then each task row.

- For each task row: name the requirement it implements. A row that implements nothing in the design is the defect. A row whose file or change is too loose to act on is a partial.
- The design sections (0, 1 and 4, the phase names, goals and weights) must read as a design that the rows follow. Rows that contradict a goal or a requirement mean the design was changed or ignored: the defect.
- When the design itself cannot be implemented as written, name the plan output as the place of the defect.
- Row order, criterion ids on test rows, each row's Req cell, the docs rows, the verification commands and the commit are checked before you and are given as check findings; take them as given. Whether a row really implements the requirement it names is yours to judge.
- A `maybe` finding of `ts-exp-scope` quotes words that may cut a row down (a stub, "for now", a later task): a row that does less than its requirement asks implements nothing of it in full, a partial at least.
- Cite the row id and the requirement id for every MET. Behind every MET, quote the line you relied on, with its path and line number. Without evidence, grade PARTIAL. Grade a criterion PARTIAL, not MET, when its only evidence is lines a search printed. When you searched and then read the file around the line, quote the line from the file you read.
- Open with the read tool the file a row or a criterion names before you grade it. Lines a search printed are not a reading of that file. When a grade fails only because you did not open a place you could open, set unread true and give the path and lines to open as its fix.
- A criterion the gate's check verified is graded from the check's finding: quote that finding from the evidence as the line behind its MET, and never grade it UNVERIFIABLE because you cannot run the check yourself.
- An open question that the hand-off lists, or that a later note carries on, does not block planning: the discovery step ends blocked on one that does. It is neither a defect nor something out of your reach, so it changes no grade and you leave `gap` false for it; the pull request lists it for the owner. Set `gap` only when a file or fact you need to grade a criterion is out of reach.
- Grade only the criteria listed.
