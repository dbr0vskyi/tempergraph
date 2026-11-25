# MADR-0002 Poll engine files by stat and offset, and call read-only verbs for what only the engine can compute

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

A mod has timers, file reads with offsets and host commands, but no socket server, and Claude Code does not poll a mod ([R-001](../research/R-001-claude-code-mods.rsrch.md)). The engine exposes runs only through files and read-only verbs ([engine ADR-0022](../../../tempergraph/docs/adr/0022-observers-read-files-not-sockets.adr.md)). The status document needs a lock probe and a read-only checkpoint, which only the engine does safely. Starting the engine's Python for every refresh costs a few hundred milliseconds.

## Decision

We will stat append-only and atomically replaced files once a second and read only appended bytes, and call `status`, `status --detail`, `orchestrate status` and `stats` on slower, change-driven schedules, two calls at most at once ([MDS](../specs/data-sources.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Stat and tail files, verbs for combined documents (chosen) | Cheap when idle, quick when something moves; never touches the checkpoint | Two kinds of source to keep in step |
| Verbs only, every second | One source | A Python start per second per root |
| Files only, including the checkpoint | No process starts | Couples the mod to SQLite and LangGraph; cannot probe the lock safely |
| A long-running `events --follow` child per run | Push-like | A child per run; `$.process.spawn` limits; lost on reload |

## Decision rationale

| Criterion | Stat + verbs | Verbs only | Files only | Follow child |
|---|---|---|---|---|
| Idle cost | low | high | low | medium |
| Latency on change | ~1–3 s | ~1 s | ~1 s | ms |
| Safe against a live run | yes | yes | no | yes |
| Survives a mod reload | yes | yes | yes | no |

## Consequences

- Positive: ten live runs cost ten stats a second and a few verb calls.
- Negative: a verdict appears up to about three seconds after it is written.
- Risk: `$.fs` cannot reach another root without a prompt (P-MOD-2). Mitigation: fall back to `events` and `logs` verbs.

## Assumptions

- Run logs grow slowly enough (records per second, not thousands) that offset reads stay small.

## Revisit when

The engine offers a push channel that survives its own death, or the mods API offers file watching.
