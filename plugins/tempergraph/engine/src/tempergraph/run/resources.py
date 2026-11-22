"""The `resources` line of the activity journal (EVT-B17, EVT-B18, EVT-B7, EVT-B19): CPU seconds, peak resident memory and the process
count of a session's process group, from a read-only process listing with constant argv. POSIX only; a
listing that fails gives no line, never an error."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

EVERY_S = 10.0


def cpu_seconds(text: str) -> float:
    """`ps` time `[[dd-]hh:]mm:ss[.cc]` in seconds."""
    days, _, rest = text.rpartition("-")
    parts = [float(p) for p in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts[-3:]
    return (int(days) if days else 0) * 86400 + h * 3600 + m * 60 + s


def sample(pgid: int, listing: Callable[[], str] | None = None) -> dict[str, Any] | None:
    """One sample of the group: `cpu_s`, `rss_kb` (summed now) and `processes`; None when unreadable."""
    from tempergraph.executors.launcher import process_listing

    try:
        text = (listing or process_listing)()
    except OSError:
        return None
    cpu, rss, n = 0.0, 0, 0
    for line in text.splitlines():
        f = line.split()
        if len(f) != 3 or f[0] != str(pgid):
            continue
        try:
            rss += int(f[1])
            cpu += cpu_seconds(f[2])
        except ValueError:
            continue
        n += 1
    return {"cpu_s": round(cpu, 2), "rss_kb": rss, "processes": n} if n else None


class Sampler:
    """Every `EVERY_S` while the session runs, one sample into `out`; the peak resident memory is kept."""

    def __init__(self, pgid: int, out: Callable[[dict[str, Any]], None], *, every_s: float = EVERY_S,
                 listing: Callable[[], str] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.pgid, self.out, self.every_s, self.listing, self.clock = pgid, out, every_s, listing, clock
        self.peak_kb = 0
        self.done = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> Sampler:
        if os.name == "posix":
            self.thread = threading.Thread(target=self._run, name="resources", daemon=True)
            self.thread.start()
        return self

    def once(self) -> None:
        got = sample(self.pgid, self.listing)
        if got is None:
            return
        self.peak_kb = max(self.peak_kb, int(got.pop("rss_kb")))
        self.out({"ev": "resources", "t": round(self.clock(), 3), **got, "rss_peak_kb": self.peak_kb})

    def _run(self) -> None:
        while not self.done.wait(self.every_s):
            self.once()

    def stop(self) -> None:
        self.done.set()
