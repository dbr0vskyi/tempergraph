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
| B6 | Conversation, modes `blocking` and `always`: one batched pause with typed questions and defaults; answers by terminal, file or the owner's own agent session; a deadline takes the defaults | The owner answers only real decisions, once per run, and a deadline keeps the run moving (engine: ask unit and deadlines, release 2; a deadline that takes the defaults is not an engine choice yet, so `escalate` until then, [stages F2](../research/stages-against-engine-releases.rsrch.md)) | [next features §2](../research/next-features.rsrch.md) |
| B7 | Per-phase coding: one fresh session, one gate and one commit per phase of a complex plan | A fresh context per phase of a large plan, and a failed phase reruns alone (engine: sequential map, release 2) | [next features §3](../research/next-features.rsrch.md); the owner's ruling on complex tasks |
| B9 | Cheaper model for mechanical phases, a stronger one only after a judged blocker | Lower cost on rows that need no design, without raising the model on any failure (engine: ladders, release 2) | [next features §5, row 6](../research/next-features.rsrch.md) |
| B10 | Verification commands read from the repository, so temperspec works outside Python | temperspec runs on repositories that are not Python (engine: `@repository` commands from `tempergraph.commands.json`, release 2) | [next features §5, row 5](../research/next-features.rsrch.md) |

## Waiting for the engine

| # | Feature | Waits for | Source |
|---|---|---|---|
| B8 | Reading in parallel: discovery research per gap, the setup survey per component, the judges of one gate, for shorter discovery and setup | The concurrent map and a cap that reserves for sessions in flight (engine release 3); release 2's parallel block has fixed branches only ([stages F2](../research/stages-against-engine-releases.rsrch.md)) | [next features §3, case A](../research/next-features.rsrch.md) |
| B11 | Repository setup as a sub-workflow | Sub-workflows (engine release 3) | The owner's request of 2026-11-21 |
| B12 | Coding phases in parallel, behind three rules: the plan declares independence, a check proves disjoint files, verification runs again after the merge | Writer branches and the parallel map (engine release 3) | [next features §3, case B](../research/next-features.rsrch.md) |
| B13 | Several independent answers to a hard choice, then a pick or a vote | Contest and council units (engine release 3), and a measured gain | [next features §3, case D](../research/next-features.rsrch.md) |
| B14 | A scheduled drift audit: a judge compares specs with the code and files what it finds | Schedules (engine, designed) | [next features §5, row 4](../research/next-features.rsrch.md) |

## To tune once runs exist

| # | What | Measure |
|---|---|---|
| T1 | The quick lane's limits (3 acceptance criteria, 2 code files, 200 changed lines) | The share of quick runs the guard sends back to triage |
| T2 | Whether hand-over notes add to what the owner reads | Lines a person opens per pull request |
| T3 | The owner's open confirmations: the package's decision record 0001, and the default for tests that already fail before the code step | The owner's answer |

## Left out on purpose

Delta specs, agent personas, regenerating code from specs, and a knowledge file the agent appends to. The reasons are in [next features §5](../research/next-features.rsrch.md). The release step and a start from a work tracker were left out of the first version by the owner.
