---
title: Prompt audit
type: component
status: review
prefix: PRA
adrs: [0054, 0051, 0016]
---

# Prompt audit

## 1. Overview

The part of the [workflow audit](55-workflow-audit.spec.md) that reads every piece of **model-facing text** a workflow sends and asks four questions of it: does everything it names exist, is anything it names out of date, does it agree with what the step declares and produces, and does it fit. [R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) found each of these costing runs: references to a skill, an agent, a prompt file and two tool names that did not exist (F7.2), newer tracker and wiki tool names the judge catalog did not know (F4.6), a step told to change directory before a command the CLI refuses (F4.2), a tracker tool the prompt relied on but the step was not granted (F4.4), and a whole plan written in one response that stalled for 52 minutes (F3.3).

Prompt lint ([LIF](18-lifecycle-and-evals.spec.md)) keeps the **text-style** rules, which need only the package: vague words, self-grading, rule-like branching, human-wait instructions, accepting briefs. This spec adds what prompt lint cannot see from the package alone: names resolved against the **executor, the view catalog and the installed plugins on this host**, staleness against the **last stamp**, consistency with the **step's declarations**, and, from history, the **rendered size** and how a prompt change moved its gate ([ADR-0054](../adr/0054-audit-joins-existing-checks-and-files-nothing.adr.md)).

## 2. Contract

### 2.1 What is model-facing text

| Source | Read for |
|---|---|
| Step template (inline or file) | step |
| Judge stance, brief, criteria text and `check_method` | judge (criteria text also step) |
| The engine's tools block for the step, as rendered ([PRM](04-prompt-rendering.spec.md)) | step |
| Lessons file entries ([LSN](42-workflow-lessons.spec.md)) | step |
| Skills, agents and instruction files a step names, from the workflow's authoring surface for that executor ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)) | step |

Each is read once; a file shared by several steps is reported once, with every step that uses it.

### 2.2 Names found

The reader is prompt lint's, so both agree on what a text names ([TSA](57-tool-surface-audit.spec.md) uses the same reader).

| Kind | Example | Resolved against |
|---|---|---|
| Tool name | `Bash`, `Grep`, `run_command`, `mcp__tracker__get_issue` | The step's executor `tool_map` and the view catalog |
| Command | `pytest -q`, `git -C . status` | Declared prefixes and `command_resolver` output |
| Skill or agent | `/plan-review`, agent `coder` | The workflow's authoring surface, then every installed plugin on the host |
| File or path | `docs/rules/plan.rule.md` | The package, then the target repository |
| Input or engine key | `{ticket}` | Owned by validation's template grammar |
| Artifact key | "write `plan.md`" | The step's `produces` and the judge's `references` |

### 2.3 Rules (family C7, with C3 and C4 links)

| id | layer | sev / conf | cause | Fires when | Remedy |
|---|---|---|---|---|---|
| `prompt-lint` | definition | per owner | per rule | Prompt lint's text-style findings | owner: [LIF](18-lifecycle-and-evals.spec.md) |
| `ref-missing` | definition | error / high | `ref_missing` *new* | A named skill, agent or file exists neither in the package nor, for files, in the target | Fix or remove the reference; the session wastes turns looking for it (F7.2) |
| `ref-resolves-elsewhere` | host | warning / high | `skill_clash` *new* | A named skill or agent is missing from the workflow's authoring surface but found in another installed plugin, or found in more than one | Ship it with the workflow or name it by plugin path (F4.8) |
| `tool-name-unknown` | host | error / high | `unknown_tool_name` | A tool name in the text is in neither the executor's current `tool_map` nor the view catalog | Use the capability's current name; the engine's tools block already names it |
| `tool-name-stale` | host | warning / high | `unknown_tool_name` | A tool name in the text is one the catalog or the executor's compatibility table marks renamed or retired, or was in the tool set recorded at the last stamp and is gone now | Replace it with the new name the finding gives (F4.6) |
| `prompt-tool-conflict` | definition | warning / high | `prompt_conflict` *new* | The text forbids a declared tool ("do not use the shell" with `shell` declared) or tells the step to use a tool or command it does not declare | Make the text and the declaration say the same; the engine's tools block is the source of truth |
| `skill-frontmatter-nonstandard` | definition | info / high | `skill_nonportable` *new* | A workflow skill declared by a step on an executor other than `claude` or `agent-sdk`, or named in `surfaces`, uses frontmatter beyond the six fields of the Agent Skills standard ([PKG §2.6](88-workflow-package.spec.md)) | Keep to `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`, or ship a second form |
| `artifact-not-asked` | definition | warning / medium | `prompt_conflict` *new* | A key in `produces` is never mentioned in the template, or the template asks for an output key that `produces` does not declare | Name each produced artifact in the template; declare what the text asks for |
| `criterion-not-in-reach` | definition | warning / medium | `prompt_conflict` *new* | A criterion names an artifact or system that is not in the judge's references or view set | Add the reference or view, or mark the system `unverified_system` |
| `one-shot-long-output` | definition | warning / low | `long_response` *new* | The template asks for a whole long document in one answer (one `file` artifact and words such as "write the whole", "complete plan") with no instruction to write it in parts | Write a skeleton, then one edit per part (F3.3) |
| `rendered-near-cut` | history | warning / high | `missing_input` *new* | A recorded rendered prompt or request was cut by the renderer's limit in any run | Narrow what the step is given; a cut criterion fails three attempts (F1.5) |
| `prompt-change-moved-gate` | history | per owner | — | After a change of a template's digest, the gate's first-pass yield fell | owner: the post-release watch of [SIL](16-self-improvement.spec.md) and [PRP](40-improvement-proposals.spec.md); shown here with the digest dates |

Missing tools that a prompt asks for are reported once, by `needed-not-granted` and `artifact-needs-write` in [TSA §2.4](57-tool-surface-audit.spec.md); this spec does not report them again.

### 2.4 `audit prompts`

`audit prompts <workflow>` prints one row per model-facing file instead of findings:

| Column | Values |
|---|---|
| File | Package path, or `inline:<unit>` |
| Used by | Units and roles |
| Size | Characters, rendered size with the start examples |
| Names | Found / unresolved / stale |
| Findings | Count by severity, prompt lint included |
| Changed | Version of the last digest change, and the gate's first-pass yield before and after (history) |

## 3. Behaviours

**PRA-B1 A renamed tool.** Given a step on `claude` whose template says "use `mcp__wiki__get_page`" and a view catalog that lists that name as renamed to `mcp__wiki__getConfluencePage`, when the host layer runs, then `tool-name-stale` fires with both names, and `mcp-tool-not-in-catalog` in TSA fires only if the declaration also uses the old name.

**PRA-B2 A skill from another plugin.** Given a template that names skill `plan-review`, which the workflow does not ship and two installed plugins do, when the host layer runs, then `ref-resolves-elsewhere` fires naming both plugins.

**PRA-B3 Text against declaration.** Given a step that declares `shell` with prefix `pytest` and a template that says "never run commands", when the definition layer runs, then `prompt-tool-conflict` fires once, citing the sentence's file and line.

| Template says | Declared | Finding |
|---|---|---|
| "never run commands" | `shell`, `pytest` | `prompt-tool-conflict` |
| "run `npm test`" | `shell`, `pytest` | `needed-not-granted` (TSA), not this spec |
| "use Grep to search" | `search` on `claude` | none |
| "use Grep to search" | `search` on `antigravity` | `tool-name-unknown` (the name is not in that executor's map) |

**PRA-B4 No double count.** Given a prompt that names an undeclared tool, when the audit runs, then the finding appears once, under its owner, whichever of prompt lint, WFM and TSA owns it.

## 4. Error conditions

| Condition | Result |
|---|---|
| A named file cannot be read | `ref-missing` with reason `unreadable`, not `absent` |
| No authoring surface for the step's executor | Skill and agent rules skipped with that reason; WFM's warning stands |
| No start examples to render with | `prompt-oversized` uses the template without inputs and says so |

## 5. Design notes

- **Names, not meaning.** Every rule here resolves a name or measures a size; none judges whether the text is good. That stays with prompt lint's fixed rules, the judge readiness report and, if the owner wants one later, a model-assisted review outside this verb (AUD open question).
- **Staleness needs a baseline.** A tool is "outdated" only against something: the catalog's rename table, the executor's compatibility table, or the tool set recorded when the workflow was last stamped ([LIF](18-lifecycle-and-evals.spec.md)). The audit never guesses from a name's shape.
- **Executor-specific names in a portable workflow.** Templates should name capabilities through the engine's tools block; a hard-coded executor tool name makes the prompt wrong on the other executors, which `tool-name-unknown` shows when audited with `--executor`.

## 6. Acceptance criteria

- [ ] PRA-AC-1 Every rule in §2.3 has a fixture that raises it and a clean fixture that does not.
- [ ] PRA-AC-2 PRA-B3's table holds as a table test across the four executors' `tool_map`s.
- [ ] PRA-AC-3 The name reader is shared with prompt lint and TSA (one function, source test).
- [ ] PRA-AC-4 No finding is reported twice across prompt lint, WFM, TSA and this spec on a fixture built to raise each once.

## Open questions

| Question | Owner |
|---|---|
| Should the catalog's rename table be filled from executor release notes by hand, or from a probe that lists tool names per version? | Executor implementer |

## References

[AUD](55-workflow-audit.spec.md) · [TSA](57-tool-surface-audit.spec.md) · [ARC](56-audit-rule-catalog.spec.md) · [LIF](18-lifecycle-and-evals.spec.md) · [PRM](04-prompt-rendering.spec.md) · [R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md)
