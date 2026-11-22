"""Engine environments under `~/.tempergraph/engines/` (UPD-B11, UPD-B12, UPD-B13) and the first one (UPD-B18, UPD-B19 step 3).

One virtual environment per installed release, named `<engine_version>-<digest12>` by the staged engine's
source digest; `.complete` is written last, and an environment without it is never made current.
`current.json` is replaced by write-then-rename, the old value moved to `previous.json` first.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from tempergraph.docs import write_json
from tempergraph.install.launch import INSTALL_TIMEOUT_S, run
from tempergraph.release import release
from tempergraph.store.layout import now_iso

PREVIOUS_RE = re.compile(r"^[0-9][0-9A-Za-z.]*-[0-9a-f]{12}$")
SKIP = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "build", "dist"})


class InstallFailed(Exception):
    pass


def staged_engine() -> Path | None:
    """The plugin's staged engine this code runs from (UPD-B14, UPD-B6 step 1: no option names a path)."""
    root = Path(__file__).resolve().parents[3]
    return root if (root / "pyproject.toml").is_file() and (root / "src" / "tempergraph").is_dir() else None


def source_digest(engine: Path) -> str:
    """VER-B7 engine source digest: `pyproject.toml` and every file under `src/`."""
    h = hashlib.sha256()
    files = [engine / "pyproject.toml", *sorted(p for p in (engine / "src").rglob("*")
                                                if p.is_file() and not (SKIP & set(p.parts)) and p.suffix != ".pyc")]
    for p in files:
        rel = p.relative_to(engine).as_posix().encode()
        h.update(rel + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def engines_dir(home: Path) -> Path:
    return home / "engines"


def interpreter(env: Path) -> Path:
    return env / "bin" / "python"


def current(home: Path) -> dict[str, Any] | None:
    path = engines_dir(home) / "current.json"
    if not path.is_file():
        return None
    doc = _read(path)
    env = Path(str(doc.get("path") or ""))
    return doc if (env / ".complete").is_file() else None


class Builder(Protocol):
    def create(self, python: str, env: Path) -> None: ...
    def install(self, env: Path, engine: Path, extras: tuple[str, ...]) -> None: ...
    def self_check(self, env: Path) -> dict[str, Any]: ...
    def reconcile(self, env: Path, previous: str | None = None) -> dict[str, Any]: ...


class VenvBuilder:
    """The real builder: `venv`, then `pip install <staged engine>[extras]`, then the self-check module."""

    def create(self, python: str, env: Path) -> None:
        got = run([python, "-m", "venv", str(env)], timeout_s=300)
        if got.code != 0:
            raise InstallFailed(f"venv failed ({got.code})")

    def install(self, env: Path, engine: Path, extras: tuple[str, ...]) -> None:
        target = str(engine) + (f"[{','.join(extras)}]" if extras else "")
        got = run([str(interpreter(env)), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", target],
                  timeout_s=INSTALL_TIMEOUT_S)
        if got.code != 0:
            raise InstallFailed(f"pip install failed ({got.code}): {got.err.strip()[-400:]}")

    def self_check(self, env: Path) -> dict[str, Any]:
        got = run([str(interpreter(env)), "-m", "tempergraph.install.selfcheck"], timeout_s=120)
        try:
            doc = json.loads(got.out)
        except ValueError:
            doc = None
        if got.code != 0 or not isinstance(doc, dict):
            raise InstallFailed(f"self-check failed ({got.code})")
        return doc


    def reconcile(self, env: Path, previous: str | None = None) -> dict[str, Any]:
        argv = [str(interpreter(env)), "-m", "tempergraph.install.reconcile"]
        if previous and PREVIOUS_RE.match(previous):  # constants-only argv: an engine folder name of ours
            argv += ["--previous", previous, "--install"]
        got = run(argv, timeout_s=INSTALL_TIMEOUT_S)
        try:
            doc = json.loads(got.out)
        except ValueError:
            doc = None
        return doc if got.code == 0 and isinstance(doc, dict) else {"error": f"reconcile failed ({got.code})"}


@dataclass(frozen=True)
class Installed:
    env: Path
    engine_version: str
    digest: str
    check: dict[str, Any]


def install_engine(home: Path, python: str, engine: Path, builder: Builder, extras: tuple[str, ...] = (),
                   *, version: str | None = None) -> Installed:
    """UPD-B14, UPD-B6 steps 3 and 4 into a new environment folder; on failure the folder is removed and
    `current.json` is untouched."""
    version = version or str(release()["engine_version"])
    digest = source_digest(engine)
    env = engines_dir(home) / f"{version}-{digest[:12]}"
    if (env / ".complete").is_file():  # this release is already installed (a rollback kept it): use it as it is
        return Installed(env=env, engine_version=version, digest=digest, check=builder.self_check(env))
    if env.exists():
        shutil.rmtree(env)
    env.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        builder.create(python, env)
        builder.install(env, engine, extras)
        check = builder.self_check(env)
        if check.get("engine_version") != version:
            raise InstallFailed(f"self-check reports engine {check.get('engine_version')!r}, expected {version!r}")
        rel = _read(engine / "src" / "tempergraph" / "data" / "release.json") or dict(release())
        write_json(env / "release.json", rel)  # read by a later engine to choose a pin (MIG-B12, MIG-B13, MIG-B14)
        (env / ".complete").write_text(now_iso() + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(env, ignore_errors=True)
        raise
    return Installed(env=env, engine_version=version, digest=digest, check=check)


def switch(home: Path, inst: Installed, *, extras: tuple[str, ...] = (),
           release_doc: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make `inst` current. The pointer also records what the engine reads, so a rollback can be checked
    without starting it (UPD-B17)."""
    eng = engines_dir(home)
    cur = eng / "current.json"
    if cur.is_file() and _read(cur).get("path") != str(inst.env):
        write_json(eng / "previous.json", _read(cur))
    rel = release_doc or release()
    doc = {"schema_version": 1, "engine_version": inst.engine_version, "digest": inst.digest,
           "path": str(inst.env), "switched_at": now_iso(), "extras": list(extras),
           "reads_store_layouts": list(rel.get("reads_store_layouts") or [rel.get("store_layout") or 1]),
           "resumes_checkpoint_formats": list(rel.get("resumes_checkpoint_formats") or [1])}
    write_json(cur, doc)
    return doc


def newest_complete(home: Path) -> Path | None:
    eng = engines_dir(home)
    envs = [p for p in eng.iterdir() if (p / ".complete").is_file()] if eng.is_dir() else []
    return max(envs, key=lambda p: (p / ".complete").stat().st_mtime) if envs else None
