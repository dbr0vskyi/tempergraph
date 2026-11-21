---
name: setup
description: Install or update the temperspec rule files (spec, plan, decision record, research note, task notes) in this repository or for the whole machine. Use when the user asks to set up temperspec, install its rules, or update them after a plugin update.
---

# Set up temperspec rules

temperspec ships rule files that say how each document is written. Claude Code loads them from `.claude/rules/temperspec/` of a repository, or from `~/.claude/rules/temperspec/` for every repository on the machine.

A temperspec run installs the rules into the repository by itself when neither place has them. Use this skill to install them ahead of a run, to install them for the whole machine, or to update them.

## Steps

1. Decide the place. The repository is the default. Use the whole machine only when the user asks for it.
2. Run the installer that sits next to this file, from the repository root:
   - repository: `python3 <this skill's folder>/install_rules.py`
   - whole machine: `python3 <this skill's folder>/install_rules.py --global`
   - add `--update` to replace rule files that differ from the plugin's version.
3. Report the lines the installer printed. A file it reports as `kept (differs)` was edited locally: tell the user, and replace it only when they say so.
4. For a repository install, tell the user the files are new and uncommitted.

Do not edit the rule files in the plugin. A repository that needs a different rule edits its own copy.
