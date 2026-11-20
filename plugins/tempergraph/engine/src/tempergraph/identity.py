"""Pseudonymous join keys for the ledger (IMD-R1): the machine id and the repository digest.

The machine id is the random id of `<home>/machine.json`, never a host name. The repository digest is the
SHA-256 of the normalized `origin` remote URL (no scheme, no credentials, no `.git`, lower case), cut to 16 hex;
None when the repository has no `origin`.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from tempergraph.git import git
from tempergraph.store.layout import ensure_home, home_path


def machine_id(home: Path | None = None) -> str | None:
    try:
        h = ensure_home(home or home_path())
        doc = json.loads((h / "machine.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing id never stops a run (C2)
        return None
    return str(doc.get("machine_id")) if isinstance(doc, dict) and doc.get("machine_id") else None


def normalize_remote(url: str) -> str:
    u = url.strip()
    scheme = re.match(r"^[a-z+]+://", u)
    u = u[scheme.end():] if scheme else u
    u = re.sub(r"^[^@/]+@", "", u)  # user and token
    if not scheme:  # scp-like `host:path`
        u = u.replace(":", "/", 1)
    u = re.sub(r"\.git$", "", u.rstrip("/"))
    return u.lower()


def repo_id(main: Path | None) -> str | None:
    if main is None:
        return None
    url = git(["config", "--get", "remote.origin.url"], main, check=False).strip()
    if not url:
        return None
    return hashlib.sha256(normalize_remote(url).encode()).hexdigest()[:16]
