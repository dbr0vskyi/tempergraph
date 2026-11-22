"""The self-check a new engine environment runs (UPD-B14, UPD-B6 step 4): its version and an import check of every
executor module; no probe, no model. Prints one JSON document."""

from __future__ import annotations

import importlib
import json
import sys


def main() -> int:
    from tempergraph.release import release

    rel = release()
    imports: dict[str, str] = {}
    try:  # the registry imports every shipped executor module (ADR-0091: claude only)
        from tempergraph.executors.registry import default_registry

        imports = {name: "ok" for name in default_registry().available()}
    except Exception as exc:  # noqa: BLE001
        imports = {"registry": type(exc).__name__}
    importlib.import_module("tempergraph.cli.main")
    sys.stdout.write(json.dumps({"schema_version": 1, "engine_version": rel["engine_version"],
                                 "workflow_api": rel["workflow_api"], "executors": imports}) + "\n")
    return 0 if all(v == "ok" for v in imports.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
