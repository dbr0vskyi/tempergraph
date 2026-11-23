"""Loop thresholds as parameter records with provenance (IMD-B23); the loop never changes its own."""

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
    Param(name="retry_burst.min_retries", value=3, source="SIL-B12 to SIL-B16"),
    Param(name="pattern_rule.min_runs", value=3, source="SIL-B3"),
    Param(name="pattern_rule.min_distinct_requests", value=3, source="SIL-B3"),
    Param(name="pattern_rule.window_days", value=30, source="SIL-B3"),
    Param(name="friction.file_confidence", value=0.75, source="earlier runs"),
    Param(name="outcome.audit_every", value=20, source="SIL-B10"),
    Param(name="outcome.low_confidence", value=0.5, source="SIL-B10"),
    Param(name="cost.every_n_exits", value=10, source="SIL-B10"),
    Param(name="cost.window_days", value=30, source="earlier runs"),
    Param(name="cost.min_runs", value=5, source="earlier runs"),
    Param(name="cost.repeat_share", value=0.3, source="release 1 default"),
    Param(name="cost.min_monthly_usd", value=10, source="earlier runs"),
    Param(name="cost.max_lever_share", value=0.5, source="earlier runs"),
    Param(name="stable.new_version_runs", value=5, source="SIL-B10"),
    Param(name="stable.cost_percentile", value=0.9, source="SIL-B10"),
    Param(name="stable.daily_cap_usd", value=50, source="SIL-B19, SIL-B20"),
    Param(name="autonomy.min_room_usd", value=5, source="PRP-B11, release 1 default"),
    Param(name="measure.quality_drop", value=0.05, source="earlier runs"),
    Param(name="digest.repeat_min", value=3, source="SRV-B11"),
    Param(name="digest.idle_minutes", value=10, source="SRV-B11"),
    Param(name="digest.retry_overlap", value=0.8, source="SRV-B12"),
    Param(name="digest.unused_runs", value=5, source="SRV-B12"),
    Param(name="review.max_input_tokens", value=60_000, source="SRV-B17"),
    Param(name="review.max_sessions.signals", value=3, source="SRV-B21"),
    Param(name="review.run_share.dev", value=0.25, source="SRV-B21"),
    Param(name="review.run_share.stable", value=0.10, source="SRV-B21"),
    Param(name="review.run_cap_usd.dev", value=5, source="SRV-B21"),
    Param(name="review.run_cap_usd.stable", value=2, source="SRV-B21"),
    Param(name="review.probation_runs", value=5, source="SRV-B13, SRV-B14, SRV-B15"),
    Param(name="review.repeat_sessions", value=3, source="SRV-B26"),
    # FBK-B9, FBK-B14 (T12.3)
    Param(name="labels.rerun_days", value=14, source="FBK-B9"),
    Param(name="reliability.window_days", value=90, source="FBK-B11, FBK-B12"),
    Param(name="reliability.recent_days", value=30, source="FBK-B11, FBK-B12"),
    Param(name="reliability.min_labels", value=20, source="FBK-B11, FBK-B12"),
    Param(name="reliability.min_known_bad", value=5, source="FBK-B11, FBK-B12"),
    Param(name="reliability.max_false_pass", value=0.15, source="FBK-B11, FBK-B12"),
    Param(name="reliability.min_audit_agreement", value=0.8, source="FBK-B11, FBK-B12"),
    Param(name="reliability.min_audited", value=30, source="FBK-B11, FBK-B12"),
    Param(name="reliability.queue_confidence", value=0.5, source="FBK-B13"),
    Param(name="reliability.queue_sample", value=0.05, source="FBK-B13"),
    Param(name="shift.first_n", value=10, source="FBK-B14"),
    Param(name="shift.last_n", value=30, source="FBK-B14"),
    Param(name="shift.pass_points", value=20, source="FBK-B14"),
    Param(name="shift.unverifiable_points", value=15, source="FBK-B14"),
    # PRP-B12, PRP-B18, PRP-B19, PRP-B20 (T12.5, T12.6)
    Param(name="proposals.label_value", value=5, source="PRP-B12"),
    Param(name="trial.alpha", value=0.05, source="PRP-B18, PRP-B19, PRP-B20, R-031 F3"),
    Param(name="trial.min_pairs", value=8, source="PRP-B18, PRP-B19, PRP-B20"),
    Param(name="trial.noisy_floor", value=0.5, source="PRP-B18, PRP-B19, PRP-B20"),
    Param(name="trial.guard_cost", value=0.15, source="PRP-B18, PRP-B19, PRP-B20"),
    Param(name="trial.guard_outcome_cases", value=1, source="PRP-B18, PRP-B19, PRP-B20"),
    Param(name="trial.guard_check_cases", value=1, source="PRP-B18, PRP-B19, PRP-B20"),
    Param(name="trial.guard_escapes", value=1, source="PRP-B18, PRP-B19, PRP-B20"),
    Param(name="trial.cap_usd", value=200, source="PRP-B7"),
    Param(name="trial.monthly_cap_usd", value=500, source="PRP-B11, release 1 default"),
    Param(name="trial.after_release_runs", value=10, source="PRP-B9"),
)}


def value(name: str) -> float:
    return PARAMS[name].value


def max_sessions(depth: str) -> int:
    """SRV-B21: `review.max_sessions.<depth>`, the sessions a review of that depth may read in one run."""
    return int(PARAMS[f"review.max_sessions.{depth}"].value)
