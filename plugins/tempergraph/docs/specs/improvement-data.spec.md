# Improvement data requirements

## Purpose

What the self-improvement loop ([SIL](self-improvement.spec.md), [PRP](improvement-proposals.spec.md), [FBK](feedback-and-judge-reliability.spec.md), [LSN](workflow-lessons.spec.md)) needs to read, stated as requirements on the run data store that the observability design owns: the per-repository state under `.tempergraph/` and the cross-machine aggregate, which in this release is the directory sink of [CST](central-run-stats.spec.md). This spec designs no store of its own ([ADR `improvement-data-is-a-requirement-on-the-run-store`](../adr/improvement-data-is-a-requirement-on-the-run-store.adr.md)): it lists the records and fields the loop reads, which may leave the machine and which may not, the events the loop emits, the parameters whose values must carry provenance, and the figures that measure the loop itself. The requirements add to what [OBS](observability-and-cost.spec.md) records; where it names a field differently, its name wins. Pseudonymous machine ids and keyed request digests are the smallest identity that makes cross-machine pattern counting work without sending text. The analysis behind it is [research `self-improvement-gap-analysis`](../research/self-improvement-gap-analysis.rsrch.md) F2. The loop, its reports and the monitor depend on it.

## Behaviours

### IMD-B5 Join keys

WHEN a record the loop reads is written THE engine SHALL give it `run_id` (`<thread>#<segment>`), `thread`, `workflow`, `workflow_version`, `machine` (the stable pseudonymous machine id, not a host name) and `repo` (the first 16 hex of the SHA-256 of the normalized origin URL, null without an origin, locally; keyed with the sink key in a sink row), so records join across runs, machines and repositories.

- GIVEN a ledger `run_segment` row and a `label` row of one segment WHEN joined THEN they share `run_id`, `machine` and `repo`

### IMD-B6 Digests of what the model saw

WHEN an `agent_run` is recorded THE engine SHALL carry the digests of its rendered template, its lessons block and, for a judge, its brief, stance and criteria set, so a version comparison splits by what the model saw.

- GIVEN a judge's `agent_run` WHEN read THEN it carries brief, stance and criteria digests

### IMD-B7 Gate records keep the criteria

WHEN a `gate` record is kept THE engine SHALL keep the per-criterion list (id, status, `defect_in`, `no_change`), confidence with its source and the judge binding ([FBK-B8](feedback-and-judge-reliability.spec.md)), for reliability, the quality lens and gate escapes.

- GIVEN a judged gate WHEN its records are read THEN each criterion's id and status is there

### IMD-B8 Loop records have their own kinds

WHEN labels, clusters, proposals and trials are stored THE engine SHALL store each as its own record kind with `schema_version`, since they outlive the run that produced them.

- GIVEN a proposal WHEN stored THEN it is a record of kind `proposal` with `schema_version`

### IMD-B9 Issue and pull-request state

WHEN a loop-filed issue or a proposal's pull request changes state THE store SHALL keep its state `filed`, `commented`, `fixed` (closed by a merged change), `noise` (closed as not planned) or `stale` (open 60 days) with timestamps, for the loop's own metrics.

- GIVEN an issue closed as not planned WHEN read THEN its state is `noise`

### IMD-B10 Evidence stays on its machine

WHEN records cross a machine boundary THE engine SHALL keep the local evidence file (request, outputs, feedback text) on the machine that made it and send only what IMD-B20 allows (OVR-B11, [SEC-B9](security.spec.md)).

- GIVEN a run on machine A WHEN its records are synced THEN no evidence file leaves A

### IMD-B11 Window queries in one call

WHEN the loop asks the aggregate a window query THE aggregate SHALL answer in one call the counts of runs, distinct request digests and machines per cluster in the window, the repeat cost per cluster, and the labels per gate binding.

- GIVEN a 30-day window WHEN the loop queries THEN one call returns runs, requests and machines per cluster

### IMD-B12 Local fallback

WHEN no aggregate is configured or it cannot be reached THE engine SHALL answer every query from the local records with `scope: local` in its result, never blocking a run, and otherwise answer with `scope: aggregate`.

- GIVEN an unreachable aggregate WHEN queried THEN the result says `scope: local`

### IMD-B13 Append-only

WHEN a loop record is corrected THE engine SHALL append a new record that names the one it replaces, so trials and grades are reproducible from history.

- GIVEN a corrected label WHEN read THEN both records exist and the newer names the older

### IMD-B14 Retention

WHEN the loop's records are kept THE engine SHALL keep metadata records at least 400 days and evidence files 90 days by default (operator-configurable), a deleted evidence file leaving its records readable.

- GIVEN an evidence file pruned after 90 days WHEN its records are read THEN they still read

### IMD-B15 Loop events reach observers

WHEN the loop emits events THE store SHALL put them on the engine's event surface, lifecycle hooks ([HOK](lifecycle-hooks.spec.md)) and the observer interface ([EVT-B23](run-events.spec.md)).

- GIVEN a registered observer WHEN an issue is filed THEN it gets `issue_filed`

### IMD-B16 Keyed request digests

WHEN a request digest is made THE engine SHALL key the hash with a per-installation key (the sink key, [CST-B11](central-run-stats.spec.md)), so equal requests match across one team's machines and cannot be looked up from outside, and count distinct requests per key, warning `mixed_digest_keys` when one aggregate holds two keys.

- GIVEN two installations with different keys in one aggregate WHEN reported THEN distinct-request counts are per key with `mixed_digest_keys`

### IMD-B17 Settings on every record

WHEN a run line, `agent_run`, ledger or finding record is written THE engine SHALL carry `settings_digest` and `overridden_keys`, and a rerun's records `rerun_of` ([RST](run-settings-and-overrides.spec.md), [RRN](reruns-and-feedback.spec.md)), so lenses compare runs with like settings, do not file an operator's override as a workflow fault, and join a rerun to its source.

- GIVEN a run with an operator override WHEN its finding is recorded THEN it carries `overridden_keys`

### IMD-B18 Grants counted

WHEN a tool grant or allowed command takes effect THE engine SHALL write a `grant` run-log record and an entry of the ledger row's `grants[]` (names, classes, `via`, used or not, outcome after, never the session's text), and the aggregate SHALL count grants per workflow, unit and capability across runs and machines ([SIL](self-improvement.spec.md), [RST](run-settings-and-overrides.spec.md)).

- GIVEN a grant used in three runs WHEN aggregated THEN its workflow, unit and capability counts 3

### IMD-B19 Supervision on every intervention

WHEN an intervention is recorded THE engine SHALL carry its caller ([PRV](caller-provenance.spec.md)), put `supervision{}` on the ledger row ([SUP](supervision-metrics.spec.md)) and, once closed, a `supervision` line with the supervising sessions' cost ([SCO](supervision-cost.spec.md)), and the aggregate SHALL count touches by class, decider and pause cause per workflow and unit across runs and machines.

- GIVEN an agent rescue WHEN aggregated THEN it counts under its class and decider

### IMD-B20 What may leave the machine

WHEN records reach the aggregate THE engine SHALL let cross, of run lines, `agent_run` and `gate`, only names, enums, counts, costs, durations, digests, criterion ids and statuses (no evidence text, tool inputs or paths outside the package); of caller blocks and supervision records only kinds, deciders, relay values, touch counts, levels, token counts, costs and hashed host sessions (no host session id in the clear, prompt text or command); of findings and clusters only cause codes, counts and sides (no rationale text); of labels every field but the typed reason; of proposals ids, classes, side, state, the rule sentence and the patch digest (never the patch); of trials pairs as values and outcomes, metrics, spend and decision (no case request); and parameters whole; and SHALL read a record without `machine` or `repo` locally only, counted under `unkeyed`; labels do not cross to a sink in this release.

- GIVEN a record without `repo` WHEN aggregated THEN it is excluded and counted under `unkeyed`

### IMD-B2 Evidence stays home

WHEN records of a run on machine A reach the aggregate THE engine SHALL keep the canary string planted in its request out of every aggregated record.

- GIVEN a planted canary WHEN synced THEN no aggregated record holds it

### IMD-B1 Pattern across machines

WHEN the pattern rule runs on an outcome gap seen once each on three machines with three distinct request digests in 30 days THE engine SHALL count three runs, three requests and three machines and file with the aggregate reachable, and count one with `scope: local` when it is not.

- GIVEN the aggregate unreachable WHEN the rule runs THEN it counts one and records `scope: local`

### IMD-B21 Loop events

WHEN the loop records findings, files or comments on an issue THE engine SHALL emit `finding_recorded` (run, causes, sides, with the labels and binding shifts the exit added), `issue_filed` and `issue_commented` (cluster, issue URL, side), ids and enums only; `label_recorded`, `proposal_state`, `trial_progress` and `binding_shift` are read from their records until a release adds them.

- GIVEN an exit that adds two labels WHEN `finding_recorded` is read THEN it carries both

### IMD-B22 Loop metrics

WHEN `report --loop` runs THE engine SHALL print per workflow and for the engine side over the window, read-only, the funnel (findings, clusters, issues filed, proposals, trials, `shown_better`, opened, merged, held after release), issue precision (`fixed` over `fixed` plus `noise`), time to fix (median days from a cluster's first finding to the merge that closed it), held after release, loop spend (children, proposer and trials, reported and estimated apart, a trial's total shown as estimated), estimated saving (repeat cost per run before and after the merge times runs since, with its run counts, never one headline figure), label coverage (share of gates whose binding is `reliable`, `unmeasured` or `unreliable`) and the parameters with their provenance, printing a figure that needs code-host state as not derived with that reason, never as zero.

- GIVEN no code-host state read WHEN `report --loop` runs THEN issue precision prints as not derived with its reason

### IMD-B3 Loop precision is computed

WHEN `report --loop` runs over 10 loop issues closed in a window, 6 by a merged change and 4 as not planned THE engine SHALL show issue precision 0.6 and name both counts.

- GIVEN 6 fixed and 4 noise WHEN reported THEN precision is 0.6

### IMD-B23 Parameters with provenance

WHEN the loop uses a threshold THE engine SHALL read it from a named parameter record with `name` (such as `pattern_rule.min_distinct_requests`), `value`, `provenance` (`default_no_data`, `fitted`, `owner_decision`), `fitted_on` (`{window, n, query digest}` when fitted), `set_at` and `set_by`, print a parameter's provenance beside any figure it decides, and never change its own parameters, a change being a configuration change reviewed like any other.

- GIVEN a loop run WHEN its parameters are read after THEN none has changed

### IMD-B4 Provenance printed

WHEN a report row decided by `trial.guard.run_cost_pct = 15` with provenance `default_no_data` is printed THE engine SHALL show the parameter and its provenance on the row.

- GIVEN that parameter WHEN the row prints THEN it shows `trial.guard.run_cost_pct` and `default_no_data`

### IMD-B24 Store failures

WHEN a store write fails THE engine SHALL leave the run and its exit code unchanged (OVR-B4), the loop reading what exists.

- GIVEN a failing store write WHEN the run ends THEN its exit code is unchanged

## Acceptance criteria

- IMD-AC1 (IMD-B20, IMD-B2, IMD-B10): Every record kind that crosses passes the canary test over the sink, the fleet copy, the outbox and label rows: no planted request, output or feedback text crosses to the aggregate
- IMD-AC2 (IMD-B12, IMD-B1, IMD-B11): Every loop query returns `scope: local` or `scope: aggregate`, and IMD-B1 holds in both
- IMD-AC3 (IMD-B23): Every threshold named in SIL, ISS, PRP, FBK and LSN exists as a parameter record with a provenance
- IMD-AC4 (IMD-B22, IMD-B3, IMD-B4): `report --loop` reproduces a hand-computed fixture of every figure
- IMD-AC5 (IMD-B5, IMD-B6, IMD-B7, IMD-B8, IMD-B9, IMD-B13, IMD-B14, IMD-B15, IMD-B16, IMD-B17, IMD-B18, IMD-B19, IMD-B21, IMD-B24): A fixture run's records carry the join keys, digests, settings, grants and callers, loop records are append-only with their own kinds, and a failed store write leaves the exit code unchanged

## Open questions

- Who reads pull-request and issue state for IMD-B9 on a team: each machine, or the aggregate's collector once? Until answered: the collector, to avoid N reads of the code host; release 1 reads none. Owner: owner, with the run-monitor design.
