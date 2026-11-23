"""A run sets a contest's `concurrency` and `attempt_cost_cap_usd` over what the contest declares (CTS-AC6; CTS-B6, RST-B19)."""

from __future__ import annotations

from pathlib import Path

from tempergraph.constants import ExitCode
from tempergraph.settings import ConfigFiles, options_snapshot, resolve

from .test_contest_run import BySlot, contest_spec, go, recs


def declared() -> object:
    """A contest declaring `concurrency` 3 and `cost_cap_usd` 1.00."""
    return contest_spec(slots=3, concurrency=3, cost_cap_usd=1.0, then=False)


def test_the_flag_layer_resolves_both_values_over_the_declared_ones_CTS_AC6() -> None:  # CTS-AC6 (CTS-B6, RST-B19)
    sp = declared()
    options, findings = options_snapshot(sp, {"pick.concurrency": 1, "pick.attempt_cost_cap_usd": 0.4}, (), ConfigFiles())  # type: ignore[arg-type]
    assert findings == []
    res = resolve(sp, options)  # type: ignore[arg-type]
    assert (res.values["pick.concurrency"], res.values["pick.attempt_cost_cap_usd"]) == (1, 0.4)
    assert {r.key: r.layer for r in res.rows if r.key.startswith("pick.")} == {
        "pick.concurrency": "flag", "pick.attempt_cost_cap_usd": "flag"}  # both from the `flag` layer


def test_a_run_started_with_the_flags_runs_one_slot_at_a_time_and_starts_none_past_the_cap_CTS_AC6(repo: Path) -> None:  # CTS-AC6 (CTS-B6)
    ex = BySlot(step_cost=0.30, hold_s=0.05)
    out = go(repo, declared(), ex, flags={"pick.concurrency": 1, "pick.attempt_cost_cap_usd": 0.4})  # type: ignore[arg-type]
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.peak == 1  # the slots run one at a time
    assert {k for k in ex.sessions if k.startswith("step.")} == {"step.s1", "step.s2"}  # 0.60 >= 0.40: `s3` never starts
    (rec,) = recs(repo, "contest")
    assert [s["name"] for s in rec["slots"] if s.get("skipped")] == ["s3"]


def test_without_flags_the_declared_values_stand_CTS_AC6(repo: Path) -> None:  # CTS-AC6 (CTS-B6)
    ex = BySlot(step_cost=0.30, hold_s=0.15)
    out = go(repo, declared(), ex, task="C-2")  # type: ignore[arg-type]
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.peak == 3  # the declared concurrency of 3: all slots at once, and 0.90 stays under the cap of 1.00
    (rec,) = recs(repo, "contest", "C-2")
    assert not [s for s in rec["slots"] if s.get("skipped")]
