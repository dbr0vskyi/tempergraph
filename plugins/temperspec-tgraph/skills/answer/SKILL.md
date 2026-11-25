---
name: answer
description: Walk the user through the questions a paused temperspec run asks its owner, then resume the run with their answers. Use when a temperspec run exits paused after triage, or the user asks what a temperspec run is waiting for.
---

# Answer a temperspec run's owner questions

A run on `blocking` or `always` pauses once, after triage and before discovery, with at most 20 questions. Each owner decision is a choice with two to four options and a default; on `always` there is also one `right` or `wrong` question for the run's reading of each gap. Every answer is the user's. You explain and record; you never choose.

## Steps

1. Find the run and its questions: `tempergraph status <thread>` names the pause, and the run's triage note (`docs/tasks/<task id>.triage.md`, or the `tasks/` folder beside the repository's specs) holds, under `## Owner decisions`, each question with its `Options:`, its `Default:` and `If wrong:`.
2. For each owner decision, in the note's order, show the user the gap it belongs to in one line, the question, every option as written, which option is the default and what the note says a wrong default costs. Then ask for their choice. Do not recommend an option unless the user asks what you would pick, and then say that it is your opinion.
3. For a reading question, show the gap row and what the run understood, and ask `right` or `wrong`. A reading answered `wrong` keeps the run paused: the user either corrects the task and starts again, or changes the answer to `right`.
4. A question the user does not want to answer stays open. Say what happens to it: at the deadline (86,400 seconds unless the run was started with another) the run takes its default and lists it in the pull request under `Assumptions to confirm`.
5. Resume with the answers given, as the engine's `run` skill says for a pause, with `--relayed`: one `--decision answer:<name>=<value>` for each answer, where the name is the gap's id in lower case (`g2`) and the value is the option's letter, or `right` or `wrong`. Example: `tempergraph resume temperspec <thread> --decision answer:g1=b --decision answer:g2=a --relayed`. Answers that leave a question open leave the pause open for it.
6. Report what the run did next. The pull request lists each answered decision under `Decided` with the words of the option chosen.

## Limits

- Never answer for the user, never pick the default for them and never resume without their answers.
- Do not edit the triage note or the run's state. A wrong question is fixed by correcting the task and starting a new run.
- Do not apply the deadline yourself: `resume --apply-deadline` is refused before the deadline, and after it the choice to go on with defaults is the user's.
