# list_components

## 1. Overview

A script, with no model session, lists the top-level folders of the repository that hold components, so that each is read by its own reading session before the setup step writes the specs.

Part of the [overview](overview.spec.md). It runs on the path of a repository with no overview spec, after the [setup route](setup-route.spec.md), and writes a list of the folders other than hidden ones, dependency folders, build-output folders and the documentation folder, or an empty list for fewer than two ([parallel reading](parallel-reading.spec.md), PRL-B4 and PRL-B5). The list is read by [read_component](read-component.spec.md) and feeds the [setup](setup.spec.md) step.

## 6. Acceptance criteria

None: the unit has no gate criteria. `tests/test_parallel_reading.py` covers the script.
