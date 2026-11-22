# ADR-0011 Restrict Antigravity sessions with an isolated config home and a deny-only gatekeeper hook

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-19 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

`agy` reads settings, permission rules, hooks and MCP servers only from fixed paths under the user's home (`~/.gemini`) and offers no flag to point elsewhere ([R-002](../research/R-002-antigravity-cli-headless.rsrch.md) A15, A17). Writing the engine's rules into the operator's own config would change the operator's interactive sessions and race between parallel runs. A PreToolUse hook's `deny` was reported honoured in print mode, while its `allow` was reported ignored (A16).

## Decision

We will start each isolated Antigravity session with `HOME` pointing at a fresh, owner-only session home that holds only the engine's settings, permission rules, MCP config for the allowed views, a hook entry for the engine's gatekeeper, and the credentials P-AG-1 confirms. The gatekeeper answers only `deny` for tool calls outside the session's allow-list and stays silent otherwise. The home is removed on every exit path. Until P-AG-1 and P-AG-2 are confirmed for the installed version, sessions run in **user mode** with the operator's home, enforcement off and `isolation = user` recorded ([EAG-B10, EAG-B11, EAG-B5](../specs/12-executor-antigravity.spec.md)).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Per-session home plus deny-only gatekeeper (chosen) | Leaves the operator's config untouched; parallel sessions do not collide; deny is the reported-working hook path | Rests on undocumented path behaviour; credentials must be supplied per session |
| Edit the operator's `~/.gemini` for the run | Uses documented paths as is | Changes the operator's own sessions; races between parallel runs; restore can fail |
| Allow-returning hook as the whole policy | One mechanism | `allow` was reported ignored in print mode |
| Container per session | Strong isolation | Heavy; sign-in and tooling must be rebuilt inside |

## Decision rationale

| Criterion | Session home | Edit user config | Allow hook | Container |
|---|---|---|---|---|
| Operator's config untouched | yes | no | yes | yes |
| Safe for parallel sessions | yes | no | yes | yes |
| Rests on reported behaviour | deny path | documented paths | refuted path | — |
| Setup cost | low | low | low | high |

## Assumptions

- Pointing `HOME` elsewhere makes `agy` read only the new home and not cache paths elsewhere. **Open:** probe P-AG-1.
- API-key mode is allowed for the operator; copying cached sign-in files is a fallback whose terms were not read ([ADR-0007](0007-two-first-class-executors.adr.md)).

## Consequences

- Positive: once probed, Antigravity steps can enforce step tools and host judges.
- Negative: anything else the CLI reads from `HOME` (shell config, git config, other tools) is absent in the session. Mitigation: probe P-AG-1 also records which non-`agy` tools a step's commands needed from the home; until then, steps that need such tools run in user mode.
- Risk: a release moves the config path. Mitigation: P-AG-1 is re-run on every new CLI version before isolation is declared again.

## Revisit when

`agy` documents a config-directory flag or per-invocation settings.
