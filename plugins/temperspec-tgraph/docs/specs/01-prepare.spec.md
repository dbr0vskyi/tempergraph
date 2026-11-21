# prepare

## 1. Overview

A script with no session, first in every run. It installs the rule files when neither the repository nor the machine has them, keeps the temperspec block in the project-context file (`CLAUDE.md`, or `AGENTS.md` when that is the file the repository has), commits both, and reports whether the repository has an overview spec.

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

None: the unit has no gate criteria. `tests/test_temperspec.py` covers the script.
