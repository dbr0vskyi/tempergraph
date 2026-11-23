# Prompt audit

## Purpose

The part of the [workflow audit](55-workflow-audit.spec.md) that reads every piece of model-facing text a workflow sends and asks four questions of it: does everything it names exist, is anything it names out of date, does it agree with what the step declares and produces, and does it fit. [R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) found each costing runs: references to a skill, an agent, a prompt file and two tool names that did not exist (F7.2), newer tracker and wiki tool names the judge catalog did not know (F4.6), a step told to change directory before a command the CLI refuses (F4.2), a tracker tool the prompt relied on but the step was not granted (F4.4), and a whole plan written in one response that stalled (F3.3). Prompt lint ([LIF-B12](18-lifecycle-and-evals.spec.md)) keeps the text-style rules that need only the package; this spec adds names resolved against the executor, the view catalog and the installed plugins on this host, staleness against the last stamp, consistency with the step's declarations, and from history the rendered size and how a prompt change moved its gate ([ADR-0054](../adr/0054-audit-joins-existing-checks-and-files-nothing.adr.md)). Every rule resolves a name or measures a size; none judges whether the text is good, and staleness is only ever measured against a recorded baseline, never guessed from a name's shape. Workflow authors and the audit depend on it.

## Behaviours

### PRA-B5 Model-facing text

WHEN the audit reads a workflow THE audit SHALL read once each of the step templates (inline or file), the judge stances, briefs, criteria text and `check_method`s (criteria text also for the step), the engine's tools block as rendered ([PRM](04-prompt-rendering.spec.md)), the lessons entries ([LSN](42-workflow-lessons.spec.md)) and the skills, agents and instruction files a step names from the workflow's authoring surface for that executor ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)), reporting a file shared by several steps once with every step that uses it, and skipping the skill and agent rules with that reason when a step's executor has no authoring surface.

- GIVEN one brief shared by two judges WHEN audited THEN its findings are reported once naming both

### PRA-B6 Names found

WHEN the audit reads a text THE audit SHALL use prompt lint's name reader, shared with [TSA](57-tool-surface-audit.spec.md), and resolve tool names (`Bash`, `run_command`, `mcp__tracker__get_issue`) against the step's executor tool map and the view catalog, commands against declared prefixes and resolver output, skills and agents against the workflow's authoring surface then every installed plugin on the host, files and paths against the package then the target repository, artifact keys against the step's `produces` and the judge's `references`, and leave input and engine keys to validation's template grammar.

- GIVEN `{ticket}` in a template WHEN read THEN the audit leaves it to validation

### PRA-B7 Reference rules

WHEN references are resolved THE audit SHALL render `prompt-lint` findings from prompt lint, render `ref-missing` (error/high, `ref_missing`) from prompt lint's `lint-ref-missing` for package paths under `prompts/`, `judges/`, `skills/`, `agents/` or `lessons/`, with reason `unreadable` rather than `absent` for a file that cannot be read (F7.2), and fire `ref-resolves-elsewhere` (host, warning/high, `skill_clash`) when a named skill or agent is missing from the workflow's authoring surface but found in another installed plugin (reading `skills/*/SKILL.md` of the newest non-orphaned version of each plugin in Claude Code's plugin cache), or in more than one, a name given as `plugin:skill` that matches being resolved (F4.8).

- GIVEN a named file that cannot be read WHEN audited THEN `ref-missing` gives reason `unreadable`

### PRA-B2 A skill from another plugin

WHEN the host layer runs on a template naming skill `plan-review`, which the workflow does not ship and two installed plugins do THE audit SHALL fire `ref-resolves-elsewhere` naming both plugins.

- GIVEN two plugins shipping `plan-review` WHEN audited THEN the finding names both

### PRA-B8 Tool name rules

WHEN tool names are resolved THE audit SHALL render `tool-name-unknown` (host, error/high, `unknown_tool_name`) from prompt lint's `lint-tool-name-foreign` for a name in neither the executor's current tool map nor the view catalog, skipping it for MCP names until the view catalog exists, and fire `tool-name-stale` (host, warning/high, `unknown_tool_name`) for a name the catalog or the executor's compatibility table (an optional `renamed` map per executor) marks renamed or retired, or that was in the `tool_set` of the last `stamp.json` and is gone now, giving the new name (F4.6), skipped when neither baseline exists; a hard-coded executor tool name in a portable workflow shows up when audited with `--executor`.

- GIVEN no stamp and no rename map WHEN audited THEN `tool-name-stale` is skipped with its reason

### PRA-B1 A renamed tool

WHEN the host layer runs for a step on `claude` whose template says "use `mcp__wiki__get_page`" and a view catalog that lists it as renamed to `mcp__wiki__getConfluencePage` THE audit SHALL fire `tool-name-stale` with both names, TSA's `mcp-tool-not-in-catalog` firing only if the declaration also uses the old name.

- GIVEN that rename WHEN audited THEN `tool-name-stale` names both

### PRA-B9 Consistency rules

WHEN the definition layer runs THE audit SHALL fire `prompt-tool-conflict` (warning/high, `prompt_conflict`) when the text forbids a declared shell, edit, write, web fetch or web search tool, citing the sentence's file and line, the half "tells the step to use a tool it does not declare" being TSA's `needed-not-granted`; `skill-frontmatter-nonstandard` (info/high, `skill_nonportable`) when a workflow skill declared by a step on an executor other than `claude` or `agent-sdk`, or named in `surfaces`, uses frontmatter beyond `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools` ([PKG](88-workflow-package.spec.md)); `artifact-not-asked` (warning/medium, `prompt_conflict`) when a key in `produces` is never named in the template (a default template not read); and `criterion-not-in-reach` (warning/medium, `prompt_conflict`) when a criterion backticks an artifact key another unit produces that the judge neither references nor has as subject.

- GIVEN a `produces` key never named in the template WHEN audited THEN `artifact-not-asked` fires

### PRA-B3 Text against declaration

WHEN the definition layer runs on a step that declares `shell` with prefix `pytest` and a template that says "never run commands" THE audit SHALL fire `prompt-tool-conflict` once, citing the sentence's file and line.

- GIVEN "run `npm test`" with `shell` and `pytest` declared WHEN audited THEN TSA's `needed-not-granted` reports it, not this spec
- GIVEN "use Grep to search" with `search` on `claude` WHEN audited THEN nothing fires
- GIVEN "use Grep to search" with `search` on `antigravity` WHEN audited THEN `tool-name-unknown` fires

### PRA-B10 Size rules

WHEN sizes are measured THE audit SHALL fire `one-shot-long-output` (warning/low, `long_response`) when a template asks for a whole long document in one answer (one `file` artifact and words such as "write the whole" or "complete plan") with no instruction to write it in parts (F3.3); render `prompt-oversized` (warning/high, `prompt_size`) from prompt lint's `lint-oversized` (a rendered template over 32,000 characters, a skill or agent file over 40,000, a table cell over 2,000), measuring the template without inputs and saying so when there are no start examples; fire `rendered-near-cut` (history, warning/high, `missing_input`) when a recorded rendered prompt or request was cut by the renderer's limit (F1.5); and render `prompt-change-moved-gate` from the post-release watch of [SIL](16-self-improvement.spec.md) and [PRP](40-improvement-proposals.spec.md) with the digest dates.

- GIVEN "write the whole plan" with one `file` artifact WHEN audited THEN `one-shot-long-output` fires

### PRA-B4 No double count

WHEN a prompt names an undeclared tool THE audit SHALL report the finding once under its owner, whichever of prompt lint, validation and TSA owns it, missing tools being reported only by TSA's `needed-not-granted` and `artifact-needs-write`.

- GIVEN a fixture built to raise each owner's finding once WHEN audited THEN no finding appears twice

### PRA-B11 The prompts matrix

WHEN `audit prompts <workflow>` runs THE audit SHALL print JSON rows instead of findings, one per model-facing file, with `file` (package path or `inline:<unit>`), `used_by` (units and roles), `size` (characters and rendered size with the start examples), `names` (found, unresolved, stale), `findings` (count by severity, prompt lint included) and `changed` (the version of the last digest change with the gate's first-pass yield before and after, `not recorded` without history).

- GIVEN a new workflow WHEN `audit prompts` runs THEN `changed` reads `not recorded`

## Acceptance criteria

- PRA-AC1 (PRA-B7, PRA-B8, PRA-B9, PRA-B10): Every prompt-audit rule has a fixture that raises it and a clean fixture that does not
- PRA-AC2 (PRA-B3): PRA-B3's scenarios hold as a table test across the four executors' tool maps
- PRA-AC3 (PRA-B6): The name reader is shared with prompt lint and TSA, one function, by a source test
- PRA-AC4 (PRA-B4): No finding is reported twice across prompt lint, validation, TSA and this spec on a fixture built to raise each once
- PRA-AC5 (PRA-B1, PRA-B2, PRA-B5, PRA-B11): Fixtures cover a renamed tool, a skill in two plugins, a shared file reported once and the prompts matrix

## Open questions

- Should the catalog's rename table be filled from executor release notes by hand, or from a probe that lists tool names per version? Owner: executor implementer.
