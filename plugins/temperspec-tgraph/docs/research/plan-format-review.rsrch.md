# What temperspec's plan takes from other tools' plan formats

| | |
|---|---|
| Date | 2026-11-21 |
| Asked by | The owner: is it intentional that temperspec has no plan template, and which plan parts common in spec-driven tools would make temperspec plans better. Then: compare with the plan formats of the tools of the [earlier comparison](sdd-tools-comparison.rsrch.md) |
| Method | Common plan parts read against temperspec's [plan rule](../../rules/plan.rule.md), `workflow/temperspec/specfmt.py` (`parse_plan`, `row_problems`, `proof_problems`, `simple_overruns`), `checks.py` (`plan_check`, `expand_check`, `code_check`), the plan, expand and code prompts, and the engine on `main` (release 2, engine 0.2.0). Then the plan and task documents of the nine tools of the earlier comparison, read from their repositories (§5) |
| Status | Built on the owner's choice of 2026-11-21: the templates of §6 point 3 (generated at install into `docs/templates/`, tested against the rules), A1 to A5, and, at the owner's ruling, the plan's status and each row's completion mark and date (row 4), checked first at the code gate. Per-phase items wait for backlog B7 |

## 1. Summary

The difference is mostly deliberate, but not all of it was decided. The large differences follow recorded rules: no status, version, date or change note in a document; one home per artifact (decisions in decision records, the hand-off in its note); no release step. temperspec also has parts the other formats lack: a proof table per criterion, spec ids on each requirement, and a measured complexity. The rest of the gap (§3) was never decided. Four of those parts are cheap; reading sets and verification kinds only pay off once coding runs per phase and commands come from the repository.

**Recommended to add now** (rule, prompt and check changes inside the package; no engine work):

| # | Add | Why | Seen in | Cost here |
|---|---|---|---|---|
| A1 | A `Req` column on every task row; the check fails a requirement with no row and a row with no requirement | A link the expand judge checks on every attempt becomes a model-free check; the judge keeps only whether the row really implements the requirement | Spec Kit, GSD (a blocker there), GSD 2 and Superpowers (§5) | One column, one check function, the rule example, two check fixtures |
| A2 | Every document under `## 4. Docs to update` is the file of a `docs` row (after expand for a complex plan) | A listed document with no row is either skipped or edited as a deviation | — | One check, one fixture |
| A3 | Write the plan as a skeleton, then one edit per phase, each write under about 12 KB | One large write can run past the API's response time limit, and Claude Code then retries silently | — | Two sentences in the plan and expand prompts and one in the rule; no check |
| A4 | For each type or signature a row changes, the plan searches the tests for pins of it and gives each hit a row, or says none | A new field or signature can break a test that pins it while the plan calls that test untouched | — | One sentence in the rule and the expand prompt |
| A5 (optional) | The plan check returns `maybe` when the plan says "stub", "for now", "v1", "placeholder" or similar, so the judge looks at whether scope was cut | A plan can shrink the scope quietly; unmeasured in any tool | GSD's scope-reduction check (always a blocker there) | A word list and about ten lines in the plan check |

**Recommended with per-phase coding** (backlog B7, which the engine's sequential map now allows): per phase a short `Read:` list and a `Produces:` list (files and interfaces later phases rely on), existence-checked only, the command that proves the phase, and a warning cap on rows and files per phase. Not reading sets per row: they are costly to write and to check (§4 F5). The other tools point the same way: GSD, GSD 2 and Superpowers name what to read and what a task produces, GSD and GSD 2 cap the unit of work, and none of them lints reading sets (§5).

**Templates:** do not ship separate template files. Each rule file already holds a filled example under `## Structure`, and the tests parse the spec, plan and task-note examples. Extend that test to the decision and research examples. If fill-in files are wanted for people writing by hand, generate them from those examples at install time, so there is no second copy to drift (§6).

## 2. Sources consulted

| Source | Type | Where |
|---|---|---|
| Spec Kit plan and tasks templates, plan, tasks and analyze commands | web | `github.com/github/spec-kit`, `templates/plan-template.md`, `templates/tasks-template.md`, `templates/commands/` |
| GSD phase plan template, planner and plan checker; GSD Core plan reference | web | `github.com/gsd-build/get-shit-done` (archived), `github.com/open-gsd/gsd-core` `docs/reference/plan-md.md`, `planning-artifacts.md` |
| GSD 2 roadmap, slice plan and task plan templates, auto mode | web | `github.com/gsd-build/gsd-2` (archived; continued as `open-gsd/gsd-pi`), `src/resources/extensions/gsd/templates/` |
| OpenSpec spec-driven schema | web | `github.com/Fission-AI/OpenSpec`, `schemas/spec-driven/schema.yaml` |
| BMAD v7 build plan template and dev agent | web | `github.com/bmad-code-org/BMAD-METHOD`, `skills/method/bmad-build/plan-template.md` |
| Superpowers writing-plans, executing-plans, subagent-driven-development | web | `github.com/obra/superpowers`, `skills/` |
| Agent OS shape-spec command | web | `github.com/buildermethods/agent-os`, `commands/agent-os/shape-spec.md` |
| Kiro, Tessl | not reached | `kiro.dev`, `docs.tessl.io` did not resolve; only the earlier comparison's facts are used |
| temperspec plan rule and documents rule | rule | `rules/plan.rule.md`, `rules/documents.rule.md` |
| Plan format the checks read | code | `workflow/temperspec/specfmt.py` (`PLAN_HEADINGS`, `parse_plan`, `row_problems`, `proof_problems`, `SIMPLE_MAX`) |
| Plan, expand, code gates | code | `workflow/temperspec/checks.py` (`plan_check`, `expand_check`, `code_check`, `outcome_check`) |
| Plan, expand, code prompts and judge briefs | prompt | `prompts/plan.md`, `prompts/expand.md`, `prompts/code.md`, `judges/plan.md`, `judges/expand.md` |
| Rule examples held to the parser | test | `tests/test_temperspec.py` (`test_the_plan_rule_example_and_limits_match_the_parser` and its neighbours) |
| Owner's rulings on format and cascades | research | engine R-125, R-127; package [next features](next-features.rsrch.md) |
| Engine rulings reach later judges | spec | engine spec `reruns-and-feedback` RRN-B1, spec `judge-and-verdict` "Feedback" |
| Engine release 2: sequential map, self-check, `@repository` commands | spec, code | engine spec `check-contract-and-command-runs` "As built (R2-T7)", `model/validate.py` (map mode `sequential`) |

## 3. Side by side

Origin: **decided** means a recorded rule or ruling explains the difference; **undecided** means no record does.

| # | Plan part | temperspec plan | Origin | Worth adding? |
|---|---|---|---|---|
| 1 | File named by purpose, component and version | `docs/plans/<task id>.plan.md` | Decided: collision-free names, no version (documents rule; R-127 C1, C8) | No |
| 2 | Front matter: goal, version, dates, owner, status, tags, tracker link | `task`, `complexity`, `specs`; the goal is the title | Decided for version, dates, status (documents rule 1); tracker left out by the owner; owner and tags undecided | No: git holds who and when |
| 3 | Front matter: the short commit each spec was read at | None | Undecided | No: the run's base commit already fixes it inside a run; across runs, backlog B2 (spec changed on the base) is the better guard |
| 4 | Status values (planned to deprecated), a completed mark and date per row | Built: `status` (`planned`, `in-progress`, `completed`) and a `Completed` cell `✓ <date>` per row, set by the code step | First decided against (no status in a document); the owner then ruled that a plan is not a spec and causes no cascade, so it carries both | Yes, built: the code gate checks the marks first and returns at once without running anything, then verifies a marked plan as if it had no marks |
| 5 | A leading section with five parts (origin, research, decision record, spec at a commit, tracker) and four subsections (problem, decisions made, implementation guidance, context) | `## 0. Hand-off`: triage note, specs read, why this design. Problem, decisions and open questions live in the discovery hand-off note | Decided: one home per artifact (the hand-off and decision records own them) | No. "Why this design" already carries the one judged criterion |
| 6 | Requirements with type prefixes (requirement, architecture, API, state, type, doc) | `R<n>` with `Criteria` and `Spec ids` columns | Prefixes undecided; API and type items point at a contracts spec, which temperspec does not have (R-127 C5, no Interface section) | No. The `Spec ids` column is stronger than the prefixes |
| 7 | Every acceptance criterion maps to a requirement | Same, checked (`ts-plan-trace`) | Built | — |
| 8 | Every requirement maps to a phase | Stated in the rule; nothing links a row to a requirement, so nothing checks it | Undecided | **Yes, A1** |
| 9 | Track map (track, spec, phases, depends on) with a Kind column and a release track | None | Release track decided (owner left the release step out); the map undecided, tied to per-phase coding | No. Phases are enough until coding runs per phase; even then a track adds only a grouping |
| 10 | Phase: heading, goal, table header, one anchor line | Heading, `Goal:`, `Weight:` | Weight decided (owner's complexity ruling); anchor lines go with the two-pass rule | See row 11 |
| 11 | Two-pass writing: skeleton in one write under ~14 KB, then one edit per part, each response under ~12 thousand tokens | One write | Undecided | **Yes, A3**, as prompt text only |
| 12 | Architecture decisions in full inside the plan | None | Decided: decisions belong in decision records | No |
| 13 | Task columns: Task, File, Code change, Reading set, TDD, Priority, Completed, Date | Row, Kind, File, Proves, Change | TDD replaced by `Kind` plus the order rule and `Proves` (stronger); Completed and Date decided (row 4); Priority and Reading set undecided | Priority: no (rows run in order). Reading set: row 14 |
| 14 | Reading set per row: each called function with file and line range, files earlier rows create, no file over 30 KB whole, plan under 12 KB, set near 60 KB; a lint of it before the judge | None. The plan's named files count toward complexity (200 KB limit) | Undecided; the single code session reads freely | **Later, per phase** (§4 F5) |
| 15 | Pin search: grep the tests for pins of each changed type's field order and signature, record the hits | None | Undecided | **Yes, A4** |
| 16 | A section of dependencies and imports | None | Undecided | No: a new dependency is a `chore` row |
| 17 | A file table (create, modify, delete) | None; the `File` column of the rows | Undecided | No: derived from rows, it cannot disagree with them |
| 18 | Verification items of kinds build, type, test, lint, coverage, end-to-end (or a reason to skip), release; the check requires the kinds | `## 3. Verification`: plain commands from a fixed list (`VERIFY`), plus the **proof table** | Kinds undecided; the fixed list came from a release 1 limit (no per-repo commands) | Not now. Revisit with backlog B10, now possible through the engine's `@repository` commands (§4 F6) |
| 19 | Whole suite as a merge-step item; merge-only items with a reason | None; `git push` and `gh` are forbidden in verification | Undecided (no release step) | Optional (§4 F7) |
| 20 | A section of code assumptions | None | Undecided | Optional, folded into §4 F7 |
| 21 | Revision note; changed phases get a fresh anchor and their rows reset | None; a trip back rewrites the plan in place | Decided: no note about a change (documents rule 7). A person's direction travels as an engine ruling that every later attempt and judge sees (engine RRN-B1) | No |
| 22 | Never written against a draft or missing spec | The plan prompt stops and blames discovery | Built (temperspec specs have no status, so "missing or open question" is the test) | — |
| 23 | Docs rows for every doc the change makes false (judged) | `## 4. Docs to update` plus a `docs` row kind; nothing ties the two | Built in part | **Yes, A2** |
| 24 | Code mode chosen from the plan's size | `complexity` measured on seven signs and checked (`ts-plan-size`); proof table per criterion; spec ids per requirement | temperspec's own, from the owner's rulings and the GSD comparison | — (see §4 F8 on the row limit) |

## 4. Key findings

### F1 The large differences are decided, and the rule that decides them holds `confirmed`

Rows 1, 2, 4, 12 and 21 all fall under the documents rule ("A document carries no version, date, status, change log…"; "A line says what the system does now") and under one home per artifact. A status in a spec makes every change touch it, and a change note in a document is bookkeeping that cascades. A plan with status and completed marks needs sessions that mark rows in the plan as they go; temperspec's code step reports row status in the code report instead (`code_check` reads `parse_report`), so the plan never changes after expand. Nothing argues for undoing this for specs. **The owner's ruling (2026-11-21)** separates the plan: it belongs to one task and nothing links to it, so its status and its rows' marks cause no cascade. The plan now carries them; the code gate reads them first as a cheap gate, and then verifies the work as before, plus a new check that each marked row's file changed in the run (`ts-code-changed`).

### F2 The requirement-to-row link is the one structural hole `confirmed`

`plan.rule.md` says "Every requirement is served by at least one phase", but `parse_plan` reads no link between a row and a requirement, and `row_problems` checks only id, kind, file and test-first order. The expand judge (`judges/expand.md`) is told to "name the requirement it implements" for each row: a judgement every attempt repeats. A `Req` column makes both directions a model-free check; the judge keeps only whether the row really implements it.

**Cost.** Column in the rule example and fixtures; `Row.req` in `parse_plan`; about 20 lines in `row_problems` or a new function used by `plan_check` (simple) and `expand_check`; the alignment test picks it up from the example. Prompt growth: one cell per row.

### F3 Docs to update is a list nothing holds to account `confirmed`

The plan has `## 4. Docs to update` and a `docs` row kind, but a listed document can have no row and the code step is told to change "only the files the task rows name". So a listed doc is either skipped or edited as a deviation. A check that every listed path is the file of a `docs` row closes it.

**Cost.** `parse_plan` already reads paths with `listed_paths`; about 15 lines in the plan and expand checks, one must-fail fixture.

### F4 The two-pass writing rule protects against a stall temperspec can hit `inferred`

One response that runs past the API's response time limit stalls the step, and Claude Code then retries silently. temperspec's plan prompt says "Write the plan to …" in one step and the expand prompt "Save the plan at the same path": a complex plan with many phases is one large write. The fix is procedural and needs no check: write the sections with empty phase tables first, then one edit per phase, keeping each write under about 12 KB. Anchor lines in a two-pass format only serve a check that no part was left unwritten; temperspec's `ts-exp-rows` (every phase has a row) already covers that.

**Cost.** Two sentences in each prompt and one in the rule. Nothing to check, and no harm on a small plan.

### F5 Reading sets per row cost more than they save today `inferred`

For: a coder that knows exactly what to read spends less context finding it. Against: a set per row is long to write and to check, a lint of it can fail a whole expand attempt over one detail, and its rules grow the expand prompt. temperspec's single code session reads the plan's files itself, so per-row sets buy little today.

They start to pay when each phase gets a fresh session (backlog B7), because a fresh session must be told where to start. The cheap form is one `Read:` line per phase listing paths (and optionally line ranges), checked only for existence; sizes warn, never fail. That is the "certain findings fail, uncertain ones warn" half of a reading-set lint, without the call-graph part.

**Pin search** is the one reading-set rule worth taking now (A4): it is one sentence, and it guards against a test the plan never named breaking.

### F6 Engine release 2 has moved three related items `confirmed`

The engine on `main` now has the sequential map (`model/validate.py` accepts map mode `sequential`), a check preview inside an attempt (`tempergraph self-check`), and repository-declared commands (`tempergraph.commands.json`, `@repository`; engine spec `check-contract-and-command-runs` "As built (R2-T7)"). So:

- Backlog B7 (per-phase coding) and B10 (verification commands from the repository) no longer wait for the engine. This pull request moves them, with B6, B8 and B9 whose engine parts are also in release 2, to Ready.
- Expand could preview its own check inside one attempt. That lowers the cost of stricter expand checks such as A1 and A2: a failed check no longer costs a whole new attempt. Adopting it is a separate change to the expand step.
- Verification kinds (row 18) become meaningful only once commands come from the repository. With `@repository`, the check could warn when a repository documents a lint or type command and the plan lists none. That belongs to B10, not to this note.

### F7 Merge-only items and assumptions have no place `inferred`

A row asking for tracker or GitHub work, or a whole suite, costs a code attempt, a pause or a person when the code step cannot do it. temperspec forbids `git push` and `gh` in verification and has no release step, so such work has nowhere to go but a deviation. An optional `## 5. Left open` list (work only a person or the merge can do, and the plan's assumptions), copied into the draft pull request description by `summary.py`, would give it a place. It overlaps with backlog B1, which lists triage's default answers as assumptions in the pull request; if both are built they should share one pull request section. Value is moderate and unmeasured here, so it is offered as optional.

### F8 The `simple` row limit is a value to tune `inferred`

`SIMPLE_MAX` sets 12 rows and 3 phases, with no measurement of how much one code session handles well. Today the value matters less, since complex plans also code in one session; it matters once B7 makes `complex` mean per-phase coding. This is a tuning item for the backlog's "To tune once runs exist" list, not a format change.

## 5. Plan formats of the other tools

The nine tools of the [earlier comparison](sdd-tools-comparison.rsrch.md), read for their plan and task documents on 2026-11-21. Spec Kit, GSD, GSD 2, OpenSpec, Superpowers and Agent OS were read from their repositories (templates, agent and skill files). BMAD was read from its v7 preview branch only (the build plan template; its v6 story template was not reached). **Kiro and Tessl could not be read**: their documentation hosts do not resolve from this session, so their rows below come only from the earlier comparison and are marked. The quotes were read through a summarising fetcher and should be checked at the source before they are repeated.

### 5.1 The formats at a glance

| Tool | Plan documents | A task is written as | Task linked to requirements | Verification in the plan | Completion recorded | Size rule | Templates |
|---|---|---|---|---|---|---|---|
| **Spec Kit** | `plan.md` (summary, technical context, constitution check, project structure, complexity tracking) plus `research.md`, `data-model.md`, `contracts/`, `quickstart.md`; then `tasks.md` | `- [ ] T012 [P] [US1] Create User model in src/models/user.py`; phases Setup, Foundational, one per user story, Polish | By user-story label `[USn]`; `/analyze` reports coverage gaps read-only | A checkpoint per story ("fully functional and testable independently"); tests optional, "MUST be written and FAIL before implementation" when asked for | Checkbox in `tasks.md` | None on files; analyze caps findings at 50 | Template files, filled by setup scripts |
| **Kiro** (not read) | `requirements.md` (EARS), `design.md`, `tasks.md` (earlier comparison) | Not read | Not read | Property-based tests derived from requirements (earlier comparison) | Not read | Not read | Not read |
| **Tessl** (not read) | Spec-anchored; scripts check that linked tests and target files exist (earlier comparison) | Not read | Not read | Linked tests (earlier comparison) | Not read | Not read | Not read |
| **OpenSpec** | Per change: `proposal.md`, spec deltas, `design.md` (only when cross-cutting), `tasks.md` | `- [ ] 1.1 <task>` under `## 1. <group>`; the verification "goes in the same checkbox line" | None by id; by capability and spec path | In each task line; "Do NOT collect testing or documentation into a final group" | Checkbox; only `x` counts as done; the apply step marks it | Proposal "1-2 pages"; requirement text at most 500 characters | Template files in the schema folder, with the schema's instructions |
| **BMAD** (v7 build plan) | One plan: intent, boundaries (Always / Never), an I/O and edge-case matrix, a code map, tasks and acceptance, implementation notes, a plan change log, a review triage log, verification | `` `FILE` -- ACTION -- RATIONALE `` | Acceptance as Given/When/Then, no ids | `` `COMMAND` -- expected: SUCCESS_CRITERIA `` plus manual checks | Front matter `status`; a plan change log | None found | One plan template file |
| **GSD** | Per phase folder: context, research, validation, patterns, then `<NN>-<PP>-PLAN.md` and a `SUMMARY.md` after it | XML `<task>` with `name`, `files`, `read_first`, `action`, `verify` (with `<automated>`), `acceptance_criteria`, `done` | `requirements:` in each plan's front matter "MUST NOT be empty"; the checker blocks an id no plan covers; actions cite decision ids ("per D-03") | `must_haves`: observable truths, artifacts (path, exports, contains), key links between them; a verifier checks them after the run | A summary file per plan; `status: superseded` | 2-3 tasks per plan (5 or more blocks), 5-8 files (15 or more blocks), about 50% of context per plan | Template files |
| **GSD 2** | Milestone roadmap (success criteria, proof strategy, requirement coverage, boundary map), slice plan, task plan | `- [ ] **T01: Title** `est:30m`` with `Why:`, `Files:`, `Do:`, `Verify:`, `Done when:`; a task plan lists `Inputs` and `Expected Output` | A slice lists requirement and decision ids it touches; tasks do not | `Verify` "mechanically executable": no pipes, redirects, semicolons | Checkboxes; summary files per slice and task | A task of 10 or more steps or 12 or more files warns | Template files; the files are projections of a database |
| **Superpowers** | One plan file: goal, architecture, tech stack, spec path, global constraints copied verbatim, review focus, then tasks | `### Task N` with `Files:` (`Modify: path:123-145`), `Interfaces:` (consumes, produces), then steps: write the failing test, run it (`Expected: FAIL …`), implement, run (`Expected: PASS`), commit | The spec is "the binding authority"; a self-review adds a task for any spec requirement without one | Every command step has an expected result the executor compares | A separate ledger outside the plan (`Task N: complete (commits a..b, review clean)`) | None; "A plan longer than the code it describes has written the code instead" | Inline in the skill text |
| **Agent OS** | `plan.md` beside `shape.md` (scope, decisions, context, standards applied), `standards.md`, `references.md` | `## Task 2: <task>`, "specific and actionable" | None | None | None | "Keep it lightweight" | Inline in the command text |
| **temperspec** | One plan: hand-off, requirements, phases with task tables, verification with the proof table, docs to update | Table row: `Row`, `Kind`, `File`, `Proves`, `Change` | Requirement to criterion (checked); row to requirement **missing** (A1) | Plan-level commands, single plain commands; a proof row per criterion with its test file and command, checked at the code gate | Code report, outside the plan | Seven measured signs that decide `simple` or `complex`; no cap on a phase | Inline in the rule file, held to the parser by tests |

### 5.2 What the comparison adds

**F9 A link from each task to what it delivers is the common practice, and the strictest tool checks it `confirmed`.** Spec Kit labels tasks by story, GSD requires `requirements:` on every plan and blocks an uncovered id, GSD 2 lists the ids each slice touches, Superpowers makes the plan's self-review add a task for any uncovered requirement. Only OpenSpec, BMAD's build plan and Agent OS have no link. This supports A1; GSD's form (a list per plan, checked in both directions) is the same shape A1 proposes per row.

**F10 Most tools tell the coder what to read and what a task produces `confirmed`.** GSD has `read_first` and `@` context references per plan; Superpowers names files with line ranges and each task's `Interfaces: consumes / produces`; GSD 2's task plan lists `Inputs` and `Expected Output` as file paths and machine-parses them to order tasks; BMAD has a code map. None of them lints reading sets per row. This supports the §4 F5 conclusion: a per-phase `Read:` list, and adds a second line for per-phase coding (B7): `Produces:`, the files and interfaces later phases rely on. It names, in a cheap form, the files an earlier phase creates, and it is the same data GSD 2 uses to find tasks that can run side by side (B12).

**F11 Verification is per task in most tools; temperspec's proof table is per criterion, which none of them has `supported`.** GSD puts an automated command in every task's `verify`, GSD 2 and BMAD write the command with its expected result, Superpowers runs every test twice (fail, then pass) against a written expectation. temperspec fixes before coding which test proves each acceptance criterion and the gate checks the test exists, carries the id and is not skipped. That is stronger than any of them on what "done" means. What temperspec lacks is a command per phase, which only matters when phases run in their own sessions (B7): the phase gate needs to know which listed command proves that phase.

**F12 Caps on a unit of work are common; temperspec measures the whole plan only `confirmed`.** GSD caps a plan at 2-3 tasks and 5-8 files (blocking at 5 tasks or 15 files) and targets about half the context; GSD 2 warns at 10 steps or 12 files per task. temperspec's signs classify the whole plan; a single phase can be any size. With per-phase coding, a cap per phase (rows and files, warning only, values to tune) would keep each session small. GSD's limits are design values, not measurements.

**F13 Status in the plan is common, but the two most careful tools keep progress outside it `supported`.** Spec Kit, OpenSpec and GSD 2 tick checkboxes in the plan, and BMAD keeps a plan change log. Superpowers writes progress to a separate ledger and GSD writes a summary file per plan. temperspec's code report is the same choice, and it matches its rule against edits that only record history (§4 F1).

**F14 Guarding the scope against quiet shrinking is GSD's, and cheap `supported`.** GSD's checker always blocks a plan that says "v1", "static for now", "stub" or similar where the requirement asks for the real thing (its dimension 7b, "Scope Reduction Detection"). BMAD's `Never` list and Superpowers' verbatim global constraints aim at the same failure. In temperspec the plan judge (`ts-plan-spec`) and the code judge would have to notice. A word list in the plan check that returns `maybe` (so the judge looks) is about ten lines. Unmeasured anywhere, so it is offered as optional (A5).

**F15 Templates: five tools ship template files, two keep the format inline `confirmed`.** Spec Kit, OpenSpec, GSD, GSD 2 and BMAD ship template files; Superpowers and Agent OS keep the format in the skill or command text, as temperspec keeps it in the rule. OpenSpec's form is the closest to what §6 recommends: one schema file holds the instructions and the order of artifacts, next to its templates. None of the tools reports drift between templates and checkers; only temperspec tests the example against the parser.

**What not to take.** Spec Kit's separate research, data-model, contracts and quickstart files and GSD's per-phase context, research, validation and patterns files are the "markdown volume" the earlier comparison found criticised most (Spec Kit: 2,577 lines of markdown for 689 lines of code in one report). GSD's XML tasks and GSD 2's database projections do not fit a plan a person reads in a pull request. Code inside the plan (Superpowers' test code) is the "plan longer than the code" Superpowers itself warns about.

## 6. Templates

**What other tools do.** Five of the nine ship template files (F15). A format restated in several places drifts until the copies disagree, which is why each temperspec format has one rule file.

**What temperspec does.** Each rule file's `## Structure` holds one filled example of the document (plan, spec, decision record, research note, task notes). The tests parse the spec, plan and task-note examples with the same functions the gates use (`test_the_spec_rule_example_passes_the_spec_parser`, `test_the_plan_rule_example_and_limits_match_the_parser`, `test_the_task_notes_rule_examples_match_the_parsers`), so those examples cannot drift from the checks. The decision and research examples are not tested: nothing parses those documents yet.

**So the answer to "is it intentional":** yes in effect. The example in the rule is the template, and a model step reads the rule anyway. A filled example also teaches a model better than a form of placeholders, and leaves no placeholder text behind for a check to catch.

**Recommended.**

1. Extend the alignment test to the decision and research examples: their headings must be the ones the rule's text requires. A few lines, no new parser.
2. Ship no separate template files in the package.
3. If the owner wants fill-in files for people writing by hand, let the installer write them, generated from the rule's fenced example (`.claude/rules/temperspec/templates/<type>.md`), refreshed by `--update`, with a test that the generated file equals the block. One source, so no drift in the plugin; an installed copy can go stale only the way an installed rule file already can.

## 7. Conclusions

1. temperspec's plan differs from the common plan parts mainly by decision: no bookkeeping in documents, decisions in their own records, no release step. Those differences should stay.
2. Four parts were left out without a decision and are cheap to add: the requirement link on rows (A1), docs rows for listed docs (A2), two-pass writing (A3) and the pin search (A4).
3. Reading sets, the track map and verification kinds should wait for the features that give them value: per-phase coding (B7) and repository commands (B10), both now possible on the engine.
4. Separate templates are not needed; the rule examples are the templates and are held to the parser. The two untested examples should be tested.
5. The other tools agree with 2 and 3: most link tasks to requirements, name what to read and what a task produces, and cap the unit of work. None has a per-criterion proof like temperspec's, and none lints reading sets. GSD's scope-reduction guard is the one new idea worth a small optional check (A5).

## 8. Open questions

| # | Question | Who |
|---|---|---|
| Q1 | Which of A1 to A5 to build now, and whether the per-phase `Read:` and `Produces:` lists, phase command and phase cap go with B7 | Owner |
| Q4 | Kiro's and Tessl's plan formats, which this session could not reach | A session whose network allows `kiro.dev` and `docs.tessl.io` |
| Q2 | Whether the optional `## 5. Left open` section (F7) is wanted, and if so merged with B1's assumptions in one pull request section | Owner |
| Q3 | Whether fill-in template files should be generated at install time for people writing by hand (§6, point 3) | Owner |
