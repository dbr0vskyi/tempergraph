# Running workflows

## The short version

Ask Claude in plain words: "run doc-refresh on docs/guide.md, the install section". The `run` skill picks the workflow from the catalog, asks for any value the workflow needs (it never guesses one), preflights the run, starts it, and reports how it ended. When the run pauses for a person, it explains the pause and waits for your decision. It never decides for you.

The rest of this guide is the CLI underneath, for when you want to drive runs yourself.

## Find and inspect a workflow

```sh
tempergraph list                       # the workflow catalog
tempergraph graph <workflow>           # the workflow diagram
tempergraph outcome show <workflow>    # what a good result is, and how runs measure against it
tempergraph config show <workflow>     # the settings a run would use
```

## Check, then start

```sh
tempergraph run <workflow> --check [--input key=value …] <request…>
tempergraph run <workflow> [--input key=value …] <request…>
```

`--check` spends nothing. It prints one JSON status: `ok`, `needs` (questions to answer first), `error` (refusals and how to fix them) or `broken` (the workflow did not load).

Useful options on `run`:

| Option | Does |
|---|---|
| `--run-cost-cap USD` | Stop the run before it spends more than this |
| `--auto-reopen N` | Retry the whole run up to N times after a failure |
| `--approve <step>` | Pause for your approval after that step |
| `--model`, `--judge-model` | Pick model aliases for steps and judges |
| `--json` | Machine-readable output, for scripts |

`--dry-run` is not a preview: every step still runs and spends. Only the issue filer stays quiet.

## How a run ends

| Exit | Meaning | What to do |
|---|---|---|
| 0 | Finished; every step passed its gate | Read the outcome verdict, cost and branch |
| 2 | Refused; nothing ran or was spent | Follow the message; `run --check` shows the same refusal |
| 3 | Paused for a person | Decide, then resume (below) |
| 4 | Stopped or drained | Resume with the command the message gives |
| 5 | Retries spent, timeout, loop budget or infrastructure failure | Not a success. Read the logs, then rerun or fix the workflow |
| 127 | Engine not installed | See [Getting started](getting-started.guide.md) |

## Answer a pause

A pause says which step paused, why, the failing criteria, where the output is, and which decisions it accepts:

| Decision | Does |
|---|---|
| `proceed` | Accept the output and go on |
| `retry` | Run the step again, optionally with your feedback |
| `back:<step>` | Send the run back to an earlier step |
| `stop` | End the run |

```sh
tempergraph attention                                     # everything waiting on a person, oldest first
tempergraph resume <workflow> <thread> --decision retry --feedback 'Keep the table, shorten the intro'
```

Use `--ruling` with your feedback when it should hold on every later attempt, not just the next one. Don't `proceed` after an infrastructure failure: nothing was judged.

## Watch and inspect

```sh
tempergraph status [<thread>] [--detail]       # one row per run, or one run in detail
tempergraph wait <thread>                      # block until the run ends or pauses
tempergraph events <thread> [--follow]         # the run log, record by record
tempergraph logs <thread> --kind raw|check|stderr|engine   # raw session and check output
tempergraph facts <thread>                     # read-only facts about a run
tempergraph stop <thread> [--now]              # drain after the current step, or stop now
```

With the `tempergraph-monitor` plugin installed, Claude Code also shows running and paused runs, alerts and cost while you work.

## Rerun from a step

```sh
tempergraph rerun <workflow> <thread> --from <step> --feedback 'Use the 2.x changelog format'
```

A rerun is a new run linked to the old one, starting at the step you name. It asks before repeating anything with an external effect.

## Cost and supervision

```sh
tempergraph report [7d|30d|all] [--by unit|executor|workflow]   # cost and friction
tempergraph report --supervision                                 # how often runs needed a person
tempergraph supervision show                                     # what supervising them cost
```

Every model call is costed. Where Claude Code does not report a cost, the engine estimates it and marks it as an estimate. It never counts it as zero.

## When something goes wrong

Ask Claude: "why did my doc-refresh run fail?" The `troubleshoot` skill reads the run's state and logs without changing anything, and gives you ranked causes with the next command to run.
