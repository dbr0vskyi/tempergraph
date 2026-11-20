"""`install` (UPD §2.7): run by the plugin's launcher with the first real Python 3.11+, or through the shim.

The launcher accepts `install` and `update`; `update` is built in release 2 (ADR-0090) and is refused with
exit 2 here. Steps: 1 Python, 2 home, 3 engine (update steps 3 and 4 into the first environment, then
`current.json`), 4 shim and `PATH` block, 5 registry (created, then reconciled inside the new environment),
6 report. Exit codes: 0 done or already current, 2 refused (no Python, not in this release), 1 failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Any

from tempergraph.install import environment as envmod
from tempergraph.install import shim
from tempergraph.install.python import find_python
from tempergraph.release import release
from tempergraph.store.layout import ensure_home, home_path

NOT_INSTALLED = 127
EXTRAS = ("agent-sdk", "messages-api")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tempergraph install")
    p.add_argument("--check", action="store_true", help="look up and print the plan; read-only")
    p.add_argument("--json", action="store_true")
    p.add_argument("--with", dest="extras", action="append", default=[], choices=EXTRAS)
    p.add_argument("--add-to-path", action="store_true")
    p.add_argument("--repair", action="store_true", help="rewrite the shim and current.json; install nothing")
    return p


def _report(out: IO[str], lines: list[dict[str, Any]], as_json: bool) -> None:
    for line in lines:
        out.write((json.dumps(line) if as_json else f"{line['kind']}: {line['says']}") + "\n")


def install(argv: Sequence[str], *, home: Path | None = None, builder: envmod.Builder | None = None,
            out: IO[str] | None = None, shell: str | None = None, user_home: Path | None = None) -> int:
    out = out or sys.stdout
    a = parser().parse_args(list(argv))
    home = home or home_path()
    lines: list[dict[str, Any]] = []
    python = find_python()  # step 1
    if python is None:
        lines.append({"kind": "engine", "says": "no Python 3.11 or newer found; install one (python.org, your "
                      "package manager) or set TEMPERGRAPH_PYTHON", "state": "no_python"})
        _report(out, lines, a.json)
        return 2
    exe, ver = python
    cur = envmod.current(home)
    engine = envmod.staged_engine()
    if a.check:
        state = "current" if cur else ("would_install" if engine else "no_staged_engine")
        lines += [{"kind": "engine", "says": f"Python {ver[0]}.{ver[1]} at {exe}; engine {state}", "state": state,
                   "python": exe},
                  {"kind": "summary", "says": "read-only check; nothing written"}]
        _report(out, lines, a.json)
        return 0
    ensure_home(home)  # step 2
    b = builder or envmod.VenvBuilder()
    if a.repair:
        env = envmod.newest_complete(home)
        if env is None:
            lines.append({"kind": "engine", "says": "no complete engine environment to repair from", "state": "none"})
            _report(out, lines, a.json)
            return 1
        envmod.switch(home, envmod.Installed(env=env, engine_version=env.name.split("-", 1)[0],
                                             digest=env.name.split("-", 1)[-1], check={}))
        lines.append({"kind": "engine", "says": f"current.json points at {env.name}", "state": "repaired"})
    elif cur is not None:
        lines.append({"kind": "engine", "says": f"engine {cur.get('engine_version')} is already current; "
                      "`tempergraph update` moves to a newer one", "state": "current"})
    else:
        if engine is None:
            lines.append({"kind": "engine", "says": "no staged engine beside this code; run the plugin's "
                          "bin/tempergraph install", "state": "no_staged_engine"})
            _report(out, lines, a.json)
            return 1
        try:
            inst = envmod.install_engine(home, exe, engine, b, tuple(a.extras))  # step 3
        except envmod.InstallFailed as exc:
            lines.append({"kind": "engine", "says": f"install failed: {exc}; nothing was switched", "state": "failed"})
            _report(out, lines, a.json)
            return 1
        envmod.switch(home, inst)
        lines.append({"kind": "engine", "says": f"installed engine {inst.engine_version} ({inst.env.name})",
                      "state": "installed", "executors": inst.check.get("executors", {})})
    lines.append({"kind": "extras", "says": ", ".join(a.extras) or "none asked",
                  "available": sorted(release().get("extras") or {})})
    wrote = shim.write_shim(home)  # step 4
    name, file = shim.shell_file(shell, user_home)
    path_state = "on_path" if shim.on_path(home) else "not_on_path"
    if a.add_to_path:
        file, added = shim.add_to_path(home, shell, user_home)
        path_state = "added" if added else "already_added"
    lines.append({"kind": "shim", "says": f"{shim.shim_path(home)} {'written' if wrote else 'unchanged'}; PATH "
                  f"{path_state}", "path_state": path_state, "shell_file": str(file),
                  "block": shim.path_block(home, name)})
    cur = envmod.current(home)  # step 5
    reg_path = home / "registry.json"
    if not reg_path.exists():
        from tempergraph.docs import write_json

        write_json(reg_path, {"schema_version": 1, "workflows": []})
    rec = b.reconcile(Path(str(cur["path"]))) if cur else {"error": "no current engine"}
    lines.append({"kind": "workflow", "says": rec.get("error") or f"{len(rec.get('workflows') or [])} workflow "
                  "plugin(s) registered from the plugin cache", "registry": rec})
    lines.append({"kind": "summary", "says": "next: open a new terminal (or add the PATH block), run "
                  "`tempergraph executors --probe`, then bootstrap each repository"})
    _report(out, lines, a.json)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    verb, rest = (args[0], args[1:]) if args else ("", [])
    if verb == "install":
        return install(rest)
    if verb == "update":
        sys.stderr.write("tempergraph: update is built in release 2; this release installs only\n")
        return 2
    sys.stderr.write("tempergraph: the engine is not installed; run: bin/tempergraph install\n")
    return NOT_INSTALLED


if __name__ == "__main__":
    raise SystemExit(main())
