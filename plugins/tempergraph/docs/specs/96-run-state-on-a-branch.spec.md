---
title: Run state carried on a branch
type: component
status: review
prefix: CAR
adrs: [0126]
---

# Run state carried on a branch

## 1. Overview

A paused run resumes only where its state root is. Until pipelines arrive in a later release, a person may **carry** one run's state through git: the engine commits a scrubbed, thread-scoped copy of the run's state to a **state branch** of its own, pushes it, and another machine pulls it and resumes. When the thread finishes, the engine deletes the state branch locally and on the remote, so no trace stays in the work branch, its pull request or the remote ([R-133](../research/R-133-carrying-run-state-on-a-branch.rsrch.md), [ADR-0126](../adr/0126-a-run-carries-a-scrubbed-thread-state-on-its-own-branch-and-deletes-it-when-done.adr.md)).

Carrying is off unless a person turns it on for the run. It never carries transcripts, prompts, operator config, executor scratch or another thread's state.

## 2. Contract

```text
tempergraph run … --carry                       # turn carrying on for a new thread
tempergraph resume <workflow> <thread> --carry  # or for an existing one
tempergraph carry push|pull|status|drop <workflow> <thread> [--remote <name>] [--force] [--json]
```

### 2.1 The state branch

| Rule | Value |
|---|---|
| Name | `tempergraph/state/<workflow>/<task_id>`, ref-safe by the rule of [WTR §2.4](82-worktree-mode.spec.md) |
| History | An orphan branch: it shares no commit with any work branch; each push adds one commit by the engine's identity with the subject `tempergraph state <workflow>/<task_id> seq <n>` |
| Remote | The work branch's upstream remote, else `origin`, else `--remote`; none is a refusal |
| Contents | `.tempergraph-carry/` only (§2.2); a commit that would hold any other path is refused |
| Written by | The engine through git plumbing (`hash-object`, `mktree`, `commit-tree`, `update-ref`, `push`), without touching any checkout or the index |

### 2.2 What is carried

| Path in `.tempergraph-carry/` | From the state root ([LOS §2.1](33-local-observability-store.spec.md)) |
|---|---|
| `carry.json` | The manifest: schema, engine version, store layout, checkpoint format, workflow version, `seq`, `lease` (§2.4), the list of files with digests |
| `checkpoint.sqlite` | Only this thread's rows of `checkpoints/<workflow>.sqlite` |
| `run/` | `runs/<workflow>/<task_id>/` without `sessions/*/raw.jsonl`, `stderr.log`, `output/`, `evidence/prompts/`, `checks/` and `hooks/`; `sessions/*/meta.json`, `activity.jsonl` and `digest.json` are kept |
| `ledger.jsonl` | Only this thread's ledger rows |
| `workspace.json` | The `WorkspaceRecord` with the branch and base, and paths made relative to the root rule ([WTR §2.2](82-worktree-mode.spec.md)) |

Every text file passes the run log's scrubber before it is written ([SEC §2.3](14-security.spec.md)); a scrubber hit is replaced as in the run log and counted in `carry.json`. Never carried: `config/`, `scratch/`, `locks/`, other threads, `authoring/`, `upgrades/`, `backups/`, `engine/`, the home folder.

### 2.3 When it happens

| Event, with carrying on | Effect |
|---|---|
| The run pauses (exit 3) or exits unfinished or stopped | Push, releasing the lease |
| `carry push` | Push now; refused while the run is running in another process |
| `carry pull` on a machine without the thread | Fetch the branch, check §2.5, import the checkpoint rows and files, take the lease on the next resume |
| `carry pull` on a machine that has the thread | Refused unless the carried `seq` is newer than the local one; then the local copy is replaced after a backup under `backups/` |
| The thread finishes (exit 0, or a person's final stop) | Delete the state branch locally and on the remote; the local state root keeps its copy as for any finished run |
| `carry drop` | The same deletion, at a person's word, for a thread that will not be resumed |

### 2.4 Lease

A resume of a carried thread writes `lease: {machine, process, since}` to the state branch before its first attempt, and a pause or exit clears it in the same push that carries the new state. A pull or a resume elsewhere is refused while a lease names another machine, with the machine and time; `--force` takes it, recorded as a `steer` touch with the caller ([SUP](86-supervision-metrics.spec.md), [PRV](85-caller-provenance.spec.md)). A push rejected as not fast-forward means another machine pushed first: the engine keeps its local state, pushes nothing, and tells the person to pull.

### 2.5 Checks before a pull imports

| Check | On failure |
|---|---|
| `carry.json` parses and every file's digest matches | Refused, exit 2 |
| Checkpoint format and store layout not newer than this engine ([MIG](62-state-and-run-migration.spec.md)) | Refused with the needed engine version |
| The workflow is registered here at the carried workflow version | Refused, or with `--force`, the change-under-a-thread rules of MIG apply |
| The work branch exists on the remote | Refused: there is nothing to resume on |

After the import, resume re-attaches or recreates the worktree on the recorded branch under this machine's worktree root, as after a deleted worktree ([WTR](82-worktree-mode.spec.md)).

## 3. Behaviours

**CAR-B1 Pause on one machine, resume on another.** Given a run started with `--carry` that pauses at gate `plan` on machine A, when it exits 3, then branch `tempergraph/state/notes/T-12` holds one new commit with `.tempergraph-carry/` and no lease, and the work branch has no new commit; when a person on machine B runs `carry pull notes T-12` and `resume notes T-12 --decision proceed`, then the run continues at the step after `plan`.

**CAR-B2 Nothing private travels.** Given a carried thread whose sessions wrote `raw.jsonl` and whose evidence holds `prompts/`, when it is pushed, then the state branch holds neither, and a canary secret placed in a step's output appears scrubbed in `run/` ([SEC-B2](14-security.spec.md)).

**CAR-B3 No trace after the finish.** Given a carried thread, when it finishes with exit 0, then `git ls-remote` lists no `tempergraph/state/…` branch for it and the work branch's history holds no `.tempergraph-carry/` path.

**CAR-B4 One driver.** Given a lease held by machine A, when machine B runs `carry pull`, then it is refused naming A and the time; with `--force` it imports and records the takeover.

| Machine B | Lease | Result |
|---|---|---|
| `carry pull` | none | imported |
| `carry pull` | A, held | refused |
| `carry pull --force` | A, held | imported, takeover recorded |
| resume after A pushed again | — | refused until B pulls |

## 4. Error conditions

| Condition | Result |
|---|---|
| No git repository, or no remote | `--carry` refused at start, exit 2 |
| A push fails on the network | The run's exit code is unchanged (contract C2); the status row shows `carry: unpushed` and `carry push` retries |
| The remote refuses the deletion at finish | Recorded; `attention` lists the branch with the `carry drop` command |
| A path outside `.tempergraph-carry/` in a state commit | Refused before the commit |

## 5. Design notes

- A separate orphan branch keeps state out of the work branch, its pull request and its diff statistics, and is deleted whole; a removal commit on the work branch would leave the state in its history ([R-133](../research/R-133-carrying-run-state-on-a-branch.rsrch.md) F4).
- The subset is what a resume reads; transcripts and prompts stay local by LOS's marks and contract C9.
- Plumbing commits touch no checkout, so a carry never disturbs the person's working tree or the run's worktree.
- **As built (R2-T5.2).** `durability/carry.py`. Each machine keeps its own record of a carried thread in `runs/<workflow>/<task_id>/carry.local.json` (on or off, remote, state, last pushed `seq`), which is never carried. `seq` is the run log's last sequence number. A push fetches the state branch first and is refused when the branch holds a newer `seq` or another machine's lease; the new commit's parent is the fetched tip, so the branch stays a line of engine commits. The engine never pushes the work branch: the person pushes it, and a pull refuses until it is on the remote. A pull creates the local work branch from the remote when it is missing, and the next resume moves the workspace record to this machine's worktree root; for a run in the checkout itself the pull says which branch to check out. A forced pull is one `intervention` ledger row with a `steer` touch, the caller and the machine it was taken from. The thread's status row shows `carry` (`unpushed`, `delete_failed`) when something is left to do; `carry status` compares the local and the remote `seq` and shows the lease. A finish with exit 0 deletes the branch; a stopped thread is pushed and ends with `carry drop`. Open: `attention` does not yet list a branch whose deletion the remote refused (the status row and `carry status` do).

## 6. Acceptance criteria

- [x] CAR-AC-1 CAR-B1 to CAR-B4 and every row of the CAR-B4 table hold offline with two state roots and one bare remote repository.
- [x] CAR-AC-2 No state commit holds a path outside `.tempergraph-carry/`, and none of the never-carried paths of §2.2 (fixture with every LOS file present).
- [x] CAR-AC-3 A finished carried thread leaves no ref under `refs/heads/tempergraph/state/` locally or on the remote.
- [x] CAR-AC-4 Each row of §2.5 refuses with its message on a fixture.

## Open questions

| Question | Owner | Default |
|---|---|---|
| State branch or the work branch? | Owner: state branch (decided 2026-11-21) | State branch |
| Should a workflow be able to default carrying on? | Owner | No: a person turns it on per run |

## References

[LOS](33-local-observability-store.spec.md) · [DUR](09-durability-and-resume.spec.md) · [WTR](82-worktree-mode.spec.md) · [MIG](62-state-and-run-migration.spec.md) · [SEC](14-security.spec.md) · [R-133](../research/R-133-carrying-run-state-on-a-branch.rsrch.md)
