# A step's check confirms that each rule file its prompt names was opened

## Context

Triage and plan left `documents.rule.md` unopened in every reviewed run, and a short discovery retry got the hand-off's section order wrong after only searching `task-notes.rule.md` (issue 129, from [R-160](../../../tempergraph/docs/research/R-160-does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md) F7). The issue allows two answers: put the part of the rule the step must follow into its prompt, or have the check confirm from the session record that the named rule file was read. Neither is built.

What the package holds today, read in it:

- Seven prompts name rule files: `setup.md` line 9 (`spec`, `task-notes`, `documents`), `triage.md` line 13 (`task-notes`, `documents`), `discovery_short.md` line 14 (`task-notes`, `documents`), `discovery.md` line 14 (`spec`, `decision`, `research`, `task-notes`, `documents`), `plan.md` line 15 (`plan`, `documents`), `expand.md` line 10 (`plan`) and `code.md` line 13 (`task-notes`, `plan`). Each says the files are in `.claude/rules/temperspec/` of the repository, or already in the session's instructions when they are installed for the whole machine. `prepare` copies them into the repository unless the repository or the machine holds them (`workflow/temperspec/routing.py` lines 86-100).
- Three prompts tell the session to read: discovery ("Read the rule of a document type before you write a document of that type"), short discovery ("Read the hand-off part of `task-notes.rule.md`") and setup ("Read the spec rule before you write"). The other four only name the files, and the discovery prompt says it does not repeat the formats.
- The formats live once, in the rule files; `workflow/temperspec/specfmt.py` reads the same formats and `tests/test_temperspec.py` holds the two together (the repository's `CLAUDE.md`). A repository that already has rule files keeps its own.
- The package's checks already read the package's own prompt files for what they say (`PROMPT_SAYS`, `workflow/temperspec/checks.py` lines 65-101).
- A retry runs a fresh session that is told what was rejected and not resumed ([PRM-B5](../../../tempergraph/docs/specs/04-prompt-rendering.spec.md)), so a file opened in an earlier attempt tells the retry nothing.
- The short discovery prompt limits the visit to 10 files (`prompts/discovery_short.md` line 19).
- The engine now gives a check the attempt's tool calls, each with its capability (`read` for the read tool, `search` for a search) and target ([CHK-B24](../../../tempergraph/docs/specs/75-check-contract-and-command-runs.spec.md)), and none for a stand-in executor, a preview or hidden tool inputs ([CHK-B25](../../../tempergraph/docs/specs/75-check-contract-and-command-runs.spec.md)).

## Decision

We will take option A: keep the rule text in the rule files and have each step's check confirm from the session record that the session opened every rule file its prompt names, as [the spec](../specs/session-record-checks.spec.md) says:

- A rule file is named when its file name appears in the step's prompt file; the check reads the prompt for the names, so no second list can drift from it.
- A rule file is opened by a call of the read tool that ended without an error and whose target ends in the file's name, in any folder: a session that opens another copy of the file, such as the package's own, passes. A search of the file, or a listing, never counts, and a partial read counts because the record keeps no range.
- Only a rule file the repository holds under `.claude/rules/temperspec/` is asked for. When it holds none of them, their text is installed for the whole machine and is in the session's instructions, so the criterion does not apply and says so.
- The record is the attempt's own session. A retry opens the files again.
- Each prompt that names a rule file tells the session to open it with the read tool and that a search is not opening it; the short discovery prompt says the rule files do not count in its 10 files.
- No prompt carries rule text.

## Options considered

### A. The check confirms the opening, and the prompt names the file and says to open it (chosen)

For: the rule text stays in one place and a repository's own rule files stay authoritative; a miss costs one read, not a rewrite; the retry prompt names the file; it uses the engine's record. Against: an opening proves the file was read, not that it was followed (the format checks and the judges still grade that); it asks for files a given run may not need, such as `decision.rule.md` in a discovery that writes no decision; it does nothing where the engine gives no record.

### B. Carry the part of the rule the step must follow in each prompt

For: the session has the text without a read, and the check needs no record. Against: seven prompts would copy text that the rule files hold and `specfmt.py` parses, so two copies can drift and a repository's own rules would be overruled by the prompt's; the discovery prompt says on purpose that it does not repeat the formats; which part a step "must follow" is itself a judgment that a copy freezes; and a copy cannot be checked against what the session did.

### C. Ask only the rule files of the types the session wrote

For: it follows the discovery prompt's own wording, so a discovery that writes no decision is not sent back for not opening `decision.rule.md`. Against: it needs the map from a rule file to the documents it governs, which is the `paths` header of each rule file and none for `documents.rule.md`, and a glob match on the record's targets: a second thing that can be wrong, to save two small reads.

### D. Leave it to the format checks and the judges

For: nothing to build. Against: it is today's behaviour; a step that never opened the rule is found only by a wrong format, after a session's cost, as in the runs the issue cites.

## Consequences

A step that skips a rule file fails its gate with a finding that names the file, and the retry costs one session. The cost of a miss is highest on the discovery and code steps, which are the largest sessions; the prompts say to open the files first, which limits it. The rule-file criterion does not apply, and says so, in a repository without the rule folder, with a stand-in executor, in a preview and under `observe.tool_inputs = off`; so on a machine with the rules installed for the whole machine this decision adds no check: those files are outside the workspace, where the record shows only `<outside workspace>` and the check cannot tell which file a read opened.

Taken without the owner, who is away, and open to change: reading by another folder's path with the same name counts; a partial read counts; the discovery prompt's five rule files are all asked for (option C is the way to ask fewer); a finding names the rule file and never a call of the session (SRC-B9 in [the spec](../specs/session-record-checks.spec.md)).

## Revisit when

A discovery retry is caused only by a rule file the session had no document of that type to write, or the engine can say what part of a file a read covered.
