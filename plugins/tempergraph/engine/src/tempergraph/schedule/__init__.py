"""Schedules (SCH, release 3 phase R3-T5.1): rule model and slots, exact formats and the word grammar, the canonical
form and its echo, the schedule entry and fire log, and the fire-decision policies as pure functions.

Nothing in this package reads the clock on its own, starts a process or spends: a caller passes the clock, and the
tick of the next phase only calls the policies (TCK, R3-T5.2). The engine names no workflow here (ADR-0129).
"""

from __future__ import annotations

from tempergraph.schedule.model import (
    Clock,
    Needs,
    Reading,
    Rule,
    ScheduleError,
    Slot,
    When,
    next_slots,
    parse_rule,
    slots_between,
    system_clock,
)

__all__ = ["Clock", "Needs", "Reading", "Rule", "ScheduleError", "Slot", "When", "next_slots", "parse_rule",
           "slots_between", "system_clock"]
