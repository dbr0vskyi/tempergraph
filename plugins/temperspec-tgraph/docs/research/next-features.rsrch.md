# Next features for temperspec: conversation, parallel work, a small-task route, and others

| | |
|---|---|
| Date | 2026-11-21 |
| Asked by | The owner, after the [comparison with other spec-driven development tools](sdd-tools-comparison.rsrch.md): how to design the conversation, how and when to support parallel work, how to route a small task, and which other features are promising |
| Method | The comparison's findings, read against what the engine already has or has designed (its specs for ask units, maps, flow extensions, worktrees, complexity switches and ladders) |
| Status | Proposal. Built since, on the owner's choice of 2026-11-21: the small-task route (§4) and features 1 to 3 of §5 (the criterion-to-test link in the reverse direction: the test carries the criterion, so a spec names no test file). The rest is not built |

## 1. Summary

| # | Feature | What it gives | Needs from the engine | Can start |
|---|---|---|---|---|
| 1 | **Conversation on demand** | The owner shapes the specs only when a real decision is open | A step that ends with questions and defaults; the ask unit (release 2) | Defaults-only mode now; questions with release 2 |
| 2 | **Parallel work**, in four cases | Shorter runs, and better judgement on hard choices | Read-only parallel branches and the sequential map (release 2); writer branches and parallel map (release 3) | Staged, §3 |
| 3 | **A small-task route** | No discovery, plan or expand for a fix that does not change behaviour | Nothing new | Now |
| 4 | Seven further features | §5 | Mostly nothing new | Three of them now |

**Recommended order:** the live checks first, since nothing here is worth more than a first real run. Then the small-task route, the criterion-to-test link and the pull request summary, which need no engine change. Then the conversation and per-phase coding, when the engine's release 2 brings the ask unit and the sequential map. Parallel writing last.

## 2. Conversation: unattended first, a person only when needed

**Problem.** Every compared tool talks to the person before the spec is written. temperspec takes the task as given. The owner's rulings stand: fewer touches by a person, no approval pause by default, no interactive agent inside a step.

**Design.** The engine never hosts a chat. A run asks at most once, before any spec is written, and only for decisions no code or document can settle.

1. **Triage sorts each gap.**
   - *Findable*: the code or the docs can answer it. Discovery closes it, as today.
   - *Owner decision*: only the owner can answer it. Examples: two possible behaviours, a missing acceptance criterion, two specs that conflict, a change that breaks a published behaviour.
   For each owner decision triage writes the question, two to four options, the default it would take, and what the default costs if it is wrong.
2. **A check keeps the list honest.** A question with no options or no default fails the triage check. A judge criterion asks whether each question could have been answered from the repository; if so it is a gap for discovery, not a question.
3. **No owner decision, no stop.** The run goes on unattended.
4. **Owner decisions stop the run once.** All questions arrive together. The run shows in the list of things waiting on a person. Two ways to answer:
   - *Plain*: answer in the terminal, or resume with an answers file.
   - *Interactive*: the tempergraph skill in the owner's own Claude Code session picks up the pause, talks the questions through, writes the answers file and resumes the run. The conversation lives in that session, so a pipeline runs the same workflow with no change.
5. **A setting chooses the behaviour**, per run or per repository:

   | Value | Behaviour | For |
   |---|---|---|
   | `never` | Take every default; list them in the pull request as assumptions to confirm | A pipeline, a night run |
   | `blocking` (proposed default) | Ask only when a decision has no safe default | Daily use |
   | `always` | Ask every owner decision | A new repository, a risky area |

   A time limit turns an unanswered pause into "take the defaults".
6. **Answers are documents.** They are written to the task's folder, cited by the specs that rely on them, and an answer that settles a lasting choice becomes a decision record in discovery.
7. **Measured.** Each question is a supervision touch in the engine's records. Questions that keep returning point at a missing rule or spec, which the improvement loop can propose.

**Engine side**, stated for any workflow: a step may end with a list of typed questions with defaults; the engine pauses on them, validates the answers by rule, and hands them to later steps as an artifact; a deadline applies the defaults. The engine's ask unit and deadlines (planned for release 2) are this. Mode `never` needs nothing from the engine and can be built now.

**Risks.** Triage asks too much (the judge criterion and the touch count are the guard), or too little (the defaults are listed in the pull request, so a wrong one is visible).

## 3. Parallel work: four cases

Parallel work shortens the wall-clock time of a run. It does not lower the token cost, and on a subscription sign-in several sessions at once reach the usage limit sooner; users of GSD report exactly that. For an unattended run the wall clock matters less than for a person waiting, so each case below must earn its place.

| Case | What runs side by side | When it pays | When not | Risk | Engine |
|---|---|---|---|---|---|
| **A. Reading** | Discovery research, one branch per gap; the setup survey, one branch per component; the judges of one gate, one per group of criteria | Three or more independent gaps or components. Always for judges, which are independent by design | One or two gaps | Low: nothing is written, one step joins the notes | Parallel read-only branches (release 2) |
| **B. Phases of one task** | Coding phases, each in its own sibling worktree, merged in the plan's order | The plan states phases with no dependency between them, and the plan check confirms from the task rows that their files do not overlap | Phases that depend on each other, shared files, refactoring | Merge conflicts, and tests that pass apart and fail together | Writer branches and the parallel map (release 3) |
| **C. Several tasks** | Whole runs, each in its own worktree and branch | Unrelated tasks. It already works: two runs can be started today | Tasks that edit the same spec | Two pull requests edit one spec. OpenSpec teams report this contention on shared files | Worktrees (built); batches and orchestration (release 3) |
| **D. Hard choices** | Several independent answers to one question, then a pick or a vote | An architecture decision in discovery, or a plan for a complex task | Routine work | Cost, by a factor of the number of answers | Contest and council units (release 3) |

**Order.**

1. **Sequential map first (release 2).** One fresh session, one gate and one commit per phase. This is not parallel, but it is the step that the other tools' quality rests on (GSD, GSD 2, Superpowers), it is what the owner already ruled for complex tasks, and case B is the same thing with the phases overlapped.
2. **Case A** next: cheap, safe, and it speeds up the two slowest document steps.
3. **Case C** needs one guard and no engine change: the outcome check fails when a spec the run edited has changed on the base branch since the run started, and sends the run back to discovery to edit the newer text.
4. **Case B** last, and only behind three rules: the plan declares independence, the check proves disjoint files, and the run's verification commands run again on the merged result. A merge conflict falls back to running the remaining phases in order.
5. **Case D** only where a measured switch shows a better outcome for its cost.

## 4. A route for small tasks

**Why.** A benchmark of 50 tickets found specs raised the merge rate only for features and for changes touching three or more files, not for bug fixes or refactors. A study of practice found people skip the method for small tasks. "One heavy workflow whatever the task" is the second most repeated criticism of these tools.

**Design: three lanes, chosen by triage, confirmed by a check.**

| Lane | Path | For |
|---|---|---|
| `quick` | triage → code → outcome gate → draft pull request | A fix or small change that leaves every spec as it is |
| `standard` | triage → (discovery) → plan → code | A change to behaviour of ordinary size. Today's simple path |
| `full` | triage → discovery → plan → expand → code | A complex task. Today's complex path |

**A task is `quick` only when all of these hold.** Triage states each one with its evidence, and the triage check verifies what it can:

- No gap of either kind.
- No behaviour or acceptance criterion of any spec has to change. A bug where the code disagrees with an existing spec qualifies: the spec is already the truth.
- At most three acceptance criteria in the task.
- Triage names the files, and they are at most two code files plus their tests.
- None of the heavy signs the plan step uses for complexity.

**What the quick lane keeps.** The same code gate: the model-free check runs the verification commands, the judge checks the change against the task's criteria and the related specs, and a test carries each criterion's id. For a bug, the test that reproduces it comes first. The triage note carries a short "change" section in place of a plan. The engine still commits after every step.

**What it drops.** Discovery, plan and expand: three sessions and three judges.

**The guard is measured after the fact.** The code check fails the quick lane when the change touched a spec, touched more files than triage named, or passed a line limit. The run then goes back to triage, which must choose `standard`. The move is one-way: a run never goes from a heavier lane to a lighter one. This is the rule the engine's complexity switches use (the safe arm is the most detailed one).

**Override.** The owner can force a lane at the start. `quick` forced on a task that fails the conditions is still caught by the guard.

**Engine side.** Nothing new: routes on step values exist today.

**To measure once runs exist:** how often the guard sends a quick run back. A high rate means the conditions are too loose.

## 5. Other promising features

Ranked by value for the effort.

| # | Feature | Taken from | What it gives | Engine | Can start |
|---|---|---|---|---|---|
| 1 | **A checked link from each acceptance criterion to its test.** The spec names the test; a check confirms the test exists, carries the id and ran | Tessl | Moves "code agrees with specs" partly from a judge to a check. It narrows the gap the package's decision record 0001 accepts | None | Now |
| 2 | **A test command for each criterion before coding.** The plan maps every criterion to the command that will prove it | GSD | "Done" is decided before the code exists; the code step cannot redefine it | None | Now |
| 3 | **A pull request summary of what the owner must read**: the behaviours and criteria that changed, the defaults taken, the deviations | The review-burden criticism | The owner reads a page, not every file | None | Now |
| 4 | **A drift check outside runs.** A model-free script for pre-commit or CI: spec format, links, criterion-to-test links. And a scheduled run in which a judge compares specs with the code and files what it finds | Tessl's scripts; no tool has the second part | Specs stay true between runs, where 81.5% of spec files elsewhere are never touched again | Schedules (designed) | Script now; scheduled run later |
| 5 | **Commands per repository.** The verification commands are read from the repository instead of one fixed list | Every compared tool supports many toolchains | temperspec works outside Python | A general command resolver | Needs the engine change |
| 6 | **Cheaper models where the work is mechanical, a stronger one only on evidence.** The lowest tier for mechanical phases; a step up only after a judged blocker | GSD 2's routing; Superpowers' fix rounds; the owner's ladder rule | Lower cost without lower quality, if measured | Ladders and per-phase steps (release 2) | Release 2 |
| 7 | **Property-based tests from behaviours.** A behaviour in the fixed pattern becomes a property, tested with generated inputs | Kiro | The only deterministic link from a requirement to code found in the survey | None, but one test library per language | After 1 and 2 |

**Not proposed.**

- *Delta specs* (OpenSpec): the owner chose direct edits, and archived changes pile up there.
- *Agent personas* (BMAD): they add documents, not checks.
- *Regenerating code from specs* (Tessl's first idea): not deterministic, and its authors moved away from it.
- *A knowledge file the agent appends to* (GSD 2): the engine's improvement loop does this from run records, with a trial before a change is kept.

**One piece of evidence still missing everywhere.** No published study measures whether specs still match the code after a second change to the same feature. A small trial of temperspec against OpenSpec and GSD 2 on the same tickets, with a second change, would answer the question that matters most for this design.

## 6. What each proposal needs

| Proposal | In temperspec | In the engine, stated for any workflow |
|---|---|---|
| Conversation | Triage sorts gaps and writes questions; a setting; the pull request lists defaults | A step may end with typed questions and defaults; deadline applies defaults (ask unit, release 2) |
| Small-task route | A third lane, its conditions, the guard in the code check | None |
| Per-phase coding | The plan's phases become the list | Sequential map (release 2) |
| Parallel reading | Discovery and setup split by gap or component | Parallel read-only branches (release 2) |
| Guard for parallel tasks | Outcome check compares edited specs with the base branch | None |
| Parallel phases | The plan declares independence; the check proves disjoint files | Writer branches, parallel map (release 3) |
| Criterion-to-test link, test command per criterion, pull request summary | Rule files, checks, the last stage | None |
| Commands per repository | Reads the resolver | A command resolver per repository |

## 7. Sources

The tools, studies and critiques are listed in the [comparison](sdd-tools-comparison.rsrch.md), section 11. The engine's side is in its specs for the ask unit, the map unit, flow extensions, worktree mode and workspace and concurrency, and in its decision record on the first release, which places the ask unit, parallel read-only branches and the sequential map in release 2, and writer branches, the parallel map, sub-workflows, council and contest in release 3.
