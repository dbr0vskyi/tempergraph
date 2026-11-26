# Judge read share

## Purpose

Split from [session review](session-review.spec.md) by capability, keeping its ids: which change a judge's counts are taken over (the paths its digest counts as changed, SRV-B11), and the model-free finding for a judge that graded a change after reading too little of it. The digest that holds the counts and the cause `judge_unread_pass` stay in session review (SRV-B11, SRV-B12).

## Behaviours

### SRV-B34 A judge's changed paths are counted from where its visit began

WHEN a gate's judge starts to grade an attempt of a unit that is not a map, in a git workspace, THE engine SHALL record as the judge's changed paths, counted by its digest as `changed_total` (SRV-B11), up to 200 of the paths that differ between the commit recorded when the judged visit was entered ([EVT-B12](run-events.spec.md)) and the attempt's workspace at that moment, committed or not, untracked paths included.

- GIVEN a visit whose step wrote two files and whose script committed both before the judge WHEN the judge starts THEN its digest holds `changed_total` 2
- GIVEN a visit that committed nothing and left one file modified and one file untracked WHEN the judge starts THEN its digest holds `changed_total` 2
- GIVEN a unit whose second visit, begun by a trip back, left unchanged a file that its first visit committed WHEN the second visit's judge starts THEN its digest holds `changed_total` 0

### SRV-B35 An item's judge counts from where the item began

WHEN a gate's judge starts to grade an attempt at an item of a map, in a git workspace, THE engine SHALL record as the judge's changed paths, counted as in SRV-B34, up to 200 of the paths that differ between the commit the attempt's workspace was at when the item's first attempt in the map's current visit started and the workspace at that moment, committed or not, untracked paths included.

- GIVEN a sequential map whose first item's script committed a file and whose second item wrote another file WHEN the second item's judge starts THEN its digest holds `changed_total` 1
- GIVEN an item whose first attempt's script committed a file and whose retry wrote another file WHEN the retry's judge starts THEN its digest holds `changed_total` 2
- GIVEN a map whose first visit committed a file for an item, and whose second visit, begun by a trip back, runs that item without changing the file WHEN the item's judge starts THEN its digest holds `changed_total` 0

### SRV-B36 A gate whose unit has no step session counts from that unit's own entry

WHEN a gate's judge starts to grade a unit that is not a map and has no step session of its own, such as a sub-workflow, a council or the outcome gate, THE engine SHALL record as the judge's changed paths, counted as in SRV-B34, the paths that differ between the commit recorded when that unit's own visit was entered and the workspace at that moment, never from the entry of a unit it contains.

- GIVEN a sub-workflow unit whose child committed one file during the unit's visit WHEN the unit's judge starts THEN its digest holds `changed_total` 1
- GIVEN the outcome gate entered after every earlier unit committed all its work WHEN its judge starts THEN its digest holds `changed_total` 0

### SRV-B31 A judge graded after reading little of the change

WHEN findings are derived for a judge that gave a judgement and, by its own record of paths opened and paths changed (SRV-B11), opened at least one changed path but under `digest.judge_read_share` (0.25, provenance `default_no_data`, [IMD-B23](improvement-data.spec.md)) of them THE engine SHALL add `judge_partial_read` (fault, workflow, as `judge_unread_pass`) with no model call, whatever the verdict.

- GIVEN a judge that escalated after opening 1 of 10 changed paths WHEN findings are derived THEN they carry `judge_partial_read`
- GIVEN a judge that gave a judgement after opening 3 of 12 changed paths WHEN findings are derived THEN they carry no `judge_partial_read`
- GIVEN a judge that passed every blocker after opening none of 10 changed paths WHEN findings are derived THEN they carry `judge_unread_pass` and no `judge_partial_read`
- GIVEN a judge that timed out after opening 1 of 10 changed paths WHEN findings are derived THEN they carry no `judge_partial_read`

## Acceptance criteria

- SRV-AC13 (SRV-B19, SRV-B20, SRV-B31): The citation check keeps `judge_unread` and `judge_trusts_report` of a judge that opened 1 of 12 changed paths or none, rates them `unsupported` for one that opened 3 of 12, and keeps `judge_shallow` naming `judge_model`
- SRV-AC14 (SRV-B31): A fixture judge that gave a judgement after opening 1 of 10 changed paths yields `judge_partial_read` with no model call, and a judge that opened 3 of 12, one that opened none and one that timed out each yield none
- SRV-AC21 (SRV-B34, SRV-B12): A fixture unit whose step writes two files and whose script commits them before its judge, judged by a session that opens neither file and passes every blocker, leaves the judge's digest with `changed_total` 2 and `changed_read` 0, and the findings derived for the unit carry `judge_unread_pass`
- SRV-AC22 (SRV-B34, SRV-B31): The fixture of SRV-AC21 with ten files written by the step and committed by the script, judged by a session that gives a judgement after opening one of them, leaves the judge's digest with `changed_total` 10 and `changed_read` 1, and the findings derived for the unit carry `judge_partial_read`
- SRV-AC23 (SRV-B34, SRV-B19, SRV-B20): The citation check keeps a `judge_unread` observation for the judge of the fixture of SRV-AC21
- SRV-AC24 (SRV-B34): A fixture unit that commits nothing before its judge leaves the judge's `changed_total` equal to the number of paths modified or untracked in its workspace when the judge starts
- SRV-AC25 (SRV-B34): A fixture visit whose first attempt's script commits one file and whose retry writes another leaves the retry judge's digest with `changed_total` 2
- SRV-AC26 (SRV-B34): A fixture unit that commits a file in its first visit, and whose second visit begins after a later gate sends the run back and leaves that file unchanged, has a second-visit judge digest with `changed_total` 0
- SRV-AC27 (SRV-B35): A fixture sequential map whose first item's script commits a file and whose second item writes another leaves the second item's judge digest with `changed_total` 1
- SRV-AC28 (SRV-B35): A fixture map item whose first attempt's script commits a file and whose retry writes another leaves the retry judge's digest with `changed_total` 2
- SRV-AC29 (SRV-B35): A fixture map that committed a file for an item in its first visit, and whose second visit, begun by a trip back, leaves that file unchanged, has a second-visit judge digest for that item with `changed_total` 0
- SRV-AC30 (SRV-B36): A fixture sub-workflow unit whose child commits one file leaves the unit's judge digest with `changed_total` 1
- SRV-AC31 (SRV-B36): The outcome gate of a fixture run whose units committed all their work leaves its judge digest with `changed_total` 0
