# A rule the CLI attaches by its paths counts as opened

## Context

[`a-step-check-confirms-that-each-rule-file-its-prompt-names-was-opened`](a-step-check-confirms-that-each-rule-file-its-prompt-names-was-opened.adr.md) counts a rule file as opened only through the read tool. Claude Code already attaches a rule of `.claude/rules/` to the session: one with no `paths` front matter from the start, a path-scoped one when the session first reads a file its `paths` match. The check then asks for a second copy of text the session holds (issue #225). This record narrows that record's second decision point, a rule file is opened by a call of the read tool; the rest of it stands.

## Current state

- Every rule file but `documents.rule.md` starts with a `paths` front matter (`rules/*.rule.md`; the repository's `CLAUDE.md`).
- The rule-file check reads only read-tool calls on the rule's name (`_opened`, `workflow/temperspec/checks.py`).
- Over the session records of nine carried runs (245 step and retry sessions), 105 of 241 rule reads, about 741k characters, were of rules the CLI had already attached by its `paths` at that point; discovery 286k, expand 181k, code 178k, plan 50k, triage 46k. Measured from each run's `activity.jsonl` by matching read targets against the rules' current `paths`.

## Forces

- C1 (constraint): a session writes no document of a type before it holds that type's rule. Source: SRC-B1
- C2 (constraint): a finding names the rule and never quotes a call of the session. Source: SRC-B9
- F1: the session should not read text it already holds
- F2: the check should need nothing the record does not show

## Options considered

### A. Count a rule the CLI attached (chosen)

How it works: a rule with no `paths` counts as opened; a path-scoped rule counts when an ok read of a file it governs comes before any write of one. A first write before that fails, naming the rule and the file.
For: removes the duplicate reads (F1); the rule's own front matter is the map, read from the file the check already finds (F2). Against: the attachment is inferred from paths, not seen in the record (F2).

### B. Keep the read-tool rule

How it works: no change.
For: the opening is seen in the record (F2). Against: about 40% of rule reads repeat attached text (F1).

## Decision

We will take option A, as [SRC-B13](../specs/session-record-checks.spec.md) says.

## Decision rationale

C1 holds: a write that comes before the rule arrived fails. C2 holds: the finding names the rule and the governed file the session wrote, never a call. F1 is met. F2 is given up in part: the record shows the reads the attachment follows, not the attachment itself, because the CLI does not report which rules it loaded.

## Consequences

A step that reads an existing plan or spec before writing passes without opening its rule. A step that creates a document type the repository holds none of must still open the rule first, which the prompts already say.

## Risks

- The CLI stops attaching path-scoped rules on a read, or changes its matching. Limited by: a session that opens the rule still passes. Noticed by: format findings after a pass of the rule-file check.

## Assumptions

- A1: the CLI attaches a path-scoped rule on the first read of a matching file and a pathless rule at session start, as its documentation says. Check: a probe session that reads a matching file and reports the rule's text unprompted. If wrong: steps write documents without their rule, and the format checks catch it a retry later.

## Revisit when

- Claude Code version reaches 3.0.0.
- A format finding follows a pass that counted the rule as attached.
