# Command line

## Purpose

How the tool is started. People and scripts that start the tool depend on its options and on what it prints.

## Behaviours

### CLI-B1 The version option prints the version

WHEN the tool is started with `--version` THE tool SHALL print its version and exit with code 0.

- GIVEN any folder WHEN the tool is started with `--version` THEN the version is printed and the exit code is 0

### CLI-B2 A start reports how many settings it read

WHEN the tool is started in a folder with a `tool.toml` THE tool SHALL print the number of settings it read.

- GIVEN a `tool.toml` with two settings WHEN the tool is started THEN it prints `running with 2 settings`

## Acceptance criteria

- CLI-AC1 (CLI-B1): `--version` prints the version and exits with code 0
- CLI-AC2 (CLI-B2): Started with a `tool.toml` of two settings, the tool prints `running with 2 settings`
