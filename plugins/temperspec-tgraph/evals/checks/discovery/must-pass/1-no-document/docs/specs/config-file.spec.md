# Config file

## 1. Overview

The tool reads its settings from `tool.toml` in the folder it is started in. This spec is in the earlier layout, which a run leaves as it is when it edits nothing in it.

## 2. Contract

### CFG-B1 A missing config file is reported

WHEN the tool starts and `tool.toml` does not exist THE tool SHALL print one line to standard error that names the missing file.

### CFG-B2 A missing config file ends the run

WHEN the tool starts and `tool.toml` does not exist THE tool SHALL exit with code 2.

## 6. Acceptance criteria

- [ ] cfg-message The tool prints exactly one line to standard error that names `tool.toml`
- [ ] cfg-exit The tool exits with code 2
