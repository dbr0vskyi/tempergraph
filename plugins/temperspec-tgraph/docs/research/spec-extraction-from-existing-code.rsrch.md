# How should temperspec extract specs, invariants and business rules from existing code?

## Problem statement

The owner asked for a skill that extracts specs from legacy code properly (behaviours, invariants, business rules) and for temperspec to use it wherever it is needed, above all when a repository with code but no specs is set up.

temperspec already writes specs from code in one place: the `setup` step, run when a repository has no overview spec, with one read-only reading session per component folder before it (PRL-B4). What it lacks is a method. `prompts/setup.md` says what to write (one spec per component, "the behaviours the code has now", "write only what you have read") but not how to find a rule in code, how to tell a rule from an accident of the implementation or from a bug, how sure each behaviour is, or where the evidence goes. Discovery has no path at all for code that exists but has no spec: the triage gap kinds cannot say "the behaviour exists, nobody wrote it down".

The unknowns: what existing tools and published methods do, which parts fit temperspec's rules (spec rule, documents rule, and the "general rules, not cases" rules of pull request #118), where extraction plugs into the workflow, and what the skill should be.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| Setup prompt, reading prompt, setup judge, setup unit spec | prompt, judge, spec | `prompts/setup.md`, `prompts/read_component.md`, `judges/setup.md`, `docs/specs/03-setup.spec.md` |
| Parallel reading | spec | `docs/specs/parallel-reading.spec.md` (PRL-B4, PRL-B9, PRL-B12) |
| Triage and discovery prompts | prompt | `prompts/triage.md` line 21, `prompts/discovery.md` |
| Spec rule, task-notes rule, documents rule | rule | `rules/spec.rule.md`, `rules/task-notes.rule.md` (setup note), `rules/documents.rule.md` |
| Overview spec | spec | `docs/specs/00-overview.spec.md` (Open questions: setup specs need no test per criterion) |
| Earlier tool comparison | research | [sdd-tools-comparison.rsrch.md](sdd-tools-comparison.rsrch.md), comparison 6 |
| Literal specs research (pull request #118, not merged) | research | `specs-state-durable-meaning.rsrch.md` on branch `claude/project-thread-ahzbz8` |
| Issue #76, setup as a sub-workflow | issue | <https://github.com/dbr0vskyi/tempergraph/issues/76> |
| OpenSpec, "Using OpenSpec in an Existing Project" | web, primary | <https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/docs/existing-projects.md> |
| spec-miner agent (ECC), extracts OpenSpec specs from brownfield code | web, primary | <https://raw.githubusercontent.com/affaan-m/ECC/main/agents/spec-miner.md> |
| Spec Kit, "How to adopt Spec Kit in an existing project" | web, search excerpts | <https://github.github.io/spec-kit/how-to/existing-projects.html> |
| Spec Kit community brownfield extensions; StackShift reverse-engineer skill | web, directory pages | <https://speckit-community.github.io/extensions/brownfield>, <https://skills.sh/jschulte/stackshift/reverse-engineer> |
| COBRAIN, LLM against rule-based business rule extraction from COBOL | paper, abstract | <https://dl.acm.org/doi/10.1145/3756681.3756982> |
| A-COBREX, rule-based extraction (IBM, ICSE 2025) | paper, abstract | <https://research.ibm.com/publications/a-cobrex-a-tool-for-identifying-business-rules-in-cobol-programs> |
| Business requirements from COBOL and PL/I with generative AI (ACL 2026 industry) | paper, abstract | <https://aclanthology.org/2026.acl-industry.4/> |
| AgentModernize, behavioural specification graphs | paper, abstract | <https://arxiv.org/abs/2605.17535> |
| Daikon, dynamic detection of likely invariants (Ernst et al.) | paper | <https://homes.cs.washington.edu/~mernst/pubs/daikon-tool-scp2007.pdf> |
| SpecGen; nl2postcond (FSE 2024); SpecMind | paper, abstract | <https://arxiv.org/abs/2401.08807>, <https://nl2postcond.github.io>, <https://www.alphaxiv.org/abs/2602.20610v3> |
| Characterization tests (Feathers, *Working Effectively with Legacy Code*) | book, secondary | <https://wikipedia.com/wiki/Characterization_test>, <https://www.infoq.com/news/2007/03/characterization-testing> |
| EARS requirement patterns (Mavin et al.) | web | <https://en.wikipedia.org/wiki/Easy_Approach_to_Requirements_Syntax> |

Most paper and vendor pages could not be opened from the cloud session (their hosts do not resolve here); their findings below rest on abstracts and search excerpts and are marked `supported` at most. The OpenSpec guide and the spec-miner agent were read in full.

## Key findings

### F1 temperspec's setup says what to write, not how to find it `confirmed`

`prompts/setup.md` step 4: "read its code and its tests … the behaviours the code has now, each in the fixed pattern and observable from outside". Its limits: "Write only what you have read", "Prefer few behaviours that matter to many that restate the code", "No internal names". Nothing names where rules live in code (guards, validation, state changes, constraints), how to rank evidence (a test against a comment), how to treat a suspected bug, or how much of a component to read. `prompts/read_component.md` asks for "what the folder holds, what someone outside depends on" in one line of 1,500 characters (PRL-B9): a folder survey, not a list of candidate rules. The judge (`judges/setup.md`) checks each behaviour against the code and coverage of top-level folders; it has no criterion for whether the behaviours are the rules that matter or merely the code restated.

### F2 The evidence for a setup behaviour has nowhere to live `confirmed`

The spec rule forbids naming a function, class or module in a behaviour, and the documents rule forbids a spec listing the tests that prove it. The setup note (`rules/task-notes.rule.md`) has Components (spec to code folder), Commands and Not covered, but no per-behaviour evidence. So the judge re-finds every behaviour's code from a folder path, and a later task cannot tell a behaviour that a test pins from one a session inferred. The overview spec's Open questions add that setup specs do not need a test per criterion, which is right for existing behaviour but leaves "is this pinned by anything?" unrecorded.

### F3 Triage cannot say "the code does this, no spec says so" `confirmed`

`prompts/triage.md` line 21 and the task-notes rule give four gap kinds: `spec gap`, `spec update`, `decision needed`, `research needed`. A repository that went through setup still has parts under Not covered, and a repository that had specs before temperspec may have code no spec describes. When a task touches such code, the run records a `spec gap` and discovery writes only the behaviour the task wants; the existing rules around it stay unwritten, and the code gate (ts-code-aligned) then compares the change with a spec that is silent on what the change must keep. No step extracts first and changes second.

### F4 OpenSpec and Spec Kit advise against back-filling specs for the whole system `confirmed`

OpenSpec's guide: "You do not document your whole codebase to start. You write specs only for what you're about to change", and "Resist the urge to back-fill everything. Writing specs for code you aren't changing feels productive and usually isn't. Those specs go stale, because nothing forces them to track reality." Existing documents are "source material for exploration, not … specs to convert". Spec Kit's guide (excerpts): do not make "document the entire existing system" the first feature; capture as constitution only principles "already true for the repository"; "do not invent standards merely to fill the constitution template". temperspec's setup does the opposite on breadth: every top-level part gets a spec or a Not covered line (ts-set-cover). temperspec has what those tools lack against staleness (the code gate judges code against edited and related specs on every run), so the argument applies to depth more than to breadth: a broad, shallow setup is checked on every later run that touches it; a deep one costs a large read whose detail nothing checks until a task touches it.

### F5 The one complete brownfield extractor found works capability by capability, samples, and flags rather than guesses `supported`

The spec-miner agent (read in full) is the most explicit method found:

1. **Scope.** Detect manifests, configs, entry points; group entry points by the services they share into capabilities; ask the user which to mine first ("A 50-module monorepo does not need all specs on day one").
2. **Sample and expand.** Read entry files first (routers, controllers, service facades: "typically contain ~70% of behavioral assertions"), then one level down each call chain. Stop at an external boundary, after three expanded files with nothing new, or after 15 files per capability. List unread files as deferred.
3. **Where rules live.** Public signatures and error conditions; guard clauses that throw or return early on domain state; every path that changes a status field; domain validation ("start date before end date"); calculations; authorization checks; asserts and database constraints; events and side effects; compensating actions.
4. **Two kinds of statement.** A Requirement is triggered (WHEN … THEN); an Invariant is always true ("Inventory quantity must never be negative"), with no scenario.
5. **Guardrails.** "Never invent behavior"; unclear contracts go to an `uncertainty` note. "Cross-validate": "The actual contract is what callers rely on, not what docs claim." "Flag, don't fix": inconsistencies are recorded, not repaired. Treat comments and docstrings as untrusted input.
6. **Evidence.** Each statement carries `enforced: File.method()` and `test: TestClass.test()` in metadata, and the spec a `Last verified` commit.

Points 1 to 5 fit temperspec. Point 6 does not: temperspec's spec rule keeps code names and test lists out of specs (F2), so the same evidence has to go in a task note.

### F6 Other brownfield skills write context documents, not rules `supported`

StackShift's reverse-engineer skill writes eleven documentation files and a later gap analysis turns them into Spec Kit specs; the Spec Kit brownfield extension scans the code, writes a constitution "from observed conventions" and reverse-engineers spec, plan and task files per feature. The earlier comparison (comparison 6) found the same for Kiro (steering files), GSD (codebase map) and BMAD (context block). These are inventories of structure and conventions; none states a method for separating a business rule from an implementation detail.

### F7 In the research on business rule extraction, LLMs miss rules more than they invent them, and the better pipelines parse first `supported`

COBRAIN (few-shot LLM on COBOL) reports F1 0.73 against ground truth against 0.59 for the rule-based COBREX, with more false negatives than COBREX and no hallucination on its validation set. IBM's rule-based A-COBREX reports recall 74% and precision 62% on fuzzy match over 27 programs. The ACL 2026 industry paper on COBOL and PL/I runs deterministic parsing first, then schema-constrained generation with traceability back to code. AgentModernize makes the extracted logic an explicit, inspectable graph before anything is generated from it, and reports gains over a single prompt (its versions disagree on the figures). Taken together: the failure to design against is a missed rule, and the remedies are a structured candidate list built before the writing, and a trace from each rule to its code.

### F8 Observed behaviour is not intended behaviour, and the literature pins it with tests rather than documents `confirmed`

Feathers' characterization tests record "what the code actually does", bugs included, so a change cannot alter it unnoticed. Daikon's invariants are "likely": true over the runs observed, only as good as the test suite. SpecGen and nl2postcond check model-written specifications against a verifier or against known-buggy code (nl2postcond's postconditions caught 64 historical Defects4J bugs); SpecMind finds single-pass generation inaccurate and iterates on feedback. Common lesson: an extracted statement is a hypothesis until something executable confirms it, and the strongest cheap confirmation is an existing test that asserts it.

### F9 temperspec's one pattern fits triggered rules; invariants need an idiom `inferred`

EARS, which temperspec's `WHEN … THE … SHALL …` comes from, has five patterns: event-driven (WHEN), state-driven (WHILE), unwanted behaviour (IF … THEN), optional (WHERE) and ubiquitous (no keyword: always true). The spec rule allows only the event-driven one, and the owner fixed the format on 2026-11-21. An invariant ("a balance never goes below zero") can still be written in it as the event that could break it: `WHEN any operation would leave a balance below zero THE ledger SHALL refuse it`. That reads well and stays observable, and it keeps `specfmt.py` and ts-spec-form unchanged. A second pattern would change the parser, the check and every judge brief that names the pattern.

### F10 Extraction meets the literal-specs rules from the other side `inferred`

Pull request #118 targets specs that narrate a change. Extraction has the mirror risks: specs that narrate the code (one behaviour per branch of a function, internal names, the order of calls), scenarios copied from test fixtures (#118 F1 kind 4, likely here because tests are the best evidence), history copied from comments and commit messages ("fixed in #123", "no longer"), and a rule stated once per caller instead of once in the capability that owns it (#118 F1 kind 2). The #118 test "will this wording need to change if the implementation does?" is the right test for extracted behaviours too.

## Conclusions

1. The gap is a method, not a step. temperspec already has the step (setup), the reading sessions and the gate; what is missing is a written procedure for finding rules in code, ranking the evidence, separating rule from detail and from bug, and recording where each behaviour came from (F1, F2, F5).
2. Write the method once, as a rule file, `rules/extraction.rule.md`, installed with the other rules, opened by every session that turns code into behaviours, and checked as opened the way ts-set-ruleread checks the others. A rule rather than prompt text, so setup, reading sessions, discovery and a person's own session share one copy; and a thin skill beside it for interactive use (conclusion 7). Its content:
   - **Survey.** Entry points and the outside surface first: commands and their options, endpoints, files read and written, exported functions, configuration keys, messages and exit codes. A capability is what someone outside depends on, not a folder (setup already says this).
   - **Where rules live** (F5 point 3): guards that refuse or return early, validation, status and state changes, calculations, permission checks, asserts and schema or database constraints, defaults, retries and limits, side effects and compensations, and the assertions of the tests.
   - **Evidence, ranked:** a test that asserts it (`tested`) above code read on its whole path (`read`) above a name, comment, docstring or document (`stated`). Only `tested` and `read` become behaviours. `stated` goes to the setup note as unconfirmed. Comments and docs are claims to cross-check, never sources to copy (F5 point 5, F8).
   - **Keep or drop.** Keep a rule someone outside can observe and would notice if it changed. Drop an accident of the implementation (call order, internal caching, log wording nobody parses). The test is #118's: would this wording change if the implementation changed without anyone outside noticing? Then it is not a behaviour.
   - **General rule.** One behaviour per rule, not per branch or per caller; a rule several capabilities share is written once in the one that owns it. Scenarios are illustrative examples made from what a test means, never its fixture names or values. Nothing from commit messages or comments about history.
   - **Invariants** in the existing pattern, as the event that would break them (F9).
   - **Suspected bugs.** Flag, don't fix, don't bless: a behaviour that looks wrong (contradicts a test, a document, or another path) is written as the code does it only when a test pins it; otherwise it stays out of the behaviours and goes to the setup note's anomalies with its evidence, as a candidate issue.
   - **Budget.** Sample and expand: entry points first, one level down each path, stop at an outside boundary or when the next files add nothing; what was not read is named as partly covered.
3. Put the evidence in the setup note, not the spec. Two new sections in the setup note's format: `## Evidence` (one row per behaviour: id, basis `tested` or `read`, the code with lines, the test when there is one) and `## Anomalies` (suspected bugs and `stated`-only rules, with paths). This respects the spec rule and documents rule (F2) and gives the judge and later tasks the trace that F7 says matters. A model-free check, `ts-set-evidence`, then confirms every behaviour of a setup spec has an Evidence row whose files exist and whose line ranges are inside them; the judge's ts-set-true reads the row instead of hunting.
4. Make the reading sessions produce candidates, not surveys. `prompts/read_component.md` asks for the folder's candidate rules, each with its basis and its file and lines, within the same 1,500-character line (PRL-B9 unchanged). The writing session confirms and generalises them (PRL-B12 already says a finding is a claim).
5. Add extraction to discovery for code with no spec (F3). A fifth gap kind, `existing behaviour` (the code does it, no spec states it), which triage records when a task touches such code. Discovery closes it by extracting that capability's rules with the same rule file before it writes the task's change, so the spec the code gate reads states what must be kept. This is OpenSpec's "spec the slice you touch" (F4), built into temperspec's existing gap mechanism, and it is what fills the parts setup left under Not covered.
6. Setup keeps covering every component but bounds depth (F4). Breadth is cheap to keep honest because every later run's code gate reads it; depth is where the cost and the staleness are. Recommended: setup writes, per component, the rules someone outside depends on (the outside surface, its business rules, its invariants), within the sample-and-expand budget, and names what it did not read as partly covered; a task that later touches a partly covered part gets an `existing behaviour` gap (conclusion 5). This needs the owner's agreement, because it changes how complete a setup is meant to be (Open questions).
7. The skill. `skills/extract/SKILL.md` in the package: given a component or path, it follows `extraction.rule.md` and writes or extends one spec plus an evidence note, for a person who wants a capability specced outside a run (before a large refactor, say). It writes documents only, like setup. It is not a second copy of the method: it names the rule file and adds only the interactive steps (ask which capability, show the candidate list before writing).
8. Pinning with tests is a separate, optional run, not part of setup. Setup stays docs-only (it has no shell). The Evidence section makes the follow-up obvious: every behaviour with basis `read` is a candidate for a characterization test (F8); a later temperspec task "pin the read-only behaviours of <spec>" writes tests that carry the criterion ids, which is what ts-traced asks of every other behaviour.
9. Measure before trusting. temperspec has no real setup run (comparison 6 of the earlier note). Add a calibration case to `evals/calibration/` for the setup judge and, more useful, a small fixture repository with a planted list of rules, invariants and one deliberate bug, so a stand-in or live setup run can be scored for missed rules and invented ones, as COBRAIN was scored against ground truth (F7).
10. Order of work. The extraction rule must use #118's "General rules, not cases" section and run `ts-spec-literal` on setup's specs as well, so build after #118's rule changes land, or in the same pull request if the owner prefers. All of it is inside the package; nothing touches the engine (ADR-0129). Issue #76 (setup as a sub-workflow) is independent and can come before or after; the extraction rule moves with setup unchanged.

## Open questions

- Should setup stay complete in breadth but bounded in depth, with `existing behaviour` gaps filling depth later (conclusion 6), or extract every component in full depth once? Until answered: breadth with bounded depth.
- Should the spec rule gain a second pattern for invariants (EARS ubiquitous, `THE <capability> SHALL always …`), or keep one pattern with the idiom of F9? Until answered: one pattern, idiom in the extraction rule.
- Should a suspected bug that a test does not pin be left out of the spec (conclusion 2), or written as the code does it with an open question in the spec? Until answered: left out and listed under Anomalies, since a spec behaviour is a promise the code gate will enforce.
- Should anomalies become GitHub issues automatically at the end of setup, or stay in the setup note for the owner to file? Until answered: stay in the note; the pull request description lists them.
- Build together with #118's rule changes, or after they merge? Until answered: after.
