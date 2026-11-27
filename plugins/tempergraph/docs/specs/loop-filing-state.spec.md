# Filing state of the loop

## Purpose

At a thread's final exit the loop is in one of three states: it files its findings, it shows what it would file and files nothing (a dry run), or it only records them (held). This spec owns the run setting `loop_dry_run` that makes a dry run, what decides the state and in what order, and the two words, `filing` and `filing_source`, that the loop child's summary keeps for the exit. Operators read the two words to see afterwards whether an exit filed, ran dry or was held, and which input decided it.

## Depends on

- `contracts.spec.md`: workflow fields (CON-B4)
- `improvement-proposals.spec.md`: autonomy level (PRP-B11); the operator's setting lowers the autonomy at each final exit (PRP-B31)
- `loop-summary-and-review-retries.spec.md`: the summary says how the exit filed (SIL-B52)
- `run-events.spec.md`: settings and workflow changes (EVT-B11)
- `run-options.spec.md`: dry run and no dry run on start and on resume (ROP-B9, ROP-B14)
- `run-settings-and-overrides.spec.md`: layers (RST-B22); snapshot and resume (RST-B26); the config verb (RST-B31); refusals before spend (RST-B32)
- `self-improvement.spec.md`: filing by attribution or by count (SIL-B18); daily cap (SIL-B20); dry run files nothing (SIL-B6)

## Does not own

- The settings catalog, its layers and the refusals before spend: `run-settings-and-overrides.spec.md`
- The options `--dry-run` and `--no-dry-run`: `run-options.spec.md`
- What the loop writes in a dry run, and which findings meet the filing rules: `self-improvement.spec.md`
- Which autonomy levels exist and how a machine lowers one: `improvement-proposals.spec.md`
- How `status` shows the two words: `durability-and-resume.spec.md`

## Behaviours

### LFS-B1 The dry run is a run setting

WHEN the settings catalog is read THE engine SHALL hold at scope `run` the key `loop_dry_run`, `true` or `false`, default `false`, which a workflow declares as its default ([CON-B4](contracts.spec.md)), a settings file or a profile sets and the flag layer overrides, like every run key ([RST-B22](run-settings-and-overrides.spec.md)).

- GIVEN a workflow that declares `loop_dry_run` `true` WHEN `config show` runs for it ([RST-B31](run-settings-and-overrides.spec.md)) THEN the row of `run.loop_dry_run` shows `true` and the layer `workflow:default`
- GIVEN that workflow and a settings file whose `overrides` entry sets `run.loop_dry_run` `false` WHEN `config show` runs THEN the row shows `false` from that file, with the workflow's value shadowed
- GIVEN `--set run.loop_dry_run=maybe` WHEN `run --check`, `run` or `resume` is given it THEN each refuses it as `setting_value` in the same words before any spend ([RST-B32](run-settings-and-overrides.spec.md))

### LFS-B2 The improvement mode has no part in the filing state

WHEN the loop decides at a thread's final exit whether it files, runs dry or is held THE loop SHALL decide from the dry run, the autonomy level and the machine's hold alone, so that a workflow that declares none of them files in `dev` mode and in `stable` mode alike.

- GIVEN a `dev` workflow that declares no dry run and no autonomy level WHEN a thread with a finding that meets the filing rules of [SIL-B18](self-improvement.spec.md) reaches its final exit THEN the finding is filed
- GIVEN the same workflow declared `stable`, with room under its daily cap ([SIL-B20](self-improvement.spec.md)) WHEN a thread with that finding reaches its final exit THEN the finding is filed
- GIVEN either mode WHEN `loop_dry_run` is `true` for the thread THEN nothing is filed and each finding that would file is a `would_file` record

### LFS-B3 A dry run that only the log records holds

WHEN a thread's log holds `dry_run` on a `run_started` record and holds no `settings_resolved` record ([EVT-B11](run-events.spec.md)) with a row for `run.loop_dry_run` THE loop SHALL run the thread dry at its final exit.

- GIVEN a thread whose log shows a dry-run start and no row for the setting WHEN it is resumed with neither option and reaches its final exit THEN the loop runs dry at that exit
- GIVEN that thread WHEN a resume gives `--no-dry-run` and the thread reaches its final exit THEN the loop files at that exit
- GIVEN that thread resumed with `--no-dry-run` and later with `--unset run.loop_dry_run` WHEN it reaches its final exit THEN the loop files at that exit

### LFS-B4 An argument lifts a declared `record` for one thread

WHEN a workflow declares the autonomy level `record` and a thread's value of `run.loop_dry_run` is `false` from the flag layer THE loop SHALL run that thread at the level `file` in place of `record`, never above `file` and never over the machine's hold ([PRP-B31](improvement-proposals.spec.md)).

- GIVEN a workflow that declares `record` WHEN a thread started or resumed with `--no-dry-run` ([ROP-B9, ROP-B14](run-options.spec.md)) reaches its final exit THEN its findings are filed as at the level `file`, and no proposal is made and no trial runs
- GIVEN the same workflow WHEN a thread with no argument, or whose `false` comes from a settings file, a profile or the workflow's declaration, reaches its final exit THEN nothing is filed and each decided finding is recorded with the reason `autonomy_record`
- GIVEN a thread given `--no-dry-run` WHEN `loop_autonomy` is set to `record` in a settings file before its final exit, or `TEMPERGRAPH_AUTONOMY=record` is in the environment of the process that ends it THEN nothing is filed and each decided finding is recorded with the reason `autonomy_record`

### LFS-B5 The filing state of an exit

WHEN a loop child ends THE loop child SHALL give the `filing` of its `loop_summary` record ([SIL-B52](loop-summary-and-review-retries.spec.md)) the value `held` when the level the thread runs at ([PRP-B31](improvement-proposals.spec.md)) is `record`, otherwise `dry_run` when the thread runs dry ([SIL-B6](self-improvement.spec.md), LFS-B3), otherwise `file`.

- GIVEN the level `record` and `run.loop_dry_run` `true` WHEN the child ends THEN `filing` is `held`, each decided finding is recorded with the reason `autonomy_record` and no `would_file` record is written
- GIVEN the level `file`, `propose` or `trial` and `run.loop_dry_run` `true` WHEN the child ends THEN `filing` is `dry_run`
- GIVEN the level `file` and `run.loop_dry_run` `false` WHEN the child ends THEN `filing` is `file`

### LFS-B6 The source of a held exit

WHEN `filing` is `held` THE loop child SHALL give `filing_source` the value `machine_hold` when `loop_autonomy` or `TEMPERGRAPH_AUTONOMY` holds the level at `record`, and `declared_record` otherwise.

- GIVEN `loop_autonomy` set to `record` in a settings file WHEN a thread's loop child ends THEN `filing_source` is `machine_hold`
- GIVEN a workflow that declares `record`, no hold and a thread with no `--no-dry-run` WHEN the loop child ends THEN `filing_source` is `declared_record`
- GIVEN a workflow that declares `record` and a hold at `record` WHEN the loop child ends THEN `filing_source` is `machine_hold`

### LFS-B7 The source of an exit that files or runs dry

WHEN `filing` is `file` or `dry_run` THE loop child SHALL give `filing_source` the word for the layer that gave `run.loop_dry_run` its value for the thread: `argument` for the flag layer, `settings` for a settings file or a profile, `workflow` for the workflow's declaration and `default` for no layer, and `argument` for a dry run that only the log records (LFS-B3).

- GIVEN a workflow that declares `record` WHEN a thread given `--no-dry-run` files THEN `filing` is `file` and `filing_source` is `argument`
- GIVEN `run.loop_dry_run` `true` from a settings file or a profile, or from the workflow's declaration WHEN the loop child ends THEN `filing` is `dry_run` and `filing_source` is `settings` or `workflow` respectively
- GIVEN a workflow that declares no dry run and no autonomy level and a thread with no argument WHEN the loop child ends THEN `filing` is `file` and `filing_source` is `default`

## Acceptance criteria

- LFS-AC1 (LFS-B1): `run.loop_dry_run` has a fixture value on each of the flag, profile, file and workflow layers that `config show` prints with its layer, its value with nothing set is `false`, and a value other than `true` or `false` is refused as `setting_value` in the same words by `run --check`, `run` and `resume` before any file is created under the state root
- LFS-AC2 (LFS-B2): A fixture workflow that declares no dry run and no autonomy level files a finding that meets the filing rules against a fake code host in `dev` mode and in `stable` mode, and a fixture exit has the same `filing` in both modes for every combination of `loop_dry_run`, autonomy level and hold
- LFS-AC3 (LFS-B3): A fixture thread whose log holds a dry-run start and no row for the setting runs dry at its final exit after a resume with neither option, files after a resume with `--no-dry-run`, and still files after a later `--unset run.loop_dry_run`
- LFS-AC4 (LFS-B4): Against a fake code host, a thread of a fixture workflow that declares `record`, started or resumed with `--no-dry-run`, files its findings, proposes nothing and runs no trial; a second thread of it with no argument files nothing and records the reason `autonomy_record`; with `loop_autonomy` or `TEMPERGRAPH_AUTONOMY` at `record` the first thread files nothing as well; and the package's declaration is unchanged
- LFS-AC5 (LFS-B5): A fixture loop child leaves `filing` `held` for a thread at the level `record` with or without a dry run, `dry_run` for a thread at a higher level with a dry run, and `file` for a thread with neither, and writes no `would_file` record at the level `record`
- LFS-AC6 (LFS-B6, LFS-B7): A fixture thread for each of `default`, `workflow`, `settings`, `argument`, `machine_hold` and `declared_record` leaves that `filing_source` in its `loop_summary` with the `filing` its behaviour names, and the thread of LFS-AC4 that files leaves `file` and `argument`
- LFS-AC7 (LFS-B5): Against a fake code host that sees no issue and no comment, a fixture workflow that declares `loop_dry_run` `true`, and one whose settings file sets it, each write at every final exit of their threads a `would_file` record with the title of each finding that would file
