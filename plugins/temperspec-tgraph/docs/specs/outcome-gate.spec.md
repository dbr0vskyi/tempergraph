# Outcome gate

## Purpose

What the final gate of the temperspec workflow requires of the documents a run leaves, and what it reports about the push of the run's branch. The gate runs after every step and before the last stage, which pushes the branch and opens the draft pull request, so a run's branch is normally not pushed when the gate runs. A discovery visit, short or full, writes the hand-off, the plan step writes the plan and the code step writes the code report; a run that skips a step leaves no such document, and the engine requires a deliverable only on a path that produces it ([OUT-B15](../../../tempergraph/docs/specs/run-outcome.spec.md)). The push is read from the engine's git facts ([CHK-B10](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)). The owner who reads a run's outcome and the maintainers of the final criteria listed in the overview depend on it. Part of the [overview](overview.spec.md).

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
