"""Registry reconcile, run inside an engine environment by `install` step 5 and `update` step 6 (UPD §2.8).
Prints one JSON document; a constant module the updater's launch site starts. With `--install` (an update)
each workflow's declared requirements are installed into this environment from an engine-owned file, and
`--previous <engine folder>` names the engine a workflow that broke is pinned to."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def pip_installer(name: str, lines: list[str]) -> str | None:
    """Install from an engine-owned requirements file, so no package text reaches the installer's argv."""
    from tempergraph.install.launch import INSTALL_TIMEOUT_S, run
    from tempergraph.package.importer import private_name

    folder = Path(sys.prefix) / "tempergraph-requirements"
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / f"{private_name(name)}.txt"
    file.write_text("".join(ln.strip() + "\n" for ln in lines), encoding="utf-8")
    got = run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r", str(file)],
              timeout_s=INSTALL_TIMEOUT_S)
    return None if got.code == 0 else f"pip install failed ({got.code}): {got.err.strip()[-300:]}"


def main(argv: list[str] | None = None) -> int:
    from tempergraph.executors.registry import default_registry
    from tempergraph.package.registry import after_update, reconcile

    p = argparse.ArgumentParser(prog="tempergraph.install.reconcile")
    p.add_argument("--previous")
    p.add_argument("--install", action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    reg = default_registry()
    caps = {n: reg.get(n).capabilities() for n in reg.available()}
    if a.install:
        env = Path(sys.prefix)
        done = after_update(caps, previous=a.previous, engine=env.name, installer=pip_installer)
    else:
        done = reconcile(caps)
    sys.stdout.write(json.dumps({"schema_version": 1, "workflows": [
        {"name": c.entry.get("name"), "plugin": c.entry.get("plugin"), "kind": c.entry.get("kind"),
         "state": c.entry.get("state"), "version": c.entry.get("version"),
         "engine_pin": c.entry.get("engine_pin"), "dependencies": c.entry.get("dependencies"),
         "findings": [f.code for f in c.findings]} for c in done]}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
