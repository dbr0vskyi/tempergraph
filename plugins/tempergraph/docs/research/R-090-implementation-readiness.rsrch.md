# R-090 Implementation readiness of the design set

## Problem statement

The owner asked on 2026-11-20 whether the specs and decision records are ready to start implementing tempergraph from, and what the first release should contain. This note answers the first half. It first read the set as merged on `main` after PR 13 (overview, contracts, 61 component specs, ADR-0001 to ADR-0089, R-001 to R-085, the monitor's own set); it was re-run the same day after PRs 15, 16 and 17 merged (69 spec files, ADR-0001 to ADR-0114, R-001 to R-105; see [Re-evaluation](#re-evaluation-after-prs-15-16-and-17)) against what the temperspec method requires before a plan is written, and lists what blocks or risks a start. The scope half is [ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md), [ADR-0091](../adr/0091-first-release-ships-the-claude-executor-only.adr.md) and the [first-release plan](../plans/first-release.plan.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Specs 00 to 87 and the monitor specs 00 to 06 | Behaviour specs | [specs/](../specs/00-overview.spec.md), [monitor](../../../tempergraph-monitor/docs/specs/00-overview.spec.md) |
| ADR-0001 to ADR-0089 | Decision records | [adr/](../adr/README.md) |
| R-011 gap review | Research note | [R-011](R-011-design-gap-review.rsrch.md) |
| temperspec artifacts 3.5 to 3.7 | Method reference | — |
| Scripted scans of the set | Id uniqueness, behaviour order, link resolution, size budget, open-question tables | run on 2026-11-20 over `specs/`, `adr/`, `research/` |

## Key findings

### A. What the method requires before a plan

| # | Finding | Confidence |
|---|---|---|
| A1 | A plan is never written against a draft or missing spec, and a spec is `ready-for-implementation` only when no open question blocks planning; its open-questions table is then empty. | confirmed |
| A2 | Every spec in this set is `review` (TEL is `draft`, deferred). No spec is `ready-for-implementation`, because the owner has reviewed none ([ADR-0001](../adr/0001-standalone-design-assumptions.adr.md)). | confirmed |
| A3 | Every acceptance criterion maps to a requirement and every requirement to a phase; each phase is one coding session's work. A release-level plan can meet this by naming, per spec, the criteria in scope and the phase that owns them; the expanded per-track plans then add rows. | inferred |

### B. Structure and hygiene

| # | Finding | Confidence |
|---|---|---|
| B1 | Every spec is within the 400-line and 30 KB budget (largest: RST 28.5 KB, CON 359 lines). | confirmed |
| B2 | Every relative link in the engine and monitor sets resolves (0 broken). | confirmed |
| B3 | One duplicate id: `SEC-AC-4` twice. Fixed in this change (`SEC-AC-5`). | confirmed |
| B4 | `EXI-B11` sat after `EXI-B15`. Moved into order in this change. Behaviour ids out of order in CST, TEL, ORC and RST are append-order only; ids are unique, so nothing is renumbered. | confirmed |
| B5 | Of the 62 specs, 44 carry open questions. Each one in the specs the first release builds has a stated default in its own row (for example "first release keeps the per-invocation cap", "assumed: the collector"). None blocks planning. | confirmed |

### C. Contradictions between documents

| # | Contradiction | Severity | Resolution | Confidence |
|---|---|---|---|---|
| X1 | ADR-0007 ("two first-class executors") was `proposed` as if current; ADR-0018 adds two more and superseded nothing (R-011 X1). | low | Fixed: ADR-0007 marked superseded by 0018, in its header, 0018's header and the index. ADR-0001 A3 ("no SDK or raw API in the first release") is true again under [ADR-0091](../adr/0091-first-release-ships-the-claude-executor-only.adr.md). | confirmed |
| X2 | JDG said it owns C4 "together with" PRM and GRD; OVR-AC-1 needs exactly one owner (R-011 X2). | low | Fixed: JDG owns C4; PRM and GRD uphold it. | confirmed |
| X3 | The `attention` verb of accepted [ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md) is used by ASK-B4, ORC, SCO and ADR-0041, but no spec owned it and the CLI verb table did not list it. | medium | Fixed: verb row, CLI-B6 and CLI-AC-5 in [CLI](../specs/17-engine-cli.spec.md), from the ADR's own wording. | confirmed |
| X4 | The `evals …` verbs (EVS, JCL, LIF) were not in the CLI verb table that claims to list every verb. | low | Fixed: one row pointing to the owner specs. | confirmed |
| X5 | CLI-B3 listed probe ranges P-CC-1…6, P-AS-1…3, P-AG-1…8; the executor specs define P-CC-1…8, P-AS-1…4, P-AG-1…9. | low | Fixed in CLI-B3. | confirmed |
| X6 | EXI's design note says a capability resting on an unconfirmed probe is declared `false` until the probe is recorded; ECC declares `restricts_judge_tools = true` while P-CC-2 and P-CC-6, which it rests on, are `not run`. If the rule were applied, no shipped executor but `messages-api` could host a judge. | **high** | Not mechanical. Run P-CC-2 and P-CC-6 before the judge launch is relied on (plan track T0); the guard of [GRD](../specs/06-independence-guard.spec.md) backs them after the fact. If the owner prefers, amend EXI's note to admit "guard-backed" as a basis. | confirmed |
| X7 | `promote-check` is a verb in ADR-0041 (proposed), AUD, SUP-AC-3 and ADR-0089, but no spec owns it and the CLI table omits it. | medium | Not mechanical: it needs a spec (stages, stamp, criteria). Out of the first release ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md)); SUP-AC-3's `promote-check` half moves with it. | confirmed |
| X8 | The ledger is owned by SIL ([CON §2.10](../specs/01-contracts.spec.md)), but HUM-B6, OBS-B3, OBS §2.4 and SUP write ledger rows. With SIL out of the first release, the ledger writer must still ship. | low | Scope note, not a design change: the first release builds the ledger writer and its rows; SIL's lenses come later. | confirmed |
| X9 | The README and CONTEXT call tempergraph a "Python framework"; the owner's decision is a CLI delivered as a Claude Code plugin (R-011 G2, X4). CLAUDE.md and CONTEXT say "no commits yet". | low | The stale status lines are fixed; the product wording is left for the owner's README rewrite. | confirmed |

### D. Gaps that block a part of the first release

| # | Gap | Blocks | Evidence | Confidence |
|---|---|---|---|---|
| D1 | **The workflow package and its declaration format are unspecified** (R-011 G2). `load()` "imports the package's declaration module", but no spec says what that module holds, how the plugin half and the Python half of a package relate, or what the authoring skill writes. | Registry and loading, the authoring path, every example workflow | [WFM §2](../specs/02-workflow-model.spec.md), [CON §2.1](../specs/01-contracts.spec.md) | confirmed |
| D2 | **Resolved by [AUT](../specs/89-workflow-authoring.spec.md) and [SCF](../specs/91-blueprint-and-scaffold.spec.md).** **Authoring has a phase list but no contract** (R-011 G3). A blueprint document, its validation, the scaffold, a blueprint comparison and a literal check have no spec; there is no minimal workflow and no template. | The workflow creation path, which the owner names as half of the first release | [SHL-B9](../specs/19-plugin-shell.spec.md) | confirmed |
| D3 | **No run-level definition of a good outcome** (R-011 G1). The concept's first line has per-step criteria only; the authoring "outcome" phase produces nothing a gate reads. | The authoring outcome phase and a final judged gate | [CON §2.1](../specs/01-contracts.spec.md) | confirmed |
| D4 | **Non-git folders are undefined** (R-011 G9). The state root is found from git's common directory. | Workflows run outside a repository | [WSP §2](../specs/13-workspace-and-concurrency.spec.md) | confirmed |

R-011 G6 (structured judge output), G8 (run cap on uncapped executors), G10 (step sandbox profile), U2 (event delivery) and U4 (confining LangGraph imports) are still unapplied. None blocks a first release on `claude`: it has a session cost cap, judges parse a fenced block with one re-ask, event waits are later, and U4 is a code rule the plan adopts (§3 of the plan). G5 (version identity), G7 (judge bar), G11 to G13 and U1 were applied by later threads (VER, JCL, EVT, PRP, ORC, PRV, CHK). G14 is ADR-0041 without a spec (X7).

### E. Facts about binaries and hosts that need a live probe

No control may rest on an unrun probe ([research rules](../README.md#research-rules)). These are the probes the first release's code depends on; every other probe belongs to an executor or host the first release does not ship.

| Probe | Fact | What depends on it in the first release | If refuted |
|---|---|---|---|
| P-CC-5 | Prompt on stdin with `-p` and no positional prompt | Every launch (`prompt_off_argv`) | Switch to `--input-format stream-json` (ECC's open question) |
| P-CC-2 | `--tools` plus `--disallowedTools "mcp__*"` leaves exactly those tools | Judge restriction | Judges cannot run on `claude`; first release blocked until a fix (X6) |
| P-CC-6 | `dontAsk` refuses an unlisted call without a prompt and emits `permission_denied` | Judge launch | Guard still discards; judges may hang until timeout |
| P-CC-1 | `--bare` keeps user plugins out and gateway credentials working | `isolates_user_config`, the cleaner judge launch | `--setting-sources ""` path, already specified |
| P-CC-3 | Stream shape when `--max-budget-usd` ends a session | `cap_reached` classification | Classified as `model` until known |
| P-CC-4, P-CC-7, P-CC-8 | Subagent model precedence; native transcript path; `Skill(<p>:<n>)` rule | Subagent alias; transcript locator; `skill:` capability | Each has a stated fallback in ECC, EVT and ADR-0078 |
| P-SUP-1, P-SUP-2, P-SUP-3 | Session id in the Bash environment; prompt text in `UserPromptSubmit`; `PostToolUse` and transcript usage | Relayed decisions counted as a person's; supervision cost | Relays stay `turn_only`; supervision cost `unmeasured`, shown as such |
| Monitor mod API | The mods facts of the monitor's R-001 on the current Claude Code release | The monitor plugin | Monitor track waits |

## Conclusions

1. **Ready, with conditions.** The engine core (workflow model, compiler, gate funnel, judge and guard, budgets, durability, executor interface and the `claude` adapter, settings, reruns, observability and supervision) is specified to the level the method asks: typed contracts, behaviours with example tables, error tables and verifiable criteria, within budget and with no broken link. Code for it can start once its specs move to `ready-for-implementation`.
2. **Condition 1, status.** No spec is `ready-for-implementation`. The cheapest path keeps the owner's attention small: each track's first phase converts its specs' open questions into recorded defaults (every one already has one, B5) and moves them to `ready-for-implementation`, and the owner's review is of the plan and the two scope records, not of 62 specs.
3. **Condition 2, design gaps D1 to D3.** The creation path cannot be built until the package format, the authoring contract and the outcome definition are specified. They block only the packaging and authoring tracks, which come after the core in the plan, so design and core code can proceed side by side.
4. **Condition 3, probes.** P-CC-2, P-CC-5 and P-CC-6 must be run on the pinned Claude Code release before the `claude` adapter is relied on (X6). They are short, model-free or near-free, and need the owner's machine and sign-in.
5. **Not blocking.** D4 is a recorded limitation of the first release (git repositories only). X7 moves with promotion to a later release. The mechanical contradictions are fixed in this change.

## Open questions

| Question | Owner |
|---|---|
| May each track's first phase move its specs to `ready-for-implementation` on the recorded defaults, or does the owner want to review each spec first? The plan assumes the former. | Owner |
