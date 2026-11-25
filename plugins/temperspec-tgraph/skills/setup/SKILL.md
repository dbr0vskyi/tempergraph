---
name: setup
description: Install or update the temperspec rule files (spec, extraction, plan, decision record, research note, task notes) and their fill-in templates in this repository, or the rule files for the whole machine. Use when the user asks to set up temperspec, install its rules, or update them after a plugin update.
---

# Set up temperspec rules

temperspec ships rule files that say how each document is written. Claude Code loads them from `.claude/rules/temperspec/` of a repository, or, for interactive use, from `~/.claude/rules/temperspec/` for every repository on the machine; the step sessions of a run read only the repository's rule files. A repository install also writes fill-in templates into `docs/templates/` (`plan.template.md`, `spec.template.md`, `decision.template.md`, `research.template.md` and one per task note). Each is generated from the example in its rule file, so the plugin holds no second copy.

A temperspec run installs the rules into the repository by itself whenever the repository holds none (neither its own `.claude/rules/temperspec/` nor a folder that holds all seven rule files), the machine's folder not counting, adds the temperspec note to `CLAUDE.md` unless that file already names where the specs are, in which case it is left unchanged, writes `tempergraph.commands.json` for a Python repository that has none (an existing one is left unchanged), and writes the overview and component specs when the repository has no overview spec. This skill covers the rule files only. Use this skill to install them ahead of a run, to install them for the whole machine, or to update them.

## Steps

1. Decide the place. The repository is the default. Use the whole machine only when the user asks for it.
2. Run the installer that sits next to this file, from the repository root:
   - repository: `python3 <this skill's folder>/install_rules.py`
   - whole machine: `python3 <this skill's folder>/install_rules.py --global`
   - add `--update` to replace rule files that differ from the plugin's version.
3. Report the lines the installer printed. A file it reports as `kept (differs)` was edited locally: tell the user, and replace it only when they say so. A template is changed by changing its rule; `--update` writes it again.
4. For a repository install, tell the user the files are new and uncommitted.

Do not edit the rule files in the plugin. A repository that needs a different rule edits its own copy.
