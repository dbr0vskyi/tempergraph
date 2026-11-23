"""Reservations for the sessions that run at once: the branches of a parallel block, writer branches included, the
items of a concurrent map and the slots of a contest, their step and judge sessions alike (BUD-B12 to BUD-B15).

A thread-safe ledger of what each running session holds. A branch's, an item's or a slot's cost reaches the run state only
when its superstep or its node ends, so the cost check cannot see a sibling; the ledger counts what is in flight, and
adds the real cost of sessions that ended under the same snapshot of the state, which the state a sibling read at its
start does not hold. The width a caller gives `share` is the number of branches of the block, the items of the map or the
slots of the contest that may run at once: the lower of `concurrency` and the number of items or slots.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

WAIT_S = 1.0

Write = Callable[..., object]


def share(cap_usd: float, spent_usd: float, width: int) -> tuple[float, str]:
    """The run's remaining cap divided by the number of branches, items or slots that may run at once (BUD-B12, third tier)."""
    return round((cap_usd - spent_usd) / max(width, 1), 6), "share"


def session_amount(session_cap: float | None, cap_usd: float, spent_usd: float, width: int) -> tuple[float, str]:
    """The session's own cost cap when it has one, else the share. No per-unit projection exists in the central
    run stats, so the `projection` source is never produced."""
    if session_cap is not None:
        return float(session_cap), "session_cap"
    return share(cap_usd, spent_usd, width)


class Ledger:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self.held: dict[str, float] = {}  # session key to the amount it reserved
        self.ended: dict[int, float] = {}  # snapshot id to the real cost of sessions that ended under it

    def acquire(self, key: str, *, snapshot: int, spent_usd: float, cap_usd: float,
                amount: Callable[[float], tuple[float, str]], write: Write,
                drain: Callable[[], str | None]) -> str | None:
        """Take the reservation of `key`: None when held, else the reason to drain. A reservation that would take
        spend plus reservations strictly over the cap waits for a running session to end; with none running it is
        refused (BUD-B12, BUD-B14, BUD-B15)."""
        waited = False
        with self._cond:
            while True:
                spent = round(spent_usd + self.ended.get(snapshot, 0.0), 6)
                reserved, source = amount(spent)
                in_flight = round(sum(self.held.values()), 6)
                figures = {"reserved_usd": reserved, "source": source, "spent_usd": spent,
                           "in_flight_usd": in_flight, "cap_usd": cap_usd}
                if round(spent + in_flight + reserved, 6) <= cap_usd:
                    self.held[key] = reserved
                    write("held", **figures)
                    return None
                if not self.held:
                    write("refused", **figures)
                    self._cond.notify_all()
                    return "cost_cap"
                if not waited:
                    write("waiting", **figures, waiting_for=sorted(self.held))
                    waited = True
                self._cond.wait(WAIT_S)
                reason = drain()
                if reason:
                    return reason

    def release(self, key: str, *, snapshot: int, real_usd: float) -> None:
        """A session ended: its reservation is replaced by its real cost."""
        with self._cond:
            if self.held.pop(key, None) is not None:
                self.ended[snapshot] = round(self.ended.get(snapshot, 0.0) + real_usd, 6)
            self._cond.notify_all()
