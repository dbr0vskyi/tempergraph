# Triage: TASK-7

## Task

Source: the start request. Summary: report a missing config file with one line and exit code 2 instead of a stack trace.

## Acceptance criteria

1. Starting the tool with no config file prints one line to standard error that names the missing file
2. Starting the tool with no config file exits with code 2

## Intent

- Goal: report a missing config file with one line and exit code 2 instead of a stack trace
- In scope: the change the acceptance criteria describe
- Out of scope: any behaviour the criteria do not name
- Assumptions: None

## Existing documents

- `docs/specs/cli.spec.md`: options and exit codes (CLI-B1, CLI-B2); nothing on the config file
- `README.md`: names `tool.toml`, says nothing about a missing file

## Uncertainties

None

## Gaps

None

## Route

- Deliver: code
- Route: plan
