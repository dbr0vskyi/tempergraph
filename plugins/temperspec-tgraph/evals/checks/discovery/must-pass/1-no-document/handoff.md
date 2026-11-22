# Hand-off: STANDIN-1

## Problem

The tool crashes with a stack trace when `tool.toml` is missing. The task asks for one line and exit code 2.

## Gaps closed

- G1: no document needed. The README states that every error message goes to standard error

## Changed documents

- None

## Decisions

- The message goes to standard error, as the README already says for every error message

## Open questions

- None

## Reading list

- `docs/specs/config-file.spec.md` (CFG-B1, CFG-B2): the behaviours the plan checks the message and the exit code against
