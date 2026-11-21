# Documents of a repository that uses temperspec

These rules hold for every document below. Each document type has its own rule file next to this one.

## Folders and names

| Document | Folder | File name ends with | Rule |
|---|---|---|---|
| Behaviour spec | `docs/specs/` | `.spec.md` | `spec.rule.md` |
| Decision record | `docs/adr/` | `.adr.md` | `decision.rule.md` |
| Research note | `docs/research/` | `.rsrch.md` | `research.rule.md` |
| Plan | `docs/plans/` | `.plan.md` | `plan.rule.md` |
| Triage note, hand-off, code report | `docs/tasks/` | `.triage.md`, `.handoff.md`, `.report.md` | `task-notes.rule.md` |

A repository that already keeps these folders elsewhere (for example under a plugin's `docs/`) keeps its place; the folder names `specs`, `adr`, `research` and `plans` and the endings stay the same. `README.md` and `index.md` are exempt from the endings.

A new document takes a name that cannot collide with another branch: a short slug of its subject (`session-expiry.spec.md`), or the task id and a topic (`TASK-12-token-storage.rsrch.md`). Never take "the next number" of a folder.

## Truth ranking

When two sources disagree, the higher one wins and the lower one is the defect:

1. The task's acceptance criteria.
2. Specs and decision records.
3. The plan.
4. The code.

A change to code that makes a document false changes that document in the same run.

## Rules against cascade edits

1. A document carries no version, date, status, change log or list of the tests that prove it. Git holds the history.
2. A link lives in one place. No document lists "who links to me".
3. An index is generated from the files. Nobody edits an index by hand.
4. A link names an id (`SES-B3`) or a file path, never a section number. An id is never reused and never renumbered.
5. A shared term or type is defined once, in the spec that owns its behaviour. There is no central file that every change has to touch.
6. A spec is edited only where a behaviour or an acceptance criterion changes. Any other edit to a spec is collateral and is reported.
7. A line says what the system does now. A change rewrites the lines it affects and appends no note about the change.
