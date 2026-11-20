"""Registry reconcile, run inside an engine environment by `install` step 5 and `update` step 6 (UPD §2.8).
Prints one JSON document; a constant module the updater's launch site starts."""

from __future__ import annotations

import json
import sys


def main() -> int:
    from tempergraph.executors.registry import default_registry
    from tempergraph.package.registry import reconcile

    reg = default_registry()
    caps = {n: reg.get(n).capabilities() for n in reg.available()}
    done = reconcile(caps)
    sys.stdout.write(json.dumps({"schema_version": 1, "workflows": [
        {"name": c.entry.get("name"), "plugin": c.entry.get("plugin"), "state": c.entry.get("state"),
         "version": c.entry.get("version"), "findings": [f.code for f in c.findings]} for c in done]}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
