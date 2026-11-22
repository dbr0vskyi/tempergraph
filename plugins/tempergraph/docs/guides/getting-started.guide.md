# Getting started

This guide takes you from nothing to a first run of an example workflow.

## What you need

- macOS or Linux
- Python 3.11 or newer
- git, and a git repository to run workflows in
- [Claude Code](https://docs.claude.com/en/docs/claude-code), installed and signed in (`claude --version` prints a version)

Releases 1 and 2 run every step on Claude Code. The other executors are designed but not built yet.

## 1. Add the plugin marketplace

This repository is a Claude Code plugin marketplace named `tempergraph`.

```sh
git clone https://github.com/dbr0vskyi/tempergraph.git
claude plugin marketplace add ./tempergraph
claude plugin install tempergraph@tempergraph
```

> [!NOTE]
> Installing from the plugin is live check L-16 and is not confirmed yet.

Optional plugins from the same marketplace:

| Plugin | What it adds |
|---|---|
| `tempergraph-monitor` | Live runs, alerts, a per-step drill-down and cost, inside Claude Code |
| `release-notes-tgraph` | Example workflow: one judged step that writes release notes since the last tag |
| `doc-refresh-tgraph` | Example workflow: a script, a route on a value, a trip back, an approval and a finalizer |

## 2. Install the engine

In Claude Code, say:

> Install tempergraph.

The `install` skill checks your machine, then shows one plan: the Python it found, where the engine will live, and an optional change to your `PATH`. Say yes once and it installs, then probes that `claude` is installed, signed in and at a tested version. It never installs Claude Code or touches your credentials.

The same steps by hand, where `<plugin>` is the installed plugin's folder:

```sh
<plugin>/bin/tempergraph install --check --json    # look, change nothing
<plugin>/bin/tempergraph install --add-to-path     # install; drop --add-to-path to edit PATH yourself
tempergraph executors --probe                       # in a new terminal: is claude ready?
```

## 3. Prepare a repository

Runs keep their state in `.tempergraph/` inside the repository. Make git ignore it once per repository:

> Prepare this repository for tempergraph.

The `bootstrap` skill adds the ignore rule to `.gitignore` and tells you to review and commit it. It never commits for you.

## 4. Try an example

Register an example workflow, look at it, then run it:

```sh
tempergraph workflows register <clone>/plugins/release-notes-tgraph
tempergraph list                          # the catalog
tempergraph graph release-notes           # what it will do
tempergraph run release-notes --check v1.2   # preflight: spends nothing
tempergraph run release-notes v1.2
```

Or ask Claude: "Run the release-notes workflow for v1.2." The `run` skill checks first, starts the run, and reports how it ended.

A run spends money on Claude Code sessions: one per step attempt plus one per judge. Each run has a cost cap; see `tempergraph config show <workflow>`.

## Next

- [Running workflows](running-workflows.guide.md): pauses, reruns, logs and cost.
- [Authoring workflows](authoring-workflows.guide.md): build your own.

## Working on tempergraph itself

```sh
cd plugins/tempergraph/engine
python -m pip install -e '.[dev]'
python -m pytest     # offline, stand-in executors only
ruff check src tests
mypy
```
