# 0002 Model and effort per unit

Status: accepted, to be confirmed by the owner

## Decision

Every step and every judge states its model tier, its effort and one sentence of why, in the workflow's declaration and in its blueprint, so no session runs at a default nobody chose (owner, 2026-11-21). The values below are a first assessment made without a run; the first measured runs may move them.

| Unit | Step | Why | Judge | Why |
|---|---|---|---|---|
| `setup` | medium, high | It reads a whole repository once and writes the specs every later task trusts | medium, medium | It compares each written spec with the code it describes, one file at a time |
| `triage` | medium, medium | It reads one task and the spec index to sort gaps and pick a route; the check verifies the note's shape | medium, medium | It reads one note against the task; the route it confirms is cheap to correct later |
| `discovery` | medium, max | It closes gaps by research and design, the deepest thinking in the workflow, and nothing downstream rechecks its facts | medium, high | It decides whether each gap is really closed across specs, records and research notes |
| `plan` | medium, high | It designs across specs and code, and a weak plan costs a whole code session | medium, high | It judges that the design covers every criterion and contradicts no spec it references |
| `expand` | medium, medium | It turns an approved plan into task rows and decides little | medium, medium | It compares the task rows with the plan they expand |
| `code` | medium, high | It is a long session that builds test first; the tests and the code check catch slips that more effort would not | medium, high | It reads the diff, the report and the proof of every criterion, and a miss ships a defect |

The outcome gate's judge keeps the engine's default effort: the engine's outcome declaration takes a judge model and no effort yet.

## Alternatives

One effort for the whole workflow, which pays for deep thinking where a step only sorts or copies; The large tier for `discovery`, `plan` and `code`, left until a measured run shows the medium tier at high effort is not enough; An effort ladder on `code`, left until its judge is calibrated, since an uncalibrated judge never moves a ladder

## Consequence

A run costs more than at the default effort on `setup`, `plan`, `code` and three judges, and less surprise comes from a changed default. Efforts `xhigh` and `max` are not yet shown by a live probe on every alias; `discovery` keeps `max` as before.
