# Configuration errors go to standard error

## Context

A missing `tool.toml` must end the run with one line and exit code 2. Where that line goes is not stated.

## Current state

Errors usually go to standard error.

## Forces

- C1 (constraint): standard output stays machine-readable
- F1: a person at a terminal sees the line

## Decision

We will write the line to standard error.

## Options considered

### Standard error

For: keeps standard output clean.

### Standard output

Against: breaks C1.

## Decision rationale

Standard error keeps standard output clean.

## Consequences

Scripts that read standard output see nothing from a failed run.

## Risks

- A wrapper that merges the two streams shows the line in its output.

## Revisit when

If needs change.
