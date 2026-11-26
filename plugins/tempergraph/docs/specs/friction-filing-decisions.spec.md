# Friction filing decisions

## Purpose

How the answers of the loop's friction judge decide whether a friction finding files, and what the loop writes about each decision: when the answers recorded for a fingerprint attribute it, the one reason that a finding which is not filed carries, the numbers and the reason that the loop's records hold, and what the judge is told about attribution. An answer is an entry of the loop's record of what its judge answered ([SIL-B36](self-improvement.spec.md)), and the exit is the final exit whose findings the loop is deciding on ([SIL-B9](self-improvement.spec.md)). When a finding files, the pattern rule and what the loop does without an answer are owned by [self-improvement](self-improvement.spec.md) ([SIL-B18](self-improvement.spec.md), [SIL-B3](self-improvement.spec.md), [SIL-B35](self-improvement.spec.md)), which is at its size budget; what a filed issue or comment holds is owned by [loop-issues](loop-issues.spec.md). Workflow owners and the engine's maintainers who read a thread's `loop.jsonl` to see why a finding did or did not file depend on it.

## Depends on

- `self-improvement.spec.md`: pattern rule (SIL-B3); the loop records what its friction judge answered (SIL-B36)

## Behaviours

### FFD-B1 A finding files by the count only on a majority of its recorded answers

WHEN a friction finding whose confidence is below `friction.file_confidence` has a fingerprint that meets the pattern rule of [SIL-B3](self-improvement.spec.md) THE loop SHALL file it only if at least two answers of the friction judge are recorded for that fingerprint inside `pattern_rule.window_days` ([SIL-B36](self-improvement.spec.md)), this exit's answer included, and more than half of them are `attributed: true`.

- GIVEN a fingerprint that meets the pattern rule and three recorded answers inside the window, attributed at 0.5, not attributed at 0.5 and, at this exit, attributed at 0.5 WHEN filing runs THEN one issue is filed
- GIVEN two recorded answers, an earlier one not attributed and this exit's attributed at 0.5, with the pattern rule met WHEN filing runs THEN the finding is recorded and no issue is filed
- GIVEN an attributed answer recorded 31 days before and this exit's attributed at 0.5, with the pattern rule met WHEN filing runs THEN the finding is recorded and no issue is filed

### FFD-B2 A finding that is not attributed is recorded `not_attributed`

WHEN a friction finding of class `fault` that its judge answered for is not filed because the judge did not attribute it at this exit, at any confidence, or because its fingerprint meets the pattern rule of [SIL-B3](self-improvement.spec.md) on two or more recorded answers of which not more than half are attributed, THE loop SHALL record it `not_attributed`.

- GIVEN a finding that its judge marked not attributed at 0.9, with the pattern rule met WHEN filing runs THEN it is recorded `not_attributed` and no issue is filed
- GIVEN two recorded answers, an earlier one attributed and this exit's not attributed WHEN filing runs THEN the finding is recorded `not_attributed`
- GIVEN two recorded answers, an earlier one not attributed and this exit's attributed at 0.5, with the pattern rule met WHEN filing runs THEN the finding is recorded `not_attributed`

### FFD-B3 A finding below the count is recorded `below_count` or `few_answers`

WHEN a friction finding that its judge attributed at this exit, at a confidence below `friction.file_confidence`, is not filed THE loop SHALL record it `below_count` when its fingerprint does not meet the pattern rule of [SIL-B3](self-improvement.spec.md), and `few_answers` when it meets the rule on one recorded answer.

- GIVEN a finding attributed at 0.5 whose fingerprint is recorded in two runs WHEN filing runs THEN it is recorded `below_count`
- GIVEN a finding attributed at 0.5 whose fingerprint meets the pattern rule on one recorded answer WHEN filing runs THEN it is recorded `few_answers` and no issue is filed
- GIVEN that fingerprint with its one recorded answer attributed at 0.8 WHEN filing runs THEN one issue is filed

### FFD-B4 A decision's record holds the numbers the pattern rule counted

WHEN the loop writes a `loop_result` record for a friction finding of class `fault` that its judge answered for THE loop SHALL put in it the numbers `runs`, `requests` and `machines` that the pattern rule of [SIL-B3](self-improvement.spec.md) counted for its fingerprint.

- GIVEN a finding attributed at 0.5 whose fingerprint is recorded in the exit's run and one earlier run, each under its own request, on two machines WHEN the loop child ends THEN the finding's `loop_result` record holds `runs` 2, `requests` 2 and `machines` 2 as numbers
- GIVEN a dry run in which a finding would file by the pattern rule on three runs, three requests and one machine WHEN the loop child ends THEN its `would_file` record holds `runs` 3, `requests` 3 and `machines` 1

### FFD-B5 A filed or commented record holds the reason

WHEN the loop opens an issue or adds a comment for a finding THE loop SHALL write in its `issue_filed` or `issue_commented` record the reason of the decision: `pattern_met` when the finding filed by the pattern rule of [SIL-B3](self-improvement.spec.md) and `fault` when it filed otherwise.

- GIVEN a friction finding that files by the pattern rule WHEN its issue opens THEN the `issue_filed` record holds the reason `pattern_met`
- GIVEN a friction finding attributed at 0.9 whose fingerprint is recorded in one run WHEN its issue opens THEN the `issue_filed` record holds the reason `fault`
- GIVEN that issue open WHEN the cause files at a later exit by the pattern rule THEN the `issue_commented` record holds the reason `pattern_met`

### FFD-B6 The judge is told that attribution can file by the count

WHEN the loop child asks the friction judge about findings THE loop child SHALL tell it in the prompt that an answer `attributed: true` can file a finding by the count whatever its confidence.

- GIVEN a ticket with one friction finding WHEN the friction judge's session starts THEN its prompt tells it that an answer `attributed: true` can file the finding by the count whatever its confidence

## Acceptance criteria

- FFD-AC1 (FFD-B1): Against a fake code host and the answers that earlier fixture runs recorded, a finding at 0.5 whose fingerprint meets the pattern rule files one issue on the answers attributed, not attributed, attributed (this exit's last), and files none on not attributed then attributed, and on one attributed answer recorded outside `pattern_rule.window_days`
- FFD-AC2 (FFD-B2): Against a fixture loop child, a finding whose fingerprint meets the pattern rule is recorded `not_attributed`, with no issue and no comment, when its judge answered not attributed at 0.9, when the answers are attributed then not attributed, and when they are not attributed then attributed at 0.5
- FFD-AC3 (FFD-B3): Against a fixture loop child, a finding attributed at 0.5 in two runs is recorded `below_count`, one attributed at 0.5 whose fingerprint meets the pattern rule on one recorded answer is recorded `few_answers`, and one attributed at 0.8 on one recorded answer files one issue
- FFD-AC4 (FFD-B4): The `loop_result` records of a fixture loop child for a recorded finding, for a finding that would file in a dry run and for a muted finding each hold `runs`, `requests` and `machines` as numbers equal to what the pattern rule counted
- FFD-AC5 (FFD-B5): Against a fake code host, the `issue_filed` record of a friction finding that files by the pattern rule holds `pattern_met`, that of a finding attributed at 0.9 in one run holds `fault`, and the `issue_commented` record of a later comment holds the reason of the decision that commented
- FFD-AC6 (FFD-B6): The prompt that a fixture friction judge session receives holds the sentence that an answer `attributed: true` can file a finding by the count whatever its confidence
