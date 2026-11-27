# Cloud threads

Run files from `temperspec` runs that Claude Code cloud threads of this project ran on 2026-11-22 and 2026-11-23 (release 3 tracks R3-T2, R3-T3, R3-T5 and R3-T8, engine 0.2.0, executor `claude`). Each cloud thread ran in a short-lived container that no longer exists, so no home folder, state root, `stats/` table or session record survives. What survives is the record that the thread "Assess self-improvement in overnight runs" saved to the project's shared folder (`loop-assessment/<thread>.txt`) on 2026-11-23: one text file per run that pasted whole engine files under headings, next to command output and notes.

This folder holds only those pasted engine files, cut out of the text files without any change to their lines:

| file | threads | content |
|---|---|---|
| `runs/temperspec/<thread>/exit.json` | 7 | `exit_code`, `reason`, `schema_version`, as on `pi5-a`. |
| `runs/temperspec/<thread>/loop.jsonl` | 7 | Events of the improvement loop, same schema as on `pi5-a`. Each file runs from `loop_started` to `loop_summary`; there is no review text. |

`MANIFEST.json` in this folder gives, for each file, its bytes, lines, sha256 and the heading of the text file it came from. The repository-wide `MANIFEST.json` and `tools/collect.py` were not used or changed: the collector needs the live state root, which is gone.

Threads: `r3-t2-1`, `r3-t2-1a`, `r3-t2-2`, `r3-t2-3`, `r3-t3-1`, `r3-t5-1` (exit only: the run was stopped before its loop started), `r3-t5-2`, `r3-t8-4` (loop only: its text file gave the exit in a sentence, not as the file). `r3-t8-1` to `r3-t8-3` never reached a final exit and left no file.

## Left out

- The other sections of the same text files: tails of `run.jsonl` (judge prose, reasons), output of `improve review show`, `improve show`, `status`, `attention` and `improve backlog`, and the notes of the thread. They are excerpts or command output, not files, and hold free text.
- `live-checks/` in the shared folder: pytest reports of the live checks, authoring and verify reports with finding text, and three judge session transcripts (`raw.jsonl`) of live check L-32. None of it is run statistics in the form of this branch, and transcripts are left out here as on `pi5-a`.
