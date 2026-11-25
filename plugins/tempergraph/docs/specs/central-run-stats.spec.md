# Central run stats

## Purpose

How run numbers from every repository and every machine end up in one place a person can read, without a tempergraph server: a machine index of state roots, so one machine's runs are listed together; sinks, opt-in destinations to which each machine pushes metadata-only rows; a fleet copy in each machine's home folder, `~/.tempergraph/fleet/`, into which every machine pulls the rows of all the others; and an aggregate reader, `stats`, that totals them. A folder every machine can write is enough for a small team, and one writer per file is what makes a synced folder safe ([ADR `cross-machine-stats-through-opt-in-sinks`](../adr/cross-machine-stats-through-opt-in-sinks.adr.md)). A sink carries numbers, names from fixed lists and hashes, never request text, outputs, commands or paths (OVR-B11); hashing by default means a shared sink shows "repo 3f2a…" until the operator opts into names. Pushing is best effort and never changes a run (OVR-B4). With no sink configured nothing leaves the machine ([OBS](observability-and-cost.spec.md)). A sink is the aggregate the improvement data names ([IMD](improvement-data.spec.md)); what crosses follows IMD and CST-B11, whichever is stricter. Operators, teams sharing a sink, the orchestration supervisor and the monitor depend on these rows; release 1 build notes are kept in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### CST-B8 Machine index

WHEN a run starts THE engine SHALL write, best effort, one entry per state root seen on this machine in `~/.tempergraph/index.json` ([LOS-B10](local-observability-store.spec.md), schema version 1) with path, repository name, `repo_id`, `first_seen` and `last_run_at`, under a lock taken with exclusive create, skipping the update and recording it when the lock is not had in 2 s; `status --all-roots`, `attention --all-roots` and `stats` read it and show an entry whose path is gone as `missing`, never removing it.

- GIVEN an index entry whose folder was deleted WHEN `status --all-roots` runs THEN it shows `missing` and the entry stays

### CST-B9 Rows

WHEN a row is built THE engine SHALL build a `run` row at every `run_exit` ([EVT-B15](run-events.spec.md)) by the same function as the stats row and the ledger row, with `row_id` (UUID), `schema_version`, `machine_id`, `user`, `repo_id`, `workflow`, `workflow_version`, `thread_hash`, `segment`, `alias`, `ticket`, `origin`, `parent` and `schedule_id` (hashed like `thread_hash`, [TCK](schedule-ticks-and-unattended-fires.spec.md)), executors and models used, exit code and reason, `units_run`, `repeats` by cause, `gate_verdicts` counts, `escapes`, tokens by kind, `reported_cost_usd`, `estimated_cost_usd`, completeness flag, `wall_s`, `agent_s`, `person_wait_s` and the supervision fields `touches_undesigned`, `touches_by_decider`, `agent_own_rescues`, `level`, `level_by` and `callers_unknown` ([SUP](supervision-metrics.spec.md)); a `heartbeat` (one file replaced atomically, at `run_started`, `pause` and `run_exit` and at most every 60 s while a thread is alive) with `machine_id`, `label`, `at` and the running and paused threads (`repo_id`, `workflow`, `alias`, `state`, current unit, attempt, `estimated_cost_usd` so far, `waiting_for_person_s`, `waiting_on`); a `supervision` row when a thread's supervision cost closes ([SCO](supervision-cost.spec.md)) with `row_id`, `thread_hash`, `workflow`, `workflow_version`, marginal and turn tokens and estimated cost by category, hashed host sessions with their hosts and models, reported session figures and completeness; and, opt-in, a `session` row per `agent_run` with `row_id`, `thread_hash`, `unit`, `kind`, executor, alias, model, tokens, costs, `duration_s`, `outcome` and `tool_calls` count; field names follow the per-user stats rows so one reader serves both.

- GIVEN a run exit WHEN its `run` row and stats row are compared THEN their figures are equal

### CST-B10 Sinks configured

WHEN sinks are configured in `config/sinks.json` of the home folder or the state root (`{"schema_version": 1, "sinks": [...]}`, none by default, a state-root entry replacing the home entry of the same name) THE engine SHALL read each sink's `name` (a slug), `kind` (`directory`; `otlp` is designed and deferred, [TEL](telemetry-export.spec.md), [ADR `own-observability-first-export-deferred`](../adr/own-observability-first-export-deferred.adr.md)), `path` (a folder every machine can write), `include` (a subset of `run`, `heartbeat`, `supervision`, `session`, default the first three, `session` only when named), `user` (`name`, `hash` by default, or `none`) and `repo` (`name` or `hash` by default), and refuse two sinks with one name in the `stats` verbs and skip them in a run.

- GIVEN two sinks named `team` WHEN `stats` runs THEN it exits 2

### CST-B11 Identity and privacy

WHEN a row is delivered to a sink THE engine SHALL identify the machine by the random UUID of `machine.json` (never a host name, MAC or serial), hash with one secret key per sink shared by every machine writing to it (kept in `<path>/sink.json`, created owner-only where the share allows by the first machine that writes, and the same key for the request digests of [IMD-B16](improvement-data.spec.md)), set `user` to the HMAC-SHA256 of the operator's git `user.email` (or the git user name only when the operator sets `name`), `repo_id` to the HMAC of the origin URL with scheme, credentials and `.git` removed (or `folder:<name>` without an origin), `thread_hash` to the HMAC of the thread id, keep `ticket` only with `sink.tickets = true`, keep `alias` only when it matches `[a-z0-9-]{1,40}`, and drop every free-text field, the row's `label` included; the local stats row keeps `thread_id`, `repo` and `state_root` in plain text because it never leaves the machine.

- GIVEN alias `fix canary now` WHEN a row is delivered THEN the alias is dropped
- GIVEN task id `PROJ-1-canary` WHEN a row is delivered THEN only `thread_hash` carries it, and `ticket` only with `sink.tickets`

### CST-B12 Delivery through the outbox

WHEN a row is due for a sink THE engine SHALL append a reference to the local row (`row_id`, month, state root, never the row) to `~/.tempergraph/outbox/<sink>.jsonl`, and a detached flusher started at `run_exit` (or `TEMPERGRAPH_FLUSHER=inline|off`), or `stats flush`, SHALL build the sink row with the key at delivery, append it inside `machines/<machine_id>/` only (`machine.json` with label, engine version and `first_seen`, `runs/<YYYY-MM>.jsonl`, `sessions/<YYYY-MM>.jsonl`, `supervision/<YYYY-MM>.jsonl`, `heartbeat.json` replaced atomically), remove the reference only after the write returns, treat a missing sink path as `unreachable` creating nothing there, and keep a failing sink's outbox, `status` showing one warning line after 7 days of failures.

- GIVEN a sink path that does not exist WHEN the flusher runs THEN nothing is created there and the outbox is kept

### CST-B13 Sync to the home folder

WHEN a flush or `stats sync` runs for a directory sink THE engine SHALL copy new bytes of every other machine's files into `~/.tempergraph/fleet/<sink>/machines/` (append-only files by offset, `heartbeat.json` whole), add this machine's own rows, de-duplicate by `row_id`, rebuild `rollup/<YYYY-MM>.json` and record the sync in `synced.json`; an offline machine keeps its last copy and says when it was synced, and the fleet copy is a cache whose deletion loses nothing the sink holds.

- GIVEN the fleet copy deleted WHEN `stats sync` runs THEN it is rebuilt from the sink

### CST-B14 Aggregate reader

WHEN `stats [--source <sink> | --local] [--sync] [--month YYYY-MM | --since <date>] [--by machine|user|repo|workflow|version|executor|model|ticket|exit|month|parent|schedule|level|decider|host] [--projection] [--live] [--json]` runs THE engine SHALL read, read-only and model-free (OVR-B15), the home folder (this machine's rows plus the fleet copy of every directory sink) with no `--source`, this machine only with `--local`, the sink folder directly with `--source`, pulling first with `--sync`; keep reported and estimated cost apart with the completeness flag, a total with any incomplete row being a lower bound that says so ([ADR `cost-when-executor-reports-tokens-only`](../adr/cost-when-executor-reports-tokens-only.adr.md)); group `--by machine` by label and the first 8 characters of `machine_id`; and drop a repeated `row_id`, skip and count under `unknown_schema` a row of a newer major schema, and keep twice and list in `duplicate_row_ids` with a warning a repeated `row_id` whose content differs.

- GIVEN a fixture with every row delivered twice WHEN totalled THEN each run counts once
- GIVEN two rows with one `row_id` and different exit codes WHEN read THEN both are shown and listed in `duplicate_row_ids`

### CST-B15 Projection

WHEN `stats --projection` runs THE engine SHALL add per workflow (and version with `--by version`) the median and 90th percentile of estimated cost per finished run, falling back to the reported cost for a run with no estimate, with the sample size, marking a projection over fewer than 5 runs `thin`; the orchestration supervisor reads it ([ORC](orchestration.spec.md)).

- GIVEN 3 finished runs of a workflow WHEN projected THEN the projection is marked `thin` with count 3

### CST-B16 Live view

WHEN `stats --live` runs THE engine SHALL list live runs on every machine from the heartbeats, mark a beat `stale` when it is older than 5 minutes and lists a running thread (a paused thread has no process to beat for it), and add the beat's age to a paused wait.

- GIVEN a beat 6 minutes old listing only paused threads WHEN read THEN it is not stale

### CST-B1 Nothing leaves by default

WHEN a run ends with no sink configured THE engine SHALL leave the outbox empty and write nothing outside the state root and `~/.tempergraph/`.

- GIVEN no sink WHEN a run ends THEN no file is created outside the state root and home folder

### CST-B2 Two machines, one folder

WHEN machines A and B, both configured with the same directory sink, each finish 3 runs THE engine SHALL show, by `stats --source team --by machine` on either, 3 runs for each with cost totals equal to the sum of their local stats rows.

- GIVEN 3 runs on each of A and B WHEN `stats --source team --by machine` runs THEN each shows 3 runs

### CST-B3 Offline machine

WHEN a laptop whose sink folder was unreachable for two days reconnects and a run ends THE flusher SHALL deliver every outbox row once in order, and a reader SHALL count each run once.

- GIVEN two days of queued rows WHEN delivered THEN each run is counted once

### CST-B4 Live across machines

WHEN `stats --source team --live` runs on machine A while a run has been paused for a person on machine B for 40 minutes THE engine SHALL list the run with its workflow, alias, state `paused` and waiting time, and no repository name when the sink hashes names.

- GIVEN a hashing sink WHEN the live run is listed THEN no repository name appears

### CST-B5 No text

WHEN runs complete under the canary test ([SEC-B2](security.spec.md)) with a sink of every kind and every row included THE engine SHALL keep the canary out of every sink file, outbox row and export.

- GIVEN request text or a tool input `echo canary` WHEN rows are delivered THEN neither appears

### CST-B7 Global numbers at home

WHEN `stats --by machine` runs on machine A, offline since its last sync an hour ago, while A and B share a directory sink THE engine SHALL read `~/.tempergraph/fleet/team/`, show both machines up to that sync and mark B's figures `synced 1 h ago`, and after A reconnects and syncs show B's newer runs with no sink read at query time.

- GIVEN A offline for an hour WHEN `stats --by machine` runs THEN B's figures are marked `synced 1 h ago`

### CST-B6 Sink failure is safe

WHEN a sink's write raises at a run's end THE engine SHALL keep the exit code the run would have had and the row in the outbox.

- GIVEN a raising sink WHEN a run ends THEN its exit code is unchanged and the row stays queued

## Acceptance criteria

- CST-AC1 (CST-B1, CST-B2, CST-B3, CST-B4, CST-B5, CST-B6, CST-B7, CST-B11, CST-B12, CST-B13): The behaviours pass with two simulated machines (two home folders) writing to one temporary folder
- CST-AC2 (CST-B9, CST-B14): Cost totals from `stats --source` equal the sum of the local stats rows of each machine for a fixture month
- CST-AC3 (CST-B14): Readers de-duplicate a fixture with every row delivered twice
- CST-AC4 (CST-B1): A test with no sink configured asserts no file is created outside the state root and home folder
- CST-AC5 (CST-B8, CST-B10, CST-B15, CST-B16): The index marks a gone path `missing`, a duplicate sink name is refused, a thin projection is marked, and a stale beat is marked only when it lists a running thread

## Open questions

- Is a shared folder enough for the owner's machines, or is there a backend the owner already runs (which would make OTLP the main sink)? Owner: owner.
- Should a team sink also accept rows from CI runners, whose `machine_id` changes every job? The design suggests a fixed `machine.json` in the CI cache. Owner: owner.
