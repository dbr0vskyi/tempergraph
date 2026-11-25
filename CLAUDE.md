# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Release 1 was built from `plugins/tempergraph/docs/plans/first-release.plan.md`, one track plan per track (`plugins/tempergraph/docs/plans/t<N>-*.plan.md`); release 2 from `plugins/tempergraph/docs/plans/second-release.plan.md` (track plans `r2-t<N>-*.plan.md`, each with a triage note and a code report in `plugins/tempergraph/docs/tasks/`). Both wait on the owner's own live checks in `plugins/tempergraph/docs/plans/live-checks.plan.md` (every check a cloud container can run has passed). Release 3 is scoped by ADR-0132 (accepted) and planned in `plugins/tempergraph/docs/plans/third-release.plan.md`. The engine's Python source is the plugin's staged engine at `plugins/tempergraph/engine/` (src layout, ADR-0115). **Scope lives in GitHub issues** (owner, 2026-11-23): everything planned and not built (features, bugs, debt, open live checks, owner decisions) is an issue with type, area, priority and effort labels; there is no backlog, roadmap or TODO file. Labels are in `.github/labels.yml`, issue forms in `.github/ISSUE_TEMPLATE/`, and the process, including how agents communicate through issue and pull request comments, in `CONTRIBUTING.md`. Release plans, per-task plans, task notes and live-check runbooks stay as records. Truth ranking: acceptance criteria, then specs and decision records, then plans, then code; a code change that makes a doc false updates the doc in the same pull request.

## Commands

Run from `plugins/tempergraph/engine/`:

- Install: `python -m pip install -e '.[dev]'` (Python 3.11+)
- Test: `python -m pytest` (offline; stand-in executors only). It runs on up to four workers by default (one per processor, at most four; `pytest-xdist` comes with the `dev` extra); `python -m pytest -n 0` runs one process, and so does a run where `pytest-xdist` is missing. `TEMPERGRAPH_SUITE_AUDIT=1` adds the slow check that every test file passes alone. Live checks against a signed-in `claude` are marked `live` and run only with `TEMPERGRAPH_LIVE=1`.
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
- `temperspec-tgraph`: the temperspec delivery workflow (see Layout).
- `release-notes-tgraph` and `doc-refresh-tgraph`: example workflow packages (workflows `release-notes` and `doc-refresh`) (first-release plan T11.1); the engine's `tests/test_workflow_packages.py` finds every package under `plugins/` by its `tempergraph.json`, loads it and runs its own tests, so a change that breaks one fails the engine's suite.

Layout:

- `.claude-plugin/marketplace.json`: marketplace catalog (named `tempergraph`); add every new plugin here.
- `plugins/<name>/.claude-plugin/plugin.json`: per-plugin manifest.
- `plugins/<name>/docs/`: every plugin has a docs folder, reserved for specs. The engine's user-facing how-to guides live in `plugins/tempergraph/docs/guides/*.guide.md` and are linked from the root README; keep them true to the CLI and skills.
- `plugins/tempergraph-monitor/docs/{specs,adr,research}/`: the monitor mod's own design set, same rules as the engine's (start at its `README.md`); it reads only engine documents defined in the engine specs 09 and 30 to 35.
- Workflow packages (temperspec and any authored workflow) are Claude plugins with a Python part and their own `docs/{specs,adr,research}/` in the engine's shape, rules provisional until temperspec owns them (engine spec 88, PKG). A workflow plugin is named `<workflow name>-tgraph` (for example `release-notes-tgraph`); the workflow name inside the engine stays short (ADR-0120).
- `plugins/tempergraph/docs/{specs,adr,research,plans}/`: the engine's design (overview and component specs, decision records, research notes), written per the temperspec method. Start at `plugins/tempergraph/docs/README.md`. New artifacts use a type suffix (`*.spec.md`, `*.adr.md`, `*.rsrch.md`, `*.plan.md`, …); the rule is under File naming in that README. Engine features found useful and not built yet are GitHub issues labelled `area: engine` (their text names no workflow).
- `plugins/temperspec-tgraph/`: **temperspec**, the delivery workflow (repository setup when needed → triage → discovery → plan → code → draft pull request), authored through the engine's own authoring path. Besides the package parts it ships `rules/*.rule.md` (how specs, plans, decision records, research notes and task notes are written, and `extraction.rule.md`, how behaviours are extracted from existing code; every rule file but `documents.rule.md` starts with a `paths` front matter that says when Claude Code loads it; `workflow/temperspec/specfmt.py` reads the same formats and `tests/test_temperspec.py` holds the two together) and the `setup` skill that installs them (after a rule changes, run `python plugins/temperspec-tgraph/skills/setup/install_rules.py --update` so this repository's copy in `.claude/rules/temperspec/` stays the same), and the `extract` skill. Its own tests run with the engine's suite (`tests/test_workflow_packages.py`). Features found useful and not built yet are GitHub issues labelled `area: temperspec`: open one when the owner wants a feature, close it with the pull request that builds it.

**The engine knows no workflow (ADR-0129).** No engine source, skill, test or plan row names a workflow package; tests find packages, they never list them. A workflow may need an engine change, extension or fix: write the need in the package's docs first, then make the engine change as a general capability, stated in the engine's specs without the workflow and tested with an engine fixture. If it cannot be said without naming the workflow, it belongs in the package. Tests of one workflow's own behaviour and its live checks live in that package.

Use the `plugin-authoring` skill when making mods or hooks.

## Notes

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `style`, `revert`. The scope is optional, e.g. a plugin name (`docs(tempergraph): …`). Mark breaking changes with `!` or a `BREAKING CHANGE:` footer.
- Repo: github.com/dbr0vskyi/tempergraph (private), default branch `main`.
- `.vscode/settings.json` holds only an `airun.settings` workspace ID; it is untracked editor config.

<!-- temperspec:start -->
## temperspec

This repository is developed with temperspec: a change goes from a task with acceptance criteria through
behaviour specs and a plan to tested code.

- Specs are in `docs/specs/` (`*.spec.md`), starting at the overview spec. Decision records are in `docs/adr/`,
  research notes in `docs/research/`, plans in `docs/plans/`, task notes in `docs/tasks/`.
- How each document is written: the rule files in `.claude/rules/temperspec/`; fill-in templates generated from
  them are in `docs/templates/`.
- When two sources disagree: the task's acceptance criteria, then specs and decision records, then the plan,
  then the code. A code change that makes a spec false changes the spec in the same change.
- A test that proves an acceptance criterion of a spec carries the criterion's id.
- Start a run with `tempergraph run temperspec "<the task and its acceptance criteria>"`.
<!-- temperspec:end -->
