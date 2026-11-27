---
name: operate
description: Operate tempergraph runs as an agent the person has asked to answer pauses itself, for example a batch of runs while the person is away. Use when told to drive, babysit or keep runs going without relaying each pause. For relaying pauses to a person, use the run skill instead.
---

# Operate tempergraph runs as an agent

The person handed you the operator's seat: you start runs, read why they stop and answer pauses that the
repository's own documents settle. Everything else goes back to the person. Read the engine's state through its
verbs, never with scripts of your own.

## Rules

- **Only with a mandate.** Answer a pause yourself only when the person said so for these runs. Without it,
  use the run skill and relay every pause.
- **Every answer is marked as yours.** Pass `--as-agent` on `run` and `resume`, so the ledger counts the
  decision as an agent's, not the person's.
- **Check before spend.** `tempergraph run <workflow> --check …` first, with the exact arguments.
- **Wait, do not poll.** Start each run in the background with `--json` and wait for the process to exit; a
  pause exits too. For several live threads use one `tempergraph wait <thread> <thread> --any`; it returns on
  the first pause or end, not on each gate verdict. Never loop over log files or exit files.
- **Read through the verbs.** `tempergraph status <thread> --detail --unit <unit>`, `tempergraph logs <thread>
  --kind check`, `tempergraph events <thread>`, `tempergraph facts <thread>`. Raw files under `.tempergraph/`
  are the last resort.
- **Never edit run state.** Fix a run by resuming, rerunning or starting a new task id.
- **Never `proceed` after an infrastructure failure** (exit 5): nothing was judged.

## Procedure

1. **Start.** `tempergraph run <workflow> --check …`, then the same command without `--check`, with
   `--json --as-agent`, in the background.
2. **On exit 3**, read what the exit printed: the resume command and the `next` reads. Then:
   - `tempergraph status <thread> --detail --unit <unit>`: the blockers, the failing criteria, the attempts;
   - `tempergraph attention`: everything else that waits, oldest first;
   - decide from the repository's documents (the task's acceptance criteria, then specs and decision
     records, then the plan). A question only the person can answer, or a step that cannot be undone, goes to
     the person with your recommended answer; the run keeps waiting.
   - answer with `tempergraph resume <workflow> <thread> --decision <word> --as-agent`, with
     `--feedback '…'` saying what to change on `retry`. A usage-limit pause takes no decision.
3. **On exit 5**, read `tempergraph status <thread> --detail` and `tempergraph logs <thread>`, then hand the
   cause to the troubleshoot skill or to the person. Do not retry an infrastructure failure more than once.
4. **On exit 0**, report the outcome, cost and branch, then `tempergraph improve review show <thread>` for
   what the loop recorded about the run.
5. **Afterwards**, `tempergraph report --supervision` shows how often runs needed an operator; say which pauses
   you answered and why.

## Exit codes

| Exit | Means | What you do |
|---|---|---|
| 0 | Finished | Report it (step 4) |
| 2 | Refused; nothing was spent | Follow the message; `run --check` gives the same refusal |
| 3 | Paused | Step 2 |
| 4 | Stopped or drained | `tempergraph resume <workflow> <thread> --as-agent` continues a drained thread |
| 5 | Budget spent or infrastructure failure | Step 3 |
| 127 | Engine not installed | Send the person to the install skill |
