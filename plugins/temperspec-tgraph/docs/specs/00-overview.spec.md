# temperspec

## 1. Overview

Every acceptance criterion in the task's triage_note is met on the run's own branch: by tested code that follows specs which agree with each other, or by those specs alone in a docs-only run.

Units:

- [prepare](01-prepare.spec.md): Install rules and the project note; see if setup is due
- [setup_route](02-setup_route.spec.md): a repository with no overview spec goes to setup
- [setup](03-setup.spec.md): Write the overview spec and one spec per component
- [triage](04-triage.spec.md): Read the task, find the gaps, pick the route
- [discovery](05-discovery.spec.md): Close each gap with a spec, record or research note
- [plan](06-plan.spec.md): Design requirements and phases; state complexity
- [expand](07-expand.spec.md): Write task rows and verification for a complex plan
- [code](08-code.spec.md): Build the plan test first in one session

## 6. Acceptance criteria

- [ ] ts-committed Every file the run changed is committed on the run's own branch
- [ ] ts-spec-form Every spec the run edited passes the spec rule's structure check
- [ ] ts-spec-cap No spec the run edited is over 400 lines
- [ ] ts-spec-links Every id that a spec the run edited links to resolves to exactly one definition
- [ ] ts-traced Every acceptance criterion of each spec the run edited is named by at least one test that is not skipped
- [ ] ts-verify Every verification command the plan lists exits 0 on the branch head
- [ ] ts-collateral No spec file is edited without a change to a behaviour or an acceptance criterion
- [ ] ts-spec-sync No behaviour in a spec the run edited contradicts a behaviour in a spec it links to
- [ ] ts-accepted Each acceptance criterion of the task is achieved by the run's commits

## Open questions

- Per-phase coding waits for the engine's sequential map; until then a complex plan is coded in one session.
- The plan, the code report and the discovery hand-off are not listed as deliverables because the engine requires every listed deliverable on every path, and a docs-only run or a run with no gaps does not produce them all.
- No step or judge uses the large model tier.
- Whether the code agrees with the specs by meaning is judged once, at the code gate (ts-code-aligned, ts-code-related), not again at the outcome gate.
- The release step and a work-tracker start are left out of the first version.
- Verification commands resolve against one fixed list (pytest, ruff, mypy and read-only git) because release 1 of the engine reads no per-repository command resolver; a repository with another toolchain adds its prefixes to the workflow's list.
- Whether a commit is absent from every remote is not checked: the engine's git facts do not report it in release 1. Steps cannot push, and only the last stage does.
- Specs written by the setup step describe behaviour that exists already, so the outcome gate does not ask for a test that names each of their acceptance criteria; a task that later touches such a behaviour adds the id to its test.
- Repository setup is a conditional first step of this workflow because release 1 of the engine has no sub-workflows; it moves into one when the engine has them.
