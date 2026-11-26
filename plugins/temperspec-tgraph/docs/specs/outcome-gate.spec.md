# Outcome gate

## Purpose

What the final gate of the temperspec workflow requires of the documents a run leaves, and what it reports about the push of the run's branch. The gate runs after every step and before the last stage, which pushes the branch and opens the draft pull request, so a run's branch is normally not pushed when the gate runs. A discovery visit, short or full, writes the hand-off, the plan step writes the plan and the code step writes the code report; a run that skips a step leaves no such document, and the engine requires a deliverable only on a path that produces it ([OUT-B15](../../../tempergraph/docs/specs/run-outcome.spec.md)). The push is read from the engine's git facts ([CHK-B10](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)). When the outcome judge grades a final criterion PARTIAL or UNMET, the engine sends the run back to the earliest step on the run's path that has a criterion serving the failing final criterion ([OUT-B3](../../../tempergraph/docs/specs/run-outcome.spec.md), [OUT-B16](../../../tempergraph/docs/specs/run-outcome.spec.md)); this spec states which step that is for each final criterion the judge grades and what the step is told, and it does not own the engine's rule. The owner who reads a run's outcome and the maintainers of the final criteria listed in the overview depend on it. Part of the [overview](overview.spec.md).

## Behaviours

### OGT-B1 A document is required on the path that writes it

WHEN a run reaches the outcome gate after taking a step that writes the hand-off, the plan or the code report THE outcome gate SHALL fail its check, naming the document, when that document's file does not exist.

- GIVEN a run that took the full discovery and whose hand-off file does not exist WHEN the outcome gate's check runs THEN the check fails and names the hand-off
- GIVEN a run that took the short visit and whose hand-off file does not exist WHEN the outcome gate's check runs THEN the check fails and names the hand-off
- GIVEN a run that took the plan step and whose plan file does not exist WHEN the outcome gate's check runs THEN the check fails and names the plan
- GIVEN a run that took the code step and whose code report file does not exist WHEN the outcome gate's check runs THEN the check fails and names the code report
- GIVEN a run that took every step and left the triage note, the hand-off, the plan and the code report WHEN the outcome gate's check runs THEN the check does not fail for a missing document

### OGT-B2 A document of a step the run did not take is not required

WHEN a run reaches the outcome gate without having taken the step that writes the hand-off, the plan or the code report THE outcome gate SHALL not require that document.

- GIVEN a run of the quick lane (triage straight to code) that left no hand-off and no plan WHEN the outcome gate's check runs THEN the check does not fail for a missing hand-off or plan
- GIVEN a run whose triage found no gap, which went from triage to the plan step and left no hand-off WHEN the outcome gate's check runs THEN the check does not fail for a missing hand-off
- GIVEN a docs-only run that ended after discovery and left no plan and no code report WHEN the outcome gate's check runs THEN the check does not fail for a missing plan or code report

### OGT-B3 The outcome judge is shown the documents the run wrote

WHEN the outcome judge is briefed THE outcome gate SHALL name to it the triage note, the hand-off, the plan and the code report that the run wrote.

- GIVEN a run that wrote the triage note, the hand-off, the plan and the code report WHEN the outcome judge is briefed THEN the brief names all four files
- GIVEN a docs-only run that wrote the triage note and the hand-off WHEN the outcome judge is briefed THEN the brief names those two files and names no plan and no code report

### OGT-B4 The check reports whether the branch is pushed

WHEN the outcome gate's check grades a run against the final criteria THE outcome gate SHALL state in the check's evidence whether the run's branch is pushed.

- GIVEN the engine's git facts report the run's branch as pushed WHEN the check grades the run THEN the evidence says the branch is pushed
- GIVEN the engine's git facts report the run's branch as not pushed WHEN the check grades the run THEN the evidence says the branch is not pushed

### OGT-B5 A push never decides the check's result

WHEN the outcome gate's check grades a run that meets every criterion the check grades THE outcome gate SHALL pass the check whether or not the run's branch is pushed.

- GIVEN a run that meets every criterion the check grades and whose branch is not pushed WHEN the check grades the run THEN the result is PASS
- GIVEN a run that meets every criterion the check grades and whose branch is pushed WHEN the check grades the run THEN the result is PASS

### OGT-B6 A spec disagreement goes back to the full discovery

WHEN the outcome judge grades `ts-spec-sync` PARTIAL or UNMET, names no earlier step's output as the place of the defect and grades no other final criterion PARTIAL or UNMET THE outcome gate SHALL send a run whose path holds the full discovery back to the full discovery.

- GIVEN a run that took the full discovery and whose judge grades `ts-spec-sync` PARTIAL with no place named WHEN the outcome gate routes THEN the full discovery is the next step entered
- GIVEN a run that took the setup step, the triage step and the full discovery and whose judge grades `ts-spec-sync` UNMET with no place named WHEN the outcome gate routes THEN the full discovery is the next step entered and the setup step is not
- GIVEN a run that took the short visit and then the full discovery, and whose judge grades `ts-spec-sync` PARTIAL with no place named WHEN the outcome gate routes THEN the full discovery is the next step entered

### OGT-B7 A spec disagreement on a path with a plan step and no full discovery goes back to the plan step

WHEN the outcome judge grades `ts-spec-sync` PARTIAL or UNMET, names no earlier step's output as the place of the defect and grades no other final criterion PARTIAL or UNMET THE outcome gate SHALL send a run whose path holds the plan step and no full discovery back to the plan step.

- GIVEN a run that took the short visit and the plan step and whose judge grades `ts-spec-sync` PARTIAL with no place named WHEN the outcome gate routes THEN the plan step is the next step entered and the triage step and the setup step are not
- GIVEN a run that went from the triage step straight to the plan step and whose judge grades `ts-spec-sync` UNMET with no place named WHEN the outcome gate routes THEN the plan step is the next step entered

### OGT-B8 A spec disagreement on a path with no full discovery and no plan step goes back to the code step

WHEN the outcome judge grades `ts-spec-sync` PARTIAL or UNMET, names no earlier step's output as the place of the defect and grades no other final criterion PARTIAL or UNMET THE outcome gate SHALL send a run whose path holds neither the full discovery nor the plan step back to the code step.

- GIVEN a run of the quick lane, which took the triage step and then the code step, and whose judge grades `ts-spec-sync` PARTIAL with no place named WHEN the outcome gate routes THEN the code step is the next step entered and the triage step is not

### OGT-B9 A task criterion that is not achieved goes back to the triage step

WHEN the outcome judge grades `ts-accepted` PARTIAL or UNMET on a run that took no setup step, names no earlier step's output as the place of the defect and grades no other final criterion PARTIAL or UNMET THE outcome gate SHALL send the run back to the triage step.

- GIVEN a run that took the full discovery and no setup step and whose judge grades `ts-accepted` UNMET with no place named WHEN the outcome gate routes THEN the triage step is the next step entered
- GIVEN a run of the quick lane whose judge grades `ts-accepted` PARTIAL with no place named WHEN the outcome gate routes THEN the triage step is the next step entered

### OGT-B10 Several failing criteria go back to the earliest step

WHEN the outcome judge grades more than one final criterion PARTIAL or UNMET and names no earlier step's output as the place of any defect THE outcome gate SHALL send the run back to the step that the workflow runs first among the steps those criteria send a run to.

- GIVEN a run that took the full discovery and whose judge grades `ts-spec-sync` UNMET and `ts-accepted` PARTIAL with no place named WHEN the outcome gate routes THEN the triage step is the next step entered and the full discovery is not

### OGT-B11 The step the run goes back to is told the judge's place and fix

WHEN the outcome gate sends the run back for a final criterion that the outcome judge graded PARTIAL or UNMET THE outcome gate SHALL give the step the run goes back to, as the reason for its visit, the place of the defect and the fix that the outcome judge stated for that criterion, in the judge's own words.

- GIVEN an outcome judge that grades `ts-spec-sync` PARTIAL and states a place and a fix, one line each WHEN the run goes back to the full discovery THEN the reason for the visit of the full discovery holds that place and that fix word for word
- GIVEN an outcome judge that grades `ts-accepted` UNMET and states a place and a fix WHEN the run goes back to the triage step THEN the reason for the visit of the triage step holds that place and that fix word for word

### OGT-B12 The outcome judge is told to state the place and the fix in its evidence

WHEN the outcome judge is briefed THE outcome gate SHALL tell it to state, in the evidence of each criterion it grades PARTIAL or UNMET, the place of the defect and the fix in one line.

- GIVEN the brief of the outcome judge WHEN a person reads it THEN it asks that the evidence of a criterion graded PARTIAL or UNMET state the place of the defect and the fix in one line

## Acceptance criteria

- OGT-AC1 (OGT-B1): The outcome check of a run whose path holds the full discovery, with its hand-off file missing, fails and names the hand-off
- OGT-AC2 (OGT-B1): The outcome check of a run whose path holds the short visit, with its hand-off file missing, fails and names the hand-off
- OGT-AC3 (OGT-B1): The outcome check of a run whose path holds the plan step, with its plan file missing, fails and names the plan
- OGT-AC4 (OGT-B1): The outcome check of a run whose path holds the code step, with its code report file missing, fails and names the code report
- OGT-AC5 (OGT-B1): The outcome check of a run that took every step and left the triage note, the hand-off, the plan and the code report does not fail for a missing document
- OGT-AC6 (OGT-B2): The outcome check of a quick-lane run with no hand-off file and no plan file does not fail for either
- OGT-AC7 (OGT-B2): The outcome check of a run that went from triage to the plan step with no hand-off file does not fail for a hand-off
- OGT-AC8 (OGT-B2): The outcome check of a docs-only run with no plan file and no code report file does not fail for either
- OGT-AC9 (OGT-B3): The outcome judge's brief for a run that wrote the triage note, the hand-off, the plan and the code report names all four files
- OGT-AC10 (OGT-B3): The outcome judge's brief for a docs-only run that wrote the triage note and the hand-off names those two files and names no plan and no code report
- OGT-AC11 (OGT-B4): The check evidence of a run whose branch the engine's git facts report as pushed says the branch is pushed
- OGT-AC12 (OGT-B4): The check evidence of a run whose branch the engine's git facts report as not pushed says the branch is not pushed
- OGT-AC13 (OGT-B5): The outcome check of a run that meets every criterion it grades has the result PASS with the branch pushed and with the branch not pushed
- OGT-AC14 (OGT-B6): In a run whose path holds the full discovery, an outcome judgement that grades `ts-spec-sync` PARTIAL or UNMET and names no place is followed by the full discovery as the next step entered, and by no triage step, no setup step and no reading session
- OGT-AC15 (OGT-B6): In a run whose path holds the setup step, the triage step and the full discovery, the same judgement is followed by the full discovery as the next step entered and not by the setup step
- OGT-AC16 (OGT-B7): In a run whose path holds the short visit and the plan step and no full discovery, the same judgement is followed by the plan step as the next step entered, and by no triage step and no setup step
- OGT-AC17 (OGT-B7): In a run that went from the triage step straight to the plan step, the same judgement is followed by the plan step as the next step entered
- OGT-AC18 (OGT-B8): In a run of the quick lane, the same judgement is followed by the code step as the next step entered and not by the triage step
- OGT-AC19 (OGT-B9): In a run that took the full discovery and no setup step, an outcome judgement that grades `ts-accepted` PARTIAL or UNMET and names no place is followed by the triage step as the next step entered
- OGT-AC20 (OGT-B10): In a run that took the full discovery, an outcome judgement that grades `ts-spec-sync` UNMET and `ts-accepted` PARTIAL and names no place is followed by the triage step as the next step entered and not by the full discovery
- OGT-AC21 (OGT-B11): In a stand-in run whose outcome judge states a place and a fix for a failing criterion, the reason for the visit of the step the run goes back to holds that place and that fix word for word
- OGT-AC22 (OGT-B12): The outcome judge's brief asks that the evidence of each criterion graded PARTIAL or UNMET state the place of the defect and the fix in one line
