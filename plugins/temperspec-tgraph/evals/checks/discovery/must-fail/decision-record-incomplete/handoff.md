# Hand-off: STANDIN-1

## Problem

The tool crashes with a stack trace when `tool.toml` is missing. The task asks for one line and exit code 2, and leaves open where the message goes.

## Gaps closed

- G1: `docs/adr/config-errors-go-to-standard-error.adr.md`

## Changed documents

- `docs/adr/config-errors-go-to-standard-error.adr.md`: new

## Decisions

- The message goes to standard error

## Open questions

- None

## Reading list

- `docs/adr/config-errors-go-to-standard-error.adr.md` (Decision): where the plan sends the message
