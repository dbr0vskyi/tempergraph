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

- U1 existing behaviour: does the tool read the file before it parses its flags? Shapes where the message is printed. Route: code

## Gaps

None

## Route

- Deliver: code
- Route: discovery
