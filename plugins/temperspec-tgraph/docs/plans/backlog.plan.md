# Backlog of temperspec

The one list of features found useful and not built yet. A feature enters here when the owner says it is worth having, and leaves when it is built: its row is deleted in the pull request that builds it, so the list never holds history. The reasoning behind each row is in the note its Source column names; this file holds only what is needed to pick the next one.

**How to use it.** To build a row: read its source, write what it needs from the engine (if anything) in general terms first, as the engine's decision record 0129 requires, then build, and delete the row. To add a row: one line, with its source. A row whose engine release has arrived moves to "Ready". The order in which rows are built, and which engine release each stage needs, is in the [next stages plan](next-stages.plan.md).

## Ready: needs nothing new from the engine

| # | Feature | What it gives | Source |
|---|---|---|---|
| B1 | Conversation, mode `never`: triage sorts gaps into findable and owner decisions, takes the default for each owner decision and lists them in the pull request as assumptions to confirm | The run stays unattended and the owner sees every guess | [next features §2](../research/next-features.rsrch.md) |
| B2 | Guard for tasks run side by side: the outcome check fails when a spec the run edited has changed on the base branch since the run started | Two runs cannot silently overwrite each other's spec edits | [next features §3, case C](../research/next-features.rsrch.md) |
| B3 | Drift check outside runs: a model-free script for pre-commit and CI (spec format, links, criteria carried by tests) | Specs stay true between runs | [next features §5, row 4](../research/next-features.rsrch.md) |
| B4 | Property-based tests from behaviours written in the fixed pattern | A deterministic link from a behaviour to code | [next features §5, row 7](../research/next-features.rsrch.md) |
| B5 | A like-for-like trial against OpenSpec and GSD 2 on the same tickets, with a second change to the same feature | The only evidence that settles the comparison | [comparison §10](../research/sdd-tools-comparison.rsrch.md) |
| B6 | Conversation, modes `blocking` (the default, owner 2026-11-22) and `always`: one batched pause with typed questions and defaults; answers by terminal, file or the agent that started the run, which answers what it can and takes the rest to a person; a deadline takes the defaults | The owner answers only real decisions, once per run, and a deadline keeps the run moving (engine: ask unit and deadlines, release 2; a deadline that takes the defaults is not an engine choice yet, so `escalate` until then, [stages F2](../research/stages-against-engine-releases.rsrch.md)) | [next features §2](../research/next-features.rsrch.md) |
| B7 | Per-phase coding: one fresh session, one gate and one commit per phase of a complex plan | A fresh context per phase of a large plan, and a failed phase reruns alone (engine: sequential map, release 2) | [next features §3](../research/next-features.rsrch.md); the owner's ruling on complex tasks |
| B9 | Cheaper model for mechanical phases, a stronger one only after a judged blocker | Lower cost on rows that need no design, without raising the model on any failure (engine: ladders, release 2) | [next features §5, row 6](../research/next-features.rsrch.md) |
| B10 | Verification commands read from the repository, so temperspec works outside Python | temperspec runs on repositories that are not Python (engine: `@repository` commands from `tempergraph.commands.json`, release 2) | [next features §5, row 5](../research/next-features.rsrch.md) |
| B16 | The hand-off, the plan and the code report listed as deliverables, each required on the path that produces it; the outcome check reports whether the branch was pushed | The final gate checks and judges every document a run leaves, not the triage note alone (engine: per-path deliverables and `GitFacts.pushed`, release 2) | [stages F1](../research/stages-against-engine-releases.rsrch.md) |
| B17 | The plan's route as the engine's complexity switch, measured on the plan check's facts, in place of the hand-written route | The choice between one session and phases is reported per arm, and the owner's override at start comes from the engine (engine: complexity switches, release 2) | [stages F1](../research/stages-against-engine-releases.rsrch.md) |
| B19 | `prepare` writes the `CLAUDE.md` block from the repository's real layout (where the overview spec, the specs and the rules are) and counts rule files the repository already ships as installed | Steps write into the folders the repository uses; no copies of the rules in a repository that ships them | [R-160](../../../tempergraph/docs/research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md), run r3-t1-1b, 2026-11-22 (first write went to a root `docs/tasks/`; rules copied in the spec 35 run) |
| B20 | The code check runs the verification commands itself and compares them with the run's base: a failure already present before the change, or one that no file of the change touches, escalates as environmental instead of a retry | No retries spent on a fault no code change can fix (four retries, about 2 USD in this run) | [R-160](../../../tempergraph/docs/research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md), run r3-t1-1b, 2026-11-22 |
| B23 | A trip back to plan keeps the completed marks of rows whose files are unchanged instead of refusing them, and the code step after it codes only the rows the trip changed | A trip back does not redo or relabel finished work | [R-160](../../../tempergraph/docs/research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md), run r3-t1-1b, 2026-11-22 (`row 3.2 is already marked completed`) |
| B28 | The code gate reuses the session's own last run of the plan's commands: the session runs them through the engine's check preview, and the reuse key names the tree's content so that it survives the engine's commit | A clean code visit pays the full suite once instead of twice (session, then gate) | [command reuse note](../research/speedup-runs-command-reuse.rsrch.md), open question; run speedup-runs, 2026-11-22 |
| B29 | A plan row that adds a unit checks first what a new unit costs the package: the engine's stand-in run, the docs self-test, eval fixtures, the diagram and the stamp | The plan does not promise a step the code step cannot add with the files the rows name | Code report of run speedup-runs, deviation 6, 2026-11-22 |
| B18 | A passed deadline answers every open question of the conversation with its default and the run goes on | The run's conversation answers its own questions on a passed deadline with no person present; the engine has `on_deadline: defaults` for ask units since its release 3 item I3-15 | [stages F2](../research/stages-against-engine-releases.rsrch.md) |
| B40 | The plan, report and note tables read a cell with an escaped pipe (`X \| None`, legal Markdown) as two cells | A row whose change text holds a type union is no longer read as marked completed, which made the expand check fail three times in a row | engine runs r3-t8-1 to r3-t8-4, 2026-11-22 |
| B41 | A judge that finds no blocker and only open questions the hand-off marks as not blocking planning lets the run go on, with the questions listed in the pull request description | Three of four runs paused at discovery, and again at plan or code, as `unresolved_gap` with an empty blocker list | engine runs r3-t8-1 to r3-t8-4, 2026-11-22 |

## Waiting for the engine

| # | Feature | Waits for | Source |
|---|---|---|---|
| B8 | Reading in parallel: discovery research per gap, the setup survey per component, the judges of one gate, for shorter discovery and setup | The concurrent map and a cap that reserves for sessions in flight (engine release 3); release 2's parallel block has fixed branches only ([stages F2](../research/stages-against-engine-releases.rsrch.md)) | [next features §3, case A](../research/next-features.rsrch.md) |
| B11 | Repository setup as a sub-workflow | Sub-workflows (engine release 3) | The owner's request of 2026-11-21 |
| B12 | Coding phases in parallel, behind three rules: the plan declares independence, a check proves disjoint files, verification runs again after the merge | Writer branches and the parallel map (engine release 3) | [next features §3, case B](../research/next-features.rsrch.md) |
| B13 | Several independent answers to a hard choice, then a pick or a vote | Contest and council units (engine release 3), and a measured gain | [next features §3, case D](../research/next-features.rsrch.md) |
| B14 | A scheduled drift audit: a judge compares specs with the code and files what it finds | Schedules (engine, designed) | [next features §5, row 4](../research/next-features.rsrch.md) |
| B15 | A trust report on the pull request: the engine's pull-request gate grades the final criteria in CI and posts task completion, plan completion and code-to-spec alignment | The engine's pull-request gate (proposed in its research note R-135, release not set) | [pull request report](../research/pull-request-report.rsrch.md) |

## To tune once runs exist

| # | What | Measure |
|---|---|---|
| T1 | The quick lane's limits (3 acceptance criteria, 2 code files, 200 changed lines) | The share of quick runs the guard sends back to triage |
| T2 | Whether hand-over notes add to what the owner reads | Lines a person opens per pull request |
| T3 | The owner's open confirmations: the package's decision record 0001, and the default for tests that already fail before the code step | The owner's answer |

## Left out on purpose

Delta specs, agent personas, regenerating code from specs, and a knowledge file the agent appends to. The reasons are in [next features §5](../research/next-features.rsrch.md). The release step and a start from a work tracker were left out of the first version by the owner.
