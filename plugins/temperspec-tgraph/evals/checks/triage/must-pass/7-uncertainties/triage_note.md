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
- Assumptions:
  - A1: the config file is looked for in the working folder only. If wrong: the message names the wrong path

## Existing documents

- `README.md`: says the tool reads `tool.toml`, says nothing about a missing file

## Uncertainties

- U1 existing behaviour: does the tool read the file before it parses its flags? Shapes where the message is printed. Route: code
- U2 names: which exit code do other tools of the suite use for a missing file? Blocks the criterion on the exit code. Route: owner
- U3 failures: what is printed when the file exists and cannot be read? Detail of the message. Route: plan

## Gaps

- G1 decision needed: whether the message goes to standard output or standard error. Searched `docs/` for "stderr" and "standard error": nothing. Owner decision

## Owner decisions

- G1: Does the missing-file message go to standard output or to standard error?
  - Options: a) standard error; b) standard output
  - Default: a
  - If wrong: a script that reads the tool's standard output sees no message

- U2: Which exit code marks a missing file?
  - Options: a) 2; b) 78
  - Default: a
  - If wrong: scripts that test for the other code miss the failure

## Route

- Deliver: code
- Route: discovery
