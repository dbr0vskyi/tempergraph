---
title: Central run stats
type: component
status: review
prefix: CST
adrs: [0012, 0025]
---

# Central run stats

## 1. Overview

How run numbers from every repository and every machine end up in one place a person can read, without a tempergraph server. Three layers: a **machine index** of state roots, so one machine's runs are listed together; **sinks**, opt-in destinations to which each machine pushes metadata-only rows; a **fleet copy** in each machine's home folder, `~/.tempergraph/fleet/`, into which every machine pulls the rows of all the others, so global stats and metrics sit in the same `.tempergraph` folder on every machine; and an **aggregate reader**, `stats`, that totals them. A sink carries numbers, names from fixed lists and hashes, never request text, outputs, commands or paths (contract C9). Pushing is best effort and never changes a run (contract C2). With no sink configured, nothing leaves the machine, as before ([OBS §2.4](15-observability-and-cost.spec.md)).

## 2. Contract

### 2.1 Machine index

`~/.tempergraph/index.json` ([LOS §2.2](33-local-observability-store.spec.md)), schema version 1: one entry per state root seen by a run on this machine, with path, repository name, `repo_id` (§2.4), `first_seen` and `last_run_at`. Written at `run_started` under a lock, best effort. `status --all-roots` and `stats` read it; an entry whose path is gone is shown as `missing`, never removed by a reader.

### 2.2 Rows

| Row | Written | Fields |
|---|---|---|
| `run` | At every `run_exit` ([EVT §2.2](30-run-events.spec.md)), built by the same function as the stats row and the ledger row so the figures cannot drift | `row_id` (UUID), `schema_version`, `machine_id`, `user` (§2.4), `repo_id`, `workflow`, `workflow_version`, `thread_hash`, `segment`, `alias`, `ticket`, `origin`, `parent` (orchestration id and node, hashed like `thread_hash`), `schedule_id` (hashed the same way, [SCH §2.8](83-schedules.spec.md)), executors and models used, exit code and reason, `units_run`, `repeats` by cause, `gate_verdicts` counts, `escapes`, tokens by kind, `reported_cost_usd`, `estimated_cost_usd`, completeness flag, `wall_s`, `agent_s`, `person_wait_s`; supervision: `touches_undesigned`, `touches_by_decider`, `agent_own_rescues`, `level`, `level_by`, `callers_unknown` ([SUP §2.2](86-supervision-metrics.spec.md)) |
| `heartbeat` | Every 60 s while any thread on the machine is alive, and once when the last one exits; one file replaced atomically | `machine_id`, `label`, `at`, live threads: `repo_id`, `workflow`, `alias`, `state`, current unit, attempt, `estimated_cost_usd` so far, `waiting_for_person_s`, `waiting_on` (`person` or the host of the supervising session that last called) |
| `supervision` | When a thread's supervision cost closes ([SCO §2.5](87-supervision-cost.spec.md)) | `row_id`, `thread_hash`, `workflow`, `workflow_version`, marginal and turn tokens and estimated cost by category, hashed host sessions and their hosts and models, reported session figures, completeness |
| `session` (opt-in, `include: [session]`) | At every `agent_run` | `row_id`, `thread_hash`, `unit`, `kind`, executor, alias, model, tokens, costs, `duration_s`, `outcome`, `tool_calls` count, per-capability counts |

Row field names follow the stats rows already kept per user, so one reader serves both.

### 2.3 Sinks

Configured in user or state-root config as a list; none by default.

| Field | Meaning |
|---|---|
| `name` | Operator's name for it |
| `kind` | `directory`; `otlp` is designed but deferred ([TEL](35-telemetry-export.spec.md), [ADR-0029](../adr/0029-own-observability-first-export-deferred.adr.md)) |
| `path` (directory) | A folder every machine can write: a synced folder, a network share, a mounted bucket |
| `include` | Subset of `run`, `heartbeat`, `supervision`, `session`; default all four ([ADR-0029](../adr/0029-own-observability-first-export-deferred.adr.md)) |
| `user` | `name`, `hash` (default) or `none` |
| `repo` | `name`, `hash` (default) |

**Delivery.** A row is first appended to `~/.tempergraph/outbox/<sink>.jsonl`, then flushed by a detached flusher started at `run_exit` and by `stats flush`. Flushing appends to the sink and removes the row from the outbox only after the sink write returns; a row may be delivered twice and readers de-duplicate by `row_id`. A sink that fails keeps its outbox; after 7 days of failures `status` shows one warning line.

**Sync to the home folder.** Every flush, and `stats sync`, also pulls: for a directory sink it copies new bytes of every other machine's files into `~/.tempergraph/fleet/<sink>/machines/` (append-only files by offset, `heartbeat.json` whole), adds this machine's own rows, de-duplicates by `row_id` and rebuilds `rollup/<YYYY-MM>.json` ([LOS §2.2](33-local-observability-store.spec.md)). A machine that is offline keeps its last copy and says when it was synced. An `otlp` sink is push-only: its fleet copy holds this machine's rows alone, and global numbers come from the backend. The fleet copy is a cache: deleting it loses nothing the sink does not hold.

**Directory sink layout.** Each machine writes only inside its own folder, so a synced folder never sees two writers on one file:

```text
<path>/
  machines/<machine_id>/
    machine.json                 label, engine version, first_seen
    runs/<YYYY-MM>.jsonl         run rows
    sessions/<YYYY-MM>.jsonl     session rows, if included
    heartbeat.json               replaced atomically
```

### 2.4 Identity and privacy

| Item | Rule |
|---|---|
| `machine_id` | Random UUID from `machine.json`; never a host name, MAC or serial |
| Sink key | One secret key per sink, shared by every machine that writes to it, so a hash matches across machines: a directory sink keeps it in `<path>/sink.json`, created by the first machine that writes (owner-only where the share allows); an `otlp` sink reads it from the operator's config. The same key serves the request digests of [IMD-R12](43-improvement-data.spec.md) |
| `user` | `hash` = HMAC-SHA256 of the operator's git `user.email` with the sink key; `name` = the git user name, only when the operator sets it |
| `repo_id` | `hash` = HMAC of the normalized origin URL with the sink key; `name` = the repository's folder name |
| `thread_hash` | HMAC of the thread id; a task id can hold a ticket or a branch name |
| `ticket` | Kept only when the operator sets `sink.tickets = true` |
| Free text | None: `alias` is kept only if it matches `[a-z0-9-]{1,40}`, else dropped |

### 2.5 Aggregate reader

```text
stats [--source <sink> | --local] [--sync] [--month YYYY-MM | --since <date>] [--by machine|user|repo|workflow|version|executor|model|ticket|exit|month|parent|schedule|level|decider|host] [--projection] [--live] [--json]
```

`--projection` adds, per workflow (and version with `--by version`), the median and 90th percentile of estimated cost per finished run and the sample size; the orchestration supervisor reads it for its projected cost ([ORC §2.8](45-orchestration.spec.md) N7). A projection over fewer than 5 runs is shown with its count and marked `thin`.

With no `--source`, `stats` reads the home folder: this machine's rows plus the fleet copy of every configured directory sink, so global numbers need no access to the shared folder at read time. `--local` reads this machine's rows only; `--source` reads the sink folder directly; `--sync` pulls first.

Read-only, model-free (contract C13); `stats sync` writes the fleet copy only. `--live` reads the heartbeats and lists live runs on every machine, marking a heartbeat older than 5 minutes `stale`. Totals keep reported and estimated cost apart and show the completeness flag ([ADR-0012](../adr/0012-cost-when-executor-reports-tokens-only.adr.md)); a total with any incomplete row is a lower bound and says so.

## 3. Behaviours

**CST-B1 Nothing leaves by default.** Given no sink configured, when a run ends, then the outbox is empty and no network or file write happens outside the state root and `~/.tempergraph/`.

**CST-B2 Two machines, one folder.** Given machines A and B both configured with the same directory sink, when each finishes 3 runs, then `stats --source team --by machine` on either shows 3 runs for each, with cost totals equal to the sum of their local stats rows.

**CST-B3 Offline machine.** Given a laptop whose sink folder is unreachable for two days, when it reconnects and a run ends, then the flusher delivers every outbox row once in order, and a reader counts each run once.

**CST-B4 Live across machines.** Given a run paused for a person on machine B for 40 minutes, when `stats --source team --live` runs on machine A, then it lists the run with its workflow, alias, state `paused` and waiting time, and no repository name if the sink hashes names.

**CST-B5 No text.** Given the canary test ([SEC-B2](14-security.spec.md)) with a sink of every kind and `include` of all rows, when runs complete, then no sink file, outbox row or export contains the canary.

| Field planted with the canary | Appears in rows as |
|---|---|
| request text | — |
| alias `fix canary now` | dropped (not a slug) |
| task id `PROJ-1-canary` | `thread_hash` only; `ticket` only with `sink.tickets` |
| tool input `echo canary` | — |

**CST-B7 Global numbers at home.** Given machines A and B sharing a directory sink and A offline since its last sync an hour ago, when `stats --by machine` runs on A, then it reads `~/.tempergraph/fleet/team/`, shows both machines up to that sync, and marks B's figures `synced 1 h ago`; after A reconnects and syncs, B's newer runs appear with no sink read at query time.

**CST-B6 Sink failure is safe.** Given a sink whose write raises, when a run ends, then the exit code is the one it would have had and the row stays in the outbox.

## 4. Error conditions

| Condition | Result |
|---|---|
| Two sinks with one name | Config refused at preflight, exit 2 |
| A row with a newer major schema in a sink | Skipped by the reader and counted under `unknown_schema` |
| A machine folder written by two machines (copied `machine.json`) | Reader warns on duplicate `row_id`s with different content and shows both |
| Index lock not acquired in 2 s | Index not updated this run, recorded |

## 5. Design notes

- No tempergraph server: a folder every machine can write is enough for a small team and needs no service to run or secure; an OTLP sink covers teams that already run a telemetry backend ([ADR-0025](../adr/0025-cross-machine-stats-through-opt-in-sinks.adr.md)).
- One writer per file is what makes a synced folder safe; appends from two machines to one file are what break it.
- Hashing by default means a shared sink shows "repo 3f2a…" until the operator opts into names; that is the price of being able to share it widely.
- A sink is the aggregate the self-improvement loop's data requirements name ([IMD](43-improvement-data.spec.md)): the `run` and `session` rows carry the identifiers of IMD-R1, and the loop's own record kinds may be written to a sink beside them by the same outbox; what crosses follows IMD §2.2 and this spec's §2.4, whichever is stricter.
- The heartbeat makes the sink a monitoring surface, not only a ledger: a person sees what is running and waiting across machines.

## 6. Acceptance criteria

- [ ] CST-AC-1 CST-B1 to CST-B6 pass with two simulated machines (two home folders) writing to one temporary folder.
- [ ] CST-AC-2 Cost totals from `stats --source` equal the sum of the local stats rows of each machine for a fixture month.
- [ ] CST-AC-3 Readers de-duplicate a fixture with every row delivered twice.
- [ ] CST-AC-4 A test with no sink configured asserts no file is created outside the state root and home folder.

## Open questions

| Question | Owner |
|---|---|
| Is a shared folder enough for the owner's machines, or is there a backend the owner already runs (which would make OTLP the main sink)? | Owner |
| Should a team sink also accept rows from CI runners, whose `machine_id` changes every job? The design suggests a fixed `machine.json` in the CI cache. | Owner |

## References

