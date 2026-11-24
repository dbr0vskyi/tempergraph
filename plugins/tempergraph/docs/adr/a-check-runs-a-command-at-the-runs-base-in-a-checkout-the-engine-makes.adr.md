# A check runs a command at the run's base in a checkout the engine makes

## Context

A gate that retries a failure which was there before the change spends money that no code change can win back. One run retried its code gate four times, about 2 USD, on an environment fault, and another met 590 errors from its container's signing fault ([R-160](../research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md) F1 and H1; issue 54). A workflow's check could not tell a failure the change made from one already there: it ran each verification command once, on the workspace, and failed on any non-zero exit.

To tell the two apart a check needs the same command's result on the run's base commit, and the engine gives it no way to get one. A command runs in `cwd` or `workdir` only (CHK-B12), and the reuse key is made of the workspace's head, status and changed files (CHK-B13). `git.base` names the commit ([WTR-B21](../specs/82-worktree-mode.spec.md)), but only a worktree run records one: an in-place run's workspace record carries no base commit (`workspace.py`, `prepare_workspace`).

What the code says, and so bounds the choice:

- The engine starts a process only at the sanctioned sites, among them the git reader and the workflow command runner ([SEC-B7](../specs/14-security.spec.md); `security/launch.py`, `SANCTIONED_SITES`). The source scan reads the engine's source only (`tests/test_source_rules.py`, `test_launch_sites_sanctioned`). A workflow package's own script can call `subprocess` and is not scanned, but a call made that way has none of the safeguards of CHK-B12: no credentials removed, no process tree ended at a limit, no output file, no record in `runs[]`, no reuse.
- The engine never removes a worktree with `--force` ([WTR-B23](../specs/82-worktree-mode.spec.md)), and git refuses to remove a worktree that holds untracked files, which any command run in it leaves (caches, build output).
- The main checkout is read-only to a check, may hold uncommitted changes ([WTR-B6](../specs/82-worktree-mode.spec.md)) and can move on while a run goes on, so it is not the base.
- A Python package installed in editable mode loads the tree it was installed from, and the engine's own `pyproject.toml` sets no `pythonpath` for its tests (`[tool.pytest.ini_options]`), so a command run in another folder can still exercise the workspace's code.

[ADR-0075](0075-checks-get-a-context-and-an-engine-command-runner.adr.md) already splits the work: the engine owns the mechanics of a command run, the workflow owns what its result means. [ADR-0129](0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md) asks that a request from a workflow lands as a capability any workflow can use. "Did this command already fail before the change?" is such a question; it needs no workflow's name.

## Decision

We will let a check run a command at the run's base commit through the engine's own command runner: `run(cmd, at_base=True)` runs the command as it resolves for the workspace, in a clean checkout of the base commit that the engine makes outside the workspace, with the launch, limit, output and record of any other run, marked `at_base`. The engine reuses the result for the rest of the visit (CHK-B20), starts nothing when the run has no base commit or the folder is not in it (CHK-B19), and removes the checkout when the check ends, leaving nothing in the repository (CHK-B21). What a base result means stays with the workflow: the engine hands the check the run, and a check that finds the same failure there returns its result marked `environmental` (CHK-B14).

The checkout is a throwaway clone that shares the repository's objects and is detached at the base commit, made through the git reader on the first run that has to start. It has a `.git`, so a command that reads git state finds a repository, and it is a folder to delete, not a worktree the repository has to forget.

## Options considered

### A. The engine runs the command at the base (chosen)

For: one launch site with the safeguards of CHK-B12, one reuse store, one record that the judge, the pause and the run detail document already read; any workflow can use it; a check stays a function of its context. Against: the engine grows a checkout routine and a second kind of side effect for a check; a failing command costs a second run.

### B. The workflow's check launches git and the command itself

For: no engine change. Against: a second launcher beside CHK-B12 with none of its limits or records; the engine's reuse cannot see it, so the once-per-visit rule would be the workflow's own bookkeeping; a check that writes outside its workspace is no longer one the engine can bound.

### C. A git worktree registered in the repository at the base

For: the simplest git. Against: the repository then lists a worktree the engine does not own, which `worktree list --all` shows ([WTR-B27](../specs/82-worktree-mode.spec.md)); removing it needs `--force`, which no engine path may call; a worker ended at its limit leaves a stale entry behind.

### D. Judge a failure by its output alone, with no base run

For: no second run. Against: the output cannot say whether the failure was there before the change, which is the question; a failure from an environment fault names no more files than one from a regression.

### E. Run the command in the main checkout

For: nothing to make. Against: it may be dirty or on another commit than the base, and a check treats it as read-only.

## Consequences

- A workflow's check can ask whether a failure predates the change, with the limit, scrubbing, process-tree kill, reuse and evidence every run already has.
- A check's side effects are now two: a command run in the workspace, and one at the base in a folder the engine makes and removes. The Purpose of the check contract says so.
- A base run costs a run of the command, only for a command the check chose to run there; with the reuse of CHK-B20 it costs one per command per visit. It shares the check's limit (CHK-B16, 1800 s unless the gate sets another), so a base run that cannot start or finish is not a result and the workflow falls back to what it did before.
- Risk: a base run is as faithful as the environment allows. A package installed in editable mode loads the workspace's code, so a command at the base can fail for a reason the base commit does not have. The engine does not hide this; it is listed as an open question of the check contract, and the workflow's comparison must not treat a base failure as proof alone (the workflow's own record says how).
- Risk: a result reused for the visit can be stale after a person repairs the environment and resumes in the same visit. A trip back or a new visit runs the command again.
- Risk: a failed checkout makes a run `not_started`, never an error, so the check degrades to its old behaviour.

## Revisit when

A workflow reports a run at the base that passed where the base commit really fails, or checks end at their limit because of base runs.
