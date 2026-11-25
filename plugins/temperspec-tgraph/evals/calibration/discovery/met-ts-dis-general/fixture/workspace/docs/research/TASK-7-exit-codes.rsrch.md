# Which exit codes does the tool already use?

## Problem statement

The task asks for exit code 2 on a missing config file (gap G2). A code that already means something else would mislead scripts.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Entry point | code | `src/tool/main.py` |
| Command line spec | spec | `docs/specs/cli.spec.md` |

## Key findings

### F1 The entry point returns 0 only, and a crash exits with 1 `confirmed`

When this note was written, `src/tool/main.py` returned 0 from both of its branches and had no error branch. A missing `tool.toml` raised an uncaught exception, which Python turns into exit code 1. No other code was returned anywhere under `src/tool/`.

### F2 The spec asks only for a code above zero on failure `confirmed`

CLI-B2 states that a failed start exits with a code above 0.

## Conclusions

1. Exit code 2 is free and agrees with CLI-B2.

## Open questions

- None
