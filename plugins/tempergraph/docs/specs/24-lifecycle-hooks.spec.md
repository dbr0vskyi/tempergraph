# Lifecycle hooks

## Purpose

An operator-registered command the engine runs on a run event, so a notifier can reach a person about an unattended run. The engine ships no hook; a tracker integration is a separate plugin that registers one. Operators and those plugins depend on the `hooks` verbs, the event names, the registry file and the environment a hook reads. Split from the engine CLI spec ([CLI](17-engine-cli.spec.md)) when the specs moved to temperspec's format.

## Behaviours

### HOK-B1 Registering a hook

WHEN `hooks add <event> -- <argv…>` is given THE engine CLI SHALL store the argv list in `<state root>/config/hooks.json` with a new hook id, keeping at most 20 hooks.

- GIVEN no hook WHEN `hooks add finished -- notify-send done` runs THEN `hooks list` shows one hook for `finished` with that argv
- GIVEN 20 hooks WHEN another is added THEN it is refused and the registry is unchanged
- GIVEN a hook id WHEN `hooks remove <id>` runs THEN the hook is gone from the registry

### HOK-B2 Events a hook may name

WHEN a hook is added THE engine CLI SHALL accept the run events `started`, `unit_entered`, `gate_verdict`, `paused`, `resumed`, `stop_requested`, `finished` and `failed` ([EVT-B22, EVT-B23, EVT-B24](30-run-events.spec.md)), and refuse `stalled`, the orchestration events `orchestration_attention` and `orchestration_finished` ([ORC](45-orchestration.spec.md)) and the schedule events `schedule_fired`, `schedule_missed`, `schedule_refused` and `schedule_paused` ([SCH-B28](83-schedules.spec.md)) until a record marks them.

- GIVEN `hooks add paused -- notify` WHEN it runs THEN the hook is stored
- GIVEN `hooks add stalled -- notify` WHEN it runs THEN it is refused as not built yet

### HOK-B3 How a hook runs

WHEN a run event a hook names happens THE engine SHALL run the hook as a detached child in the main checkout, with a 60 s limit, with `TEMPERGRAPH_HOOK_EVENT` and `TEMPERGRAPH_HOOK_FACTS` (the path of a facts file) in its environment and never with run text on its argv ([SEC-B5, SEC-B6](14-security.spec.md)).

- GIVEN a hook on `finished` WHEN the run finishes THEN the hook reads `finished` from `TEMPERGRAPH_HOOK_EVENT` and the facts file from `TEMPERGRAPH_HOOK_FACTS`
- GIVEN a hook that sleeps for 90 s WHEN it runs THEN it is ended at 60 s

### HOK-B4 A hook's output and result

WHEN a hook ends THE engine SHALL write its output to `runs/<workflow>/<thread>/hooks/<event>-<seq>.<hook id>.log` and its result as one line of `hooks/results.jsonl` there.

- GIVEN a hook on `paused` that prints `sent` WHEN the run pauses THEN the log file holds `sent` and `results.jsonl` has one line for it

### HOK-B5 A hook never changes the run

WHEN a hook fails THE engine SHALL record the failure and leave the run and its exit code unchanged.

- GIVEN a hook that exits 1 on `finished` WHEN a run finishes with exit 0 THEN the run still exits 0 and the hook's result line records the failure

### HOK-B6 Testing a hook

WHEN `hooks test <event>` is given THE engine CLI SHALL run the event's hooks once against a fixture facts file and exit 6 when a hook failed.

- GIVEN a hook that exits 1 WHEN `hooks test finished` runs THEN the command exits 6

## Acceptance criteria

- HOK-AC1 (HOK-B1): `hooks add`, `list` and `remove` keep the registry in `<state root>/config/hooks.json`, refusing a 21st hook
- HOK-AC2 (HOK-B2): A hook on each built run event is accepted, and one on `stalled`, an orchestration event or a schedule event is refused
- HOK-AC3 (HOK-B3): A hook reads its event and facts path from its environment, has no run text on its argv, and is ended at 60 s
- HOK-AC4 (HOK-B4): After a hook runs, its log file and its line in `hooks/results.jsonl` exist under the thread's folder
- HOK-AC5 (HOK-B5): A failing hook leaves the run's exit code unchanged
- HOK-AC6 (HOK-B6): `hooks test` exits 6 when a hook failed and 0 when every hook passed
