# Temperspec against other spec-driven development tools

| | |
|---|---|
| Date | 2026-11-21 |
| Asked by | The owner: compare temperspec with the well-known spec-driven development (SDD) solutions, GSD 2 included, through several different comparisons |
| Method | Four separate web research passes on 2026-11-21 (GSD and GSD 2; Spec Kit, Kiro, Tessl; OpenSpec, BMAD, Agent OS, Superpowers; independent critiques and measurements), then seven comparisons, each through a different lens |
| Confidence | Tool facts: medium to high, read from primary docs through a summarising fetcher, so quotes and figures should be checked at the source before they are repeated. temperspec facts: high for the design, **none for results: temperspec has not made a single real run** |

## 1. What this note answers

Where temperspec stands among nine tools, on what it is ahead by design, on what it is behind, and what is worth taking. Every claim about temperspec below describes what is built and checked on stand-ins. Nothing here is a measured result of temperspec.

## 2. The tools

| Tool | What it is | Delivered as | State in November 2026 |
|---|---|---|---|
| **GSD** (now GSD Core) | Prompts, agents and hooks that run a discuss, plan, execute, verify loop per phase | Installed into a coding agent (Claude Code and others) | Original repository archived June 2026 at 64k stars; continues under a new organisation |
| **GSD 2** (now GSD Pi) | The same idea rebuilt as a program that owns sessions, state, budgets and recovery | Standalone CLI on the Pi SDK, 20+ model providers | Original archived October 2026; continues under the new organisation |
| **Spec Kit** (GitHub) | Templates and commands: constitution, specify, clarify, plan, tasks, analyze, implement, converge | CLI that installs commands into 30+ agents | 145k stars, released every few days |
| **Kiro** (AWS) | Requirements in EARS, design, tasks; steering files; hooks; property-based tests | Proprietary IDE, CLI and web | Paid tiers |
| **Tessl** | Long-lived specs per module with links to tests; began as "spec as source" | CLI and registry of skills | The spec-as-source framework is still closed beta; the company moved to skills and evals |
| **OpenSpec** | Change proposals with delta specs, archived into living specs per domain | CLI that installs commands into 30+ tools | 73k stars; Thoughtworks Radar "Trial" |
| **BMAD** | Agent personas; brief, PRD, epics, stories; build and review | Installer of skills | 55k stars; v6 frozen, v7 in preview |
| **Agent OS** | Standards, product notes, and shaped specs; no implementation or verification phase since v3 | Commands for Claude Code | Little activity since January 2026 |
| **Superpowers** | Skills: brainstorm, plan, subagent per task, test first, reviewer subagent | Plugin for 16 agents | 321k stars |
| **temperspec** | A fixed workflow of gated steps run by an engine: setup when needed, triage, discovery, plan, expand, code, outcome gate, draft pull request | A workflow package of tempergraph, run by `tempergraph run` | Built; model-free checks pass; no real run yet |

Sources for each tool are in §11.

## 3. Comparison 1: how long a spec lives

Birgitta Böckeler's three kinds are the vocabulary reviewers use: **spec-first** (written before the task, then left), **spec-anchored** (kept and changed with the code), **spec-as-source** (people edit only the spec). She found the tools she tried were spec-first in practice.

| Tool | Kind in practice | How an existing spec changes | What catches a spec that no longer matches the code |
|---|---|---|---|
| Spec Kit | Spec-first; a folder per feature. The docs name three ways to keep specs and say none is the default | Team convention | `/converge` (model, same agent) |
| Kiro | Spec-first; a folder per feature | Edit requirements, ask for design update, "Sync Files" | Property-based tests (IDE only) |
| OpenSpec | Spec-anchored | Delta files (ADDED, MODIFIED, REMOVED) merged at archive | Nothing mechanical; `verify` is advisory and does not block |
| Tessl | Spec-anchored, aiming at spec-as-source | Direct edit | Scripts check that linked tests and target files exist |
| BMAD | Ticket documents per level; finished ones are not rewritten | A new story | Not addressed |
| GSD, GSD 2 | Project and roadmap files persist; plans are per phase | Roadmap is reassessed | A drift gate on the codebase map only |
| Agent OS, Superpowers | Per-change documents | None | None |
| **temperspec** | **Spec-anchored**: one living spec per capability | **Direct edit**, with a check that fails an edit to a spec in which no behaviour or acceptance criterion changed | The code gate: a check passes the changed paths and related specs to a judge that must find the code aligned, by meaning, with the edited and the related specs; the outcome gate judges agreement between specs |

**Reading.** Only OpenSpec, Tessl and temperspec keep a spec per capability. OpenSpec's deltas make a change easy to review, at the price of a merge step and of archived changes piling up: a study of repositories found 19,067 archived changes against 6,644 capability specs. temperspec chose direct edits and guards them with a collateral-edit check. The same study found 81.5% of spec files are never touched after their first commit, which is the failure temperspec's alignment judge exists to prevent. Whether it does is unmeasured.

## 4. Comparison 2: what a spec looks like and what it costs to read

| Tool | Requirement form | Typical volume reported |
|---|---|---|
| Spec Kit | User stories, Given/When/Then, `FR-001: System MUST`, success criteria; plus plan, research, data model, contracts, tasks, checklists | 8 files and about 1,300 lines for a date display; 2,577 lines of markdown for 689 lines of code |
| Kiro | EARS: `WHEN … THE SYSTEM SHALL …`, with design and tasks files | A small bug fix became 4 user stories and 16 acceptance criteria |
| OpenSpec | `### Requirement:` with SHALL, then `#### Scenario:` with GIVEN/WHEN/THEN | 93 spec lines per ticket in one vendor benchmark, the lowest of four |
| BMAD | PRD, epics, stories | 188 spec lines per ticket in the same benchmark, the highest |
| GSD | Requirements with ids; plans as XML tasks with `verify` and `done` | "An insane amount of files" (user report) |
| Superpowers | No requirement syntax; acceptance is the tests in the plan | Not reported |
| **temperspec** | Purpose, **Behaviours** in one fixed pattern (`WHEN … THE … SHALL …` with a GIVEN/WHEN/THEN example), **Acceptance criteria**. No version, status or change log. At most 400 lines; a behaviour names only what someone outside depends on | Not measured |

**Reading.** temperspec's format is closest to Kiro's and OpenSpec's, and is stricter than both on what may not be in a spec. That answers the most repeated criticism, markdown volume, by rule rather than by habit. It also writes more kinds of file than OpenSpec does: a triage note, specs, decision records, research notes, a plan and a code report. Only the specs and records are meant to be read by a person; the rest are hand-overs between steps. This needs a number from real runs before it can be claimed as an advantage.

## 5. Comparison 3: who decides the work is done

This is the lens on which the tools differ most.

| Tool | Deterministic checks | Model review | Is the reviewer separate from the builder? | Can a failed check block? |
|---|---|---|---|---|
| Spec Kit | None documented | `/analyze`, `/checklist`, `/converge` | No, same agent | Converge appends tasks; a person loops |
| Kiro | Property-based tests derived from requirements; hooks | Analyze Requirements | Not stated | A failing property offers a fix |
| OpenSpec | `validate` (structure of specs only) | `/opsx:verify` | No | No: verify "does not block archive" |
| Tessl | Scripts for structure and links, then linked tests | Verification and review skills | No | Not stated |
| BMAD | None documented | Self-review in the build, optional review in a fresh chat, retrospective | Fresh chat | Review leaves the status unchanged |
| GSD | Per-task verify commands; a test mapped to each requirement before coding | Plan checker (3 rounds); a verifier subagent told to distrust the builder's summary; human acceptance test | Own context, same model family | Retry, decompose or prune, budget 2 |
| GSD 2 | Host-run verification commands after each task; "no host-run check is never a pass" | Milestone validation | No task-level verifier documented | Retry twice, then pause |
| Superpowers | Tests, written first | Reviewer subagent per task; final review on the strongest model | Yes, fresh subagent | Fix loop up to 5 rounds |
| Agent OS | None | None | | |
| **temperspec** | A model-free check on **every** step, before any judge; the workflow's verification commands are run by the check, not reported by the step | A read-only judge on every step and at the end, with criteria fixed in advance and each "met" needing evidence | Yes: a separate session with no write tools, and the verdict is derived by rule from its rows | Yes: fail retries the step; a defect written earlier sends the run **back to that step** by itself |

**Reading.** temperspec's design is the strictest here, and three points are not found together in any other tool: the check runs before the judge on every step including the document steps, the judge cannot write, and the gate can name an earlier step as the place of the defect and return there. GSD's verifier and Superpowers' reviewer are the nearest equivalents. Evidence supports the direction: agents exploit tests when they can (ImpossibleBench: models passed conflicting tasks mostly by editing tests), a first review found a blocking issue in 15 of 20 artifacts in one gated-workflow study, and judges are useful but noisy. That last point is also the risk: temperspec leans on judges whose 32 test cases have not yet been graded once.

Two things others have that temperspec lacks: Kiro's property-based tests, and a test-first loop with a commit per task (Superpowers, GSD). temperspec asks for tests first inside one coding session and commits once per step.

## 6. Comparison 4: who is in control of the run

| Tool | What drives the steps | Person's stops | Crash recovery, timeouts |
|---|---|---|---|
| Spec Kit, OpenSpec, Agent OS | A person runs each command | Between every phase | None |
| Kiro | The product | Between phases; "Run all tasks" then goes alone | Product-managed |
| BMAD | Skills; an unattended build takes one story per run | Plan approval; only a person marks a story done | Not documented |
| GSD | The model follows prompts; auto-advance and autonomous modes | Roadmap, discussion, acceptance test | Pause and resume files; no automatic recovery |
| Superpowers | A controller agent with subagents | Design, go, final merge | Ledger file |
| GSD 2 | **A program**: state machine, a fresh session per task, state in a database | Initial discussion; escalations | Yes: recovery, stuck guard, soft, idle and hard timeouts |
| **temperspec** | **A program**: the tempergraph engine runs each step as a fresh session with stated tools, a time limit and a retry budget | **None by default**; the run ends in a draft pull request | Yes, from the engine: resume, time limits, waiting list |

**Reading.** GSD 2's authors rebuilt GSD for the reason tempergraph exists. In their words the first version "was fighting the tool … hoping the LLM would follow instructions, with no actual control over context windows, sessions, or execution". temperspec and GSD 2 are the only two here in which code, not a prompt, decides what runs next. The difference is what the program enforces: GSD 2 enforces sessions, budgets and recovery; temperspec enforces gates.

temperspec is behind on the human side. Every other tool has a way to ask the person questions before the spec is written (Spec Kit's clarify, GSD's discuss, Superpowers' brainstorm, Kiro's inline review). temperspec takes a task with its acceptance criteria as given, and a gap becomes a discovery step, not a question. A user of GSD 2 complained that auto mode "moves too fast for the discussion to meaningfully shape anything"; temperspec is exposed to the same complaint.

## 7. Comparison 5: cost, context and measuring itself

| Tool | Fresh context per unit | Model per step | Parallel work | Cost tracking | Measures its own quality |
|---|---|---|---|---|---|
| Spec Kit, OpenSpec, Agent OS | No | No | No | No | No |
| Kiro | Steering inclusion modes | Auto routing | Tasks in waves | Credits | No |
| BMAD | Fresh chat per build | No | No | No | Retrospective per epic |
| GSD | Subagent per plan | Profiles per role | Waves, worktrees | Estimate only | Learnings file |
| GSD 2 | Session per task | Per phase, routing by complexity, downgrade under budget | Milestones and slices | Ledger in USD with a ceiling | Tier success history |
| Superpowers | Subagent per task | Cheap, standard, strongest by task | No | No | Public eval suite run by the author |
| Tessl | Tiles | Eval flag | No | Credits | Evals with and without the context |
| **temperspec** | Session per step | Fixed per step: middle tier everywhere, highest effort for discovery, no top tier | **None** | Per run, with a cost cap, from the engine | Judge test cases with a pass bar; the engine's self-improvement loop proposes and trials changes from run records |

**Measured overhead of others.** Spec Kit: about ten times slower than iterative prompting for one feature, with no quality gain (Scott Logic). A vendor benchmark of 50 existing-code tickets: a merge rate of 72% without specs and 80 to 84% with them, median time 29 minutes against 36 to 55, and 28 to 44% of tokens spent in the spec phase; gains appeared only on features and changes touching three or more files, not on bug fixes. GSD: users report ten times the tokens. GSD 2: one test spent 27 USD against a 20 USD ceiling and 90 minutes against 5. A study of 88,000 pull requests found no defect reduction from linked specification artifacts.

**Reading.** temperspec's routes are its answer to the "one heavy workflow for every task" criticism: a task with no gap skips discovery, and a simple plan skips the expand step. It has no route for a task too small to deserve the workflow at all, which is where the benchmark says specs do not pay. It has no parallel work and one coding session, so a large change will be slower than in GSD or Kiro. On self-measurement the design goes further than any tool here, since the judges themselves are tested and the loop is in the engine, but GSD 2's cost ledger and tier routing run today and temperspec's loop has not.

## 8. Comparison 6: existing code and git

| Tool | Onboarding an existing repository | Git |
|---|---|---|
| Spec Kit | A guide; one team spent 2 to 3 days on the constitution of a large codebase | Optional branch per feature |
| Kiro | Generates three steering files | Web version opens pull requests |
| OpenSpec | `onboard` scans the code; deltas suit existing specs | Not covered |
| BMAD | Writes a project context block | One commit per build; branch per epic |
| GSD | Parallel mapper agents write a codebase folder | Commit per task; worktrees; pull request through `gh` |
| GSD 2 | Codebase map injected; scout agent | Worktree or branch; squash merge; optional pull request |
| Superpowers | Optional reconnaissance | Worktree, commit per task, merge or pull request |
| **temperspec** | A model-free probe at the start of every run; without an overview spec, a gated `setup` step writes the overview and one spec per component from the code, and the temperspec note goes into `CLAUDE.md` | The engine commits after every step; the run's own branch; a draft pull request at the end |

**Reading.** temperspec is the only one that writes behaviour specs of the existing system as its onboarding and gates them. The others write context for the agent (steering, standards, a map). That is more valuable if the specs are right and more expensive if they are not, and it is untested on a real repository. The engine has worktrees; temperspec does not yet use parallel ones.

## 9. Comparison 7: against the ten recurring criticisms

The criticisms are those that independent reviewers repeat (§11).

| # | Criticism | temperspec by design | Open |
|---|---|---|---|
| 1 | Markdown volume and review burden | Three-section spec, 400-line cap, no change log, collateral-edit check | Hand-over files are not counted yet |
| 2 | One heavy workflow whatever the task | Routes on gaps and on complexity; a docs-only run | No route for a trivial fix |
| 3 | Waterfall | A gate sends the run back to the step where the defect was written | Still plans before it codes, by intent |
| 4 | Agents do not follow the spec | Read-only judge checks code against edited and related specs; checks run the commands themselves | Judges uncalibrated |
| 5 | Specs decay, nothing fails | Living specs; the alignment and agreement criteria fail the run | Agreement between specs is judged only (the package's decision record `ts-spec-sync`) |
| 6 | Blind to existing code | Setup step; triage must search before it claims a gap | Untested |
| 7 | Cost without proven gain | Middle tier only; skipped steps; cost cap | No measurement at all |
| 8 | Implementation detail in specs | Behaviours name only what an outsider depends on | Enforced by a judge, not a check |
| 9 | Unclear audience | Specs are for the owner; hand-overs are for the next step | |
| 10 | Spec-as-source is not deterministic | Not attempted: code is written and tested, never regenerated | |

## 10. Conclusions

**Where temperspec is ahead by design**

1. **Gates that hold.** A check before a judge on every step, a judge that cannot write, verdicts by rule, and a return to the faulty step. OpenSpec's verify does not block, Spec Kit's is the same agent, GSD 2 has no task-level reviewer.
2. **Living specs with a guard against decay**, in a short fixed format. Only OpenSpec and Tessl are in the same group.
3. **A program in control**, shared only with GSD 2, on an engine that also serves workflows that are not about code.
4. **Its own trust is measured**: judge test cases and a loop that improves the workflow from run records.

**Where it is behind**

1. **No evidence.** Every other tool has users and several have measurements. temperspec has no run. This outweighs everything above until rows TS-L1 and TS-L2 of the [live checks](../plans/live-checks.plan.md) are done.
2. **No conversation with the person** before the specs are written.
3. **No parallel work and one coding session**, where GSD, GSD 2, Kiro and Superpowers split work into tasks with a fresh context each.
4. **One executor and one fixed toolchain** (Claude Code; pytest, ruff, mypy), against 16 to 30 agents for the popular tools.
5. **No small-task path.**
6. **Agreement between specs rests on a judge alone.**

**What is worth taking**

| From | Idea | Why | Where it would land |
|---|---|---|---|
| GSD | Map each acceptance criterion to an automated test command before coding | Makes "done" checkable without a judge | temperspec: the plan check |
| Kiro | Property-based tests derived from behaviours written in the fixed pattern | The only deterministic link from a requirement to code found in this survey | temperspec: an optional kind of test row |
| Tessl | A link from each acceptance criterion to its test, checked by a script | Turns "specs and code agree" partly into a check, which the package's decision record `ts-spec-sync` leaves to a judge | temperspec: the spec rule and the code check |
| Superpowers, GSD | A fresh session and a commit per task, with a review per task | Smaller contexts; the owner already asked for a commit per phase | Waits for the engine's sequential map |
| GSD 2 | Model routing by measured success per tier | Matches the owner's wish to move phases to a cheaper tier later | The engine's ladder work, as a general capability |
| Superpowers | A stronger model only after repeated failed fix rounds | The same rule the owner set for ladders | The engine's ladder work |
| Spec Kit, GSD | A short clarify step that asks the person only when triage finds an open decision | Answers the "moves too fast" complaint without a pause on every run | temperspec: an optional question from triage |
| Vendor benchmark | Skip the workflow for bug fixes and changes under three files | Specs did not pay there | temperspec: a triage route |
| OpenSpec | Nothing on deltas | The owner chose direct edits; the archive pile-up supports that | |

**The comparison to run next.** A like-for-like trial is the only way to settle the open column: the same five to ten tickets in one repository through temperspec, OpenSpec and GSD 2, recording time, cost, lines of markdown a person must read, defects found in review, and whether the specs still match the code after a second change to the same feature. No published study measures that last point.

## 11. Sources

All read on 2026-11-21. Items marked (v) come from a vendor or a competitor and are weighted accordingly.

**Tools**
- GSD: <https://github.com/gsd-build/get-shit-done>, <https://github.com/open-gsd/gsd-core>
- GSD 2: <https://github.com/gsd-build/gsd-2>, <https://github.com/open-gsd/gsd-pi>
- Spec Kit: <https://github.com/github/spec-kit>, <https://github.github.io/spec-kit/reference/agentic-sdd.html>
- Kiro: <https://kiro.dev/docs/specs/>, <https://kiro.dev/docs/specs/correctness/>
- Tessl: <https://docs.tessl.io/>, <https://tessl.io/registry/tessl-labs/spec-driven-development>
- OpenSpec: <https://github.com/Fission-AI/OpenSpec>
- BMAD: <https://github.com/bmad-code-org/BMAD-METHOD>, <https://docs.bmad-method.org/start/how-bmad-works/>
- Agent OS: <https://github.com/buildermethods/agent-os>
- Superpowers: <https://github.com/obra/superpowers>, <https://blog.fsck.com/2026/06/15/Superpowers-6/>

**Critiques and comparisons**
- Böckeler, "Understanding Spec-Driven-Development: Kiro, spec-kit, and Tessl", October 2025: <https://www.martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html>
- Thoughtworks Technology Radar, spec-driven development: <https://www.thoughtworks.com/radar/techniques/spec-driven-development>; OpenSpec: <https://www.thoughtworks.com/en-gb/radar/tools/openspec>
- Eberhardt (Scott Logic), "Putting Spec Kit Through Its Paces", November 2025: <https://blog.scottlogic.com/2025/11/26/putting-spec-kit-through-its-paces-radical-idea-or-reinvented-waterfall.html>
- Zaninotto (Marmelab), "The Waterfall Strikes Back", November 2025: <https://marmelab.com/blog/2025/11/12/spec-driven-development-waterfall-strikes-back.html>
- Uvik benchmark of 50 tickets (v): <https://uvik.net/?p=7598>
- User reports on GSD: <https://hn.nuxt.dev/item/47417804>; on GSD 2 (v): <https://chaseai.io/blog/gsd2-vs-claude-code-which-ai-coding-tool-wins>, <https://github.com/gsd-build/gsd-2/discussions/3333>

**Studies**
- Agarwal et al., "SDD as Prescribed and as Practiced", 2026: <https://arxiv.org/pdf/2608.25202>
- Hill, specification artifacts and defects, ESEM 2026: <https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ESEM.2026.84>
- Taghavi and Bhavani, "Spec Kit Agents", 2026: <https://arxiv.org/pdf/2604.05278>
- Abdo and Brom, "A Gated Spec-Driven Workflow", 2026: <https://arxiv.org/pdf/2611.05094>
- Zhong, Raghunathan, Carlini, "ImpossibleBench", 2025: <https://arxiv.org/pdf/2510.20270v1>
- Peng et al., on judges verifying rubrics in agentic work, 2026: <https://arxiv.org/abs/2606.29920>

**Not found or not verified:** a study of EARS-style requirements with language models; any hands-on measurement of GSD or GSD 2 beyond single user reports; why the GSD projects moved to a new organisation; the current state of BMAD v7.
