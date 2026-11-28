# A removal runs after the session and before its gate

## Context

A plan row that removes a file stops a run: the session of the code step has no tool that deletes a file, tries `git rm`, and the run pauses with cause `tool_access`. The two ways out that the task names are a script after the step that carries the removal out with no model, and a tool the step declares; it rules out giving the session a general shell or `git rm`. The choice also fixes when the file goes away in relation to the gate that checks the change, which decides what the verification commands and the checks see.

## Current state

- The session of the code step and of a phase declares `edit`, `write` and a `shell` limited to read-only git and the repository's declared commands (`plugins/temperspec-tgraph/workflow/temperspec/__init__.py` lines 267-278).
- The Claude executor turns `shell` into one allow rule for each command the step declares (`plugins/tempergraph/engine/src/tempergraph/executors/claude.py` lines 83-104).
- The engine's tool capabilities are `read`, `search`, `list`, `web_fetch`, `web_search`, `edit`, `write`, `shell`, `subagent`, `mcp` and `skill`, and none deletes or moves a file ([CON-B11](../../../tempergraph/docs/specs/contracts.spec.md)).
- A step whose session recorded a refused call makes the run pause with cause `tool_access` (`plugins/tempergraph/docs/specs/budgets-and-failures.spec.md` line 86).
- The `after` scripts of a step run in one attempt, in declaration order, only when the session ended ok, and before the gate decides ([SCR-B2](../../../tempergraph/docs/specs/script-units-and-hybrid-steps.spec.md); `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` lines 703-705 and 1304-1313).
- A callable of an `after` script is given the run's artifacts and values and no map item, and one that raises fails the attempt as an environmental failure that spends no retry (`plugins/tempergraph/engine/src/tempergraph/run/nodes.py` lines 1263-1271 and 758-760).
- The code and phase steps already end with the `commit` script, which stages everything with `git add -A`, so a deletion is committed (`plugins/temperspec-tgraph/workflow/temperspec/routing.py` lines 546-564).
- The code gate takes a marked row's file as changed when it is among the paths that differ from the base, which a deleted file is, and then runs the verification commands itself (`plugins/temperspec-tgraph/workflow/temperspec/checks.py` lines 1815-1823; `plugins/tempergraph/engine/src/tempergraph/git.py` lines 301-314).
- The regeneration unit runs after the code gate, starts only commands the repository declares and takes nothing from the plan ([RGN-B1](../specs/regeneration.spec.md), [RGN-B16](../specs/regeneration.spec.md); `plugins/temperspec-tgraph/workflow/temperspec/regeneration.py` lines 172-197).
- A mark on a row whose file a later commit of the run changed is refused ([KMK-B3](../specs/kept-marks.spec.md)).

## Forces

- C1 (constraint): The session gets no general shell and no `git rm`. Source: the out-of-scope list of `plugins/temperspec-tgraph/docs/tasks/i166e.triage.md`
- C2 (constraint): The verification commands and the checks of the gate see the tree the run delivers. Source: `ts-code-verify` in `plugins/temperspec-tgraph/docs/specs/code.spec.md`
- C3 (constraint): A marked row's file is not changed by a commit later than the commit that marks the row. Source: [KMK-B3](../specs/kept-marks.spec.md)
- C4 (constraint): An `after` script cannot tell which phase it follows, because it is given no map item. Source: `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` lines 1263-1267
- C5 (constraint): The engine names no workflow, so a change to the engine is a general capability stated in its own specs. Source: `CLAUDE.md`
- F1: A file that moves stays readable while the session writes its new path.
- F2: The smallest change: reuse the `after` scripts, the commit script and the gate's checks.
- F3: A failure names its file for the owner.
- F4: No model session and no command run that nothing needs.

## Options considered

### A. A script in the `after` list of the code step and of the phase step, before the commit

How it works: a callable reads the plan's removal rows, removes the file of each row that the session marked and that is still in the workspace, and the commit script that follows commits the deletion with the session's files, all before the gate decides.
For: C2 and C3 hold, because the gate and the marking commit see the removed file (F1: the file is there while the session works). It reuses the engine's hybrid step (F2) and starts no session (F4). Against: F3, because the engine records only the exception type of a callable that raises, so the file needs a report that the checks read; F4, because the tree changes after the session's preview, so the gate runs each command again.

### B. A script unit after the code gate, beside the regeneration unit

How it works: a unit with no session reads the plan and removes the files, with a check that sends a failure back to the code step, as the regeneration unit does.
For: F3, since a report and a check name the file as the regeneration check does. Against: breaks C2, because the gate's commands run while the file is still there and a test that imports it passes at the gate; breaks C3, because the removal commit follows the marking commit.

### C. A tool the step declares that deletes or moves a file

How it works: the engine gains a capability that deletes or moves a file, bound for each executor, and the code and phase steps declare it.
For: F1, since the session removes the file when it has no further use for it. Against: F2, because a new capability is a release of the engine, bound for four executors (CON-AC5 of `plugins/tempergraph/docs/specs/contracts.spec.md`) and open to a session that deletes any file, where a plan row names one file; C5 holds only if it is built as a general capability.

### D. The commands `git rm` or `rm` added to the code and phase steps

How it works: the steps' `commands` gain `git rm` or `rm`.
Against: breaks C1.

## Decision

We will take option A: the workflow removes the file of each removal row that the session marked, in a script in the `after` list of the code step and of the phase step, before the commit that precedes the gate.

## Decision rationale

- C1: met; the session gets no new tool or command.
- C2: met; the removal is done before the gate runs its commands and checks.
- C3: met; the commit script that follows holds the deletion in the same commit as the marks.
- C4: met; the script takes the marked rows of the plan as its trigger and needs no item, and a later phase's row is unmarked until its own session marks it.
- C5: met; no engine change is needed.
- F1: met; the file is in the workspace until the session has ended.
- F2: met; only the script and the row kind are new.
- F3: given up in the engine's record and met by a report the gate's checks read, which names the file and the reason.
- F4: met for the model (no session); given up for commands, which the gate runs again after the removal.

## Consequences

A plan can say that a file goes away, and a run removes it with no person and no session. A plan with a removal row costs the gate one run of each verification command, because the removal changes the tree after the session's preview. No test of the plan can need the file to be absent while the session works.

## Risks

- A session marks a removal row before a later row has finished with the file. Limited by: the briefs tell the session to mark the row once no other row needs the file, and the check of the step fails a test that needs the file. Noticed by: a phase check or the code check failing on a file that the removal took.
- The pause of a refused removal names no file. Limited by: the script records each refusal in a report and does not raise for a path it refuses. Noticed by: a pause whose evidence lacks the path.

## Assumptions

- A1: The session writes its marks into the plan before it ends, so the script reads them from the workspace. Check: step 6 of `plugins/temperspec-tgraph/prompts/code.md` and step 8 of `plugins/temperspec-tgraph/prompts/phase.md`. If wrong: no file is removed, and the gate fails the row's changed-file check, naming the row.
- A2: The process of the run may delete a tracked file of its workspace. Check: a fixture run on each operating system the engine supports. If wrong: the run pauses naming the file.

## Revisit when

The engine's tool capabilities in `plugins/tempergraph/docs/specs/contracts.spec.md` include one that deletes or moves a file.
