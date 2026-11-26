---
name: extract
description: Write or extend a behaviour spec for existing code that no spec describes, by extracting its rules, invariants and business rules with their evidence. Use when the user asks to spec a component, module or path as it is now, for example before a large refactor, outside a temperspec run.
---

# Extract a spec from existing code

The method is in `extraction.rule.md` (in `.claude/rules/temperspec/` of the repository, or the plugin's `rules/` folder when the repository holds no rule files). Open it and `spec.rule.md` with the read tool before you write; this skill adds only the steps of an interactive session and repeats neither.

## Steps

1. Ask which capability to spec, unless the user named a component or a path. Search the existing specs for it first: a rule that belongs to an existing spec goes into that spec, not into a new one.
2. Survey and read the code as the extraction rule says, within its budget, and collect the candidate rules, each with its basis (`tested`, `read` or `stated`) and its file and lines.
3. Show the user the candidate list before you write: the rules you will write as behaviours, the anomalies (suspected bugs and rules only stated) and what you did not read. Take their corrections.
4. Write or extend the spec, named for its capability, with behaviours from `tested` and `read` rules only and the acceptance criteria that prove them, and its `Depends on` rows: each spec a behaviour links and each outside thing the code needs.
5. Write the evidence beside the spec in a research note (`<capability>-evidence.rsrch.md` in the research folder beside the specs): one row per behaviour with its basis, the code with lines and the test, then the anomalies with their paths. The spec states the rules only.
6. Tell the user which behaviours rest on code read but not tested: each is a candidate for a test that carries its criterion id.

Write documents only: no code, no tests, no configuration. Do not run git.
