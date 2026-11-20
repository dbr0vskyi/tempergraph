# R-056 Automated and model-assisted migrations: public practice

## Problem statement

The owner asked for a command that upgrades a workflow to a newer engine: it reads the workflow's and the engine's metadata, works out what must change, and changes it, which "requires a model". The other way is an upgrade check that detects and explains, and leaves every edit to a person. This note asks how public tools that migrate code between library versions split the work between deterministic transforms and a model, and how they verify the result, so the workflow upgrade ([WUP](../specs/63-workflow-upgrade.spec.md)) follows practice that has been measured. It informs [ADR-0057](../adr/0057-typed-version-metadata-on-both-sides.adr.md) to [ADR-0059](../adr/0059-an-upgrade-is-done-when-model-free-checks-pass-against-the-old-baseline.adr.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Angular CLI `ng update` specification | Design spec in the Angular CLI repository (may lag the current CLI) | https://github.com/angular/angular-cli/blob/master/docs/specifications/update.md |
| "Migrating Code At Scale With LLMs At Google" (arXiv 2504.09691) | Industrial experience paper | https://arxiv.org/abs/2504.09691 |
| "How is Google using AI for internal code migrations?" (arXiv 2501.06972) | Industrial experience paper | https://arxiv.org/html/2501.06972v1 |

Both arXiv papers were read in part verbatim; their later sections only through a summary, which no finding below uses.

## Key findings

| # | Finding | Confidence |
|---|---|---|
| M1 | `ng update` selects migrations by **version range**: a library lists migrations, each with a `version`, and the tool runs every migration whose version lies between the installed and the requested version, in ascending order; `--from` and `--to` bound the range. | supported (Angular spec) |
| M2 | Angular migrations are **code** (a schematic factory per entry); only the version and the path are data. Peer dependency checks run first, and on failure "nothing will be committed on the filesystem". | supported (Angular spec) |
| M3 | Google's migration system finds candidate locations **deterministically** (code search and cross-references), deliberately over-inclusive, then **categorizes** them (not migrated, irrelevant, relevant, left over); the model edits only locations that are relevant and not yet migrated. | confirmed (both papers) |
| M4 | The model's output is a **diff**, made at temperature 0 with several attempts per file; each attempt passes a fixed order of validators (applies cleanly, whitespace, parses, "was the change necessary", builds, tests). A file that fails is dropped and marked for manual migration. | supported (2504.09691) |
| M5 | Measured share: 74% of code changes and 69% of edits in 595 changes over 39 migrations were model-generated (2504.09691); 80% of modifications in landed changes fully model-authored in one ID-width migration, and 87% of generated code committed unchanged in a test-framework migration (2501.06972). | supported (each from one paper) |
| M6 | The time saved (about 50%) is an **engineers' estimate**, not a measurement, in both papers. | confirmed (both papers say so) |
| M7 | **A person reviews every change**; code owners accept through code review; final edits by hand are common; rollout stays largely human-driven. | confirmed (both papers) |
| M8 | Named failure modes: context-window limits on whole files, hallucinated edits (reformatting, added comments), languages the model handles poorly, **pre-existing test failures that block validation**, and tests the validators could not run. | supported (2504.09691) |
| M9 | A breaking engine change can touch many files across several workflows by hand. Detect patterns written for it match before the change and none after, so the same rules both find the work and show it done. | inferred |
| M10 | A breaking change can need an answer only the owner has: new judge briefs and criteria, the repository for the workflow's issues. A guessed one passes the check and judges badly, which is the case against a model rewrite. | inferred |
| M11 | Detect rules can be text patterns over code and prompts; a stamp that follows them means "every deterministic check in the changelog passes", not that behaviour is identical. | inferred |

## Conclusions

1. **Select by range, apply in release order.** A workflow upgrade selects the changelog entries between the workflow's stamp and the running engine and applies them oldest first (M1), so a workflow two releases behind is upgraded the same way as two single steps.
2. **Find deterministically, edit with a model only where a rule cannot.** Locations come from detect rules (M3, M9); a transform that a rule can express (a renamed field, a renamed tool, a default) is an engine-shipped deterministic transform (M2); the model edits only the hits an entry marks as needing judgement (M3).
3. **Validate every model edit in a fixed order and drop what fails.** The order is: applies to the package, the package still loads, the hit is gone, validation passes, then the checks a person relies on (M4). A failed item is left for the person, never retried without bound (M4, M8).
4. **Questions only the owner can answer stay the owner's.** A new criterion, a judge brief that must say what the bar is, or a repository name is drafted for a person to accept, never decided by the model (M10). This keeps the reason against a model rewrite while taking the measured gain of M5.
5. **A person reviews the result before it lands** (M7); the upgrade's product is a branch and a report, not a changed installed copy.
6. **Record the gain honestly.** Report the share of items done by transform, by model and by person per upgrade, since public figures are partly estimates (M6).
7. **Run the old baseline first.** Pre-existing failures blocked validation in practice (M8), so the upgrade records what was already failing before it changes anything and judges its result against that baseline, not against an empty slate.

## Open questions

| Question | Owner |
|---|---|
| What share of real workflow upgrades will need the model at all? No tempergraph workflow has been upgraded yet; the first release with a breaking change will measure it (WUP report fields). | Implementer, after the first breaking release |
| Does a typed detect rule over the parsed workflow find everything a text pattern over code and prompts finds (M9, M11)? To be checked on the first breaking change. | Implementer |
