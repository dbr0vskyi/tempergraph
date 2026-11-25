# A failing command is environmental when the base fails it too, unless the change touches it

## Context

The code check fails on any verification command that does not exit 0 and the gate retries the code step, which cannot help when the failure was there before the change. Run `r3-t1-1b` retried four times, about 2 USD, on an environment fault, and run `r3-t4-1b` met 590 errors from its container's signing fault ([research `does-the-improvement-loop-find-what-a-reviewer-finds`](../../../tempergraph/docs/research/does-the-improvement-loop-find-what-a-reviewer-finds.rsrch.md) F1 and H1; issue 54).

What the code does today, read in `workflow/temperspec/checks.py` and `prompts/code.md`:

- Each command of the plan runs once on the workspace, with reuse, and fails the check on any exit but 0 or on a run that did not finish (`_verify`).
- When the step reports `tests_passed: no`, the check fails `ts-code-verify` and runs no command at all (`code_check`). The prompt tells the step to note a command that already fails before its first change under Deviations and not to repair it (line 31), and `tests_passed` is `no` unless every command exited 0 (line 40). A step that meets a failure present before the change therefore reports `no`, and the gate retries it without looking.
- A check FAIL marked environmental escalates at once, with no judge and no retry (HUM-B7, BUD-B11, CHK-B14). The engine can now run a command at the run's base commit and reuse the result for the visit (CHK-B18 to CHK-B20, [the engine's decision](../../../tempergraph/docs/adr/a-check-runs-a-command-at-the-runs-base-in-a-checkout-the-engine-makes.adr.md)).

The task's first criterion says a command that fails at the gate and also at the base is environmental. Its second says a failure that no changed file touches (no changed path in its output, and the same failure at the base) is environmental. The two overlap: read literally, every case of the second is a case of the first. The way they differ in practice is in what each guards against. A command that names a file the change creates, such as `pytest tests/test_new.py`, fails at the base with another exit code (pytest exits 4 for a missing file) and fails at the gate for a real reason, and the check must not escalate it. A base run is also not a perfect base: a package installed in editable mode loads the workspace's code, and a failure present before the change can hide a new one. The run record keeps only the last 40 lines of a command's output and any summary lines the prefix declares (CHK-B12).

## Decision

We will have the code check run every verification command itself, whatever the step reported, and judge a command that finished at the gate with a non-zero exit by one more run of it, at the run's base commit, once per visit:

- The check returns an environmental result for the command when its run at the base finished with a non-zero exit and either the exit code is the same as at the gate, or no path the run changed appears in the last lines the command printed at the gate (written from the repository root or from the folder the command ran in).
- The command fails the check as a retry in every other case: it exits 0 at the base, it did not finish at the gate or at the base, or the base could not be run (no base commit, no folder for it there, not enough time).
- The check as a whole is environmental only when every failing finding is such a command. When another finding also fails, the check stays an ordinary failure that lists only what the code step can fix, and the evidence still names the environmental command.
- The evidence names each failing command with its exit code at the gate and at the base and the reason it was judged environmental, caused by the change or not compared.

## Options considered

### A. The same exit code, or no changed path in the output (chosen)

For: it escalates the incidents that started this, where the same failure appears at both places whatever the output names; it keeps a retry for a command that fails at the base for another reason and names a changed file, the case of a new test file; it satisfies both criteria in the cases each states. Against: it narrows the first criterion in one corner, a base failure with a different exit code and a changed path in the output, which it retries; it compares exit codes, not failures, so a new failure behind an old one with the same code escalates.

### B. Environmental whenever the base run also fails

For: the first criterion read literally, and the simplest rule. Against: a command that names a new file fails at the base with exit 4 and would escalate every real failure of it; a person would answer a pause for a failure the step could fix.

### C. Environmental only when the exit codes match and no changed path appears

For: the second criterion read as a rule, and the fewest escalations by mistake. Against: the failure that started this lists hundreds of failing tests, and a changed or new test file among them puts a changed path in the output, so the check would retry again on the fault it was written for.

### D. Compare the failing lines of the two outputs

For: the closest to "the same failure". Against: the lines carry timings and temporary paths, each tool prints failures its own way, so the check needs a parser per tool; and the record keeps only the last lines.

### E. Judge by the changed paths in the output alone, with no base run

For: no second run. Against: it cannot tell a failure present before the change from one the change caused in a file the output does not name; the task asks for the comparison with the base.

## Consequences

- A failure the base shows too stops the run at a pause with the evidence in hand, with no retry and no judge, instead of costing retries. A person answers it.
- The error direction is safe: a wrong environmental result is a pause for a person, never a failure accepted in silence; a wrong retry is what happens today.
- A new failure behind an old one with the same exit code escalates, as the first criterion asks. The evidence names the changed paths the output shows, so the person can see it.
- A step's report of failing tests no longer ends the check. The gate runs the commands itself, and a long command runs at the gate that the report used to skip.
- A command runs a second time only when it failed at the gate, and the result is kept for the visit, so a passing command costs nothing and a retry in the same visit costs nothing more. A person who repairs the environment and resumes in the same visit gets the kept result; a trip back starts a new visit.
- The comparison shares the check's limit, 1800 s on the code gate. A suite that takes more than half of it cannot be compared and is retried as before; the plan may raise the limit.
- The outcome gate's own run of the plan's commands is not part of this decision; the task names the code check.

## Revisit when

The first runs show an escalation that a retry would have fixed, or a retry the base run would have saved.
