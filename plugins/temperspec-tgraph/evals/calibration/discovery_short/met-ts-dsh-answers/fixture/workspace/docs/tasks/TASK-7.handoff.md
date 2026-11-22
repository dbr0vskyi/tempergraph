# Hand-off: TASK-7

## Problem

Starting the tool with no `tool.toml` crashes with a stack trace. The task asks for one line that names the file and exit code 2.

## Gaps closed

- G1: CFG-B1 answers it. It prints exactly one line to standard error that names `tool.toml`, which is criterion 1
- G2: CFG-B2 answers it. The run ends with exit code 2 when `tool.toml` is missing, which is criterion 2

## Changed documents

- None

## Decisions

- None

## Open questions

- None

## Reading list

- `docs/specs/config-file.spec.md` (CFG-B1, CFG-B2, CFG-AC1, CFG-AC2): the behaviours the plan implements and the criteria its tests carry
- `docs/specs/cli.spec.md` (CLI-B2): the exit codes the new code must agree with
