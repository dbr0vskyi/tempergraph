# Temperspec as the first workflow authored with tempergraph

## Problem statement

The owner asked on 2026-11-20 whether the project is ready to create its first real workflow, then asked for research on how to create temperspec, with the details to be discussed, and added: "But I want you to run through tempergraph."

That sentence is read as: temperspec is produced by tempergraph's own authoring path (an authoring session, the outcome file, the blueprint, `scaffold`, `author verify`), as a workflow package named `temperspec-tgraph` ([ADR `a-workflow-plugin-name-is-the-workflow-name-plus-tgraph`](../adr/a-workflow-plugin-name-is-the-workflow-name-plus-tgraph.adr.md)), and then runs on the engine. It is not hand-built beside the engine. A second reading, "run temperspec's tasks through the engine once it exists", follows from the first and needs no separate plan.

This note answers:

1. What is temperspec's pipeline, in the terms the engine uses?
2. How does each part map onto what release 1 has on `main` (code, not only specs)?
3. What does not fit release 1, and does a useful first version fit without engine work?
4. What good outcome should it be authored against, and who verifies each criterion?
5. One workflow or several?
6. How does the authoring path run for it, and what must wait for a live `claude`?
7. Which choices are the owner's?

This is research for a discussion. Nothing is scaffolded and no spec, decision record or code changes with it. It builds on [research `temperspec-needs-against-the-engine`](temperspec-needs-against-the-engine.rsrch.md), which checked the engine **design** against temperspec's needs; this note re-checks those rows against the **code** and the release boundary of [ADR `first-release-is-simple-trusted-workflows-on-one-machine`](../adr/first-release-is-simple-trusted-workflows-on-one-machine.adr.md).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S2 | research `temperspec-needs-against-the-engine`, the coverage check of the design | Research note | [research `temperspec-needs-against-the-engine`](temperspec-needs-against-the-engine.rsrch.md) |
| S3 | Release 1 plan: feature list I-1 to I-94, exclusions X2 and X3 | Plan | [first-release.plan.md](../plans/first-release.plan.md) §1.3 |
| S4 | Authoring, outcome, package and scaffold specs | Specs | [AUT](../specs/workflow-authoring.spec.md), [OUT](../specs/run-outcome.spec.md), [PKG](../specs/workflow-package.spec.md), [SCF](../specs/blueprint-and-scaffold.spec.md) |
| S5 | Engine code on `main` at `26096be`: `api.py`, `model/validate.py`, `run/nodes.py`, `run/gate.py`, `run/checks.py`, `run/finalize.py`, `render/output.py`, `executors/capabilities.py`, `executors/binding.py`, `cli/author.py` | Code, read not run | [engine/src/tempergraph](../../engine/src/tempergraph/) |
| S6 | The two example packages | Code | [doc-refresh-tgraph](../../../doc-refresh-tgraph/), [release-notes-tgraph](../../../release-notes-tgraph/) |
| S7 | research `effort-ladders-and-one-step-model-escalation` on effort ladders and model escalation | Research note | [research `effort-ladders-and-one-step-model-escalation`](effort-ladders-and-one-step-model-escalation.rsrch.md) |
| S8 | Pending live checks | Plan | [live-checks.plan.md](../plans/live-checks.plan.md) |

## Key findings

### F1 temperspec's pipeline `confirmed`

| Step | Tier | Produces | Check (model-free) | Judge | When spent | Back to |
|---|---|---|---|---|---|---|
| triage | Sonnet | Triage note; values: gap list, route, story line, task detail | Note sections, one-line gap list, route follows gaps, existing plans named | Sonnet, 5 blockers and 3 warnings | stop | none |
| discovery (skipped when no gaps) | Opus, survey on a cheaper subagent | Research notes, decision records, specs, hand-off | Hand-off links, gap rows point to files, record numbering, spec sizes | Sonnet, 9 blockers | stop | none |
| plan (design pass) | Opus | Plan skeleton: Section 0, requirements, phases, track map | Section 0 parts, skeleton shape, track map, release mark | Sonnet, 4 blockers | ask | discovery |
| expand (expansion pass) | Sonnet | Task rows, reading sets, runnable verification, phase list | Task quality, test-first order, reading sets, verification commands, no anchor left | Sonnet, 6 blockers and 1 warning | ask | plan, discovery |
| phase × N (sequential map) | Sonnet, low effort | One commit per plan phase | Rows marked, committed on previous head, clean tree, nothing pushed; runs no command | Sonnet, 2 blockers | ask, per item | none |
| code (the join) | Sonnet | Whole change, final report, tests-passed value | Cheap checks, then the gate runs the plan's verification commands itself | **Opus**, 6 blockers and 4 warnings | ask | plan, discovery |
| release (skipped when no release track) | Haiku | Version bumps, changelog, status marks | Release rows marked, commit past the code gate's, release commands | Sonnet, 3 blockers | ask | code |
| final stage | no model | Pushed branch, draft pull request | — | — | never raises | — |

Around the steps the method defines **43 judged criteria**, **48 labelled calibration cases**, **3 agents**, **17 skills** and **6 rule files plus a machine-readable spec rules file**. The rule files are where the method's artifact formats live, one home per artifact: the plan rule, spec rule, decision rule, documentation rule, workflow orientation and the story template. The owner's naming rule (`*.spec.md`, `*.adr.md`, `*.plan.md`, `*.rsrch.md`, [ADR `artifact-type-suffixes`](../adr/artifact-type-suffixes.adr.md)) belongs in those rules once temperspec owns them ([ADR `the-workflow-docs-set-is-provisional-until-temperspec-owns-it`](../adr/the-workflow-docs-set-is-provisional-until-temperspec-owns-it.adr.md)).

A person is asked only when a budget is spent on plan, expand, phase, code or release, when a step ends blocked, when every blocker needs no change or a person's ruling, or on an environment mark. An approval pause after a chosen step is opt-in.

### F2 The method fixes temperspec's structure, not its text `inferred`

The method fixes every artifact's structure, each gate's check list, criteria **counts** and themes, and the rules each rule file enforces. It does **not** fix the prompt texts, the 43 criteria's wording, the 48 calibration cases, the rule files or the skills' text. Those have to be written.

Consequences:

- The authoring entry path is `sources`, not `solution` ([AUT-B13](../specs/workflow-authoring.spec.md)): the inventory finds checklists and rules, not a runnable thing.
- The nearest thing to a working rule set is this repository's own docs set. [docs/README.md](../README.md) already states file naming, spec and decision-record form, and the plans follow the method's plan shape (Section 0, requirements, tracks). It is the best source for intake.
- Criteria wording is the owner's call during the interview. The method's themes are candidates, not confirmed criteria; the authoring skill never invents a rubric the person did not confirm ([AUT-B16, AUT-B17, AUT-B18](../specs/workflow-authoring.spec.md)).

### F3 research `temperspec-needs-against-the-engine`'s rows against the code and the release boundary `confirmed` (code read, not run)

research `temperspec-needs-against-the-engine` found 17 gap rows and closed them in specs `check-contract-and-command-runs`, `step-values-and-template-keys`, `map-unit`, `finalizer-contract` and `measured-switches` and ADRs `checks-get-a-context-and-an-engine-command-runner`, `claims-may-target-a-route-skipped-back-target`, `a-step-previews-its-own-check-in-the-attempt`, `skills-are-a-declared-tool-capability` and `switches-are-measured-before-they-route`. Their state on `main`:

| research `temperspec-needs-against-the-engine` gap | Closed by | In release 1 code? | Evidence |
|---|---|---|---|
| Check context, findings, facts, `n_a`, mechanical criteria (T19, T24, T29 to T31) | CHK | **Yes** | `run/checks.py` `CheckContext` (artifacts, values, facts, git, settings, criteria); `contracts.py` `CheckResult.facts`, `Criterion.mechanical` |
| Check runs commands with a budget, tree kill, reuse (T25, T26) | CHK-B12, CHK-B13 | **Yes** | `CheckContext.resolve`, `.run(reuse=…)`, `run/commands.py` |
| Run values and template keys (T13, T14) | VAL | **Yes**, without item keys | `api.Value`; used by `doc-refresh` for its route |
| Finalizer contract, outcomes, URL (T51 to T53) | FIN | **Yes** | `run/finalize.py` `FinalizerContext` with `resolve` and `run`, `open_warnings`, `run_options` |
| Skill as a declared tool (T11) | ADR `skills-are-a-declared-tool-capability` | **Yes, coarse** | `executors/capabilities.py`: `skill:*` maps to the bare `Skill` tool; a per-skill allow rule waits on probe P-CC-8 |
| Subagent model (T12), workflow settings (T27, T54), lasting rulings (T49) | RST, RRN | **Yes** | `api.Step(subagent_model=…)`, `api.Setting`, I-34 to I-36 |
| Claims against a route-skipped target (T17, T35) | ADR `claims-may-target-a-route-skipped-back-target` | **Partly** | See F4 |
| Sequential map over plan phases (T43, T44, T50) | MAP | **No**, release 2 (X2-15) | `api.Map` is refused with `not_in_release` |
| Code-mode router: shadow mode, arm overrides (T46) | SWM | **No**, release 2 (X2-16) | Only a plain switch with `--arm` |
| A step previews its own check (T38) | ADR `a-step-previews-its-own-check-in-the-attempt` | **No**, release 2 (X2-18) | `self_check` is refused |
| Judge reads the tracker through a remote server (T37) | GRD, ECC | **No**, release 2 (X2-20) | `judge_mcp = false`; the judge marks the quote unverifiable, which is also the method's default |

Everything research `temperspec-needs-against-the-engine` marked covered that temperspec's line needs is in the release 1 feature list: steps, routes from a step, back targets with loop budgets, approval, budgets by cause, the independent judge, worktree per run, effort per step, model aliases (`small`, `medium`, `large` bind to Haiku, Sonnet, Opus on `claude`), package skills on step sessions through `--plugin-dir`.

### F4 An upstream claim pauses for a person; it does not send the run back `confirmed` (code read)

In the method a step's upstream claim ("the plan conflicts with the tooling") sends the run back by itself, once per edge. In the code:

- `render/output.py` accepts `UPSTREAM <unit>:` for any unit in the gate's `back_targets`. It does not check that the target ran or was route-skipped, so it is more permissive than [PRM-B11](../specs/prompt-rendering.spec.md).
- `run/nodes.py` turns an accepted claim into `escalate = "upstream"`, and `run/gate.py` sends every escalation cause to a person. No judge confirms the claim and no automatic trip back follows.
- A **judge's** attribution (`back_to`) does route back automatically within the loop budget (`run/gate.py`).

So trips back driven by the judge work as in the method; trips back driven by a step's own claim cost one pause, where the person picks `back`. That is safe and usable for a first version, but it is a difference from the method and from what [HUM-B7 to HUM-B11](../specs/gate-and-human.spec.md) implies ("an upstream claim the judge could not confirm" escalates). It should be either built or recorded as release 1 behaviour in the spec. This is a small engine item, not a blocker.

**Since fixed (2026-11-21, on the owner's ruling to reduce pauses):** a claim is now judged on its own against one criterion; confirmed goes back, refuted retries the step, undecided asks a person ([JDG-B9](../specs/judge-and-verdict.spec.md)).

### F5 The outcome gate adds a grader the method does not have `confirmed`

Every authored workflow gets a final `outcome` unit before the finalizer, judged by default on the strongest model any step judge uses ([OUT-B15, OUT-B16, OUT-B17](../specs/run-outcome.spec.md)). For temperspec that is a second Opus read of the change, right after the Opus code judge. The method's rule is that no criterion is judged twice. The outcome file therefore has to split the work: final criteria are mostly `check`, and the one judged final criterion is taken out of the code gate rather than repeated in it (see the proposed outcome).

### F6 What needs a live `claude` `confirmed`

Release 1 has never run against a live Claude Code session, and the owner cannot run live checks for about two more days (S8). For temperspec that splits the work:

| Model-free, possible now | Needs a live `claude`, stays pending |
|---|---|
| `author start`, `author intake`, drafting `outcome.json` and `blueprint.json`, `author check`, `author approve`, `blueprint draw`, `scaffold` | `author verify --judge-seeds` (rung 8: each judged criterion's seeds graded twice) |
| Writing prompts, judge briefs, checks, rule files, skills | `author verify --trial` (rung 9: one capped, consented run the person grades) |
| `author verify` rungs 1 to 7, the generated tests, offline flow tests on stand-ins, `audit`, prompt lint | Judge calibration scores, any real task run |
| | The live probes temperspec leans on: P-CC-8 (per-skill allow rule), P-CC-9 (plugin content on step sessions), the worktree probe |

The interview itself is led by the `tempergraph:author` skill in a Claude Code session. That is an ordinary conversation, not an engine run, so it does not wait for the live checks.

## Analysis

### A first version that fits release 1

The method already has the mode that fits: the **single-session code mode**, which leaves the phase fork out and runs the code step once for the whole plan. On small plans it is also the cheaper mode: one session reads the plan and the code once, where per-phase code reads them again in every phase.

| Part of the method | First version on release 1 | Loses |
|---|---|---|
| triage, discovery, plan, expand, their gates and routes | As in the method | Nothing |
| phase × N and its narrow judge | Left out; `code` builds the whole plan in one session | A failed phase reruns the whole code step; large plans cost more. The phase gate's two criteria move into the code gate |
| code gate running the plan's commands | As in the method, through `ctx.resolve` and `ctx.run` with reuse | Nothing |
| release step and route | As in the method, or deferred (owner's choice, Q4) | — |
| final stage | A finalizer: push, open or reuse a draft pull request, never raise | Nothing; tested against a local bare remote until a live run |
| Expand previewing its own check | Not available; a failed expand check costs a new attempt | The saving a preview would bring |
| Code-mode router | Not available and not needed without the map | Nothing yet |
| Triage judge reading the tracker | Unverifiable path, as the method's default | Nothing against the method's default |
| Upstream claims | One pause per claim (F4) | An automatic trip back |
| 17 skills and 3 agents | Only the skills a step declares as a tool (codebase discovery, spec authoring, decision records, test fixing) and the bootstrap | The interactive twins; they add nothing to a headless run |
| 48 calibration cases | The seeds `author verify` requires: at least one met and one unmet or partial per judged criterion | Calibration depth; grows from real runs and labels |

**Conclusion: a useful first temperspec fits inside release 1 with no engine work first.** The sequential map is the only large piece missing, and its saving on small plans is unconfirmed. Release 2's map then adds per-phase code as a change to an existing, measured workflow, which is what the self-improvement loop is for.

### Proposed good outcome (draft for the interview, not confirmed)

Statement: *the task's acceptance criteria are met by tested code on the run's own branch, built from a plan that traces to a spec, and offered as a draft pull request.*

Deliverables: the triage note, the plan, the code result (branch head and final report), and the pull request URL (reported by the finalizer, so it is not a gate criterion).

Final criteria, graded at the outcome gate:

| Id | Criterion | Severity | Verified by |
|---|---|---|---|
| ts-verify | Every verification command the plan lists exits 0 on the branch head | blocker | check (reuses the code gate's run on an unchanged tree) |
| ts-committed | Every plan row is marked, the work is committed, the tree is clean and the branch is not on a remote | blocker | check (git facts) |
| ts-traced | Each acceptance criterion in the triage note is named by at least one plan requirement and at least one test row | blocker | check (the plan's own tables) |
| ts-accepted | Each acceptance criterion of the task is achieved by the change, with the file and test that show it | blocker | judge, strongest tier; **moved out of the code gate** so it is judged once (F5) |
| ts-docs | Each spec or decision record the change makes false is updated in the same branch | warning | judge |
| ts-review | A person accepts the draft pull request | — | none at the gate; read later from the pull request's merged or closed state |

Intermediate outcomes, each serving the final criteria above:

| Unit | Outcome | Check | Judge |
|---|---|---|---|
| triage | The note states the acceptance criteria, the owner of the change, the gaps and a route that follows them | Sections, one-line gap list, route equals gaps | Facts match the task; owner; gaps; existing plans found (Sonnet) |
| discovery | Every gap is closed by a research note, decision record or spec, with a hand-off | Links resolve, gap rows point to files, numbering, file names carry their type suffix | Gap coverage, no scope creep, behavioural specs, research from sources (Sonnet) |
| plan | The skeleton traces every acceptance criterion to requirements and phases and matches the specs | Section 0 parts, shape, track map | Traceable requirements, spec match, goal alignment (Sonnet) |
| expand | Every phase has task rows, reading sets and runnable verification | Row quality, test-first order, reading sets exist, commands resolve | Rows implement the design, tests assert what rows say (Sonnet) |
| code | The whole plan is built test first and committed | Rows marked, committed, not pushed, then the plan's commands | Each row's change is where it says; scenarios covered by asserting tests; nothing beyond the plan (large tier) |
| release | Release rows are done and truthful | Rows marked, commit past the code gate's, release commands | Changelog truthful, nothing else changed (Sonnet) |

Trust at the start: every judged criterion is `uncalibrated` until its seeds are graded live, and the outcome record shows that rather than hiding it ([OUT-B13, OUT-B14](../specs/run-outcome.spec.md)).

### Models and effort

The method's tiers map directly: triage and expand `medium`, discovery and plan `large`, release `small`, judges `medium` except the code judge `large`. Release 1 has one effort per step and a model ladder on retries; the effort ladder and the one-step escalation of research `effort-ladders-and-one-step-model-escalation` are research only and unmeasured on this engine (research `effort-ladders-and-one-step-model-escalation` conclusion 7). Proposal: start with the method's fixed tiers and no ladder, so the first runs give a clean baseline that research `effort-ladders-and-one-step-model-escalation`'s ideas can later be trialled against.

### One workflow or several

Release 1 has no sub-workflows (X3-7) and no orchestrator (X3-1), so "several" would mean separate workflows a person chains by hand. That breaks the two things the method's value rests on: trips back across steps, which cannot cross a workflow boundary, and files handing over inside one run. **Recommendation: one workflow, `temperspec`, in one package.** Repository setup (vendoring the rule files) stays a skill in the same package. A split into composed workflows is worth revisiting when sub-workflows exist.

### How the authoring path would run

1. `author start temperspec --from sources plugins/tempergraph/docs/README.md` and intake (model-free; sources are read, never edited).
2. Interview phases 2 to 6 with the owner: final outcome, working backwards, verifications, steps' work, start and routing. The drafts above are the starting point; three questions a turn at most.
3. Phase 7: the owner approves the engine-drawn blueprint with the outcome and verification tables. Nothing is written to the package before this.
4. `scaffold` into `plugins/temperspec-tgraph/`, then the content: prompts, judge briefs, checks, rule files, the four tool skills, the finalizer, seeds and fixtures. The marketplace catalog gets the plugin.
5. `author verify` rungs 1 to 7 and offline flow tests on stand-ins.
6. Pending the owner's machine: rung 8 (judge seeds), rung 9 (the trial), then the first real task.

Risks to name early: the content volume (seven prompts, seven judge briefs, about 40 criteria with scales and seeds, six rule files) is the bulk of the work and most of it is wording only the owner can confirm; and temperspec will be the first workflow to exercise routes, back edges, command-running checks and the finalizer together on a live session, so its first trial doubles as the engine's hardest live check.

## Conclusions

1. temperspec is seven gated steps, two skip routes, a per-phase map with a join, five once-only trips back and a model-free publishing stage, backed by 43 criteria, rule files and skills. The method fixes their structure; their text must be written.
2. Release 1 on `main` covers the whole line except the sequential map, measured switches, the in-attempt check preview and tracker access for judges, all release 2.
3. A first version fits release 1 with no engine work, by using the method's own single-session code mode.
4. One engine difference surfaced: a step's upstream claim pauses for a person instead of sending the run back (F4). Decide whether to build it or record it.
5. The outcome gate would judge the change twice unless the final judged criterion is moved out of the code gate (F5).
6. Recommended shape: one workflow in `temperspec-tgraph`, authored from `sources`, fixed model tiers as in the method.
7. Authoring up to and including `author verify` rungs 1 to 7 is model-free and can proceed now; judge seeds, the trial and any real run wait for the owner's machine and are never faked.

## Open questions

| # | Question | Owner |
|---|---|---|
| Q1 | Is the reading right: temperspec is authored through tempergraph's authoring path, as `temperspec-tgraph`? | Owner |
| Q2 | First version without per-phase code (single-session code step), with the map added in release 2? Or build the map first? | Owner |
| Q3 | Which repository is the first target: this one (its docs already follow the method), or another? This also sets what the rule files are derived from and where the loop files issues | Owner |
| Q4 | Is the release step in the first version, or deferred? | Owner |
| Q5 | Are the rule files written from this repository's docs README and the method's structure, or does the owner have rule files and prompts to bring in as sources? | Owner |
| Q6 | Model access: the Claude subscription sign-in, or a cloud provider such as Amazon Bedrock? | Owner |
| Q7 | Is the work tracker part of the first version (a tracker key as a start form), or task files and plain requests only? | Owner |
| Q8 | Should the upstream-claim trip back (F4) be built in the engine before the first trial, or recorded as release 1 behaviour? | Owner |
| Q9 | Should the approval pause after the code gate be on by default while the workflow is in `dev`? | Owner |
| Q10 | Are the draft final criteria (ts-verify to ts-review) the right bar, and what would make the owner reject a run that passes all of them? | Owner, in interview phase 2 |

## What was built from this note (2026-11-21)

The package is [`plugins/temperspec-tgraph`](../../../temperspec-tgraph/README.md): a model-free repository probe, six steps (setup, which runs only in a repository without an overview spec, then triage, discovery, plan, expand, code), the outcome gate and a last stage that pushes and opens a draft pull request. `author verify` passes its model-free rungs; the judge seeds and the trial run are rows TS-L1 and TS-L2 of the package's [live checks](../../../temperspec-tgraph/docs/plans/live-checks.plan.md). 

## References

[research `temperspec-needs-against-the-engine`](temperspec-needs-against-the-engine.rsrch.md) · [research `workflow-packages-authoring-and-good-outcomes`](workflow-packages-authoring-and-good-outcomes.rsrch.md) · [research `effort-ladders-and-one-step-model-escalation`](effort-ladders-and-one-step-model-escalation.rsrch.md) · [first-release plan](../plans/first-release.plan.md) · [live checks](../plans/live-checks.plan.md)
