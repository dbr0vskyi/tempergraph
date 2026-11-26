# Why did the self-improvement loop miss the flaws found in the prompts, formats and decisions, and what would let it catch that class?

## Problem statement

On 2026-11-26 outside research on temperspec, written up in `plugins/temperspec-tgraph/docs/research/spec-decision-and-discovery-formats.rsrch.md` (F10, F11) and in `step-methods-loaded-on-demand.rsrch.md` (pull request #220), found flaws that no loop issue had named:

1. Step prompts made mostly of prohibitions, with almost no reasons (discovery: 36 prohibitions, one reason).
2. Prompts growing 30 to 80% in one change.
3. No lens and no `You own` / `You do not own` structure in most steps.
4. Rule files reaching a step session twice (#225).
5. Document formats lacking sections (a spec's `Depends on` and `Does not own`, the ten-section decision record).
6. A standing decision that a step cannot load a skill because a run has no interactive mode, false since live check L-7 passed on 2026-11-21.
7. Skill grants on step sessions that do not hold (#221).

The owner asked how these were missed, given that the loop is meant to verify results, meaning, content and prompts. The coordinator's first reading listed five causes from memory and marked them unmeasured. This note tests each against the loop's code, specs and run records, and proposes general engine capabilities, stated without any workflow, that would catch this class of flaw.

It extends [research `does-the-improvement-loop-find-what-a-reviewer-finds`](does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md), whose F9 to F11 cover defects in what a run produced. This note covers a different question: defects in the workflow's own definition (its prompts, the files its steps read, its document standards and its recorded decisions), which no single run shows as a failure.

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S1 | The friction judge's input and the rule that no run text reaches it | Spec, code | [SIL-B17, SIL-B38](../specs/self-improvement.spec.md); `engine/src/tempergraph/improve/child.py` (`prompt`, line 241) |
| S2 | The reviewer's condensed view, its intent clip and the category catalog | Spec, code | [SRV-B17, SRV-B19, SRV-B22](../specs/session-review.spec.md); `improve/review.py` (`INTENT_CHARS = 12_000`, line 38) |
| S3 | What the prompt audit and prompt lint check | Spec, code, run | [PRA](../specs/prompt-audit.spec.md) Purpose and PRA-B5, PRA-B11; [LIF-B12](../specs/lifecycle-and-evals.spec.md); `model/prompt_lint.py`; `tempergraph audit` and `tempergraph audit prompts` run on `plugins/temperspec-tgraph` at main `fd4e2417` |
| S4 | The session digest's counters | Code | `improve/digest.py` (`files_reread` line 284, `undeclared_used` line 288) |
| S5 | Fixed remedies of cause codes | Code | `improve/causes.py` (`context_bloat`, line 64) |
| S6 | The proposer's brief, its judge's criteria and the class check | Code, spec | `improve/proposals.py` (`PROPOSER_BRIEF` line 528, `JUDGE_CRITERIA` line 540, `record`); [PRP](../specs/improvement-proposals.spec.md) |
| S7 | The lessons budget | Spec | [LSN-B2, LSN-B9](../specs/workflow-lessons.spec.md) |
| S8 | Loop records of the eleven runs of the night of 2026-11-22 to 23 | Loop logs | the project's saved dumps of each run's `loop.jsonl` (`r3-t2-1` to `r3-t8-4`) |
| S9 | Loop issues filed on 2026-11-26 and the owner's notes on them | Issues | #198, #199, #200 and their comments; #134, #157, #171, #196 |
| S10 | The friction judge's answers on nine threads of 2026-11-25 | Spec | open question of [SIL](../specs/self-improvement.spec.md) on `friction.file_confidence` |
| S11 | Size, prohibitions and reasons of every step prompt at each merge into `main` that changed one | Git history, measured | `git show <merge>:plugins/temperspec-tgraph/prompts/<step>.md`, first-parent history of `main` from `ffd5f055` (2026-11-21) to `fd4e2417` (2026-11-26) |
| S12 | Commits written by the loop's proposer | Git history | `git log` of `main` for subjects starting `improve(` (the subject `open_pr` writes) |
| S13 | Decision records and what reads them | Docs, code | `plugins/*/docs/adr/*.adr.md`; `grep` for `Revisit when` over `engine/src` |
| S14 | Where the "no step loads a skill" position is written, and the probe that disproves it | Docs | `plugins/temperspec-tgraph/README.md` (line 66); [plan `live-checks`](../plans/live-checks.plan.md) (L-7); `step-methods-loaded-on-demand.rsrch.md` F3, F4 (#220) |
| S15 | The workflow cases a proposal trial runs on | Data | `plugins/temperspec-tgraph/evals/cases.json` |

Prohibitions were counted as the words `never`, `do not`, `don't`, `must not`, `not`, `no` and `nothing`, and reasons as `because`, `so that`, `since` and `otherwise`, case-insensitive, with a short script over `git show`. The counts differ slightly from those of the outside research, which used a slightly different word list; the ratios agree.

## Key findings

### F1 Nothing the loop or the audit runs judges whether a prompt is well built `confirmed`

- The friction judge reads only the findings' metadata: fingerprint, cause, class, side, unit, count and record-kind counts. SIL-B38 forbids any request text, output or workspace file in its prompt (S1). It cannot see a prompt at all.
- The session reviewer does see the rendered step prompt, clipped to 12,000 characters, plus one line per turn. Tool output is left out (SRV-B17, S2). Its catalog (SRV-B19) has eleven categories, and every one describes how a session behaved: `instruction_ignored`, `wasted_turns`, `context_bloat` and so on. None describes how the prompt is written. Conformance (`followed`, `not_followed` per prompt section) asks whether the session obeyed, never whether the section was clear.
- The prompt audit says so in its Purpose: "Every rule resolves a name or measures a size; none judges whether the text is good" (PRA, S3). Its size rule fires at 32,000 characters per template. Prompt lint's style rules are vague words, self-grading, two `if … otherwise` rules, waiting for a person, an accepting brief, foreign tool names, missing references and size (LIF-B12).
- Run on main today, prompt lint reports **0 findings** on temperspec's 11 step prompts, 11 judge briefs and 6 skills. `audit prompts` lists 28 files, each with 0 errors, 0 warnings and `changed: not recorded`. The definition audit's 73 findings are all about criteria overlap, uncovered or unverified blockers, step size in criteria and hold time; none is about prompt text (S3).

So the coordinator's hypothesis "it looks inward" holds, and more strongly: the loop has no picture of a good prompt, and the audit explicitly declines to have one.

### F2 The files that make up most of what a step must read are outside every reader `confirmed`

- `audit prompts` lists templates, briefs and shipped skills, and no file of the package's `step_files` (temperspec's `rules/*.rule.md`), though PRA-B5 reads "instruction files a step names" (S3). In a discovery session the rule files are about 70% of what must be read (`step-methods-loaded-on-demand.rsrch.md` F1).
- The reviewer's view leaves out tool output, so a rule file the session opened is invisible to it as content (SRV-B17).
- `files_reread` counts paths read more than once through a read tool (`digest.py` line 284). A rule file that Claude Code attached because of its `paths` front matter, then read again because the step's check asks for it, is one tool read and counts zero. The double delivery of #225 cannot show in any digest field.

### F3 The loop did see symptoms, and turned them into nothing or into a fixed remedy `confirmed`

The hypothesis "a passing step looks healthy" is only half true. The loop saw the effects; it could not trace them to the definition.

- **Kept observations that went nowhere.** Over the night of 2026-11-22 to 23 the reviewers returned 176 observations; the citation check kept 83. Of the kept ones, 59 carry remedy class `prompt`, and 44 are `instruction_ignored`: `code` 17, `plan` 8, `triage` 7, `expand` 6, `discovery` 3, `discovery_short` 3. **None of the 83 was corroborated** (S8), so by SIL-B16 none could file, and none reached a proposer, which reads observations only of a cluster's runs (SRV-B22). `improve review summary` would have shown them, but nothing runs it unasked.
- **A true finding with a symptom remedy.** On 2026-11-26 the loop filed #200, `context_bloat` at `discovery`: 17 of 18 digested discovery sessions had a turn over 200,000 tokens, discovery was 48% of all reported cost of 14 threads (owner's comment on #200). Its remedy is the cause's fixed text, "split the step or trim inputs" (`causes.py` line 64). It carried no measure of the prompt or the files the step must read, so it pointed at #134 (split the step) and not at the prompt's structure or the doubled rule files. The owner closed it as a duplicate of #134 and #157.
- Whether the 44 `instruction_ignored` observations were caused by the prompts' structure is not known. Their notes are local evidence of the run threads' containers and were not kept (S8). At that time the prompts were small (2,400 to 4,600 characters, S11), so size alone does not explain them.

### F4 The loop's own proposals caused none of the growth; every change came through a person's thread, and nothing measured it `confirmed`

The coordinator's hypothesis "its fixes add to the problem" is false for what happened and true for the design.

What happened (S11, S12): no commit on `main` was written by the proposer, and the overnight runs recorded 0 proposals and 0 trials. Every prompt change came from a person-directed session. Between `ffd5f055` (2026-11-21) and `fd4e2417` (2026-11-26):

| Prompt | Characters, first | Characters, now | Prohibitions | Reasons |
|---|---|---|---|---|
| discovery | 2,865 | 11,450 | 11 → 50 | 0 → 4 |
| triage | 2,967 | 7,992 | 14 → 35 | 5 → 9 |
| code | 3,441 | 7,278 | 12 → 25 | 1 → 1 |
| all step prompts | 16,363 | 54,175 | | |

The step prompts grew 3.3 times in five days, over 11 merges. A crude model-free check, "a file grew 25% or more in one merge, or holds 20 or more prohibitions and at most one reason", would have flagged seven prompts at merge `0ca8af0b` on 2026-11-24, two days before the outside research, and three again at `fd4e2417` (discovery +32%, triage +50%, read_gap +83%). `discovery_short` has held 21 prohibitions and no reason since 2026-11-23 with no reader noticing.

What the design would do if the proposer ran:

- `PROPOSER_BRIEF` asks for "one small change" and "the general rule your change encodes in one sentence" (S6). Every accepted change therefore adds a rule. Nothing asks the proposer to merge, replace or delete a sentence, or to give a reason.
- Its judge has two criteria, `addresses-cause` and `general-rule` (S6). Neither looks at size, repetition or the balance of rules to reasons.
- The engine already caps growth in one place: a lessons file fails validation above 12 active entries or 2,500 characters per step, and a lessons patch may add only one entry (LSN-B2, LSN-B9, S7). Templates and step files have no such budget, and no record of their size per version (`changed: not recorded`).
- A trial runs on the workflow's cases; temperspec has 2 (S15). A trial that could show a prompt change was worse cannot be powered on two cases, so a growth-only change would pass as `not_shown`.

### F5 The loop never reads a decision, and nothing links a probe result to the decisions that rest on it `confirmed`

- No engine source reads a decision record (S13). 119 of the 148 decision records in the repository carry a `Revisit when` section; nothing reads one.
- The "no step loads a skill" position is not a decision record at all: it is a sentence of a package README and conclusions of a research note (S14). It rested on a claim (no interactive mode means no skills) that live check L-7 disproved on 2026-11-21. Nothing tied L-7's result to that claim, so it stood for five days until outside research re-asked it.
- A capability that is never declared leaves no trace. `declared_unused` reports a declared skill that was not used. A workflow that declares no skill has nothing to report, and the reviewer's `skill_not_used` needs a declared skill (SRV-B19).

The hypothesis "it never questions decisions" holds. It is also not something a per-run loop can do from run evidence alone: a wrong decision produces no failed step, only a design that is worse than it could be.

### F6 A skill that runs without a grant is excluded from the digest's check by its code `confirmed`

`undeclared_used` is computed as the capabilities used minus those declared, minus `skill`, `subagent` and `mcp` (`digest.py` line 288). A host skill or an undeclared plugin skill that runs in a step session (#221, probe K of #220) is never reported as undeclared, so the loop could not have found #221.

### F7 Missing document sections are out of reach of any run-based reader `inferred`

The loop's idea of a good artifact is the workflow's own criteria and standards (research `does-the-improvement-loop-find-what-a-reviewer-finds` F9; the artifact lens #124 is open and grades against "the standards its steps were given"). A format that lacks a `Depends on` section, or a decision record with four sections where ten would serve, is a gap in the standard itself. Every run that follows it passes. Only a comparison with an outside standard shows it, which is what the research did. No change to the loop makes run evidence show what the standard never asked for.

### F8 Evidence is thin, and the filing floor discards most of it `confirmed`

- Overnight 2026-11-22 to 23: 81 sessions reviewed for 3.47 USD, 0 issues, 0 proposals (S8; research `does-the-improvement-loop-find-what-a-reviewer-finds` F7, F8).
- On nine threads of 2026-11-25 the friction judge answered for 64 findings with a highest confidence of 0.70 and a median of 0.50, against a filing floor of 0.75 (S10). #171 asks for pattern-based filing without that floor.
- Two workflow cases (S15) cannot power a trial of a prompt change (F4).

### F9 Which flaw each reader could have seen `inferred`

| Flaw | Friction judge | Session reviewer | Digest | Prompt lint and audit | What could show it |
|---|---|---|---|---|---|
| 1 Prohibitions without reasons | no text (F1) | sees the prompt, no category | none | no rule | a model-free ratio over the text |
| 2 Growth per change | none | none | none | no size history | a size record per version |
| 3 No lens, no own and do-not-own | none | no category | none | no rule | a judged check against a prompt standard |
| 4 Rule files twice | none | tool output hidden (F2) | attached reads not counted (F2) | step files not listed (F2) | the session's start context (#157) and a step-file read count |
| 5 Format sections | none | none | none | none | outside comparison only (F7) |
| 6 Wrong standing decision | none | none | none | none | a revisit trigger tied to a probe or a measure (F5) |
| 7 Skill grants | none | none | `skill` excluded (F6) | none | the digest's undeclared check including skills |

Two of the seven (5 and part of 3) need a standard from outside the workflow. The other five need a model-free measure the engine does not take today.

## Conclusions

1. **The loop missed these flaws because they are flaws of the definition, and every reader the loop has looks at a run.** A run whose prompt is bloated and prohibition-heavy still passes its gates. The loop saw the effects (44 kept `instruction_ignored` observations, a true `context_bloat` finding at discovery) but had no measure of the definition to connect them to, so the observations went uncorroborated and the finding came with a generic remedy (F1 to F3).
2. **The coordinator's five hypotheses, tested:** "looks inward" holds (F1, F2); "a passing step looks healthy" holds in part, since the symptoms were seen and dropped (F3); "never questions decisions" holds (F5); "its fixes add to the problem" is false for the history, since the loop wrote no change, and true for the design, since the proposer can only add a rule and nothing weighs size (F4); "little evidence" holds (F8).
3. **Most of this class can be caught without a model.** Size, prohibitions per reason, repeated sentences across files, growth since the last version and step files read twice are counts. A crude version of the first two would have flagged seven prompts on 2026-11-24 (F4). Only the lens and own-and-do-not-own structure, and the format sections, need a judged comparison with a standard.
4. **Growth comes from every change path, so the guard belongs where every path passes: validation and the audit, not only the proposer.** The engine already does this for lessons (LSN-B2); templates and step files lack it (F4).

### Options

**A. Prompt health measures, model-free (audit definition layer and `audit prompts`).**

| Option | How it works | For | Against |
|---|---|---|---|
| A1 Measures in the matrix only | `audit prompts` gains, per model-facing file including every `step_files` file: characters, must-read size (template plus the step files it names plus the criteria text the engine appends), prohibitions and reasons, sentences repeated in three or more files, and share of text under goal branches | Cheap; no new rule to tune | Advisory and unread unless a person runs it, as today |
| A2 Measures plus warning rules | A1, plus rules `prompt-constraint-heavy` (at least N prohibitions per reason), `prompt-repeated-text` and `step-file-twice` (a step file that loads by path and is also required by the step's check or named in its prompt), thresholds as parameters with provenance `default_no_data` | Shows in `validate` and in CI; same shape as the existing rules | Thresholds are guesses until runs calibrate them; a ratio is a proxy, not quality |
| A3 A gate that refuses | A2 at error severity above a budget | Stops growth outright | A proxy that refuses a start would block good prompts; against the audit's advisory contract |

**B. Growth per version (stamp, history layer, loop).**

| Option | How it works | For | Against |
|---|---|---|---|
| B1 Recorded only | The stamp records A's measures per file and version; `audit prompts` fills `changed` with the growth since the last stamp | Data for every later decision | Nobody acts on a number nobody reads |
| B2 Loop finding that corroborates | B1, plus: on a new version's first final exit (the existing `stable.new_version_runs` trigger), the loop records a model-free finding `prompt_growth` or `prompt_structure` on each unit whose file crossed a threshold, carrying the measures. Under the existing corroboration rule (ADR `review-observations-are-candidates-corroborated-before-they-file`), a kept `instruction_ignored`, `prompt_misread` or `context_bloat` observation of that unit then corroborates it, and it files by the pattern rule | Joins the symptom to a cause without a new filing rule; the 44 overnight observations would have had something to corroborate | Needs the observation categories mapped to definition findings; a definition finding is per version, while the pattern rule counts runs |
| B3 File on growth alone | A crossing files at once | Fast | Files on a proxy with no evidence of harm |

**C. The proposer weighs size.**

| Option | How it works | For | Against |
|---|---|---|---|
| C1 Brief and criterion | The brief allows a change that replaces, merges or deletes text, and asks for a reason beside a non-mechanical rule; the judge gains a criterion that the change does not add text where it could replace it; the proposal report shows A's measures before and after | Small change; keeps proposals from repeating the history of F4 | A judge criterion is soft |
| C2 Budget per file, as for lessons | A package may declare a character budget per template and step file; validation fails above it; a proposal above it is refused `growth` | Same rule as LSN-B2, already understood | One more number per file to set; a person's change is blocked too |

**D. Decisions are revisited on evidence.**

| Option | How it works | For | Against |
|---|---|---|---|
| D1 Scheduled reading by a person | A recurring reminder to reread decisions and their `Revisit when` lines | No build | Depends on someone doing it |
| D2 Model-free triggers | A package's decision records may name, in `Revisit when`, an observable the engine records: a live check id, an issue number, a measure of A over a value, an engine or executor version. The audit reports `decision-revisit-due` when that observable changed since the last stamp | Would have reopened the skills position on the day L-7 passed, had it been a record naming L-7 | Works only for decisions written as records with such a line; a sentence in a README stays invisible |
| D3 Scheduled model review | A periodic judged session rereads every decision against current code and probes | Catches what no trigger names | Costly; needs calibration like any judge |

**E. Skill use is checked.** Remove `skill` from the exclusions of `undeclared_used`, so a skill that runs without a grant is a finding of the executor's side. This belongs with #221.

**F. An outside standard, for what runs cannot show.** For flaws 3 and 5 the only source is a comparison with practice outside the workflow (F7). Options: a person-run research task on a schedule (for example monthly, as a scheduled run of an agent with the research rule); or an engine-shipped prompt standard (lens, what the step owns, reasons for non-mechanical rules) that the authoring path writes to and a judged check grades against. The second is a larger design with its own calibration and should wait for A and B to show which signals matter.

### Recommendation

5. **Build A2 and B2 first, as one engine feature.** They are model-free, they reuse the audit's rule shape and the loop's corroboration rule, and on the history above they would have pointed at the prompts two days before the outside research did. Start the thresholds as `default_no_data` parameters (proposed: growth of 25% in one version, 20 prohibitions per reason, a sentence repeated in three files) and calibrate them on the runs since 2026-11-21. Include every `step_files` file in the measures, and add a start-context field per session as #157 asks, so that `step-file-twice` can be measured and not guessed.
6. **Then C1.** It is a small change to the proposer and its judge and keeps the loop from adding to growth once proposals start. Keep C2 as an option for a package that wants a hard budget.
7. **D2 for decisions,** with one package-side rule that temperspec, not the engine, owns: a position that turns down an engine capability is written as a decision record with a `Revisit when` that names its probe or measure.
8. **E as a comment on #221,** not a new issue.
9. **F stays a person's or a scheduled research task for now;** a shipped prompt standard is a later design.
10. **Proposed issues, to be filed after the owner's review:** (a) engine, prompt health measures and rules over every model-facing file and step file (A2); (b) self-improvement, prompt measures per version and a definition finding that review observations corroborate (B1, B2); (c) self-improvement, the proposer may replace and delete text and its judge weighs growth (C1); (d) engine, decision records' revisit triggers reported by the audit (D2); plus a comment on #221 (E). These are stated without any workflow; temperspec appears in this note only as the evidence.

## Open questions

- Whether a prohibitions-per-reason ratio tracks prompt quality at all, or only correlates with growth. It needs a before-and-after trial on a reshaped prompt (as #224 plans), which this note did not run. No live result is assumed.
- Whether the 44 kept `instruction_ignored` observations of 2026-11-22 to 23 were caused by the prompts or by the rule files. Their notes were not kept (F3).
- Whether a definition finding, which belongs to a version, should file by the pattern rule (which counts runs) or by a rule of its own. Until answered: by the pattern rule over the runs whose observations corroborate it. Owner: owner.
- Whether the owner wants a scheduled outside comparison (F) and at what cadence and cost. Owner: owner.
- Whether the thresholds of conclusion 5 hold for workflows whose prompts are much shorter or longer than temperspec's. Only one package's history was measured.

Assumptions made because the owner asked for standalone work: the overnight dumps of 2026-11-22 to 23 stand for the loop's behaviour on review observations, since later run threads' loop records are not kept in the repository; the word lists for prohibitions and reasons are a proxy chosen for a model-free check, not a measure of clarity; merges into `main` stand for "one change", although one merge can hold several commits.
