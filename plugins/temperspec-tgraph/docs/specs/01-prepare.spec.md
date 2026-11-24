# prepare

## 1. Overview

A script with no session, first in every run. It installs the rule files unless the repository or the machine already has them, keeps the temperspec block in the project-context file (`CLAUDE.md`, or `AGENTS.md` when that is the file the repository has) from the folders the repository really uses, unless that file already says where the specs live, commits what it changed, and reports whether the repository has an overview spec. What it writes, and when it leaves the file alone, is in [project note](project-note.spec.md).

Part of the [overview](00-overview.spec.md).

## 6. Acceptance criteria

None: the unit has no gate criteria. `tests/test_temperspec.py` covers the script.
