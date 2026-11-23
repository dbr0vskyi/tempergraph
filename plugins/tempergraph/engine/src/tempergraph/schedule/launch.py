"""Starting a scheduled run: the hand-off ticket and the detached `run` (TCK-B16, TCK-B17; SEC-B5, SEC-B6).

The child's argv holds only `run <workflow> --schedule <fire id> --task-id <id>`: constants and checked values. The
rendered request, the inputs, the options and the label wait in a hand-off ticket (owner-only, in the schedule's folder)
that the run reads once and removes; the fire token goes in the child's environment and nowhere else.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tempergraph import detach
from tempergraph.schedule import credentials, policies, store, token
from tempergraph.store.layout import ensure_home, home_path

Starter = Callable[..., bool]


def ticket_path(schedule_id: str, fire_id: str, home: Path | None = None) -> Path:
    return store.schedules_root(home) / schedule_id / "tickets" / f"{fire_id}.json"


def build_ticket(entry: dict[str, Any], start: dict[str, Any]) -> dict[str, Any]:
    """The request and the inputs with the fire keys rendered (SCH-B11), the options, the profiles and the label."""
    target = entry.get("target") or {}
    keys = start.get("keys") or {}
    options = entry.get("options") or {}
    return {"fire_id": start["fire_id"], "slot": start["slot"], "label": start["label"],
            "request": policies.render_fire_text(str(target.get("request") or ""), keys),
            "inputs": {k: policies.render_fire_text(str(v), keys) for k, v in (target.get("inputs") or {}).items()},
            "flags": {k: c["value"] for k, c in (options.get("flag") or {}).items()},
            "profiles": list(options.get("profiles") or [])}


def write_ticket(entry: dict[str, Any], start: dict[str, Any], home: Path | None = None) -> Path:
    path = ticket_path(str(entry["schedule_id"]), str(start["fire_id"]), home)
    ensure_home(home)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(build_ticket(entry, start), fh)
    os.replace(tmp, path)
    return path


def read_ticket(fire_id: str, home: Path | None = None, *, remove: bool = True) -> dict[str, Any] | None:
    """The ticket of a fire, validated (SEC-B6): the run removes it once read, so nothing is left behind."""
    parsed = token.parse_fire_id(fire_id)
    if parsed is None:
        return None
    path = ticket_path(parsed[0], fire_id, home)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if remove:
        path.unlink(missing_ok=True)
    if not (isinstance(doc, dict) and doc.get("fire_id") == fire_id and isinstance(doc.get("request"), str)
            and isinstance(doc.get("inputs"), dict) and isinstance(doc.get("flags"), dict)
            and isinstance(doc.get("profiles"), list) and isinstance(doc.get("label"), str)):
        return None
    return doc


def launch_run(entry: dict[str, Any], start: dict[str, Any], *, home: Path | None = None,
               starter: Starter = detach.start_run) -> bool:
    """Write the ticket, then start `run` detached in its own process group and never wait for it. False when the token
    or the ticket is missing or the start failed (the tick records the failure)."""
    home = home or home_path()
    sid, workflow, thread = str(entry["schedule_id"]), (entry.get("target") or {}).get("workflow"), start.get("thread")
    secret = token.read_token(sid, home)
    if not secret or not workflow or not thread or "/" not in str(thread):
        return False
    try:
        path = write_ticket(entry, start, home)
    except OSError:
        return False
    profile = credentials.read_profile(home)  # a fire runs in the trigger's environment: the operator's profile supplies it
    child_env = {**{k: v for k, v in profile.items() if k in credentials.CREDENTIAL_NAMES}, token.ENV_VAR: secret}
    words = ("run", str(workflow), "--schedule", str(start["fire_id"]), "--task-id", str(thread).split("/", 1)[1])
    ok = starter(words, home, env=child_env, cwd=Path(str((entry.get("target") or {}).get("repo"))))
    if not ok:
        path.unlink(missing_ok=True)
    return ok
