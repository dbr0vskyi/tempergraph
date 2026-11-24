# code_mode

## 1. Overview

The switch after the plan. It receives the plan and the seven facts the plan check recorded, produces no file, and has no session, gate or approval. It sends the run to [code](08-code.spec.md) for the arm `single`, or to [expand](07-expand.spec.md) for the arm `phases`, the safe arm. A run that goes from triage straight to code never reaches it. Its behaviours, its rules file `routing/code_mode.json`, the operator's `--arm code_mode=<arm>` and the report by arm are those of [code mode](code-mode.spec.md), which this page does not restate.

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

None: a switch has no gate criteria; the criteria of the route are those of [code mode](code-mode.spec.md).
