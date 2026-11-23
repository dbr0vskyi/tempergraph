---
name: schedule
description: Schedule a tempergraph workflow to run once or on a recurrence, and manage those schedules. Use when someone asks to run a workflow every day, every weekday, at a time, or on a calendar, to list, pause, resume, skip, fire or remove a schedule, to see scheduled runs, or to start the trigger that makes schedules fire. Never uses Claude Code's scheduled tasks or /loop.
---

# Schedule a tempergraph workflow

The engine owns the timing: it parses the words, computes the slots, asks about an ambiguity and fires the runs. You
translate the person's words into one `schedule` call, show what the engine understood, and save only on the person's
yes. This skill holds no state: every fact is in the engine's schedule store, read with `tempergraph schedule list` and
`tempergraph schedule show <id>`. Every schedule stays possible with the CLI and exact formats alone.

## Rules

- **Parse first, show the echo verbatim.** Call `tempergraph schedule parse "<phrase>"` (or the exact format) and show its
  echo as printed. Never paraphrase the sentence, the zone or the next slots.
- **Ask about each `needs`.** Exit 3 lists the readings of an ambiguous phrase. Ask in the person's terms
  ("morning or evening?"), then pass the chosen reading with `--choose`. Never pick one for them.
- **A run cost cap is required.** Say the cap the schedule will run under. Pass `--run-cost-cap <usd>` unless the
  workflow declares its own. For a recurrence, propose a period budget from `tempergraph stats --projection` and pass it
  with `--budget month:<usd>`.
- **One yes, then save.** Ask once, on the echo, the caps and the policies (`--catch-up`, `--overlap`, `--max-live`,
  `--pause-after-failures`). Save with `tempergraph schedule add <workflow> <request…> --when "<phrase>" --run-cost-cap <usd> --yes --relayed`.
  `--relayed` carries the person's decision; without a person turn in this session the engine refuses
  (`schedule_not_by_person`): tell the person to run the command themselves.
- **Never fire a run from Claude Code's own scheduled tasks or `/loop`.** A schedule is the engine's: its tick fires it.
  Never create a Claude Code scheduled task for it, and do not use `/loop` to run a workflow on a timer.
- **A schedule never grants.** A schedule cannot carry a tool grant; a pause of a scheduled run waits for a person.

## Procedure

1. **Find the run.** `tempergraph list` gives the catalog; `tempergraph run <workflow> --check <request…>` shows the
   questions the request still needs. Ask them, as the run driver does.
2. **Translate the timing.** Use an exact format when the person gave one (`--at`, `--rrule`, `--every`, `--cron`, `--tz`),
   else pass their phrase unchanged with `--when`. Ask for the zone when it is not the machine's.
3. **Parse.** `tempergraph schedule parse --when "every weekday at 8:00"` (add `--json` to read it). Show the echo.
4. **Check without saving.** `tempergraph schedule add <workflow> <request…> --when "<phrase>" --run-cost-cap <usd> --check`
   prints the echo and saves nothing.
5. **Save.** `tempergraph schedule add … --yes --relayed` after the person's yes. Say the schedule id it prints.
6. **Offer the trigger.** A saved schedule fires only while something calls the tick. Run `tempergraph schedule trigger status`;
   when no trigger is alive, offer `tempergraph schedule loop --detach` (a portable loop in the background) and name the
   optional adapters once: `tempergraph schedule trigger install --os` starts it at login, the plugin's session hook
   starts it when `schedule.loop_autostart` is on, and any scheduler can call `tempergraph schedule tick`.

## Managing schedules

- See them: `tempergraph schedule list`, `tempergraph schedule show <id>`, `tempergraph schedule history <id>`.
- Change one: `tempergraph schedule edit <id> --when "<phrase>" --yes --relayed` (its workflow and repository are fixed;
  remove it and add another to change them).
- Stop and start: `tempergraph schedule pause <id>`, `tempergraph schedule resume <id> --relayed`,
  `tempergraph schedule skip <id> --next`, `tempergraph schedule remove <id> --yes`.
- Run now: `tempergraph schedule fire <id> --yes --relayed`. It spends, so confirm the cap first.
- Look back: `tempergraph schedule runs --schedule <id>` lists every fire on the machine with its outcome and cost.
- Move it to a pipeline: `tempergraph schedule export <id> --for github-actions` (or `gitlab-ci`, `crontab`) prints a
  snippet and keeps nothing; a zone with daylight saving needs `--pin-offset` or a UTC rule.
- Orchestration targets are release 4: `schedule add --orchestration` is refused (`not_in_release`).

Eval cases for this skill are in [references/eval-cases.md](references/eval-cases.md).
