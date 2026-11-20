# Phase 1: intake and the entry paths

The three paths differ only in how the first drafts are found. From phase 2 on, the interview is the same. A session can mix paths: take more sources in at any time with `tempergraph author intake <id> <path>…`.

| Path | The person brings | You read first | First drafts come from | Watch for |
|---|---|---|---|---|
| `solution` | Something that already does the job: a script, a prompt or prompt chain, a runbook, a skill or agent, another tool's workflow, past outputs | Its stages, calls, the files passed on, its own tests and assertions, its outputs | Steps from its stages; deliverables from its outputs; criteria from its tests, assertions and reviewers' comments | A self-check of the solution is a claim, never a verification (`claim:self_check` in the inventory) |
| `sources` | Templates, good and bad examples, standards, checklists, a Definition of Done or Ready, style guides, acceptance criteria, review rules, docs pages, tickets | Headings, task lists, rules, numbered requirements, the examples' structure | The statement and deliverables from the template and examples; criteria from checklists and rules; bad examples as must-fail fixtures | Requirements that conflict between sources: show them side by side and let the person rank them |
| `chat` | Only words | Nothing | The answers to phase 2's three questions, then a graded draft: write two short contrasting sample outputs, or ask for one real example, and ask which is better and why | Criteria drift: say the first list will change, because people find criteria by grading |

## Taking sources in

- Examples: `--kind example_good` or `--kind example_bad`, with `--artifact <key>` naming the deliverable they show (and `--unit <unit>` when you already know the unit). Scaffold turns them into must-pass and must-fail fixtures.
- A source over 5 MB or binary is recorded as `other` with no candidates.
- The record keeps names, lines, counts and digests. The text stays in the session folder. Never paste source text into `authoring.json`.

## Play back and fit check

Play the process back in at most six bullets, then check the fit:

| A good candidate | Not a fit yet |
|---|---|
| It is done again and again | A one-off exploration |
| It ends in something a check or a judge can grade | Every step is a conversation |
| The person can say in words what done means, and the inputs are known | Nobody can yet say what good looks like |
| It splits into two to six steps, each with a checkable result | A shape this release does not run (see the steps reference) |

When the person says yes to the play-back, run `tempergraph author approve <id> 1`.
