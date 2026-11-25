# read_component

## 1. Overview

The findings of the reading of one component folder say what the folder holds, or state what was searched, and name the files they rest on

Part of the [overview](overview.spec.md). The [setup](setup.spec.md) step starts with one read-only reading session for each component folder that [list_components](list-components.spec.md) lists, three at a time on the engine's concurrent map; its one writing session then writes the specs from their findings ([parallel reading](parallel-reading.spec.md)).

## 6. Acceptance criteria

- [ ] ts-rdc-answers The findings (`component_finding`) of a component folder's reading say what the folder holds and what someone outside depends on, or state what was searched
- [ ] ts-rdc-cited The findings (`component_finding`) name each file they rest on with its line ranges or ids
