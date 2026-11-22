# Triage: TASK-7

## Task

Source: the start request. Summary: report a missing config file with one line and exit code 2 instead of a stack trace.

## Acceptance criteria

1. Starting the tool with no config file prints one line to standard error that names the missing file
2. Starting the tool with no config file exits with code 2

## Existing documents

- `docs/specs/config-file.spec.md`: what the tool does when `tool.toml` is missing (CFG-B1, CFG-B2)
- `docs/specs/cli.spec.md`: options and exit codes (CLI-B1, CLI-B2)

## Gaps

- G1 spec update: the message for a missing config file. `docs/specs/config-file.spec.md` states it. Covered by CFG-B1 and CFG-AC1
- G2 spec update: the exit code for a missing config file. `docs/specs/config-file.spec.md` states it. Covered by CFG-B2 and CFG-AC2

## Route

- Deliver: code
- Route: discovery
