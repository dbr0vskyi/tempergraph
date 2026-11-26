# Ts-spec-sync

Status: accepted, to be confirmed by the owner

## Decision

Accept ts-spec-sync as judged at the outcome gate with no deterministic check serving it on every step; its trust stays uncalibrated until its judge seeds are graded by a signed-in judge (author verify rung 8).

A failing grade of ts-spec-sync reaches the step that owns the specs the run edited and never the first step of the run. The engine derives that step from the criteria that serve ts-spec-sync, so only criteria of the steps that write specs, plan their edits or build them serve it: ts-dis-links, ts-plan-spec and ts-code-related. The outcome gate spec names the step for each path ([OGT-B6](../specs/outcome-gate.spec.md), [OGT-B7](../specs/outcome-gate.spec.md), [OGT-B8](../specs/outcome-gate.spec.md)) and what the step is told ([OGT-B11](../specs/outcome-gate.spec.md), [OGT-B12](../specs/outcome-gate.spec.md)).

## Alternatives

A person signs off spec agreement on every run; A deterministic check for contradictions between behaviours, which no rule can express

For where a failing grade goes: the criteria of the setup step and of the triage step serve it as well, so the engine sends the run to the earliest of them, and one sentence of a spec costs triage, the reading sessions, discovery, the plan and the code once more; the judge names the place of the defect, which decides nothing at the outcome gate, because the engine derives the target from the criteria that serve the final criterion and never from the judge's answer ([OUT-B16](../../../tempergraph/docs/specs/run-outcome.spec.md)); a change of the engine's rule so that a named place decides, which the package cannot make and which leaves the rule as it is ([OUT-B3](../../../tempergraph/docs/specs/run-outcome.spec.md)).

## Consequence

Until rung 8 has run and the outcome judge is accepted, a contradiction between specs can pass the outcome gate on the judge's word alone; ts-dis-links (one definition per id), ts-plan-spec (judged at the plan gate) and ts-code-related (judged at the code gate) are the earlier lines of defence.

A failing grade costs the step that owns the specs and what follows it, not the whole run. A run with no full discovery goes to the plan step, which may add a row that edits the spec or may say that the discovery output is at fault, which its gate sends to the full discovery; the quick lane plans and edits no spec, so the code step is the one step on its path with a criterion that serves ts-spec-sync. The engine returns once to each step, so a failing grade that follows a return to the same step asks a person ([OUT-B3](../../../tempergraph/docs/specs/run-outcome.spec.md)).
