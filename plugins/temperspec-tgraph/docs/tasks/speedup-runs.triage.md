# Triage: speedup-runs

## Task

Source: a task file (`task-speedup.md`) kept outside the repository. Make temperspec runs faster: run the engine's suite in parallel, run the full suite once per code visit, reuse a full-suite result for an unchanged tree, size discovery to the gap (backlog B21), and make discovery and plan read narrowly through a reading list in the hand-off.

## Acceptance criteria

1. **The engine's suite runs in parallel.** `python -m pytest` in `plugins/tempergraph/engine/` runs its tests across workers (pytest-xdist, `-n auto` or an equivalent default), `pytest-xdist` is in the `dev` extra, and the suite passes in parallel with no test relying on order or on shared files outside its own temporary folder. The engine's CLAUDE.md command line and any guide that states how to run the suite stay true. Report the serial and the parallel wall time measured on this machine in the code report.
2. **A code visit runs the full suite at most once in its session.** The code step's prompt tells the session to run, after each phase, only the tests of that phase's rows (the test files the rows name), and to run the plan's full verification commands once, at the end, before it writes the report. The code spec states this behaviour.
3. **The gate reuses a full-suite result for an unchanged tree.** When the code gate's check would run a verification command whose result is already recorded for the same command on the same tree (the engine's command reuse, CHK-B12 and CHK-B13), it reuses it instead of running again, including across a retry or a later visit of the same unit where the tree did not change. If the engine already does this in every such case, the change only states it in temperspec's code spec and adds a test that proves it; if it does not, the missing case is added to the engine as a general capability with its spec behaviour and an engine test.
4. **Discovery is sized to the gap (backlog B21).** Triage marks each gap that an existing spec already answers as covered (for example a `covered` column or mark in the triage note's gap list, read by the triage check). When every gap is covered, discovery runs as a short visit: lower effort than `max` (for example `high`) and a stated reading limit, using the engine's existing means of choosing a unit's sizing or arm by a run fact (for example the complexity switch or effort ladder of engine release 2; if none fits, say so in the hand-off and pick the closest general capability). When no gap is open at all, the run goes on as today. Sizing reasons stay explicit for each arm.
5. **Discovery and plan read narrowly.** The discovery prompt tells the session to search (grep for ids and names) and read the line ranges it needs instead of whole files, and to stop reading once each gap has its answer. The hand-off carries a reading list: each file the plan will need, with the line ranges or ids that matter and one line on why. The task-notes rule's hand-off section and its example state the reading list, `workflow/temperspec/specfmt.py` and the discovery check read it (a missing reading list is a finding), and `tests/test_temperspec.py` keeps the rule and the module in agreement. The plan prompt tells the session to start from the reading list and to open other files only for what the list does not answer.
6. **Tests.** Each criterion above is proved by a test that carries its id, in the package's tests for temperspec's behaviour and in the engine's tests for any engine change. The engine's full suite, the package's tests, `ruff check src tests` and `mypy` pass.

## Existing documents

- `plugins/temperspec-tgraph/docs/specs/triage.spec.md`: triage note form, route and gap criteria (ts-tri-*); says nothing about marking a gap as covered
- `plugins/temperspec-tgraph/docs/specs/discovery.spec.md`: discovery criteria (ts-dis-*); says nothing about sizing, reading limits or a reading list
- `plugins/temperspec-tgraph/docs/specs/plan.spec.md`: plan criteria; no statement that the plan starts from a reading list
- `plugins/temperspec-tgraph/docs/specs/code.spec.md`: code criteria (ts-code-*), including ts-code-verify; says nothing about running the full suite once per visit or about reusing a result
- `plugins/temperspec-tgraph/rules/task-notes.rule.md`: triage, hand-off and report formats; the hand-off has no reading list, the gap row has no covered mark
- `plugins/temperspec-tgraph/docs/plans/backlog.plan.md`: row B21 (covered gaps, short discovery), to be deleted when built
- `plugins/tempergraph/docs/specs/check-contract-and-command-runs.spec.md`: CHK-B12 and CHK-B13, command runs reused by key (argv, program, head, status listing, content digest) within a thread; whether this covers a retry and a later visit of the same unit must be checked in the engine code
- `plugins/tempergraph/docs/specs/complexity-routing.spec.md`, `effort-ladder-and-model-escalation.spec.md`, `measured-switches.spec.md`: the engine's means to choose a unit's arm or effort by a run fact
- `plugins/tempergraph/engine/pyproject.toml`: pytest config (`addopts = "-q --strict-markers"`), no xdist worker option found

## Gaps

- G1 spec update: triage marks a gap an existing spec already answers as covered, read by the triage check. `triage.spec.md` and `task-notes.rule.md` state no such mark. Searched `plugins/temperspec-tgraph/docs/specs/` and the rule for "covered": nothing about gap marks
- G2 spec update: discovery sized to the gap (short visit with lower effort and a reading limit when every gap is covered, unchanged when no gap is open). Searched `discovery.spec.md`, `blueprint.json` and the specs for "sizing", "effort", "reading", "complexity": nothing about discovery sizing by gaps; the engine's means exist in specs `measured-switches`, `effort-ladder-and-model-escalation` and `complexity-routing` but no temperspec spec uses them for discovery
- G3 spec update: the hand-off reading list, read by the discovery check, and the plan starting from it. Searched temperspec specs and `task-notes.rule.md` for "reading list": nothing
- G4 spec update: a code visit runs only the phase's test files after each phase and the full verification commands once at the end. Searched `code.spec.md` for "full suite", "once", "phase": nothing
- G5 spec update: the code gate reuses a verification command's recorded result for an unchanged tree, across a retry and a later visit. CHK-B13 covers reuse by key in a thread, but `code.spec.md` does not state it, and whether the engine covers retry and later-visit cases is unverified. In doubt, listed
- G6 spec gap: the engine's own suite runs in parallel with order-independent, folder-isolated tests. Searched `plugins/tempergraph/docs/specs/` and the guides for "xdist", "parallel" in the sense of running the test suite: nothing about how the suite runs

## Route

- Deliver: code
- Route: discovery
