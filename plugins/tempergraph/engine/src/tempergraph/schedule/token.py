"""The fire token (TCK-B17; ADR-0095).

A random token is made at `schedule add`; its SHA-256 is the entry's `token_digest` and the token itself lives only in
a private file beside the entry (`schedules/<schedule_id>/token`, owner-only). The tick puts it in the child's
`TEMPERGRAPH_SCHEDULE_TOKEN` and nowhere else; the run's caller classification checks it against the digest of the entry
the fire id names. The token is on no argv, in no record and in no step session's environment.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tempergraph.schedule import store
from tempergraph.store.layout import ensure_home

ENV_VAR = "TEMPERGRAPH_SCHEDULE_TOKEN"
FIRE_ID = re.compile(r"^(?P<sid>[a-z0-9][a-z0-9-]{0,63})@(?P<when>manual-\d{8}T\d{6}Z|\d{8}T\d{4}Z)$")


def make_token() -> str:
    return secrets.token_urlsafe(32)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def matches(token: str, wanted: str | None) -> bool:
    """A constant-time compare of the token's digest with the stored one."""
    return bool(wanted) and hmac.compare_digest(digest(token), str(wanted))


def write_token(schedule_id: str, token: str, home: Path | None = None) -> Path:
    """Owner-only (0600) beside the entry; on Windows the user's profile is the only guard the platform gives."""
    ensure_home(home)
    path = store.token_path(schedule_id, home)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    os.replace(tmp, path)
    return path


def read_token(schedule_id: str, home: Path | None = None) -> str | None:
    try:
        return store.token_path(schedule_id, home).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def parse_fire_id(fire_id: str) -> tuple[str, str] | None:
    """`(schedule_id, slot as an ISO UTC instant)` of a fire id, or None when it is not one (SCH-B26)."""
    m = FIRE_ID.match(fire_id or "")
    if not m:
        return None
    when = m.group("when")
    if when.startswith("manual-"):
        at = datetime.strptime(when[len("manual-"):], "%Y%m%dT%H%M%SZ")
    else:
        at = datetime.strptime(when, "%Y%m%dT%H%MZ")
    return m.group("sid"), at.replace(tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def entry_for_fire(fire_id: str, home: Path | None = None) -> dict[str, Any] | None:
    """The entry a fire id names, or None; read-only."""
    parsed = parse_fire_id(fire_id)
    if parsed is None:
        return None
    try:
        return store.read_entry(parsed[0], home)
    except (OSError, ValueError):
        return None
