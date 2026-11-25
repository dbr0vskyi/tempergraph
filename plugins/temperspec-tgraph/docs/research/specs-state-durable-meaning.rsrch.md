# How does temperspec keep the meaning of a change out of a spec's wording?

## Problem statement

The owner reviewed pull request #113 (twelve issues built by temperspec runs) and found that the engine specs it changes read as literal descriptions of the tasks: what the bug was, which workflow needed it, which fixtures prove it. They do not state the general rule of the capability. That breaks what a spec is for, and in the engine repository it also breaks ADR-0129 (the engine knows no workflow): engine specs name no workflow package and state a workflow's need only as a general capability.

The unknown: which part of temperspec lets task-shaped and workflow-shaped text into a spec, and what change to the rules, the prompts, the checks or the judge would make a run extract the durable meaning instead.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Engine specs changed by pull request #113 | spec | `git diff main...claude/project-thread-ku7dl5 -- plugins/tempergraph/docs/specs` (13 files) |
| Triage notes and hand-offs of the runs i6-8, i9, i16, i17-18 | task note | `plugins/tempergraph/docs/tasks/` on that branch |
| Engine specs on `main` | spec | `plugins/tempergraph/docs/specs/` |
| Spec rule | rule | `rules/spec.rule.md` |
| Documents rule | rule | `rules/documents.rule.md` |
| Triage prompt | prompt | `prompts/triage.md` |
| Discovery prompt | prompt | `prompts/discovery.md` |
| Discovery judge brief | judge | `judges/discovery.md` |
| Earlier comparison of spec-driven tools | research | [sdd-tools-comparison.rsrch.md](sdd-tools-comparison.rsrch.md) |
| OpenSpec concepts: `specs/` is current truth, `changes/` holds proposals and deltas merged at archive | web | <https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/docs/overview.md>, <https://github.com/Fission-AI/openspec> |
| Spec Kit spec template: "Focus on WHAT users need and WHY; avoid HOW" | web | <https://devblogs.microsoft.com/blog/spec-driven-development-spec-kit>, <https://www.mintlify.com/github/spec-kit/advanced/templates> |
| Cucumber guidance: scenarios hold just enough to describe behaviour; declarative over imperative; "will this wording change if the implementation does?" | web | <https://docs.cucumber.io/community/faq/>, <https://itsadeliverything.com/declarative-vs-imperative-gherkin-scenarios-for-cucumber>, <https://www.thoughtworks.com/en-in/insights/blog/imperative-vs-declarative-style-writing-twist-scenarios> |

## Key findings

### F1 The leak in pull request #113 is shape and history, not the word "temperspec" `confirmed`

No line the pull request adds to an engine spec names temperspec (searched the diff for `temperspec`, `triage`, `discovery`). What leaked is of five kinds:

1. **The change's history as behaviour.** Headings and rules written against the old defect: CTS-B11 "A later attempt runs in worktrees of its own", CTS-B12 "An earlier attempt's slot work is left as it is", MAP-B15 "An earlier visit's item work is left as it is", SRV-B28 "… files nothing alone". Each says "no longer what the bug did" rather than the rule. Task i16's criterion 3 asked for exactly this: "the R3-T4.2 known limit is no longer true in the specs".
2. **One rule copied per task.** MAP-B14 to MAP-B16 (issue #17) and CTS-B11 to CTS-B13 (issue #16) are the same rule twice, one per unit kind: a writer cut for a later pass of a unit gets fresh names from the current head, earlier cuts are left alone, and only this pass's work is merged. WTR-B20 then spells out both suffix forms (`--i<n>-`, `--s<n>-`) in one long sentence. The owning capability (writer worktrees, WSP and WTR) never got the general rule.
3. **The motivating workflow's shape in engine scenarios.** WSP-B18: "a workflow of a planning step followed by a concurrent map whose step declares `write`" (`workspace-and-concurrency.spec.md` line 137 on the branch); MAP-B14: "the planning step having rewritten the list file" (`map-unit.spec.md` line 98). Both are temperspec's plan-then-phase map. The new `review-repeats.spec.md` names the units `code` and `plan` 18 times, temperspec's unit names, and takes `instruction_ignored` on `code` from temperspec's overnight runs (R-160 F7).
4. **Test fixtures as scenarios.** Session keys `code.1.step`, `code.2.retry`; issues "#12 and #19" (PRP-B24, PRP-B29, PRP-AC8); branch names `demo--C-1--s2-s1` in the plan. A scenario that copies a fixture is a test, not an illustration.
5. **Cross-capability proof inside a behaviour.** AUD-B17's third scenario proves `author verify` rung 6 (SCF) from inside the audit spec.

### F2 The same kinds already sit on `main` `confirmed`

- Five engine specs cite "R-075 temperspec needs against the engine" in their Purpose as the reason they exist (75, 76, 77, 78, 79).
- PKG-B8 "A delivery workflow as a package" and AUT-B8 describe temperspec (known debt).
- SIL-B17 carries an owner's reason inside the rule: "default `max`, because the loop reads session logs and the owner keeps it on the medium tier" (`self-improvement.spec.md` line 95). Thirty-eight behaviour lines hold "because" or "the owner".
- Unit names `code` and `plan` appear in scenarios of 31 engine specs. Many of these are harmless placeholders, but they are temperspec's names, not neutral ones.

### F3 Nothing in the rules asks for a general rule, and two prompts push the other way `confirmed`

- `rules/spec.rule.md` checks the form (WHEN/THE/SHALL, scenarios, criteria), observability (line 44: no class, function, module or variable) and length. It says nothing about stating the rule in general, nothing about scenarios being examples rather than fixtures, and nothing about workflow names.
- `rules/documents.rule.md` line 38 has the right idea ("A line says what the system does now … appends no note about the change"), but it is about notes appended to a line, and no check or judge criterion applies it.
- `prompts/triage.md` line 19 copies the task's criteria word for word. Issue criteria are often written about documents ("CTS states what a second attempt does", "the known limit is no longer true in the specs").
- `prompts/discovery.md` line 30: "Every acceptance criterion of the task that a gap concerns must be provable from the behaviours you wrote." The shortest way to satisfy this is to restate the task's criterion as a behaviour, with its wording, its case and its fixture.
- `prompts/discovery.md` line 38 and `rules/spec.rule.md` line 67 ("Edit only the behaviours … the task changes … do not touch other specs") are right against cascades, but they also stop discovery from lifting a rule into the spec that owns the mechanism, which is why F1.2 happened twice.

### F4 The judge grades coverage, observability and scope only `confirmed`

`judges/discovery.md` line 10 checks that an observer can see the event and the result, line 11 that every change serves a gap row. No criterion asks whether a behaviour is the general rule, whether it would read right to someone who never saw the task, or whether it names a workflow. "Judge meaning, not wording" refers to agreement between behaviours, not to abstraction.

### F5 Other tools keep the change and the truth in separate documents `supported`

OpenSpec keeps `openspec/specs/` as how the system behaves now and `openspec/changes/<name>/` for the proposal (why), the tasks and the delta; the delta is merged into the specs at archive. The why and the case stay in the change folder; only requirements reach the spec. Spec Kit's template tells the writer to state what and why, not how, and keeps technical choices for the plan. Neither has a mechanical check for abstraction.

### F6 BDD practice gives a usable test for scenarios `supported`

Cucumber's guidance: a scenario holds just enough to describe the behaviour, and declarative scenarios outlive imperative ones. The practical test it cites is "Will this wording need to change if the implementation does?" The same test works for the motivating workflow: will this wording need to change if a different workflow had asked for it?

### F7 temperspec already has the second document OpenSpec has `inferred`

The triage note (task, its criteria) and the hand-off (what changed and why) are temperspec's change folder. The plan's proof table maps the task's criteria to tests. So the task's literal criteria already have a home outside the spec; the prompts do not tell discovery to leave them there.

## Conclusions

1. The cause is in the package, not in one run: the rules never ask for a general rule, the discovery prompt asks that the task's criteria be provable from the spec, and the judge does not grade abstraction (F3, F4). Every run that closes a bug through discovery will write the bug into the spec.
2. Neither a rule change nor a skill alone is enough. The rule says what a durable spec is; the prompt must turn the task into that rule; a check and a judge criterion must catch what slips through, since F1 shows a rule that is only implied (documents rule 7) is not followed.
3. Recommended change, all inside the package:
   - **Spec rule, a new section "General rules, not cases":** a behaviour is a rule of the capability that holds for every case, written as if the capability had always worked this way. It never refers to a task, issue, bug, earlier limit or earlier behaviour ("no longer", "again", "still", "now", "instead of"). It names no workflow and no workflow's units or shape: placeholders such as `a`, `b`, `step one` stand in. A scenario is an illustrative example, at most three per behaviour, and never a test fixture: no issue numbers, session keys or branch names of a test. A reason goes in a decision record, not in the behaviour. When the same rule holds for several capabilities, it is stated once in the capability that owns the mechanism and linked from the others; that edit is not collateral.
   - **Triage:** keep copying the task's criteria verbatim (they rank first), but add a column or line that says which capability each criterion is an instance of, so discovery knows the owning spec.
   - **Discovery prompt, an extract step:** for each task criterion, write the general rule it is an instance of into the owning spec, and leave the task's own wording, case and history in the triage note and the hand-off. Replace "provable from the behaviours you wrote" with "an instance of a behaviour you wrote or one that exists". Then reread each new behaviour as someone who has never seen the task.
   - **Model-free check `ts-spec-literal` (warning first, failure later):** on the lines a run adds to a spec, flag issue numbers (`#\d+`), the task id, change words ("no longer", "anymore", "known limit", "bug", "fix", "instead of"), and terms from a repository-owned deny list. The engine repository's list holds the names of its workflow packages and their units, read from `plugins/*/tempergraph.json`, so the check knows no workflow name itself.
   - **Discovery judge, one new criterion:** each new or changed behaviour reads as a general rule of its capability, true without the task; a behaviour that narrates the change, describes the motivating workflow, copies a fixture, or repeats a rule another spec owns is a defect.
4. The cleanup of what already leaked is separate and small: the five F1 kinds in pull request #113, and on `main` the R-075 references in five Purposes, PKG-B8, AUT-B8 and the owner's reason in SIL-B17. Merging MAP-B14 to MAP-B16 and CTS-B11 to CTS-B13 into one rule in WSP retires those six ids and defines new ones there, so it is a rewrite of six behaviours and their criteria, not a wording edit.

## Open questions

- Should the cleanup of pull request #113's specs happen in that pull request before it merges, or in a follow-up? The owner decides; this note recommends a follow-up so the branch's own runs are not disturbed.
- Should `ts-spec-literal` fail the gate from the start or warn for a first set of runs? Until answered: warn, since its word list has no measured false-positive rate.
- Should the one rule for later passes of a writing unit (F1.2) live in WSP (workspace) or WTR (worktree mode)? Until answered: WSP, which owns writer worktrees and the checkpoint.
