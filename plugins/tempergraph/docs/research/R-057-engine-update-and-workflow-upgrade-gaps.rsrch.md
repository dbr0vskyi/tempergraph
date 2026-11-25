# R-057 Engine update and workflow upgrade: what the design has and lacks

## Problem statement

On 2026-11-20 the owner asked for two commands: one that updates the engine, including the CLI installation, and one that upgrades a workflow by reading the workflow's and the engine's metadata, working out what must change, and changing it with a model's help. This note checks what the design set already says about each, and lists every gap with the document that closes it. It is the input to specs [60](../specs/engine-update.spec.md) to [64](../specs/upgrade-workflow.spec.md) and [ADR-0055](../adr/0055-side-by-side-engine-environments-switched-atomically.adr.md) to [ADR-0059](../adr/0059-an-upgrade-is-done-when-model-free-checks-pass.adr.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Lifecycle and evals (LIF), Engine CLI (CLI), Plugin shell (SHL) | Design specs | [LIF](../specs/lifecycle-and-evals.spec.md), [CLI](../specs/engine-cli.spec.md), [SHL](../specs/plugin-shell.spec.md) |
| Contracts (CON), Workflow model (WFM), Durability (DUR), Local store (LOS) | Design specs | [CON](../specs/contracts.spec.md), [WFM](../specs/workflow-model.spec.md), [DUR](../specs/durability-and-resume.spec.md), [LOS](../specs/local-observability-store.spec.md) |
| Audit (AUD, TSA, PRA), proposals (PRP), eval suites (EVS) | Design specs | [AUD](../specs/workflow-audit.spec.md), [TSA](../specs/tool-surface-audit.spec.md), [PRA](../specs/prompt-audit.spec.md), [PRP](../specs/improvement-proposals.spec.md), [EVS](../specs/eval-suites.spec.md) |
| Design gap review, G2 and G5 | Research | [R-011](R-011-design-gap-review.rsrch.md) |
| Public practice | Research | [R-055](R-055-updating-a-tool-with-long-lived-runs.rsrch.md), [R-056](R-056-automated-and-model-assisted-migrations.rsrch.md) |

## Key findings

### What exists

| # | Finding | Confidence |
|---|---|---|
| H1 | `update [--dry-run]` installs or upgrades the engine from the invoked package's staged copy, decides currency by a content hash, refuses a downgrade and reconciles the manifest; `update --json` prints one object per line. | confirmed (CLI-B7, CLI-B8, CLI-B14, LIF-B7 to LIF-B16) |
| H2 | The installer skill puts the shim on PATH, creates the managed environment and hands over to `update`; it installs the optional `agent-sdk` and `messages-api` extras when asked. | confirmed (SHL-B5) |
| H3 | `upgrade-check <workflow> [--stamp]` checks a workflow against the compatibility changelog (breaking flag, migrate steps, detect rules as patterns) and writes `verified_engine` only when every check passes. It calls no model and rewrites nothing. | confirmed (CLI-B7, CLI-B8, CLI-B14, LIF-B7 to LIF-B16, CON-B4, CON-B5, CON-B6, CON-B7) |
| H4 | Old checkpoints resume: fixtures from each earlier release are kept and tested for every thread state. | confirmed (DUR-B6, DUR-AC4) |
| H5 | The state root and the home folder carry `manifest.json` with a layout version; a newer layout makes runs refuse with exit 2 and read-only verbs read tolerantly. | confirmed (LOS-B7, LOS-B8, LOS-B9, LOS-B12, LOS-B18, LOS-B15) |
| H6 | Every persisted document is versioned and read tolerantly; renaming a key bumps its version. | confirmed (CON-B14, CON-B1, CON-B15) |
| H7 | The audit already finds what a newer engine or executor made stale: `tool-name-stale` in prompts and `declared-tool-stale` and `tool-set-drift` in declarations, measured against the tool set recorded at the last stamp. | confirmed (PRA-B5 to PRA-B11, TSA-B6 to TSA-B12) |
| H8 | The proposal machinery classifies a patch by comparing the parsed workflow before and after, and flags `weakening` (a removed criterion, a lowered severity, a widened judge view). | confirmed (PRP-B14, PRP-B15) |
| H9 | Model-free regression suites gate the stamp. | confirmed (EVS-B7) |

### What is missing

| # | Gap | Where it bites | Confidence | Closed by |
|---|---|---|---|---|
| X1 | **No engine release record.** Nothing names, per release, the workflow-facing interface level, the store layout, the checkpoint format or the plugin version it must ship with; "engine version" is used by AUD and LOS but defined nowhere. | Update, preflight, audit header | confirmed | [VER](../specs/version-metadata.spec.md) |
| X2 | **The changelog's shape is prose-level.** "Breaking flag, migrate steps, detect rules (patterns)" cannot tell a deterministic rename from a change that needs judgement, and detect rules are text patterns only. | Workflow upgrade | confirmed | VER, [ADR-0057](../adr/0057-typed-version-metadata-on-both-sides.adr.md) |
| X3 | **Workflow version identity is undefined** ([R-011](R-011-design-gap-review.rsrch.md) G5): `WorkflowSpec` has `verified_engine` but no version, digest or engine range, while reports, proposals (`base_version`) and lessons (`added_in`) use one. | Upgrade, reports, PRP | confirmed | VER |
| X4 | **The plugin and the engine update apart and nothing ties them.** Claude Code updates the plugin; nothing says when the plugin's skills learn that the engine they ship differs from the installed one ([R-055](R-055-updating-a-tool-with-long-lived-runs.rsrch.md) conclusion 1). | Every session after a plugin update | confirmed | [UPD](../specs/engine-update.spec.md) |
| X5 | **The update replaces the environment in place.** A failed install leaves a half environment; there is no rollback; a running run's process shares the environment being replaced. | Update | confirmed | UPD, [ADR-0055](../adr/0055-side-by-side-engine-environments-switched-atomically.adr.md) |
| X6 | **Runs in flight are not addressed.** Nothing says what happens to a running run, a paused thread, a running orchestration or a detached self-improvement child when the engine changes, or what happens when a release cannot read an old checkpoint. | Update | confirmed | [MIG](../specs/state-and-run-migration.spec.md), [ADR-0056](../adr/0056-threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them.adr.md) |
| X7 | **Store layout migration is not defined.** LOS refuses a newer layout, but nothing moves an older one forward, backs it up or rolls it back. | Update | confirmed | MIG |
| X8 | **A workflow edit under a paused thread is not addressed.** A plugin update repoints the manifest to a new workflow version; a thread paused at a unit the new version removed cannot resume ([R-055](R-055-updating-a-tool-with-long-lived-runs.rsrch.md) U13). | Resume after any workflow update | confirmed | MIG |
| X9 | **No command changes a workflow for a new engine.** `upgrade-check` detects and explains; the owner now asks for the change itself, with a model where a rule cannot do it. | Workflow upgrade | confirmed | [WUP](../specs/workflow-upgrade.spec.md), [UWF](../specs/upgrade-workflow.spec.md), [ADR-0058](../adr/0058-upgrade-by-transforms-first-and-a-gated-model-workflow-for-the-rest.adr.md) |
| X10 | **"Done" for an upgrade is under-defined.** The stamp means the changelog's checks pass; nothing compares the upgraded workflow's validation, audit and suites with what they were before, so a change that adds findings or weakens a gate can still be stamped. | Workflow upgrade | confirmed | WUP, [ADR-0059](../adr/0059-an-upgrade-is-done-when-model-free-checks-pass.adr.md) |
| X12 | **No first-install verb.** Installation was a skill procedure plus `update`; with no shim on `PATH`, nothing a person or agent can type installs the CLI. | First use | confirmed | [UPD-B18, UPD-B19](../specs/engine-update.spec.md) |
| X13 | **Workflows are not carried into a new engine.** Their Python dependencies live in the engine environment, and the register-once manifest has no defined place, so an update can lose a registration or break a workflow. The owner requires that installed workflows be reinstalled automatically and keep working. | Every update | confirmed | [UPD-B20 to UPD-B24](../specs/engine-update.spec.md), [ADR-0060](../adr/0060-registered-workflows-are-reinstalled-and-pinned-never-lost.adr.md) |
| X14 | **No conversational path for the whole update.** Nothing ties Claude Code's marketplace and plugin updates, the engine verb run from the new copy, and the follow-up for workflows. | "Update tempergraph" | confirmed | [LSK](../specs/lifecycle-skills.spec.md), [ADR-0061](../adr/0061-lifecycle-skills-drive-plugin-commands-then-engine-verbs.adr.md) |
| X11 | **Composed workflows have no change notes of their own.** A workflow pack that uses another as a sub-workflow ([ADR-0040](../adr/0040-take-script-steps-attention-and-composition-from-archon.adr.md)) cannot learn what changed in it. | Upgrading a parent workflow | inferred | VER (workflow change notes), WUP |

### Choices against a simpler rule

| # | Simpler rule | This design | Confidence |
|---|---|---|---|
| D1 | No automatic rewrite: the engine checks, the person edits. | Deterministic transforms and a model draft the edits on a branch; a person still reviews and merges, and questions only the owner can answer stay pauses. The owner asked for it, and public practice measures a large share of migration edits done by a model under deterministic validation ([R-056](R-056-automated-and-model-assisted-migrations.rsrch.md) M5). | confirmed (owner's request), the gain `supported` |
| D2 | The compatibility comparison never refuses a run. | The same: the engine range and the stamp only warn; a run refuses only when validation fails, which a tightening release causes by content. | confirmed |
| D3 | One environment per machine. | One **current** environment per machine, with the previous one kept for rollback and for threads a release pins. | confirmed |

## Conclusions

1. Close X1 to X3 and X11 with one metadata spec owning the engine release record, a typed changelog, the workflow's version fields, its stamp record and its own change notes.
2. Close X4, X5 and the CLI-installation half of the ask with an update spec that moves the shim, the managed environment, the extras and the home folder together, beside the old environment, and that tells the plugin's skills when to call it.
3. Close X6 to X8 with a migration spec: running processes keep their engine; paused threads move at resume unless a release pins them; store layouts move forward on first write with a backup; a workflow change under a paused thread is tested by unit names and state keys, the two things a checkpoint holds.
4. Close X9 and X10 with an upgrade verb that plans by detect rules, applies deterministic transforms, hands what needs judgement to a built-in gated workflow, verifies against the pre-upgrade baseline, and stamps only then.
5. `upgrade-check` survives as the read-only planning step of the new verb, so no caller of the old verb breaks.

## Open questions

| Question | Owner |
|---|---|
| Should a later Python-package distribution (pip, uv tool) share the side-by-side environment layout, or leave environments to the package manager? The design keeps the engine's own layout for the plugin channel only. | Owner |
