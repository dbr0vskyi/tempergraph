---
name: bootstrap
description: Prepare a repository for tempergraph runs by adding the run-state ignore rule. Use once per repository before the first run, or when run files show up in git status. Writes nothing workflow-shaped.
---

# Prepare a repository for tempergraph

One job: make sure git ignores the engine's run state (`.tempergraph/`) in this repository. Re-running is safe.
The state folder also carries its own `.gitignore`, so this rule is a second guard for tools that read only the
root ignore file.

## Rules

- The helper script is the only writer of the ignore file. Do not edit `.gitignore` yourself.
- Never stage, commit, untrack or delete anything. If git already tracks files under `.tempergraph/`, show the
  person the list and the untrack command the script prints, and let them run it.
- A person's negation (`!.tempergraph/…`) stands. Report it; do not override it.
- Name no workflow; a workflow package may ship its own setup on top of this.

## Procedure

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/bootstrap/scripts/ignore_rule.py" <repository path>`.
2. Read its one JSON line and report:
   - `added`: the rule was appended to the root `.gitignore`; ask the person to review and commit that change.
   - `already_ignored`: nothing to do.
   - `negated`: a rule of theirs un-ignores the folder; show the block in `paste` if they want to fix it.
   - `write_failed`: the file could not be written; give them the `paste` block to add by hand.
   - `not_a_repository`: the folder is not a git repository; nothing was written.
3. If `tracked` is not empty, list those files and show the `untrack` command. Do not run it.
