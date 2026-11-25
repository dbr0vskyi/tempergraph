---
goal: Build the shell skills of release 1, the authoring verbs and the tempergraph:author skill, the troubleshooter and the install skill
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: In progress
tags: [track-plan, tempergraph, T9]
tracker: none
spec: plugins/tempergraph/docs/specs/workflow-authoring.spec.md
spec_commit: a94f977
task_id: first-release-t9
---

# T9 Shell skills

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T9 |
| Specs | [SHL](../specs/plugin-shell.spec.md), [AUT](../specs/workflow-authoring.spec.md), [OUT](../specs/run-outcome.spec.md), [SCF](../specs/blueprint-and-scaffold.spec.md), [LSK](../specs/lifecycle-skills.spec.md) |
| Builders | T9.1 was built by the main build thread; T9.2 and T9.3 by the T8 thread, after T8 |

**Status: In progress.** T9.1 is built: the run driver and the project bootstrap. T9.2 is built: the criteria lint, the inventory, the session verbs, revise mode and the `tempergraph:author` skill; its rubric scenarios are live checks. T9.3 is built: the troubleshooter and the install skill; their rubric scenarios are live checks.

Status pass: AUT and LSK are `ready-for-implementation`, with the release 1 decisions in AUT-B12, AUT-B15, AUT-B19, AUT-B24, AUT-B25 and LSK-B9. SHL is `ready-for-implementation` from T9.1; SHL-B5, SHL-B12, SHL-B13 holds the authoring and troubleshooter skills' release 1 notes and §5 the run driver's and bootstrap's.

Live checks (owner's machine, signed-in `claude`; not faked here):
- AUT-AC1 and AUT-AC8: the rubric scenarios per entry path and per guidance rung need the skill run by a model.
- SHL-AC2: a rubric scenario per skill.
- P-CC-9: `claude -p --plugin-dir` loads the plugin's skills headless (also listed in T8).

## T9.1 Run driver and project bootstrap

Goal: start, report by exit code, walk the person through pauses with `--relayed`; add the state-root ignore rule.

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 9.1.0 | `docs/specs/plugin-shell.spec.md` | Status pass: SHL `ready-for-implementation`, run driver and bootstrap notes in SHL-B7, SHL-B8, SHL-B11 | SHL | | P1 | ✓ | 2026-11-20 |
| 9.1.1 | `skills/run/SKILL.md`, `skills/run/references/pauses.md` | `tempergraph:run`: catalog match, `run --check` (ok, needs at most four rounds, error, broken), background start, report by exit code, pauses back to the person with `resume --relayed`, never proceed after an infra failure | SHL-B5, B1, B2, §4 | | P1 | ✓ | 2026-11-20 |
| 9.1.2 | `skills/bootstrap/SKILL.md`, `skills/bootstrap/scripts/ignore_rule.py` | `tempergraph:bootstrap`: the ignore-rule helper is the only writer; it asks git, keeps bytes and line endings, lets a negation stand, and reports tracked files with the untrack command without running it | SHL-B5, LOS-B4 | yes | P1 | ✓ | 2026-11-20 |
| 9.1.3 | `engine/tests/test_run_skills.py` | The helper in throwaway repositories (exact bytes, CRLF, the inner ignore file not counted, negation, tracked files, not a repository); the run driver's verbs and options checked against the parser | SHL-AC1 | yes | P1 | ✓ | 2026-11-20 |
| 9.1.4 | live, owner's machine | SHL-AC2 rubric scenarios for the run driver: ask before guessing, never answer a pause | SHL-AC1 | | P1 | ○ | |

## T9.2 Authoring

Goal: the `author` verbs and the `tempergraph:author` skill per AUT: entry paths, inventory, backwards interview, verification classification, criteria lint, guidance rungs, authoring record and revise mode, ending in a registered, audited, stamped workflow.

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 9.2.0 | `docs/specs/workflow-authoring.spec.md` | Status pass: AUT `ready-for-implementation`, release 1 decisions in AUT-B12, AUT-B15, AUT-B19, AUT-B24, AUT-B25 | AUT | | P1 | ✓ | 2026-11-20 |
| 9.2.1 | `engine/src/tempergraph/author/criteria_lint.py`, `engine/tests/test_criteria_lint.py` | The criteria lint of AUT-B19, AUT-B20, AUT-B21 and the sufficiency check, over an outcome document; a must-fire and a must-not-fire fixture per code (AUT-AC7, first half); joined to validation (warnings), `author verify` rung 1 and the readiness report | AUT-B19, AUT-B20, AUT-B21, AUT-B12, AUT-B15, AUT-B24, AUT-B25, LIF-B13 | yes | P1 | ✓ | 2026-11-20 |
| 9.2.2 | `engine/src/tempergraph/author/inventory.py`, `engine/tests/test_inventory.py` | The intake inventory of AUT-B14, AUT-B15 on a fixture repository: every row detected, no source text in the record (AUT-AC2); a self-check in a solution recorded as a claim (AUT-B1) | AUT-B14, AUT-B15, AUT-B12, AUT-B19, AUT-B24, AUT-B25 | yes | P1 | ✓ | 2026-11-20 |
| 9.2.3 | `engine/src/tempergraph/author/session.py`, `engine/src/tempergraph/cli/author.py`, `engine/tests/test_author_session.py` | `author start\|intake\|check\|show\|list\|drop\|approve`; phase approvals by digest, cleared on a later edit; one session per name; nothing under the package folder before phase 7 (AUT-AC4); phase 2 not approvable while the sufficiency check fails (AUT-AC7, second half); resume from `author show` alone (AUT-AC5); scaffold reads intake's copies and marks the session finished | AUT-B11, AUT-B12, AUT-B16, AUT-B17, AUT-B18, AUT-B23, AUT-B15, AUT-B24, AUT-B19, AUT-B25 | yes | P1 | ✓ | 2026-11-20 |
| 9.2.4 | `engine/src/tempergraph/author/session.py`, `engine/src/tempergraph/author/scaffold.py` | Revise mode: `author start <workflow> --revise`, the change classes against the package's outcome, the weakening rows marked, the new revision written with `origin: revise_session` by `scaffold --update-docs`, which also writes `blueprint.json`; a changed outcome must bump its revision; nothing is written before the phase 7 yes (AUT-AC6) | AUT-B25, AUT-B12, AUT-B15, AUT-B19, AUT-B24, OUT-B20, OUT-B21, SCF-B11, SCF-B13, SCF-B15, SCF-B16, SCF-B17, SCF-B18, SCF-B19, SCF-B20, SCF-B22 | yes | P1 | ✓ | 2026-11-20 |
| 9.2.5 | `skills/author/SKILL.md`, `skills/author/references/*.md` | The `tempergraph:author` skill: modes, entry paths, phases, search order, guidance ladder, executor consequences read from `executors` (SHL-AC3), criteria examples per task kind; a core of 64 lines and six references read per phase | AUT, SHL, SCF | | P1 | ✓ | 2026-11-20 |
| 9.2.6 | `engine/tests/test_shell_skills.py` | Skill structure: frontmatter, references resolve, no shipped workflow named (SHL-AC1), every verb a skill names exists and every option it passes is built; applies to every skill under `skills/` | SHL-AC1 | yes | P1 | ✓ | 2026-11-20 |
| 9.2.7 | live, owner's machine | AUT-AC1, AUT-AC8 rubric scenarios | AUT-AC1 | | P1 | ○ | |

## T9.3 Troubleshooter and install

Goal: read-only diagnosis from logs, detail and audit; the install skill.

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 9.3.0 | `docs/specs/plugin-shell.spec.md`, `docs/specs/lifecycle-skills.spec.md` | Status pass: LSK `ready-for-implementation` with LSK-B9; SHL-B5, SHL-B12, SHL-B13 for the authoring and troubleshooter skills (SHL's status flips with T9.1) | SHL, LSK | | P1 | ✓ | 2026-11-20 |
| 9.3.1 | `skills/troubleshoot/SKILL.md`, `skills/troubleshoot/references/*.md` | Read-only diagnosis with ranked hypotheses and next actions from `status`, `facts`, the run log, `validate`, `audit`; the read-only grant as `allowed-tools`, checked by the structure test; five references by symptom | SHL-B5, SHL-B12, SHL-B13 | yes | P1 | ✓ | 2026-11-20 |
| 9.3.2 | `skills/install/SKILL.md` | The install procedure of LSK-B9, LSK-B10 at LSK-B9; its commands checked against the launcher's options (LSK-AC3, structurally) | LSK-B9, LSK-B10 | yes | P1 | ✓ | 2026-11-20 |
| 9.3.3 | live, owner's machine | SHL-AC2 and LSK-AC1 rubric scenarios for the troubleshooter and the install skill | SHL-AC1, LSK-AC1 | | P1 | ○ | |
