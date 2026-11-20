# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Release 1 is being built from `plugins/tempergraph/docs/plans/first-release.plan.md`, one track plan per track (`plugins/tempergraph/docs/plans/t<N>-*.plan.md`). The engine's Python source is the plugin's staged engine at `plugins/tempergraph/engine/` (src layout, ADR-0115). Truth ranking: acceptance criteria, then specs and decision records, then plans, then code; a code change that makes a doc false updates the doc in the same pull request.

## Commands

Run from `plugins/tempergraph/engine/`:

- Install: `python -m pip install -e '.[dev]'` (Python 3.11+)
- Test: `python -m pytest` (offline; stand-in executors only). Live checks against a signed-in `claude` are marked `live` and run only with `TEMPERGRAPH_LIVE=1`.
- Lint: `ruff check src tests`
- Types: `mypy`

## What the project is

An opinionated, LangGraph-based Python framework ("Tempered rails for AI workflows") that enforces AI engineering best practices so non-experts can still build good workflows. Intended capabilities:

- Start from a user-defined description of a good outcome.
- Deterministic (rule-based) checks.
- LLM-as-judge checks for what rules cannot express.
- Graph loopbacks/retries driven by check verdicts.
- Self-improvement loop and other batteries-included features.

## Repo is also a Claude Code plugin marketplace

Besides the framework, this repo is a Claude plugin marketplace with several plugins built around tempergraph:

- `tempergraph`: the engine itself.
- `tempergraph-monitor`: a Claude Mod showing progress of runs, etc.
- `release-notes` and `doc-refresh`: example workflow packages (first-release plan T11.1); the engine's `tests/test_examples.py` loads and runs them on stand-ins, so a change that breaks them fails the engine's suite.

Layout:

- `.claude-plugin/marketplace.json`: marketplace catalog (named `tempergraph`); add every new plugin here.
- `plugins/<name>/.claude-plugin/plugin.json`: per-plugin manifest.
- `plugins/<name>/docs/`: every plugin has a docs folder, reserved for specs.
- `plugins/tempergraph-monitor/docs/{specs,adr,research}/`: the monitor mod's own design set, same rules as the engine's (start at its `README.md`); it reads only engine documents defined in the engine specs 09 and 30 to 35.
- Workflow packages (temperspec and any authored workflow) are Claude plugins with a Python part and their own `docs/{specs,adr,research}/` in the engine's shape, rules provisional until temperspec owns them (engine spec 88, PKG). A workflow plugin is named `<workflow name>-tgraph` (for example `release-notes-tgraph`); the workflow name inside the engine stays short (ADR-0120).
- `plugins/tempergraph/docs/{specs,adr,research,plans}/`: the engine's design (overview and component specs, decision records, research notes), written per the temperspec method. Start at `plugins/tempergraph/docs/README.md`. New artifacts use a type suffix (`*.spec.md`, `*.adr.md`, `*.rsrch.md`, `*.plan.md`, …); the rule is under File naming in that README. Engine features found useful and not built yet are GitHub issues labelled `area: engine` (their text names no workflow).

Use the `plugin-authoring` skill when making mods or hooks.

## Notes

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `style`, `revert`. The scope is optional, e.g. a plugin name (`docs(tempergraph): …`). Mark breaking changes with `!` or a `BREAKING CHANGE:` footer.
- Repo: github.com/dbr0vskyi/tempergraph (private), default branch `main`.
- `.vscode/settings.json` holds only an `airun.settings` workspace ID; it is untracked editor config.
