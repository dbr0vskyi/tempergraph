---
name: author
description: Author or revise a tempergraph workflow with the person, starting from the good outcome. Use when the person wants to turn a process, script, template, examples or an idea into a workflow they can trust, or to revise a workflow's outcome after its runs.
---

# Author a workflow

You lead the interview. The engine checks, draws and writes. You draft; the person decides; you never decide a gate, never edit the engine, never draw or type a diagram, and never write a package file by hand.

Every engine call below is model-free and prints JSON. Read the JSON; do not guess what it says.

## Modes

| Mode | Starts with | Ends with |
|---|---|---|
| new | `tempergraph author start <name> --from solution\|sources\|chat [<path>…]` | A registered, verified, stamped package in `dev` mode |
| revise | `tempergraph outcome candidates <workflow>`, then `tempergraph author start <workflow> --revise` | A new outcome revision, re-checked. Read [references/revise.md](references/revise.md) |
| upgrade | The person asks to upgrade a workflow to a newer engine | Hand over to the upgrade skill if it is installed; otherwise run `tempergraph upgrade-check <workflow>` and report what it says |

If the person returns to unfinished work, run `tempergraph author list`, then `tempergraph author show <id>`. Continue at `next_phase` with the drafts it shows. Never ask again what an approved phase already settled.

## Rules for every turn

- **Draft, then ask.** Propose concrete answers from the material, then ask. At most three questions per turn, one phase per turn.
- **The person's words** name outcomes, steps and criteria. What they do not know becomes an assumption in `outcome.json` `assumptions`, said out loud.
- **Each phase ends** by showing its part of the drafts and getting a yes. Record it with `tempergraph author approve <id> <phase>` only after the person's yes in this conversation. If the engine refuses, show its message and fix the drafts.
- **Nothing outside the session folder** is written before phase 7 is approved. You edit only the session's `outcome.json` and `blueprint.json` (the folder is in `author show`'s `folder`), and the person's yes covers those edits.
- **After every edit** run `tempergraph author check <id>` and fix each `error` before you ask for a yes. Show warnings.
- **Prefer a deterministic check** over a judge, and a judge over nothing. Flag a criterion nobody can verify. Never hide it.
- **A self-check is a claim.** A script that asserts its own success, or a prompt that asks the model whether it succeeded, is never a verification. The inventory marks these as `claim:self_check`.
- **Never invent a rubric** the person did not confirm.
- **Paths.** `author intake` takes workspace paths. Pass `--outside` only for a path the person named. Save connector content (a wiki page, a ticket) as a file in the session's `sources/` folder first, then take it in. Never put a URL with a token into a draft.
- **No engine version knowledge.** Decide from what the engine answers. If a verb or option is refused as unknown, offer `tempergraph update`.

## The phases

| Phase | You produce | Read first |
|---|---|---|
| 1 Intake | Sources and candidates; the process played back in at most six bullets; a fit check | [references/entry-paths.md](references/entry-paths.md) |
| 2 Final outcome | `statement`, `deliverables`, `final` criteria | [references/outcome-and-guidance.md](references/outcome-and-guidance.md) |
| 3 Work backwards | `intermediate` outcomes per unit, each criterion's `serves` | [references/backwards-and-verification.md](references/backwards-and-verification.md) |
| 4 Find verifications | `verified_by`, `verifier`, `source` for every criterion | [references/backwards-and-verification.md](references/backwards-and-verification.md) |
| 5 Steps' work | `blueprint.json` units: kind, produces, reads, check, judge, policies, executor | [references/steps-and-executors.md](references/steps-and-executors.md) |
| 6 Start and routing | `input` in the blueprint, examples, `routing` in the record | [references/steps-and-executors.md](references/steps-and-executors.md) |
| 7 Approval | One yes on the drawing and both tables together | [references/approve-scaffold-verify.md](references/approve-scaffold-verify.md) |
| 8 Scaffold | The package | [references/approve-scaffold-verify.md](references/approve-scaffold-verify.md) |
| 9 Verify, register, stamp | `author verify` passing | [references/approve-scaffold-verify.md](references/approve-scaffold-verify.md) |

Read a reference when its phase starts, not before.

## When the definition is thin

`author check` runs the criteria lint. Each finding has a `guidance` field: follow it. For each criterion that fails, climb the guidance ladder in [references/outcome-and-guidance.md](references/outcome-and-guidance.md), one rung at a time. Phase 2 cannot be approved until the sufficiency check holds (`sufficiency` is empty). If no observable blocker exists after the last rung, say the workflow is not a fit yet, keep the session, and offer to resume when the person has an example.

## Decisions

Each time the person chooses against your draft, record a decision in the session's `authoring.json` `decisions`: `id`, `phase`, `subject` (the criterion or unit id), `choice`, `alternatives`, `consequence`, `decided_by: person`. These cases count: a criterion dropped as not observable, a `none` accepted, an executor choice with its stated consequence, a step boundary the person moved, and a literal kept on purpose (`literal_digest`, from `tempergraph literals`). Scaffold turns each one into a decision record in the workflow's `docs/adr/`.

## Never

- Answer a pause of a run, or start a run the person did not ask for.
- Spend money without a yes: `author verify --judge-seeds` and `--trial` are the only calls that spend. In this release both are refused, and you say so.
- Move a workflow to `stable` mode. That is the owner's decision, after calibration.
- Name or copy another workflow's private content into this one.
