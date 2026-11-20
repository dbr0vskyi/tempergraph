# Refused starts and resumes, run state, and leaked test state

## Exit 2

A refusal spent nothing and created nothing. Its message names the cause and usually the fix. Read the message first; do not guess past it.

| Often | Look at |
|---|---|
| An input is missing or does not resolve | The workflow's start examples (`tempergraph list`), and the request given |
| A thread with this id is live | `tempergraph status`; a held lock under `.tempergraph/locks/` |
| A resume with a decision the pause does not offer | `tempergraph facts <thread>`: the pending gate and its decisions |
| Preflight: the executor is missing or not signed in | `tempergraph executors --probe` |
| The workflow does not load | The install and workflows reference |

## Run state

- `tempergraph status` lists threads with their state; `tempergraph facts <thread>` gives one thread's exit, reason, pending gates and next step.
- The checkpoint store is `.tempergraph/checkpoints/<workflow>.sqlite`. Never open it for writing.
- A held lock means a process owns the thread. `ps` shows whether it still runs. A lock whose process is gone is reported, and the person decides.

## Leaked test state

Fixture runs in the real state root (a workflow name the person does not recognise, or a test suite stopped by the state-root guard): give the person two commands, a dry-run listing first and then a removal, with the ledger backed up first and nothing removed while a run is live. Never suggest removing a registered workflow's state, an entry with a held lock, or an entry changed in the last hour.
