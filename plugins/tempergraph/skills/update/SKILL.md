---
name: update
description: Update the tempergraph plugin and engine on this machine, with one plan and one yes, and report what each registered workflow needs afterwards. Use when the person says "update tempergraph" or asks whether tempergraph is up to date.
---

# Update tempergraph

You drive Claude Code's plugin commands, the updated plugin's launcher and the engine's verbs. The verbs decide; you read their JSON and exit codes, never their prose. Show one plan, ask once, then carry the whole plan out.

`<plugin>` is the folder two levels above this skill's base directory (the base directory is `<plugin>/skills/update`). `<shim>` is the engine command the install step put on the machine; call it by its absolute path when `tempergraph` is not on `PATH`.

## Never

- Pull, commit or change a repository of the person's.
- Stop a run or answer a pause. A run that is in progress keeps the engine it started on.
- Run a workflow upgrade without the person's yes to its cost.
- Run a command that is not in the steps below, or put free text the person typed into a command. Values come from the verbs' output.

## Steps

1. **Look.** Read the plugin's version from `<plugin>/.claude-plugin/plugin.json`. Run `<shim> update --check --json` and `<shim> workflows list`. Each line of the first is one JSON object with a `kind`.
2. **Plan.** Show in one view what will run, in order:
   - `claude plugin marketplace update tempergraph`, and the same for the marketplace of each workflow whose registry entry has kind `plugin`
   - `claude plugin update tempergraph@tempergraph`, and the same for each such workflow plugin, at the scope it was installed with
   - the engine update from the updated plugin copy
   Ask one question: go ahead with all of it.
3. **Plugins.** Run the marketplace updates, then the plugin updates. If one fails (offline, not signed in), say so and continue with the plugin copy that is installed: it may already carry a newer engine.
4. **New copy.** Find the updated plugin copy: the folder Claude Code reports for the plugin after the update. Run `<new plugin>/bin/tempergraph update --check --json` and show its lines: the `engine` line (what will be installed), `extras`, each `run` line (a live run that keeps its engine), each `thread` line (a thread that moves or stays pinned), each `store` line (a store that migrates when the new engine first writes to it) and each `workflow` line (reinstalled, or pinned to the old engine and why). If this differs from what step 2 showed in a way that costs or risks something, ask again.
5. **Run.** In the background, with a long timeout, never interrupted: `<new plugin>/bin/tempergraph update --json`. Read the `summary` line and quote it.
6. **Workflows.** Read the `workflow` lines.
   - Pinned, with a local source: offer the upgrade skill for it, after `<shim> upgrade <workflow> --check --format json` shows what the upgrade would do. An upgrade with assisted or owner items spends money; name the cost cap.
   - Pinned, from a marketplace: say it keeps working on the pinned engine until its owner ships an update.
   - A dependency could not be installed: quote the reason; `<shim> workflows reinstall <workflow>` retries it once the cause is fixed.
7. **Executors.** Run `<shim> executors`. For an executor whose version is outside the tested range, say so and name its own updater for the person to run.
8. **Close.** One summary: what changed, what keeps an older engine and why, and what the person still has to do: `/reload-plugins` or a new session for the updated plugin, a new terminal, an upgrade they declined.

## Exits of `update`

| Exit | Do |
|---|---|
| 0 | Continue. `engine` with decision `up_to_date` and no plugin change: say everything is current and list only the workflow lines that need something |
| 1 | The old engine is still current and unchanged. Quote the reason and offer the troubleshoot skill |
| 2 | Refused. A downgrade: quote the cause and the fix from the `engine` line, and never offer to force it |

## Going back

`tempergraph update --rollback --json` makes the previous engine current again. It is refused when a store was moved to a layout the previous engine cannot read; `--restore-backups` restores such a store only while no run has written to it since. Show the refusal as it is and let the person decide. `tempergraph update --prune-engines --json` removes engines that no run, thread, workflow or pointer names; offer it only when the person asks to free space.
