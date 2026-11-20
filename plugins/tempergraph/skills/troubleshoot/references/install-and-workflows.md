# Install, and workflows that will not load, register, audit or stamp

## Install

- `tempergraph install --check --json` is read-only: the Python found, the engine environment, the shim and the `PATH` block.
- Exit 127 from `tempergraph` means the shim is not on `PATH` or the engine is not installed: hand over to the install skill.
- A new terminal is needed after the `PATH` block is added.

## A workflow that will not load

`tempergraph workflows list` shows each entry's `state` and `reason`. `not_loaded` reasons name the load step that failed:

| Reason | Usually |
|---|---|
| `manifest` | `tempergraph.json` or `.claude-plugin/plugin.json` is missing a field or has an unknown one |
| `workflow_api_newer`, `workflow_api_retired` | The package needs a newer engine, or an upgrade; the remedy is in the entry |
| `dependency_refused` | A declared requirement the dependency gate refuses |
| `import`, `build` | The declaration raised; the exception type is in the reason |
| `invalid` | Validation errors: run `tempergraph validate <workflow>` |

## Audit and stamp

- `tempergraph audit <workflow> --format json` lists findings with a remedy each. It is advisory and read-only.
- `tempergraph upgrade-check <workflow>` (without `--stamp`) shows the compatibility state and any changelog hits. A stamp is refused when a check fails; the failing check names its evidence.

## An authored workflow

`tempergraph author show <id>` shows a session's next phase and findings. `author verify` stops at its first failing rung, named in its report; the authoring skill knows how to fix each rung.
