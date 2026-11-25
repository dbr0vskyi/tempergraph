# Workflow authoring

## Purpose

Authoring turns what a person has, an existing solution, references and sources, or only an idea in a conversation, into a workflow package they can trust ([PKG](workflow-package.spec.md)). Its focus is the good outcome: what a good run leaves, and how each part of that, final and intermediate, is verified ([OUT](run-outcome.spec.md)). The interview works backwards from the final outcome to an intermediate outcome per step, then finds a verification for every criterion, preferring one the person already has, creating one where none exists, classifying each by who verifies it (script check, judge, person), and flagging, never hiding, a criterion with no trustworthy verification ([ADR-0109](../adr/0109-author-backwards-from-the-outcome-preferring-existing-verifications.adr.md)). The work splits between the authoring skill (`tempergraph:author`, a model in the person's own Claude Code session that leads the interview) and model-free engine verbs that inventory sources, check drafts, draw the blueprint, scaffold the package and check the result; the skill drafts, the engine checks and writes ([SHL](plugin-shell.spec.md)), and nothing is written to the package before the person approves the engine-drawn blueprint with the outcome and verification tables. How the result is checked is [SCF](blueprint-and-scaffold.spec.md). This spec owns the entry paths, the intake inventory, the interview and its phases, the verification search and classification, the authoring record and the revise mode; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### AUT-B1 From a solution

WHEN a session starts from a solution and intake runs THE engine SHALL record the solution's tests and structure as verification candidates, and the skill SHALL play back its stages, propose criteria its tests decide as `check` with `existing:<kind>`, and flag a self-check of the solution as a claim, never a verification.

- GIVEN a shell script and a prompt file that write release notes and the script's test that greps for "## Fixes" WHEN `author start release-notes --from solution scripts/notes.sh prompts/notes.md tests/test_notes.sh` and intake run THEN the inventory records a test command and a heading candidate, `rn-sections` is proposed as `check` (`existing:test`), and the prompt's "check that you covered everything" is flagged as a self-check

### AUT-B2 From sources

WHEN intake reads a template and a finished example saved from a connector THE engine SHALL make the template's headings one `existing:template` candidate and the example an `example_good` fixture, writing no URL or page text to `authoring.json`.

- GIVEN a release-page wiki template and one finished page WHEN intake runs THEN `authoring.json` holds one template candidate, one good fixture and no page text

### AUT-B3 From a chat

WHEN a session starts from words only THE skill SHALL ask the three outcome questions, then show two contrasting short outputs and ask which is better and why, the person's reason becoming a criterion classified after the person confirms its form.

- GIVEN "I want weekly meeting summaries for my team" WHEN phase 2 runs THEN the answer "the second one lists who owns each action" becomes "every action item names one owner", classified `check`

### AUT-B4 Backwards to steps

WHEN phase 3 asks what must be true before a deliverable THE skill SHALL make each answer that is a checkable result of its own a step boundary with an intermediate outcome whose criteria serve the final criterion.

- GIVEN the final criterion "every action item names one owner" WHEN phase 3 runs THEN "the transcript is complete" and "decisions and actions are extracted" become two units before `summarize`, each serving the final criterion

### AUT-B5 Prefer what exists

WHEN an inventory candidate decides a criterion THE skill SHALL classify it `check` with `existing:<kind>` and propose no judge for it.

- GIVEN "the code passes the project's type check" and `mypy` configured WHEN phase 4 runs THEN the criterion is `check` with `existing:type_check` and command prefix `mypy`

### AUT-B6 Flag, never hide

WHEN no source, primitive, reference or role can verify a blocker THE skill SHALL put the four choices to the person, and "accept as none" SHALL record `none` with reason and risk, write a decision record, and show the row in the blueprint's unverified section.

- GIVEN the final blocker "customers understand the change" WHEN the person accepts it as none THEN the record holds `none` with reason and risk and the docs gain a decision record

### AUT-B7 Resume a session

WHEN a new conversation calls `author show <id>` on a stopped session THE skill SHALL continue at the next unapproved phase with the approved drafts, asking no approved phase again.

- GIVEN a session stopped after phase 4 WHEN `author show` runs in a new conversation THEN the skill continues at phase 5

### AUT-B8 A program as the solution

WHEN a delivery process with gates, rule sets and reviewers is authored from its own blueprint as the solution THE skill SHALL make its mechanical review rules `check` criteria with `existing:review_rule`, its reading judgements `judge` criteria, and a judgement only a reviewer outside the run can make `none` with the reason naming where it is reviewed, nothing in the engine naming the workflow ([ADR-0129](../adr/0129-the-engine-names-no-workflow.adr.md)).

- GIVEN a blueprint whose final outcome is reviewed in a pull request WHEN it is authored THEN "the change is the right one for the product" is `none` with reason "reviewed in the pull request"

### AUT-B9 A vague outcome

WHEN `author check` finds a vague word with no measure in the statement THE engine SHALL report `criterion-vague` for each, and the skill SHALL offer observable rewrites and not end phase 2 until one is chosen.

- GIVEN "good, complete release notes" WHEN `author check` runs THEN it reports `criterion-vague` twice and the skill offers "every merged change since the last tag is listed or excluded with a reason" and "every entry links its change"

### AUT-B10 A contrast pair settles a judged criterion

WHEN a judged criterion stays vague after two clarifying rounds THE skill SHALL show two outputs that differ only in the property in doubt, the person's choice and reason becoming the criterion text and its `met` anchor and the pair its two seeds.

- GIVEN "entries are understandable to customers" WHEN rung 3 runs THEN the reason "say what changes for the user" becomes the criterion and its anchor

### AUT-B11 Authoring verbs

WHEN an `author` verb runs THE engine CLI SHALL offer, model-free and spending nothing: `author start <name> --from solution|sources|chat [<path>…]` (repeatable `--from` for a mixed session) and `author start <workflow> --revise`, opening `<state root>/authoring/<id>/` with `authoring.json`, the draft `outcome.json` and `blueprint.json`; `author intake <id> <path>… [--kind <kind>] [--artifact <key>] [--unit <unit>] [--outside]`, adding sources and running the inventory; `author check <id>`, checking the drafts (OUT's outcome errors, the blueprint rules of [SCF](blueprint-and-scaffold.spec.md), coverage, trust and the criteria lint), read-only; `author show <id> [--json]`, read-only, printing phase, sources, outcome and verification tables, open decisions, assumptions and cleared approvals; `author list`; `author drop <id>`, removing only that session folder; and `author approve <id> <phase>`, writing only `authoring.json`; `blueprint`, `scaffold`, `author verify` and `literals` being SCF's, `author verify --judge-seeds` and `--trial` the only ones that spend.

- GIVEN a session WHEN `author check` and `author show` run THEN the session folder is unchanged

### AUT-B12 Skill modes and sessions

WHEN the authoring skill runs THE skill SHALL call these verbs, read their JSON and keep its state in the session folder so an interrupted session resumes in a new conversation; work in mode `new` (from `author start` to a registered, verified, stamped package in `dev`), `revise` (from `outcome candidates <workflow>`, [OUT](run-outcome.spec.md), to a new re-checked `outcome.json` revision) or `upgrade` (handing over to the upgrade skill, [LSK](lifecycle-skills.spec.md)); read connector content (a wiki page, a ticket) with the person's connectors and save it into the session folder as a source file first, so the inventory reads files only; and THE engine SHALL name a session `<name>-<yyyymmdd>-<4 hex>`, refuse a second open session for one name on a state root (revise included) until the first is dropped or scaffolded, and mark a session `scaffolded` at `scaffold`, which frees the name.

- GIVEN an open session for `release-notes` WHEN `author start release-notes --from chat` runs THEN it is refused

### AUT-B13 Entry paths

WHEN the first drafts are found THE skill SHALL draft them per entry path: for `solution` (a script, prompt chain, runbook, skill or agent, another tool's workflow, past outputs), read its stages, tests, assertions and outputs, drafting steps from its stages, deliverables from its outputs and criteria from its tests, assertions and reviewers' comments; for `sources` (templates, good and bad examples, standards, checklists, a Definition of Done or Ready, style guides, acceptance criteria, review rules, docs pages, tickets), draft the statement and deliverables from the template and examples, criteria from checklists and rules and must-fail fixtures from known-bad examples, showing conflicting requirements side by side for the person to rank; for `chat`, draft from the answers to the outcome questions and then a graded draft, saying the first list is expected to change ([R-105](../research/R-105-workflow-packages-authoring-and-good-outcomes.rsrch.md) B2); let a path be mixed, every addition going through `author intake`; and run the same interview from phase 2 on.

- GIVEN two sources that require different heading orders WHEN phase 2 drafts THEN both are shown side by side for the person to rank

### AUT-B14 Intake inventory

WHEN `author intake` reads a source THE engine SHALL record, with no model, its `id`, `kind` (`solution`, `reference` and the other entry kinds, `example_good`, `example_bad`, `other`), `locator` (a workspace path, or `saved:<file>` for connector content, never a URL with a token), `digest`, size, `private` (true by default for connector content), candidate ids and the optional `artifact` and `unit` an example fixture is for; and detect the candidates `existing:test` (a command prefix from `pyproject.toml`, `package.json` scripts, `Makefile`, `justfile`, CI files, a README's commands), `existing:linter` and `existing:type_check` (their config files and pre-commit config), `existing:schema` (JSON Schema, OpenAPI, frontmatter rules), `existing:checklist` one per item (task lists, numbered "must" lists, a PR template), `existing:acceptance_criteria` and `existing:definition_of_done` (headings of those names, `Given/When/Then`), `existing:review_rule` (`CODEOWNERS`, review guides), `existing:template` (a template's heading structure) and must-pass or must-fail fixtures from examples; recording names, paths, counts and digests, never source text, in `authoring.json`, the text staying in the local session folder ([SEC](security.spec.md), OVR-B11).

- GIVEN a fixture repository with each candidate kind WHEN intake runs THEN each is detected and `authoring.json` holds no source text

### AUT-B15 Intake limits

WHEN intake is given paths THE engine SHALL accept paths inside the workspace (the repository root of the state root) and refuse others with exit 2 unless `--outside` is passed, which the skill passes only for a path the person named; copy sources into the session's `sources/`; walk a directory up to 500 files; record a source over 5 MB, or with a NUL byte in its first 8 KB, as `kind: other` with no candidates; and default `kind` to `solution` on a solution session, else `reference`.

- GIVEN a 6 MB source WHEN intake runs THEN it is `kind: other` with no candidates

### AUT-B16 Interview rules

WHEN the skill runs a phase THE skill SHALL draft, then ask; ask at most three questions per turn and one phase per turn; end each phase by showing its part of the drafts and getting a yes; use the person's words for outcomes, steps and criteria; record what the person does not know as an assumption; never invent a rubric the person did not confirm; and write only the session folder in phases 1 to 7.

- GIVEN phase 3 WHEN the skill asks THEN it asks at most three questions in the turn

### AUT-B17 The phases

WHEN the interview runs THE skill SHALL take in order 1 intake (sources and candidates, the process played back in at most six bullets, a fit check against the skill's good-candidate table); 2 final outcome (`statement`, `deliverables`, `final` criteria from three questions: what would make you reject the result, what has gone wrong before, what does a reviewer check first, each answer an observable statement, a vague word rewritten or dropped with a note); 3 work backwards (intermediate outcomes, the unit chain and `serves` as AUT-B4, stopping at the run's input, a final criterion nothing serves and the outcome gate cannot verify shown as uncovered); 4 find verifications (AUT-B18, with each criterion's trust); 5 steps' work (per unit kind, prompt outline, tools, executor, model, policies, executor consequences from `executors`, [SHL-B3](plugin-shell.spec.md), every option not asked taking its documented default and shown); 6 start and routing (`input`, examples from intake where possible, `routing`); 7 approval (one yes on the blueprint, outcome table and verification table together after `blueprint draw`, a change redrawing); 8 scaffold; 9 verify, register, trial and stamp with `author verify`, calibration cases seeded from the trial; `scaffold` before phase 7 is approved being refused `blueprint_not_approved`, and unit kinds not yet built offered only by name, marked "later" ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)).

- GIVEN a session approved through phase 6 WHEN `scaffold` runs THEN it is refused `blueprint_not_approved` and nothing exists under the package folder

### AUT-B18 Verification search order

WHEN phase 4 classifies a criterion THE skill SHALL try in turn 1 an inventory candidate that decides it (`check`, source `existing:<kind>`); 2 a deterministic primitive (a file, heading, pattern or value, a git fact, a command fixed in the workflow; `check`, `created`); 3 a split into a `check` and a `judge` criterion serving the same final criterion; 4 reading against named references the judge can open (`judge` with `check_method` and references, `existing:<kind>` when the method comes from a review rule or checklist, else `created`); 5 authority only a person has (`person` with `role` and `question`, `interview`); 6 nothing trustworthy (`none` with `reason` and `risk`, offering the cheapest way to make it verifiable later); prefer an earlier row and say why it takes a later one; and put a blocker it cannot place above row 6 to the person as a decision: a `person` sign-off, `none` with a decision record in the workflow's docs ([PKG-B21](workflow-package.spec.md)), a warning, or dropping it.

- GIVEN a criterion a heading check decides and no candidate WHEN phase 4 runs THEN it is `check` with source `created`

### AUT-B19 Criteria lint

WHEN `author check`, validation or the readiness report lints criteria ([ADR-0114](../adr/0114-judged-criteria-carry-a-scale-and-authoring-guides-to-clarity.adr.md)) THE engine SHALL report, model-free, `criterion-vague` (a word from the vague list such as complete, good, clear, appropriate, high quality, user-friendly, robust, as needed, with no measure in the sentence, a measure being a number, `every`, `each`, `all`, `no`, `none`, `at least`, `at most`, a backticked name or a path); `criterion-compound` (more than one claim joined by "and", "or", a list or a semicolon); `criterion-unobservable` (no deliverable key, reference, file or field to look at); `criterion-self-graded` (it asks the producer to report on itself); `criterion-unanchored` (a judged criterion without a complete scale, [OUT](run-outcome.spec.md)); `criterion-overlap` (two criteria of one unit whose content-word sets share at least 60% of the smaller set, or a final criterion restated as an intermediate one with no narrowing); and `criterion-no-seed` (a judged criterion with no `met` seed and no `unmet` or `partial` seed); as errors in `author check` except `criterion-overlap` (warning) and `criterion-no-seed` (a warning there and an error of SCF's seed rung), and all as warnings in validation and the readiness report; the skill giving each code's guidance (the question "what would you look at to tell it is {word}?" with two rewrites, a split proposal, "where would a reviewer see this?", a rewrite as a fact the gate checks, a drafted scale from the examples, a merge or narrowing, a request for seeds or a contrast pair).

- GIVEN "the notes are clear and complete" WHEN `author check` runs THEN it reports `criterion-vague` and `criterion-compound`

### AUT-B20 Sufficiency of the outcome

WHEN phase 2 would end THE engine SHALL require the statement to have no `criterion-vague` or `criterion-unobservable` finding, at least one deliverable, at least one blocker final criterion and every final criterion passing the lint, phase 2 not being approvable until it holds.

- GIVEN an outcome with no blocker final criterion WHEN `author approve <id> 2` runs THEN it is refused

### AUT-B21 Guidance ladder

WHEN a criterion fails the lint or the outcome fails the sufficiency check THE skill SHALL take in order, at most three questions per turn, rung 1 clarifying questions (the lint code's question and the three outcome questions); rung 2 examples of criteria from the engine's library `skills/author/references/criteria-examples/<task kind>.md` (document, code change, analysis, ticket, data, message), each with its verifier class and scale; rung 3 a contrast pair (AUT-B10); rung 4 grade a full draft, each mark becoming a criterion candidate; and rung 5 decide after two rounds with no observable form (`person` sign-off with the person's own question, `none` with a reason, or drop, recorded as a decision); and say a workflow whose final outcome still has no observable blocker after rung 5 is not a fit yet, keep the session, and offer to resume when the person has an example.

- GIVEN a criterion still vague after rung 4 WHEN rung 5 runs THEN a decision is recorded for it

### AUT-B22 Decisions and assumptions

WHEN the person chooses against the skill's draft, drops a criterion as not observable, accepts a `none`, makes an executor choice with a stated consequence or moves a step boundary THE engine SHALL record a decision in `authoring.json` and, at scaffold, a decision record in the workflow's `docs/adr/` ([ADR-0113](../adr/0113-the-workflow-docs-set-is-provisional-until-temperspec-owns-it.adr.md)), and put each assumption the person did not settle in `outcome.json` `assumptions` and the overview spec's open questions.

- GIVEN a criterion dropped as not observable WHEN the package is scaffolded THEN its `docs/adr/` holds a record of it

### AUT-B23 The authoring record

WHEN `authoring.json` is written THE engine SHALL hold `schema_version`, `id`, `name`, `path` (`solution`, `sources`, `chat` or a list for a mixed session), `mode`; `sources[]` (metadata only); `candidates[]` with their source id and whether a criterion used them; `phases[]` (per phase approved at, by as a `Caller`, the digest approved); `decisions[]` (id, phase, subject, choice, alternatives, consequence, decided by); `blueprint_digest` and `outcome_revision`; and `verify`, the last `author verify` report id and result; copy it into the package at scaffold, outside the content digest ([PKG-AC7](workflow-package.spec.md)).

- GIVEN a scaffolded package WHEN its content digest is computed after editing `authoring.json` THEN it is unchanged

### AUT-B24 Approvals

WHEN `author approve <id> <phase>` runs THE engine SHALL record `{phase, approved_at, by, digest}`, `by` the caller ([PRV-B13](caller-provenance.spec.md)) and `digest` the SHA-256 of that phase's part (1 the sources list; 2 the statement, deliverables and final criteria without verifier fields; 3 the intermediate outcomes likewise; 4 every criterion's `verified_by`, `verifier` and `source`; 5 the blueprint without `input`; 6 `input` and the record's `routing`; 7 both drafts, setting `blueprint_digest` and `outcome_revision`); approve a phase only when every earlier phase is approved and its drafts pass `author check`, phase 2 also needing the sufficiency check and phase 4 a class for every criterion; and count an approval whose digest no longer matches as cleared with every later one, `author show` listing them under `cleared` and `approve` dropping them.

- GIVEN phase 3 approved WHEN its intermediate outcomes are edited THEN `author show` lists phases 3 to 7 as cleared

### AUT-B25 Revise mode

WHEN a workflow's outcome is revised THE engine SHALL open with `author start <workflow> --revise` a `mode: revise` session holding copies of the package's `outcome.json`, `blueprint.json` and `authoring.json` with approvals, so only phases whose part moved are asked again; require a higher `revision` for a changed outcome (`revision-not-bumped`); list in `author check` each criterion's change class against the package, a removal, a blocker made a warning or a verifier of lower trust being `weakening`, an addition or the reverse `strengthening`, a text or scale change `neutral`; and write the revision with an `OutcomeRevision` of `origin: revise_session` through `scaffold <session> --out <package> --update-docs`, then `author verify` without trial; and THE skill SHALL read only the evidence the person opens from `outcome candidates`, draft per picked candidate a criterion, its class and its change class, show the tables before and after with weakening rows marked for one yes, and leave a prompt or step change the revision suggests to a separate later change, grader first ([ADR-0031](../adr/0031-steps-and-their-graders-change-apart.adr.md)).

- GIVEN a revise session that turns a blocker into a warning WHEN `author check` runs THEN the row is `weakening` and phase 7 needs a yes on the marked table

## Acceptance criteria

- AUT-AC1 (AUT-B1, AUT-B2, AUT-B3, AUT-B4, AUT-B6, AUT-B8, AUT-B13, AUT-B16, AUT-B17, AUT-B18): A rubric scenario per entry path reaches an approved blueprint with every criterion classified and every `none` explained
- AUT-AC2 (AUT-B14, AUT-B15): The inventory detects each candidate kind on a fixture repository and records no source text in `authoring.json` (scan test)
- AUT-AC3 (AUT-B5, AUT-B18): In every scenario, a criterion an inventory candidate decides is classified `check` with `existing:<kind>`, unless a recorded decision says otherwise
- AUT-AC4 (AUT-B11, AUT-B17, AUT-B22, AUT-B23): Nothing under the package folder exists before phase 7's approval (scenario test with a file watch)
- AUT-AC5 (AUT-B7, AUT-B12, AUT-B24): A session interrupted after any phase resumes at the next phase from `author show` alone
- AUT-AC6 (AUT-B25): Revise mode never writes a weakening without the person's yes on a table that marks it
- AUT-AC7 (AUT-B9, AUT-B19, AUT-B20): Every lint code has a must-fire and a must-not-fire fixture; phase 2 cannot be approved while the sufficiency check fails
- AUT-AC8 (AUT-B10, AUT-B21): A rubric scenario per guidance rung reaches an observable criterion or a recorded decision

## Open questions

- Should authoring also run in a non-Claude host (an Antigravity skill)? Until answered: the verbs are host-neutral and only the skill is Claude Code's, deferred with SHL's open question on an Antigravity-native shell. Owner: owner.
- Should the inventory read CI results (which checks are green today) to prefer verifications that already run? Until answered: configuration only. Owner: owner.
- Not built yet: the rubric scenarios (AUT-AC1, AUT-AC8) run the skill with a model and are live checks on the owner's machine. Owner: engine owner.
