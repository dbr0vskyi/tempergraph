# Raw run statistics

This branch (`dbr0vskyi/stats`) holds raw statistics files that tempergraph and temperspec workflow runs left on the machines that ran them. It shares no history with the code branches. Nothing here is aggregated: each file is a copy of a file the engine or the operator wrote, so any later analysis can start from the same records.

Each machine has its own folder, so another agent can add its machine beside the existing ones.

## Layout

```
README.md
MANIFEST.json                   one entry per data file: path, bytes, lines, sha256, source pattern, collected-at (UTC)
tools/collect.py                the collector that produced machines/<machine-id>/
machines/<machine-id>/<path under the user's home>/...
```

The path below `machines/<machine-id>/` mirrors the source path relative to the home folder of the machine. A state root that is not under the home folder goes under `machines/<machine-id>/_outside_home/<absolute path>/`.

## Machines

| id | hardware | system | collected (UTC) |
|---|---|---|---|
| `pi5-a` | Raspberry Pi 5 Model B, 4 cores (aarch64), 16 GB memory | Linux 6.12, Python 3.13, engine 0.2.0, executor `claude` | 2026-11-27 |
| `laptop-a` | MacBook Pro, Apple M3 Pro, 12 cores (arm64), 18 GB memory | macOS 27.2, Python 3.14, engine 0.2.0, executor `claude` | 2026-11-27 |

`pi5-a` ran 21 `temperspec` threads against this repository between 2026-11-25 and 2026-11-27 (`i123` to `i206`), one `demo` thread, and several stand-in test runs. Two threads (`i196`, `i206`) were still running at collection time, so their files are snapshots.

`laptop-a` ran 9 `temperspec` threads against this repository on 2026-11-25 (`i7` to `i148`): 514 files, 2.1 MB, 502 replacements, same layout as `pi5-a` with the state root at `~/Projects/homelab/tempergraph/.tempergraph/`. It has no operator folder. Only the 25 rows of `~/.tempergraph/stats/` with `repo` equal to `tempergraph` are real runs; the other 110 (`user` `Test`, or a `repo` such as `repo`, `r`, `a`) come from test runs of the engine's suite whose state roots no longer exist, and so do the matching rows of `stats/sessions/` and the `index.json` roots under `/private/var/folders/`. Filter them out for cost or duration figures. One file was left out by the collector's guard: `runs/temperspec/i21/carry.local.json`, whose `error` field holds multi-line command output.

## Datasets

The engine specifications that define these files are on the code branches under `plugins/tempergraph/docs/specs/`: `local-observability-store`, `central-run-stats`, `run-events`, `observability-and-cost`.

For `pi5-a`: 2,426 files, 5.2 MB.

### Home folder: `~/.tempergraph/` and `~/tg-runs/verify-home/`

`~/tg-runs/verify-home/` is a second home folder that the operator used for verification runs. It has the same layout.

| file | rows | content |
|---|---|---|
| `stats/<YYYY-MM>.jsonl` | 125 + 2 | One row per run segment, metadata only. Fields: `row_id`, `kind`, `schema_version`, `machine_id`, `user`, `label`, `repo`, `state_root`, `workflow`, `workflow_version`, `thread_id`, `ticket`, `segment`, `origin`, `parent`, `schedule_id`, `alias`, `executors[]`, `models[]`, `exit_code`, `reason`, `completeness`, `ended_at`, `wall_s`, `agent_s`, `person_wait_s`, `sessions`, `reported_sessions`, `estimated_sessions`, `unmeasured_sessions`, `units_run`, `reported_cost_usd`, `estimated_cost_usd`, `tokens.{input,output,cache_read,cache_write,thinking}_tokens`, `gate_verdicts.{PROCEED,RETRY,BACK,ESCALATE}`, `repeats.{proceed,retry,back}`, `level`, `level_by`, `touches_by_decider.*`, `touches_undesigned`, `agent_own_rescues`, `callers_unknown`, `escapes`. |
| `stats/sessions/<YYYY-MM>.jsonl` | 1,725 + 44 | One row per agent session. Fields: `row_id`, `kind`, `schema_version`, `machine_id`, `state_root`, `workflow`, `workflow_version`, `thread_id`, `segment`, `unit`, `session_kind`, `executor`, `model`, `outcome`, `ended_at`, `duration_s`, `tool_calls`, `slow_host`, `reported_cost_usd`, `estimated_cost_usd`, `tokens.*`. |
| `index.json` | | The machine index of state roots: `roots[].{path, repository, first_seen, last_run_at}`. |
| `registry.json` | | Registered workflows: `workflows[].{name, kind, path, version, workflow_version, requirements_digest, engine_pin, state, registered_at, last_checked_at}`. |
| `machine.json`, `manifest.json` | | Machine id, label and creation time; home layout and engine version. |
| `ledger.jsonl`, `runs/demo/T-1/...` | | The ledger and the run files of the one `demo` thread that ran with the home folder as its state root. Same schemas as below. |

### State root: `~/projects/tempergraph/.tempergraph/`

| file | files | rows | content |
|---|---|---|---|
| `ledger.jsonl` | 1 | 178 | One row per run segment, intervention, improvement loop pass and label. `kind` is `run_segment` (83), `intervention` (53), `loop` (33) or `label` (9). A `run_segment` row has `ts`, `machine`, `repo`, `workflow`, `workflow_version`, `thread_id`, `origin`, `stage`, `exit_code`, `reason`, `settings_digest`, `overridden_keys[]`, `cost.{reported, estimated, completeness, incomplete, counters.*}`, `outcome.{verdict, revision, criteria[].{id, class, severity, status, trust, grader}, intermediate[].{id, unit, status}}`, `supervision.{level, level_by, person_wait_s, latency_s, touches.{designed,engine,rescue,steer}.<decider>, rescue_by_pause.*, relayed.*, supervisors.*}`. An `intervention` row has `id`, `decision`, `pause_kind`, `cause`, `caller.{kind, host, host_session, call_id, confidence, decided_by, relay, evidence[]}`; its `feedback` and `ruling` fields are null in every row. A `label` row has `run_id`, `label_id`, `label_kind`, `gate_verdict`, `criterion_id`, `binding.*`. |
| `runs/<workflow>/<thread>/exit.json` | 21 | | `exit_code`, `reason`, `schema_version`. |
| `runs/<workflow>/<thread>/engine.json` | 21 | | Engine versions the thread ran on: `started_on`, `last_on`, `pinned`, `history[].{engine, engine_version, workflow_version, checkpoint_format, shape_digest, started_at, units.<unit>.{kind, digest, produces[]}}`. |
| `runs/<workflow>/<thread>/carry.local.json` | 21 | | State of the run-state branch: `state`, `branch`, `commit`, `seq`, `remote`, `lease.*`, `work_branch`. |
| `runs/<workflow>/<thread>/pause-workspace.json` | 2 | | `head` commit at a pause. |
| `runs/<workflow>/<thread>/loop.jsonl` | 19 | 3,170 | Events of the improvement loop. `kind` is `review_session`, `review_done`, `loop_result`, `review_skipped`, `loop_started`, `review_planned`, `loop_summary`, `loop_judged` or `issue_filed`. Fields: `ts`, `session_key`, `reviewed`, `executor`, `alias`, `effort`, `ok`, `cost_usd`, `reported`, `kept`, `none_found`, `fingerprint(s)`, `op`, `reason`, `observations[].{category, check, confidence, corroborated, remedy_class, turns[]}`, `answers[].*`, `targets[].*`, `top[].*`, `usage.*`, `cap_usd`, `estimate_tokens`, `url`. Categories and classes are enums; there is no review text. |
| `runs/<workflow>/<thread>/sessions/<session>/meta.json` | 1,093 | | `session_key`, `kind`, `executor`, `alias`, `model`, `cli_version`, `session_id`, `started_at`, `ended_at`, `pgid`, `transcript.*` (the path of the session log, which is not published). |
| `runs/<workflow>/<thread>/sessions/<session>/digest.json` | 1,083 | | Per-session measures: `turns`, `peak_context`, `turns_over_200k`, `tokens_before_first_write`, `files_reread`, `changed_read`, `changed_total`, `outside_workspace`, `shell_for_files`, `cd_before_git`, `prior_overlap`, `capture`, `end.state`, `tools.<tool>.{capability, calls, failures, refused, duration_s}`, `repeats[].{tool, target, error_class, count, first_turn, last_turn}`, `idle_spans[].*`, `declared_unused[]`. `reads[]`, `_wrote[]`, `_commands[]` and `repeats[].target` are 16-character digests, not paths or commands. |
| `manifest.json` | 1 | | State root layout and engine version. |

### Stand-in state roots

`machines/pi5-a/tg-runs/tmp/...` and `machines/pi5-a/_outside_home/var/tmp/...` hold the `ledger.jsonl` and `loop.jsonl` files (29 each) of the state roots that the home index lists and that still existed. They belong to stand-in test runs of the engine (`standin-repo`, thread `STANDIN-1`), not to real work. The rows of `~/.tempergraph/stats/` with `repo` equal to `standin-repo` refer to them. Filter them out for cost or duration figures of real runs.

### Operator folder: `~/tg-runs/`

| file | files | content |
|---|---|---|
| `<thread>-<verb><n>.exit` | 82 | The exit code of one engine command the operator launched (`run`, `resume`, `stop`), as one number. The file name gives the thread and the command; the file time is not kept, so use the ledger for timing. |

## What was changed in the copies

The files are raw: original file names, original line format, no field dropped, no row dropped. The collector makes these edits only:

1. The absolute home prefix becomes `~`. On `pi5-a` two prefixes were replaced: the home folder of the Pi, and the macOS home prefix of the owner's other machine, which 67 `meta.json` files of threads carried over from that machine contain.
2. The machine host name becomes the machine id (`pi5-a`). It occurs in `machine.json` as `label`.
3. A `.jsonl` file that was being appended to during the copy is cut at its last complete line.

For `pi5-a` this was 2,643 replacements. `MANIFEST.json` records the sha256 of each file as published, after these edits.

Kept as written: `machine_id` (a random UUID made by the engine), `user` in the stats rows (the git author name of the machine, already public in this repository's commits), branch names, commit ids, issue and pull request URLs of this public repository, and repository-relative paths.

## What is not here, and why

These sources exist on `pi5-a` and were left out on purpose. They hold prompt text, model output, judge prose, operator feedback or command output, and nobody has reviewed that text for publication.

| source | files | size | why |
|---|---|---|---|
| `runs/*/*/run.jsonl` | 21 | 5.0 MB, 7,187 rows | Mostly ids and numbers (364 distinct fields), but these fields carry text: `evidence` (745 values, up to 200 characters of judge prose), `signals.gap_finding*` (up to 60 characters of model output), `reason`, `manual_steps[]`, `resume`. |
| `runs/*/*/command_runs.jsonl` | 21 | 0.9 MB, 528 rows | `run.tail` is command output (up to 4,671 characters); `run.argv[]` is the command line. |
| `runs/*/*/findings.json` | 21 | 0.6 MB | `findings[].remedy` is a sentence (up to 136 characters); the other fields are ids and numbers. |
| `runs/*/*/evidence/record.json`, `evidence/judgements/`, `evidence/review/`, `evidence/prompts/` | 1,638 | 6.6 MB | Prompts, step values, judge verdict text, operator feedback. |
| `runs/*/*/sessions/*/activity.jsonl`, `live.json` | 1,095 | 13.9 MB | `text`, `last_line`, `input_summary`: model output and tool input. |
| `runs/*/*/sessions/*/raw.jsonl`, `stderr.log` | 2,052 | 326 MB | Full session transcripts. |
| `runs/*/*/loop/sessions/*/` (`raw.jsonl`, `activity.jsonl`, `live.json`) | 2,976 | 24.6 MB | Transcripts of the improvement loop's review sessions. |
| `runs/*/*/checks/**/*.out`, `finalizer/*.out` | 2,560 | 24.3 MB | Command output of checks. |
| `runs/*/*/answers/ask_owner.json` | 1 | 103 B | An owner's answer. |
| `checkpoints/*.sqlite*` | 4 | 451 MB | Checkpoint databases; they hold step values and are over the size limit. |
| `tickets/*.json`, `locks/` | 27 | 96 KB | Check tickets with step values; lock files. |
| `~/tg-runs/*.log` | 85 | 360 KB | Operator launch logs with engine output and blocker text. |
| `~/tg-runs/filing-outbox.held-*.jsonl` | 2 | 144 KB | Held issue drafts. |
| `~/tg-runs/*.md`, `drafts/`, scripts, `df.txt`, `seen.txt` | 75 | 0.2 MB | Operator notes, feedback files, issue drafts, helper scripts. |
| `~/tg-runs/stats/` (`build.py`, `data.json`, `tables.md`, ...) | 7 | 172 KB | An earlier aggregated build, not raw data. `data.json` also has text fields. |
| `~/tg-runs/tmp/` other than the stand-in ledgers | about 3,000 | 28 MB | Scratch: repository copies, test folders, stand-in session logs. |
| `.tempergraph/` in the run worktrees | 20 | 0.5 MB | Review inputs (`change.diff`, `criteria.md`, `capabilities.md`), no statistics. |
| `~/.tempergraph/engines/`, `bin/`, `request_key` | | 1.9 GB | Installed engine copies and a key file. Never read. |

No credential file, `.env` file or key file was read.

## Add a machine

1. Check out this branch in its own worktree:
   `git fetch origin dbr0vskyi/stats && git worktree add ../stats-branch dbr0vskyi/stats`
2. Pick a short machine id that says nothing private (`laptop-a`, `desk-b`), then run the collector from the worktree. Name every tempergraph home folder, every state root, and the operator folder if there is one:

   ```
   python3 tools/collect.py --machine-id <id> --home ~ \
       --tempergraph-home ~/.tempergraph \
       --state-root <main checkout>/.tempergraph --state-roots-from-index \
       --ops-dir <folder with *.exit files>
   ```

   Add `--dry-run` first to see what would be copied. Add `--home-alias <prefix>` for each foreign home prefix the data may contain.
3. Read the lines that start with `LEFT OUT`. The collector leaves out any file with free text, a secret pattern, an e-mail address or a remaining absolute home path. Do not force such a file in; report it.
4. Add a row to the Machines table above, then commit `machines/<id>/` and `MANIFEST.json` and push. The collector replaces only the manifest entries of the machine id it was given.
