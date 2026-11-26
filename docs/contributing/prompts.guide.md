# Prompts for contributors

Briefs for a coding agent's session, for the work [CONTRIBUTING.md](../../CONTRIBUTING.md) describes. Each one states the goal, what is already known, the scope and what to report. Fill the angle brackets.

## A request file for one slice

Use it as the input to a temperspec run, or as your own checklist when you build by hand. One slice per file, with only that slice's acceptance criteria.

```text
<One line: what changes, and the issue number>

<Two or three paragraphs of context: what the system does today, with the spec
file and behaviour ids that state it (for example SIL-B18), and the evidence
that it is wrong or missing. Name files and line numbers you have checked.>

Acceptance criteria
1. <A behaviour stated so a test can prove it. One behaviour per criterion.>
2. <...>
N. The specs changed state what the code does and name no workflow; each new
   test carries the id of the criterion it proves.

Out of scope
- <What a reader might expect and will not get, and where it is tracked.>

Likely files
- <source files, spec files, test files>

Rules that bind this change
- The engine names no workflow. An engine capability is stated and tested
  with an engine fixture.
- At least one test per criterion drives a real fixture run. A test must not
  hand-write a record in a shape the system never emits.
```

## Independent review of a diff

Use it on a finished diff, in a fresh session that has not seen the author's plan, notes or report.

```text
You are an independent reviewer of a delivered change. Read-only: do not edit,
commit or push. You may run single test files to prove a defect.

The change: <how to produce the diff, for example
git diff $(git merge-base HEAD main) HEAD>.
The request it was built from, with its acceptance criteria: <path>.

Judge it only from the diff, the criteria, and the code and specs the diff
touches. Do NOT read the author's plan, notes or report before forming your
findings: the point is a reader who has not seen the author's account.

Look for:
- behaviour that does not meet a criterion;
- defects the tests do not catch: error paths, failures between two writes,
  the same input arriving twice or in the other order, timeouts, empty input;
- for every record, file or message the change reads, open the code that
  writes it and compare the fields. A test that passes only on a shape the
  system never writes is a blocker;
- who else can write each input, and how many calls one run makes;
- specs that disagree with the code; tests that assert nothing real.

Report: verdict (merge / merge with follow-ups / blocked), then numbered
findings, most severe first, each with file:line, what is wrong, the evidence
(a failing input or a quoted line) and the fix you would ask for. End with one
paragraph: which of these a deterministic check could have caught.
```

## Read-only diagnosis of a failing test

Use it when tests fail on your machine and pass in CI.

```text
Diagnose, read-only, why <these tests> fail on this machine while CI passes
them. Do not edit tracked files, do not commit, do not run the whole suite;
run only these tests with a single worker.

Hypotheses to test, in order:
1. Something inherited from the caller's environment (variables, the home
   folder, a sign-in or credentials file, the temporary folder's path).
2. A difference of platform or interpreter version.
3. <your own>

For each, change one thing and rerun: an empty environment, an empty home
folder, a different temporary folder. Never print a secret's value.

Report: the assertion of each failure in one line; the root cause with the
run that proves it (passes when X is removed); whether it is a test-isolation
defect or a product defect; the smallest workaround; and a five-line issue
draft (title, what happens, where, done when).
```

## Replay a rule on real records before switching it on

Use it before a new rule may act outside the machine, for example before the improvement loop may file issues.

```text
Read-only, with no network call: replay <the new rule> against the records
this machine holds under <state root>, using the engine's own functions with
the outside service replaced by an in-memory stand-in.

Report what the rule would have done over the whole history:
- how many <actions> it would take, listed by cause with the number of runs;
- for each, your verdict: a true fault, a duplicate of something a person
  already filed (name it), or noise (say why);
- what bounds the number of actions per run and per day.

State plainly whether the bar is met: no noise, no duplicate, a bounded
number of actions. Then the exact steps to move from "held" to "dry run",
without doing them.
```

## Merge a branch that touched shared files

Use it when two branches both changed generated files or added spec ids.

```text
Merge <branch> into <trunk> with --no-ff. Do not push.

Conflicts:
- Generated files (stamps, diagram digests): never resolve by hand. Take
  either side, finish the merge, then regenerate with the merged tree's own
  engine and include the result.
- Specs: keep both sides' behaviour. If both sides added the same behaviour
  or criterion id, renumber the incoming side consistently across spec, tests
  and code, and list every place you changed.

After the merge, read the merged file around every hunk of both sides in
<files several branches edited> and check that each side's record fields and
writes still hold. Run every test file either side touched, together. Two
changes that each pass their own tests can still break each other's.

Report: the commit, each conflict and how it was resolved, the semantic
checks, test counts.
```

## Answering a pause

Use it as the feedback text that goes with `proceed` or `retry` on a paused run. Open the plan, test or commit the pause is about before you write it.

```text
Decision on <row or criterion> (from the truth ranking: <which source wins>).

<The fact you checked, with where you checked it: the commit that changed the
file, the lines of the test that hold the assertion, the command and its
result.>

<Exactly what to do now, and what to leave alone: "rewrite the text of row
4.4 to say X, mark it, change nothing else". If you ran a command the session
cannot run, say what is now in the working tree and that it must not be
edited.>

<Which reported deviations are accepted.>
```
