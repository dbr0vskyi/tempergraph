# Judge read share

## Purpose

Split from [session review](session-review.spec.md) by capability, keeping its ids: the model-free finding for a judge that graded a change after reading too little of it.

## Behaviours

### SRV-B31 A judge graded after reading little of the change

WHEN findings are derived for a judge that gave a judgement and, by its own record of paths opened and paths changed (SRV-B11), opened at least one changed path but under `digest.judge_read_share` (0.25, provenance `default_no_data`, [IMD-B23](improvement-data.spec.md)) of them THE engine SHALL add `judge_partial_read` (fault, workflow, as `judge_unread_pass`) with no model call, whatever the verdict.

- GIVEN a judge that escalated after opening 1 of 10 changed paths WHEN findings are derived THEN they carry `judge_partial_read`
- GIVEN a judge that gave a judgement after opening 3 of 12 changed paths WHEN findings are derived THEN they carry no `judge_partial_read`
- GIVEN a judge that passed every blocker after opening none of 10 changed paths WHEN findings are derived THEN they carry `judge_unread_pass` and no `judge_partial_read`
- GIVEN a judge that timed out after opening 1 of 10 changed paths WHEN findings are derived THEN they carry no `judge_partial_read`

## Acceptance criteria

- SRV-AC13 (SRV-B19, SRV-B20, SRV-B31): The citation check keeps `judge_unread` and `judge_trusts_report` of a judge that opened 1 of 12 changed paths or none, rates them `unsupported` for one that opened 3 of 12, and keeps `judge_shallow` naming `judge_model`
- SRV-AC14 (SRV-B31): A fixture judge that gave a judgement after opening 1 of 10 changed paths yields `judge_partial_read` with no model call, and a judge that opened 3 of 12, one that opened none and one that timed out each yield none
