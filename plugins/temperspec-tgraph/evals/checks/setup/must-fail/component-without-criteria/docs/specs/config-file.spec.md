# Config file

## Purpose

The tool reads its settings from `tool.toml` in the folder it is started in. People who start the tool depend on what it does when that file is missing.

## Behaviours

### CFG-B1 A missing config file is reported

WHEN the tool starts and `tool.toml` does not exist THE tool SHALL print one line to standard error that names the missing file.

- GIVEN a folder with no `tool.toml` WHEN the tool starts THEN standard error holds one line that contains `tool.toml`
- GIVEN a folder with a `tool.toml` WHEN the tool starts THEN standard error is empty

### CFG-B2 A missing config file ends the run

WHEN the tool starts and `tool.toml` does not exist THE tool SHALL exit with code 2.

- GIVEN a folder with no `tool.toml` WHEN the tool starts THEN the exit code is 2

