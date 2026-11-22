# Config file

## Purpose

The tool reads its settings from `tool.toml` in the folder it is started in. People who start the tool depend on what it does when that file is missing. Exit codes follow CLI-B2.

## Behaviours

### CFG-B1 A missing config file is reported

WHEN the tool starts a run (any start other than `--version`) and `tool.toml` does not exist THE tool SHALL print exactly one line to standard error that names the missing file.

- GIVEN a folder with no `tool.toml` WHEN the tool starts THEN standard error holds exactly one line and it contains `tool.toml`
- GIVEN a folder with a `tool.toml` WHEN the tool starts THEN standard error is empty

### CFG-B2 A missing config file ends the run

WHEN `load_settings()` finds no file THE ConfigLoader SHALL raise `ConfigMissingError` to `main()`.

- GIVEN no file WHEN `load_settings()` is called THEN `ConfigMissingError` is raised

## Acceptance criteria

- CFG-AC1 (CFG-B1): Started in a folder with no `tool.toml`, the tool prints exactly one line to standard error and the line names `tool.toml`
- CFG-AC2 (CFG-B2): Started in a folder with no `tool.toml`, the tool exits with code 2
