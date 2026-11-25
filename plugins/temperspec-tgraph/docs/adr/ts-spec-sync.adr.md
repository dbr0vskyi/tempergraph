# Ts-spec-sync

Status: accepted, to be confirmed by the owner

## Decision

Accept ts-spec-sync as judged at the outcome gate with no deterministic check serving it on every step; its trust stays uncalibrated until its judge seeds are graded by a signed-in judge (author verify rung 8).

## Alternatives

A person signs off spec agreement on every run; A deterministic check for contradictions between behaviours, which no rule can express

## Consequence

Until rung 8 has run and the outcome judge is accepted, a contradiction between specs can pass the outcome gate on the judge's word alone; ts-dis-links (one definition per id) and ts-code-related (judged at the code gate) are the earlier lines of defence.
