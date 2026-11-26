# Owner questions

## Purpose

The one pause a run makes for the owner. When the conversation value is `blocking` or `always` ([conversation](conversation.spec.md)), the run asks the owner every question it has for them in a single pause, after the reading sessions of discovery and before its writing session: each owner decision of the triage note is a typed choice question with its options and its default, each question that blocks the change and that a reading session could not answer is a question the owner answers in words, and `always` adds a question on the reading of each findable gap that no spec already answers. The owner is asked last, so that nothing is asked that the code or the documents answer. The owner, a script, or the agent that started the run answers by terminal, by file or by decision words; what the agent cannot answer stays open for a person; once the deadline has passed each open question takes its default. A run with nothing to ask makes no pause. Discovery closes each owner decision on its answer, or on its default when it has none, and says in its hand-off which it did. How an ask takes, checks and keeps answers and applies a deadline is the engine's ([ASK-B5](../../../tempergraph/docs/specs/ask-unit.spec.md), [FLX-B8](../../../tempergraph/docs/specs/flow-extensions.spec.md)) and is not restated here. Whoever starts a run and whoever answers its questions depend on it. Part of the [overview](overview.spec.md); the units are `owner_questions`, a script with no model session and no gate that lists the questions of the pause after the reading sessions and says whether there are any, which this spec describes, the route that pauses or skips ([ask_route](ask-route.spec.md)) and the pause itself ([ask_owner](ask-owner.spec.md)).

## Behaviours

### OWQ-B1 The run pauses once for its questions

WHEN a run whose conversation value is `blocking` or `always` ends the reading sessions of discovery with at least one question to ask THE workflow SHALL pause the run once, before the writing session of discovery, with every question in that one pause.

- GIVEN `blocking` and a triage note with three owner decisions WHEN the reading sessions end THEN the run pauses once and the pause holds three questions
- GIVEN a triage note with three gap rows and a question to ask WHEN the run pauses THEN three reading sessions have ended and no writing session has started
- GIVEN `always` and a triage note with no owner decision and two findable gaps that no spec answers WHEN the reading sessions end THEN the run pauses once and the pause holds two questions
- GIVEN a pause with three questions WHEN the agent that started the run answers two of them with `--decision answer:g1=b --decision answer:g2=a` and leaves the third THEN the run stays in that pause, open for the third question, with the two answers kept ([ASK-B8](../../../tempergraph/docs/specs/ask-unit.spec.md))

### OWQ-B2 No question, no pause

WHEN a run has no question to ask for its conversation value THE workflow SHALL go on by the route the triage note names, with no pause.

- GIVEN `blocking` and a triage note whose `Owner decisions` says `None` and whose gaps are all findable WHEN triage ends THEN the run goes on to discovery with no pause
- GIVEN `never` and a triage note with two owner decisions WHEN triage ends THEN the run goes on to discovery with no pause
- GIVEN `always` and a triage note with no gap WHEN triage ends THEN the run goes on to the plan, or to the code step on the quick lane, with no pause
- GIVEN `always` and a triage note whose every gap row says `Covered by` WHEN triage ends THEN the run takes the short discovery visit with no pause

### OWQ-B3 Each owner decision is a choice question

WHEN the run pauses THE workflow SHALL put into the pause, for each owner decision of the triage note, one choice question named by the id of its gap row or uncertainty row in lower case, whose choices are the labels of the decision's options, whose default is the decision's default, and whose wording gives the row's id, the question and each option with its label.

- GIVEN an owner decision of gap G2 with the options a) 2, b) 1 and c) 78 and the default a WHEN the pause is shown THEN it holds a choice question `g2` with the choices `a`, `b` and `c`, the default `a`, and a wording that names G2, the question and the three options
- GIVEN owner decisions of gaps G1 and G3 WHEN the pause is shown THEN the questions come in the order of the triage note
- GIVEN an owner decision of the uncertainty row U2 with the options a) 2 and b) 78 WHEN the pause is shown THEN it holds a choice question `u2` with the choices `a` and `b`
- GIVEN an owner decision whose question and options together run past 500 characters WHEN the pause is built THEN the pause is shown, the wording of each question is at most 500 characters, and every option keeps its label
- GIVEN the pause WHEN it is shown THEN it names the triage note, where the cost of each wrong default is written

### OWQ-B4 `always` also asks the reading of each findable gap

WHEN a run whose conversation value is `always` pauses THE workflow SHALL put into the pause, after the owner decisions, one choice question for each gap row that says findable and does not say `Covered by`, named by the gap's id in lower case, with the choices `right` and `wrong`, the default `right`, and a wording that gives the gap's row and asks whether the reading is right.

- GIVEN `always` and the gaps G1 (findable), G2 (owner decision) and G3 (findable, `Covered by` a behaviour) WHEN the pause is shown THEN it holds `g2` first and `g1` second, and no question for G3
- GIVEN `blocking` and the same gaps WHEN the pause is shown THEN it holds `g2` only

### OWQ-B5 A reading called wrong keeps the pause open

WHEN the answers to the pause are complete and call the reading of a gap `wrong` THE pause SHALL stay open, naming the gap and saying that the run can be stopped to correct the task or the answer changed to `right`.

- GIVEN every question answered and `g1` answered `wrong` WHEN the answers are given THEN the run stays paused with exit code 3 and the message names G1
- GIVEN `g1` answered `wrong` and the deadline passed WHEN `resume --apply-deadline` runs THEN the run stays paused with exit code 3 and the message names G1
- GIVEN `g1` answered `wrong` WHEN the owner then answers `g1` with `right` THEN the run goes on to discovery

### OWQ-B6 At most twenty questions

WHEN the questions to ask would number more than 20 THE pause SHALL hold the first 20, the owner decisions before the readings.

- GIVEN `blocking` and 22 owner decisions WHEN the pause is shown THEN it holds 20 questions, those of the first 20 owner decisions of the triage note
- GIVEN `always` and 15 owner decisions and 10 findable gaps WHEN the pause is shown THEN it holds the 15 owner decisions and the first five readings

### OWQ-B7 The pause has a deadline

WHEN the run pauses THE workflow SHALL give the pause a deadline 24 hours after it began, or the time that `--set ask_owner.deadline_s=<seconds>` gives.

- GIVEN a start that sets no deadline WHEN the run pauses THEN the pause shows a deadline 86,400 seconds after it began
- GIVEN a start with `--set ask_owner.deadline_s=3600` WHEN the run pauses THEN the pause shows a deadline one hour after it began
- GIVEN a pause before its deadline WHEN `resume --apply-deadline` runs THEN it is refused with exit code 2 and the pause stays open

### OWQ-B8 A passed deadline takes the defaults

WHEN `resume --apply-deadline` is run after the deadline of the pause THE workflow SHALL go on past the pause with each question that is still open at its default, as [ASK-B10](../../../tempergraph/docs/specs/ask-unit.spec.md) states.

- GIVEN a pause with three questions of which `g1` is answered and the deadline passed WHEN `resume --apply-deadline` runs THEN the run goes on to discovery, and the answers hold the answer of `g1` and the defaults of `g2` and `g3`
- GIVEN a pause with three questions none of which is answered and the deadline passed WHEN `resume --apply-deadline` runs THEN the run goes on to discovery with the default of each question

### OWQ-B9 Discovery closes each owner decision on its answer

WHEN the discovery step closes the gaps of a run whose pause the owner answered THE discovery step SHALL close each owner decision that has an answer on the option the answer names instead of the default, leaving no open question for it in the spec.

- GIVEN the owner decision of G2 answered `b` in a file given with `resume --answers FILE`, while its default is `a` WHEN discovery closes G2 THEN the spec it writes states the behaviour of option `b` and holds no open question for the decision
- GIVEN the owner decision of G2 answered `b` with `--decision answer:g2=b` WHEN discovery closes G2 THEN the spec it writes states the behaviour of option `b` and holds no open question for the decision
- GIVEN an owner decision with no answer, because the deadline took its default or because the pause held only 20 questions WHEN discovery closes its gap THEN the spec states the behaviour of the default and holds no open question for the decision

### OWQ-B10 The hand-off says how each owner decision was closed

WHEN the discovery step ends after a pause THE discovery step SHALL list under `Decisions` in its hand-off each owner decision of the triage note, as answered with the option the owner chose or as a default taken.

- GIVEN G1 answered `b` and G2 taken at the deadline with its default `a` WHEN the hand-off is written THEN `Decisions` says that G1 was answered `b` and that G2 took its default `a`
- GIVEN G21 left out of a pause of 20 questions WHEN the hand-off is written THEN `Decisions` says that G21 took its default

### OWQ-B11 A blocking question the reading could not answer is asked in words

WHEN a run whose conversation value is `blocking` or `always` ends its reading sessions, and the reading session of an uncertainty row that says `Blocks` reported `Not answered` THE workflow SHALL put into the pause, after the owner decisions, one text question named by the row's id in lower case, whose wording gives the row and whose default is to take the reading that changes the least of what exists.

- GIVEN `blocking` and the row U1, which says `Blocks` and `Route: code`, whose reading session reported `Not answered: searched src/ for "retry"` WHEN the pause is shown THEN it holds a text question `u1` whose wording holds the row and whose default is the reading that changes the least
- GIVEN the same row whose reading session reported `Answered: 3 attempts (src/retry.py, lines 4-9)` WHEN the reading sessions end THEN the pause holds no question for U1
- GIVEN a row that says `Shapes` whose reading session reported `Not answered` WHEN the reading sessions end THEN the pause holds no question for it
- GIVEN `never` and a `Blocks` row reported `Not answered` WHEN the reading sessions end THEN the run makes no pause

## Acceptance criteria

- OWQ-AC1 (OWQ-B1): A run on `blocking` whose triage note holds three owner decisions pauses once with three questions, after its reading sessions have ended and before any writing session of discovery starts; a run on `always` whose note holds no owner decision and two findable gaps that no spec answers pauses once with two questions; after two of three questions are answered by decision words the run is still in that pause, open for the third
- OWQ-AC2 (OWQ-B2): A run goes on by the route the triage note names, with no pause, on `blocking` with a note whose `Owner decisions` says `None`, on `never` with a note that has owner decisions, and on `always` with a note that has no gap or whose every gap row says `Covered by`
- OWQ-AC3 (OWQ-B3): The pause for an owner decision with three options shows one choice question named by the lower-case id of its row, with the choices `a`, `b` and `c`, the decision's default, and a wording that gives the gap id, the question and the options in the order of the note; the questions follow the order of the note, no wording passes 500 characters, every option keeps its label, and the pause names the triage note
- OWQ-AC4 (OWQ-B4): On `always` the pause holds, after the owner decisions, one question with the choices `right` and `wrong` and the default `right` for each findable gap that no spec answers, and none for a gap that says `Covered by`; on `blocking` it holds none
- OWQ-AC5 (OWQ-B5): A complete set of answers that calls a reading `wrong` leaves the run paused with exit code 3 and a message that names the gap, also after `resume --apply-deadline`, until the reading is answered `right`
- OWQ-AC6 (OWQ-B6): A pause for 22 owner decisions holds 20 questions; a pause for 15 owner decisions and 10 readings holds the 15 and five readings
- OWQ-AC7 (OWQ-B7): The pause shows a deadline 86,400 seconds after it began, or 3,600 seconds after it with `--set ask_owner.deadline_s=3600`, and `resume --apply-deadline` before the deadline is refused with exit code 2
- OWQ-AC8 (OWQ-B8): After the deadline, `resume --apply-deadline` takes the run on to discovery with the answers already given and the default of each open question
- OWQ-AC9 (OWQ-B9): The discovery prompt names the owner's answers and tells the session to close each owner decision on its answer instead of its default, and on its default when it has no answer, with no open question left in the spec; an answer given with `resume --answers FILE` and one given with `--decision answer:g2=b` each reach it
- OWQ-AC10 (OWQ-B10): The discovery prompt tells the session to list under `Decisions` in the hand-off each owner decision of the triage note as answered, with the option chosen, or as a default taken
- OWQ-AC11 (OWQ-B11): The list of questions holds one text question, named by the lower-case row id and defaulting to the reading that changes the least, for an uncertainty row that says `Blocks` whose reading session reported `Not answered`, and none for such a row reported `Answered`, for a row that says `Shapes`, or on `never`
