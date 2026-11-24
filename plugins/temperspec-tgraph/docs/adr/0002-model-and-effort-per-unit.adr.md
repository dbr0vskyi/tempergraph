# 0002 Model and effort per unit

Status: accepted, to be confirmed by the owner

## Decision

Every step and every judge states its model tier, its effort and one sentence of why, in the workflow's declaration and in its blueprint, so no session runs at a default nobody chose (owner, 2026-11-21). The values below were a first assessment made without a run; the first measured runs (below, under Consequence) leave them as they are.

| Unit | Step | Why | Judge | Why |
|---|---|---|---|---|
| `setup` | medium, high | It reads a whole repository once and writes the specs every later task trusts | medium, medium | It compares each written spec with the code it describes, one file at a time |
| `triage` | medium, medium | It reads one task and the spec index to sort gaps and pick a route; the check verifies the note's shape | medium, medium | It reads one note against the task; the route it confirms is cheap to correct later |
| `discovery_short` | medium, high | It confirms that each behaviour triage cited answers its gap and lists the files the plan will need; it designs nothing, and the check verifies the cited ids | medium, high | A gap wrongly taken as answered costs a whole code session, so the verdict keeps the effort of the full visit's judge |
| `discovery` | medium, max | It closes gaps by research and design, the deepest thinking in the workflow, and nothing downstream rechecks its facts | medium, high | It decides whether each gap is really closed across specs, records and research notes |
| `plan` | medium, high | It designs across specs and code, and a weak plan costs a whole code session | medium, high | It judges that the design covers every criterion and contradicts no spec it references |
| `expand` | medium, medium | It turns an approved plan into task rows and decides little | medium, medium | It compares the task rows with the plan they expand |
| `code` | medium, high | It is a long session that builds test first; the tests and the code check catch slips that more effort would not | medium, high | It reads the diff, the report and the proof of every criterion, and a miss ships a defect |

The outcome gate's judge keeps the engine's default effort: the engine's outcome declaration takes a judge model and no effort yet.

## Alternatives

One effort for the whole workflow, which pays for deep thinking where a step only sorts or copies; The large tier for `discovery`, `plan` and `code`, left until a measured run shows the medium tier at high effort is not enough; An effort ladder on `code`, left until its judge is calibrated, since an uncalibrated judge never moves a ladder

## Consequence

A run costs more than at the default effort on `setup`, `plan`, `code` and three judges, and less surprise comes from a changed default. Efforts `xhigh` and `max` are not yet shown by a live probe on every alias; `discovery` keeps `max` as before. The row `discovery_short` was added by [0003](0003-short-discovery-visit.adr.md), which replaces no row.

The first measured sizing comes from six real runs on this repository (cloud container, `claude` 2.1.331, worktree mode, conversation `never`), each building one or two issues: runs `i17-18` (the TS-L2 real run, end to end with no pause: 9.25 USD, 58 minutes), `i16` (8.55), `i9` (9.17), `i106` (6.81), `i6-8` (13.38) and `i58` (19.24). `discovery` is the largest step in every one of them, 40 to 48 percent of the run (3.40 to 9.21 USD, 15 minutes or more of one session); `code` takes 0.63 to 2.45 USD, `plan` 0.51 to 2.31, `expand` 0.36 to 2.19, `triage` 0.29 to 0.58, each `read_gap` session under 0.30, and all judges together 0.83 to 2.42. Nothing in these runs shows that a step or judge needs more effort; `discovery` at `max` is the first place to look for a saving.
