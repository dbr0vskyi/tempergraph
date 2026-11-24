# R-131 Running a workflow outside a git repository

## Problem statement

The engine finds its state root from git's common directory and refuses to start anywhere else (`NotInRepository` in `store/layout.py`). Release 2 lists "state root outside git" ([ADR-0125](../adr/0125-release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing.adr.md), [R-130](R-130-release-two-readiness-and-gaps.rsrch.md) G1), and the owner asked on 2026-11-20 for research on it. Many workflows are not code (meeting notes, story refinement, a release page), so a folder that is not a repository, or no folder at all, is a real case ([R-011](R-011-design-gap-review.rsrch.md) G9).

The questions: what in the engine depends on git, what each dependency is for, and what replaces it outside a repository without weakening a rule.

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S3 | [R-011](R-011-design-gap-review.rsrch.md) G9: proposed fallback state root, `in_place` only, file hashes for the guard | Design set | research/ |
| S4 | This design: WSP-B8, WSP-B9, WSP-B11 and C10, LOS-B7, LOS-B8, LOS-B9, WTR, GRD (the head-and-status fingerprint), CHK `GitFacts`, FIN (push, draft PR), SIL filing, PRP trials (worktrees at a base), VER stamp and digest, SCH | Design set | [specs](../specs/00-overview.spec.md) |
| S5 | Engine code on `main`: `git.py` (`main_checkout`, `fingerprint`, `branch`, `changed_paths`), `store/layout.py` (`state_root_path`) | Code | `plugins/tempergraph/engine/src/tempergraph/` |

## Key findings

### F1 What git gives the engine today `confirmed`

| Use | Where | What it protects |
|---|---|---|
| Finding the state root from any subfolder or worktree | WSP-B8, WSP-B9, WSP-B11, `store/layout.py` | One state root per project, so locks and checkpoints are never split |
| The workspace fingerprint (head and status) before and after an attempt | GRD, WSP-B11, WSP-B12 parallel branches, JCL fixtures | A read-only session that wrote something is caught |
| `GitFacts` for checks (branch, base, changed paths, commits) | CHK-B10 | Checks that a step committed, stayed on its branch, touched only some paths |
| Engine worktrees, writer branches, trial cases at a base | WTR, WSP, PRP | Isolation of a run's writes; undo by branch |
| Push and draft pull request in a finalizer | FIN | Publishing only after every gate passed |
| Diff statistics for a judge's risk rule and complexity measures | JRK, CXR | Model-free risk and size signals |
| The workflow package's content digest | VER | A package is often in git, but the digest is computed from files, not from git |

Only the first two are needed to run at all; the rest are features a workflow uses or does not.

### F2 Non-code workflows need only a folder and a fingerprint `inferred`

Non-code workflows write files into a folder (a dated meeting folder) or write outside the machine (a tracker story, a wiki page). None of them needs a branch, a worktree or a pull request. What they need is a place for run state and a way to tell whether a read-only session wrote something.

### F3 A file manifest can replace head and status `inferred`

Outside git, "did the workspace change" can be answered by a manifest of `(path, size, mtime_ns)` for every file under the workspace, excluding the state root, with a content hash for files whose size or time changed. This is what backup tools and build systems do for change detection. Costs: a walk of the tree per attempt, so it needs a file limit (for example 20,000 files) beyond which the engine refuses to guard and says so, rather than guard silently partly.

### F4 Where the state root goes `inferred`

| Option | For | Against |
|---|---|---|
| `<start dir>/.tempergraph/` | Simple | A run started in a subfolder makes a second state root |
| Walk up from the start dir to the nearest folder with `.tempergraph/manifest.json`, else the start dir | One root per project, like git's walk-up | A stray `.tempergraph` in a parent folder captures runs |
| A declared root: `--state-root`, `TEMPERGRAPH_STATE_ROOT`, or a `state_root` in the operator config | Explicit; works with no folder at all | One more setting |

Walk-up plus an explicit override, with the home folder never a state root, mirrors git's own discovery and keeps C10's "one root per project".

### F5 A run with no workspace folder `inferred`

A workflow that only reads inputs and writes to remote systems still needs a working directory for its sessions. An engine-made scratch folder under the state root (`work/<workflow>/<task_id>/`), kept for the thread's life, serves; paths still resolve inside it (C10).

## Conclusions

1. Outside git the engine needs two replacements: a state root found by walk-up or declared, and a file-manifest fingerprint.
2. Everything else that uses git becomes a declared requirement: a workflow that needs a worktree, `GitFacts`, a finalizer push, worktree trials or diff signals is refused outside a repository before spend, with a finding naming the feature.
3. `run.workspace` is `in_place` outside git; `auto` resolves to it and `worktree` is refused.
4. A workflow with no folder runs in an engine scratch folder under the state root.

## Open questions

| Question | Who answers | Default until answered |
|---|---|---|
| Is 20,000 files the right ceiling for the manifest fingerprint? | Data | 20,000; a larger workspace runs only if the workflow has no read-only parallel branch and no judge view that writes (nothing to guard), else it is refused |
| Should a folder inside a git repository ever use the non-git rules? | Owner | No: inside a repository git rules apply |
