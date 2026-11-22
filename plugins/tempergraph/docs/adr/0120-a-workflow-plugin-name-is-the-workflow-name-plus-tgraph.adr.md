# ADR-0120 A workflow plugin's name is the workflow name plus `-tgraph`

| | |
|---|---|
| Status | accepted |
| Date | 2026-11-20 |
| Authors | Claude (build session for the owner) |
| Supersedes | — |

## Context

A workflow package is a Claude Code plugin ([ADR-0105](0105-a-workflow-package-is-one-claude-plugin-with-a-python-part-and-a-docs-set.adr.md)). In a plugin list, a marketplace or a `skill:<plugin>:<name>` reference, nothing told a person that a plugin is a tempergraph workflow rather than an ordinary plugin. The owner asked for a naming agreement so a tempergraph workflow is recognisable by name (2026-11-20), considered `.tgflow` and `-tg-graph`, and decided on the suffix `-tgraph`, for example `release-notes-tgraph`.

Until now [PKG-B13](../specs/88-workflow-package.spec.md) required one name in three places: `plugin.json` `name`, `tempergraph.json` `name` and the built `WorkflowSpec.name`. The workflow name is also what `tempergraph run` takes, the registry key, the run folder name and the `tgwf-<name>` distribution and private module name.

Claude Code's plugin rules (code.claude.com plugins reference, marketplace reference, checked 2026-11-20): a plugin name has no spaces, `@`, `:` or path separators and should be kebab-case (`claude plugin validate --strict` fails otherwise); the prefixes `claude-`, `anthropic-`, `anthropics-` and `cc-plugin-` are reserved; the plugin name is part of namespaced skill and MCP tool names, which are capped at 64 characters overall. A `.` suffix such as `.tgflow` is not kebab-case.

## Decision

We will name every workflow package's plugin `<workflow name>-tgraph`, and keep the workflow name itself short.

- `tempergraph.json` `name` is the **workflow name** (`release-notes`): what `run` takes, the registry key, the run folder, `tgwf-<name>`.
- `plugin.json` `name` is the **plugin name**, always the workflow name plus `-tgraph` (`release-notes-tgraph`). It is derived, never chosen: loading refuses any other value with `plugin-name-suffix` (`not_loaded: manifest`), naming the expected name.
- A workflow name is kebab-case, does not itself end in `-tgraph`, does not start with a reserved prefix, and is at most 57 characters so the plugin name stays within 64.
- The CLI accepts the plugin name wherever it takes a workflow name: `tempergraph run release-notes-tgraph …` runs `release-notes`.
- `skill:` capabilities keep Claude Code's namespace, which is the plugin name: `skill:release-notes-tgraph:<skill>`.
- The scaffold writes both names; a blueprint `name` ending in `-tgraph` is refused, with the short name as the remedy.
- The engine plugin `tempergraph` and the monitor `tempergraph-monitor` are not workflow packages and keep their names. temperspec, once packaged as a workflow ([PKG-B8](../specs/88-workflow-package.spec.md)), is `temperspec-tgraph`.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Suffix `-tgraph` on the plugin name only (chosen) | Recognisable in every plugin list; kebab-case; run ids stay short | Two names to explain; the plugin name is derived, so it cannot drift |
| Suffix `.tgflow` | Reads like a file type | Not kebab-case: `claude plugin validate --strict` fails; `.` is unusual in plugin and skill namespaces |
| Suffix `-tg-graph` | Kebab-case | Longer, and "tg" plus "graph" repeats the owner's own short form `tgraph` |
| One name everywhere, suffixed (`run release-notes-tgraph`) | One field | Every run id, folder, thread id and `tgwf-` name carries a suffix that says nothing inside the engine, where everything is a workflow |
| A `keywords` entry or a prefix | No rename | A keyword is not visible in a name; a prefix sorts every workflow together but hides what it does behind the brand |

## Decision rationale

| Criterion | `-tgraph` plugin only | `.tgflow` | `-tg-graph` | Suffix everywhere |
|---|---|---|---|---|
| Recognisable in a plugin list | yes | yes | yes | yes |
| Passes `claude plugin validate --strict` | yes | no | yes | yes |
| Short names inside the engine | yes | yes | yes | no |
| Owner's choice | yes | considered | considered | — |

## Consequences

- Positive: any plugin ending in `-tgraph` is a tempergraph workflow; a package that breaks the rule cannot load, so the convention cannot erode.
- Negative: packages written before this decision fail to load until `plugin.json` `name` is renamed (no release has shipped, so only the examples in progress are affected).
- Risk: a person types the plugin name where a workflow name is expected. Mitigation: the CLI strips the suffix, and every refusal shows the expected name.
