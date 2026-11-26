# The review reader's independence rests on what it is handed and on its session record

## Context

Two runs of the workflow passed every gate, and a reader who was given only the diff and the task's criteria then found a defect that blocks the change's use in about three minutes (the task text, `batch-queue/tasks/i173.md`). The review unit of [the spec](../specs/independent-review.spec.md) is that reader's place. Its value is its independence, and the task allows no engine change: the engine names no workflow ([ADR `the-engine-names-no-workflow`](../../../tempergraph/docs/adr/the-engine-names-no-workflow.adr.md), [OVR-B10](../../../tempergraph/docs/specs/overview.spec.md)), so a need the engine cannot meet is written in the package's docs as a general capability.

What the engine offers today, read in it:

- A step declares its tools, its commands, its values, its scripts and its gate; no field names a path its session may not read (`StepSpec`, `plugins/tempergraph/engine/src/tempergraph/contracts.py` lines 198-215). Every step session starts in the run's workspace (`run/nodes.py` lines 588-597), so the repository a reader reads holds each file a step committed.
- The package commits what each step left, after the step (`after=[_commit()]`, `workflow/temperspec/routing.py` lines 457-475). The triage note, the hand-off, the plan and the code report are committed on the branch, so they are both in the repository and in the diff since the run's base.
- A step prompt holds its template, and the engine adds sections of its own: the unmet warnings of the previous unit's judgement, the visit's reason and the lessons of earlier runs (`run/nodes.py` lines 552-569, [PRM-B6](../../../tempergraph/docs/specs/prompt-rendering.spec.md)). A template may name the value of any earlier unit (`run/nodes.py` lines 1106-1122).
- A script gets a context with the request, the artifacts, the values and the settings, and no git facts (`run/nodes.py` lines 1181-1187). A check gets the git facts with the run's base commit and the calls of the attempt's session (`run/nodes.py` lines 1568-1587, [CHK-B24](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)); where the engine has no trustworthy record, the check has none ([CHK-B25](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)).
- Only a judge's finding sends a run back, by naming an earlier unit's artifact key in `defect_in` (`run/judging.py` lines 283-286, `run/gate.py` lines 435-448); a check that fails a mechanical criterion starts no judge, and the step is retried with the finding in its prompt ([CHK-B1](../../../tempergraph/docs/specs/check-contract-and-command-runs.spec.md)). The count of trips back is kept for each back target, not for the gate (`run/gate.py` lines 439-441).
- The engine's blocker that every point of a visit's reason is addressed is a sentence in the visited step's prompt and in its judge's prompt (`render/prompt.py` lines 97-100, `run/judging.py` lines 176-178). It is no criterion with a result of its own, so no record of it exists for a point or for a visit ([RRN-B14](../../../tempergraph/docs/specs/reruns-and-feedback.spec.md)).

## Decision

We will build the review with no engine change and hold the reader's independence in two layers, as [the spec](../specs/independent-review.spec.md) says, and write each need the engine cannot meet below.

- What the unit hands over: the change and the criteria, a reader prompt that names nothing else of the run, and a place behind a unit with no judge, so that no unmet warning of an earlier gate reaches the prompt (IRV-B3 to IRV-B5).
- What the unit confirms afterwards: from the session record, that the reader opened no hand-over document and wrote no file but its findings document (IRV-B6, IRV-B7).

The needs, each a general capability of the engine and none naming a workflow:

- A step may declare the paths its session is refused, for reading and for searching. Until it can, a search may still print lines of a document the run wrote; the check sees an opened file and never a search's lines.
- A script's context carries the run's base commit, as a check's does. Until it does, the package finds the base itself.
- A unit's visit leaves a result, readable by a later script or check, for each numbered point of its reason: whether the point was addressed. Until it does, the findings document records the result of the whole visit for each finding (RVF-B7).

## Options considered

### A. Build with what the engine offers and write the needs (chosen)

For: the unit exists now and its independence is measured on each run, where the engine gives a record; the needs are stated once, for the engine's own tasks; the task asks for it. Against: a search can still show the reader a line of a hand-over document; with no record (a stand-in executor, a preview, hidden tool inputs) the check does not apply; the findings of a first review all get the visit's one result.

### B. Change the engine first

For: independence by refusal rather than by a check afterwards; a per-point result of the visit-reason blocker. Against: the task excludes an engine change; each change is a task of its own with its own specs and tests; the unit waits for all of them.

### C. State the rule in the prompt alone

For: nothing to check, nothing to build. Against: "never given" cannot be tested on a run, and a reader that opens the plan looks independent; the package's own prompts already pair a stated rule with a check of the record ([SRC-B1](../specs/session-record-checks.spec.md)).

### D. Give the reader a copy of the repository without the run's documents

For: the strongest independence. Against: every step session of a run starts in the run's workspace, and no step field points a session elsewhere, so it is an engine change as well.

## Consequences

A reader that opens a hand-over document fails its gate with a finding that names the document, and a new session reads again; a reader that writes another file fails the same way. The cost is one more session on a miss. Independence is high and not absolute: a search of the repository can show lines of a hand-over document, and no gate sees it. The unit's gate can send a run back only through a judge's finding, so a judge of that gate names the step a blocking finding goes back to. It is a session of its own and not the reader, and it reads the findings document and the earlier artifacts it needs to name the step; the rule that picks the step is model-free (IRV-B9, IRV-B10), and the judge applies it.

The budget of one trip back has to hold for the unit and not for each back target, since the engine counts for each target: the plan step takes it into account when it builds the gate.

## Revisit when

The engine lets a step declare refused paths, gives a script the run's base commit, or leaves a result for each point of a visit's reason.
