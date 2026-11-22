# ADR-0128 Windows is supported natively, with job objects, and judges wait for live probes

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | ADR-0090 assumption S3 (macOS and Linux only) from release 2 |

## Context


## Decision

We will support native Windows in release 2 by the rules of [WIN](../specs/97-windows-support.spec.md): job objects with kill-on-close for every session, owner-only ACLs, replace retries, locked appends, a `.cmd` shim, CRLF-normalized comparisons, long-path checks and a PowerShell speed probe. WSL counts as Linux. Preflight refuses judge sessions on Windows until probes P-WIN-1 to P-WIN-3 pass on the pinned CLI.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| WSL only | Nothing to build | Windows users must move their repositories into WSL |
| **Native, judges gated by probes (chosen)** | Works where Claude Code works; no unproven isolation | Needs a Windows machine for the probes |
| Native, judges trusted without probes | Usable at once | Judge isolation unproven, against C15 |

## Decision rationale

| Criterion | WSL only | Chosen | No probes |
|---|---|---|---|
| Runs where Claude Code runs natively | no | yes | yes |
| Judge isolation proven before use (C15) | yes | yes | no |

## Consequences

- Positive: Windows teams can use the engine as they use Claude Code.
- Negative: gated workflows wait for the probes on Windows.
- Risk: no Windows machine for probes. Mitigation: WSL works meanwhile; probes stay pending, never faked.

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| W1 | Native Windows is wanted, not only WSL. | WIN-B8 |

## Revisit when

The probes pass, or Claude Code changes its Windows shell.
