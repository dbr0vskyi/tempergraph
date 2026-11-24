# temperspec

## 1. Overview

Every acceptance criterion in the task's triage_note is met on the run's own branch: by tested code that follows specs which agree with each other, or by those specs alone in a docs-only run.

Units:

- [prepare](01-prepare.spec.md): Install rules and the project note; see if setup is due
- [setup_route](02-setup_route.spec.md): a repository with no overview spec goes to setup
- [setup](03-setup.spec.md): Write the overview spec and one spec per component
- [triage](04-triage.spec.md): Read the task, find the gaps, pick the route
- [discovery_short](09-discovery_short.spec.md): Confirm the cited behaviours; write the hand-off
- [discovery](05-discovery.spec.md): Close each gap with a spec, record or research note
- [plan](06-plan.spec.md): Design requirements and phases; state complexity
- [code_mode](13-code_mode.spec.md): Pick one code session or the expand step from the plan check's facts
- [expand](07-expand.spec.md): Write task rows and verification for a complex plan
- [code](08-code.spec.md): Build the plan test first in one session
- [code_join](14-code_join.spec.md): Where both arms meet after the code step

Beside the units: [judge reading](judge-reading.spec.md), what each judge is told to read and to cite before it grades; [outcome gate](outcome-gate.spec.md), the documents the final gate requires of a run and what it reports about the push; [kept marks](kept-marks.spec.md), which completed marks of a plan survive a trip back to plan; [project note](project-note.spec.md), the rule files and the project-context block that prepare puts in a repository; [runs side by side](side-by-side-runs.spec.md), what the outcome check does when the base branch has changed a spec the run edited; [code mode](code-mode.spec.md), what chooses after the plan between building it at once in the one code session and having the expand step write its task rows first; [session record checks](session-record-checks.spec.md), what the gates confirm from the record of a step's session: the rule files opened, the files the expand rows name opened, and each phase's tests written before its source.

## 6. Acceptance criteria

- [ ] ts-committed Every file the run changed is committed on the run's own branch
- [ ] ts-spec-form Every spec the run edited passes the spec rule's structure check
- [ ] ts-spec-cap No spec the run edited is over 400 lines
- [ ] ts-spec-links Every id that a spec the run edited links to resolves to exactly one definition
- [ ] ts-spec-moved An acceptance criterion that a split left in a spec may name a behaviour the split moved to another spec, where it keeps its id: the spec rule's structure check reads the id as defined in the spec it moved to, in the run that made the split and in any later run
- [ ] ts-spec-parent An acceptance criterion of a spec split from another may name an id of the spec it was split from: the spec rule's structure check reads the id as defined there, in the run that made the split and in any later run
- [ ] ts-spec-fresh No spec the run edited has changed on the base branch since the run started
- [ ] ts-traced Every acceptance criterion the run added or reworded in a spec, and every criterion that proves a behaviour the run added or changed, is named by at least one test that is not skipped
- [ ] ts-verify Every verification command the plan lists exits 0 on the branch head
- [ ] ts-collateral No spec file is edited without a change to a behaviour or an acceptance criterion
- [ ] ts-spec-sync No behaviour in a spec the run edited contradicts a behaviour in a spec it links to
- [ ] ts-accepted Each acceptance criterion of the task is achieved by the run's commits

## Open questions

- Per-phase coding waits for the engine's sequential map; until then a complex plan is coded in one session.
- No step or judge uses the large model tier; each states its effort and the reason ([0002](../adr/0002-model-and-effort-per-unit.adr.md)).
- Whether the code agrees with the specs by meaning is judged once, at the code gate (ts-code-aligned, ts-code-related), not again at the outcome gate.
- The release step and a work-tracker start are left out of the first version.
- Verification commands resolve against one fixed list (pytest, both spellings of `python -m pytest`, ruff, mypy and read-only git) because release 1 of the engine reads no per-repository command resolver; a repository with another toolchain adds its prefixes to the workflow's list. A command written `cd <folder> && <command>` runs in that folder, so a plan copies the repository's own instructions as written.
- A judge sees a step's output and its references, never the step's prompt or the gate's command runs, so criteria about how a step works are checked by the gate, model-free (ts-dis-narrow, ts-plan-reading, ts-code-once, ts-code-preview, ts-code-reuse, ts-code-ran, ts-dsh-limit). What a code session actually ran is read by the engine's session review in the improvement loop, not graded at the gate.
- The short discovery visit (discovery_short) is a second step beside discovery, chosen by the route after triage; every return to discovery from a later gate goes to the full visit ([0003](../adr/0003-short-discovery-visit.adr.md)).
- Specs written by the setup step describe behaviour that exists already, so the outcome gate does not ask for a test that names each of their acceptance criteria; a task that later touches such a behaviour adds the id to its test.
- Repository setup is a conditional first step of this workflow because release 1 of the engine has no sub-workflows; it moves into one when the engine has them.
