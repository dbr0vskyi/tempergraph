# Configuration errors go to standard error

## Context

A missing `tool.toml` must end the run with one line and exit code 2. Where that line goes is not stated.

## Current state

The `README.md` says every error message goes to standard error. The loader in `src/tool/config.py` raises `FileNotFoundError` and nothing catches it.

## Forces

- C1 (constraint): standard output stays machine-readable. Source: `README.md`, section Output
- F1: a person at a terminal sees the line
- F2: one place handles every error

## Options considered

### Standard error

How it works: the entry point catches the error and writes the line to standard error before it exits with 2.
For: keeps standard output clean (C1) and is seen at a terminal (F1). Against: none found.

### Standard output

How it works: the entry point prints the line with the normal output.
Against: breaks C1.

## Decision

We will write the line to standard error.

## Decision rationale

Standard error meets C1 and F1. F2 is met too: the same entry point catches every error.

## Consequences

Scripts that read standard output see nothing from a failed run.

## Risks

- A wrapper that merges the two streams shows the line in its output. Limited by: the exit code still says the run failed. Noticed by: a wrapper's own tests.

## Assumptions

- A1: no caller parses standard error. Check: search the callers in `scripts/`. If wrong: a caller must change its parsing.

## Revisit when

The tool gains an output format whose errors are written as records on standard output.
