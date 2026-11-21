# tool

## Purpose

A small command line tool that reads its settings from `tool.toml` and runs with them. Its one component is the command line: `docs/specs/cli.spec.md`.

## Behaviours

### SYS-B1 The tool runs from the folder it is started in

WHEN the tool is started THE tool SHALL read `tool.toml` from the folder it was started in.

- GIVEN two folders with different `tool.toml` files WHEN the tool is started in each THEN each start uses the file of its own folder

## Acceptance criteria

- SYS-AC1 (SYS-B1): The tool started in a folder uses that folder's `tool.toml`
