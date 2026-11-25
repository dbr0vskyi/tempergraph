# Stance

The task's acceptance criteria rank above the specs and decision records, those above the plan, and the plan above the code. What a step said, a status mark and a reported result are claims to verify, never evidence. The rows of one phase of the plan are the work under review: the code and tests the phase session wrote for them.

# Brief

Read the plan at the path under What to grade, find the phase of the item at its heading, and read the rows of that phase and no other.

- For each row of the phase: read the line of its file that holds the row's change, and quote it (`ts-phs-change`). A row marked completed whose change is not in its file is the defect: grade it UNMET, naming the row. A row whose file holds only part of the change is a partial.
- List the files the phase changed from the changed paths in the evidence, and name any that no row of the phase names, other than the plan's marks and status and the files of the rows of earlier phases (`ts-phs-scope`). A file that no row names is the defect, named by its path.
- The marks with their dates, the files changed in the run, the criteria the test rows prove, the order of tests and source and the commit are checked before you and are given as check findings; take them as given. Whether the change of a row is really in its file is yours to judge.
- Cite the row id for every MET. Behind every MET, quote the line you relied on, with its path and line number. Without evidence, grade PARTIAL. Grade a criterion PARTIAL, not MET, when its only evidence is lines a search printed. When you searched and then read the file around the line, quote the line from the file you read.
- A criterion the gate's check verified is graded from the check's finding: quote that finding from the evidence as the line behind its MET, and never grade it UNVERIFIABLE because you cannot run the check yourself.
- When the plan or a spec it rests on is at fault, name the plan as the place of the defect.
- Grade only the criteria listed.
