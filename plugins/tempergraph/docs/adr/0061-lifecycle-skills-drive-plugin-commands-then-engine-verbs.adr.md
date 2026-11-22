# ADR-0061 Lifecycle skills drive Claude Code's plugin commands and then the engine verbs, from one plan and one yes

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner wants a person to say "update tempergraph" to their agent and have it handle the marketplace, the plugin updates, the CLI reinstall, and the reinstall and update of workflows, including workflows in their own repositories. They also asked for an install command with a skill. The engine cannot update the plugin that carries it: Claude Code does, through `claude plugin marketplace update` and `claude plugin update`, and the engine verb must then run from the new plugin copy ([R-055](../research/R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U1 to U4, [UPD-B14, UPD-B6](../specs/60-engine-update.spec.md)). The shell's rule is that a skill drives the engine and never decides ([SHL](../specs/19-plugin-shell.spec.md)).

## Decision

We will ship three skills ([LSK](../specs/65-lifecycle-skills.spec.md)): `install`, `update` and `upgrade`. Each one shows a single plan of every write, asks once, and carries the plan out through fixed commands decided by JSON and exit codes. It asks again only before spending money and at every pause that belongs to the person. The update skill runs in this order: marketplaces, plugins, then the engine verb from the new plugin copy. The engine reinstalls workflows itself, and the skill offers an upgrade for local sources a release broke.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Thin skills, one plan and one yes (chosen) | Says "update tempergraph" and it is done; every mutation still shown first; same verbs serve CI | The skill depends on Claude Code's plugin commands behaving headlessly (P-LSK-2) |
| A yes per command | Most cautious | A routine update becomes a dozen prompts; people stop reading them |
| Engine verb calls `claude plugin update` itself | One command | The engine would shell out to its own host and run code from a copy it did not start from; CI has no Claude Code |
| No skill; document the commands | Least work | Fails the owner's request |

## Decision rationale

| Criterion | One plan, one yes | Yes per command | Engine calls plugin | Docs only |
|---|---|---|---|---|
| "Just say update" | yes | partly | yes | no |
| Every write shown before it happens | yes | yes | no | n/a |
| Works without Claude Code (CI) | verbs do | verbs do | no | yes |
| Spend and pauses stay with the person | yes | yes | n/a | n/a |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | "Clue reinstall" in the request means the tempergraph CLI (the shim and the environment). The Claude Code CLI's own version is checked and reported, and the person updates it. | LSK-B11, LSK-B12 step 8 |
| A2 | "Workflow reinstall and update if users have repos of some" means re-registering local workflow sources and offering the upgrade on them. Pulling or committing in those repositories stays the person's job. | LSK-B11, LSK-B12 step 7 |
| A3 | The person's agent may run `claude plugin …` commands through its shell tool, subject to the agent's own permission prompts. | LSK-B11, LSK-B12 |

## Consequences

- Positive: install, update and upgrade are each one sentence to the agent, with every write still shown in advance.
- Negative: three more skills to evaluate; two probes before the update skill is live-proven.
- Risk: a single yes covers more than the person read. Mitigation: the plan lists each step's effect in plain words, and anything outside it needs a new yes.

## Revisit when

Claude Code gains a documented way for a plugin to run code after its own update, which could replace the skill's ordering.
