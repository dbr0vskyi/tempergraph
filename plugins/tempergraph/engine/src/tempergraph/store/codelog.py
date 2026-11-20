"""The engine code log (LOS §2.3): JSON lines, one file per process per day, scrubbed.

Read-only verbs log only to standard error (contract C13): they never call :func:`attach`.
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import UTC, datetime
from pathlib import Path

from tempergraph.security.scrub import scrub

_context: dict[str, object] = {}


def set_context(**kv: object) -> None:
    _context.update(kv)


class JsonLineHandler(logging.Handler):
    def __init__(self, folder: Path, worker: str | None = None) -> None:
        super().__init__()
        self.folder = folder
        self.worker = worker

    def emit(self, record: logging.LogRecord) -> None:
        try:
            day = datetime.now(UTC).strftime("%Y-%m-%d")
            path = self.folder / f"{day}-{os.getpid()}.jsonl"
            line: dict[str, object] = {
                "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "level": record.levelname,
                "logger": record.name,
                "pid": os.getpid(),
                "msg": scrub(record.getMessage()),
            }
            for k in ("thread_id", "seq"):
                if k in _context:
                    line[k] = _context[k]
            if self.worker:
                line["worker"] = self.worker
            if record.exc_info and record.exc_info[0] is not None:
                line["exc_type"] = record.exc_info[0].__name__
                line["traceback"] = scrub("".join(traceback.format_exception(*record.exc_info))[-4000:])
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, (json.dumps(line) + "\n").encode())
            finally:
                os.close(fd)
        except Exception:  # best effort, contract C2
            pass


def level() -> int:
    name = os.environ.get("TEMPERGRAPH_LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def attach(state_root: Path, worker: str | None = None) -> None:
    """Route the `tempergraph` logger to `<state root>/engine/`."""
    folder = state_root / "engine"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    logger = logging.getLogger("tempergraph")
    logger.setLevel(level())
    for h in list(logger.handlers):
        if isinstance(h, JsonLineHandler):
            logger.removeHandler(h)
    logger.addHandler(JsonLineHandler(folder, worker))
    logger.propagate = False
