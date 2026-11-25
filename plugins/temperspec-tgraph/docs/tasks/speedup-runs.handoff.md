# Hand-off: speedup-runs

## Problem

temperspec runs are slow in four places: the engine's suite runs in one process, a code visit runs the full suite more than once, the gate's reuse of a result is neither stated nor tested, and a task whose gaps a spec already answers still pays for a full discovery at `max` that reads whole files. The task asks for a parallel engine suite, one full run per code visit, reuse of a gate result for an unchanged tree, a short discovery for covered gaps (backlog B21) and narrow reading through a reading list. The engine already reuses a result for an unchanged tree, so that part needs a spec row and a test, not an engine change.

## Gaps closed

- G1: `plugins/temperspec-tgraph/docs/specs/triage.spec.md` (ts-tri-covered); the form of the mark goes into the task-notes rule in the plan
- G2: `plugins/temperspec-tgraph/docs/specs/discovery.spec.md` (ts-dis-short, ts-dis-full) and the decision record `plugins/temperspec-tgraph/docs/adr/short-discovery-visit.adr.md`, which says why no engine switch, override or ladder fits and picks the route after triage
- G3: `plugins/temperspec-tgraph/docs/specs/discovery.spec.md` (ts-dis-narrow, ts-dis-reading) and `plugins/temperspec-tgraph/docs/specs/plan.spec.md` (ts-plan-reading)
- G4: `plugins/temperspec-tgraph/docs/specs/code.spec.md` (ts-code-once)
- G5: `plugins/temperspec-tgraph/docs/specs/code.spec.md` (ts-code-reuse) and the research note `plugins/temperspec-tgraph/docs/research/speedup-runs-command-reuse.rsrch.md`, which shows that the engine already reuses a result in every case the task names (CHK-B13, CHK-B5)
- G6: the new `plugins/tempergraph/docs/specs/test-suite.spec.md` (TST-B1 to TST-B6, TST-AC1 to TST-AC8)

## Changed documents

- `plugins/tempergraph/docs/specs/test-suite.spec.md`: new
- `plugins/tempergraph/docs/specs/overview.spec.md`: one line added to Purpose that names the new spec, which the overview must do
- `plugins/temperspec-tgraph/docs/specs/triage.spec.md`: one criterion row added (ts-tri-covered)
- `plugins/temperspec-tgraph/docs/specs/discovery.spec.md`: four rows added (ts-dis-short, ts-dis-full, ts-dis-narrow, ts-dis-reading)
- `plugins/temperspec-tgraph/docs/specs/plan.spec.md`: one row added (ts-plan-reading)
- `plugins/temperspec-tgraph/docs/specs/code.spec.md`: two rows added (ts-code-once, ts-code-reuse)
- `plugins/temperspec-tgraph/docs/adr/short-discovery-visit.adr.md`: new
- `plugins/temperspec-tgraph/docs/research/speedup-runs-command-reuse.rsrch.md`: new

## Decisions

- The rows of the four package specs are added in those specs' earlier layout (numbered sections, `- [ ] ts-…` rows), as the spec rule says to leave an earlier layout as it is. That layout has no behaviours section, so each row states one observable result, as the existing rows do. The code step mirrors each row into `outcome.json` with the same text (revision 5), because a rescaffold rebuilds the criteria section from that file and would drop a row that is not there.
- A gap is still listed in doubt. `Covered by <behaviour id> and <criterion id>` records the answer triage found, so that discovery confirms it instead of searching. The triage check confirms that both ids exist once in one spec and that the criterion names the behaviour.
- None of the engine's means fits discovery sizing. The complexity switch is sticky for the run and would keep a run short after a trip back to discovery; an arm override changes the effort but not the prompt and carries no reason; the effort ladder starts at one rung whatever the note says. The closest general capability is the route after triage, which already picks the next unit from the values the triage step produced. It picks a second, short discovery step (decision record). No engine change for G2.
- The short step runs at effort `high` with a reading limit of 10 files, and its judge at `high`. The task gave `high` as an example and left the limit open. These are first assessments made without a run, as in the decision record `model-and-effort-per-unit`; the first measured runs may move them. Each visit states its own reasons for step and judge (decision record), which the existing sizing test and the engine's audit rule already hold for every step.
- "When no gap is open at all, the run goes on as today" is read as `Gaps: None`, which already goes to the plan or the quick lane with no discovery (ts-tri-route). No row changes for it.
- The engine already reuses a verification result for the same tree across a retry, a later visit and the outcome gate, so criterion 3 needs a statement (ts-code-reuse) and a gate-level test, not an engine capability (research note, F1 to F4 and F7).
- The engine suite runs on at most four workers by default (`auto`, capped at four), not on plain `auto`. The task allowed `-n auto` or an equivalent. `-n 0` runs one process. When `pytest-xdist` is missing the suite runs in one process and says so: a code session cannot install a package (its commands are the plan's verification prefixes), and an unknown option in the configuration would stop every run in an environment without the runner.
- The new engine spec is `test-suite.spec.md`, a slug and not a numbered file: the documents rule forbids claiming the next number, and no engine test requires the prefix.
- This hand-off already carries the reading list the task asks for. The task-notes rule does not define the section yet, so it follows the five sections of the current rule.

## Open questions

- Should the session's own end-of-visit full run count as the gate's result? Today a clean visit runs the suite twice, once in the session (criterion 2 asks for one run) and once in the gate, because the engine records only its own runs and its reuse key holds `HEAD`, which the engine's commit moves (research note, F5 and F6). Options: (a) accept two runs per visit; (b) ask the engine for a reuse key that holds the working tree's content, and end the code session with the engine's own check preview, so that its run is the gate's. Until answered: (a). It does not block planning.

## Reading list

- `plugins/temperspec-tgraph/docs/tasks/speedup-runs.triage.md` (lines 9-14, 30-35): the six criteria, which the plan names `AC 1` to `AC 6`, and the gaps G1 to G6
- `plugins/tempergraph/docs/specs/test-suite.spec.md` (TST-B1 to TST-B6, TST-AC1 to TST-AC8): the source of the requirements for criterion 1; each criterion needs a test carrying its id
- `plugins/temperspec-tgraph/docs/specs/triage.spec.md` (ts-tri-covered): requirement source for the covered mark
- `plugins/temperspec-tgraph/docs/specs/discovery.spec.md` (ts-dis-short, ts-dis-full, ts-dis-narrow, ts-dis-reading): requirement source for the short visit, the narrow reading and the reading list
- `plugins/temperspec-tgraph/docs/specs/plan.spec.md` (ts-plan-reading): requirement source for the plan prompt
- `plugins/temperspec-tgraph/docs/specs/code.spec.md` (ts-code-once, ts-code-reuse): requirement source for criteria 2 and 3
- `plugins/temperspec-tgraph/docs/adr/short-discovery-visit.adr.md` (Decision, the sizing table): the short step's effort and reasons, to copy into the sizing table and the blueprint
- `plugins/temperspec-tgraph/docs/research/speedup-runs-command-reuse.rsrch.md` (F1 to F4, F7, conclusions 1 and 2): why the engine needs no change, and how to test the gate (two gate runs over one tree and one store, the second reused)
- `plugins/temperspec-tgraph/rules/task-notes.rule.md` (lines 31-33, 42, 77-105): add `Covered by` to the Gaps example and bullet, and the reading list to the hand-off example and bullets; the templates regenerate from the examples
- `plugins/temperspec-tgraph/workflow/temperspec/specfmt.py` (lines 14, 54, 60-72, 196-238): `HANDOFF_HEADINGS`, `GAP_ROW`, `rule_templates`, `Triage` and `parse_triage`; parse the covered marks and the reading list here
- `plugins/temperspec-tgraph/workflow/temperspec/checks.py` (lines 34-38, 76-95, 249-292, 314-326, 575-587, 644-645): `_value`, the spec index, `triage_check` (covered marks and the covered value), `discovery_check` (reading list; `_docs_only` exempts a run that ends after discovery), `_verify` (already asks for reuse)
- `plugins/temperspec-tgraph/workflow/temperspec/__init__.py` (lines 1-14, 43-61, 96-109, 123-131): the docstring, `SIZING`, the triage and discovery steps and the code step; declare the short step, its sizing and the covered value, and keep `back_targets` on the full `discovery`
- `plugins/temperspec-tgraph/workflow/temperspec/routing.py` (lines 53-62): `route_triage` sends an all-covered task to the short step, and `route_discovery` ends both discovery steps the same way
- `plugins/temperspec-tgraph/prompts/triage.md` (lines 19-23): the step that defines covered; add the mark
- `plugins/temperspec-tgraph/prompts/discovery.md` (lines 16-37): narrow reading and the reading list; the short step's prompt states the limit of 10 files
- `plugins/temperspec-tgraph/prompts/plan.md` (lines 19-21): start from the reading list, open another file only for what it does not answer
- `plugins/temperspec-tgraph/prompts/code.md` (lines 22-24): steps 6 and 7; the phase's test files after each phase, the full commands once at the end, and the quick lane's `Verify` commands once
- `plugins/temperspec-tgraph/blueprint.json` (lines 67-92, 184-210): the discovery unit and the flow; add the short step with its sizing and keep the literal check passing
- `plugins/temperspec-tgraph/outcome.json` (lines 346-480, 923-961): the discovery criteria, the assumptions and the revisions; mirror the eight new rows with the same text as revision 5. `author verify` flags a blocker that nobody verifies (`plugins/tempergraph/engine/src/tempergraph/author/verify.py` lines 159-165) and `tests/test_workflow_packages.py` line 36 fails on an uncovered final criterion, so choose per row: a check with fixtures, a judge criterion, or severity `warning`
- `plugins/temperspec-tgraph/tests/test_temperspec.py` (lines 106-170, 180-193, 370-398, 519-556): rule-against-parser tests, the route test, the sizing tests (efforts are written out per unit) and the code-gate helpers; `_code_ctx` needs a reuse store for the gate-level reuse test
- `plugins/temperspec-tgraph/evals/checks/triage/must-pass/1-gap/triage_note.md` (whole file): one of ten triage check fixtures; add a must-pass note with a `Covered by` row and a must-fail one that cites an id no spec defines
- `plugins/temperspec-tgraph/evals/checks/discovery/must-pass/2-new-spec/handoff.md` (whole file): one of seven discovery check fixtures; the must-pass hand-offs need a reading list once the check asks for one, and a new must-fail case has none
- `plugins/temperspec-tgraph/README.md` (lines 15-16, 22): the step table and "discovery thinks at the highest effort", which stops being true for the short step
- `plugins/temperspec-tgraph/docs/plans/backlog.plan.md` (line 24): delete row B21 in the change that builds it
- `plugins/tempergraph/docs/research/does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md` (line 23): the 16-minute discovery, with 362k tokens of context, its first write at turn 135 and about 40 turns re-checking form by reading checker code; the evidence behind the narrow reading rule
- `plugins/tempergraph/engine/pyproject.toml` (lines 16-21, 32-37): the `dev` extra and the pytest options; add `pytest-xdist` and the default workers; the code session's environment may lack the runner, so TST-B3 matters
- `plugins/tempergraph/engine/tests/conftest.py` (lines 32-45, 66-71, 74-85, 91-98): per-test home isolation, the real-state guard, the tree hash and the live skip; where the missing-runner notice (TST-B3) and the session-level check (TST-AC7) can live
- `plugins/tempergraph/engine/tests/test_workflow_packages.py` (lines 55-58): runs a package's own tests in a subprocess with `-o addopts=`, so the worker option does not nest
- `plugins/tempergraph/engine/tests/test_launcher.py` (lines 31-45): the only test that sets `os.environ` directly, restored by an autouse fixture; check it under workers
- `plugins/tempergraph/engine/tests/test_checks.py` (lines 87-106): the engine's reuse test at the check-context level, the model for the gate-level test
- Known causes to look for first: a guard run under workers, and tests that fail only under workers because their temporary paths are longer (a printed label cut at 120 characters)
- `CLAUDE.md` (line 14): the engine's test command; true as it is with the default in configuration, and worth a few words on `-n 0`
- `README.md` (line 56): the engine's install and test command; stays true
- `plugins/tempergraph/docs/guides/getting-started.guide.md` (line 85): the suite command in the guide; stays true
- `plugins/tempergraph/docs/plans/live-checks.plan.md` (lines 8, 16): the offline command stays true, and the live command clears `addopts`, so live tests stay in one process
