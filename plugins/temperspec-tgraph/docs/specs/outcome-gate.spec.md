# Outcome gate

## Purpose

What the final gate of the temperspec workflow requires of the documents a run leaves, what it reports about the push of the run's branch, and what it does when a final criterion fails for a fact no step can change. The gate runs after every step and before the last stage, which pushes the branch and opens the draft pull request, so a run's branch is normally not pushed when the gate runs. A discovery visit, short or full, writes the hand-off, the plan step writes the plan and the code step writes the code report; a run that skips a step leaves no such document, and the engine requires a deliverable only on a path that produces it ([OUT-B15](../../../tempergraph/docs/specs/run-outcome.spec.md)). The push is read from the engine's git facts ([CHK-B10](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)). When the outcome judge grades a final criterion PARTIAL or UNMET, the engine sends the run back to the earliest step on the run's path that has a criterion serving the failing final criterion ([OUT-B3](../../../tempergraph/docs/specs/run-outcome.spec.md), [OUT-B16](../../../tempergraph/docs/specs/run-outcome.spec.md)); this spec states which step that is for each final criterion the judge grades and what the step is told, and it does not own the engine's rule. A final criterion that fails for a fact no step can change (a spec the base branch has changed since the run started, a verification command that fails for a reason the run's change did not cause) is not sent back to a step, because a trip back cannot make the gate pass while the fact stands: the gate pauses the run for a person, and the check's evidence names the fact. The owner who reads a run's outcome and the maintainers of the final criteria listed in the overview depend on it. Part of the [overview](overview.spec.md).

## Depends on

- `code.spec.md`: how the code gate compares a verification command that fails with the run's base commit, judges it environmental or caused by the change and names it in its evidence (the rows `ts-code-base`, `ts-code-touch`, `ts-code-passes`, `ts-code-nobase` and `ts-code-evidence`)
- `../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md`: what a check returns and what an environmental result does (CHK-B14); a failed mechanical criterion starts no judge (CHK-B1); a run at the base is reused within a visit (CHK-B20)
- `../../../tempergraph/docs/specs/gate-and-human.spec.md`: a check result that no step can change pauses with kind `escalation` (HUM-B7); the decision `retry` (HUM-B12)
- `../../../tempergraph/docs/specs/run-outcome.spec.md`: a failing final criterion sends the run back to the earliest step that serves it (OUT-B16)

## Does not own

- When `ts-spec-fresh` fails and what its failure names: `side-by-side-runs.spec.md`
- How the code gate handles a verification command that fails, including what it does when another finding also fails: `code.spec.md`
- Which step a failing final criterion sends the run back to, and how often: `../../../tempergraph/docs/specs/run-outcome.spec.md`

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

### OGT-B13 A fact no step can change pauses the gate

WHEN the outcome check fails `ts-spec-fresh`, or fails `ts-verify` on a command judged environmental (OGT-B16), each a fact no step can change, THE outcome gate SHALL pause the run with kind `escalation` ([HUM-B7](../../../tempergraph/docs/specs/gate-and-human.spec.md)) and send it to no step, whatever else the check fails.

- GIVEN a spec the run edited and a commit that the base branch gained after the run started and that changed the same spec WHEN the outcome check runs THEN the run pauses with kind `escalation` and no step is entered after the check
- GIVEN a spec the run edited that the base branch has changed since the run started, and a failing `ts-traced` WHEN the outcome check runs THEN the run pauses and is sent to no step
- GIVEN a run paused for a changed spec beside a failing `ts-traced` WHEN an operator brings the head of the base branch into the run's branch and answers `retry` ([HUM-B12](../../../tempergraph/docs/specs/gate-and-human.spec.md)) THEN the check runs a second time and passes `ts-spec-fresh`, and the run goes back for `ts-traced` as [OUT-B16](../../../tempergraph/docs/specs/run-outcome.spec.md) says

### OGT-B14 A pause starts no outcome judge

WHEN the outcome check fails for a fact no step can change (OGT-B13) THE outcome gate SHALL start no outcome judge session ([CHK-B14](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md), [CHK-B1](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)).

- GIVEN a spec the run edited that the base branch has changed since the run started WHEN the outcome check runs THEN the run pauses and the outcome judge has started no session
- GIVEN a verification command that fails with the same exit code at the run's base commit WHEN the outcome check runs THEN the run pauses and the outcome judge has started no session
- GIVEN a run paused for a changed spec WHEN an operator brings the head of the base branch into the run's branch, answers `retry` and the check passes THEN the outcome judge starts its session

### OGT-B15 The fact no step can change comes first in the evidence

WHEN the outcome check fails for a fact no step can change (OGT-B13) and fails a final criterion that a step could repair as well THE outcome check SHALL name each failing criterion in its evidence, the facts no step can change first.

- GIVEN a spec the run edited that the base branch has changed since the run started, and a failing `ts-traced` WHEN the outcome check runs THEN its evidence names `ts-spec-fresh` and then `ts-traced`
- GIVEN a verification command that fails with the same exit code at the run's base commit, and a failing `ts-traced` WHEN the outcome check runs THEN its evidence names `ts-verify` and then `ts-traced`
- GIVEN a spec the run edited that the base branch has changed since the run started, and no other failing criterion WHEN the outcome check runs THEN the one failing criterion its evidence names is `ts-spec-fresh`

### OGT-B16 A failing verification command is judged as at the code gate

WHEN a verification command fails at the outcome gate THE outcome check SHALL compare the failure with the run's base commit, judge it environmental, caused by the change or not compared, and name the command, its exit code at the gate and at the base commit and the reason in its evidence, in each of these exactly as the code gate does for the same command ([code.spec.md](code.spec.md)).

- GIVEN a verification command that exits 0 at the run's base commit and 1 at the gate WHEN the outcome check runs THEN the failure is caused by the change, the run goes back as [OUT-B16](../../../tempergraph/docs/specs/run-outcome.spec.md) says to the earliest step that serves `ts-verify`, and the reason for that step's visit holds the last lines the command printed
- GIVEN a verification command that exits 1 at the gate and at the run's base commit WHEN the outcome check runs THEN the failure is environmental, the evidence names the command, both exit codes and the reason, and the run pauses as OGT-B13 says
- GIVEN a run with no base commit and a verification command that fails at the gate WHEN the outcome check runs THEN the failure is not compared, the evidence says so, and the run goes back as OUT-B16 says

### OGT-B17 A verification command is run at the base only when it fails, once in a visit

WHEN the outcome check runs a verification command THE outcome check SHALL start it at the run's base commit only when it fails at the gate, and at most once in a visit of the outcome gate however many times the check runs in that visit ([CHK-B20](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)).

- GIVEN a verification command that exits 0 at the gate WHEN the outcome check runs THEN the command is not started at the run's base commit
- GIVEN a verification command that fails at the gate and a pause that an operator answers with `retry` WHEN the check runs a second time in the same visit THEN the command has been started at the run's base commit once in all
- GIVEN a trip back that gives the outcome gate a new visit and a verification command that fails at the gate WHEN the check runs in the new visit THEN the command is started at the run's base commit once in that visit

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
- OGT-AC23 (OGT-B13): In a stand-in run whose base branch gains a commit to a spec the run edited, the first invocation ends paused at the outcome gate with kind `escalation` and no step is entered after the check; after the head of the base branch is merged into the run's branch and the operator answers `retry`, the run reaches the finalizer
- OGT-AC24 (OGT-B13): In a stand-in run whose verification command fails with the same exit code at the run's base commit, the first invocation ends paused at the outcome gate with kind `escalation` and no step is entered after the check
- OGT-AC25 (OGT-B13): In a stand-in run whose base branch gains a commit to an edited spec and whose `ts-traced` fails, the first invocation ends paused with no step entered after the check, and after the head is merged into the run's branch and the operator answers `retry` the run goes back to the earliest step that serves `ts-traced`
- OGT-AC26 (OGT-B14): In the stand-in runs of OGT-AC23 to OGT-AC25 the outcome judge has started no session when the run pauses, and in the run of OGT-AC23 it starts one after the answer `retry`
- OGT-AC27 (OGT-B15): In the stand-in run of OGT-AC25 the outcome check's evidence names `ts-spec-fresh` before `ts-traced`, and in the runs of OGT-AC23 and OGT-AC24 the one failing criterion it names is `ts-spec-fresh` and `ts-verify` respectively
- OGT-AC28 (OGT-B16): In a stand-in run whose verification command exits 0 at the run's base commit and 1 at the gate, the run is sent back to the earliest step that serves `ts-verify`, the reason for that step's visit holds the last lines the command printed, and the run does not pause
- OGT-AC29 (OGT-B16): The outcome check's evidence for a command that fails with the same exit code at the run's base commit names the command, its exit code at the gate, its exit code at the base commit and the reason, and for a run with no base commit it names the command as not compared
- OGT-AC30 (OGT-B17): With the started commands counted, a verification command that exits 0 at the gate is never started at the run's base commit, and one that fails is started there once in a visit however many times the check runs in it, and once more in the next visit
