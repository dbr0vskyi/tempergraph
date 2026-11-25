# Supervision cost is measured by a journal the host writes, not by the engine's read-only verbs

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner calls the extra cost of agentic babysitting a crucial metric. A supervising session costs a share on top of the runs it supervises, and none of that spend is tied to a run (research `callers-supervision-and-babysitting-cost` B1, B4). OSK-AC4 asks for at most 3% but no document says how it is measured (D7). The spend happens in the supervising host, which may be Claude Code, an Agent SDK or Messages API application, or an Antigravity session; the engine meters only its own sessions ([OBS](../specs/observability-and-cost.spec.md)). Most supervising calls are read-only verbs (`status`, `wait`, `facts`), and OVR-B15 says they create nothing (D8). Hook input carries no usage, but the transcript the hook can read holds per-message usage (H6).

## Decision

We will measure supervision cost from a **supervision journal** per host session in the home folder, written by the tempergraph plugin's Claude Code hooks (engine calls, person turns, per-message usage read from the transcript, session start and end) and, for applications, by one writing verb, `supervision log` ([SCO-B10, SCO-B11](../specs/supervision-cost.spec.md)). The model-free orchestration supervisor and scripted pipelines are `measured_zero` by construction; any other supervisor is `unmeasured`, never zero. The engine joins the journal to run logs when a thread's supervision closes and writes the figures to the ledger and the sinks. No read-only verb writes anything; C13 is unchanged. The engine's own sessions are excluded by an environment key the launcher sets.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Host-written journal plus a writing verb for applications (chosen) | Measures where the spend is; keeps C13; the plugin is already in the host | Depends on hook behaviour (P-SUP-3); unmarked hosts stay unmeasured |
| Let read-only verbs append an access record | Counts every poll from every host | Breaks C13 and its hash test; still no token usage |
| Ask the supervising agent to report its own cost | No hooks | Models do not know their usage; prose is not data |
| Read the status line's session cost only | One number, already reported | Session-level: cannot be split per run, mixes other work |
| A proxy in front of the model API that meters the host | Exact | Changes the person's setup and credentials; out of scope for a plugin |

## Decision rationale

| Criterion | Journal | Verb records | Self-report | Status line | Proxy |
|---|---|---|---|---|---|
| Per-run figures | yes | calls only | no | no | yes |
| Keeps C13 | yes | no | yes | yes | yes |
| No change to the person's setup | yes | yes | yes | yes | no |
| Unmeasured shown as such | yes | partly | no | partly | yes |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| C1 | Claude Code hooks can see an engine command, its response size, and the transcript path whose lines carry usage (P-SUP-3). | SCO-B12 |
| C2 | Reading the host's transcript for numbers only, from the person's own plugin, on the person's machine, is acceptable; nothing is copied but counts. | SCO-B17 |
| C3 | Prices for the supervising host's model come from the engine's price table, so the figure is an estimate beside any session cost the host reports. | SCO-B13, SCO-B14 |

## Consequences

- Positive: supervision cost per run, per workflow and per orchestration becomes a number the loop, the audit and promotion can use; OSK-AC4 can be checked.
- Negative: one more home-folder file per session, hooks that must stay fast, and a figure that is projected until the probe runs.
- Risk: hooks slow the host. Mitigation: append-only writes, no network, a 2 s ceiling and failure containment (SCO-AC4).

## Revisit when

A host exposes per-message usage to hooks directly, or the Messages API or Agent SDK gains a usage callback the engine could subscribe to.
