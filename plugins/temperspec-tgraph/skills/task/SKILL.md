---
name: task
description: Write a task that a temperspec run can take, with numbered acceptance criteria, and start the run. Use when the user wants to build, fix or change something with temperspec, asks how to phrase a task for it, or a run ended blocked because the task had no acceptance criteria.
---

# Write a temperspec task and start the run

A temperspec run is measured against the task's acceptance criteria and nothing else: triage copies them and every later gate proves them. A task without one ends blocked in triage. This skill gets the task into that shape with the user, then hands the start to the engine's `run` skill. It designs nothing: what the system should do beyond the criteria is the run's work.

## Steps

1. Ask what should be true when the work is done, in the user's words. Do not read the code to decide it for them.
2. Write each answer as one acceptance criterion: a numbered sentence that someone outside can observe and a test can prove. One result per sentence. No "works well", "fast" or "handles errors" without the event and the result. No file, function or class name unless someone outside depends on it.
3. Say which criteria are the user's and which you inferred, and drop each inferred one the user does not confirm. Never add a criterion to make the task look complete.
4. Ask whether the run delivers code or documents only. For documents only, the task says `docs only`.
5. Ask how much the run may ask them, and name what each value does:
   - `blocking` (the default): one pause after triage with the questions only the owner can answer.
   - `never`: no pause; the run takes the default of each question and lists it in the pull request under `Assumptions to confirm`. For overnight or pipeline runs.
   - `always`: the same pause, and it also asks whether the run read each gap right.
6. Write the task to a file the user names, or keep it as text: a title line, one paragraph of context, then `Acceptance criteria:` with the numbered list.
7. Start it with the engine's `run` skill: `tempergraph run temperspec <the task text or the file's path>`, with `--set settings.conversation=<value>` when the value is not `blocking`. That skill checks before it spends, waits, and reports the exit.

## Limits

- The criteria are the user's decision. Offer wording; never settle what the system should do.
- Do not name a lane. Triage picks the quick lane by itself for a small fix that changes no spec, and a run never moves to a lighter lane.
- When the run pauses with questions, use the `answer` skill.
