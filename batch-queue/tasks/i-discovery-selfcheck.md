The discovery step checks its own work before its judge, and a judged retry of discovery changes only what the failing criteria name (issue: to be filed)

temperspec's discovery step is its costliest thinking step, and a failed gate today costs a second visit of the same size. This run makes the first attempt check itself before it ends, and makes a retry after the judge a narrow one. The area is the temperspec package only (`plugins/temperspec-tgraph`): specs `discovery` and `discovery-short`, the prompt and the judge brief of `discovery`. Related and not the same: #134 (split the discovery gate), #224 (method skills piloted in discovery), #181 (a retry that breaks a criterion met before).

What the code does today, on the trunk at `7fd52537`:

- The engine can give a step a preview of its gate's check (`self_check: true`, engine spec `check-contract-and-command-runs`, CHK-B17): the session runs one command and reads what the check would find, up to the run's `self_check_limit` times an attempt. In `workflow/temperspec/__init__.py` only the `code` step declares it. `discovery` does not, so a form, link, budget or commit failure of `discovery_check` is first seen at the gate and costs an attempt.
- The judge of `discovery` grades four criteria the check cannot (`ts-dis-gaps`, `ts-dis-behaviour`, `ts-dis-general`, `ts-dis-scope`, in `docs/specs/discovery.spec.md`). `prompts/discovery.md` does not tell the session to hold its documents against them before it ends.
- After a judged RETRY the engine opens a fresh session with the same template, the blockers (criterion, place, problem, fix), the previous report and the changed paths (engine spec `prompt-rendering`, PRM-B9). The template tells that session to do the whole step: read the rules, read the triage note and close every gap. Nothing tells it that the gaps the judge did not fault are done.

Acceptance criteria:

1. The `discovery` step declares the check preview, so its prompt carries the engine's section "Check your work before you end" with the command; a package test asserts the declaration and the rendered section.
2. `prompts/discovery.md` tells the session to run the preview after its last edit and commit, to fix each finding it reports, and to end only when the preview reports none or the attempt's previews are used up.
3. `prompts/discovery.md` holds a self-check list the session goes through before it ends, one item for each criterion the judge grades (`ts-dis-gaps`, `ts-dis-behaviour`, `ts-dis-general`, `ts-dis-scope`), each in the judge's own terms: what a defect is and where to look.
4. A package test holds the prompt and the judge brief together: every criterion id the judge of `discovery` grades is named in the prompt's self-check list, and the test fails when a judged criterion is added without its item.
5. The hand-off of a first attempt has a section that says, for each item of the self-check list, what was checked and where (a path and a behaviour id or a line), or says the item does not apply; `discovery_check` fails a hand-off of a task with gaps that lacks the section, under a criterion id of its own.
6. `prompts/discovery.md` has a part for a retry after the judge. It tells the session: the blockers above are the whole task; open only the documents and gap rows they name; change nothing else; do not read the rule files again except the one a blocker names; do not rewrite the hand-off, only amend the rows that changed.
7. A retry after the judge leaves the documents no blocker names unchanged: `discovery_check` reports, as a lead for the judge, each document the retry changed that no blocker of the previous verdict names. A package test with a scripted session proves the lead for one such document and its absence for a named one.
8. The check criterion `ts-dis-ruleread` (every rule file the prompt names is opened) holds for a first attempt and, on a retry after the judge, only for a rule file a blocker names; a test proves both.
9. The judge brief of `discovery` says that on a retry it grades every listed criterion again, and that a document changed outside the blockers is a scope defect unless the hand-off says why the change was needed.
10. A fixture run of the package with a scripted executor proves the path end to end: a first attempt whose judge fails one criterion on one document is followed by a retry whose prompt holds the narrow part and the blocker, and the run passes the gate at the second attempt.
11. `docs/specs/discovery.spec.md` states the behaviours of criteria 1 to 9 and its criteria list carries the new ids; the spec stays within the spec budget, and `discovery-short` changes only where it would be false.
12. The step's effort, model and timeout, the judge's effort and model, and the run's default attempt cap are unchanged; a test asserts the sizing of `discovery` and its judge is what the trunk holds. Each new test carries the id of the spec criterion it proves, and the package's existing discovery tests still pass, changed only where a criterion above changes the fact they assert.

Out of scope, each named in the report:

- The effort level of discovery and the default attempt cap: the owner's decisions, not this run's.
- Splitting the discovery gate into two passes (#134).
- An engine change. If a criterion cannot be met in the package, the run stops and says which, and the need is written in the package's docs for a later request.
- The short visit `discovery_short` gaining a self-check of its own, and the reading sessions before discovery.
- A retry after a check FAIL: it already carries the failing findings and is not changed here.

Likely files: `plugins/temperspec-tgraph/workflow/temperspec/__init__.py` (the `discovery` step), `workflow/temperspec/checks.py` (`discovery_check`), `prompts/discovery.md`, `judges/discovery.md`, `docs/specs/discovery.spec.md`, `tests/` (the discovery tests and one fixture run). The package is restamped by its script step. No engine file.

To settle before the run starts: no issue exists for this request; the owner files one and its number replaces the first line's note.
