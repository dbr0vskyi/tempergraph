"""Loop thresholds as parameter records with provenance (IMD §2.5); the loop never changes its own."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, kw_only=True)
class Param:
    name: str
    value: float
    provenance: Literal["default_no_data", "fitted", "owner_decision"] = "default_no_data"
    source: str = ""

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "value": self.value, "provenance": self.provenance, "source": self.source}


PARAMS = {p.name: p for p in (
    Param(name="retry_burst.min_retries", value=3, source="SIL §2.4"),
    Param(name="pattern_rule.min_runs", value=3, source="SIL-B3"),
    Param(name="pattern_rule.min_distinct_requests", value=3, source="SIL-B3"),
    Param(name="pattern_rule.window_days", value=30, source="SIL-B3"),
    Param(name="friction.file_confidence", value=0.75, source="earlier runs"),
    Param(name="outcome.audit_every", value=20, source="SIL §2.2"),
    Param(name="outcome.low_confidence", value=0.5, source="SIL §2.2"),
    Param(name="cost.every_n_exits", value=10, source="SIL §2.2"),
    Param(name="cost.window_days", value=30, source="earlier runs"),
    Param(name="cost.min_runs", value=5, source="earlier runs"),
    Param(name="cost.repeat_share", value=0.3, source="release 1 default"),
    Param(name="cost.min_monthly_usd", value=10, source="earlier runs"),
    Param(name="cost.max_lever_share", value=0.5, source="earlier runs"),
    Param(name="stable.new_version_runs", value=5, source="SIL §2.2"),
    Param(name="stable.cost_percentile", value=0.9, source="SIL §2.2"),
    Param(name="stable.daily_cap_usd", value=50, source="SIL §4"),
    Param(name="measure.quality_drop", value=0.05, source="earlier runs"),
    Param(name="digest.repeat_min", value=3, source="SRV §2.1"),
    Param(name="digest.idle_minutes", value=10, source="SRV §2.1"),
    Param(name="digest.retry_overlap", value=0.8, source="SRV §2.2"),
    Param(name="digest.unused_runs", value=5, source="SRV §2.2"),
    Param(name="review.max_input_tokens", value=60_000, source="SRV §2.5"),
    Param(name="review.max_sessions.full", value=12, source="SRV §2.7"),
    Param(name="review.max_sessions.signals", value=3, source="SRV §2.7"),
    Param(name="review.run_share.dev", value=0.25, source="SRV §2.7"),
    Param(name="review.run_share.stable", value=0.10, source="SRV §2.7"),
    Param(name="review.run_cap_usd.dev", value=5, source="SRV §2.7"),
    Param(name="review.run_cap_usd.stable", value=2, source="SRV §2.7"),
    Param(name="review.probation_runs", value=5, source="SRV §2.3"),
)}


def value(name: str) -> float:
    return PARAMS[name].value
