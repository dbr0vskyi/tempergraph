"""The check preview a step may run from inside its attempt (CHK §2.5).

A step that declares `self_check` gets a random ticket for one attempt. The ticket file holds the check
worker's input document, so the `self-check` verb needs no checkpoint and no catalog: it refreshes the git
facts, runs the unit's check in the check worker with `preview = true`, prints what the gate's check would
find and notes the call on the ticket. It writes no verdict, fact, artifact or state and spends no budget;
the engine writes one `self_check` record a call when the attempt ends, and removes the ticket.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import re
import secrets
import time
from pathlib import Path
from typing import IO, Any

from tempergraph.contracts import GateSpec
from tempergraph.docs import write_json
from tempergraph.run import checks as checkmod
from tempergraph.run.check_worker import context_doc, run_doc

TICKET_RE = re.compile(r"^[0-9a-f]{32}$")
DEFAULT_LIMIT = 3
EVIDENCE_CHARS = 2_000
COMMAND = "tempergraph self-check"


def ticket_path(state_root: Path, ticket: str) -> Path:
    return state_root / "tickets" / f"{ticket}.json"


def command(ticket: str) -> str:
    return f"{COMMAND} {ticket}"


def issue(state_root: Path, gate: GateSpec, ctx: checkmod.CheckContext, *, thread: str, limit: int) -> str:
    """A ticket for one attempt of one unit; `close` ends it."""
    ticket = secrets.token_hex(16)
    path = ticket_path(state_root, ticket)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(path, {"schema_version": 1, "thread": thread, "unit": ctx.unit, "item": ctx.item,
                      "attempt": ctx.attempt, "limit": int(limit), "calls": [],
                      "doc": context_doc(gate, dataclasses.replace(ctx, preview=True))})
    return ticket


def close(state_root: Path, ticket: str) -> list[dict[str, Any]]:
    """End the ticket and return its calls, for the engine's `self_check` records."""
    path = ticket_path(state_root, ticket)
    try:
        calls = list(json.loads(path.read_text(encoding="utf-8")).get("calls") or [])
    except (OSError, ValueError, AttributeError):
        calls = []
    with contextlib.suppress(OSError):
        path.unlink()
    return calls


def run(state_root: Path, ticket: str, out: IO[str]) -> int:
    """The `self-check <ticket>` verb. Exit 2 for an unknown or expired ticket and at the limit, else 0."""
    path = ticket_path(state_root, ticket) if TICKET_RE.match(ticket) else None
    try:
        t = json.loads(path.read_text(encoding="utf-8")) if path is not None else None
    except (OSError, ValueError):
        t = None
    if not isinstance(t, dict) or not isinstance(t.get("doc"), dict):
        out.write("self-check: unknown or expired ticket; nothing was run\n")
        return 2
    calls = list(t.get("calls") or [])
    if len(calls) >= int(t.get("limit") or DEFAULT_LIMIT):
        out.write(f"self-check: the limit of {t.get('limit')} previews for this attempt is reached; "
                  "the gate's own check runs when you end\n")
        return 2
    doc = t["doc"]
    c = doc["context"]
    workdir = Path(c["workdir"])
    g = checkmod.git_facts(workdir, str((c.get("git") or {}).get("base") or ""))
    c["git"] = {"branch": g.branch, "base": g.base, "head": g.head, "base_head": g.base_head, "clean": g.clean,
                "pushed": g.pushed, "changed_paths": list(g.changed_paths),
                "commits_since_base": list(g.commits_since_base)}
    c["preview"] = True
    t0 = time.monotonic()
    res, _ = run_doc(doc, workdir, int(doc.get("check_timeout_s") or 1800), f"preview-{c['unit']}-{c.get('attempt')}")
    counts = {s: sum(1 for f in res.findings if f.status == s) for s in ("pass", "fail", "maybe")}
    calls.append({"result": res.result, "findings": counts, "duration_s": round(time.monotonic() - t0, 3),
                  "environmental": bool(res.environmental)})
    if path is not None and path.exists():  # an attempt that ended meanwhile keeps its ticket closed
        write_json(path, {**t, "calls": calls})
    out.write(f"self-check {len(calls)} of {t.get('limit')}: {res.result}\n")
    for f in res.findings:
        parts = [f.status, f.criterion or "-", f.place or "-", f.message or "-"]
        out.write("  " + " | ".join(parts) + (f" | fix: {f.fix}" if f.fix else "") + "\n")
    if res.evidence:
        out.write(res.evidence[:EVIDENCE_CHARS].rstrip() + "\n")
    out.write("This is a preview. The gate's own check runs after you end.\n")
    return 0
