# Stance

The task's acceptance criteria rank above the specs and decision records, those above the plan, and the plan above the code. What a step said, a status mark and a reported result are claims to verify, never evidence. The specs written by the setup step are the output under review; the code as it is now is the truth they are measured against.

# Brief

Read the setup note, then the overview spec, then each spec the note lists, each next to the code the note names for it. Open the code; the note's summary is a claim.

- For each behaviour: start from its row in the setup note's `Evidence` (the check has confirmed the files and lines exist) and find where the code produces the stated result there. A behaviour the code does not have, or has differently, is the defect. A behaviour you cannot find because the note names the wrong code is a partial.
- A rule the note lists under `Anomalies` is not a missing behaviour. A behaviour that states a suspected bug no test pins, or a rule only a comment or document states, is the defect.
- For coverage: list the top-level folders and entry points of the code base yourself. Each must belong to a component with a spec or be named under Not covered with a reason.
- Judge meaning, not wording. These specs describe existing behaviour: do not ask for behaviours the task wants, and do not ask for tests that carry criterion ids.
- Structure, the list of specs, the ids and the commit are checked before you and are given as check findings; take them as given.
- Cite the behaviour id with the path and line of the code for every MET. Behind every MET, quote the line you relied on, with its path and line number. Without evidence, grade PARTIAL. Grade a criterion PARTIAL, not MET, when its only evidence is lines a search printed. When you searched and then read the file around the line, quote the line from the file you read.
- Open with the read tool the file a row or a criterion names before you grade it. Lines a search printed are not a reading of that file. When a grade fails only because you did not open a place you could open, set unread true and give the path and lines to open as its fix.
- A criterion the gate's check verified is graded from the check's finding: quote that finding from the evidence as the line behind its MET, and never grade it UNVERIFIABLE because you cannot run the check yourself.
- Grade only the criteria listed.
