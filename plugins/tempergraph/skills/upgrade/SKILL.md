---
name: upgrade
description: Bring one workflow package up to the running tempergraph engine on a branch of its source, with a plan first and the owner's decisions left to the owner. Use when the person says "upgrade my workflow" or "make this workflow work with the new engine", or when the update skill reports a pinned workflow with a local source.
---

# Upgrade a workflow

You drive the engine's `upgrade` verb. The verb decides; you read its JSON and exit codes, never its prose. The upgrade never touches the person's checkout: its changes are commits on a branch of its own, in a worktree the report names.

`<workflow>` is the workflow's registered name or the path of its package folder, as `tempergraph workflows list` shows it.

## Never

- Answer an owner's question. When the upgrade pauses, the decision is the person's, word for word.
- Edit the upgrade branch yourself. A fix by hand is the person's, or the authoring skill's on their ask.
- Stamp, bump the version or open a pull request without a yes.
- Run a command that is not in the steps below, or put free text the person typed into a command. Values come from the verbs' output.

## Steps

1. **Plan.** Run `tempergraph upgrade <workflow> --check --format json`. It is read-only and calls no model. Show the pending items with their hits, and say that the upgrade's first step turns each into a transform (done by rule, no cost), an assisted item (a gated model edit) or an owner item (a question for the person).
2. **Run.** Ask one question, naming the cost cap (10 USD unless the person sets another): go ahead. Then run `tempergraph upgrade <workflow> --cap <cap> --format json` in the background. To spend nothing, run `tempergraph upgrade <workflow> --no-assist --format json` instead: the transforms run and the other items are listed for a person.
3. **Read the result.** The output is one JSON report with `exit_code`, `upgrade_id`, `items`, `verification`, `proposed`, `branch` and `worktree`.
4. **Owner pauses (exit 3).** The upgrade's own run, thread `upgrade/<upgrade_id>`, waits for the person. Show the pause from `tempergraph status upgrade/<upgrade_id> --json`: the question, the draft on the branch and what each choice changes. Ask the person, then resume with their decision only: `tempergraph resume upgrade <upgrade_id> --decision proceed` (the draft is the answer), `--decision retry --feedback <their words>` (a new draft), or `--decision stop` (the item is skipped). When the run finishes, go on with `tempergraph upgrade <workflow> --continue <upgrade_id> --format json`.
5. **Verification failed (exit 4).** Show each failing check with its evidence, the items still open, and that the branch is kept. After the person fixes it on the branch (or asks the authoring skill to), run `tempergraph upgrade <workflow> --continue <upgrade_id> --format json`.
6. **Done (exit 0).** Show the items by who did them (the `shares`: transform, model, person), the checks, the proposed version with its level, and anything under `warnings` and `stale`.
7. **Finish.** Offer the three together and run only what the person says yes to, as options of one more `--continue`: `--stamp` (record that the workflow is verified on this engine), `--bump` (write the proposed version and a draft of the change notes to the branch) and `--open-pr` (a draft pull request with the report). Name the `weakens-gate` label when the report says a gate was weakened with the owner's approval. Nothing is merged: the person reviews and merges the branch.

## Exits

| Exit | Do |
|---|---|
| 0 | Step 6 |
| 2 | Refused: quote the reason. An installed copy cannot be upgraded; the person clones the workflow's source and registers that folder. Uncommitted changes in the source are committed or stashed by the person first |
| 3 | Step 4 |
| 4 | Step 5 |
| 5 | The cost cap was spent. Finished items stay on the branch; ask before running again with a higher cap |
