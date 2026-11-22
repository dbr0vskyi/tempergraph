# Run state carried on a branch

## Purpose

A paused run resumes only where its state root is. Until pipelines arrive, a person may carry one run's state through git: the engine commits a scrubbed, thread-scoped copy of the run's state to a state branch of its own, pushes it, and another machine pulls it and resumes; when the thread finishes, the engine deletes the state branch locally and on the remote, so no trace stays in the work branch, its pull request or the remote ([R-133](../research/R-133-carrying-run-state-on-a-branch.rsrch.md), [ADR-0126](../adr/0126-a-run-carries-a-scrubbed-thread-state-on-its-own-branch-and-deletes-it-when-done.adr.md)). Carrying is off unless a person turns it on for the run, and it never carries transcripts, prompts, operator config, executor scratch or another thread's state. A person moving a paused run between machines, and later the pipeline stage ([PRO](95-promotion-check.spec.md)), depend on it; design notes are in [R-150](../research/R-150-rationale-carried-from-the-engine-specs.rsrch.md).

## Behaviours

### CAR-B1 Pause on one machine, resume on another

WHEN a carried run pauses on one machine THE engine SHALL push one new state commit with no lease and no commit on the work branch, and a `carry pull` and `resume` on another machine SHALL continue the run at the step after the pause.

- GIVEN a run started with `--carry` that pauses at gate `plan` on machine A WHEN it exits 3 THEN `tempergraph/state/notes/T-12` holds one new commit with `.tempergraph-carry/` and the work branch has no new commit
- GIVEN that branch WHEN machine B runs `carry pull notes T-12` and `resume notes T-12 --decision proceed` THEN the run continues at the step after `plan`

### CAR-B2 Nothing private travels

WHEN a carried thread is pushed THE engine SHALL leave out every never-carried file and pass every text file through the run log's scrubber ([SEC-B8](14-security.spec.md)), counting each hit in `carry.json`.

- GIVEN sessions that wrote `raw.jsonl`, evidence holding `prompts/` and a canary secret in a step's output WHEN the thread is pushed THEN the branch holds neither file and the canary appears scrubbed in `run/` ([SEC-B2](14-security.spec.md))

### CAR-B3 No trace after the finish

WHEN a carried thread finishes with exit 0 or a person's final stop THE engine SHALL delete its state branch locally and on the remote, the local state root keeping its copy as for any finished run.

- GIVEN a carried thread WHEN it finishes with exit 0 THEN `git ls-remote` lists no `tempergraph/state/…` branch for it and the work branch's history holds no `.tempergraph-carry/` path

### CAR-B4 One driver

WHEN a pull or resume meets a lease held by another machine THE engine SHALL refuse it naming the machine and the time, and with `--force` import it and record the takeover as one `intervention` ledger row with a `steer` touch, the caller and the machine it was taken from ([SUP](86-supervision-metrics.spec.md), [PRV](85-caller-provenance.spec.md)).

- GIVEN no lease WHEN machine B runs `carry pull` THEN it imports
- GIVEN a lease held by A WHEN machine B runs `carry pull` THEN it is refused naming A and the time
- GIVEN a lease held by A WHEN machine B runs `carry pull --force` THEN it imports and records the takeover
- GIVEN A pushed again after B's pull WHEN B resumes THEN it is refused until B pulls

### CAR-B5 Carry verbs

WHEN carrying is asked for THE engine CLI SHALL accept `run … --carry` for a new thread and `resume <workflow> <thread> --carry` for an existing one, refusing with exit 2 at start where there is no git repository or no remote; and offer `carry push|pull|status|drop <workflow> <thread> [--remote <name>] [--force] [--json]`, `carry push` pushing now and being refused while the run is running in another process, `carry status` comparing the local and remote `seq` and showing the lease, and `carry drop` deleting the branch at a person's word for a thread that will not be resumed; each machine keeping its own record of a carried thread in `runs/<workflow>/<task_id>/carry.local.json` (on or off, remote, state, last pushed `seq`), never carried.

- GIVEN a repository with no remote WHEN `run notes --carry` starts THEN it exits 2

### CAR-B6 The state branch

WHEN a state commit is made THE engine SHALL name the branch `tempergraph/state/<workflow>/<task_id>`, ref-safe by [WTR-B20](82-worktree-mode.spec.md); keep it an orphan sharing no commit with any work branch, each push adding one commit by the engine's identity with the subject `tempergraph state <workflow>/<task_id> seq <n>` (`seq` the run log's last sequence number) whose parent is the fetched tip; push to the work branch's upstream remote, else `origin`, else `--remote`, none being a refusal; hold only `.tempergraph-carry/`, refusing before the commit one that would hold any other path; write through git plumbing (`hash-object`, `mktree`, `commit-tree`, `update-ref`, `push`) without touching any checkout or the index; and never push the work branch, which the person pushes.

- GIVEN a state commit WHEN its tree is read THEN it holds only `.tempergraph-carry/` and shares no commit with the work branch

### CAR-B7 What is carried

WHEN a thread's state is copied from its state root ([LOS-B7](33-local-observability-store.spec.md)) THE engine SHALL write into `.tempergraph-carry/` `carry.json` (schema, engine version, store layout, checkpoint format, workflow version, `seq`, `lease`, the list of files with digests); `checkpoint.sqlite` with only this thread's rows of `checkpoints/<workflow>.sqlite`; `run/`, the thread's `runs/<workflow>/<task_id>/` without `sessions/*/raw.jsonl`, `stderr.log`, `output/`, `evidence/prompts/`, `checks/` and `hooks/`, keeping `sessions/*/meta.json`, `activity.jsonl` and `digest.json`; `ledger.jsonl` with only this thread's rows; and `workspace.json`, the `WorkspaceRecord` with branch and base and paths made relative to the root rule ([WTR-B18](82-worktree-mode.spec.md)); never `config/`, `scratch/`, `locks/`, other threads, `authoring/`, `upgrades/`, `backups/`, `engine/` or the home folder.

- GIVEN a fixture state root with every store file present WHEN it is pushed THEN no never-carried path is in the commit

### CAR-B8 When carrying happens

WHEN carrying is on THE engine SHALL push, releasing the lease, when the run pauses (exit 3) or exits unfinished or stopped; on `carry pull` on a machine without the thread fetch the branch, run the import checks, import the checkpoint rows and files, create the local work branch from the remote when it is missing, and take the lease on the next resume; on `carry pull` on a machine that has the thread refuse unless the carried `seq` is newer, then replace the local copy after a backup under `backups/`; and on a failed push keep the run's exit code (OVR-B4), show `carry: unpushed` on the status row and retry on `carry push`.

- GIVEN a network failure at the pause push WHEN the run exits 3 THEN the exit code stays 3 and the status row shows `carry: unpushed`

### CAR-B9 Lease

WHEN a carried thread is resumed THE engine SHALL write `lease: {machine, process, since}` to the state branch before its first attempt and clear it in the same push that carries the new state at a pause or exit; fetch the state branch before each push and refuse when it holds a newer `seq` or another machine's lease; and on a push rejected as not fast-forward keep its local state, push nothing, and tell the person to pull.

- GIVEN another machine pushed first WHEN this machine pushes THEN nothing is pushed and the person is told to pull

### CAR-B10 Checks before a pull imports

WHEN a pull would import THE engine SHALL refuse with exit 2 when `carry.json` does not parse or a file's digest does not match; refuse with the needed engine version when the checkpoint format or store layout is newer than this engine ([MIG](62-state-and-run-migration.spec.md)); refuse when the workflow is not registered here at the carried workflow version, or with `--force` apply MIG's change-under-a-thread rules; refuse when the work branch is not on the remote; and after the import, on the next resume, re-attach or recreate the worktree on the recorded branch under this machine's worktree root as after a deleted worktree ([WTR](82-worktree-mode.spec.md)), saying which branch to check out for a run in the checkout itself.

- GIVEN a carried thread whose work branch was never pushed WHEN `carry pull` runs THEN it is refused saying the branch is not on the remote

### CAR-B11 Failed deletion

WHEN the remote refuses the deletion at finish THE engine SHALL record it and show `carry: delete_failed` on the thread's status row and in `carry status`, and `attention` SHALL list the branch with the `carry drop` command.

- GIVEN a remote that refuses deletes WHEN a carried thread finishes THEN `carry status` shows `delete_failed`

## Acceptance criteria

- CAR-AC1 (CAR-B1, CAR-B3, CAR-B4, CAR-B5, CAR-B8, CAR-B9, CAR-B11): CAR-B1 to CAR-B4 and every case of CAR-B4 hold offline with two state roots and one bare remote repository
- CAR-AC2 (CAR-B2, CAR-B6, CAR-B7): No state commit holds a path outside `.tempergraph-carry/`, and none of the never-carried paths (fixture with every store file present)
- CAR-AC3 (CAR-B3): A finished carried thread leaves no ref under `refs/heads/tempergraph/state/` locally or on the remote
- CAR-AC4 (CAR-B10): Each import check refuses with its message on a fixture

## Open questions

- Should a workflow be able to default carrying on? Until answered: no, a person turns it on per run. Owner: owner.
- Not built yet: `attention` does not list a branch whose deletion the remote refused (the status row and `carry status` do). Owner: engine owner.
