# A stored command run is keyed on the tree's content, not on the commit

## Context

[ADR-0075](0075-checks-get-a-context-and-an-engine-command-runner.adr.md) gave a check's command runner reuse "keyed by the tree" and named the key in its risk note: head, status and the digest of changed and untracked files. This record refines that key. ADR-0075's decision stands, and the record is not edited.

The key is built by `reuse_key` in `plugins/tempergraph/engine/src/tempergraph/run/checks.py` (lines 132-146): the command's argv and working folder, the resolved program, `HEAD`, the status listing, and the bytes of the changed and untracked files outside the state root. Two facts follow from reading it and its callers:

- A commit changes the key although no file changed. It moves `HEAD` and empties the status listing, so a run stored before a commit is not found after it.
- A commit can come between a step's session and its gate's check. The engine runs a step's `after` scripts after a session that ended `ok` and runs the check after them ([SCR-B2](../specs/script-units-and-hybrid-steps.spec.md); `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` lines 593-595), and a script may commit the step's files. The engine only runs the scripts and does not know which one commits, so it cannot re-key stored runs at that point.

The check preview stores its command runs for reuse, and its spec says the gate's check reuses them on an unchanged tree ([CHK-B17](../specs/check-contract-and-command-runs.spec.md), [CHK-AC6](../specs/check-contract-and-command-runs.spec.md), [ADR-0077](0077-a-step-previews-its-own-check-in-the-attempt.adr.md)). By the code above, for a step whose files are committed after its session the key the preview stored differs from the key the gate computes, so the reuse never happens. No test runs that case.

The task that raised this states the goal: the key must name the tree's content so that it survives the commit. It leaves open how the content is named and what that does to [CHK-B5](../specs/check-contract-and-command-runs.spec.md) and CHK-AC6. The owner is away, so this record takes the choice and states it as an assumption.

## Decision

We will take option A and key a stored command run on the content of the tree: every file git tracks and every untracked file git does not ignore (every file, outside a git repository), outside the state root, each by its path, its bytes and its executable bit. The commit, the index and the status listing are no part of the key. A caller still chooses, call by call, whether to ask for reuse. The behaviour is [CHK-B13](../specs/check-contract-and-command-runs.spec.md), proved together with the preview by CHK-AC12 of the same spec.

## Options considered

### A. A digest of each file's path, bytes and executable bit (chosen)

For: nothing in the key depends on history, so a commit, an amend, a reset or a checkout that leaves the files as they were leaves the key as it was, and any change to a file changes it. One rule serves CHK-B5's "nothing in the tree changed" and the preview's "unchanged tree". It is tested with a scratch repository and no knowledge of how git stores objects. Against: it reads every file git lists on each call that asks for reuse, so the cost grows with the tree and is paid for each command before a hit.

### B. Git's tree object of the working tree, made from a temporary index

For: it is the value a commit records, and git's stat cache keeps it fast. Against: it writes objects into the repository's store from a check that must change nothing but command runs ([CHK](../specs/check-contract-and-command-runs.spec.md) Purpose); it needs a temporary index and an exclusion for the state root; and it takes on git's own treatment of line endings and attributes.

### C. Keep `HEAD` and the status listing and re-key stored runs at each commit

For: the key is unchanged. Against: the engine does not know which script commits (it only runs `after` scripts), so it has nothing to hook; a workflow's script would have to call back into the engine's store.

## Consequences

- Reuse survives a commit, an amend, a reset and a checkout of the same content, and a retry that undoes its edits finds the earlier run. A changed byte, a changed executable bit, and a file added or removed outside git's ignore rules each make the key differ.
- CHK-B5 holds as written: "nothing in the tree changed" now means the same content, and its two scenarios are unchanged. CHK-AC6 holds as written, and its "unchanged tree" now includes a commit in between, which CHK-AC12 proves.
- Reuse still rests on ADR-0075's assumption that a command's result depends on the tree's content and on nothing else. A command whose result depends on history (a log, or a diff against another commit) is answered from the earlier run when the content is the same. The commit in the old key was a weak guard against that. The caller that passes `reuse=True` chooses its commands, and ADR-0075's mitigation stands: a workflow passes `reuse=False` for a command that reads elsewhere.
- Files git ignores stay outside the key, as before. A command that reads one (a virtual environment, a build output) can be answered from an earlier run.
- Outside a git repository, git prints nothing, so the old key held no file content and every call after the first was a hit. The new key covers every file under the workspace outside the state root, so a changed file runs again.
- Runs stored by an older engine version keep their old keys and are not found: one extra run for a run in flight at an upgrade, never a wrong answer.
- Risk: the cost of reading the tree on each call that asks for reuse. Not measured here. Limit: only a call with `reuse=True` computes the key, the reading is bounded by the size of the tree, and the commands that ask for reuse are the long ones (tests, linters, type checks). How the digest is computed is left to the plan, which measures it on this repository; any way that names content only is allowed.
- Risk: the resolved program is part of the key, and it is found on the `PATH` of the process that runs the check. A preview runs in the step's own shell and the gate's check in the engine's process; if their `PATH`s differ the keys differ and the command runs again. That costs time and never gives a wrong answer, and the run records of the gate's check show it with `reused: false`.

## Revisit when

A command whose result depends on history must be reused, or reading the tree on each call costs more than the commands it saves.
