# Command line

## Purpose

How the tool is started and how a start ends. Scripts that call the tool depend on its options and exit codes.

## Behaviours

### CLI-B1 The version option answers without a config file

WHEN the tool is started with `--version` THE tool SHALL print its version and exit with code 0.

- GIVEN a folder with no `tool.toml` WHEN the tool is started with `--version` THEN the version is printed and the exit code is 0

### CLI-B2 A failed start ends with code 1

WHEN a start fails for any reason THE tool SHALL exit with code 1.

- GIVEN a start that fails WHEN the tool ends THEN the exit code is 1

## Acceptance criteria

- CLI-AC1 (CLI-B1): `--version` prints the version and exits with code 0 in a folder with no `tool.toml`
- CLI-AC2 (CLI-B2): A failed start always exits with code 1
