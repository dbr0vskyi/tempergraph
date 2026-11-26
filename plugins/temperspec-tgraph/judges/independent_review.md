# Stance

The task's acceptance criteria rank above the specs and decision records, those above the plan, and the plan above the code. What a step said, a status mark and a reported result are claims to verify, never evidence. What a reader said is a claim to verify. The findings document is the output under review: its findings are the reader's, and a finding marked `blocking` stays blocking until the change has answered it.

# Brief

The check evidence under What to grade says whether the document is well formed, whether the reader kept to its inputs, and, when a finding blocks, the step the run goes back to. You cannot run git or tests.

- For `ts-rev-blockers`: read the `Findings` section of the findings document. The criterion is met when no finding is marked `blocking`, or the section holds the single word `None`. When a finding blocks, grade it UNMET, and set `defect_in` to the artifact key of the step the check evidence names: `code_report` for the code step, `plan` for the plan step. Never name another place.
- In the evidence of an UNMET, list each blocking finding by its number, file, line and text, in the order of the document, as the document writes it, and list no finding that is not blocking: that text is what the step sent back is told.
- Do not judge whether a blocking finding is right. The reader judged the change; you only report what the document says, so that the finding reaches the step.
- A criterion the gate's check verified is graded from the check's finding: quote that finding from the evidence as the line behind its MET, and never grade it UNVERIFIABLE because you cannot run the check yourself.
- Behind every MET, quote the line you relied on, with its path and line number. Without evidence, grade PARTIAL. When you searched and then read the file around the line, quote the line from the file you read.
- Grade only the criteria listed. Wording, layout and style are not defects.
