"""What a thread records about engines and workflow versions, and what happens to it at its next resume
(MIG-B8, MIG-B12, MIG-B13, MIG-B14, MIG-B15). The rule: move at the resume boundary, pin only on a break (ADR-0056).

`engine.json` sits beside the thread's run log. The decisions here are pure functions over that document, the
release record and the kept engines, so every row of MIG's tables is a test without a second engine installed.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tempergraph.constants import ENGINE_VERSION
from tempergraph.contracts import WorkflowSpec
from tempergraph.docs import write_json
from tempergraph.store.layout import now_iso, run_dir

FILE = "engine.json"
HISTORY_KEPT = 50


def path(root: Path, workflow: str, task_id: str) -> Path:
    return run_dir(root, workflow, task_id) / FILE


def read(root: Path, workflow: str, task_id: str) -> dict[str, Any]:
    """A thread from before this record reads as started on an unknown engine, not pinned (MIG-B16, MIG-B12, MIG-B10, MIG-B15)."""
    try:
        doc = json.loads(path(root, workflow, task_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def this_engine() -> dict[str, Any]:
    """The engine this process runs on: its version, and its environment folder when it is a managed one."""
    env = Path(sys.prefix)
    managed = env.parent.name == "engines"
    return {"engine_version": ENGINE_VERSION, "engine": env.name if managed else None}


def checkpoint_format() -> int:
    from tempergraph.release import release

    return int(release().get("checkpoint_format") or 1)


def unit_digests(spec: WorkflowSpec) -> dict[str, dict[str, Any]]:
    """Per unit: its kind, the keys it produces and a digest of everything declared on it."""
    from tempergraph.package.inventory import canonical

    out: dict[str, dict[str, Any]] = {}
    for name, u in spec.units.items():
        body = json.dumps(canonical(u), sort_keys=True, separators=(",", ":"), default=str)
        produces = sorted((u.step.produces if u.step else {}) or {})
        out[name] = {"kind": str(u.kind), "digest": hashlib.sha256(body.encode()).hexdigest()[:16],
                     "produces": produces}
    return out


def last(doc: Mapping[str, Any]) -> dict[str, Any]:
    hist = doc.get("history") or []
    return dict(hist[-1]) if hist and isinstance(hist[-1], dict) else {}


UNKNOWN = {"engine_version": None, "engine": "unknown"}


def record(root: Path, spec: WorkflowSpec, task_id: str, *, content_version: str, shape_digest: str,
           resumed: bool = False) -> dict[str, Any] | None:
    """One history entry for this process. Returns `moved_from` (the engine and workflow version of the
    previous process) when either differs from this one's, else None. A resumed thread with no engine file
    was started by a release before this file existed (MIG-B16, MIG-B12, MIG-B10, MIG-B15): `started_on` is unknown, never this engine,
    and `moved_from` says so."""
    doc = read(root, spec.name, task_id)
    eng = this_engine()
    prev = last(doc)
    legacy = resumed and not doc.get("history")
    entry = {**eng, "workflow_version": content_version, "shape_digest": shape_digest,
             "checkpoint_format": int(prev.get("checkpoint_format") or checkpoint_format()), "units": unit_digests(spec), "started_at": now_iso()}
    hist = [*(doc.get("history") or []), entry][-HISTORY_KEPT:]
    for old in hist[:-1]:  # only the latest entry needs the per-unit digests
        old.pop("units", None)
    started = doc.get("started_on") or (dict(UNKNOWN) if legacy else eng if not prev else None)
    new = {"schema_version": 1, "started_on": started,
           "last_on": eng, "pinned": doc.get("pinned"), "history": hist}
    write_json(path(root, spec.name, task_id), new)
    if legacy:
        return {"engine_version": "unknown", "workflow_version": None}
    moved = prev and (prev.get("engine_version") != eng["engine_version"]
                      or prev.get("workflow_version") != content_version)
    return {"engine_version": prev.get("engine_version"), "workflow_version": prev.get("workflow_version")} \
        if moved else None


def pin(root: Path, workflow: str, task_id: str, engine: str, reason: str) -> dict[str, Any]:
    doc = read(root, workflow, task_id)
    doc = {"schema_version": 1, **doc, "pinned": {"engine": engine, "reason": reason, "since": now_iso()}}
    write_json(path(root, workflow, task_id), doc)
    return doc


def unpin(root: Path, workflow: str, task_id: str) -> None:
    doc = read(root, workflow, task_id)
    if doc.get("pinned"):
        write_json(path(root, workflow, task_id), {**doc, "pinned": None})


def decide(doc: Mapping[str, Any], *, resumes: Sequence[int], kept: Mapping[str, Sequence[int]],
           current: str | None = None) -> tuple[str, str | None]:
    """MIG-B12, MIG-B13, MIG-B14: `("dispatch", engine)` for a pinned thread, `("move", None)` when this engine resumes the
    thread's checkpoint format, `("pin", engine)` to the newest kept engine that does, else
    `("refuse", message)`. `kept` maps each kept engine folder to the formats it resumes."""
    pinned = doc.get("pinned")
    if isinstance(pinned, Mapping) and pinned.get("engine"):
        return ("move", None) if pinned["engine"] == current else ("dispatch", str(pinned["engine"]))
    fmt = int(last(doc).get("checkpoint_format") or 1)
    if fmt in [int(f) for f in resumes]:
        return "move", None
    able = sorted((e for e, formats in kept.items() if fmt in [int(f) for f in formats] and e != current),
                  key=_folder_key)
    if able:
        return "pin", able[-1]
    return "refuse", (f"this thread's checkpoint format {fmt} is resumed by no installed engine; install an "
                      f"engine release that resumes format {fmt} beside this one, then resume")


def _folder_key(name: str) -> tuple[int, ...]:
    return tuple(int(p) if p.isdigit() else 0 for p in name.split("-", 1)[0].split("."))


def kept_engines(home: Path) -> dict[str, list[int]]:
    """Every complete engine environment and the checkpoint formats its release resumes."""
    out: dict[str, list[int]] = {}
    eng = home / "engines"
    for env in sorted(p for p in eng.iterdir() if (p / ".complete").is_file()) if eng.is_dir() else []:
        try:
            rel = json.loads((env / "release.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rel = {}
        out[env.name] = [int(f) for f in (rel.get("resumes_checkpoint_formats") or [1])]
    return out


def thread_format(root: Path, workflow: str, task_id: str) -> int:
    """The checkpoint format the thread was last written in; this engine's own for a new or unrecorded one."""
    return int(last(read(root, workflow, task_id)).get("checkpoint_format") or checkpoint_format())


def checkpoint_of(root: Path, workflow: str, task_id: str) -> Path:
    from tempergraph.store.layout import checkpoint_path

    return checkpoint_path(root, workflow, thread_format(root, workflow, task_id))


def resumes() -> list[int]:
    from tempergraph.release import release

    return [int(f) for f in release().get("resumes_checkpoint_formats") or [1]]


def at_resume(root: Path, workflow: str, task_id: str, home: Path | None = None, *, write: bool = True
              ) -> tuple[str, str | None]:
    """MIG-B12, MIG-B13, MIG-B14 for this process: `("move", None)`, `("dispatch", engine folder)` or `("refuse", message)`.
    A format break writes the pin first; a refusal writes nothing."""
    from tempergraph.store.layout import home_path

    home = home or home_path()
    doc = read(root, workflow, task_id)
    if doc and not doc.get("history"):
        doc = {**doc, "history": [{"checkpoint_format": 1}]}
    current = this_engine()["engine"]
    action, detail = decide(doc or {"history": [{"checkpoint_format": checkpoint_format()}]},
                            resumes=resumes(), kept=kept_engines(home), current=current)
    if action == "pin":
        if write:
            pin(root, workflow, task_id, str(detail), "checkpoint_format")
        action = "dispatch"
    if action == "dispatch" and not (home / "engines" / str(detail) / ".complete").is_file():
        return "refuse", (f"this thread is pinned to engine {detail}, which is no longer installed; run "
                          f"`tempergraph update` from a plugin copy of that version to install it beside the "
                          "current one, then resume")
    return action, detail


def try_unpin(root: Path, workflow: str, task_id: str) -> str | None:
    """`resume --unpin`: clear the pin when this engine resumes the thread's format. This release ships no
    checkpoint converter, so any other pin stays and the reason is returned."""
    doc = read(root, workflow, task_id)
    if not doc.get("pinned"):
        return None
    fmt = int(last(doc).get("checkpoint_format") or 1)
    if fmt not in resumes():
        return (f"this engine does not resume checkpoint format {fmt} and ships no converter for it; the "
                f"thread stays pinned to {doc['pinned'].get('engine')}")
    unpin(root, workflow, task_id)
    return None


# -- a workflow changed under a thread (MIG-B15) -----------------------------------------------------------------


def _reads(spec: WorkflowSpec, unit: str) -> set[str]:
    """The artifact keys a unit's prompt and judge read."""
    from tempergraph.model.text import TextUnreadable, load_text
    from tempergraph.render.template import TemplateError, fields

    u = spec.units[unit]
    out: set[str] = set()
    if u.step is not None:
        with contextlib.suppress(TextUnreadable, TemplateError):
            out |= set(fields(load_text(spec, u.step.prompt)))
    if u.gate.judge is not None:
        out |= set(u.gate.judge.references or ())
    return out


def breaks(prev: Mapping[str, Any], spec: WorkflowSpec, values: Mapping[str, Any], pending: Sequence[str]
           ) -> list[str]:
    """The four tests of MIG-B15 against the units of the previous process (`prev` is its history entry).
    An empty list means the thread may resume on the new content."""
    from tempergraph.model import flow

    old = prev.get("units") or {}
    out: list[str] = []
    order = [n for n in flow.effective_order(spec) if n in spec.units]
    for unit in pending:  # 1 the pending unit keeps its name and kind
        was = old.get(unit) or {}
        if unit not in spec.units:
            out.append(f"the pending unit {unit!r} no longer exists")
        elif was and was.get("kind") != str(spec.units[unit].kind):
            out.append(f"the pending unit {unit!r} changed kind from {was.get('kind')} to {spec.units[unit].kind}")
    done = [u for u in (values.get("attempts") or {}) if u not in pending]
    for unit in done:  # 2 every completed unit still exists
        if unit in old and unit not in spec.units:
            out.append(f"the completed unit {unit!r} no longer exists, so a trip back cannot find it")
    recorded = {u: set((values.get("artifacts") or {}).get(u) or {}) | set((values.get("values") or {}).get(u) or {})
                for u in done}
    later = [u for u in order if u not in done]
    needed = set().union(*(_reads(spec, u) for u in later)) if later else set()
    for unit in done:  # 3 a key a pending or later unit reads from a completed unit is recorded
        if unit not in spec.units or spec.units[unit].step is None:
            continue
        for key in sorted(set(spec.units[unit].step.produces or {}) & needed):  # type: ignore[union-attr]
            if key not in recorded.get(unit, set()):
                out.append(f"{unit!r} now produces {key!r}, which a later unit reads and this thread never recorded")
    inputs = (values.get("request") or {}).get("inputs") or {}
    for p in spec.input.parameters:  # 4 every input parameter the new version requires has a value
        if p.name not in inputs:
            out.append(f"the input parameter {p.name!r} has no value in this thread")
    return out


def changed_units(prev: Mapping[str, Any], spec: WorkflowSpec) -> list[str]:
    """The units of the previous process whose prompts, gates or limits changed since."""
    old = prev.get("units") or {}
    now = unit_digests(spec)
    return sorted(u for u, d in now.items() if u in old and old[u].get("digest") != d["digest"])
