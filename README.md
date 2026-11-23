<div align="center">

<img src="assets/logo.svg" alt="tempergraph logo: a hammer and anvil on a tile striped in steel's temper colours" width="112">

# tempergraph

**Tempered rails for AI workflows.**

Build AI workflows you can trust: state the good outcome first, check every step against it, and temper the workflow over repeated runs until it holds up without you watching.

![status: pre-release](https://img.shields.io/badge/status-pre--release-C9773A)
![python 3.11+](https://img.shields.io/badge/python-3.11%2B-4A7FC1)
![built on LangGraph](https://img.shields.io/badge/built%20on-LangGraph-8A5CB0)
![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-E3B04B)

[Quick start](#quick-start) · [How it works](#how-it-works) · [Features](#built-in-not-bolted-on) · [Guides](plugins/tempergraph/docs/guides/README.md) · [CLI](#the-cli) · [Design docs](plugins/tempergraph/docs/README.md) · [Roadmap](#roadmap)

</div>

> [!IMPORTANT]
> **Releases 1 and 2 are built and offline-tested; their live checks are under way.** The offline suite runs every component on stand-in executors. The checks that need a signed-in `claude` (install from the plugin, a real two-step run, judge scoring, the monitor mod) are listed with their commands, pass criteria and results in [live-checks.plan.md](plugins/tempergraph/docs/plans/live-checks.plan.md). Until every row there passes, expect rough edges.

## Quick start

You need macOS or Linux, Python 3.11+, git and a signed-in [Claude Code](https://docs.claude.com/en/docs/claude-code).

**1. Install.** Add this repository as a plugin marketplace, install the plugin, then let Claude install the engine:

```sh
git clone https://github.com/dbr0vskyi/tempergraph.git
claude plugin marketplace add ./tempergraph
claude plugin install tempergraph@tempergraph
```

> Install tempergraph, and prepare this repository for it.

**2. Run a workflow.** Install an example (`release-notes-tgraph` or `doc-refresh-tgraph`) from the same marketplace, or register its folder, then ask:

> Run the release-notes workflow for v1.2.

Claude checks the run first (no spend), starts it, reports how it ended, and hands every pause back to you. The CLI equivalent:

```sh
tempergraph workflows register ./tempergraph/plugins/release-notes-tgraph
tempergraph run release-notes --check v1.2
tempergraph run release-notes v1.2
```

**3. Create your own.** Describe what you want automated and what you already have:

> Turn our release checklist into a tempergraph workflow. Here's the script we use today.

Claude interviews you, starting from what a good result is, then scaffolds, verifies and registers the workflow package.

> [!NOTE]
> The plugin install path is live check L-16 and has not been confirmed yet. To work on the engine itself instead: `cd plugins/tempergraph/engine && python -m pip install -e '.[dev]' && python -m pytest` (offline, stand-in executors only).

Each step has a guide: [getting started](plugins/tempergraph/docs/guides/getting-started.guide.md), [running workflows](plugins/tempergraph/docs/guides/running-workflows.guide.md), [authoring workflows](plugins/tempergraph/docs/guides/authoring-workflows.guide.md) and [improving workflows](plugins/tempergraph/docs/guides/improving-workflows.guide.md).

## Why tempergraph

Chaining model calls is easy. Trusting the result is not. Most AI workflows check their own work with the same model that did it, retry until something looks plausible, and leave no record of what the run cost or how often a person had to step in.

tempergraph is an opinionated Python engine on [LangGraph](https://github.com/langchain-ai/langgraph) that builds the practices of careful AI engineering into the framework, so people who are not AI-engineering experts still end up with workflows that behave well:

- **Outcome first.** Every workflow states what a good result is, as criteria that a check, a judge or a person verifies. Anything unverified is shown as unverified.
- **Rules before models.** Deterministic checks run first. An independent judge, which cannot see the step's reasoning or edit its work, covers what rules cannot express. The verdict comes from a rule, not from a model's mood.
- **Verdicts drive the graph.** Retries, trips back to an earlier step and pauses for a person are graph edges, each with a budget.
- **People decide pauses.** An agent can relay a person's decision but never makes one, and one command lists everything waiting on a person.
- **Tempered over time.** Self-improvement, observability, cost tracking and reports are part of the engine, not add-ons ([below](#built-in-not-bolted-on)).

## How it works

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/how-it-works-dark.svg">
    <img src="assets/how-it-works-light.svg" alt="How a run flows: good outcome, then for each step: step, deterministic checks, independent judge and gate; then the outcome gate and done. A failed check skips the judge. The gate retries the step with the findings, sends the run back to an earlier step or moves to the next step, and pauses for a person when the judge cannot verify, the step is blocked, a budget is spent or approval is needed; the outcome gate sends the run back to the step that serves an unmet criterion and pauses for sign-off. The person proceeds, retries, goes back, rewinds or stops. Every finished run's record feeds the self-improvement loop, whose measured changes a person merges." width="100%">
  </picture>
</p>

The judge grades and the gate decides: a rule turns the judge's findings into a verdict, and only the gate routes, so a run never pauses inside a model call. A run pauses for a person (exit 3, with the exact `resume` command) when the judge cannot verify a blocker, a step reports it is blocked or lacks a tool, a retry or loop budget is spent (`on_budget_spent: ask`, the default), a gate asks for approval or sign-off, or an `ask` or `wait` step is reached. The person's decision picks the edge: `proceed` goes on as if the gate passed, `retry` reruns the step with a fresh budget and the person's feedback, `back` and `rewind` restart an earlier step, and `stop` ends the run (exit 4). Infra failures never pause; they rerun with backoff and end the run when their tries are spent ([gates and pauses](plugins/tempergraph/docs/specs/07-gate-and-human.spec.md), [budgets](plugins/tempergraph/docs/specs/08-budgets-and-failures.spec.md)).

A **workflow** is declarative data: steps, gates and flow. The engine validates it, compiles it to a durable LangGraph state graph and runs each step as a fresh headless session on an **executor**. Runs survive restarts and can wait days at a pause. A workflow starts in `dev` mode on your machine and moves to a pipeline once its runs show it no longer needs babysitting.

Why "temper": steel is tempered by heating and cooling it in repeated, controlled cycles until it is hard and not brittle. The logo's stripes are the oxide colours steel turns as it is tempered: straw, bronze, purple and blue.

## Built in, not bolted on

<table>
<tr>
<td width="50%" valign="top">

### Self-improvement

- Every run records its findings with no model call: failed gates, retries, interventions, cost.
- Repeated causes become one de-duplicated issue each, with no request text in it.
- The loop drafts changes and measures them in paired trials (old against new) before you see them.
- Judges are calibrated against your labels, and a workflow moves to `stable` only once they clear the bar.

`improve backlog` · `improve propose` · `improve trial` · `evals bar`

</td>
<td width="50%" valign="top">

### Observability

- A detailed run log of every step, session, check, verdict and decision, in order.
- Raw session logs, check output and engine logs kept locally, with retention and export.
- A live view of running and paused runs inside Claude Code, through the monitor mod.
- A read-only troubleshooter that ranks likely causes when a run goes wrong.

`status --detail` · `events --follow` · `logs` · `store`

</td>
</tr>
<tr>
<td width="50%" valign="top">

### Tracking

- Every model call is costed. Reported and estimated cost are kept apart, and unmeasured cost is never shown as zero.
- Every call and decision names who made it: a person, an agent relaying a person, a pipeline or the engine.
- Every run records how much supervision it needed and what supervising it cost.
- Every run is tied to the workflow version and its outcome record.

`outcome show` · `supervision show` · `facts`

</td>
<td width="50%" valign="top">

### Reports

- Cost and friction by step, executor, workflow version, host or supervision level, over any window.
- Supervision and self-improvement reports, so you can see a workflow needing less of you over time.
- Monthly per-person usage, also gathered across machines through a shared folder.
- One list of everything waiting on a person, oldest first.

`report` · `report --supervision` · `report --loop` · `stats` · `attention`

</td>
</tr>
</table>

## What a workflow looks like

A workflow is a Claude Code plugin with a Python part. Its plugin name ends in `-tgraph`, for example `release-notes-tgraph`. The good outcome lives in `outcome.json`:

```json
{
  "statement": "Release notes that cover every merged change since the last tag, faithfully.",
  "final": [{
    "id": "rn-complete", "severity": "blocker", "verified_by": "judge",
    "text": "Every merged change since the last tag is in the notes or listed as excluded with a reason"
  }],
  "intermediate": {"draft": {"criteria": [
    {"id": "rn-sections", "verified_by": "check", "text": "The notes have the template's four headings in order"},
    {"id": "rn-faithful", "verified_by": "judge", "text": "Every entry matches what its merged change did"}
  ]}}
}
```

The steps and their gates are declared in Python:

```python
from tempergraph.api import Gate, Judge, Routing, Step, Workflow, text

from .checks import draft_check


def workflow():
    return Workflow(
        order=["draft"],
        routing=Routing(description="Write release notes for the changes since the last tag"),
        units={
            "draft": Step(
                prompt=text("prompts/draft.md"),
                tools=["read", "write"],
                produces={"notes": "file"},
                gate=Gate(check=draft_check, judge=Judge(file="judges/draft.md", references=["notes"])),
            )
        },
    )
```

Both are trimmed from the [`release-notes-tgraph`](plugins/release-notes-tgraph) example. You don't have to write them by hand: the `author` skill interviews you, starting from the good outcome, and the engine scaffolds, checks and registers the package.

## Skills and plugins

You mostly work through Claude Code. The plugin's skills turn plain requests into engine commands, read the engine's JSON rather than guessing, and leave every decision to you:

| Skill | Use it to |
|---|---|
| `install` | Install the engine with one plan and one yes, then probe that `claude` is ready |
| `bootstrap` | Make a repository ignore the engine's run state |
| `run` | Start, resume and report runs; every pause goes back to you |
| `author` | Turn a process, script, template or idea into a workflow, starting from the good outcome |
| `troubleshoot` | Find out, read-only, why a run failed, stalled or cost more than expected |
| `evals` | Run a workflow's eval suites, score its judges and grade what needs a person |
| `update` | Update the plugin and engine with one plan and one yes, then report what each registered workflow needs |
| `upgrade` | Bring one workflow package up to the running engine on a branch of its source, leaving the owner's decisions to the owner |

The marketplace also carries:

| Plugin | What it is |
|---|---|
| `tempergraph-monitor` | A Claude Code mod that shows live runs, alerts, a per-step drill-down and cost |
| `temperspec-tgraph` | temperspec, the delivery workflow: triage, discovery, a plan and tested code to a draft pull request |
| `release-notes-tgraph` | Example workflow: one judged step that writes release notes since the last tag |
| `doc-refresh-tgraph` | Example workflow: a script, a route on a value, a trip back, an approval and a finalizer |

## Guides

| Guide | Covers |
|---|---|
| [Getting started](plugins/tempergraph/docs/guides/getting-started.guide.md) | Requirements, install, preparing a repository, a first run |
| [Running workflows](plugins/tempergraph/docs/guides/running-workflows.guide.md) | Checking and starting runs, exit codes, pauses, reruns, logs and cost |
| [Authoring workflows](plugins/tempergraph/docs/guides/authoring-workflows.guide.md) | The outcome-first interview, verification, the package layout, revisions |
| [Improving workflows](plugins/tempergraph/docs/guides/improving-workflows.guide.md) | Labels, judge calibration, proposals and trials, dev and stable mode |

## The CLI

Every verb is model-free unless it says otherwise, and most print JSON for skills and scripts to read. A few to start with:

| Command | What it does |
|---|---|
| `tempergraph list` | The workflow catalog |
| `tempergraph graph <workflow>` | Draw the workflow |
| `tempergraph run <workflow> --check …` | Preflight a run without spending anything |
| `tempergraph run <workflow> …` | Start a run |
| `tempergraph attention` | Everything waiting on a person, oldest first |
| `tempergraph resume <workflow> <thread> --decision <word>` | Continue a paused run with a person's decision |
| `tempergraph status` · `events` · `logs` | What a run did, step by step |
| `tempergraph report` · `supervision` | Cost, friction and supervision across runs |
| `tempergraph audit <workflow>` | An advisory review of a workflow |
| `tempergraph outcome show <workflow>` | The good outcome and how runs measure against it |
| `tempergraph improve …` · `evals …` · `labels …` | The self-improvement loop, judge calibration and labels |

`tempergraph --help` lists the rest.

## Repository layout

This repository is also a Claude Code plugin marketplace named `tempergraph`.

| Path | What is there |
|---|---|
| [`plugins/tempergraph/`](plugins/tempergraph) | The engine plugin: launcher, skills, hooks and the Python engine in `engine/` |
| [`plugins/tempergraph/docs/guides/`](plugins/tempergraph/docs/guides/README.md) | How-to guides for people who use tempergraph |
| [`plugins/tempergraph/docs/`](plugins/tempergraph/docs/README.md) | The engine's design: overview and component specs, decision records, research and plans |
| [`plugins/tempergraph-monitor/`](plugins/tempergraph-monitor) | The monitor mod and its own design docs |
| [`plugins/release-notes-tgraph/`](plugins/release-notes-tgraph), [`plugins/doc-refresh-tgraph/`](plugins/doc-refresh-tgraph) | Example workflow packages |
| [`plugins/temperspec-tgraph/`](plugins/temperspec-tgraph/README.md) | temperspec, the delivery workflow built on tempergraph: a task goes through triage, discovery, a plan and tested code to a draft pull request. |
| [`assets/`](assets) | The logo, the flow diagram and the social preview image |

The project is designed spec-first: acceptance criteria rank above specs and decision records, which rank above plans, which rank above code. A code change that makes a doc false updates the doc in the same pull request.

## Roadmap

**Release 1** (built, live checks pending): simple trusted workflows on one machine, workflow authoring, full local observability and supervision, and the self-improvement loop, on the Claude Code executor ([scope](plugins/tempergraph/docs/adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md), [plan](plugins/tempergraph/docs/plans/first-release.plan.md)).

**Release 2** (built, live checks pending; engine `0.2.0`): effort ladders and one-step model escalation on evidence, a judge raised by risk, routing by task size, eval suites, promotion to `local-stable`, run state carried on a branch, engine `update` and workflow `upgrade`, ask and wait steps, parallel read-only steps, breakpoints, lifecycle hooks, and runs outside git ([plan](plugins/tempergraph/docs/plans/second-release.plan.md)).

**Designed, not built yet:**

- More executors: the Antigravity CLI, the Claude Agent SDK and the Anthropic Messages API, with refusal before spend when an executor can't enforce what a workflow asks.
- Orchestration: many runs planned as a graph of runs and supervised without a model.
- Advanced node types: contests, sub-workflows and the rest of LangGraph's shapes as workflow data.
- Scheduled runs, Windows, and writing steps side by side in their own worktrees.

**temperspec**, the first large workflow built on the engine, is built as its own package ([`temperspec-tgraph`](plugins/temperspec-tgraph/README.md)); the features it still wants are [issues labelled `area: temperspec`](https://github.com/dbr0vskyi/tempergraph/issues?q=is%3Aissue+is%3Aopen+label%3A%22area%3A+temperspec%22). To contribute, start at [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Proprietary. All rights reserved.
