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

- G1 spec gap: behaviour on a missing config file. Searched `docs/specs/` for "tool.toml", "config" and "missing": `cli.spec.md` covers options and exit codes only
- G2 research needed: which exit codes the tool already uses. Searched `docs/` for "exit code": `cli.spec.md` CLI-B2 says only "above 0"

## Route

- Deliver: code
- Route: discovery
