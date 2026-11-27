# Should a step prompt be split into a short prompt plus methods it loads on demand, and can an unattended step load them?

## Problem statement

One temperspec step often serves several goals. Discovery closes five kinds of gap: a new spec, an edit to a spec, a decision, a research question, and an `existing behaviour` gap, where it extracts the rules that the code already has. It also follows three conversation values. Code runs in three modes, and setup reverse-engineers a whole repository. Each goal adds a branch to one prompt, and every session reads every branch. The owner is worried that the prompts are weak and will grow too complex. The worry covers temperspec and every workflow the engine's authoring path produces. Skills were turned down more than once, each time on the ground that a run has no interactive mode.

The questions:

1. How large and how branched are the step prompts now, counting everything a session is told to read?
2. Where were skills turned down, and does the reason still hold?
3. Can an unattended `claude -p` step session load a skill or a rule file on demand, how reliably, and at what cost? (Measured, not assumed.)
4. Which ways of splitting a prompt are there, and what does each cost and risk?
5. What would the engine have to provide as a general capability, given that it knows no workflow?

This note recommends. It changes no prompt, rule, check or engine code. Open pull request #219 reshapes the triage, gap-reading and discovery prompts (an opening on what the step settles, plus `You own` and `You do not own` lists). This note measures #219's versions as well as `main`'s and builds on that shape without editing those files.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| The eleven step prompts, on `main` and on the branch of #219 | prompt, measured | `plugins/temperspec-tgraph/prompts/*.md` |
| Step declarations (tools, prompt files) | code | `plugins/temperspec-tgraph/workflow/temperspec/__init__.py` (lines 185 to 287) |
| Criteria per unit | data, measured | `plugins/temperspec-tgraph/outcome.json` (`intermediate`) |
| Rule files and their `paths` front matter | rule, measured | `plugins/temperspec-tgraph/rules/*.rule.md`, `.claude/rules/temperspec/` |
| The check that named rule files were opened | decision record | `docs/adr/a-step-check-confirms-that-each-rule-file-its-prompt-names-was-opened.adr.md` |
| Earlier spec-extraction research (method as a rule file, thin skill for people) | research | `docs/research/spec-extraction-from-existing-code.rsrch.md` (conclusions 2 and 7) |
| Prompt findings F10, F11 and conclusions 18 to 21 | research | `docs/research/spec-decision-and-discovery-formats.rsrch.md` |
| Package README on skills | doc | `plugins/temperspec-tgraph/README.md` (line 66) |
| Skill capability decision | decision record | `plugins/tempergraph/docs/adr/skills-are-a-declared-tool-capability.adr.md` |
| Plugin content route per executor | decision record, spec | `plugins/tempergraph/docs/adr/plugin-content-reaches-each-executor-by-a-declared-route.adr.md`, `plugins/tempergraph/docs/specs/workflow-package.spec.md` |
| What temperspec was planned to need from the engine | research | `plugins/tempergraph/docs/research/temperspec-as-the-first-authored-workflow.rsrch.md` (lines 72, 107, 128) |
| Live check L-7 (P-CC-8, P-CC-9) | plan, record | `plugins/tempergraph/docs/plans/live-checks.plan.md` (lines 30 and 87) |
| Step launch arguments | code | `plugins/tempergraph/engine/src/tempergraph/executors/claude.py` (`step_argv`, lines 106 to 150) |
| Skill capability mapping, preflight | code | `executors/capabilities.py` (line 17), `executors/preflight.py` (line 172) |
| Step prompt rendering | code | `plugins/tempergraph/engine/src/tempergraph/render/prompt.py` (`render_step`) |
| Contest slot prompt variants | code | `plugins/tempergraph/engine/src/tempergraph/run/nodes.py` (line 614, CTS-B6) |
| Skill calls in the session digest | code | `plugins/tempergraph/engine/src/tempergraph/improve/digest.py` (lines 231 to 290) |
| Prompt lint and size limits | code | `plugins/tempergraph/engine/src/tempergraph/model/prompt_lint.py` (lines 25, 26, 41) |
| Declared step files trialled by the loop | code, issue | `improve/proposals.py` (line 262), issue #125 (closed) |
| Scaffolded prompts | code | `plugins/tempergraph/engine/src/tempergraph/author/scaffold.py` (`_prompt`, line 283) |
| Issues #134 (split the discovery and code gates), #135 (shared prompt text) | issue | GitHub |
| Live probes run for this note, Claude Code 2.1.332, model alias `sonnet`, effort `medium` | probe, measured | 2026-11-26, cloud container; arguments copied from `step_argv` |
| Claude Code documentation on skills (the description stays in context and the body loads when the skill is used), and on `.claude/rules` files with `paths` | public, from memory, not fetched in this session | none |

## Key findings

### F1 Prompts are mid-sized, but they are growing, and most of what a session must read sits in the rule files `confirmed`

The table counts characters. Negations are `never`, `do not`, `not`, `no`, `must not` and `nothing`. Reasons are `because`, `so that`, `since` and `otherwise`. "Must read" is the rule files the prompt names, which the step's check requires the session to open, plus the criteria text the engine appends.

| Prompt | `main` | #219 | Negations, #219 | Reasons, #219 | Criteria (count, chars) | Rule files named (chars) | Must read, #219 |
|---|---|---|---|---|---|---|---|
| discovery | 8,644 | 11,450 | 48 | 4 | 20, 2,943 | 6 (32,924) | about 47,300 |
| triage | 5,324 | 7,992 | 34 | 9 | 8, 1,074 | 2 (14,672) | about 23,700 |
| code | 7,278 | 7,278 | 24 | 2 | 27, 4,593 | 2 (20,639) | about 32,500 |
| setup | 4,636 | 4,636 | 24 | 0 | 11, 1,287 | 4 (27,113) | about 33,000 |
| plan | 4,154 | 4,495 | 14 | 0 | 9, 1,093 | 2 (11,251) | about 16,800 |
| read_gap | 1,884 | 3,440 | 19 | 0 | 2, 146 | 0 | about 3,600 |
| the other five | 2,049 to 3,715 | same | 11 to 18 | 0 to 1 | 2 to 9 | 0 or 1 | 2,000 to 13,000 |

Measured with a short script over `git show` of each file. One pull request grows discovery by 32%, triage by 50% and read_gap by 83%. No prompt is near the engine's 32,000-character template limit (`TEMPLATE_LIMIT`). Prohibitions still outnumber reasons by about ten to one. In a discovery session the rule files hold 70% of what must be read, and the prompt itself holds 24%.

### F2 Discovery and code each carry several goals, and every session reads all of them `confirmed`

- Discovery, procedure step 4 on #219, has one branch per gap kind: `spec gap` 84 characters, `spec update` 95, `decision needed` 672, `research needed` 87, `existing behaviour` (extraction from code) 276. The Limits add 1,415 characters that apply under one conversation value each (`never`, `blocking` or `always`). About 2,600 characters, 23% of the prompt, belong to goals that a given task may not have.
- Discovery must open `decision.rule.md`, `research.rule.md` and `extraction.rule.md` (9,379 characters) even on a task that writes no decision record, no research note and no spec drawn from code. The check that confirms the reads rejected option C, "ask only for the rule files of the types the session wrote", because it would need a map from rule file to document type (ADR `a-step-check-confirms-…`, options A and C).
- Code serves the whole plan in one session, the join after the phases, and the quick lane (`code.md` lines 13 and 15). Issue #134 already asks for a prompt per procedure.
- All 20 discovery criteria are appended to every discovery attempt, whatever the gap kinds.

The prompt text that applies to only some goals is still modest. The growth comes from each new goal or fix being added as one more clause or branch, which is how F10 of `spec-decision-and-discovery-formats.rsrch.md` describes the prompts.

### F3 Skills were turned down for a reason that was never true of the engine `confirmed`

Where the question came up, in this repository:

1. The engine's plan for temperspec kept skills on steps. `temperspec-as-the-first-authored-workflow.rsrch.md` line 128 kept "the skills a step declares as a tool (codebase discovery, spec authoring, decision records, test fixing)" and dropped only "the interactive twins; they add nothing to a headless run". Line 107 lists the probes this depends on.
2. The engine built that route. ADR `skills-are-a-declared-tool-capability` (status `proposed`) adds the capability `skill:<plugin>:<name>`. `step_argv` passes the workflow plugin with `--plugin-dir`. The digest records each skill call and reports declared skills that go unused. Prompt lint resolves the skill names that prompts mention.
3. Live check L-7 passed on 2026-11-21 (Claude Code 2.1.330): a headless step under `--plugin-dir` listed the plugin's skill and recorded `Skill {skill: tgprobe:hello}` (`live-checks.plan.md` line 87).
4. temperspec never declared a skill on any step. Its README says "no step of a run loads one". The spec-extraction research put the extraction method into a rule file and left only a thin skill for a person's own session (conclusions 2 and 7). The rule-opened ADR turned down copying rule text into prompts.

The ground given was "there is no interactive mode". That ground mixes up two kinds of skill. An interactive skill talks to a person, and a run rightly has none. A method skill is a file of instructions that a session loads by name, and it needs no person. Item 3 shows that the engine could deliver method skills to unattended steps from the first release on. The part of the earlier answer that still holds is narrower: a *stage* is a gated step, not a skill. A step must not hand its procedure to a skill the gate cannot see.

### F4 Unattended step sessions load skills by name and by description, and path-scoped rule files load when a matching file is read `confirmed`

Measured 2026-11-26 on Claude Code 2.1.332. Each session ran `claude -p --output-format stream-json --verbose --permission-mode default --permission-prompts none --strict-mcp-config --setting-sources project --plugin-dir <probe plugin> --model sonnet --effort medium`, as `step_argv` does. The probe plugin held two skills with opposite descriptions: `reverse-engineer` ("describe rules existing code already implements") and `greenfield` ("new behaviour no code has yet"). Each skill body asks for a marker token in the answer, so a load shows in the result.

| Probe | Setup | Result |
|---|---|---|
| A | `Skill` in `--tools`; prompt names `tgprobe2:reverse-engineer` | 3/3 loaded it and followed its body (marker and evidence words present) |
| B | Same tools; prompt asks to list the behaviours `invoice.py` already implements, names no skill | 3/3 picked `reverse-engineer` by its description and followed it |
| C | Same tools; prompt asks for rules of a new capability, names no skill | 3/3 picked `greenfield` |
| G | Same tools; prompt "say hello" | 0/3 loaded a skill (no false trigger) |
| D | Prompt names the skill, but `Skill` is not in `--tools` | `system/init` still listed both skills. 3/3 could not load one, searched the disk with `Glob` for the file, and answered without the method, with no error |
| K | Allow rule `Skill(tgprobe2:reverse-engineer)` only | The other plugin skill also loaded, and so did the host's bundled `code-review` skill, which ran as a forked sub-session (still limited to the step's tools). An allow rule does not limit which skills run |
| X | Deny rules `Skill(tgprobe2:greenfield)`, `Skill(code-review)` | Both refused, "Skill execution blocked by permission rules". The undenied skill loaded |
| cost | One-word task, with and without the `Skill` tool | 17,748 input tokens with the tool and two plugin skills, 17,627 with the tool and no plugin, 14,377 without the tool. The tool costs about 3,250 tokens per session, and each skill's listing about 60 |
| R1, R2 | Repository with `CLAUDE.md`, a rule file without `paths`, and a rule with `paths: src/billing/**` | `CLAUDE.md` and the rule without `paths` were in context 3/3. The path rule was absent 3/3 until the session read a file under `src/billing/`, then present 3/3 |
| W | Rule with `paths: **/*.adr.md`; prompt asks to create a new `.adr.md` without reading anything | 3/3 wrote the file, got the rule after that first write, and wrote the file again to follow it |

With `Skill` granted, `system/init` listed 22 skills besides the package's own: the host's bundled skills such as `code-review`, `loop`, `batch` and `deep-research`. ECC-B16 says that no skill from user scope reaches a step. These skills come bundled with the CLI, so `--setting-sources project` does not remove them. Only deny rules or `--disable-slash-commands` do.

One caveat about the environment. A probe repository placed under this session's scratch folder loaded neither `CLAUDE.md` nor the rule files. The same repository copied to an ordinary folder loaded both. Every R, W and K result above comes from the ordinary folder. The cause was not found (see Open questions).

### F5 temperspec's rule files already act as methods loaded on demand, and some arrive twice `inferred`

This follows from F4 and the front matter of the installed rule files. `documents.rule.md` has no `paths`, so a step session in a repository that holds it already has it in context. Six prompts still tell the session to open it, and the check requires the read. `spec.rule.md` (`**/*.spec.md`), `task-notes.rule.md` and `extraction.rule.md` load as soon as the session reads any file of their kind, which discovery always does, and then the session reads them again because the check asks for it. For discovery that is up to about 27,000 characters taken in twice. The size of the duplicate has not been measured on a real run's session record.

### F6 The engine already holds most of the parts `confirmed`

- Delivery: the `skill:` capability, `--plugin-dir` with the plugin's dependencies, and a preflight that refuses a skill on an executor with no skill route (`preflight.py` line 172).
- Record: skill calls in the session digest, a declared skill that goes unused (`declared_unused`), and the cause `skill_not_used` in the session review.
- Self-improvement: a package declares `step_files`, and a proposal that changes one is classed and trialled like a prompt change (#125, closed).
- Composition: the contest slot's `prompt_variant` is appended under a fixed heading (`run/nodes.py` line 614). Routes and complexity routing pick units by value. #135, still open, asks for text parts stated once and included by name.

### F7 What the engine lacks `confirmed`

1. A way to choose, from run state and with no model, which method an attempt gets. The prompt names a skill always or never.
2. One delivery route for a method that works on every executor. A step that declares `skill:` is refused on `messages-api`, and nothing inlines the skill's text there.
3. A check that a named method was opened. temperspec built its own check for rule files, and no engine criterion exists for this.
4. Skill scoping that holds. K1 of ADR `skills-are-a-declared-tool-capability` expected a per-skill allow rule. F4 (K) shows that an allow rule does not limit which skills run, and that deny rules do.
5. Authoring guidance. `scaffold._prompt` writes one prompt per unit. The `author` skill never asks whether a step serves more than one goal. The audit flags a step with more than 8 blocker criteria (`oversized-step`) but has no signal for a prompt that branches by goal.

### F8 Options for splitting a prompt `inferred`

| Option | How it works | Cost | Risk |
|---|---|---|---|
| O1 One prompt per step, trimmed (#219's shape) | Opening, `You own` and `You do not own`, one action per procedure step | Low; under way | Every new goal still adds a branch, so growth goes on |
| O2 One unit per goal, chosen by a route | For example `discovery_extract`, `discovery_new`, `discovery_decide`, each with its own prompt and gate | New units, outcome revisions, calibration seeds per unit; shared text copied unless #135 lands | A task with mixed gap kinds needs several passes; trips back multiply |
| O3 Engine composes the prompt from parts | A template includes named parts, some only when a run value is in a set (`gaps` holds `existing behaviour`) | One engine feature (#135 plus a condition) | Template logic grows into a language unless the condition stays "value in set"; every part enters the prompt up front |
| O4 Methods as skills the engine names | The engine chooses the methods from run state, the prompt section names each one, the session loads it with `Skill`; on an executor with no skill route the engine inlines the same file | One engine feature; one file per method | The session may skip the load (needs a check); skill scoping needs deny rules; behaviour differs by executor unless the inline route is equal |
| O5 Methods the model picks by description | The step is granted a toolbox of skills; the session chooses | Only declarations | Not deterministic; measured only on a toy task (F4 B, C); the gate cannot know what was meant to load |
| O6 Path-scoped rule files (today) | Claude Code loads a rule when the session reads a matching file | None; already installed | Claude Code only; the rule arrives after a first write (F4 W); doubled by the opened-check (F5) |

O4 and O3 deliver the same text. They differ in when the text arrives. In O3 it is always in the prompt. In O4 it arrives only when the session opens it, and the same file also serves a person's own session, as the package's `extract` skill already does. O2 is the right shape where goals need different gates (#134). O4 is the right shape where the gate stays the same and only the method changes.

## Conclusions

1. **The earlier rejection does not stand on its stated ground** (F3, F4). An unattended step can load a method by name, 3/3, and had this route since L-7. What still stands is that a stage is a gated step and never a skill.
2. **Split by kind of content, not by step.** A step's prompt keeps the role: what the step settles, `You own` and `You do not own` (#219), the inputs, and a procedure skeleton that holds for every goal. A goal-specific procedure becomes a **method**: one file per goal, in the Agent Skills format under the package's `skills/`, so that a person's session can use it too. A document format stays a **rule file**, because `specfmt.py` parses it and Claude Code loads it by path. A method names the rule files it needs and repeats none of them.
3. **The engine chooses methods, not the model**, wherever run state already knows the goal: triage's `gaps` and `route`, the code mode, the conversation value. Model choice (O5) is for a toolbox only, for needs nobody can foresee, such as fixing a failing test in an unfamiliar language. It is never the only route to a method a criterion grades.
4. **Engine capability, stated with no workflow** ("step methods"):
   - a step declares methods, each a package skill with an optional condition `<state key> in [values]`;
   - at each attempt the engine renders a fixed section that names the methods that apply, and grants `skill:` for exactly those;
   - it denies every other skill that `system/init` lists, or passes `--disable-slash-commands` when the step has none. This replaces the allow-rule plan in K1 of ADR `skills-are-a-declared-tool-capability`;
   - on an executor with no skill route it inlines the method's body under the same heading, so the step behaves the same everywhere;
   - the session record marks each named method as opened, and a stock criterion fails an attempt that did not open one;
   - method files count as `step_files`, so the improvement loop can trial changes to them (#125);
   - the audit reports an unused method, and a prompt whose goal branches pass a set share of its size;
   - the authoring path asks, for each step, whether it serves more than one goal, and scaffolds one method per goal.
5. **Stop delivering rule files twice** (F5). A step's check should accept a rule file that Claude Code attached because of its `paths`, or the prompt should name only the rule files that do not load by path. Measure the saving on one run's session record first.
6. **Methods do not replace splitting the gates** (#134). A method shortens a prompt, but a gate with 20 criteria still repeats all of its work after one failure. Per-goal criteria, graded only when the goal's method applied, belong in the step-methods design.
7. **Order of work:**
   1. Let #219 merge. Its prompt shape is the role layer, and this note's methods hang from it.
   2. File the engine issue "step methods" (conclusion 4) and a debt issue for skill scoping: P-CC-8 fails as written, deny rules work, and the README line and ADR K1 need correcting.
   3. Measure the double reading of rule files on one existing run's session record, then fix conclusion 5. This is cheap and needs no engine change.
   4. Build the engine feature, with an engine fixture, on `claude` (skill route) and on a stand-in executor (inline route).
   5. Pilot in discovery. Move `existing behaviour` (shared with setup and the `extract` skill) and `decision needed` into methods, each chosen by the gap kinds in triage's `gaps`. Then run one task twice, before and after, and compare prompt characters read, cost, first-attempt gate result and blockers.
   6. Do the same for code's join and quick lane, together with #134, and for setup's reading method.
   7. Give #135 (shared sentences) its own small change, since it is independent of methods.

## Open questions

- Whether a pilot improves results, not only size. That needs a trial run before and after, about two runs at the 15 USD cost of earlier temperspec runs. Not run here, and no live result is faked.
- Whether the owner accepts model-chosen toolbox skills (conclusion 3) in gated steps at all.
- Why a repository under the session's scratch folder loaded no `CLAUDE.md` or rule files (F4 caveat). It matters if the engine ever runs steps in a worktree under such a folder.
- Whether the Agent SDK and Antigravity executors deliver a named skill the way Claude Code does (issue #93). Until then the inline route covers them.
- Whether per-goal criteria (conclusion 6) need an engine condition on criteria, or can be kept in the package's checks.

Assumptions made because the owner asked for standalone work: the probes' toy skills stand for a method's loading, not its quality; `sonnet` at effort `medium` stands for the step sizes the package uses (`medium`); three repeats per probe are enough to show a mechanism, not a rate.
