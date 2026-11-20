---
goal: Build the monitor mod's read-only parts — sources, band, status line and alerts, the run view and the drill-down — from the engine's status, detail and run-log documents
version: 1
date_created: 2026-11-20
last_updated: 2026-11-20
owner: dbr0vskyi
status: In progress
tags: [track-plan, tempergraph-monitor, T10]
tracker: none
spec: plugins/tempergraph-monitor/docs/specs/01-data-sources.spec.md
spec_commit: 47c5b7d
task_id: first-release-t10
---

# T10 Monitor (phases T10.2 and T10.3)

## 0. Hand-off

| Field | Value |
|---|---|
| Origin | [Release 1 plan](first-release.plan.md) track T10, phases T10.2 and T10.3, built after T7.1 and T7.2 in the same pass (thread "Build run events and detail view") |
| Specs | [MOV](../../../tempergraph-monitor/docs/specs/00-overview.spec.md), [MDS](../../../tempergraph-monitor/docs/specs/01-data-sources.spec.md), [MBA](../../../tempergraph-monitor/docs/specs/02-band-status-and-alerts.spec.md), [MRV](../../../tempergraph-monitor/docs/specs/03-run-view.spec.md), [MDD](../../../tempergraph-monitor/docs/specs/04-drill-down.spec.md); engine documents from [EVT](../specs/30-run-events.spec.md), [RDD](../specs/31-run-detail-document.spec.md) and [DUR §2.2](../specs/09-durability-and-resume.spec.md) |
| Decisions | [MADR-0001](../../../tempergraph-monitor/docs/adr/0001-a-claude-code-mod-that-observes.adr.md), [MADR-0002](../../../tempergraph-monitor/docs/adr/0002-poll-files-and-read-only-verbs.adr.md), [MADR-0004](../../../tempergraph-monitor/docs/adr/0004-borrow-the-workflows-view-and-add-gates.adr.md), [MADR-0006](../../../tempergraph-monitor/docs/adr/0006-one-pane-many-levels.adr.md) |
| Mod API | The types of Claude Code 2.1.329, the build this pass was written against ([R-001](../../../tempergraph-monitor/docs/research/R-001-claude-code-mods.rsrch.md)) |

**Status: In progress.** The read-only core is built: the mod reads `status --json`, stats and tails each live run log, reads `status --detail` for the open run, and draws the band, the status line, toasts and notifications, the run list, the run view, the unit view, the attempt view and the session view's Now and Info parts. Status pass: MDS, MBA, MRV and MDD are `ready-for-implementation`, each with a "Release 1 build" design note saying what is built; MOV, MAC and MCF stay `review` (T10.4 is not started).

**Pending on the owner's machine (not faked):** the probes P-MOD-2 (reads outside the working directory), P-MOD-3 (PATH under desktop and VS Code) and P-MOD-4 (the mod loads, draws and polls in a live session against a real engine run). P-MOD-1 is answered from the 2.1.329 types (`session.start`'s `isInteractive`) and still wants the same live check. The mod was not turned on in the cloud session that wrote it; its session tests run under `claude plugin test` with the engine answered from fixtures.

The monitor defines no engine type. `hooks/lib/engine.ts` types the documents as far as the mod reads them, skipping what it does not know; the fixtures under `tests/fixtures/` are written by `make_fixtures.py` from a scripted engine run, and the engine test `test_monitor_fixtures_match_the_engine` keeps them in the engine's shape.

## 1. Requirements

| Req | Spec | Criteria | Phase |
|---|---|---|---|
| REQ-32 | MDS | §2.1 run rows, change signal, run-log tail, detail document; §2.2; §2.3; AC-2, AC-3, AC-4 (rates as functions) | T10.2 |
| REQ-32 | MBA | §2.1 to §2.4 but the fleet row; AC-1 (paused row), AC-3 | T10.2 |
| REQ-32 | MRV | §2.3, §2.4; B1, B3 | T10.3 |
| REQ-32 | MDD | §2.1, §2.2 as one page, §2.4 Now and Info; B5 at the engine's switch | T10.3 |

## 2. Phases

✓ means built and tested; ○ means open. Paths are under `plugins/tempergraph-monitor/`.

### T10.2 Monitor sources, band and alerts

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 10.2.1 | `hooks/lib/engine.ts` | Engine document types for status rows, the detail document and run-log records; `isReadable` refuses a newer schema | MDS §2.2, engine C12 | yes | P1 | ✓ | 2026-11-20 |
| 10.2.2 | `hooks/lib/sources.ts` | Read-only argv builders (`status`, `status --detail`), thread id and unit checks, `isReadOnly`; tail reads with partial lines, shrink, the 4 MiB bound and 500 records; poll rates | MDS §2.1–§2.3, AC-2, AC-3, B1 | yes | P1 | ✓ | 2026-11-20 |
| 10.2.3 | `hooks/lib/model.ts` | Run label, mark, money (contract M4), band row, status line, alerts from records and from health, once per `(thread, seq)` | MBA §2, B1–B4 | yes | P1 | ✓ | 2026-11-20 |
| 10.2.4 | `hooks/register.tsx`, `types/index.d.ts` | One 1 s clock: stat and tail live logs, `status --json` at the live or idle rate, `status --detail` for the open run; band `AbovePrompt` row; `$.ui.status`; toasts and notifications with the last alerted `seq` in `$.store`; `/tg`; nothing when `isInteractive` is false | MDS §2.1, MBA §2.2–§2.4, MAC §2.2 | yes | P1 | ✓ | 2026-11-20 |
| 10.2.5 | `tests/monitor.test.tsx` | Session tests: the band names the paused fixture run on terminal and desktop; only `status` and `events` are run; a headless session registers nothing | MBA-AC-1, MDS-AC-2 | yes | P1 | ✓ | 2026-11-20 |
| 10.2.6 | `hooks/register.tsx` | `scope = machine` from `~/.tempergraph/index.json` (needs T10.1 and P-MOD-2), missing roots | MDS §2.1, B4 | yes | P2 | ○ | |
| 10.2.7 | `hooks/register.tsx` | `· stale` after 60 s, the under-20-columns row, `alerts.finished` and `alerts.fleet` as mod settings | MBA §4, §2.4 | yes | P2 | ○ | |
| 10.2.8 | `tests/` | MBA-B2 with two sessions sharing one store; MDS-B5 hash test in a live session; MDS-B1 counts under a replaced clock in a session test | MBA-AC-2, MDS-AC-1, AC-4 | yes | P2 | ○ | |

### T10.3 Monitor run view and drill-down

| Task | File | Code change | Reading set | TDD | Priority | Completed | Date |
|---|---|---|---|---|---|---|---|
| 10.3.1 | `hooks/lib/model.ts` | Run list order, list rows, unit rows with the node strip and trip-back lines, narrator, touch strip, attempt rows, the session Now block | MRV §2.3, §2.4, B1, B3; MDD §2.1, §2.4 | yes | P1 | ✓ | 2026-11-20 |
| 10.3.2 | `hooks/register.tsx` | One pane with the levels runs, run, unit, attempt and session, breadcrumbs, the stale mark, and Back as a footer `Button` with hotkey `b` | MRV §2.1, §2.2; MDD §2.1, §2.2, §2.4 | yes | P1 | ✓ | 2026-11-20 |
| 10.3.3 | `tests/monitor.test.tsx` | `/tg` opens the run list; pressing the fixture run shows its unit rows | MRV-AC-1 (in part) | yes | P1 | ✓ | 2026-11-20 |
| 10.3.4 | `hooks/register.tsx` | Keys of MRV §2.2 bound, filter, pin, map item rows, the mobile reduction | MRV §2.2, §2.3, §2.6, B2, AC-2 | yes | P2 | ○ | |
| 10.3.5 | `hooks/register.tsx` | Attempt tabs, the pause view, Calls from `activity.jsonl`, Processes from `ps`, Log tails, `show.tool_inputs` and `show.log_tails` as settings | MDD §2.2–§2.5, B1–B6, AC-1–AC-3 | yes | P2 | ○ | |
| 10.3.6 | `hooks/register.tsx` | The orchestration view (release 2, with ORC) | MRV §2.5, B4 | yes | P3 | ○ | |

### T10.1 and T10.4

Not started in this pass. T10.1 (machine index, directory sink, fleet copy) is engine work in CST; T10.4 (actions, cost and fleet) needs MAC and MCF to leave `review`.

## 3. Hand-off notes

- The mod API rules met while building, from `claude plugin validate` on 2.1.329: a function that takes `$` is declared at the top of the hooks module, and an atom's reference spells the plugin and key as string literals. Session tests load only code files, so `make_fixtures.py` also writes the fixtures as `tests/fixtures/documents.ts`.
- The session view reads the live block of the detail document (RDD §2.2), refreshed every 2 s with the document, rather than `live.json` every 1 s; MDS §5 says so.
- The monitor writes nothing but its own `$.state` and `$.store` (contract M1); the one `$.process.run` call is behind the read-only guard, which a bun test checks in the source.

## 4. Verification

From `plugins/tempergraph-monitor/`: `bun test ./tests/model.spec.ts` (pure rules against the fixtures), `claude plugin test .` (session tests), `claude plugin validate .`, and a type check with the 2.1.329 types. From `plugins/tempergraph/engine/`: `python -m pytest` includes `test_monitor_fixtures_match_the_engine`. No test calls a model or a live Claude Code session.
