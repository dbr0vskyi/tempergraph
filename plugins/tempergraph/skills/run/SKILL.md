---
name: run
description: Start, check, resume and report tempergraph workflow runs from a person's request. Use when someone asks to run a workflow, continue a paused run, or asks how a run ended. Never answers a pause itself.
---

# Run a tempergraph workflow

The engine does the work and decides nothing for the person. You pick the arguments, start the run, wait for
it to exit, explain the result, and hand every pause back to the person. You know no workflow: read the
catalog.

## Rules

- **The person decides every pause**, one at a time, also the last one, also in auto mode. Never resume on your
  own, never pick a decision word for them.
- **Ask, never guess.** A value the workflow asks for is never defaulted, inferred, or copied from an example.
  Ask the person. Pass their words quoted as one shell word (`--input ticket='…'`).
- **Check before spend.** Run `tempergraph run --check` with the exact arguments first. It spends nothing.
- **Wait, do not poll.** Start the run in the background and wait for the process to exit; a pause exits too.
  For a run you did not start, use one `tempergraph wait <thread>`; never tail logs in a loop.
- **Never edit run state.** To fix a run, resume it, rerun it, or start a new task id.
- The diagram comes from `tempergraph graph`, never from you.

## Procedure

1. **Match.** `tempergraph list` gives the catalog. Pick the workflow, say once what it does and its
   workspace mode, and offer `tempergraph graph <workflow>`. If nothing fits, say so; do not stretch one.
2. **Check.** `tempergraph run <workflow> --check [--input k=v …] <request…>`. It prints one JSON status:
   - `ok`: go on.
   - `needs`: ask the person each listed question (at most four rounds), then check again.
   - `error`: show the refusals' messages; follow them, or stop and tell the person.
   - `broken`: the workflow did not load. Stop and report its reason.
3. **Start.** Say the exact command, then run it in the background with `--json`. If the person asked for a
   retry in advance, add `--auto-reopen N`; never add it unasked.
4. **Report by exit code** (table below). At exit 3, follow [references/pauses.md](references/pauses.md).
5. **Resume** only with the person's decision, and always with `--relayed`, because the decision is theirs:
   `tempergraph resume <workflow> <thread> --decision <word> --relayed [--feedback '…']`.

## Exit codes

| Exit | Meaning | What you do |
|---|---|---|
| 0 | Finished; every unit passed its gate | Report the outcome verdict, cost, branch and pull request if any |
| 2 | Refused; nothing ran or was spent | Read the message and follow it; `run --check` shows the same refusal |
| 3 | Paused for a person | Walk them through it ([references/pauses.md](references/pauses.md)) |
| 4 | Stopped or drained | Say why and offer the resume command the message gives |
| 5 | Retries spent, timeout, loop budget, or infra failure | Never call it a success; after an infra failure never offer `proceed` |
| 127 | Engine not installed | Send the person to the install skill |

## Read-only questions

`tempergraph status [<thread>]`, `tempergraph facts <thread>`, `tempergraph outcome show <workflow>`,
`tempergraph config show <workflow>`, `tempergraph executors`, `tempergraph worktree list`. These spend nothing.

`--dry-run` is not a preview: every step still runs and spends; only the issue filer stays quiet. Say so if
the person asks for one.
