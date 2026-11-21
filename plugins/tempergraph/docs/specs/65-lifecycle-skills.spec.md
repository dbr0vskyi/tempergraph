---
title: Lifecycle skills for install, update and upgrade
type: component
status: ready-for-implementation
prefix: LSK
adrs: [0061, 0060, 0055, 0058]
---

# Lifecycle skills for install, update and upgrade

## 1. Overview

Three skills of the `tempergraph` plugin let a person say "install tempergraph", "update tempergraph" or "upgrade my workflow" to their agent and have it done. Each skill drives the CLI verbs that do the work: `install` and `update` ([UPD](60-engine-update.spec.md)), `workflows` ([UPD §2.8](60-engine-update.spec.md)) and `upgrade` ([WUP](63-workflow-upgrade.spec.md)). The update skill also runs Claude Code's own plugin commands, because the engine cannot update the plugin that carries it ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U1).

The rule of the shell holds: **a skill drives; the verbs decide** ([SHL](19-plugin-shell.spec.md), [ADR-0061](../adr/0061-lifecycle-skills-drive-plugin-commands-then-engine-verbs.adr.md)). A skill reads the verbs' JSON and exit codes, never their prose. It shows the person one plan, asks once, and then carries the whole plan out. It asks again only before something that spends money, and before a pause that belongs to the person.

## 2. Contract

### 2.1 The skills

| Skill | Said as (examples) | Drives | Never |
|---|---|---|---|
| `tempergraph:install` | "install tempergraph", "set up tempergraph", any exit 127 | `<plugin>/bin/tempergraph install`, `executors --probe`, `workflows register`, the project bootstrap skill | Install an executor CLI or store a credential; edit a shell file without the person's yes |
| `tempergraph:update` | "update tempergraph", "is tempergraph up to date?" | `claude plugin marketplace update`, `claude plugin update`, `<new plugin>/bin/tempergraph update`, `workflows list\|reinstall`, then the upgrade skill when offered | Pull, commit or change a person's repository; stop a run; answer a pause; run an upgrade without the person's yes to its cost |
| `tempergraph:upgrade` | "upgrade my workflow X", "make X work with the new engine" | `upgrade --check`, `upgrade`, `resume` of the upgrade run with the person's decision, `upgrade --continue`, `--stamp`, `--bump`, `--open-pr` | Answer an owner pause; edit the upgrade branch itself; stamp, bump or open a pull request without a yes |

They replace the shell's Installer row and serve the Authoring skill's upgrade mode ([SHL §2](19-plugin-shell.spec.md)).

### 2.2 Shared rules

| Rule | Value |
|---|---|
| One plan, one yes | Before any write, the skill shows every step it will run, in order, with what each changes, and asks once. A "yes" covers that plan only. |
| Ask again only for | Money (an upgrade's assist run, a trial), a step the plan did not list, and every pause that belongs to the person |
| Read JSON | Every verb is called with `--json` or `--format json` and decided by exit code ([CON §2.9](01-contracts.spec.md)); the person sees the skill's sentences, with the verb's `summary` line quoted |
| Commands | Each command is a fixed form with values from the verbs' own output (names, versions, ids), never from free text the person typed ([SEC](14-security.spec.md)) |
| Reload | Claude Code loads an updated plugin in the next session or after `/reload-plugins`; a skill says so, since it cannot run a slash command itself |

### 2.3 Install skill procedure

| Step | Does | Asks |
|---|---|---|
| 1 Look | Runs `<plugin>/bin/tempergraph install --check --json`. An engine that is already current hands over to the update skill. | — |
| 2 Executors | Asks which executors the person will use, with each one's consequences read from the capability table ([SHL-B3](19-plugin-shell.spec.md)). This picks the `--with` extras. | the choice |
| 3 Plan | Shows the Python found, the home folder, the environment, the extras, the `PATH` block and the file it goes in, and the workflow plugins that will be registered | one yes |
| 4 Run | `install --json [--with …] --add-to-path` in the background | — |
| 5 Verify | Calls the shim by its absolute path (`--version --json`, `workflows list --json`), then `executors --probe --json`. For each chosen executor that is missing or not signed in, says what to install or sign in to, from the probe facts. | — |
| 6 Own workflows | Asks whether the person has workflow sources in their own repositories. For each path they give, runs `workflows register <path> --check`, shows the result, and registers it on a yes. | per path |
| 7 Next | Offers the project bootstrap for the current repository, and says to open a new terminal | — |

If the plugin itself is missing, the skill cannot run. The repository README gives the two commands a person or agent types first: `claude plugin marketplace add <owner>/tempergraph`, then `claude plugin install tempergraph@tempergraph`.

### 2.4 Update skill procedure

| Step | Does | Asks |
|---|---|---|
| 1 Look | Reads the installed plugin's version from its `plugin.json`, the engine from `update --check --json` (through the shim), and the registry from `workflows list --json` | — |
| 2 Marketplaces | `claude plugin marketplace update` for the `tempergraph` marketplace and for each marketplace of a `plugin`-kind workflow | in the plan |
| 3 Plugins | `claude plugin update tempergraph@tempergraph --json` and the same for each `plugin`-kind workflow, each at the scope it was installed with | in the plan |
| 4 New copy | Finds the updated plugin copy (P-LSK-1) and runs its launcher: `<new plugin>/bin/tempergraph update --check --json` | — |
| 5 Plan | Shows in one view: the plugin before and after; the engine line; extras; live runs that keep their engine; threads that move or stay pinned; stores that migrate on first run; and each workflow with its source, whether it will be reinstalled, and whether it will be pinned ([UPD §2.4](60-engine-update.spec.md)) | one yes (covers steps 2, 3 and 6) |
| 6 Run | `<new plugin>/bin/tempergraph update --json` in the background | — |
| 7 Workflows | Reads the `workflow` lines. A pinned workflow with a `local` source: offers the upgrade skill, quoting its plan's item counts and the cost cap. A pinned workflow from a marketplace: says it keeps working on the pinned engine until its owner ships an update. A local checkout behind its remote (`git status -sb`, read-only): says so and suggests the person pull. | the upgrade's cost, per workflow |
| 8 Executors | Reads the executor lines of `executors --json`. A `claude` or `agy` version outside the executor compatibility table ([LIF](18-lifecycle-and-evals.spec.md)) is reported with its own updater command, for the person to run. | — |
| 9 Close | One summary: what changed, what keeps an older engine and why, what the person still has to do (`/reload-plugins`, a new terminal, an upgrade they declined) | — |

The order of steps 2, 3 and 6 comes from where the update code lives. Claude Code updates the plugin first. Only then does the plugin carry the new staged engine, and the engine verb must run from that copy ([UPD §2.3](60-engine-update.spec.md) step 1).

| Exit or state | Skill does |
|---|---|
| Marketplace or plugin update fails (offline, auth) | Says so, then continues from step 4 with the installed plugin copy, which may already carry a newer engine than the one installed |
| `update` exit 2, downgrade | Quotes the cause and the fix from the `engine` line; never offers a force |
| `update` exit 1 | Says the old engine is still current and unchanged ([UPD-B1](60-engine-update.spec.md)); offers the troubleshooter |
| `engine: up_to_date`, no plugin change | Says everything is current, and lists only the workflow lines that need something |

### 2.5 Upgrade skill procedure

| Step | Does | Asks |
|---|---|---|
| 1 Plan | `upgrade <workflow> --check --format json`; shows items by action (transform, model, owner), entries not touched, and the cost cap | — |
| 2 Run | Transform-only plan: one yes, then `upgrade`. A plan with assisted or owner items: a yes that names the cap, then `upgrade --cap <cap>` in the background. | one yes |
| 3 Owner pauses | On exit 3, for each pause: shows the owner's question, the draft and what each choice changes; resumes the upgrade run with the person's own decision only ([SHL-B2](19-plugin-shell.spec.md)); then `upgrade --continue <id>` | the person's decision |
| 4 Result | On exit 4: shows each failing check with its evidence and that the branch is kept, and offers the authoring skill for the manual items. On exit 0: shows the report, the share of items done by transform, model and person, and the proposed version. | — |
| 5 Finish | Offers `--stamp`, `--bump` and `--open-pr` together, and names a `weakens-gate` label when there is one | one yes |

### 2.6 Release 1

| Part | Release 1 |
|---|---|
| Skills | Release 1 ships `tempergraph:install` (I-72). Release 2 ships the update skill with `update` (X2-8) and the upgrade skill with `upgrade` beyond `--check` (moved from release 3 by [ADR-0125](../adr/0125-release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md)); the authoring skill's upgrade mode runs `upgrade-check` and reports |
| `<plugin>` | The skill's base directory's grandparent (`<plugin>/skills/install/`), which Claude Code shows when the skill loads |
| Step 1 | An engine already current is reported as current; from release 2 the install skill names the update skill for a newer release |
| Step 2 | Only `claude` runs steps, so no `--with` extra is asked; the skill reads `claude`'s row of `executors` for the consequences and says the other executors come later |
| Step 5 | The shim is called by the absolute path its `shim` line names: `workflows list`, then `executors --probe`. The CLI has no `--version` flag; the `engine` line of the install output is quoted instead |
| JSON | `install` takes `--json`; `workflows list` and `executors` print JSON always |
| Not built | The rubric scenarios of LSK-AC-1 and AC-4 run the skill with a model: live, on the owner's machine. LSK-AC-2 and AC-3's fixed command list are checked by the shell-skills structure test |

## 3. Behaviours

**LSK-B1 "Update tempergraph" end to end.** Given plugin 1.6.0, engine 1.6.0, one marketplace workflow and one local workflow, and a marketplace that now has 2.0.0, when the person says "update tempergraph", then the skill shows one plan and gets one yes. It then updates the marketplaces and both plugins and runs the new copy's `update`. It reports that both workflows were reinstalled, that the local one is pinned to 1.6.0 with the reason, and that `/reload-plugins` is needed. It then offers the upgrade with its cost cap. Nothing outside the plan runs without a second yes.

**LSK-B2 Nothing to do.** Given everything current, when the person asks "is tempergraph up to date?", then the skill runs only read-only steps (1 and 4, with no plugin update) and answers in one line.

| Person says | Writes without a further yes | Spends |
|---|---|---|
| "update tempergraph" (after the plan's yes) | marketplaces, plugins, engine environment, registry | no |
| "yes, upgrade it" | the upgrade branch, its record | up to the cap |
| "is it up to date?" | nothing | no |

**LSK-B3 Install never touches a shell file unasked.** Given a person who declines the `PATH` change, when install runs, then it runs without `--add-to-path`, prints the block, and the verify step calls the shim by its absolute path.

**LSK-B4 A pause stays the person's.** Given an upgrade paused at an owner item asking for the issue repository, when the skill reports it, then it shows the drafted value and resumes only with the person's own answer; with `--as-agent` it never resumes on its own.

**LSK-B5 Offline marketplace.** Given no network to the marketplace, when "update tempergraph" runs, then the skill says the plugin could not be refreshed, and runs `update --check` from the installed copy. If that copy carries a newer engine, it offers that update.

## 4. Error conditions

| Condition | Skill behaviour |
|---|---|
| The `claude` command is not on `PATH` inside the session | Skips steps 2 and 3, says how to update the plugin through `/plugin`, continues from step 4 |
| The new plugin copy cannot be found (P-LSK-1 not confirmed) | Asks the person to run `/reload-plugins` and say "update tempergraph" again; the reloaded session's own plugin copy is then the new one |
| Permission to run a command is denied by the person | Stops at that step and says what is left undone; nothing is retried |
| Exit 127 from the shim | Hands over to the install skill |

## 5. Design notes

- One plan and one yes answers the owner's "simply say update tempergraph". Asking once per command would turn a routine update into a dozen prompts. Asking again for money and for pauses keeps the two consents the design never folds away ([ADR-0061](../adr/0061-lifecycle-skills-drive-plugin-commands-then-engine-verbs.adr.md)).
- Reinstalling workflows is the engine's job, not the skill's ([ADR-0060](../adr/0060-registered-workflows-are-reinstalled-and-pinned-never-lost.adr.md)). An update from CI or a terminal must keep workflows working too, with no conversation.
- The skills never pull or commit in a person's repository. An upgrade works on its own branch, and a stale checkout is pointed out, not fixed.

| Probe | Fact needed | Until confirmed |
|---|---|---|
| P-LSK-1 | `claude plugin update --json` names the installed version, or the cache folder of the new version can be found by its documented layout | Fall back to asking for `/reload-plugins` (§4) |
| P-LSK-2 | `claude plugin update` and `claude plugin marketplace update` run non-interactively from a session's shell tool | Fall back to `/plugin` by the person (§4) |
- **As built (R2-T6.4).** The `update` and `upgrade` skills ship in `skills/`. The structure tests hold them to the engine's verbs and options and to LSK-AC-2 and LSK-AC-3's command list; the rubric scenarios and the two probes are live checks ([live-checks.plan.md](../plans/live-checks.plan.md) L-24, L-28).

## 6. Acceptance criteria

- [ ] LSK-AC-1 Each skill has rubric scenarios for one-plan-one-yes, ask-again-for-money, never-answer-a-pause and each row of §4 ([SHL-AC-2](19-plugin-shell.spec.md)).
- [x] LSK-AC-2 No skill text names an engine version or a shipped workflow (source scan).
- [ ] LSK-AC-3 Every command a skill runs is in its fixed command list, and every value in it comes from a verb's JSON output (scenario check on the transcript).
- [ ] LSK-AC-4 Every row of LSK-B2's table holds in a scenario with a scripted CLI.
- [ ] LSK-AC-5 P-LSK-1 and P-LSK-2 are recorded with date, machine and Claude Code version before the update skill is marked `LIVE-PROVEN`.

## Open questions

| Question | Owner |
|---|---|
| Should the update skill also offer `claude update` when the Claude Code CLI itself is outside the executor compatibility table, or only report it? The design only reports it, since the person's Claude Code is theirs to change. | Owner |

## References

