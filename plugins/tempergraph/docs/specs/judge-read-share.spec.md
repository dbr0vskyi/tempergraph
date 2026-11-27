# Judge read share

## Purpose

Split from [session review](session-review.spec.md) by capability, keeping its ids: which change a judge's counts are taken over (the paths its digest counts as changed, SRV-B11), meaning the commit they are counted from, the paths left out, and what is recorded when no commit can be used; which judgements stand for the judge of a map's item; and the model-free finding for a judge that graded a change after reading too little of it. The digest that holds the counts and the cause `judge_unread_pass` stay in session review (SRV-B11, SRV-B12); the field a gate declares to leave paths out is stated in [workflow model](workflow-model.spec.md) (WFM-B14).

## Depends on

- `contracts.spec.md`: step fields (CON-B6)
- `improvement-data.spec.md`: parameters with provenance (IMD-B23)
- `judge-model-by-risk.spec.md`: what the rule reads (JRK-B7)
- `run-events.spec.md`: units, sessions, checks and judgements (EVT-B12); keys added to existing records (EVT-B16); tool input summaries (EVT-B21)
- `workflow-model.spec.md`: paths a gate's judge may skip (WFM-B14)

## Behaviours

### SRV-B34 A judge's changed paths are counted from where its visit began

WHEN a gate's judge starts to grade an attempt of a unit that is not a map, in a git workspace, THE engine SHALL record as the judge's changed paths, at most 200 and after SRV-B39, SRV-B41 and SRV-B42 have left paths out, the paths that differ between the commit recorded when the judged visit was entered ([EVT-B12](run-events.spec.md)) and the workspace at that moment: those committed since and those modified or untracked in the workspace, including any held at the visit's entry.

- GIVEN a visit whose step wrote two files and whose script committed both before the judge WHEN the judge starts THEN its digest holds `changed_total` 2
- GIVEN a workspace that held one untracked file when a visit was entered, and a visit that committed nothing and modified one tracked file WHEN the judge starts THEN its digest holds `changed_total` 2
- GIVEN a unit whose second visit, begun by a trip back, left unchanged a file that its first visit committed WHEN the second visit's judge starts THEN its digest holds `changed_total` 0

### SRV-B35 An item's judge counts from where the item began

WHEN a gate's judge starts to grade an attempt at an item of a map, in a git workspace, THE engine SHALL count the judge's changed paths as in SRV-B34, from the commit the attempt's workspace was at when the item's first attempt in the map's current visit started.

- GIVEN a sequential map whose first item's script committed a file and whose second item wrote another file WHEN the second item's judge starts THEN its digest holds `changed_total` 1
- GIVEN an item whose first attempt's script committed a file and whose retry wrote another file WHEN the retry's judge starts THEN its digest holds `changed_total` 2
- GIVEN a map whose first visit committed a file for an item, and whose second visit, begun by a trip back, runs that item without changing the file WHEN the item's judge starts THEN its digest holds `changed_total` 0

### SRV-B36 A gate whose unit has no step session counts from that unit's own entry

WHEN a gate's judge starts to grade a unit that is not a map and has no step session of its own, such as a sub-workflow, a council or the outcome gate, THE engine SHALL count the judge's changed paths as in SRV-B34, from the commit recorded when that unit's own visit was entered, never from the entry of a unit it contains.

- GIVEN a sub-workflow unit whose child committed one file during the unit's visit WHEN the unit's judge starts THEN its digest holds `changed_total` 1
- GIVEN the outcome gate entered after every earlier unit committed all its work WHEN its judge starts THEN its digest holds `changed_total` 0

### SRV-B37 A judge's record holds the commit its count was made from

WHEN a gate's judge starts to grade an attempt THE engine SHALL write on the judge's `agent_run` record (EVT-B16) `changed_base`, the commit its changed paths were counted from (SRV-B34 to SRV-B36), or, when no commit can be used, null with no changed path and `changed_base_reason`: `outside_repository` for a workspace outside a git repository, else `no_entry_commit` for no recorded commit, else `commit_unknown` for a commit that git does not hold.

- GIVEN a visit entered at a commit WHEN its judge starts THEN `changed_base` on the judge's record is that commit
- GIVEN a visit whose entry record holds no commit WHEN its judge starts THEN `changed_base` is null and `changed_base_reason` is `no_entry_commit`
- GIVEN a recorded entry commit that git does not hold WHEN its judge starts THEN `changed_base` is null and `changed_base_reason` is `commit_unknown`

### SRV-B38 A judge with no base commit has no count

WHEN a judge's `agent_run` record holds a null `changed_base` THE engine SHALL write neither `changed_total` nor `changed_read` in that judge's digest.

- GIVEN a recorded entry commit that git does not hold, and a judge that passed every blocker having opened none of the files WHEN the digest and the findings are written THEN the digest holds no `changed_total` and the findings carry neither `judge_unread_pass` nor `judge_partial_read`
- GIVEN a visit that changed nothing, with a recorded entry commit WHEN its judge's digest is written THEN it holds `changed_total` 0 and `changed_read` 0

### SRV-B39 A path the workspace does not hold is not counted

WHEN a judge's changed paths are recorded THE engine SHALL leave out of them each path that is not in the attempt's workspace when the judge starts.

- GIVEN a visit that deleted two files and wrote one WHEN the judge starts THEN its digest holds `changed_total` 1
- GIVEN a visit that deleted a file and then wrote a different file at the same path WHEN the judge starts THEN the path is among the judge's changed paths

### SRV-B40 A name git prints quoted is counted by its own name

WHEN a changed path's name is one that git prints quoted, such as a name with a space or a letter outside ASCII, THE engine SHALL record the path in the judge's changed paths under the name the workspace holds, so that `changed_read` counts it when the judge's session reports a read of that name.

- GIVEN a visit that added `plain.md`, `my notes.md` and `café.md`, and a judge whose session reports a read of `my notes.md` and `café.md` WHEN the digest is written THEN it holds `changed_total` 3 and `changed_read` 2
- GIVEN the same visit and a judge whose session reports a read of `plain.md` only WHEN the digest is written THEN it holds `changed_read` 1

### SRV-B41 A declared file artifact is left out of every judge's counts

WHEN a judge's changed paths are recorded THE engine SHALL leave out of them each file artifact that a unit the run has entered declares in `produces` ([CON-B6](contracts.spec.md)), at the path reported for it, taken relative to the workspace, so that no judge counts it in `changed_total` or `changed_read`.

- GIVEN a step that writes its declared summary file and two other files, and a judge that opens only the summary file and passes every blocker WHEN findings are derived THEN `changed_total` is 2, `changed_read` is 0 and they carry `judge_unread_pass`
- GIVEN a declared file artifact that an earlier unit wrote and left uncommitted WHEN a later unit's judge starts THEN the file is not among that judge's changed paths
- GIVEN a summary file that no unit declares in `produces` WHEN the judge starts THEN it is among the judge's changed paths

### SRV-B42 A gate's patterns leave paths out of its judge's counts

WHEN a gate declares `judge_may_skip` ([WFM-B14](workflow-model.spec.md)) THE engine SHALL leave out of its judge's changed paths, and of no other judge's, each path that one of the patterns matches in full, case-sensitively, with `*` and `**` both crossing directories ([JRK-B7](judge-model-by-risk.spec.md)), so that neither `changed_total` nor `changed_read` of that judge counts it.

- GIVEN a gate that declares `dist/**` and a step that wrote three files under `dist/` and one elsewhere WHEN its judge starts THEN its digest holds `changed_total` 1
- GIVEN a gate that declares `dist/**`, a later gate that declares no pattern, and files under `dist/` that the first unit wrote and left uncommitted WHEN the later gate's judge starts THEN it counts those files
- GIVEN a gate that declares `dist/**`, a step that wrote one file under `dist/` and one elsewhere, and a judge that opened only the file under `dist/` WHEN the digest is written THEN `changed_total` is 1 and `changed_read` is 0

### SRV-B43 A judge's record holds how many paths its gate's patterns left out

WHEN a gate's judge starts to grade an attempt THE engine SHALL write on the judge's `agent_run` record `changed_left_out`, the number of paths, among those that would otherwise count, that the gate's `judge_may_skip` patterns left out, 0 when it declares none.

- GIVEN a gate that declares `dist/**` and a step that wrote three files under `dist/` and one elsewhere WHEN its judge starts THEN the judge's record holds `changed_left_out` 3
- GIVEN a gate that declares no pattern WHEN its judge starts THEN the judge's record holds `changed_left_out` 0

### SRV-B44 A map's judgements are read item by item

WHEN findings are derived for the judge of an item of a map THE engine SHALL decide whether that judge passed every blocker, and whether it gave a judgement, from the judgements recorded for that item alone, never from another item's.

- GIVEN a sequential map of three items whose first and third items' judges failed a blocker and whose second item's judge passed every blocker having opened none of the changed paths WHEN findings are derived THEN they carry `judge_unread_pass` once
- GIVEN a map whose first item's judge failed a blocker and whose second item's judge passed every blocker having opened none of the changed paths WHEN findings are derived THEN they carry `judge_unread_pass` once
- GIVEN a map whose two items' judges each opened 1 of 10 changed paths, the first having given a judgement and the second having timed out WHEN findings are derived THEN they carry `judge_partial_read` once

### SRV-B31 A judge graded after reading little of the change

WHEN findings are derived for a judge that gave a judgement and, by its own record of paths opened and paths changed (SRV-B11), opened at least one changed path but under `digest.judge_read_share` (0.25, provenance `default_no_data`, [IMD-B23](improvement-data.spec.md)) of them THE engine SHALL add `judge_partial_read` (fault, workflow, as `judge_unread_pass`) with no model call, whatever the verdict.

- GIVEN a judge that escalated after opening 1 of 10 changed paths WHEN findings are derived THEN they carry `judge_partial_read`
- GIVEN a judge that gave a judgement after opening 3 of 12 changed paths WHEN findings are derived THEN they carry no `judge_partial_read`
- GIVEN a judge that passed every blocker after opening none of 10 changed paths WHEN findings are derived THEN they carry `judge_unread_pass` and no `judge_partial_read`
- GIVEN a judge that timed out after opening 1 of 10 changed paths WHEN findings are derived THEN they carry no `judge_partial_read`

### SRV-B45 A judge's counts reach the loop as numbers only

WHEN a judge's counts, or a finding made from them, are written to its digest, to `loop.jsonl` or to a filed issue THE engine SHALL write counts, enums and cause codes only, never a changed path, a declared file artifact's path, a gate pattern or a commit id.

- GIVEN a judge session of a unit whose workflow declares a file artifact and a gate pattern, each holding a canary string WHEN its digest, its findings and the `loop.jsonl` records of its run are read THEN none holds either canary string
- GIVEN the same session WHEN the body of an issue built from its findings is read THEN it holds neither canary string

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
- SRV-AC32 (SRV-B37): A fixture visit entered at a commit leaves its judge's `agent_run` record with `changed_base` equal to that commit
- SRV-AC33 (SRV-B37): A fixture whose entry record holds no commit, one whose recorded commit git does not hold and one whose workspace is outside a git repository each leave `changed_base` null and no changed path, with the reasons `no_entry_commit`, `commit_unknown` and `outside_repository`
- SRV-AC34 (SRV-B38, SRV-B12, SRV-B31): A fixture judge whose record holds a null `changed_base`, and that passed every blocker having opened none of the unit's files, has a digest with neither `changed_total` nor `changed_read`, and the findings derived for its unit carry neither `judge_unread_pass` nor `judge_partial_read`
- SRV-AC35 (SRV-B38, SRV-B37): A fixture visit that changed nothing, entered at a recorded commit, leaves its judge's record with `changed_base` set and its digest with `changed_total` 0 and `changed_read` 0
- SRV-AC36 (SRV-B39): A fixture visit that deletes two tracked files and adds one leaves the judge's `changed_total` 1, and a fixture visit that deletes a tracked file and writes a different file at the same path leaves the judge's `changed_total` 1
- SRV-AC37 (SRV-B40): A fixture visit that adds a file with a plain name, one with a space in its name and one with a letter outside ASCII in its name, judged by a session that reports a read of the last two, leaves `changed_total` 3 and `changed_read` 2
- SRV-AC38 (SRV-B41, SRV-B12): A fixture unit whose step writes its declared summary file and two other files, judged by a session that opens only the summary file and passes every blocker, leaves `changed_total` 2 and `changed_read` 0, and the findings derived for the unit carry `judge_unread_pass`
- SRV-AC39 (SRV-B41): A declared file artifact that an earlier unit wrote and left uncommitted, and one reported as `./notes.md` or as an absolute path inside the workspace, are each left out of the changed paths of the judge of a later unit
- SRV-AC40 (SRV-B42): A fixture gate that declares `dist/**`, whose step writes three files under `dist/` and one elsewhere, leaves its judge's `changed_total` 1, and a fixture gate that declares no pattern leaves the judge of the same four files `changed_total` 4
- SRV-AC41 (SRV-B43): The `agent_run` record of the judge of the fixture gate that declares `dist/**` in SRV-AC40 holds `changed_left_out` 3, and that of the judge of the gate that declares no pattern holds 0
- SRV-AC42 (SRV-B44, SRV-B12): A fixture sequential map of three items, whose first and third items' judges failed a blocker and whose second item's judge passed every blocker having opened none of the changed paths, yields `judge_unread_pass` once
- SRV-AC43 (SRV-B44, SRV-B31): A fixture map of two items whose judges each opened 1 of 10 changed paths, the first having given a judgement and the second having timed out, yields `judge_partial_read` once
- SRV-AC44 (SRV-B45, SRV-B11): A canary fixture judge session of a unit whose workflow declares a file artifact and a gate pattern, each holding a canary string, leaves no canary string in its digest, in the findings derived for the unit, in the `loop.jsonl` records of its run or in the body of an issue built from those findings
- SRV-AC45 (SRV-B31, SRV-B41, SRV-B12): Fixture judge sessions, each of a judge that gave a judgement and passed every blocker having opened only its unit's declared summary file, with one, four and nine other changed paths, each yield `judge_unread_pass`, and none yields `judge_partial_read`
- SRV-AC46 (SRV-B31): A fixture judge that gave a judgement after opening one of eight counted paths yields `judge_partial_read`, and one that opened two of eight yields none, with `digest.judge_read_share` at 0.25
- SRV-AC47 (SRV-B34, SRV-B40): SRV-AC21 and SRV-AC22 hold on fixture runs whose judge sessions are stand-in sessions scripted to open a named path, each reported as a `read` call whose input summary is that path relative to the workspace ([EVT-B21](run-events.spec.md)); their digests are built from the journals those runs write, and no test writes a judge's journal itself
- SRV-AC48 (SRV-B34): A fixture workspace that holds one untracked file when a visit is entered, whose step modifies one tracked file and commits nothing, leaves the judge's `changed_total` 2
- SRV-AC49 (SRV-B34, SRV-B42): A fixture visit that writes 250 files under a folder its gate's pattern leaves out and three files elsewhere leaves the judge's `changed_total` 3
