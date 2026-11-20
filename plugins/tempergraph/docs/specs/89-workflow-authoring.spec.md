---
title: Workflow authoring
type: component
status: review
prefix: AUT
adrs: [0016, 0031, 0109, 0110, 0111, 0113]
---

# Workflow authoring

## 1. Overview

Authoring turns what a person has, an existing solution, references and sources, or only an idea in a conversation, into a workflow package they can trust ([PKG](88-workflow-package.spec.md)). Its focus is the **good outcome**: what a good run leaves, and how each part of that, final and intermediate, is verified ([OUT](90-run-outcome.spec.md)). The interview works **backwards** from the final outcome to an intermediate outcome per step, then finds a verification for every criterion, preferring one the person already has, creating one where none exists, classifying each by who verifies it (script check, judge, person), and flagging, never hiding, a criterion with no trustworthy verification ([ADR-0109](../adr/0109-author-backwards-from-the-outcome-preferring-existing-verifications.adr.md)). Steps, prompts and models come after the outcome, because they serve it.


This spec replaces the phase list of [SHL §2.1](19-plugin-shell.spec.md). It owns the entry paths, the intake inventory, the interview and its phases, the verification search and classification, the authoring record, and the revise mode.

## 2. Contract

### 2.1 Surface

| Verb | Does | Writes | Spends |
|---|---|---|---|
| `author start <name> --from solution\|sources\|chat [<path>…]` | Opens an authoring session: a folder `<state root>/authoring/<id>/` holding `authoring.json`, the draft `outcome.json` and `blueprint.json` | the session folder | no |
| `author intake <id> <path>…` | Adds sources and runs the inventory (§2.3) on them | the session folder | no |
| `author check <id>` | Checks the drafts: OUT §4 on the outcome, SCF §2.1 on the blueprint, coverage and trust (OUT §2.3) | no | no |
| `author show <id> [--json]` | The session: phase, sources, outcome and verification tables, open decisions, assumptions | no | no |
| `author list`, `author drop <id>` | Sessions on this root; drop removes a session folder only | `drop` only | no |
| `blueprint`, `scaffold`, `author verify`, `literals` | [SCF §2.6](91-blueprint-and-scaffold.spec.md) | per SCF | `author verify --trial` only |

The skill calls these verbs and reads their JSON; it keeps its own state in the session folder, so an interrupted session resumes in a new conversation (`author show`). Paths given to `intake` must be inside the workspace or named explicitly by the person; connector content (a wiki page, a ticket) is read by the skill with the person's connectors and saved into the session folder as a source file first, so the inventory reads files only.

| Skill mode | Starts from | Ends with |
|---|---|---|
| `new` | `author start` | A registered, verified, stamped package in `dev` mode (§2.4 phase 9) |
| `revise` | `outcome candidates <workflow>` ([OUT §2.6](90-run-outcome.spec.md)) | A new `outcome.json` revision, re-checked (§2.7) |
| `upgrade` | The person's ask to upgrade | Hand-over to the upgrade skill ([LSK §2.5](65-lifecycle-skills.spec.md)) |

### 2.2 Entry paths

The three paths differ only in how the first drafts of the outcome and the verification candidates are found. From phase 2 on, the interview is the same.

| Path | The person brings | Intake reads first | First drafts come from | Watch for |
|---|---|---|---|---|
| `sources` | References: templates, good and bad examples, standards, checklists, a Definition of Done or Ready, style guides, acceptance criteria, review rules, docs pages, tickets | Headings, task lists, rules, numbered requirements, example structure | The statement and deliverables from the template and the examples; criteria from checklists and rules; known-bad examples as must-fail fixtures | Requirements that conflict between sources: shown side by side for the person to rank |
| `chat` | Only words | Nothing | The person's answers to the outcome questions (phase 2); then a **graded draft**: the skill writes two short contrasting sample outputs (or asks for one real example) and asks which is better and why | Criteria drift: people find criteria by grading ([R-105 B2](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md)); the skill expects the first list to change and says so |

A path can be mixed: a `chat` session may add sources later; every addition goes through `author intake`.

### 2.3 Intake inventory

`author intake` is model-free. It reads each source file and records, per source: `id`, `kind` (as the table above, plus `example_good`, `example_bad`), `locator` (a workspace path, or `saved:<file>` for connector content, never a URL with a token), `digest`, `private` (true by default for connector content), and the **verification candidates** it detects:

| Detected | From | Candidate |
|---|---|---|
| A test command | `pyproject.toml`, `package.json` scripts, `Makefile`, `justfile`, CI workflow files, a README's commands section | `existing:test` command prefix for a check |
| A linter, formatter or type checker | Their config files (`ruff`, `eslint`, `mypy`, `markdownlint`, …), pre-commit config | `existing:linter` / `existing:type_check` |
| A schema | JSON Schema, OpenAPI, frontmatter rules | `existing:schema` |
| A checklist | Markdown task lists, numbered "must" lists, a PR template | `existing:checklist`, one candidate per item |
| Acceptance criteria, Definition of Done or Ready | Headings with those names, Gherkin `Given/When/Then` | `existing:acceptance_criteria` / `existing:definition_of_done` |
| Review rules | `CODEOWNERS`, review guides, "reviewers check" sections | `existing:review_rule` |
| A template | Heading structure of a template file | `existing:template` (a heading check) |
| Example outputs | Files marked as examples by the person | Must-pass (`example_good`) or must-fail (`example_bad`) fixtures |

Candidates are proposals; the skill binds them to criteria in phase 4. The inventory records names, paths, counts and digests, never source text, in `authoring.json`; the text stays in the session folder, which is local ([SEC](14-security.spec.md), C9).

### 2.4 The interview


| Phase | Produces | How |
|---|---|---|
| 2 Final outcome | `statement`, `deliverables`, `final` criteria | Three questions: what would make you reject the result, what has gone wrong before, what does a reviewer check first. Each answer becomes one observable statement; a vague word is rewritten ("complete" → "every acceptance criterion in the ticket is addressed by at least one task") or dropped with a note |
| 3 Work backwards | `intermediate` outcomes, the unit chain, `serves` | From each deliverable, ask "what must be true just before this?" Each answer that is a checkable result of its own is a step boundary and an intermediate outcome; stop at the run's input. Every intermediate criterion names the final criteria it serves; a final criterion nothing serves and the outcome gate cannot verify is shown as uncovered |
| 4 Find verifications | `verified_by`, `verifier`, `source` for every criterion; the trust profile | The search order below; the classification table shown with each criterion's trust (OUT §2.3) |
| 5 Steps' work | Per unit: kind, prompt outline, tools, executor, model, policies | Unit kinds offered where the interview points to them ([SHL §5](19-plugin-shell.spec.md)); executor consequences from `executors` ([SHL-B3](19-plugin-shell.spec.md)); every option not asked takes its documented default and is shown |
| 7 Approval | A yes on the blueprint, the outcome table and the verification table together | `blueprint draw` ([SCF §2.2](91-blueprint-and-scaffold.spec.md)); a change redraws |
| 8 Scaffold | The package | `scaffold` ([SCF §2.4](91-blueprint-and-scaffold.spec.md)) |
| 9 Verify, register, trial, stamp | A checked, registered, stamped package in `dev` | `author verify` ([SCF §2.5](91-blueprint-and-scaffold.spec.md)); calibration cases seeded from the trial |

**Verification search order (phase 4)**, taken in turn for each criterion:

| Order | Look for | Class | Source |
|---|---|---|---|
| 1 | A candidate from the inventory that decides this criterion (a test, a linter rule, a schema, a checklist item a script can test) | `check` | `existing:<kind>` |
| 3 | A part a check can decide and a part that needs reading | split into a `check` and a `judge` criterion serving the same final criterion | — |
| 4 | Reading and understanding, against named references the judge can open | `judge`, with `check_method` and references | `existing:<kind>` when the method comes from a review rule or checklist, else `created` |
| 5 | Authority or knowledge only a person has (safe to publish, fits the strategy) | `person`, with `role` and `question` | `interview` |
| 6 | Nothing trustworthy | `none`, with `reason` and `risk`; the skill offers the cheapest way to make it verifiable later (a feedback channel, a reviewer, a fixture) | — |

The skill prefers an earlier row and says why when it takes a later one. A blocker it cannot place above row 6 is put to the person as a decision: make it a `person` sign-off, accept it as `none` (recorded as a decision record in the workflow's docs, [PKG §2.5](88-workflow-package.spec.md)), lower it to a warning, or drop it.

### 2.5 Decisions and assumptions

Each choice the person makes against the skill's draft, each criterion dropped as not observable, each `none` accepted, each executor choice with a stated consequence, and each step boundary the person moved becomes a **decision** in `authoring.json` and, at scaffold, a decision record in the workflow's `docs/adr/` ([ADR-0113](../adr/0113-the-workflow-docs-set-is-provisional-until-temperspec-owns-it.adr.md)). Each assumption the person did not settle goes to `outcome.json` `assumptions` and to the overview spec's open questions.

### 2.6 The authoring record (`authoring.json`)

| Field | Meaning |
|---|---|
| `schema_version`, `id`, `name`, `path` (`solution`, `sources`, `chat`, or a list for a mixed session), `mode` | |
| `sources[]` | §2.3, metadata only |
| `candidates[]` | Detected verification candidates with their source id and whether a criterion used them |
| `phases[]` | Per phase: approved at, by (`Caller`), the digest of the draft approved |
| `decisions[]` | §2.5: id, phase, subject (criterion or unit id), choice, alternatives, consequence, decided by |
| `blueprint_digest`, `outcome_revision` | What was approved |
| `verify` | The last `author verify` report id and result ([SCF §2.5](91-blueprint-and-scaffold.spec.md)) |

The record is copied into the package at scaffold and kept there; it is outside the content digest ([PKG-AC-7](88-workflow-package.spec.md)).

### 2.7 Revise mode

| Step | Rule |
|---|---|
| 1 Evidence | `outcome candidates <workflow>` lists the signals of [OUT §2.6](90-run-outcome.spec.md) with thread ids and counts; the skill reads only what the person opens, from the local evidence files |
| 2 Draft | For each candidate the person picks: a new or changed criterion, its class by the §2.4 search order, and the change class (strengthening, weakening, neutral) |
| 3 Approve | The outcome and verification tables before and after, with the weakening rows marked; one yes |
| 4 Write and check | A new `outcome.json` revision with an `OutcomeRevision` (`origin: revise_session`), the docs specs updated by `scaffold --update-docs`, then `author verify` without trial; a new check needs its fixtures, a moved verifier needs the evidence OUT §2.6 asks |
| 5 Producer changes | A prompt or step change the revision suggests is a separate change after this one, grader first ([ADR-0031](../adr/0031-steps-and-their-graders-change-apart.adr.md)) |

## 3. Behaviours

**AUT-B1 From a solution.** Given a person with a shell script and a prompt file that together write release notes, and the script's own test that greps for "## Fixes", when `author start release-notes --from solution scripts/notes.sh prompts/notes.md tests/test_notes.sh` and intake run, then the inventory records a test command candidate and a heading candidate; the skill plays back three stages, proposes `rn-sections` as `check` (`existing:test`), and flags the prompt's line "check that you covered everything" as a self-check, not a verification.

**AUT-B2 From sources.** Given a release-page wiki template and one finished page saved from a connector, when intake runs, then the template's headings become one `existing:template` candidate, the finished page an `example_good` fixture, and the statement is drafted from the page's purpose; no URL or page text is written to `authoring.json`.

**AUT-B3 From a chat.** Given a person who says only "I want weekly meeting summaries for my team", when phase 2 runs, then the skill asks the three outcome questions, then shows two contrasting short summaries and asks which is better and why; the answer "the second one lists who owns each action" becomes the final criterion "every action item names one owner", classified `check` (a pattern over the action list) after the person confirms the format.

**AUT-B4 Backwards to steps.** Given the final criterion "every action item names one owner" and the deliverable "the summary file", when phase 3 asks what must be true before it, then the answers "the transcript is complete" and "decisions and actions are extracted" become two intermediate outcomes and two units before `summarize`, each criterion serving the final one.

**AUT-B5 Prefer what exists.** Given a criterion "the code passes the project's type check" and an inventory with `mypy` configured, when phase 4 runs, then the criterion is `check` with `existing:type_check` and the declared command prefix `mypy`; the skill does not propose a judge for it.

**AUT-B6 Flag, never hide.** Given a final blocker "customers understand the change", when no source, primitive, reference or role can verify it, then the skill puts the four choices to the person; "accept as none" records `none` with reason and risk, writes a decision record, and the blueprint's verification table shows the row in its unverified section.

**AUT-B7 Resume a session.** Given an authoring session stopped after phase 4, when a new conversation calls `author show <id>`, then the skill continues at phase 5 with the approved drafts, and phases 1 to 4 are not asked again.


## 4. Error conditions

| Condition | Result |
|---|---|
| `intake` on a path outside the workspace not named by the person | Refused, exit 2 |
| A source file over 5 MB or binary | Recorded with `kind: other`, no candidates |
| `author check` on drafts with an OUT §4 error or a blueprint error | Findings listed; the skill does not move to phase 7 |
| A phase approved and later edited | Its approval is cleared and every later phase's too; the skill re-shows them |
| `scaffold` asked for before phase 7 is approved | Refused: `blueprint_not_approved` |
| Two sessions for one workflow name | The second is refused until the first is dropped or finished |

## 5. Design notes

- **Backwards, as backward design does** ([R-105 B1](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md)): the evidence is fixed before the activities, so a step exists because an intermediate outcome needs it, not the other way round.
- **The skill drafts, the engine decides what is well-formed.** Every check of a draft is a model-free verb, so a different authoring host (another agent, a person by hand) gets the same refusals.
- **Graded drafts for the chat path.** When a person cannot list criteria, comparing two outputs is easier than naming rules, and the criteria found that way are what they will grade by later (R-105 B2, B3).
- **Release 1** ships `new` and `revise` modes for workflows of model steps, scripts, routes and switches; the skill offers later unit kinds only by name, marked "later" (ADR-0090 (PR 14)).

## 6. Acceptance criteria

- [ ] AUT-AC-1 A rubric scenario per entry path (AUT-B1 to B3) reaches an approved blueprint with every criterion classified and every `none` explained.
- [ ] AUT-AC-2 The inventory detects each row of §2.3 on a fixture repository and records no source text in `authoring.json` (scan test).
- [ ] AUT-AC-3 In every scenario, a criterion an inventory candidate decides is classified `check` with `existing:<kind>`, unless a recorded decision says otherwise.
- [ ] AUT-AC-4 Nothing under the package folder exists before phase 7's approval (scenario test with a file watch).
- [ ] AUT-AC-5 A session interrupted after any phase resumes at the next phase from `author show` alone.
- [ ] AUT-AC-6 Revise mode never writes a weakening without the person's yes on a table that marks it.

## Open questions

| Question | Owner |
|---|---|
| Should authoring also run in a non-Claude host (an Antigravity skill)? The verbs are host-neutral; only the skill is Claude Code's. Deferred with SHL's open question on an Antigravity-native shell. | Owner |
| Should the inventory read CI results (which checks are green today) to prefer verifications that already run? Assumed no in release 1: configuration only. | Owner |

## References

