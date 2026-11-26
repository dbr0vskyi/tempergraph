# A decision by the caller that started a run is designed

## Context

Facts read in the code and in cited documents:

- The finding `agent_decided:<pause cause>` is made for every `rescue` touch that an agent decides, as a fault of the workflow (`plugins/tempergraph/engine/src/tempergraph/improve/causes.py`, the cause table and `derive`), and it is judged, clustered and filed like any fault ([SIL-B15](../specs/self-improvement.spec.md), [SUP-B7](../specs/supervision-metrics.spec.md)).
- Every decision and every start of a run carries a caller block with the caller's `host` and `host_session` ([PRV-B16, PRV-B17](../specs/caller-provenance.spec.md)), so the caller that started a run can be told from another.
- A review of seven real threads, each paused one to four times with every pause answered by the agent that ran the batch, found `agent_decided:escalation` recorded at every answered pause, meeting the count at two units and filed in each replayed ticket (`batch-queue/tasks/i170.review.md`, finding 7).
- The supervision metrics count the same decisions as undesigned rescues of level `consultant` ([SUP-B1](../specs/supervision-metrics.spec.md)). That count answers how much a run needed someone; it says nothing of whether the workflow is at fault.

## Decision

We will class the finding `agent_decided:<pause cause>` as `designed` when the caller recorded with the decision has the same `host` and the same recorded `host_session` as the caller recorded when the run started, and as `fault` otherwise (option A; [FRC-B6](../specs/friction-causes.spec.md)).

- A decision whose caller block records no host session stays a fault, because the starting caller cannot then be told from another.
- The supervision metrics keep counting the decision as an undesigned rescue; this record changes only the loop's class.

## Options considered

### A. Class `designed` for the starting caller's decisions (chosen)

For: the finding stays recorded and countable, the loop's judging and filing rules read the class and need no exception for it, and a decision by any other agent keeps its path. Against: a fault of the workflow that the starting agent keeps working around shows in the loop only through the cause of the paused unit's own finding, and only the supervision metrics show how often the agent rescued.

### B. Keep the class `fault` and keep the finding from filing by the count

For: no new class rule. Against: the finding still reaches the friction judge at every answered pause and costs an answer there, and a rule that keeps it from filing has to name which decisions it covers, which is the same test of the caller.

### C. Leave the class `fault`

For: nothing changes, and every rescue stays evidence. Against: with an agent as the operator of a batch the finding is made at every answered pause and files in a ticket beside the pauses' own causes, which buries them.

## Consequences

- A finding of the starting caller's decision is recorded, never judged and never filed. The cause of the pause itself is still judged, with the facts of what answered it ([SIL-B37](../specs/runs-without-a-final-exit.spec.md)).
- A decision by another agent, or by an agent whose host session is not recorded, keeps the class `fault` and files by the rules of SIL-B15 and SUP-B7.
- Risk: the fingerprint of a finding carries no class, so a `designed` row and a `fault` row of one cause at one unit share it, and the pattern rule counts runs by fingerprint ([SIL-B3](../specs/self-improvement.spec.md)). What limits it: a friction finding files only on the friction judge's answers ([FFD-B1](../specs/friction-filing-decisions.spec.md)), and a `designed` finding is never judged, so its runs add no answer. The figures an issue shows ([ISS-B12](../specs/loop-issues.spec.md)) would still count them.
- Risk: a run started by a schedule or an orchestration has a different caller at its start, so an agent that answers its pauses stays a fault there. What limits it: nothing; it is the same as before.

## Revisit when

A person asks that decisions on runs started by an orchestration or a schedule be designed too, or the supervision metrics change so that the starting caller's rescues stop counting as undesigned.
