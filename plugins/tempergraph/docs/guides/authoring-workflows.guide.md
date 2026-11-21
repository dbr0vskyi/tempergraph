# Authoring workflows

A tempergraph workflow starts from what a good result is, not from the steps. You describe the outcome, the engine helps you work backwards to the steps and to how each one is verified, and then it writes the package for you.

## Start

In Claude Code, say what you want to automate and what you bring:

> Turn our release checklist into a tempergraph workflow. Here's the script we use today: `scripts/release.sh`.

The `author` skill leads an interview. It drafts every answer from your material and asks you to confirm, at most three questions at a time. You decide; it never writes a package file by hand.

There are three ways in. You can mix them, and add sources at any time.

| You bring | Path | First drafts come from |
|---|---|---|
| Something that already does the job: a script, a prompt chain, a runbook, a skill, past outputs | `solution` | Its stages, its tests and assertions, its outputs |
| Templates, good and bad examples, checklists, a Definition of Done, style guides, tickets | `sources` | Headings, rules and checklists; bad examples become must-fail fixtures |
| Only an idea | `chat` | Your answers, then two contrasting sample outputs for you to grade |

A good candidate is done again and again, ends in something a check or a judge can grade, and splits into two to six steps. If nobody can yet say what good looks like, the skill says the workflow is not a fit yet and keeps the session for later.

## The nine phases

| Phase | You agree on |
|---|---|
| 1 Intake | The process played back in six bullets or fewer, and whether it fits |
| 2 Final outcome | The statement, the deliverables and the final criteria |
| 3 Work backwards | What each step must produce for the final criteria to hold |
| 4 Verifications | How each criterion is verified: a deterministic check, an independent judge, a person, or openly unverified |
| 5 Steps | Each step's kind (script or model), inputs, outputs, check, judge and limits |
| 6 Start and routing | The inputs a run asks for, examples, and how requests are routed to this workflow |
| 7 Approval | One yes on the diagram, the outcome table and the verification table together |
| 8 Scaffold | The package is written to a folder you choose |
| 9 Verify | The package is checked rung by rung, registered and stamped |

Some rules hold throughout:

- A deterministic check beats a judge, and a judge beats nothing. A criterion nobody can verify is flagged, never hidden.
- A script that asserts its own success, or a prompt that asks the model whether it succeeded, is a claim, not a verification.
- When you choose against a draft, the choice is recorded as a decision and becomes a decision record in the workflow's docs.
- Nothing outside the authoring session's folder is written before your approval in phase 7.

## Verify

Phase 9 runs `tempergraph author verify <folder>`, which stops at the first failing rung:

| Rung | Checks |
|---|---|
| 1 | The package loads and validates |
| 2 | The workflow matches the approved blueprint |
| 3 | No literals copied from one example (ticket ids, URLs, paths) |
| 4 | The generated tests pass |
| 5 | Every final criterion is covered, and every blocker is verified |
| 6 | The audit has no errors |
| 7 | The workflow registers |
| 8 | Each judge grades its seed examples consistently (spends) |
| 9 | A first trial run on a real case (spends, capped at $5 by default) |
| 10 | The package is stamped |

Rungs 8 and 9 cost money, so the skill tells you the number of sessions and the cap and waits for your yes. After the trial you grade the output criterion by criterion yourself, before you see the verifiers' grades. Each disagreement points at the likeliest weak spot in the outcome or its verification.

Passing means "ready to run and be measured", not "trusted". The workflow starts in `dev` mode; moving it to `stable` is your call once its judges are calibrated (see [Improving workflows](improving-workflows.guide.md)).

## What a package looks like

A workflow is a Claude Code plugin whose name ends in `-tgraph`, with a Python part. The two examples in this repository are the best reference: [`release-notes-tgraph`](../../../release-notes-tgraph) is the smallest package, and [`doc-refresh-tgraph`](../../../doc-refresh-tgraph) adds a script, a route on a value, a trip back, an approval and a finalizer.

| Path | Holds |
|---|---|
| `.claude-plugin/plugin.json` | The plugin manifest, named `<workflow>-tgraph` |
| `tempergraph.json` | The workflow manifest |
| `outcome.json` | The good outcome: final and intermediate criteria and how each is verified |
| `workflow/<name>/__init__.py` | The declaration: steps, gates and flow, in typed Python builders |
| `workflow/<name>/checks.py` | Deterministic checks |
| `prompts/`, `judges/` | Step prompts and judge briefs, kept as text files |
| `evals/` | Cases, check fixtures and judge calibration seeds |
| `docs/` | The workflow's own specs and decision records |
| `blueprint.json`, `authoring.json` | The approved design and the authoring record |

## The CLI underneath

```sh
tempergraph author start <name> --from solution|sources|chat [<path>…]
tempergraph author intake <id> <path>…      # add sources
tempergraph author check <id>               # lint the drafts
tempergraph author approve <id> <phase>
tempergraph scaffold <id> --out <folder>
tempergraph author verify <folder> --json
tempergraph workflows register <folder>
tempergraph author list | show <id>         # pick up unfinished sessions
```

## Spend more only on evidence

A step names one model and one effort, and says why in `sizing`. Three declarations let a run spend more where it is earned, and none of them reacts to just any failure:

| Declaration | What it does | When it acts |
|---|---|---|
| `effort_ladder=["medium", "high"]` on a step | Retries at the next effort | Only after a judge you have calibrated repeats the same blocker |
| `escalation=Escalation(to="large")` on a step | One attempt on the next model tier | The same evidence; in a new workflow it is offered to you at a pause, not taken |
| `risk=Risk(...)` on a judge | A stronger judge for a riskier attempt | A model-free rule: paths touched, lines changed, a check's fact |

A list of models in `model` is no longer accepted; `tempergraph upgrade <workflow>` rewrites it.

## Route by size

A complexity switch picks a short path for a small task and the detailed path for a large one, from measures that cost nothing (a count in an earlier step's output, an input, a setting) and a rules file in the package. The detailed path is the safe arm: any doubt takes it, and a short path that turns out too small moves up once, never down. `tempergraph report --switch <workflow>/<switch>` shows how each arm did.

## Ask, wait and work side by side

`Ask` puts typed questions to a person and hands the answers to later steps. `Wait` holds the run until an outside value arrives that its check accepts. `Parallel` runs read-only steps side by side and goes on when all have passed. A step with `self_check=True` may run its gate's check before it ends, up to three times, so it can fix what the check would find.

## Revise a workflow

To change an existing workflow's outcome, ask Claude to revise it, or run `tempergraph outcome candidates <workflow>` and then `tempergraph author start <workflow> --revise`. A revision that weakens a criterion needs your explicit yes.

To check a workflow you already have:

```sh
tempergraph validate <workflow>
tempergraph audit <workflow>      # advisory, no model call
```
