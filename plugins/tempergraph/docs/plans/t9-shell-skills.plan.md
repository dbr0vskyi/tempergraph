---
goal: Build the shell skills of release 1, the authoring verbs and the tempergraph:author skill, the troubleshooter and the install skill
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: In progress
tags: [track-plan, tempergraph, T9]
tracker: none
spec: plugins/tempergraph/docs/specs/89-workflow-authoring.spec.md
spec_commit: a94f977
task_id: first-release-t9
---

# T9 Shell skills

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T9 |
| Specs | [SHL](../specs/19-plugin-shell.spec.md), [AUT](../specs/89-workflow-authoring.spec.md), [OUT](../specs/90-run-outcome.spec.md), [SCF](../specs/91-blueprint-and-scaffold.spec.md), [LSK](../specs/65-lifecycle-skills.spec.md) |
| Builders | T9.1 is built by the main build thread; T9.2 and T9.3 by the T8 thread, after T8 |

**Status: In progress.** T9.2 has its status pass and the criteria lint.

Status pass: AUT is `ready-for-implementation`, with the release 1 decisions in AUT §2.8. SHL and LSK get theirs in the first row of T9.1 and T9.3.

Live checks (owner's machine, signed-in `claude`; not faked here):
- AUT-AC-1 and AUT-AC-8: the rubric scenarios per entry path and per guidance rung need the skill run by a model.
- SHL-AC-2: a rubric scenario per skill.
- P-CC-9: `claude -p --plugin-dir` loads the plugin's skills headless (also listed in T8).

## T9.1 Run driver and project bootstrap

Goal: start, report by exit code, walk the person through pauses with `--relayed`; add the state-root ignore rule.

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 9.1.0 | | Rows to be written by the main build thread | SHL | | P1 | ○ | |

## T9.2 Authoring

Goal: the `author` verbs and the `tempergraph:author` skill per AUT: entry paths, inventory, backwards interview, verification classification, criteria lint, guidance rungs, authoring record and revise mode, ending in a registered, audited, stamped workflow.

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 9.2.0 | `docs/specs/89-*` | Status pass: AUT `ready-for-implementation`, release 1 decisions in AUT §2.8 | AUT | | P1 | ✓ | 2026-11-20 |
| 9.2.1 | `engine/src/tempergraph/author/criteria_lint.py`, `engine/tests/test_criteria_lint.py` | The criteria lint of AUT §2.4.1 and the sufficiency check, over an outcome document; a must-fire and a must-not-fire fixture per code (AUT-AC-7, first half); joined to validation (warnings), `author verify` rung 1 and the readiness report | AUT §2.4.1, §2.8, LIF §2.2 | yes | P1 | ✓ | 2026-11-20 |
| 9.2.2 | `engine/src/tempergraph/author/inventory.py`, `engine/tests/test_inventory.py` | The intake inventory of AUT §2.3 on a fixture repository: every row detected, no source text in the record (AUT-AC-2); a self-check in a solution recorded as a claim (AUT-B1) | AUT §2.3, §2.8 | yes | P1 | ✓ | 2026-11-20 |
| 9.2.3 | `engine/src/tempergraph/author/session.py`, `engine/src/tempergraph/cli/author.py`, `engine/tests/test_author_session.py` | `author start\|intake\|check\|show\|list\|drop\|approve`; phase approvals by digest, cleared on a later edit; one session per name; nothing under the package folder before phase 7 (AUT-AC-4); phase 2 not approvable while the sufficiency check fails (AUT-AC-7, second half); resume from `author show` alone (AUT-AC-5) | AUT §2.1, §2.4, §2.6, §4, §2.8 | yes | P1 | ○ | |
| 9.2.4 | `engine/src/tempergraph/author/session.py`, `engine/src/tempergraph/author/scaffold.py` | Revise mode: `author start <workflow> --revise`, the change classes against the package's outcome, the weakening rows marked, the new revision written with `origin: revise_session` by `scaffold --update-docs` (AUT-AC-6) | AUT §2.7, OUT §2.6 | yes | P1 | ○ | |
| 9.2.5 | `skills/author/SKILL.md`, `skills/author/references/*.md` | The `tempergraph:author` skill: modes, entry paths, phases, search order, guidance ladder, executor consequences read from `executors` (SHL-AC-3), criteria examples per task kind | AUT, SHL, SCF | | P1 | ○ | |
| 9.2.6 | `engine/tests/test_shell_skills.py` | Skill structure: frontmatter, references resolve, no shipped workflow named (SHL-AC-1), every verb a skill names exists and every option it passes is built | SHL §6 | yes | P1 | ○ | |
| 9.2.7 | live, owner's machine | AUT-AC-1, AUT-AC-8 rubric scenarios | AUT §6 | | P1 | ○ | |

## T9.3 Troubleshooter and install

Goal: read-only diagnosis from logs, detail and audit; the install skill.

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 9.3.0 | `docs/specs/19-*`, `docs/specs/65-*` | Status pass for the troubleshooter rows of SHL and the install procedure of LSK §2.3 | SHL, LSK | | P1 | ○ | |
| 9.3.1 | `skills/troubleshoot/SKILL.md` | Read-only diagnosis with ranked hypotheses and next actions from `status`, `logs`, `report`, `audit` | SHL §2 | | P1 | ○ | |
| 9.3.2 | `skills/install/SKILL.md` | The install procedure of LSK §2.3 | LSK §2.3 | | P1 | ○ | |
