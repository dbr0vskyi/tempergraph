# R-105 Workflow packages, authoring and the run-level good outcome: plugin format, prior art and gaps

## Problem statement

The readiness review found three designs missing before workflow creation can be built ([R-090](R-090-implementation-readiness.rsrch.md) D1 to D3, from [R-011](R-011-design-gap-review.rsrch.md) G1 to G3): the workflow package and its declaration format, the authoring contract, and a run-level definition of a good outcome. On 2026-11-20 the owner gave the direction for all three:

> When we're creating a workflow it should create for us a Claude plugin with prompts, agents and skills specific to the workflow and executable Python code for the engine itself. The run-level good outcome should be defined during workflow authoring and further improved. The user provides an existing solution, references, sources, or simply chats about it from scratch. Our workflow authoring should focus on the definition of a good outcome and on finding or creating (including intermediate) verifiable outcomes and criteria.

and, a minute later:

> The workflow plugin should also have specs in the same way as the engine. Going further we will improve the format and rules based on temperspec, which is not created yet.

This note answers four questions: (1) what the current Claude Code plugin format allows a workflow package to be, and how its parts reach the four executors; (2) what public practice says about defining outcomes and criteria and finding verifications for them; (3) what an authoring path needs and what the design already decided; (4) which gaps remain and which document closes each. The work was done standalone, without questions to the owner; assumptions are recorded in the decision records [ADR-0105](../adr/0105-a-workflow-package-is-one-claude-plugin.adr.md) to [ADR-0114](../adr/0114-judged-criteria-carry-a-scale-and-authoring-guides-to-clarity.adr.md).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S1 | Claude Code plugins reference: manifest fields, standard layout, `bin/`, environment variables, dependencies, component path rules | Official docs, fetched 2026-11-20 | https://code.claude.com/docs/en/plugins/manifest-reference.md |
| S2 | Claude Code plugin loading: `--plugin-dir`, how the version is computed, cache path, auto-update, Node dependencies, no Python dependency support | Official docs, fetched 2026-11-20 | https://code.claude.com/docs/en/plugins/loading.md |
| S3 | Claude Code plugin marketplaces: entry fields, `strict`, source kinds, pinning | Official docs, fetched 2026-11-20 | https://code.claude.com/docs/en/plugins/marketplace-reference.md |
| S4 | Claude Code skills (frontmatter, namespacing) and subagents (frontmatter, fields ignored for plugin agents) | Official docs, fetched 2026-11-20 | https://code.claude.com/docs/en/skills.md , https://code.claude.com/docs/en/sub-agents.md |
| S5 | Agent Skills specification (six frontmatter fields) | Open standard | https://agentskills.io/specification |
| S6 | Claude Agent SDK plugins (`plugins=[{"type": "local", "path": …}]`) | Official docs, fetched 2026-11-20 | https://code.claude.com/docs/en/agent-sdk/plugins.md |
| S7 | Claude API skills guide (`container.skills`, code execution tool, upload limits) | Official docs, fetched 2026-11-20 | https://platform.claude.com/docs/en/build-with-claude/skills-guide |
| S8 | Antigravity skills (`.agents/skills/`, `~/.gemini/config/skills/`, plugins folder for the CLI) | Vendor docs, fetched 2026-11-20 | https://antigravity.google/docs/skills.md |
| S9 | Shankar et al., "Who Validates the Validators? Aligning LLM-Assisted Evaluation of LLM Outputs with Human Preferences" (UIST 2024) | Paper | https://arxiv.org/abs/2404.12272 |
| S10 | promptfoo: deterministic assertions and model-graded assertions (`llm-rubric`) | Tool docs | https://promptfoo.dev/docs/configuration/expected-outputs/deterministic , https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded |
| S11 | Inspect AI: a task is a dataset, a solver and a scorer | Tool docs | https://inspect.aisi.org.uk/tasks.html |
| S12 | Wiggins and McTighe, *Understanding by Design*: backward design in three stages (desired results, acceptable evidence, then the plan) | Method, summarised by a teaching centre | https://cft.vanderbilt.edu/?p=984 |
| S15 | This design on `main` after PR 13: WFM, CON-B4, CON-B5, CON-B6, CON-B7, SHL-B9, VER, UPD-B20 to UPD-B24, SIL, PRP, FBK, JCL, EVS, SUP, AUD, ADR-0016, ADR-0078, R-075 | Design set | [specs](../specs/overview.spec.md) |

## Key findings

### A. The Claude Code plugin format today

| # | Finding | Confidence |
|---|---|---|
| A1 | The manifest `.claude-plugin/plugin.json` is optional and only `name` is required (kebab-case, no `:`, `@`, spaces or path separators). Other fields include `version`, `description`, `author`, `homepage`, `repository`, `license`, `keywords`, `dependencies` and component paths (`skills`, `commands`, `agents`, `hooks`, `mcpServers`, …). Unknown top-level keys are stripped with a validation warning (S1). So engine metadata cannot live in `plugin.json`; it needs its own file. | confirmed |
| A2 | Everything but the manifest sits at the plugin root: `skills/<name>/SKILL.md`, `agents/*.md`, `commands/` (kept, skills preferred), `hooks/hooks.json`, `.mcp.json`, `settings.json`, `bin/`. A `CLAUDE.md` at the plugin root is not loaded as context (S1). | confirmed |
| A3 | `${CLAUDE_PLUGIN_ROOT}` is the installed version's folder and changes on every update; `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/<id>/`) survives updates (S1). The cache is `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` (S2). This matches the registry's repoint rule ([UPD-B20 to UPD-B24](../specs/engine-update.spec.md)). | confirmed |
| A4 | Claude Code installs Node dependencies of a plugin (a `package.json` with a lockfile) into the cache with scripts off; it does **not** install Python dependencies (S2). The engine must install a workflow's Python requirements itself, as UPD-B20 to UPD-B24 already says. | confirmed |
| A5 | The version is `plugin.json`'s `version`, else the marketplace entry's, else a source-derived value (a 12-character commit id for git sources). A set version pins the plugin until it changes (S2). This confirms VER's `version-not-bumped` warning. | confirmed |
| A6 | Plugin skills are invoked as `/<plugin>:<skill>` (S4). A skill's `SKILL.md` frontmatter has six fields in the open standard (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`); Claude Code adds more (`when_to_use`, `disable-model-invocation`, `user-invocable`, `model`, `context: fork`, `agent`, `hooks`, …). The Skills API and claude.ai reject unknown keys (S4, S5). A skill that must also run on the API or on Antigravity keeps to the six standard fields. | confirmed |
| A7 | Subagents in `agents/*.md` need `name` and `description`; for agents shipped by a plugin, `hooks`, `mcpServers` and `permissionMode` are ignored for security (S4). A workflow agent therefore cannot widen its own permissions. | confirmed |
| A8 | `claude --plugin-dir <path>` loads a plugin from a folder for one session (S1, S2). The Agent SDK loads a local plugin through `plugins=[{"type": "local", "path": …}]`, with its skills, agents, hooks and commands; it does not resolve marketplace names and skips a missing path silently, reporting loaded plugins in the init message (S6). | confirmed |
| A9 | The Messages API runs custom **skills** (uploaded folders with a `SKILL.md`, at most 20 per request) only inside the code-execution tool (S7). It has no notion of a plugin, agents or hooks. | supported |
| A10 | Antigravity reads skills (a folder with `SKILL.md`, `description` required) from `<root>/.agents/skills/`, from `~/.gemini/config/skills/`, and, for the CLI, from `~/.gemini/config/plugins/<plugin>/skills/` (S8). Its docs link the Agent Skills standard; full conformance is not stated. | supported |
| A11 | A plugin may declare other plugins as `dependencies` (S1). A workflow plugin can name `tempergraph` as a dependency so that installing the workflow brings the engine plugin. | supported |

### B. Public practice on outcomes, criteria and verification

| # | Finding | Confidence |
|---|---|---|
| B1 | Backward design starts from the desired result, then fixes the acceptable evidence that the result was reached, and only then plans the activities (S12). The authoring interview in the owner's direction is the same order: good outcome, then verifiable evidence per step, then the steps' work. | supported |
| B2 | People define evaluation criteria better after grading outputs than before: **criteria drift**. Some criteria only appear once outputs are seen, and criteria are revised while grading (S9). A good outcome written once at authoring is therefore a first version that must change with graded runs; tooling should make that change cheap and recorded. | supported |
| B3 | Graders that a person helped select and align, and whose agreement with the person's grades is measured, are trusted more than graders taken as written (S9). The engine already holds this: judges are accepted on labelled cases ([JCL](../specs/judge-calibration.spec.md)). | supported |
| B4 | Evaluation tools separate deterministic assertions (contains, regex, JSON shape, a script's result) from model-graded ones (a rubric graded by a model) and recommend the deterministic kind where it can express the requirement (S10). | supported |
| B5 | An evaluation is a dataset of cases, a solver that produces output, and a scorer that grades it (S11). A workflow package with its case set, its steps and its gates has the same parts; the authoring session can produce the first cases from the person's examples. | supported |

### C. What authoring needs and what the design already decided

| # | Finding | Confidence |
|---|---|---|
| C1 | An authoring path needs phases (intake, outcome, steps, criteria and judges, policies and models, start and routing, blueprint, scaffold, verify and stamp), a rule that nothing is written before the engine-drawn blueprint is approved, a requirement-shape table (check, git check, test command, judged, outside system, not observable), a blueprint comparison, a literal check and a calibration set. None of it has a tempergraph spec; SHL-B9 lists the phases only (S15). | confirmed |
| C2 | The authoring "outcome" phase records a goal and a deliverable but produces nothing a gate reads (R-011 G1). The outcome lens of self-improvement asks "did the result meet the request" with no declared bar ([SIL-B10](../specs/self-improvement.spec.md)). | confirmed |
| C3 | The authoring phases assume a process the person already runs and one or two real examples to build from. Material of other kinds (a template, a Definition of Ready) can serve as a start as well, and a conversation from scratch is not described. | inferred |
| C4 | The design already fixes: workflows as data and a registry ([ADR-0003](../adr/0003-workflows-as-data.adr.md), [UPD-B20 to UPD-B24](../specs/engine-update.spec.md)); the check contract ([CHK](../specs/check-contract-and-command-runs.spec.md)); version fields, digest and stamp ([VER](../specs/version-metadata.spec.md)); skills as a declared capability by plugin path ([ADR-0078](../adr/0078-skills-are-a-declared-tool-capability.adr.md)); per-executor authoring surfaces ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)); grader-side changes and person-only weakening ([ADR-0031](../adr/0031-steps-and-their-graders-change-apart.adr.md)); the audit ([AUD](../specs/workflow-audit.spec.md)); eval suites and the grader order ([EVS](../specs/eval-suites.spec.md)); supervision levels ([SUP](../specs/supervision-metrics.spec.md)). | confirmed |
| C5 | temperspec is the first real package: steps triage, discovery, plan, expand, a mapped phase step, code, release, and a finalizer; agents for architecture, planning and coding; skills for spec authoring, decision records and test fixing; rule sets per artifact type; nine mechanical criteria ([R-075](R-075-temperspec-needs-against-the-engine.rsrch.md)). Its run-level good outcome is a draft pull request whose code meets the task's acceptance criteria with passing tests. | confirmed |
| C6 | The engine's own docs follow research → decision → spec → plan → code with type-suffixed files ([docs README](../README.md), [ADR-0017](../adr/0017-artifact-type-suffixes.adr.md)). The monitor plugin already keeps its own design set in the same shape ([monitor docs](../../../tempergraph-monitor/docs/specs/overview.spec.md)). | confirmed |

### D. Gaps

| # | Gap | Closed by | Confidence |
|---|---|---|---|
| D1 | No package layout: how the plugin half (skills, agents, prompts), the Python half and the docs half sit in one folder, which file tells the engine where the declaration is, how Python requirements are declared | [PKG](../specs/workflow-package.spec.md), [ADR-0105](../adr/0105-a-workflow-package-is-one-claude-plugin.adr.md) | confirmed |
| D2 | No declaration format: builders, how text files and callables are referenced, the callable signatures not yet fixed (route, resolver, command resolver) | [PKG-B19, PKG-B20](../specs/workflow-package.spec.md), [ADR-0106](../adr/0106-declare-workflows-with-typed-python-builders-and-text-in-files.adr.md) | confirmed |
| D3 | No rule for what of a workflow plugin reaches each executor, given A6 to A10 | [PKG-B23, PKG-B24](../specs/workflow-package.spec.md), [ADR-0112](../adr/0112-plugin-content-reaches-each-executor-by-a-declared-route.adr.md) | confirmed |
| D4 | No run-level outcome: no artifact, no gate, no record, no revision path | [OUT](../specs/run-outcome.spec.md), [ADR-0107](../adr/0107-the-good-outcome-is-one-data-file-of-final-and-intermediate-outcomes.adr.md), [ADR-0108](../adr/0108-a-run-is-measured-at-a-final-outcome-gate.adr.md), [ADR-0111](../adr/0111-outcome-revisions-are-grader-changes-and-verifiers-climb-a-ladder.adr.md) | confirmed |
| D5 | No entry paths beyond "a process the person runs" (C3) | [AUT-B13](../specs/workflow-authoring.spec.md), [ADR-0109](../adr/0109-author-backwards-from-the-outcome-preferring-existing-verifications.adr.md) | confirmed |
| D6 | No contract for classifying each criterion by its verifier, for preferring a verification the person already has, or for showing a criterion nobody can verify | [AUT-B16, AUT-B17, AUT-B18](../specs/workflow-authoring.spec.md), [OUT-B10, OUT-B12](../specs/run-outcome.spec.md) | confirmed |
| D7 | No blueprint schema, scaffold, minimal workflow, comparison or literal check in this set (C1) | [SCF](../specs/blueprint-and-scaffold.spec.md) | confirmed |
| D8 | No contract for checking an authoring result before it is used: model-free checks, then a first trial | [SCF-B18, SCF-B19, SCF-B20, SCF-B21, SCF-B22](../specs/blueprint-and-scaffold.spec.md), [ADR-0110](../adr/0110-check-an-authored-workflow-model-free-then-by-one-consented-trial.adr.md) | confirmed |
| D9 | A workflow package has no design docs of its own (owner's second message) | [PKG-B21, PKG-B22](../specs/workflow-package.spec.md), [ADR-0113](../adr/0113-the-workflow-docs-set-is-provisional-until-temperspec-owns-it.adr.md) | confirmed |
| D10 | Criteria drift (B2) has no path back into the workflow except the full improvement loop of release 3 | [OUT-B20, OUT-B21](../specs/run-outcome.spec.md), [AUT-B25](../specs/workflow-authoring.spec.md) revise mode | inferred |
| D11 | No check that a judged criterion states its scoring line (what met, partial and unmet look like) and no guidance when the person's definition is too thin to extract criteria (owner, 2026-11-20) | [OUT-B11](../specs/run-outcome.spec.md), [AUT-B19, AUT-B20, AUT-B21](../specs/workflow-authoring.spec.md), [SCF-B18, SCF-B19, SCF-B20, SCF-B21, SCF-B22](../specs/blueprint-and-scaffold.spec.md) rung 8, [ADR-0114](../adr/0114-judged-criteria-carry-a-scale-and-authoring-guides-to-clarity.adr.md) | confirmed |

## Conclusions

1. A workflow package can be a plain Claude Code plugin: `plugin.json` keeps only the fields Claude Code reads, and the engine reads its own manifest file beside it, because unknown manifest keys are stripped (A1).
2. The Python half cannot rely on Claude Code to install its dependencies (A4); the engine installs them into its own environment from a declared requirements file, as UPD-B20 to UPD-B24 already requires.
3. Plugin content reaches `claude` by `--plugin-dir` and `agent-sdk` by the `plugins` option (A8). The Messages API can run only skills, through code execution (A9), and Antigravity reads skills from its own folders (A10). Prompts are rendered by the engine and need no plugin on any executor; skills and agents need a declared route per executor or the step is refused before spend (C15).
4. The good outcome is best held as data that authoring writes first and that people revise after grading runs (B1, B2), with each criterion naming who verifies it, preferring a deterministic verifier (B4) and an accepted judge (B3) over a person.
5. Authoring from a solution, from references or from a conversation differs only in how the first draft of the outcome and the verification candidates is found; after that the interview is one procedure.
6. The workflow's own docs set can follow the engine's rules today and be marked provisional, so that temperspec's rule files replace the rules without moving the files.

## Open questions

| Question | Owner |
|---|---|
| Does `claude -p --plugin-dir <path>` in a headless session load the plugin's skills and agents and admit `Skill(<plugin>:<name>)` rules for it (with P-CC-8)? Probe P-CC-9 in [ECC](../specs/executor-claude-code.spec.md). | Engine implementer |
| Does Antigravity's CLI load a plugin folder placed in an isolated config home (`~/.gemini/config/plugins/<plugin>/`)? Probe P-AG-10; until it answers, workflow skills are not offered on `antigravity`. | Engine implementer |
| Should workflow skills be uploaded to the Skills API for `messages-api` steps, given they run only under code execution with no network? This note says no for now ([ADR-0112](../adr/0112-plugin-content-reaches-each-executor-by-a-declared-route.adr.md)). | Owner |
