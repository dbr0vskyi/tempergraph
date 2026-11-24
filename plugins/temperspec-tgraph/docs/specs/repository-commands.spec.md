# Verification commands from the repository

## Purpose

Which commands a run may use to verify its work: the commands a plan lists under Verification, the commands after `Verify:` in a quick-lane triage note, the commands the code gate and the outcome check run, and the commands the code step's session may run in its shell. They come from the repository and not from a list fixed in the workflow, so a repository of any language can use the workflow. A repository declares them in `tempergraph.commands.json` at its root, the file the engine reads for a step or check that asks for the repository's commands ([CHK-B11](../../../tempergraph/docs/specs/75-check-contract-and-command-runs.spec.md)). Read-only `git` (`git --version`, `git status`, `git diff`, `git log` and `git show`) is allowed in every repository, whatever the file says. For a Python repository that has no such file, prepare writes one that declares the Python commands the workflow allowed before it read the file, so a Python repository keeps the commands it had. The owners of repositories that are not Python, who declare their own commands, and the owners of Python repositories, whose runs keep their commands, depend on it. A file inside a folder of copies or fixtures does not count as the repository's own, as in the [project note](project-note.spec.md). Part of the [overview](00-overview.spec.md), where `ts-verify` is the criterion about verification commands; the units it touches are [prepare](01-prepare.spec.md), [triage](04-triage.spec.md), [plan](06-plan.spec.md), [expand](07-expand.spec.md) and [code](08-code.spec.md).

## Behaviours

### RCM-B1 A command the repository declares is accepted

WHEN a verification command starts with a command that the repository declares in `tempergraph.commands.json` THE checks that read verification commands (the triage, plan, expand, code and outcome checks) SHALL accept it.

- GIVEN a repository with a `package.json`, no Python project file and a `tempergraph.commands.json` that declares `npm test` and `npm run lint` WHEN a plan lists `npm test -- --run` THEN the plan check reports no refusal for it
- GIVEN that repository WHEN a plan lists `cd web && npm run lint` THEN the plan check reports no refusal for it
- GIVEN that repository WHEN the expand check reads a plan that lists `npm test` THEN it reports no refusal for the command
- GIVEN that repository WHEN the triage check reads a quick-lane note whose `Verify` line is `npm test` THEN it reports no refusal for the command

### RCM-B2 A command no declaration covers is refused

WHEN a verification command neither starts with a command that the repository declares nor is a read-only git command THE checks that read verification commands (the triage, plan, expand, code and outcome checks) SHALL refuse it with a finding that names `tempergraph.commands.json`.

- GIVEN a repository with a `package.json`, no Python project file and a `tempergraph.commands.json` that declares `npm test` WHEN a plan lists `pytest` THEN the plan check fails for `pytest` with a finding that names `tempergraph.commands.json`
- GIVEN a repository with no `tempergraph.commands.json` WHEN a plan lists `make test` THEN the plan check fails for `make test` with a finding that names `tempergraph.commands.json`
- GIVEN a repository whose `tempergraph.commands.json` is not valid JSON WHEN a plan lists `make test` THEN the plan check fails for it with a finding that names `tempergraph.commands.json`
- GIVEN the repository of the first scenario WHEN the expand check reads a plan that lists `pytest` THEN it fails for `pytest` with a finding that names `tempergraph.commands.json`
- GIVEN the repository of the first scenario WHEN the triage check reads a quick-lane note whose `Verify` line is `pytest` THEN it fails with a finding that names `tempergraph.commands.json`
- GIVEN the repository of the first scenario WHEN the code gate runs a plan that lists `pytest` THEN it fails for `pytest` with a finding that names `tempergraph.commands.json`

### RCM-B3 Read-only git is accepted in every repository

WHEN a verification command is `git --version`, `git status`, `git diff`, `git log` or `git show`, with or without arguments, THE checks that read verification commands (the triage, plan, expand, code and outcome checks) SHALL accept it whether or not the repository declares it.

- GIVEN a repository with no `tempergraph.commands.json` WHEN a plan lists `git status` and `git diff --stat` THEN the plan check reports no refusal for either
- GIVEN a repository whose `tempergraph.commands.json` declares only `npm test` WHEN a plan lists `git log -1` THEN the plan check reports no refusal for it
- GIVEN a repository with no `tempergraph.commands.json` WHEN the code gate runs a plan that lists `git --version` THEN it runs the command and passes `ts-code-verify`

### RCM-B4 The gates that run commands run a declared command

WHEN the code gate or the outcome check runs a plan's verification commands THE gate SHALL run each command that starts with a command the repository declares, in the folder a leading `cd <folder> &&` names.

- GIVEN a repository with no Python project file whose `tempergraph.commands.json` declares `sh check.sh`, a plan that lists `sh check.sh` and a `check.sh` that exits 0 WHEN the code gate runs THEN `ts-code-verify` passes and its evidence names the command as run
- GIVEN the same repository and a `check.sh` that exits 1 WHEN the code gate runs THEN `ts-code-verify` fails and its finding names `sh check.sh` and exit code 1
- GIVEN a repository whose `tempergraph.commands.json` declares `sh check.sh`, a plan that lists `cd tools && sh check.sh` and a `tools/check.sh` that exits 0 only if its working folder is `tools` WHEN the code gate runs THEN `ts-code-verify` passes
- GIVEN the repository of the first scenario WHEN the outcome check runs THEN `ts-verify` passes

### RCM-B5 The code step's session may run the declared commands

WHEN the code step starts THE code step SHALL let its session run the read-only git commands and the commands the repository declares in `tempergraph.commands.json`.

- GIVEN a repository with a `package.json` whose `tempergraph.commands.json` declares `npm test` and `npm run lint` WHEN the code step starts THEN its session may run `npm test`, `npm run lint` and the read-only git commands, and may not run `pytest`
- GIVEN a repository with no `tempergraph.commands.json` WHEN the code step starts THEN its session may run the read-only git commands and no other verification command
- GIVEN a Python repository whose `tempergraph.commands.json` prepare wrote WHEN the code step starts THEN its session may run `pytest`, `python -m pytest`, `python3 -m pytest`, `ruff check`, `ruff format --check`, `mypy` and the read-only git commands

### RCM-B6 Prepare writes the file for a Python repository

WHEN prepare runs in a repository that holds a Python project file (a file named `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt` or `Pipfile`, in the repository root or in a folder that is not a folder of copies or fixtures) and has no `tempergraph.commands.json` at its root THE prepare step SHALL add that file to the run's branch, declaring as `schema_version` 1 and a `commands` list `pytest`, `python -m pytest`, `python3 -m pytest`, `ruff check`, `ruff format --check` and `mypy`.

- GIVEN a repository whose root holds `pyproject.toml` and no `tempergraph.commands.json` WHEN prepare runs THEN the run's branch holds `tempergraph.commands.json` at the repository root with `schema_version` 1 and the `commands` `pytest`, `python -m pytest`, `python3 -m pytest`, `ruff check`, `ruff format --check` and `mypy`, in that order
- GIVEN a repository whose only Python project file is `plugins/a/engine/pyproject.toml` WHEN prepare runs THEN the file is written at the repository root and not in `plugins/a/engine/`
- GIVEN a repository whose only Python project file is a `requirements.txt` in its root WHEN prepare runs THEN the file is written at the repository root
- GIVEN the file prepare wrote WHEN a plan lists `python3 -m pytest tests -q`, `ruff format --check src` and `mypy` THEN the plan check reports no refusal for them
- GIVEN two Python repositories WHEN prepare writes the file in each THEN the two files are byte for byte the same

### RCM-B7 Prepare leaves an existing file as it is

WHEN a repository already has `tempergraph.commands.json` at its root THE prepare step SHALL leave it unchanged.

- GIVEN a Python repository whose `tempergraph.commands.json` declares only `make check` WHEN prepare runs THEN the file is byte for byte as it was and no change to it is committed
- GIVEN a repository with a `pyproject.toml` whose `tempergraph.commands.json` is not valid JSON WHEN prepare runs THEN the file is byte for byte as it was
- GIVEN a repository that is not Python whose `tempergraph.commands.json` declares `npm test` WHEN prepare runs THEN the file is byte for byte as it was

### RCM-B8 Prepare writes no file for a repository that is not Python

WHEN a repository holds no Python project file outside the folders of copies and fixtures and has no `tempergraph.commands.json` at its root THE prepare step SHALL write none.

- GIVEN a repository with only a `package.json` WHEN prepare runs THEN the repository has no `tempergraph.commands.json`
- GIVEN a repository whose only `pyproject.toml` is in `evals/case/` WHEN prepare runs THEN the repository has no `tempergraph.commands.json`
- GIVEN a repository whose only `setup.py` is in `node_modules/pkg/` WHEN prepare runs THEN the repository has no `tempergraph.commands.json`

### RCM-B9 A file prepare wrote is not a change of the run

WHEN prepare wrote `tempergraph.commands.json` and the file still holds what prepare wrote THE code gate SHALL list the file as written by prepare and not among the changes of the run.

- GIVEN a quick-lane run in a Python repository whose `tempergraph.commands.json` prepare wrote, a triage note that names `src/a.py` and `tests/test_a.py`, and a change of those two files only WHEN the code gate runs THEN `ts-code-lane` passes
- GIVEN a run whose prepare wrote the file WHEN the code gate runs THEN its evidence lists `tempergraph.commands.json` as written by prepare and not among the changed paths or the changed source files
- GIVEN a run whose prepare wrote the file and a step that then added a command to it WHEN the code gate runs THEN the file is among the changed paths, and in the quick lane `ts-code-lane` fails naming it

## Acceptance criteria

- RCM-AC1 (RCM-B1): For a repository with a `package.json`, no Python project file and a `tempergraph.commands.json` that declares `npm test` and `npm run lint`, the plan check reports no refusal for a plan that lists `npm test -- --run` and `cd web && npm run lint`, the expand check none for a plan that lists `npm test`, and the triage check none for a quick-lane note whose `Verify` line is `npm test`
- RCM-AC2 (RCM-B2): For the same repository a plan that lists `pytest` fails the plan check, the expand check and the code gate, and a quick-lane note whose `Verify` line is `pytest` fails the triage check, each with a finding that names `tempergraph.commands.json`; a plan that lists `make test` fails the plan check the same way for a repository with no such file and for one whose file is not valid JSON
- RCM-AC3 (RCM-B3): `git status`, `git diff --stat` and `git log -1` give no refusal in the plan check for a repository with no `tempergraph.commands.json` and for one whose file declares only `npm test`, and the code gate runs `git --version` and passes `ts-code-verify` for a repository with no such file
- RCM-AC4 (RCM-B4): For a repository with no Python project file whose `tempergraph.commands.json` declares `sh check.sh`, the code gate passes `ts-code-verify` for a plan that lists `sh check.sh` when the script exits 0 and fails it, naming `sh check.sh` and exit code 1, when the script exits 1; it runs `cd tools && sh check.sh` in the folder `tools`; and the outcome check passes `ts-verify` for the passing script
- RCM-AC5 (RCM-B5): The commands the code step lets its session run are `npm test`, `npm run lint` and the read-only git commands, and not `pytest`, for a repository whose file declares `npm test` and `npm run lint`; the read-only git commands alone for a repository with no such file; and `pytest`, `python -m pytest`, `python3 -m pytest`, `ruff check`, `ruff format --check`, `mypy` and the read-only git commands for a Python repository whose file prepare wrote
- RCM-AC6 (RCM-B6): For a repository whose root holds `pyproject.toml`, for one whose only Python project file is `plugins/a/engine/pyproject.toml` and for one whose only one is a root `requirements.txt`, prepare adds `tempergraph.commands.json` at the repository root to the run's branch with `schema_version` 1 and the `commands` `pytest`, `python -m pytest`, `python3 -m pytest`, `ruff check`, `ruff format --check` and `mypy` in that order; the files of two such repositories are byte for byte the same, and the plan check reports no refusal for `python3 -m pytest tests -q`, `ruff format --check src` and `mypy` in each
- RCM-AC7 (RCM-B7): For a Python repository whose file declares only `make check`, for a repository with a `pyproject.toml` whose file is not valid JSON, and for a repository that is not Python whose file declares `npm test`, prepare leaves `tempergraph.commands.json` byte for byte as it was and commits no change to it
- RCM-AC8 (RCM-B8): For a repository with only a `package.json`, for one whose only `pyproject.toml` is in `evals/case/`, and for one whose only `setup.py` is in `node_modules/pkg/`, prepare writes no `tempergraph.commands.json`
- RCM-AC9 (RCM-B9): For a run whose prepare wrote the file, the code gate lists `tempergraph.commands.json` as written by prepare and not among the changed paths or the changed source files, and in the quick lane `ts-code-lane` passes for a change of only the files the triage note names; after a step edits the file, it is among the changed paths and `ts-code-lane` fails naming it
