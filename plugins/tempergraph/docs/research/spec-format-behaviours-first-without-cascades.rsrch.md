# A spec format with behaviours first and no cascade edits

## Problem statement

In the discussion of temperspec's principles (2026-11-21) the owner said a run's result is rejected when specs are not in sync with each other, when a spec is incomplete, or when the code is not aligned with the specs. On the format they added: "the behaviors should be main part of them, secondary is acceptance criteria for sure, other parts under a question", that documentation takes a large share of spend, and that a change to a few specs can edit many others only to propagate a change log or version. The cascade must be avoided.

This note answers:

1. What causes a spec cascade, and which rules remove it?
2. How does this repository's own spec set, written under those rules, behave on cascade measures?
3. What do public spec formats put first, and how do they keep a change local?
4. What format and rules should temperspec's spec rule start from?

Research only. No spec, rule or code changes with this note. The proposal is input for temperspec's spec rule file and for the authoring session of `temperspec-tgraph` ([research `temperspec-as-the-first-authored-workflow`](temperspec-as-the-first-authored-workflow.rsrch.md)).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S2 | This repository's spec rules | Design set | [docs README](../README.md) |
| S3 | This repository's 70 engine specs and their git history at `26096be`, measured with two throwaway scripts on 2026-11-21 | Measurement, single run | `specs/*.spec.md`, `git log -- specs` |
| S4 | OpenSpec concepts page | Public documentation, read 2026-11-21 | https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/docs/concepts.md |
| S5 | Kiro specs concepts page | Public documentation, read 2026-11-21 | https://kiro.dev/docs/specs/concepts |
| S6 | GitHub Spec Kit templates, on a documentation mirror | Public documentation, read 2026-11-21 | https://www.mintlify.com/github/spec-kit/advanced/templates |

## Key findings

### F1 A spec cascade comes from bookkeeping, and rules can remove it `inferred`

A change that touches one spec edits others when every spec carries lines a change must keep current: a version, a number, an index row, a change log, a status, a list of the tests that prove it. Numbers taken from a shared sequence are renumbered at merge, and test names kept in a spec make it grow with every test. Each such edit is collateral: the spec's behaviour did not change.

The rules that remove it: no per-spec version, date or change log; ids scoped to the work item; a generated index; status derived from a generated proof matrix; links by id; a row says what the system does now. Two questions follow: where proof lives once test names leave the spec, and whether a row keeps a maturity mark.

### F2 This repository's specs follow those rules, and still fan out `supported` (one measurement)

| Measure (S3) | Value |
|---|---|
| Specs, total size | 70 files, 1,042 KB; none over the 30 KB budget, the largest 4 bytes under it |
| Share of bytes by section | Contract 56.3%, Behaviours 15.2%, Design notes 8.6%, Overview 6.8%, Acceptance criteria 4.5%, Error conditions 3.5%, Open questions 2.1%, References 1.9%, header 1.0% |
| Commits that touch a spec | 97; 67 of them (69%) touch more than one; median 3 files, maximum 23 |
| File edits of four changed lines or fewer | 249 of 445 (56%) |
| Changed lines that are header fields, a references line or an index row | about 6% (`adrs` 1.4%, `status` 1.2%, references 0.9%, index rows 0.7%, other header fields 1.5%) |
| Commits that edit the overview spec, the contracts spec | 22 and 25 of 97 |

Reading:

- **Behaviours are not the main part today.** Contract tables are more than half of the text; behaviours and acceptance criteria together are a fifth.
- **The version and changelog cascade is gone** (about 6% bookkeeping lines), because the updating rule already bans those notes.
- **A structural cascade remains.** Most commits touch several specs and more than half of the file edits are tiny. The causes visible in the history: the hand-kept spec index in the overview, the one contracts spec every shared type must go through (it sits at its size limit), the `adrs` and `status` header fields, references lines, and cross-links by section number.
- Limits of the measurement: these commits are design work that added whole features, where touching several specs is partly real; the line classifier is a set of regular expressions; nothing here was re-run.

A second cascade showed up during this work: **sequence numbers collide across parallel branches.** The note research `temperspec-as-the-first-authored-workflow` of this thread and another thread's note took the same number, and one was renumbered.

### F3 Public formats put behaviour first and keep everything else out of the spec `supported`

| Format | What a spec holds | What it keeps out | How a change stays local |
|---|---|---|---|
| OpenSpec (S4) | `Purpose`, then `Requirements`; each requirement has `Scenario` blocks in GIVEN/WHEN/THEN; requirement strength by SHALL, MUST, SHOULD | "A spec is a behavior contract, not an implementation plan": no internal names, library choices or step-by-step detail. Its test: "If implementation can change without changing externally visible behavior, it likely does not belong in the spec." No version, date, status or changelog field is described | Specs are grouped by capability. A change writes a **delta** (`ADDED`, `MODIFIED`, `REMOVED` requirements) in its own change folder; archiving merges the delta into the main spec and moves the change, with its design and tasks, to a dated archive |
| Kiro (S5) | `requirements.md`: user stories with acceptance criteria in EARS form, "WHEN [condition/event] THE SYSTEM SHALL [expected behavior]" | Architecture goes to `design.md`, the plan to `tasks.md` | One folder of three files per feature; no rule for syncing specs after implementation is stated |
| Spec Kit (S6) | User stories with priority and Given/When/Then acceptance scenarios, functional requirements `FR-001`, success criteria `SC-001`, key entities | "Focus on what and why, not implementation details"; the technology stack belongs to the plan | One spec per feature branch |

All three make the behaviour statement and its scenarios the body of the spec, put design and plan in separate documents, and none carries a per-spec version or change log. Only OpenSpec addresses the long-lived spec of a capability that many changes edit, which is temperspec's case; Kiro and Spec Kit describe a spec per feature.

## Analysis

### Proposed format

One spec per capability. Sections, in order:

| Section | Required | Holds |
|---|---|---|
| Purpose | yes | Two or three sentences: what the capability is for and who relies on it |
| **Behaviours** | yes, the body | One block per behaviour: a stable id (`PREFIX-Bn`), one sentence saying what the system does now, then Given/When/Then scenarios with example values. An error case is a behaviour, not a separate section |
| **Acceptance criteria** | yes | Verifiable statements with ids (`PREFIX-ACn`), each naming the behaviour ids it proves |
| Interface | only when another capability or a person consumes it | The externally visible surface only: commands, file formats, fields others read. A type lives in the spec whose behaviours produce it; other specs link its id |
| Open questions | only while any is open | Each with an owner. A spec with an open question is not ready |

Left out, with where the content goes:

| Today's part | Goes to |
|---|---|
| Header fields `status`, `adrs`, `type` | Dropped. Ready means no open question and every acceptance criterion maps to a behaviour; implemented is read from the proof matrix |
| Overview with goals and non-goals | Purpose; a non-goal that matters is a decision record |
| Error conditions | Behaviours |
| Design notes | Decision records. A behaviour may link the one record that explains it |
| References | Inline links where they are used |
| Version, date, change log, test lists, maturity marks | Git history and the generated proof matrix |

### Rules that stop the cascade

| # | Rule | Stops |
|---|---|---|
| C1 | A spec carries no version, date, change log, status or list of proving tests | Bookkeeping edits |
| C2 | A link lives in one place. No back-link lists: a spec does not list its decision records, and nothing lists "specs that mention me" | The `adrs` and references edits |
| C3 | Indexes are generated from the files (title and purpose) by a script, never edited by a step | Index edits in the overview |
| C4 | Links point to ids (`JDG-B3`), never to section numbers. An id is never reused or renumbered | Edits that only repair links |
| C5 | A shared type or term is defined once, in the spec that owns its behaviour; there is no central file every change must pass through | The contracts hot spot |
| C6 | New documents take a name that cannot collide across branches (a slug, or a number assigned at merge by a script) | Renumber-at-merge edits |
| C7 | A run may edit a spec only where a behaviour, an acceptance criterion or the interface changes. A check compares the diff with this rule and reports every other spec edit as collateral | The cascade itself, and makes it measurable |
| C8 | A row says what the system does now; a change rewrites the rows it affects | Growth by appended notes |

C7 is the one that turns the owner's concern into something a gate can hold: the discovery gate reports a **collateral share** (spec files edited with no behaviour, criterion or interface change, over spec files edited), and the run log already gives the spend of the documentation steps, so documentation cost per run becomes a number to watch rather than an impression.

### What "in sync" and "aligned" can mean to a gate

| The owner's rejection reason | Check (model-free) | Judge |
|---|---|---|
| A spec is incomplete | Purpose present; at least one behaviour; every behaviour has a scenario; every behaviour is named by an acceptance criterion and every criterion names a behaviour | Each behaviour is observable from outside and says what, not how |
| Specs are not in sync with each other | Every linked id resolves; no id or type defined twice; no open question in a spec the change relies on | No behaviour in the specs the change edited contradicts a behaviour in the specs they link. The judge reads that set, not the whole folder |
| Code is not aligned with the specs | Every acceptance criterion of an edited spec is named by at least one test (the test carries the id); those tests pass in the gate's own run; the proof matrix is generated from this | The change does what each edited behaviour says, and nothing a spec forbids |

The proof matrix answers F1's question of where proof lives: in the tests, which carry criterion ids, and the matrix is generated, never written.

### Direct edit or delta

Two ways to change a long-lived spec:

| | Direct edit under C7 | Delta, as in OpenSpec |
|---|---|---|
| How | The step edits behaviour blocks in the spec; the check flags any other edit | The step writes added, modified and removed behaviours in the task's folder; a script merges them into the spec when the run is published |
| For | Nothing new to build beyond the check; a reviewer reads the spec as it will be | The model writes only what changes; one behaviour change cannot touch another file; the delta is a ready review summary |
| Against | The step still opens and rewrites whole files, which costs tokens | A merge script and its failure cases; two places hold the truth until merge; parallel runs can conflict at merge |

Recommendation: start with direct edit and C7, because it needs only a check and gives the collateral number at once. Revisit the delta once that number and the documentation spend are measured on real runs.

## Conclusions

1. Bookkeeping lines in specs (versions, change logs, test lists) cause a cascade, and banning them removes that part of it (F1).
2. This repository's specs, written under those rules, have almost no bookkeeping lines but still fan out: 69% of spec commits touch more than one spec and 56% of file edits are four lines or fewer. The causes are structural: a hand-kept index, a central contracts file, header fields, back-links and links by section number.
3. Behaviours are 15% of this repository's spec text and acceptance criteria 4.5%; contract tables are 56%. The owner's "behaviours first" is a real change of format, not a restatement.
4. Public formats agree on behaviour statements with scenarios as the body, design and plan elsewhere, and no version or change log in the spec.
5. A format of Purpose, Behaviours, Acceptance criteria, an optional Interface and temporary Open questions, under rules C1 to C8, removes each cascade cause found here.
6. A check can hold completeness, link and id consistency, the criterion-to-test trace and the collateral share; a judge is needed only for contradiction between linked specs and for whether the change does what the behaviours say.
7. Nothing here is measured on a temperspec run. The collateral share and documentation spend should be recorded from the first runs.

## Owner's rulings after reading (2026-11-21)

| Subject | Ruling |
|---|---|
| The proposed format and rules C1 to C8 | Agreed |
| Interface section (Q1) | Not a section: it would use lines in the spec. Interface facts are written as behaviours. A behaviour may name only what someone outside the capability depends on (a command a person types, a field another tool reads), never an internal name |
| Behaviour wording (Q5) | A fixed format |
| Size | A cap of 400 lines per spec; a spec that reaches it is split or compressed |
| Direct edit or delta (Q3) | Direct edit with the collateral check, as recommended |
| The engine's 70 specs (Q4) | Migrated once temperspec is ready |

## Open questions

| # | Question | Owner |
|---|---|---|
| Q1 | Is the Interface section kept as an optional part for what others consume, or should every interface fact be written as a behaviour? | Owner |
| Q2 | Document names: slugs with no number, or numbers assigned at merge by a script? | Owner |
| Q3 | Direct edit with the collateral check first, or the delta approach from the start? | Owner |
| Q4 | Should the engine's 70 specs be migrated to the new format, and when? They are the first target repository's documents | Owner |
| Q5 | Which wording for a behaviour statement: plain present tense ("The gate retries…"), or a fixed pattern such as EARS ("WHEN … THE SYSTEM SHALL …")? A fixed pattern is easier to check, plain prose is easier to read | Owner |

## References

[research `temperspec-as-the-first-authored-workflow`](temperspec-as-the-first-authored-workflow.rsrch.md) · [docs README](../README.md)
