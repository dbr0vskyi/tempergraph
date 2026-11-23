"""`update` (UPD-B14, UPD-B6, UPD-B17): the plan, the install beside the current engine, the switch, rollback and
`--prune-engines`. Deterministic, no model. Like `install`, this module imports only the standard library and
the stdlib-only engine modules; registered workflows are reinstalled and checked inside the new environment.

Exit codes: 0 done, up to date or a read-only check; 2 refused (downgrade, no engine, rollback across a
layout the previous engine cannot read); 1 failed, with nothing switched.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Any

from tempergraph.docs import write_json
from tempergraph.install import environment as envmod
from tempergraph.install import shim
from tempergraph.install.python import find_python
from tempergraph.release import release
from tempergraph.store.layout import home_path, now_iso

EXTRAS = ("agent-sdk", "messages-api")
KEEP_UNPINNED = 2  # old engines kept before the report suggests `--prune-engines` (UPD open question)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tempergraph update")
    p.add_argument("--check", action="store_true", help="plan only; read-only")
    p.add_argument("--dry-run", action="store_true", help="print the plan with every write it would make")
    p.add_argument("--json", action="store_true")
    p.add_argument("--with", dest="extras", action="append", default=[], choices=EXTRAS)
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--restore-backups", action="store_true")
    p.add_argument("--prune-engines", action="store_true")
    return p


def _version(v: Any) -> tuple[int, ...]:
    return tuple(int(p) if p.isdigit() else 0 for p in str(v or "0").split("+", 1)[0].split("."))


def _read(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def source_release(engine: Path) -> dict[str, Any]:
    """The release record of the staged engine, read from its files (it may be newer than this code)."""
    return _read(engine / "src" / "tempergraph" / "data" / "release.json") or dict(release())


def find_source() -> Path | None:
    """UPD-B14, UPD-B6 step 1: the staged engine of the plugin copy that invoked the verb; no option names a path.
    Through the shim, the plugin copy is the one Claude Code names in `CLAUDE_PLUGIN_ROOT`."""
    here = envmod.staged_engine()
    if here is not None:
        return here
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    cand = Path(root) / "engine" if root else None
    return cand if cand and (cand / "pyproject.toml").is_file() and (cand / "src" / "tempergraph").is_dir() else None


def index_roots(home: Path) -> list[Path]:
    """The state roots of the machine index (CST-B8) that still exist."""
    doc = _read(home / "index.json")
    got = doc.get("roots")
    roots = got if isinstance(got, list) else []
    return [Path(str(r.get("path"))) for r in roots if isinstance(r, dict) and Path(str(r.get("path"))).is_dir()]


def live_processes(roots: Sequence[Path]) -> list[dict[str, Any]]:
    """Each live run with the engine its lock names (MIG-B8); a lock is live while its holder file is."""
    out = []
    for root in roots:
        for holder in sorted((root / "locks").glob("*/*.holder.json")) if (root / "locks").is_dir() else []:
            doc = _read(holder)
            pid = doc.get("pid")
            if not isinstance(pid, int) or not _alive(pid):
                continue
            out.append({"thread_id": f"{holder.parent.name}/{holder.name[:-len('.holder.json')]}",
                        "state_root": str(root), "pid": pid, "engine": doc.get("engine"),
                        "engine_version": doc.get("engine_version")})
    return out


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def thread_pins(roots: Sequence[Path]) -> list[dict[str, Any]]:
    """Threads pinned to an engine (MIG-B12, MIG-B13, MIG-B14), from each thread's `engine.json`."""
    out = []
    for root in roots:
        for f in sorted((root / "runs").glob("*/*/engine.json")) if (root / "runs").is_dir() else []:
            pin = _read(f).get("pinned")
            if isinstance(pin, dict) and pin.get("engine"):
                out.append({"thread_id": f"{f.parent.parent.name}/{f.parent.name}", "state_root": str(root),
                            "engine": pin.get("engine"), "reason": pin.get("reason")})
    return out


def workflow_pins(home: Path) -> list[dict[str, Any]]:
    entries = _read(home / "registry.json").get("workflows") or []
    return [{"workflow": e.get("name"), "engine": e["engine_pin"].get("engine"), "reason": e["engine_pin"].get("reason")}
            for e in entries if isinstance(e, dict) and isinstance(e.get("engine_pin"), dict)]


def store_layouts(home: Path, roots: Sequence[Path]) -> list[dict[str, Any]]:
    out = []
    for kind, folder in [("home", home), *(("state_root", r) for r in roots)]:
        man = _read(folder / "manifest.json")
        out.append({"kind": kind, "path": str(folder), "layout": man.get("layout"),
                    "backup": man.get("backup"), "moved_by": man.get("moved_by")})
    return out


def plan(home: Path, engine: Path | None) -> dict[str, Any]:
    """UPD-B14, UPD-B6 step 2: what an update would do; reads only."""
    cur = envmod.current(home)
    if engine is None:
        return {"decision": "no_source", "current": cur}
    rel = source_release(engine)
    digest = envmod.source_digest(engine)
    target = {"engine_version": rel.get("engine_version"), "digest": digest,
              "folder": f"{rel.get('engine_version')}-{digest[:12]}", "store_layout": rel.get("store_layout")}
    if cur is None:
        decision = "no_engine"
    elif _version(cur.get("engine_version")) > _version(target["engine_version"]):
        decision = "refused_downgrade"
    elif cur.get("engine_version") == target["engine_version"] and cur.get("digest") == digest:
        decision = "up_to_date"
    elif cur.get("engine_version") == target["engine_version"]:
        decision = "reinstall"
    else:
        decision = "install"
    roots = index_roots(home)
    layouts = store_layouts(home, roots)
    new_layout = int(rel.get("store_layout") or 0)
    return {"decision": decision, "current": cur, "target": target, "release": rel,
            "live": live_processes(roots), "thread_pins": thread_pins(roots), "workflow_pins": workflow_pins(home),
            "stores": [{**s, "moves": isinstance(s["layout"], int) and s["layout"] < new_layout} for s in layouts],
            "extras": list((cur or {}).get("extras") or [])}


ENGINE_SAYS = {
    "up_to_date": "engine {cur} is up to date",
    "install": "will install engine {new} beside {cur}",
    "reinstall": "will reinstall engine {new}: same version, other content",
    "refused_downgrade": "refused: the installed engine {cur} is newer than this copy's {new}; an older "
                         "tempergraph is probably first on PATH, so run the newer copy's `tempergraph update`",
    "no_engine": "no engine is installed; run `tempergraph install` first",
    "no_source": "no staged engine found beside this code; run the tempergraph plugin's bin/tempergraph update",
}


def _plan_lines(p: dict[str, Any], installed: bool = False) -> list[dict[str, Any]]:
    """UPD-B15: one line per kind, each with a fixed key set."""
    cur, target = p.get("current") or {}, p.get("target") or {}
    says = ENGINE_SAYS[p["decision"]].format(cur=cur.get("engine_version"), new=target.get("engine_version"))
    if installed:
        says = f"installed engine {target.get('engine_version')} ({target.get('folder')})"
    lines: list[dict[str, Any]] = [{"kind": "engine", "says": says, "decision": p["decision"],
                                    "state": "installed" if installed else p["decision"],
                                    "current": cur.get("engine_version"), "target": target.get("engine_version"),
                                    "digest": target.get("digest")}]
    rel_extras = (p.get("release") or {}).get("extras") or {}
    for name in sorted(rel_extras):
        lines.append({"kind": "extras", "says": f"{name} {rel_extras[name]}: "
                      f"{'installed' if name in p.get('extras', []) else 'not installed'}", "name": name,
                      "range": rel_extras[name], "state": "installed" if name in p.get("extras", []) else "absent"})
    if not rel_extras:
        lines.append({"kind": "extras", "says": "this release has no optional executor package", "name": None,
                      "range": None, "state": "none"})
    for lv in p.get("live") or []:
        lines.append({"kind": "live", "says": f"{lv['thread_id']} keeps engine {lv.get('engine_version') or '?'} "
                      "until it exits", "thread_id": lv["thread_id"], "pid": lv["pid"],
                      "engine": lv.get("engine_version"), "state_root": lv["state_root"]})
    by_root: dict[str, list[dict[str, Any]]] = {}
    for t in p.get("thread_pins") or []:
        by_root.setdefault(t["state_root"], []).append(t)
    for root, pins in sorted(by_root.items()):
        lines.append({"kind": "threads", "says": f"{len(pins)} thread(s) pinned to an older engine in {root}",
                      "state_root": root, "pinned": len(pins),
                      "reasons": sorted({str(t.get("reason")) for t in pins})})
    for s in p.get("stores") or []:
        if s.get("moves"):
            lines.append({"kind": "store", "says": f"{s['path']} moves from layout {s['layout']} at the first "
                          "run on the new engine, with a backup", "path": s["path"], "from_layout": s["layout"],
                          "backup": True})
    return lines


def _workflow_lines(rec: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for w in rec.get("workflows") or []:
        pin = w.get("engine_pin") or {}
        local = w.get("kind") == "local"
        remedy = (f"tempergraph upgrade {w.get('name')}" if local else "update the workflow's plugin") if pin or \
            w.get("state") == "not_loaded" else ""
        says = f"{w.get('name')} {w.get('version') or ''}: {w.get('state')}" + (
            f", pinned to engine {pin.get('engine')} ({pin.get('reason')}); it keeps working there. {remedy}"
            if pin else f". {remedy}" if remedy else "")
        out.append({"kind": "workflow", "says": says, "name": w.get("name"), "version": w.get("version"),
                    "source": w.get("kind"), "state": w.get("state"), "dependencies": w.get("dependencies"),
                    "engine_pin": pin or None, "findings": w.get("findings") or [], "remedy": remedy})
    return out


def _report(out: IO[str], lines: list[dict[str, Any]], as_json: bool) -> None:
    for line in lines:
        out.write((json.dumps(line) if as_json else f"{line['kind']}: {line['says']}") + "\n")


def kept_engines(home: Path, roots: Sequence[Path]) -> dict[str, str]:
    """UPD-B11, UPD-B12, UPD-B13: the environments `--prune-engines` never removes, each with why."""
    eng = envmod.engines_dir(home)
    kept: dict[str, str] = {}
    for name in ("current", "previous"):
        path = _read(eng / f"{name}.json").get("path")
        if path:
            kept.setdefault(Path(str(path)).name, name)
    for w in workflow_pins(home):
        kept.setdefault(str(w["engine"]), f"workflow {w['workflow']} is pinned to it")
    for t in thread_pins(roots):
        kept.setdefault(str(t["engine"]), f"thread {t['thread_id']} is pinned to it")
    for lv in live_processes(roots):
        if lv.get("engine"):
            kept.setdefault(str(lv["engine"]), f"live run {lv['thread_id']} runs on it")
    return kept


def prune(home: Path, *, dry_run: bool = False) -> list[dict[str, Any]]:
    eng = envmod.engines_dir(home)
    kept = kept_engines(home, index_roots(home))
    lines: list[dict[str, Any]] = []
    for env in sorted(p for p in eng.iterdir() if p.is_dir()) if eng.is_dir() else []:
        why = kept.get(env.name)
        if why:
            lines.append({"kind": "engine", "says": f"kept {env.name}: {why}", "state": "kept", "engine": env.name,
                          "reason": why})
            continue
        if not dry_run:
            shutil.rmtree(env, ignore_errors=True)
        lines.append({"kind": "engine", "says": f"{'would remove' if dry_run else 'removed'} {env.name}",
                      "state": "would_remove" if dry_run else "removed", "engine": env.name, "reason": None})
    return lines


def rollback(home: Path, *, restore_backups: bool = False, dry_run: bool = False) -> tuple[int, list[dict[str, Any]]]:
    """UPD-B17: swap `current.json` and `previous.json`, unless a store's layout is one the previous engine
    cannot read; `--restore-backups` restores each such store's pre-migration backup when nothing ran since."""
    from tempergraph.store import migrate

    eng = envmod.engines_dir(home)
    cur, prev = _read(eng / "current.json"), _read(eng / "previous.json")
    if not prev or not (Path(str(prev.get("path") or "")) / ".complete").is_file():
        return 2, [{"kind": "engine", "says": "no previous engine to roll back to", "state": "refused"}]
    reads = [int(n) for n in prev.get("reads_store_layouts") or [1]]
    blocked = [s for s in store_layouts(home, index_roots(home)) if isinstance(s["layout"], int)
               and s["layout"] not in reads]
    lines: list[dict[str, Any]] = []
    for s in blocked:
        ok = restore_backups and migrate.restorable(Path(s["path"]))
        lines.append({"kind": "store", "says": f"{s['path']} has layout {s['layout']}, which engine "
                      f"{prev.get('engine_version')} cannot read" + ("; its backup will be restored" if ok else ""),
                      "path": s["path"], "from_layout": s["layout"], "backup": bool(ok)})
        if not ok:
            lines.append({"kind": "summary", "says": "rollback refused; pass --restore-backups to restore each "
                          "store's pre-migration backup when no run has written to it since"
                          if not restore_backups else f"rollback refused: {s['path']} has been written to since "
                          "its migration, so its backup cannot be restored"})
            return 2, lines
    if dry_run:
        lines.append({"kind": "summary", "says": f"would switch back to engine {prev.get('engine_version')}"})
        return 0, lines
    for s in blocked:
        migrate.restore(Path(s["path"]))
    write_json(eng / "previous.json", cur)
    write_json(eng / "current.json", {**prev, "switched_at": now_iso()})
    lines.append({"kind": "engine", "says": f"switched back to engine {prev.get('engine_version')}; "
                  f"{cur.get('engine_version')} is kept as previous", "state": "rolled_back",
                  "current": prev.get("engine_version"), "target": cur.get("engine_version")})
    return 0, lines


def update(argv: Sequence[str], *, home: Path | None = None, builder: envmod.Builder | None = None,
           out: IO[str] | None = None, engine: Path | None = None, plugin_version: str | None = None) -> int:
    out = out or sys.stdout
    a = parser().parse_args(list(argv))
    home = home or home_path()
    if a.rollback:
        code, lines = rollback(home, restore_backups=a.restore_backups, dry_run=a.dry_run or a.check)
        _report(out, lines, a.json)
        return code
    if a.prune_engines:
        _report(out, prune(home, dry_run=a.dry_run or a.check), a.json)
        return 0
    engine = engine or find_source()
    p = plan(home, engine)
    lines = _plan_lines(p)
    decision = p["decision"]
    if a.check or a.dry_run or decision in ("up_to_date", "refused_downgrade", "no_engine", "no_source"):
        if a.dry_run and decision in ("install", "reinstall"):
            lines.append({"kind": "summary", "says": "would write: "
                          f"engines/{p['target']['folder']}/, engines/previous.json, engines/current.json, "
                          "registry.json; nothing was written"})
        else:
            lines.append({"kind": "summary", "says": {
                "up_to_date": "you are on the latest engine of this plugin copy; nothing to do",
                "install": "an update is available: run `tempergraph update`",
                "reinstall": "this plugin copy's engine differs from the installed one: run `tempergraph update`",
            }.get(decision, ENGINE_SAYS[decision].format(cur=(p.get("current") or {}).get("engine_version"),
                                                         new=(p.get("target") or {}).get("engine_version")))})
        _report(out, lines, a.json)
        return 2 if decision in ("refused_downgrade", "no_engine", "no_source") and not a.check else 0
    python = find_python()
    if python is None:
        _report(out, [{"kind": "engine", "says": "no Python 3.11 or newer found; install one or set "
                       "TEMPERGRAPH_PYTHON", "decision": decision, "state": "no_python", "current": None,
                       "target": None, "digest": None}], a.json)
        return 2
    assert engine is not None
    b = builder or envmod.VenvBuilder()
    extras = tuple(dict.fromkeys([*p["extras"], *a.extras]))
    rel = p["release"]
    try:
        inst = envmod.install_engine(home, python[0], engine, b, extras, version=str(rel["engine_version"]))  # 3, 4
        from tempergraph.store import migrate

        migrate.migrate(home, target=int(rel.get("store_layout") or 1), engine=str(rel["engine_version"]))  # 5
    except (envmod.InstallFailed, OSError, RuntimeError) as exc:  # a complete new folder may stay; it is prunable
        _report(out, [{"kind": "engine", "says": f"update failed: {exc}; nothing was switched",
                       "decision": decision, "state": "failed", "current": (p["current"] or {}).get("engine_version"),
                       "target": rel.get("engine_version"), "digest": p["target"]["digest"]}], a.json)
        return 1
    old = Path(str(p["current"]["path"])).name
    envmod.switch(home, inst, extras=extras, release_doc=rel)  # 6
    shim.write_shim(home)
    from tempergraph.schedule import triggers

    triggers.refresh(home)  # TCK-B8: an `os` entry is rewritten only if the shim path changed; nothing when none exists
    rec = b.reconcile(inst.env, previous=old)
    lines = _plan_lines(p, installed=True)
    if rec.get("error"):
        lines.append({"kind": "workflow", "says": f"registry not reconciled: {rec['error']}", "name": None,
                      "version": None, "source": None, "state": "error", "dependencies": None, "engine_pin": None,
                      "findings": [], "remedy": "tempergraph workflows reinstall --all"})
    lines += _workflow_lines(rec)
    if plugin_version or os.environ.get("CLAUDE_PLUGIN_ROOT"):
        pv = plugin_version or str(_read(Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / ".claude-plugin" / "plugin.json")
                                   .get("version") or "")
        same = pv == str(rel["engine_version"])
        lines.append({"kind": "plugin", "says": f"plugin {pv} {'matches' if same else 'differs from'} engine "
                      f"{rel['engine_version']}" + ("" if same else "; run /reload-plugins"), "plugin": pv,
                      "engine": rel["engine_version"], "match": same})
    unpinned = [e for e in (envmod.engines_dir(home).iterdir()) if e.is_dir()
                and e.name not in kept_engines(home, index_roots(home))]
    pinned = [w for w in lines if w["kind"] == "workflow" and w.get("engine_pin")]
    lines.append({"kind": "summary", "says": f"you are on engine {rel['engine_version']}"
                  + (f"; {len(pinned)} workflow(s) stay on the previous engine until upgraded" if pinned
                     else "; nothing else to do")
                  + (f"; {len(unpinned)} old engine(s) can go with `tempergraph update --prune-engines`"
                     if len(unpinned) > KEEP_UNPINNED else "")})
    _report(out, lines, a.json)
    return 0
