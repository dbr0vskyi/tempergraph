---
task: speedup-runs
complexity: complex
status: planned
specs: [plugins/tempergraph/docs/specs/test-suite.spec.md, plugins/temperspec-tgraph/docs/specs/04-triage.spec.md, plugins/temperspec-tgraph/docs/specs/05-discovery.spec.md, plugins/temperspec-tgraph/docs/specs/06-plan.spec.md, plugins/temperspec-tgraph/docs/specs/08-code.spec.md]
---

# Plan: faster temperspec runs

## 0. Hand-off

- Triage note: `plugins/temperspec-tgraph/docs/tasks/speedup-runs.triage.md`
- Hand-off: `plugins/temperspec-tgraph/docs/tasks/speedup-runs.handoff.md` (its Reading list was the start of this plan)
- Specs read: `plugins/tempergraph/docs/specs/test-suite.spec.md`, `plugins/temperspec-tgraph/docs/specs/04-triage.spec.md`, `plugins/temperspec-tgraph/docs/specs/05-discovery.spec.md`, `plugins/temperspec-tgraph/docs/specs/06-plan.spec.md`, `plugins/temperspec-tgraph/docs/specs/08-code.spec.md`
- Decision record read: `plugins/temperspec-tgraph/docs/adr/speedup-runs-discovery-sizing.adr.md`
- Why this design: the engine part is configuration and tests (one new engine spec, no engine source change for the gate, because the engine already reuses a command result for an unchanged tree). The temperspec part is one parser, rule and check family (the covered mark and the reading list), one second discovery step chosen by the route after triage, and prompt changes for the code, discovery and plan sessions. Phases are ordered so that the covered mark exists before the route and the short step use it.
- The hand-off's decisions bind the code step: the default worker count is `auto` capped at four, one process with `-n 0` or when `pytest-xdist` is missing; the engine's suite stays free of any workflow name (ADR-0129); the improvement loop and the gate's retry and escalation path are not touched; no step or judge uses the large model tier and every sizing keeps its reason. Rows of the four package specs are mirrored into `outcome.json` as revision 5 with the same text.
- The hand-off's one open question (whether the session's own end-of-visit run counts as the gate's result) does not block planning; as the hand-off says, until a person answers it the plan takes option (a): two runs per clean visit, and no change to the engine's reuse key.

## 1. Requirements

| Req | Criteria | Statement | Spec ids |
|---|---|---|---|
| R1 | AC 1 | `python -m pytest` in the engine folder with no worker option spreads the tests over one worker per processor, at most four, from the project's own configuration | TST-B1, TST-AC1 |
| R2 | AC 1 | `-n 0` runs every test in one process, and a missing `pytest-xdist` runs the suite in one process with a line that names the runner and the `dev` extra, with no unknown-option stop | TST-B2, TST-B3, TST-AC2, TST-AC3 |
| R3 | AC 1 | The suite passes and skips the same tests on workers as in one process, each test file passes alone, every test keeps its own temporary, home and state folders, and a full run leaves nothing changed outside cache folders | TST-B4, TST-B5, TST-AC4, TST-AC5, TST-AC6, TST-AC7 |
| R4 | AC 1 | The engine's `dev` extra lists `pytest-xdist` | TST-B6, TST-AC8 |
| R5 | AC 1 | The engine's documented test command in `CLAUDE.md` and the guides stays true with the default, and the code report states the serial and the parallel wall time of the suite measured on this machine | TST-B1, TST-B2 |
| R6 | AC 2 | The code prompt tells the session to run only the test files of a phase's rows after that phase and each verification command of the plan once, after the last phase and before the report (the quick lane's `Verify` commands once, after the last criterion) | ts-code-once |
| R7 | AC 3 | The code gate runs a verification command only when no result of it is recorded for the same tree, so a retry or a later visit on an unchanged tree runs nothing again; a package gate-level test over one tree and one store proves it, and no engine source changes | ts-code-reuse, CHK-B13 |
| R8 | AC 4 | A gap row of the triage note may say `Covered by <behaviour id> and <criterion id>`; the task-notes rule, the format module, the triage prompt and the triage check state and confirm it (both ids exist once in one spec, the criterion names the behaviour), and the step reports whether every gap is covered | ts-tri-covered |
| R9 | AC 4 | A task whose gap rows are all covered goes after triage to a short discovery step at effort `high`, its judge at `high`, with a prompt that states a reading limit of at most 10 files; any other gap, and every return from a later gate, goes to the full discovery at `max`; `Gaps: None` still skips discovery; each step and judge keeps its own sizing reason | ts-dis-short, ts-dis-full |
| R10 | AC 5 | Every discovery prompt tells the session to search for ids and names, to read the line ranges it needs instead of whole files, and to stop reading once each gap has its answer | ts-dis-narrow |
| R11 | AC 5 | The hand-off carries a reading list, one item per file the plan will need, with an existing file, the line ranges or ids and one line on why; the task-notes rule (section and example), the format module and the discovery check read it, a missing reading list or a missing file is a finding, and the package's test keeps rule and module in agreement | ts-dis-reading |
| R12 | AC 5 | The plan prompt tells the session to start from the hand-off's reading list and to open another file only for what the list does not answer | ts-plan-reading |
| R13 | AC 6 | Each criterion above is proved by a test that carries its spec id (the package's tests for temperspec behaviour, the engine's tests for the suite configuration); the new spec rows are mirrored in `outcome.json` as revision 5; backlog row B21 is deleted; the engine's full suite, the package's tests, `ruff check src tests` and `mypy` pass | TST-AC1, TST-AC2, TST-AC3, TST-AC4, TST-AC5, TST-AC6, TST-AC7, TST-AC8, ts-tri-covered, ts-dis-short, ts-dis-full, ts-dis-narrow, ts-dis-reading, ts-plan-reading, ts-code-once, ts-code-reuse |

## 2. Phases

### Phase 1: Parallel engine suite

Goal: `python -m pytest` in the engine folder runs on at most four workers by default, in one process with `-n 0` or without the runner, passes the same tests either way, and each test keeps to its own folders (R1, R2, R3, R4, R5). Tests first: each of TST-AC1 to TST-AC8 is proved by an engine test that carries its id. Work from the known causes first (tests that fail only under workers because temporary paths are longer, the one test that sets `os.environ` directly). The serial and the parallel wall times are measured and kept for the code report.
Weight: heavy (long-running)

### Phase 2: The covered mark in triage

Goal: a gap row can say `Covered by <behaviour id> and <criterion id>`, and the rule, the format module, the triage prompt, the triage check and its eval fixtures state and confirm it, with a must-pass note and a must-fail note that cites an id no spec defines (R8).
Weight: medium

### Phase 3: Reading list and narrow reading

Goal: the hand-off has a Reading list section in the task-notes rule (bullets and example), the format module and the discovery check read it, the discovery and plan prompts tell the sessions to read narrowly and to start from the list, the rule-against-module test holds the agreement, and the discovery eval fixtures carry or lack a list as their expected verdict needs (R10, R11, R12).
Weight: medium

### Phase 4: The short discovery visit

Goal: the route after triage sends a task whose gaps are all covered to a second, short discovery step with its own prompt (reading limit of 10 files), sizing (effort `high`, reason stated) and judge sizing (`high`, reason stated), while every other gap and every return from a later gate keeps the full discovery at `max`; the blueprint, the package docstring and README describe both visits, and the sizing and routing tests hold each arm (R9).
Weight: medium

### Phase 5: One full run per code visit

Goal: the code prompt carries the once-per-visit rule for the plan's phases and for the quick lane, and a gate-level test proves that a second gate run over the same tree and store reuses every verification result (R6, R7). No engine source is changed.
Weight: light

### Phase 6: Mirrors, documents and release gates

Goal: `outcome.json` mirrors the eight new spec rows as revision 5 so that `author verify` and the package coverage test pass, backlog row B21 is deleted, the documents listed under Docs to update are true, and the engine's full suite, the package's tests, ruff and mypy pass (R5, R13).
Weight: light

## 3. Verification

- `cd plugins/tempergraph/engine && python3 -m pytest`
- `cd plugins/tempergraph/engine && ruff check src tests`
- `cd plugins/tempergraph/engine && mypy`
- `cd plugins/temperspec-tgraph && python3 -m pytest tests`

## 4. Docs to update

- `plugins/temperspec-tgraph/rules/task-notes.rule.md`: the Gaps example and bullet have no `Covered by` mark and the hand-off example and bullets have no Reading list; the fill-in templates generate from these examples
- `plugins/temperspec-tgraph/README.md`: the step table and "discovery thinks at the highest effort" stop being true once the short visit exists
- `plugins/temperspec-tgraph/docs/plans/backlog.plan.md`: row B21 is built and is deleted
- `CLAUDE.md`: the engine's test command line gains the default of parallel workers and `-n 0` for one process, so that the instruction states how the suite runs
