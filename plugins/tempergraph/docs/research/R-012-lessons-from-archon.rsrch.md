# R-012 What tempergraph should take from Archon

## Problem statement

[R-010](R-010-landscape-and-verdict.rsrch.md) names Archon as the nearest neighbour to the tempergraph engine. The owner asked what tempergraph might want to take from it. The owner also stated the product's scope on 2026-11-19. tempergraph is a CLI delivered as a Claude Code plugin with skills, and a Python package may follow. It is meant for **any workflow in the delivery pipeline, not only coding**. Its distinguishing promise is a workflow you can trust, because the authoring flow **interviews the person about what a good result is** and helps them build the verifications for it.

This note sets Archon's features against that scope. Each feature is sorted into adopt, adapt or avoid, and each gets a target in the design set. As in R-011, shared specs are not edited here.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Archon README, `dev` branch (references tag v0.11.1) | Official, newest | https://raw.githubusercontent.com/coleam00/Archon/dev/README.md |
| Archon AGENTS.md | Official contributor rules | https://raw.githubusercontent.com/coleam00/Archon/HEAD/AGENTS.md |
| Galaxy Foundry component review (rev 3, 2026-05-22, on v0.3.12) | Third-party technical review, older version | https://galaxyproject.github.io/foundry/research/component-archon/ |
| Effloow Lab post, republished on dev.to (updated 2026-11-14) | Practitioner trial | https://dev.to/jangwook_kim_e31e7291ad98/archon-v2-open-source-coding-agent-harnesses-1n6f |
| Better Stack guide | Secondary guide, older model | https://betterstack.com/community/guides/ai/archon-ai/ |
| MindStudio blog (2026-04-11) | Vendor marketing; contradicts the README on runtime | https://www.mindstudio.ai/blog/what-is-archon-harness-builder |

The README and AGENTS.md are the authority. Facts found only in the v0.3-era Galaxy review are marked `supported` and may be out of date. The MindStudio post is not relied on.

## Key findings

### What Archon is (November 2026)

| # | Finding | Confidence |
|---|---|---|
| A1 | An MIT-licensed Bun/TypeScript monorepo. It describes itself as "a workflow engine for AI coding agents" and "the first open-source harness builder for AI coding". It drives Claude Code, Codex and Pi through their CLIs and SDKs. | confirmed |
| A2 | Workflows are YAML. Nodes are linked by `depends_on`, and later nodes read `$nodeId.output`. The node forms in the current README are `prompt`, `bash`, `loop` (`until_bash`, `max_iterations`, `fresh_context`), `loop_group` (nested nodes, `max_iterations`, `until_bash`) and `wait` (`attention`, `form: approval`). Nodes also take `when` and `cancel`. The older review adds `script` (Bun or uv), `output_format` (a JSON schema per node), `trigger_rule`, `retry`, `context: fresh\|shared`, and a per-node `model` and `provider`. | confirmed (README); supported (older review) |
| A3 | It ships a bundled `sdlc` workflow pack: `archon-triage`, `-investigate`, `-plan`, `-implement`, `-pr`, `-deliver`, `-ship`, `-review` (parallel specialist lenses on a diff), `-validate` (runs project checks and returns a structured verdict) and `-upkeep`. Bundled workflows are "reference implementations, not a frozen compatibility surface". Older workflows were dropped and can be recovered from a tag. | confirmed |
| A4 | Interfaces include the CLI (`workflow list`, `run`, `attention`, `serve`, `skill add`, `plugin add`) and a web UI. The UI has a runs list with status filters, run detail (event log, artifacts, graph), project chat, and an experimental visual builder. There are adapters for Slack, Telegram, Discord and GitHub webhooks, plus a triggers guide. Plugins come in four kinds: workflow pack, provider, forge and chat. | confirmed |
| A5 | Storage is SQLite by default with optional Postgres, across about 14 core tables (sessions, workflow runs, workflow events, node sessions, isolation environments, and more). Schema changes are additive only, and the two stores are kept aligned. | confirmed |
| A6 | Each run gets its own git worktree or reuses one. AGENTS.md says a worktree "is not an execution or security sandbox". | confirmed |
| A7 | Telemetry goes to PostHog and is on unless opted out. It reports per-run USD cost and tokens to the maintainers. A user-facing cost view was absent as of May 2026. | confirmed (telemetry), supported (no user view) |
| A8 | The quality controls are bash validation nodes, the `archon-validate` and `archon-review` workflows, and a merge queue that checks the review verdict and CI. No independent judge session, no read-only enforcement and no verdict derived by rule is described. | confirmed (absence in the README and the review) |
| A9 | Resume of an interrupted run and approval pauses that survive a restart were reported for v0.3. The current README does not state them. | supported |
| A10 | The project dogfoods itself: it reports 524 pull requests merged from 1 to 19 October 2026, 363 of them built by Archon runs. It has about 21.7k stars (May 2026), frequent releases and churn in node syntax before 1.0 (`approval:` became `wait:`). | confirmed (README); supported (stars) |
| A11 | The criticisms raised are these. Loops iterate one prompt, with no per-item sub-graph. It assumes a single developer. It is locked to three providers. One maintainer carries most of the work. Setup has tooling friction, and validation nodes can give false confidence. | supported |

### Adopt, adapt or avoid

| # | Archon feature | Verdict | What tempergraph should do | Target |
|---|---|---|---|---|
| L1 | **Deterministic `bash` and `script` nodes** that do work without a model | **Adopt** | tempergraph has deterministic *checks* but no deterministic *step*. Many delivery-pipeline steps are not model work, for example run the build, export a report or call an API. Add a unit kind `script`: a declared command or a callable, no judge, its gate a check only. It is logged as a step with zero model calls. This also keeps non-experts from wrapping a shell command in an agent session. | CON-B4, CON-B5, CON-B6, CON-B7 `UnitSpec.kind`, WFM, CMP |
| L2 | **`$node.output` references** and explicit `depends_on` | **Adapt** | tempergraph's artifacts already flow by key. What it lacks is a written reference syntax in the declaration format ([R-011 G2](R-011-design-gap-review.rsrch.md)). Use `{artifact.<key>}` as a template field, validated like any field. Keep forward `order` plus declared routes rather than a free DAG: static edges are what make reachability, budgets and the diagram checkable. | Declaration format spec (G2), CON-B8 |
| L3 | **`output_format` (a JSON schema per node)** | **Adopt** | This is the same move as [R-011 G6](R-011-design-gap-review.rsrch.md). Declared artifacts and the judgement are requested as a schema where the executor supports it. Archon applies it per node; tempergraph should too, so a `pull_request` artifact is a typed object, not a line of text. | CON, PRM, JDG, EXI |
| L4 | **`loop` / `loop_group` with `until_bash` and `fresh_context`** | **Adapt** | tempergraph's retries are verdict-driven edges, and that is stronger. What Archon's loop expresses that tempergraph lacks is "repeat until a deterministic condition holds", for example until every task in the list is done. The map primitive covers lists. A bounded `until` on a unit (a check that must pass to leave, with its own budget counter) is a small addition. Fresh context per iteration is already the rule. | CMP-B10 to CMP-B16, BUD |
| L5 | **`wait` with `attention`, and the `archon workflow attention` verb** | **Adopt** | One command that lists **everything waiting on a person, across all runs**, with the exact command to answer each item. tempergraph's status document has `pending_gates` per thread, but no inbox verb. Add `tempergraph attention`, read-only and model-free. It is also the natural home screen of the monitor plugin. | CLI, DUR; monitor thread |
| L6 | **Chat and forge adapters** (Slack, Telegram, Discord, GitHub webhooks) and triggers | **Adapt** | A pause answered from a phone or a pull-request comment is what makes long delivery-pipeline workflows usable. In tempergraph this is a separate plugin, never the engine. It reads `facts`, registers lifecycle hooks, and resumes through the CLI with `--as-agent` recorded. It must not answer a gate on its own: the person's reply is relayed, and C6 holds. Triggers (start a run from an issue label) take the same route. | HOK-B1 to HOK-B6 hooks, HUM-B6; a later adapter plugin |
| L7 | **Plugin kinds: workflow pack, provider, forge, chat** | **Adopt** | tempergraph is already a plugin marketplace. Name the same kinds: **workflow pack** (a Claude Code plugin carrying one or more workflows: skills, prompts and agents, plus the Python part tempergraph loads after registration, as the owner defined a workflow package on 2026-11-19), **executor** (a fifth executor without an engine edit, as EXI already allows), and **adapter** (chat or forge). Each workflow pack declares the engine release it was stamped against (`verified_engine` exists). | marketplace, LIF, SHL |
| L8 | **A bundled SDLC pack** of small, composable workflows (triage, investigate, plan, implement, pr, review, validate) | **Adopt the shape** | Ship several small workflows, each with its own signature gate, rather than one large delivery workflow. Compose them with sub-workflows. This matches the owner's "any workflow in the delivery pipeline". Mark them reference implementations with their own versions, as Archon does, so the engine's compatibility surface stays the engine. | temperspec, SHL template gallery ([R-011 G3](R-011-design-gap-review.rsrch.md)) |
| L9 | **Run detail UI: event log, artifacts, graph; runs list with filters** | **Adopt as requirements** | These are the minimum views of the monitor plugin. A tempergraph run detail should add what Archon lacks: per gate, the verdict, each criterion's status and evidence, judge executor, retries by cause, and cost reported against estimated. | monitor thread (point 3) |
| L10 | **SQLite default, Postgres optional, additive-only schema with both stores aligned** | **Adopt the rule** | Same choice as [ADR-0014](../adr/0014-sqlite-checkpointer.adr.md). Add Archon's discipline to C12: a schema change is additive, and any second store is kept in step by a test. This matters for the cross-machine aggregation of point 4. | CON-B14, CON-B1, CON-B15, DUR; observability thread |
| L11 | **"A worktree is not a sandbox", said plainly** | **Adopt the honesty** | It is the same finding as [R-011 G10](R-011-design-gap-review.rsrch.md). State it in SEC and in the authoring skill's consequences table. | SEC, SHL |
| L12 | **Dogfooding metric** (363 of 524 PRs built by Archon runs) | **Adopt** | Publish the share of tempergraph's own changes made by tempergraph runs, from the ledger. It is cheap, honest and persuasive, and fits the "say what is proven" tenet. | OBS reports, LIF |
| L13 | **Experimental visual builder** | **Avoid as the primary path** | A visual graph editor helps someone who already knows what to build. tempergraph's promise is the opposite: an **interview** that finds out what a good result is and derives the checks. A diagram drawn by the engine from the result (which tempergraph has) is enough to review the outcome. | SHL authoring |
| L14 | **Telemetry on by default (opt-out), cost sent to maintainers** | **Avoid** | It conflicts with tempergraph's "nothing is sent anywhere" stance ([OBS](../specs/observability-and-cost.spec.md)). Cost belongs to the user first. Any aggregation is opt-in and goes to the operator's own destination. | OBS; observability thread |
| L15 | **Review as a workflow of specialist lenses, no independent judge** | **Avoid; keep tempergraph's gate** | Parallel lenses are a useful *subject* for a judge, for example several judges on different criteria groups. They do not replace a read-only, guarded, rule-derived verdict. Archon's absence here is tempergraph's main differentiator ([R-010 S1](R-010-landscape-and-verdict.rsrch.md)). | JDG |
| L16 | **Free-form loops and syntax churn before 1.0** | **Avoid** | Freeze the declaration format behind a schema version from the first release (C12), with a migration in the compatibility changelog. Do not rename a node kind without a version bump. | Declaration format spec (G2), LIF |

### What the owner's scope needs that Archon does not have

The owner's scope is any delivery-pipeline workflow, trusted because the authoring flow interviews the person. Archon answers "how do I run agents in a defined order". It does not answer "how do I know this workflow produces what I want". The gap is the core of tempergraph's authoring design:

| Need | Archon | tempergraph today | What to add |
|---|---|---|---|
| An interview that turns "what does good look like for you" into a written outcome | none; you write YAML or use the builder | Authoring phases name "outcome" ([SHL-B9](../specs/plugin-shell.spec.md)), with no object behind it | The `OutcomeSpec` of [R-011 G1](R-011-design-gap-review.rsrch.md), produced by the interview: an outcome statement, outcome criteria, examples of good and bad results from the person |
| Turning each stated criterion into the cheapest trustworthy verification | bash nodes, written by the author | [SHL-B4](../specs/plugin-shell.spec.md) prefers a check over a judge | An explicit ladder the interview walks for each criterion: (1) a deterministic check, (2) a check over a structured artifact, (3) a judged criterion with a check method, (4) a person's approval. The skill records why each criterion sits on its rung. |
| Evidence that the verification works before the workflow is trusted | none | Calibration cases and the readiness report ([LIF](../specs/lifecycle-and-evals.spec.md)) | The interview collects one good and one bad example per judged criterion as the first calibration cases, so every judge starts with a score, not only after harvest |
| Non-code workflows | coding only (worktree, forge) | Git-centred workspace ([R-011 G9](R-011-design-gap-review.rsrch.md)) | The non-git workspace of G9, and artifact kinds beyond files and pull requests (a document, a ticket, a message), each with a read view for its judge |

## Conclusions

1. Archon is a well-run, popular engine for **ordering coding-agent work**. tempergraph should borrow its **operational surface**: deterministic script steps (L1), per-node output schemas (L3), an "attention" inbox across runs (L5), chat and forge adapters as separate plugins (L6), named plugin kinds (L7), small composable reference workflows (L8), the run-detail views (L9), additive schema discipline (L10) and a dogfooding metric (L12).
2. tempergraph should **not** borrow Archon's quality model (review as lenses, no independent judge), its opt-out telemetry, or its unversioned syntax churn (L14–L16).
3. The largest gap between the two is not in the runtime. It is the **interview-led authoring** the owner describes, which Archon does not attempt. It depends on [R-011 G1](R-011-design-gap-review.rsrch.md) (an outcome object), G2 (a declaration format) and G3 (a concrete path for non-experts), and adds a verification ladder and calibration from the interview itself. That is where tempergraph can be distinct from Archon and from Claude Code's dynamic workflows.
4. Of the adopt items, L1 (script units), L3 (output schemas) and L5 (attention verb) are small and change contracts, so by [ADR-0021](../adr/0021-scope-of-planned-work.adr.md)'s rule they belong in the specs before a plan is written. L6 to L9 belong to the monitor, adapter and workflow-pack work.

## Owner decisions

On 2026-11-19 the owner took L1 (script steps, extended to hybrid script-and-model steps), L5 (the attention verb) and L8 (composition), and asked for a detailed run log. The owner declined L3 for step outputs, because outputs are Markdown files, wiki pages and the like. These choices are recorded in [ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md). The owner also stated that a workflow, once improved locally to a level of autonomy and quality, moves to the pipeline; that path is proposed in [ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md).

## Open questions

| Question | Owner |
|---|---|
| Should a chat or forge adapter (L6) be a first-party plugin in this marketplace, and which channel first: GitHub comments, Slack or Telegram? | Owner |
| Should the authoring interview be a single skill or itself a tempergraph workflow, with gates on the outcome statement and on the verification plan? This note leans to a workflow, so the authoring flow is held to the standard it teaches. | Owner |
| Is Archon worth supporting as an executor or a peer (tempergraph gating an Archon run), or only as a source of ideas? Not researched further. | Owner |
