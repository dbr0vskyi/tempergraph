# Which exit codes does the tool already use?

## Problem statement

The task asks for exit code 2 on a missing config file (gap G2). A code that already means something else would mislead scripts.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Entry point | code | `src/tool/main.py` |
| Command line spec | spec | `docs/specs/cli.spec.md` |

## Key findings

### F1 The entry point returns 0 or 1 only `confirmed`

`src/tool/main.py` returns 0 after a run and 1 from its one error branch. No other code is returned anywhere under `src/tool/`.

### F2 The spec asks only for a code above zero on failure `confirmed`

CLI-B2 states that a failed start exits with a code above 0.

## Conclusions

1. Exit code 2 is free and agrees with CLI-B2.

## Open questions

- None
