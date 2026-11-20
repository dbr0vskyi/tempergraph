---
name: install
description: Install the tempergraph engine on this machine from the plugin, with one plan and one yes. Use when the person says "install tempergraph" or "set up tempergraph", or when a tempergraph command exits 127.
---

# Install tempergraph

You drive the plugin's launcher and the engine's verbs. The verbs decide; you read their JSON and exit codes, never their prose. Show one plan, ask once, then carry the whole plan out.

`<plugin>` is the folder two levels above this skill's base directory (the base directory is `<plugin>/skills/install`).

## Never

- Install an executor CLI, or store or print a credential.
- Edit a shell file without the person's yes: the `PATH` change is part of the plan, and the person may decline it.
- Run a command that is not in the steps below, or put free text the person typed into a command. Values come from the verbs' output.

## Steps

1. **Look.** Run `<plugin>/bin/tempergraph install --check --json`. Each line is one JSON object with a `kind`.
   - `engine` with `state: current`: the engine is already installed. Say so, offer step 6 and stop.
   - `engine` saying no Python 3.11 or newer was found: say that, point the person to python.org or their package manager, and stop.
2. **Executors.** Run `tempergraph executors` only after the install; for now, say that this release runs steps on `claude` (Claude Code) only, and that other executors come later.
3. **Plan.** Show, from step 1's lines: the Python found, the home folder, the environment that will be built, and the `PATH` block with the file it goes in. Ask one question: install, with or without the `PATH` change.
4. **Run.** In the background, with a long timeout, never interrupted:
   - with the `PATH` change: `<plugin>/bin/tempergraph install --json --add-to-path`
   - without it: `<plugin>/bin/tempergraph install --json`, then show the `block` from the `shim` line so the person can add it themselves
   Read the `engine` line: `state: failed` means nothing was switched; quote its reason and stop.
5. **Verify.** Call the shim by the absolute path its `shim` line names, not by `tempergraph` on `PATH` (a new terminal is needed for that):
   - `<shim> workflows list` shows the registered workflows
   - `<shim> executors --probe` shows whether `claude` is installed, signed in and at a tested version. If it is missing or not signed in, say what to install or sign in to, from the probe's facts. Do not do it yourself.
   Quote the `engine` line of step 4 for the version.
6. **Own workflows.** Ask whether the person has workflow sources in their own repositories. For each path they give, run `<shim> workflows register <path> --check`, show the result, and on a yes run `<shim> workflows register <path>`.
7. **Next.** Offer the project bootstrap for the current repository if that skill is installed, and say to open a new terminal.

## Exits

| Exit | Do |
|---|---|
| 0 | Continue |
| 2 | Quote the refusal and its fix; stop |
| 127 from the shim | The install did not finish; run step 1 again and report what it says |
