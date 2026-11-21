# Hand-off: STANDIN-1

## Problem

The tool crashes with a stack trace when `tool.toml` is missing. The task asks for one line and exit code 2.

## Gaps closed

- G1: `docs/specs/config-file.md` (CFG-B1, CFG-B2)

## Changed documents

- `docs/specs/config-file.md`: new

## Decisions

- The message goes to standard error, as the README already says for every error message

## Open questions

- None
