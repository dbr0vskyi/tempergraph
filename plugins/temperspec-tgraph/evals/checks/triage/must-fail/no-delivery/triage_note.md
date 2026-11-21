# Triage: STANDIN-1

## Task

Source: the start request. Summary: the tool reports a missing config file instead of crashing.

## Acceptance criteria

1. Starting the tool with no config file prints one line that names the missing file
2. Starting the tool with no config file exits with code 2

## Existing documents

- `README.md`: says the tool reads `tool.toml`, says nothing about a missing file

## Gaps

- G1 decision needed: whether the message goes to standard output or standard error. Searched `docs/` for "stderr" and "standard error": nothing

## Route

- Route: discovery
