# The self-improvement loop

The loop files issues from a run's findings into the workflow's issue repository, measures them over later runs, and proposes changes. It is built after the core run loop, so on this engine some of its verbs may not exist yet: list each refused verb under "not investigated".

| Check | How |
|---|---|
| The workflow names an issue repository | `tempergraph validate <workflow>`; a missing `issue_repository` is a validation error |
| Runs are allowed to file issues | `settings_resolved` in `run.jsonl` shows the self-improvement mode and whether filing is on |
| The run reached the point where findings are filed | `run_exit` reason; a run that stopped early files nothing |
| Signals exist for an outcome revision | `tempergraph outcome show <workflow> --runs`; `tempergraph outcome candidates <workflow>` lists them |

Never file, close or edit an issue yourself. Name the command the person would run.
