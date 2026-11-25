# Triage: STANDIN-6

## Task

Source: the start request. Summary: the tool reports a missing config file instead of crashing, and says where.

## Acceptance criteria

1. Starting the tool with no config file prints one line that names the missing file
2. Starting the tool with no config file exits with a code the task leaves open

## Existing documents

- `README.md`: says the tool reads `tool.toml`, says nothing about a missing file

## Gaps

- G1 spec gap: the wording of the message. Searched `docs/` for "missing" and "message": nothing. Findable
- G2 decision needed: which exit code a missing file gives. Searched `docs/` for "exit code": nothing. Owner decision
- G3 decision needed: whether the message goes to standard output or standard error. Searched `docs/` for "stderr": nothing. Owner decision

## Owner decisions

- G2: Which exit code does the tool give when the config file is missing?
  - Options: a) 2; b) 1; c) 78
  - Default: a
  - If wrong: a script that tests for 1 sees another code
- G3: Does the message go to standard output or to standard error?
  - Options: a) standard error; b) standard output
  - Default: a
  - If wrong: a script that reads the message from standard output finds it empty

## Route

- Deliver: code
- Route: discovery
