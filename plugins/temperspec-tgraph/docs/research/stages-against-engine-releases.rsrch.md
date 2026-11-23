# temperspec's next stages against the engine's releases

| | |
|---|---|
| Date | 2026-11-22 |
| Asked by | The owner, 2026-11-21: once release 2 of the engine is finished, plan and prepare the further stages of temperspec (research, spec updates). Release 2 was reported finished on 2026-11-22 (the engine's R-140 F1, in review) |
| Method | Every backlog row and every open question of the [overview spec](../specs/00-overview.spec.md) read against the engine as built at release 2 (its specs' "As built" notes and `model/validate.py`), and against release 3 as proposed in the engine's ADR-0132, R-140 and third-release plan (all in review on 2026-11-22). No live run was made for this note |
| Status | Proposal. Its stages were planned in the next-stages plan (removed 2026-11-23; its rows are now GitHub issues labelled `area: temperspec`) |

## 1. Summary

1. **Release 2 lifts four workarounds temperspec was built around** (F1): deliverables are now required only on the path that produces them, a repository can declare its own commands, `GitFacts.pushed` is set, and the engine has a complexity switch with the same rule temperspec wrote by hand. None of them is used yet.
2. **Two backlog rows need more than release 2 gives** (F2): parallel reading (B8) has a varying number of gaps, so it needs the concurrent map of release 3, and release 2's cap does not hold for sessions in flight at once (the engine's R-140 F5). A deadline that "takes the defaults" (B6) is not one of the engine's `on_deadline` choices; it is a general request to the engine.
3. **Per-phase coding (B7) fits the sequential map, with one change of shape** (F3): a map's gate takes no line back upstream, so the quick-lane guard and a plan defect found while coding move to the join that follows the map.
4. **Release 3 as proposed carries every feature waiting for the engine** (F4), and release 4 carries the two gaps the comparison found that temperspec cannot close alone: other executors and batches of tasks.
5. **Evidence still comes first** (F5): the trial and one real run that reaches a pull request. Every feature after it is tuned by numbers no run has produced yet.

## 2. Findings

### F1 What release 2 gives that temperspec does not use yet `confirmed`

| Engine capability, as built | Workaround in temperspec today | What changes |
|---|---|---|
| A deliverable is required only on a path that produces it; a judge reference to an off-path artifact is optional ([OUT, as built R2-T7](../../../tempergraph/docs/specs/90-run-outcome.spec.md)) | Only `triage_note` is a deliverable; the plan, the code report and the discovery hand-off are not, so the outcome judge never sees them as deliverables (overview, open question 2) | List `handoff`, `plan` and `code_report` as deliverables; the outcome gate checks each on the paths that produce it |
| A repository declares commands in `tempergraph.commands.json`; a step or check that lists `@repository` gets them ([CHK, as built R2-T7](../../../tempergraph/docs/specs/75-check-contract-and-command-runs.spec.md)) | One fixed list: pytest, ruff, mypy, read-only git (overview, open question 6) | Backlog B10. `prepare` writes the file when it is missing and the repository is Python, so today's behaviour is the default |
| `GitFacts.pushed` is true when the head is on a remote-tracking ref (same note) | "No commit on a remote" is not checked (open question 7) | The outcome check can say whether the branch was pushed. Steps still cannot push; the last stage does |
| A complexity switch: model-free measures, a rules file, the most detailed arm as the safe default, one-way re-arm, an override at start, a report by arm ([CXR](../../../tempergraph/docs/specs/94-complexity-routing.spec.md)) | `routing.py` routes on the plan's `complexity` value, which the plan check confirms on measurable signs | The plan's route becomes a complexity switch in CXR's "after planning" shape, measured on the plan check's facts. Same rule, but the choice is reported per arm and the owner's override at start comes from the engine. Backlog B17 |

The blueprint now takes `map`, `parallel`, `ask` and `wait` (engine R-140 F1, in review), so each change can go through `author verify` as before.

### F2 Two rows were filed against the wrong release `confirmed`

- **B8 parallel reading.** Release 2's parallel block has a fixed set of branches; picking branches at run time is FLX-B6 and a concurrent map is MAP's `concurrent` mode, both refused `not_in_release` in release 2 (`model/validate.py`; [FLX, as built](../../../tempergraph/docs/specs/74-flow-extensions.spec.md)). Discovery has one branch per gap and setup one per component, both of varying number. A sequential map over gaps works in release 2 and gives each gap a fresh context, but not a shorter run. The cap also needs the reservation of [BUD-B12](../../../tempergraph/docs/specs/08-budgets-and-failures.spec.md) (release 3) before sessions run at once. B8 moves to "Waiting for the engine".
- **B6 deadlines.** `on_deadline` is `escalate`, `stop` or a forward unit ([FLX-B8](../../../tempergraph/docs/specs/74-flow-extensions.spec.md)). A forward unit skips the ask without writing `answers`, so later steps would read no answers at all. What next-features §2 asks for is "a passed deadline answers every question with its default and continues". Stated for any workflow: *an `on_deadline` choice that fills each unanswered question with its default and proceeds when the set is then complete*. Per the engine's ADR-0129 the need is written here first, and the engine states and tests it without naming temperspec. Until it exists, `escalate` is the fallback. A deadline also acts only when someone runs `resume --apply-deadline`, until the schedule tick (release 3) can do it.

### F3 Per-phase coding on the sequential map `confirmed`

The engine's MAP spec was written for this shape (expand writes the list, a phase step runs per item, code is the join). Four points the design must take into account:

1. **No line back from an item.** A map's gate refuses `back_targets` ([MAP-B11](../../../tempergraph/docs/specs/77-map-unit.spec.md)). The quick-lane guard (back to triage) and an upstream claim against the plan are therefore raised at the join, which runs the whole-change check (`ts-verify`, the changed-files limit) and holds the code judge's upstream line. A phase gate checks only its own rows.
2. **The list.** `extract` reads the plan's phases with `specfmt.py`, one item per phase, at most 20 by MAP's default and 50 at most. The phase text carries its `Read:` and `Produces:` lists (plan-format note, B7 additions).
3. **A commit per phase.** The engine's `after` script runs after each step attempt, so each item commits as each step does today, which is the owner's rule.
4. **Simple plans keep one session.** The switch of F1 sends a simple plan to today's `code` unit. Per-phase code cost 130% of one session on small plans (the engine's R-126 F1), so the map arm is the complex one only.

B9 (a cheaper model per phase) rides on the same map: `item_model` picks among declared aliases per item, and the ladder ([LAD](../../../tempergraph/docs/specs/92-effort-ladder-and-model-escalation.spec.md)) climbs only on trusted evidence, which needs an accepted judge. So B9 waits for the phase judge's seeds to be graded live, as decision record 0002 already says for the code ladder.

### F4 Release 3 and release 4 `likely`

These rest on the engine's ADR-0132, which is proposed and not accepted.

| Row | Feature | Engine capability | Engine release |
|---|---|---|---|
| B11 | Repository setup as a workflow of its own | Sub-workflows (the engine's spec 99 SWF, in review) | 3 |
| B8 | Parallel reading | Concurrent map, reservation of the cap | 3 |
| B12 | Coding phases in parallel | Writer branches, concurrent map with item worktrees | 3 |
| B13 | Several answers to a hard choice | Contest and council units | 3 |
| B14 | A scheduled drift audit | Schedules and unattended fires | 3 |
| B15 | A trust report on the pull request (in review in its own pull request) | The pull-request gate | 3, if the owner accepts R-135 |
| — | Steps reach only what they declare when a run starts inside a Claude Code session | ECC-B14 | 3 |
| — | Other executors (comparison §10, "behind" 4) | Antigravity, Messages API, Agent SDK | 4 |
| — | Several tasks at once, coordinated (next features §3, case C) | Orchestration of runs | 4 |

Two notes. ECC-B14 matters to temperspec more than to most workflows, because its runs usually start from the owner's own Claude Code session. And the docs-only version the owner asked for (today the `discovery-only` route) can become a second workflow built from the same sub-workflows as setup, once B11 exists; it needs no feature of its own.

### F5 What every stage waits on `confirmed`

- **Live evidence.** TS-L1 (judge seeds) and the trial passed live on 2026-11-22. The real run of TS-L2 passed in part: it had no remote, so the push and the draft pull request never ran. Sizing (decision record 0002), the quick lane's limits (T1) and any ladder need measured runs.
- **The owner's confirmations**: decision records 0001 and 0002, and the default for tests that already fail before the code step (T3).

## 3. Recommendation

Build in the order of the next-stages plan (now the priority labels of the `area: temperspec` issues): evidence (S0), then what release 2 gives with no new shape (S1), then the new shapes of release 2 (S2), then release 3 (S3), then release 4 (S4). The migration of the engine's own specs to temperspec's format is work of its own, started on the owner's word of 2026-11-22.

## 4. Open questions

None. The owner ruled on 2026-11-22: temperspec is used for the development of tempergraph and temperspec, so the evidence of F5 comes from this repository's own tasks; the three proposals are backlog rows B16 (F1, deliverables and `pushed`), B17 (F1, the complexity switch) and B18 (F2, a deadline that takes the defaults); the conversation's default mode is `blocking`, because the agent that orchestrates the runs can answer or escalate to a person; and the engine's specs migrate now.

## 5. Sources

The package's backlog (now GitHub issues), [next features](next-features.rsrch.md), [comparison](sdd-tools-comparison.rsrch.md) §10 and [plan format note](plan-format-against-reference.rsrch.md); the engine's specs ASK, MAP, FLX, LAD, CXR, CHK, OUT and BUD at `main` (`a278807`); the engine's R-140, ADR-0132, ADR-0133, SWF and third-release plan as proposed on 2026-11-22; R-135 and the package's pull-request report note as proposed on 2026-11-21.
