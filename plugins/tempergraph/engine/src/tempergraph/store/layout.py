"""State-root and home layouts with their manifests (LOS §2.1, §2.2; WSP §2 contract C10).

Read-only callers use the ``*_path`` helpers, which create nothing (contract C13). Only
:func:`ensure_state_root` and :func:`ensure_home` create folders, owner-only.
"""

from __future__ import annotations

import os
import socket
import uuid
from datetime import UTC, datetime
from pathlib import Path

from tempergraph import git
from tempergraph.constants import ENGINE_VERSION, STORE_LAYOUT
from tempergraph.docs import read_json, write_json

STATE_DIR = ".tempergraph"


class NotInRepository(Exception):
    pass


class LayoutNewer(Exception):
    pass


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def state_root_path(start_dir: Path) -> Path:
    """`<main checkout>/.tempergraph/`, from git's common directory, whatever the start dir (WSP-AC-1)."""
    main = git.main_checkout(start_dir)
    if main is None:
        raise NotInRepository(f"{start_dir} is not inside a git repository")
    return main / STATE_DIR


def home_path() -> Path:
    return Path(os.environ.get("TEMPERGRAPH_HOME") or Path.home() / STATE_DIR)


def _manifest(kind: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": kind,
        "layout": STORE_LAYOUT,
        "engine_version": ENGINE_VERSION,
        "created_at": now_iso(),
    }


def _check_layout(manifest_path: Path) -> None:
    if manifest_path.exists():
        data = read_json(manifest_path, "store_manifest")
        layout = data.get("layout")
        if isinstance(layout, int) and layout > STORE_LAYOUT:
            raise LayoutNewer(f"{manifest_path.parent} has layout {layout}; this engine writes {STORE_LAYOUT}")


def ensure_state_root(root: Path) -> Path:
    """Create the state root (owner-only) with its manifest and its own .gitignore (LOS-B4)."""
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    manifest = root / "manifest.json"
    _check_layout(manifest)
    if not manifest.exists():
        write_json(manifest, _manifest("state_root"))
    ignore = root / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
        os.chmod(ignore, 0o600)
    for sub in ("config", "checkpoints", "locks", "runs", "engine", "scratch"):
        (root / sub).mkdir(exist_ok=True, mode=0o700)
    return root


def ensure_home(home: Path | None = None) -> Path:
    home = home or home_path()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = home / "manifest.json"
    _check_layout(manifest)
    if not manifest.exists():
        write_json(manifest, _manifest("home"))
    machine = home / "machine.json"
    if not machine.exists():
        write_json(machine, {"schema_version": 1, "machine_id": str(uuid.uuid4()),
                             "label": socket.gethostname(), "created_at": now_iso()})
    return home


def run_dir(root: Path, workflow: str, task_id: str) -> Path:
    return root / "runs" / workflow / task_id


def session_dir(root: Path, workflow: str, task_id: str, session_key: str) -> Path:
    return run_dir(root, workflow, task_id) / "sessions" / session_key


def checkpoint_path(root: Path, workflow: str) -> Path:
    return root / "checkpoints" / f"{workflow}.sqlite"


def lock_path(root: Path, workflow: str, task_id: str) -> Path:
    return root / "locks" / workflow / f"{task_id}.lock"


def session_key(unit: str, attempt: int, kind: str, item: str | None = None, n: int | None = None) -> str:
    """`<unit>[.<item>].<attempt>.<kind>[.<n>]` (EVT §2.1)."""
    parts = [unit] + ([item] if item else []) + [str(attempt), kind] + ([str(n)] if n is not None else [])
    return ".".join(parts)
