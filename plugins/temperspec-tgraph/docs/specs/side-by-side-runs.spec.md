# Runs side by side

## Purpose

Two runs of the workflow can work on one repository at once, each on its own branch, and both can edit the same spec. A run that edits a spec after the base branch has changed it would, once merged, overwrite or duplicate what the other run wrote. The outcome check guards against this: for each spec the run edited it compares the spec at the run's base commit with the spec at the head of the base branch now. The owner who merges the pull requests and every run that starts from the same base branch depend on it. The check reads the head of the base branch from the context the engine gives every check (CHK-B22). Part of the [overview](00-overview.spec.md), where the criterion is `ts-spec-fresh`.

## Behaviours

### SBS-B1 A spec the base branch has changed fails the check

WHEN the base branch's head holds commits that the run's base commit lacks and a spec the run edited reads differently at that head than at the run's base commit (its text differs, or it exists at one and not at the other) THE outcome check SHALL fail `ts-spec-fresh`, naming that spec.

- GIVEN a spec the run edited and a commit on the base branch, made after the run started, that changed the same spec WHEN the outcome check runs THEN it fails `ts-spec-fresh` and its finding names that spec's path
- GIVEN two specs edited by the run and a base branch that has changed only one of them since the run started WHEN the outcome check runs THEN only that spec is named
- GIVEN a spec the run created at a path where the base branch has since added a spec WHEN the outcome check runs THEN it fails naming that path
- GIVEN a spec the run edited that the base branch has since deleted WHEN the outcome check runs THEN it fails naming that path

### SBS-B2 A spec the base branch has not changed passes

WHEN a spec the run edited reads the same at the base branch's head as at the run's base commit, or the base branch's head holds no commit that the run's base commit lacks, THE outcome check SHALL pass `ts-spec-fresh` for that spec.

- GIVEN a spec the run edited and a base branch that has not moved since the run started WHEN the outcome check runs THEN `ts-spec-fresh` passes
- GIVEN a base branch that has gained commits changing other files only WHEN the outcome check runs THEN `ts-spec-fresh` passes for the spec
- GIVEN a base branch whose head is behind the run's base commit and holds an older text of the spec WHEN the outcome check runs THEN `ts-spec-fresh` passes for the spec
- GIVEN a base branch that changed the spec and later restored its text WHEN the outcome check runs THEN `ts-spec-fresh` passes for the spec

### SBS-B3 Nothing to compare is not applicable

WHEN the run has no base branch to compare with, or has edited no spec, THE outcome check SHALL report `ts-spec-fresh` as not applicable and say which of the two it is.

- GIVEN a run in place, which has no base branch WHEN the outcome check runs THEN `ts-spec-fresh` is reported not applicable, saying the run has no base branch, and fails nothing
- GIVEN a run that edited no spec WHEN the outcome check runs THEN `ts-spec-fresh` is reported not applicable, saying the run edited no spec

## Acceptance criteria

- SBS-AC1 (SBS-B1): In a scratch git repository where the run's base commit is a commit of `main`, the run edits `docs/specs/a.spec.md`, and `main` then gains a commit that changes that spec, the outcome check fails `ts-spec-fresh` and its finding names `docs/specs/a.spec.md`
- SBS-AC2 (SBS-B1): With two specs edited and only one changed on `main`, only that spec is named; a spec the run created at a path where `main` has since added one, and a spec `main` has since deleted, are each named
- SBS-AC3 (SBS-B2): `ts-spec-fresh` passes for an edited spec when `main` has not moved, when `main` has gained commits that changed other files only, when the head of `main` is behind the run's base commit, and when `main` changed the spec and restored it
- SBS-AC4 (SBS-B3): A run with no base branch and a run that edited no spec are each reported not applicable with their reason, and neither fails the outcome check
