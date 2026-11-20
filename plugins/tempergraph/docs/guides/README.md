# tempergraph guides

How-to guides for people who use tempergraph: install it, run workflows, create your own and improve them over time. The design behind each step is in the [specs](../specs/00-overview.spec.md); these guides only say what to do.

> [!NOTE]
> Release 1 is built and tested offline. It has not yet been run against a live Claude Code session, so the commands here come from the code and its tests, not from a live run. The pending checks are in [live-checks.plan.md](../plans/live-checks.plan.md).

| Guide | Read it when you want to |
|---|---|
| [Getting started](getting-started.guide.md) | Install tempergraph, prepare a repository, and try an example workflow |
| [Running workflows](running-workflows.guide.md) | Start a run, answer its pauses, see what it did and what it cost |
| [Authoring workflows](authoring-workflows.guide.md) | Turn a process, script, template or idea into a workflow you can trust |
| [Improving workflows](improving-workflows.guide.md) | Label judgements, calibrate judges, and let the self-improvement loop propose measured changes |

Every guide shows two ways to work: ask Claude in plain words, and the plugin's skills drive the engine for you; or run the `tempergraph` CLI yourself. Both do the same thing, because the skills only call the CLI.
