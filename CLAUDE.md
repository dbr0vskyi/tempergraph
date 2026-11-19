# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

tempergraph is at the early-concept stage: there is no source code, build system, test suite or commits yet. Only `README.md` and `CONTEXT.md` exist. Do not invent build/lint/test commands; update this file once tooling is added (more project info is expected to be provided later).

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
- Possibly others, to be defined.

Layout (scaffolded, plugins are empty for now):

- `.claude-plugin/marketplace.json`: marketplace catalog (named `tempergraph`); add every new plugin here.
- `plugins/<name>/.claude-plugin/plugin.json`: per-plugin manifest.
- `plugins/<name>/docs/`: every plugin has a docs folder, reserved for specs.
- `plugins/tempergraph-monitor/docs/{specs,adr,research}/`: the monitor mod's own design set, same rules as the engine's (start at its `README.md`); it reads only engine documents defined in the engine specs 09 and 30 to 35.
- `plugins/tempergraph/docs/{specs,adr,research,plans}/`: the engine's design (overview and component specs, decision records, research notes), written per the temperspec method. Start at `plugins/tempergraph/docs/README.md`. New artifacts use a type suffix (`*.spec.md`, `*.adr.md`, `*.rsrch.md`, `*.plan.md`, …); the rule is under File naming in that README. Engine features found useful and not built yet are GitHub issues labelled `area: engine` (their text names no workflow).

Use the `plugin-authoring` skill when making mods or hooks.

## Notes

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `style`, `revert`. The scope is optional, e.g. a plugin name (`docs(tempergraph): …`). Mark breaking changes with `!` or a `BREAKING CHANGE:` footer.
- Repo: github.com/dbr0vskyi/tempergraph (private), default branch `main`.
- `.vscode/settings.json` holds only an `airun.settings` workspace ID; it is untracked editor config.
