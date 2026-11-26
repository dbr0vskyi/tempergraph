# Triage: STANDIN-1

## Task

Source: the start request. Summary: the tool reports a missing config file instead of crashing.

## Acceptance criteria

1. Starting the tool with no config file prints one line that names the missing file

## Intent

- Goal: the tool reports a missing config file instead of crashing
- In scope: the change the acceptance criteria describe
- Out of scope: any behaviour the criteria do not name
- Assumptions: None

## Existing documents

- `docs/specs/config-file.spec.md`: states what the tool does when `tool.toml` is missing

## Uncertainties

None

## Gaps

- G1 spec update: the message for a missing config file. `docs/specs/config-file.spec.md` states it. Covered by CFG-B1 and CFG-AC1

## Route

- Deliver: code
- Route: discovery
