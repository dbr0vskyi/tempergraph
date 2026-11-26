# Triage: STANDIN-1

## Task

Source: the start request. Summary: the tool reports a missing config file instead of crashing.

## Acceptance criteria

1. Starting the tool with no config file prints one line that names the missing file
2. Starting the tool with no config file exits with code 2

## Intent

- Goal: the tool reports a missing config file instead of crashing
- In scope: the change the acceptance criteria describe
- Out of scope: any behaviour the criteria do not name
- Assumptions: None

## Existing documents

- `README.md`: says the tool reads `tool.toml`, says nothing about a missing file

## Uncertainties

- U1 limits: how long may the message be? Shapes the wording

## Gaps

- G1 decision needed: whether the message goes to standard output or standard error. Searched `docs/` for "stderr" and "standard error": nothing. Owner decision

## Owner decisions

- G1: Does the missing-file message go to standard output or to standard error?
  - Options: a) standard error; b) standard output
  - Default: a
  - If wrong: a script that reads the tool's standard output sees no message

## Route

- Deliver: code
- Route: discovery
