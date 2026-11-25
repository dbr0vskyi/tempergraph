# Visit session record

## Purpose

What a gate's check is given of the sessions of its unit's current visit, besides the session of its own attempt: the calls of every attempt of the visit, so that a check can hold a step to what all its sessions did and not only to what the last one did. The attempt's own record, its shape and the cases in which there is none are [CHK-B24 and CHK-B25](check-contract-and-command-runs.spec.md); this spec owns only the record of the whole visit. A visit of a unit starts when the run reaches it, and a trip back to the unit starts a new one ([CMP-B12](compiler-and-flow.spec.md)). Workflow authors depend on it.

## Behaviours

### VSR-B1 A check is given the calls of every session of the visit

WHEN a gate's check runs after an attempt that has a session record ([CHK-B24](check-contract-and-command-runs.spec.md)) THE engine SHALL give the check `visit_session`: the calls of that attempt and of each earlier attempt of the same visit of the same unit (of the same item, for an item of a map) that has a session record, in the order the attempts ran, each call shaped as in CHK-B24.

- GIVEN attempt 1 that opened `docs/a.md` and a retry attempt of the same visit that opened `docs/b.md` WHEN the check runs after the retry THEN `visit_session` lists the call on `docs/a.md` and then the call on `docs/b.md`, and `session` lists the call on `docs/b.md` only
- GIVEN a visit that opened `docs/a.md` and a later visit, started by a trip back, whose first attempt opened `docs/c.md` WHEN the check runs after that attempt THEN `visit_session` lists the call on `docs/c.md` and no call of the first visit
- GIVEN attempt 1 whose session made no call and a retry attempt that opened `docs/b.md` WHEN the check runs after the retry THEN `visit_session` lists the call on `docs/b.md` only

### VSR-B2 No record of the attempt, no record of the visit

WHEN a gate's check runs after an attempt whose session record is `None` ([CHK-B25](check-contract-and-command-runs.spec.md)) THE engine SHALL give the check `visit_session` as `None`, whatever the earlier attempts of the visit did.

- GIVEN attempt 1 that opened `docs/a.md` and a retry attempt whose executor reported tool names only WHEN the check runs after the retry THEN `visit_session` is `None`
- GIVEN a check that runs as a preview WHEN it reads `visit_session` THEN `visit_session` is `None`

## Acceptance criteria

- VSR-AC1 (VSR-B1): A check run after a retry attempt, whose first attempt opened one file and whose retry opened another, sees `visit_session` with the two calls in the order of the attempts and `session` with the retry's call only; a check run in a visit started by a trip back sees no call of the earlier visit; a first attempt that made no call adds none
- VSR-AC2 (VSR-B2): A check run after an attempt whose record is `None`, and a check run as a preview, sees `visit_session` as `None`
