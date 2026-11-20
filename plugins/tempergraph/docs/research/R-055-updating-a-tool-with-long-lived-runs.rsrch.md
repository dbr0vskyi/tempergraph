# R-055 Updating a tool whose runs outlive a release

## Problem statement

The owner asked for a command that updates the engine, one part of which is updating the CLI installation. tempergraph is delivered as a Claude Code plugin whose skills drive a CLI installed in a managed Python environment ([LIF](../specs/18-lifecycle-and-evals.spec.md)), and its runs are durable: a run may sit at a pause for days ([DUR](../specs/09-durability-and-resume.spec.md)), an orchestration supervises many runs for hours ([ORC](../specs/45-orchestration.spec.md)), and every repository keeps a versioned store ([LOS](../specs/33-local-observability-store.spec.md)). This note asks how the parts tempergraph depends on update, and how comparable systems treat work that is in flight when the code under it changes. It informs [UPD](../specs/60-engine-update.spec.md), [MIG](../specs/62-state-and-run-migration.spec.md), [ADR-0055](../adr/0055-side-by-side-engine-environments-switched-atomically.adr.md) and [ADR-0056](../adr/0056-threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them.adr.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Claude Code plugin docs: CLI reference, plugin loading, hosting a marketplace, manifest reference, dependencies | Official docs (read 2026-11-20) | https://code.claude.com/docs/en/plugins/cli-reference.md, …/loading.md, …/host-marketplace.md, …/manifest-reference.md, …/dependencies.md |
| LangGraph backward compatibility | Official docs | https://docs.langchain.com/oss/python/langgraph/backward-compatibility |
| Temporal Worker Versioning | Official docs | https://docs.temporal.io/worker-versioning |
| uv tools concept page; pipx CLI reference | Official docs (search results, not read in full) | https://docs.astral.sh/uv/concepts/tools/, https://pipx.pypa.io/latest/reference/cli/ |

The uv and pipx pages were seen only as search results; nothing below rests on them alone.

## Key findings

### Claude Code plugins

| # | Finding | Confidence |
|---|---|---|
| U1 | A marketplace plugin is updated with `claude plugin update <plugin>[@marketplace]` (with `--json`) or in a session through `/plugin`; marketplaces are refreshed with `claude plugin marketplace update`. The new version loads in the next session or after `/reload-plugins`. | supported (CLI reference, loading page; their wording differs slightly) |
| U2 | Auto-update refreshes marketplaces in the background after a session starts; it is on by default for official marketplaces and off for third-party ones, and can be switched per marketplace or off by environment variables. | supported (loading, host-marketplace pages) |
| U3 | A plugin's version string is its **cache key**: an installed copy is refreshed only when the version changes; a plugin that changes content without a version bump keeps the old cached copy. A plugin loaded in place from a local-path marketplace reads current files instead. | supported (loading, host-marketplace pages) |
| U4 | Copies live at `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`; `${CLAUDE_PLUGIN_ROOT}` points at that version folder and **changes with every version**; an old folder is marked orphaned and removed 14 days later. A running session keeps the old path until reload. | supported (loading, manifest reference) |
| U5 | `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/<id>/`) **survives updates** and is removed on uninstall unless kept. | supported (manifest reference) |
| U6 | A plugin may declare `dependencies` on other plugins with a semver range; conflicting ranges fail the install. No plugin-level minimum Claude Code version field was found. | supported (dependencies page); the minimum-version point `uncertain` |
| U7 | No documented pattern exists for a plugin to detect its own update; a session-start hook comparing the plugin's version with a value kept in its data folder is a design choice, not a documented feature. | supported (absence in the docs read) |

### Python tool environments

| # | Finding | Confidence |
|---|---|---|
| U8 | A managed environment kept outside the plugin cache is not deleted by a plugin update (U4, U5), and only the engine's own update verb, code from the package invoked, changes it: it can install from a staged copy, decide currency by a content hash and refuse a downgrade. | inferred |
| U9 | An updater that loads none of the engine's compiled libraries keeps Windows from locking them while the installer replaces them; an installer that replaces an environment in place and is killed part-way leaves it half-installed. | inferred |
| U10 | Same-version-different-code happened: an installed copy was 18 files behind the repository under the same version string. | confirmed (earlier runs) |
| U11 | Update output written as prose is ambiguous to a skill that parses it, and a skill that matches on its last line breaks when the wording changes; a machine-readable form removes both. | inferred |

### Work in flight

| # | Finding | Confidence |
|---|---|---|
| U12 | LangGraph "applies the latest graph immediately to every thread", including threads resumed from a checkpoint; it does not pin a run to the code that started it. | supported (LangGraph docs) |
| U13 | For checkpointed or interrupted threads, renaming or removing a **node** breaks them ("LangGraph cannot find the node by its saved name"), as does renaming or removing a state key old checkpoints hold, or tightening a field. Adding, removing or rerouting **edges** between nodes that still exist is safe, because edges are not in the checkpoint. | supported (LangGraph docs) |
| U14 | LangGraph recommends new state fields as optional, removals kept for at least one drain cycle, renames as add-then-remove, and a version stamped **at thread start** for business-level branching. | supported (LangGraph docs) |
| U15 | Temporal offers two behaviours per workflow: **Pinned** ("guaranteed to complete on a single Worker Deployment Version") and **Auto-Upgrade** (moves to the new current version, and must be kept replay-safe by hand). A version no longer current that still has pinned runs is **draining**; it is **drained** when they have all closed, and then may be retired. | supported (Temporal docs) |
| U16 | In Temporal, pinned parents pass the pin to children; auto-upgrade workflows never pass one on. | supported (Temporal docs) |
| U17 | Checkpoint databases written by older engines are kept as fixtures and resumed in tests, for every thread state. | supported ([DUR-B6](../specs/09-durability-and-resume.spec.md)) |

## Conclusions

1. **The plugin and the engine update by different mechanisms and must be told apart.** Claude Code updates the plugin (U1, U2); only the engine's own verb updates the managed environment (U8). The plugin's skills therefore check, at session start or before a run, whether the engine they ship matches the one installed, and hand over to the verb.
2. **Keep durable state outside every versioned folder.** The plugin folder changes with every version and old ones are deleted (U4); the engine environment, the home folder and the state roots live outside it (U5, U8). A workflow package path that points into the plugin cache goes stale on every update, which is why the manifest is reconciled.
3. **Release hygiene stays a check.** Because the cache is keyed by the version string (U3, U10), a package whose content changed without a version bump must fail a repository check; currency on the machine stays a content hash.
4. **Install beside, then switch.** Replacing an environment in place is what leaves it half-installed and what Windows file locks break (U9). Installing a new environment beside the old one and switching a pointer at the end gives an atomic update, a rollback and a place for running processes to keep their code.
5. **A durable run resumes on the newest code by default, and is pinned only when the state would break.** LangGraph's own model is auto-upgrade (U12), and edges are safe while node names and state keys are kept (U13). Temporal shows the other half: when a run cannot move, it completes on the version it started on, and that version drains before it is retired (U15). tempergraph's unit of resume is a fresh process at a checkpoint, a natural point to move a thread forward.
6. **What breaks a paused thread is known.** A removed or renamed unit that a thread is paused at or routed to, a removed state key, or a tightened field (U13). Both an engine release and a workflow edit can cause it, so the same compatibility test serves both.
7. **Stamp the versions at thread start and at every resume** (U14), so a report can tell which engine and which workflow content each attempt ran on.
8. **Children follow the parent's engine within one supervising process** (U16): an orchestration or batch started on one engine finishes its current process on it.
9. **Machine-readable update output first** (U11): one JSON object per line, so skills stop parsing prose.

## Open questions

| Question | Owner |
|---|---|
| Does `claude plugin update --json` report the old and new version in a form a skill can read? The design uses only the plugin's own manifest, read from disk. | Implementer (probe on the first release) |
