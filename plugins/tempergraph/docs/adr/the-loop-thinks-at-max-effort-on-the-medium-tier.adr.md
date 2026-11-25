# The loop thinks at the highest effort on the medium tier

## Context

The loop child's friction judge and its session reviews read long session logs and decide what in them is a defect ([SIL-B17](../specs/self-improvement.spec.md)). The run settings `loop_model` and `loop_effort` choose its tier and effort ([RST-B18 to RST-B21](../specs/run-settings-and-overrides.spec.md)). The owner set the loop on the medium tier and asked that it think at the highest effort (2026-11-22, recorded with release 3's first build). The first measured loop at that setting reviewed 13 sessions for 0.66 USD ([research `does-the-improvement-loop-find-what-a-reviewer-finds`](../research/does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md) S2).

## Decision

We will default `loop_model` to `medium` and `loop_effort` to `max`.

## Options considered

### Medium tier at the highest effort (chosen)

For: the reading of long logs gains from more thinking, at a cost measured as small. Against: the slowest setting of the tier.

### Medium tier at the default effort

For: faster and cheaper per session. Against: shallower reading of the logs the loop exists to read.

### The large tier

For: the strongest reader. Against: several times the cost on every run, for a child that files nothing alone.

## Consequences

Each loop child costs more than at the default effort; the run setting lowers it per run or per workflow. The reason lives here, so SIL-B17 states only the default.

## Revisit when

Measured loop costs or the quality of its findings argue for another tier or effort.
