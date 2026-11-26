# Lifecycle skills for install, update and upgrade

## Purpose

Three skills of the `tempergraph` plugin let a person say "install tempergraph", "update tempergraph" or "upgrade my workflow" to their agent and have it done. Each skill drives the CLI verbs that do the work: `install` and `update` ([UPD](engine-update.spec.md)), `workflows` ([UPD-B24](engine-update.spec.md)) and `upgrade` ([WUP](workflow-upgrade.spec.md)); the update skill also runs Claude Code's own plugin commands, because the engine cannot update the plugin that carries it ([research `updating-a-tool-with-long-lived-runs`](../research/updating-a-tool-with-long-lived-runs.rsrch.md) U1). The rule of the shell holds: a skill drives, the verbs decide ([SHL](plugin-shell.spec.md), [ADR `lifecycle-skills-drive-plugin-commands-then-engine-verbs`](../adr/lifecycle-skills-drive-plugin-commands-then-engine-verbs.adr.md)). A skill reads the verbs' JSON and exit codes, never their prose, shows the person one plan, asks once and carries the whole plan out, asking again only before something that spends money and before a pause that belongs to the person. Reinstalling workflows is the engine's job, not the skill's ([ADR `registered-workflows-are-reinstalled-and-pinned-never-lost`](../adr/registered-workflows-are-reinstalled-and-pinned-never-lost.adr.md)). People installing and updating the engine and workflow owners depend on it; design and build notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `contracts.spec.md`: thread states and decisions (CON-B12)
- `engine-update.spec.md`: a failed install changes nothing (UPD-B1); the update verb (UPD-B14); report (UPD-B15)
- `lifecycle-and-evals.spec.md`: executor compatibility (LIF-B10)
- `plugin-shell.spec.md`: pauses go to the person (SHL-B2); executor choice with consequences (SHL-B3); the skills and what they never do (SHL-B5)
- `security.spec.md`: security posture

## Behaviours

### LSK-B6 The skills

WHEN the plugin is installed THE plugin SHALL ship `tempergraph:install` (said as "install tempergraph", "set up tempergraph" or on any exit 127; drives `<plugin>/bin/tempergraph install`, `executors --probe`, `workflows register` and the project bootstrap skill; never installs an executor CLI, stores a credential or edits a shell file without the person's yes), `tempergraph:update` (said as "update tempergraph" or "is tempergraph up to date?"; drives `claude plugin marketplace update`, `claude plugin update`, `<new plugin>/bin/tempergraph update`, `workflows list|reinstall` and then the upgrade skill when offered; never pulls, commits or changes a person's repository, stops a run, answers a pause or runs an upgrade without the person's yes to its cost) and `tempergraph:upgrade` (said as "upgrade my workflow X" or "make X work with the new engine"; drives `upgrade --check`, `upgrade`, `resume` of the upgrade run with the person's decision, `upgrade --continue`, `--stamp`, `--bump` and `--open-pr`; never answers an owner pause, edits the upgrade branch itself, or stamps, bumps or opens a pull request without a yes), the three replacing the shell's installer and serving the authoring skill's upgrade mode ([SHL-B5](plugin-shell.spec.md)).

- GIVEN the shipped skills WHEN the structure test reads them THEN their commands are the engine's verbs and options and their fixed command lists

### LSK-B7 One plan, one yes

WHEN a lifecycle skill is about to write THE skill SHALL show every step it will run, in order, with what each changes, and ask once, the yes covering that plan only, and ask again only for money (an upgrade's assist run, a trial), a step the plan did not list and every pause that belongs to the person.

- GIVEN "update tempergraph" after the plan's yes WHEN it runs THEN marketplaces, plugins, the engine environment and the registry are written with no further yes and nothing is spent
- GIVEN "yes, upgrade it" WHEN it runs THEN the upgrade branch and its record are written, spending up to the cap
- GIVEN "is it up to date?" WHEN it runs THEN nothing is written

### LSK-B8 How a skill calls the CLI

WHEN a lifecycle skill calls a verb THE skill SHALL call it with `--json` or `--format json` and decide by exit code ([CON-B12](contracts.spec.md)), quoting the verb's `summary` line in its own sentences; run a package install in the background with a long timeout and never interrupt it; build each command as a fixed form with values from the verbs' own output (names, versions, ids), never from free text the person typed ([SEC](security.spec.md)); carry no engine-version note, deciding from what the CLI answers; and say that Claude Code loads an updated plugin in the next session or after `/reload-plugins`, a slash command it cannot run itself.

- GIVEN a skill's command list WHEN scanned THEN every value comes from a verb's JSON output

### LSK-B9 Install skill procedure

WHEN the install skill runs THE skill SHALL look with `<plugin>/bin/tempergraph install --check --json`, reporting an engine already current and naming the update skill for a newer release; ask which executors the person will use, each one's consequences read from `executors` ([SHL-B3](plugin-shell.spec.md)), to pick the `--with` extras, asking none while only `claude` runs steps and saying the other executors come later; show the plan (Python found, home folder, environment, extras, the `PATH` block and its file, the workflow plugins to register) for one yes; run `install --json [--with …] --add-to-path` in the background; verify by calling the shim by the absolute path its `shim` line names (`workflows list`, then `executors --probe`), quoting the `engine` line of the install output since the CLI has no `--version` flag, and say for each chosen executor missing or not signed in what to install or sign in to, from the probe facts; for each workflow source path the person gives, run `workflows register <path> --check`, show the result and register on a yes; and offer the project bootstrap for the current repository and say to open a new terminal, `<plugin>` being the grandparent of the skill's base directory (`<plugin>/skills/install/`).

- GIVEN a chosen executor not signed in WHEN verified THEN the skill says what to sign in to, from the probe facts

### LSK-B3 Install never touches a shell file unasked

WHEN the person declines the `PATH` change THE install skill SHALL run without `--add-to-path`, print the block, and call the shim by its absolute path to verify.

- GIVEN a person who declines the `PATH` change WHEN install runs THEN no shell file changes and the shim is called by its absolute path

### LSK-B10 A missing plugin

WHEN the plugin itself is missing THE repository README SHALL give the two commands a person or agent types first: `claude plugin marketplace add <owner>/tempergraph`, then `claude plugin install tempergraph@tempergraph`.

- GIVEN the repository README WHEN read THEN it holds both commands in that order

### LSK-B11 Update skill procedure

WHEN the update skill runs THE skill SHALL read the installed plugin's version from its `plugin.json`, the engine from `update --check --json` through the shim and the registry from `workflows list --json`; run `claude plugin marketplace update` for the `tempergraph` marketplace and each marketplace of a `plugin`-kind workflow, then `claude plugin update tempergraph@tempergraph --json` and the same for each `plugin`-kind workflow at the scope it was installed with, because only the updated plugin carries the new staged engine; find the updated copy (P-LSK-1) and run `<new plugin>/bin/tempergraph update --check --json` ([UPD-B14](engine-update.spec.md)); show in one plan the plugin before and after, the engine line, extras, live runs that keep their engine, threads that move or stay pinned, stores that migrate on first run, and each workflow with its source and whether it will be reinstalled or pinned ([UPD-B15](engine-update.spec.md)), one yes covering the marketplace, plugin and engine steps; run `<new plugin>/bin/tempergraph update --json` in the background; then read the `workflow` lines, offering the upgrade skill for a pinned `local` workflow with its plan's item counts and cost cap, saying a pinned marketplace workflow keeps working on the pinned engine until its owner ships an update, and saying a local checkout behind its remote (`git status -sb`, read-only) should be pulled by the person; read `executors --json` and report a `claude` or `agy` version outside the compatibility table ([LIF-B10](lifecycle-and-evals.spec.md)) with its own updater command for the person to run; and close with one summary of what changed, what keeps an older engine and why, and what the person still has to do.

- GIVEN a pinned local workflow after the update WHEN the skill reads its line THEN it offers the upgrade naming the item counts and the cost cap

### LSK-B1 "Update tempergraph" end to end

WHEN the person says "update tempergraph" with a newer release in the marketplace THE update skill SHALL show one plan, get one yes, update the marketplaces and plugins, run the new copy's `update`, report reinstalls, pins with their reason and `/reload-plugins`, and offer the upgrade with its cost cap, running nothing outside the plan without a second yes.

- GIVEN plugin and engine 1.6.0, one marketplace and one local workflow, and 2.0.0 in the marketplace WHEN the person says "update tempergraph" THEN both workflows are reported reinstalled, the local one pinned to 1.6.0 with the reason, `/reload-plugins` is named and the upgrade is offered with its cap

### LSK-B2 Nothing to do

WHEN the person asks whether tempergraph is up to date and everything is current THE update skill SHALL run only the read-only look and new-copy check, with no plugin update, and answer in one line.

- GIVEN everything current WHEN the person asks "is tempergraph up to date?" THEN only read-only steps run and the answer is one line

### LSK-B12 Update failures

WHEN an update step fails THE update skill SHALL say so on a failed marketplace or plugin update (offline, auth) and continue from the new-copy check with the installed copy, which may already carry a newer engine; on `update` exit 2 for a downgrade, quote the cause and fix from the `engine` line and never offer a force; on `update` exit 1, say the old engine is still current and unchanged ([UPD-B1](engine-update.spec.md)) and offer the troubleshooter; on `engine: up_to_date` with no plugin change, say everything is current and list only the workflow lines that need something; with no `claude` command on `PATH` in the session, skip the marketplace and plugin steps, say how to update through `/plugin` and continue; and when the new copy cannot be found (P-LSK-1 not confirmed), ask the person to run `/reload-plugins` and say "update tempergraph" again.

- GIVEN `update` exit 2 for a downgrade WHEN reported THEN no force is offered

### LSK-B5 Offline marketplace

WHEN the marketplace cannot be reached during an update THE update skill SHALL say the plugin could not be refreshed, run `update --check` from the installed copy, and offer that update if the copy carries a newer engine.

- GIVEN no network to the marketplace WHEN "update tempergraph" runs THEN the skill says so and runs `update --check` from the installed copy

### LSK-B13 Upgrade skill procedure

WHEN the upgrade skill runs THE skill SHALL show `upgrade <workflow> --check --format json` as items by action (transform, model, owner), entries not touched and the cost cap; run `upgrade` on one yes for a transform-only plan, or `upgrade --cap <cap>` in the background on a yes that names the cap; on exit 3 show each owner pause's question, draft and what each choice changes, resume with the person's own decision only ([SHL-B2](plugin-shell.spec.md)) and then run `upgrade --continue <id>`; on exit 4 show each failing check with its evidence and that the branch is kept and offer the authoring skill for the manual items; on exit 0 show the report, the shares done by transform, model and person and the proposed version; and offer `--stamp`, `--bump` and `--open-pr` together on one yes, naming a `weakens-gate` label when there is one.

- GIVEN exit 4 WHEN the skill reports THEN each failing check shows with its evidence and the branch is kept

### LSK-B4 A pause stays the person's

WHEN an upgrade pauses at an owner item THE upgrade skill SHALL show the drafted value and resume only with the person's own answer, and with `--as-agent` never resume on its own.

- GIVEN an upgrade paused asking for the issue repository WHEN the skill reports it THEN it shows the drafted value and resumes only with the person's answer

### LSK-B14 Stopping on a denied command

WHEN the person denies permission to run a command, or the shim exits 127 THE skill SHALL stop at that step and say what is left undone, retrying nothing, and on 127 hand over to the install skill.

- GIVEN a denied command WHEN the skill stops THEN nothing is retried and the undone steps are named

## Acceptance criteria

- LSK-AC1 (LSK-B7, LSK-B4, LSK-B12, LSK-B14): Each skill has rubric scenarios for one-plan-one-yes, ask-again-for-money, never-answer-a-pause and each failure of LSK-B12 and LSK-B14 ([SHL-AC2](plugin-shell.spec.md))
- LSK-AC2 (LSK-B6, LSK-B8): No skill text names an engine version or a shipped workflow (source scan)
- LSK-AC3 (LSK-B8, LSK-B9, LSK-B11, LSK-B13, LSK-B10): Every command a skill runs is in its fixed command list, and every value in it comes from a verb's JSON output (scenario check on the transcript)
- LSK-AC4 (LSK-B7, LSK-B1, LSK-B2, LSK-B3, LSK-B5): Every scenario of LSK-B7 holds in a scenario with a scripted CLI
- LSK-AC5 (LSK-B11, LSK-B12): P-LSK-1 (`claude plugin update --json` names the installed version, or the new version's cache folder can be found by its documented layout) and P-LSK-2 (`claude plugin update` and `claude plugin marketplace update` run non-interactively from a session's shell tool) are recorded with date, machine and Claude Code version before the update skill is marked `LIVE-PROVEN`; until then the skill falls back to `/reload-plugins` and to `/plugin` by the person

## Open questions

- Should the update skill also offer `claude update` when the Claude Code CLI itself is outside the executor compatibility table, or only report it? Until answered: only report it, since the person's Claude Code is theirs to change. Owner: owner.
- Not met yet: the rubric scenarios of LSK-AC1 and LSK-AC4 run a skill with a model and the probes of LSK-AC5 need a signed-in machine; they are live checks L-24 and L-28 ([live-checks.plan.md](../plans/live-checks.plan.md)). Owner: owner.
