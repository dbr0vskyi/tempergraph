"""The history rules of C1, C2 and C3 (ARC-B9, ARC-B10, ARC-B11): each is raised by a fixture of synthetic run records
and quiet on a clean one (AUD-AC1, ARC-AC1), carries the catalog's severity, confidence, cause, remedy and minimum
sample, and is skipped with `n=<runs> of <min>` below it (AUD-AC3). Hot spots and the summary's highest-weight cause
come from history (AUD-B3, ARC-AC5)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tempergraph.audit import catalog as cat

from .test_audit import clean_step, wf
from .test_audit_history import audit_history, many, read, write_run

Build = Callable[[Path, int], None]


def each(root: Path, n: int, make: Callable[[int], dict[str, Any]]) -> None:
    for i in range(n):
        write_run(root, f"t{i:03d}", **make(i))


def uniform(**kw: Any) -> Build:
    return lambda root, n: many(root, n, **kw)


RETRY_C3 = [{"verdict": "RETRY", "blockers": ["c3"], "cost": 2.0}, {"cost": 2.0}]
SAME_FAIL = {"verdict": "RETRY", "check": {"result": "FAIL", "evidence": "boom"}}


def _infra(root: Path, n: int) -> None:
    each(root, n, lambda i: {"attempts": [{"infra_cause": "spawn_failed", "ok": False} if i % 2 == 0 else {}]})


# rule id -> (raising fixture, clean fixture); each builds `n` runs
CASES: dict[str, tuple[Build, Build]] = {
    "loop-driver-criterion": (uniform(attempts=RETRY_C3), uniform(attempts=[{}])),
    "low-first-pass": (uniform(attempts=[{"verdict": "RETRY", "blockers": ["c1"]}, {}]), uniform(attempts=[{}])),
    "no-change-retried": (
        uniform(attempts=[{"verdict": "RETRY", "blockers": ["c1"], "no_change": ["c1"]}, {}]),
        uniform(attempts=[{"verdict": "RETRY", "blockers": ["c1"]}, {}])),
    "repeated-check-evidence": (
        uniform(attempts=[SAME_FAIL, SAME_FAIL, {}]),
        uniform(attempts=[SAME_FAIL, {"verdict": "RETRY", "check": {"result": "FAIL", "evidence": "other"}}, {}])),
    "missing-field-rendered": (uniform(attempts=[{"missing": "request"}]), uniform(attempts=[{}])),
    "fallback-rate": (uniform(attempts=[{"verdict": "FALLBACK"}]), uniform(attempts=[{}])),
    "check-ran-nothing": (
        uniform(attempts=[{"check": {"result": "FAIL", "evidence": "every declared command not run"}}]),
        uniform(attempts=[{"check": {"result": "PASS", "evidence": "2 passed"}}])),
    "infra-heavy": (_infra, uniform(attempts=[{}])),
    "timeout-below-pass-p90": (uniform(attempts=[{"duration_s": 540, "timeout_s": 600}]),
                               uniform(attempts=[{"duration_s": 300, "timeout_s": 600}])),
    "attempts-at-limit": (uniform(attempts=[{"timed_out": True, "ok": False, "duration_s": 600}]),
                          uniform(attempts=[{}])),
    "limit-far-above-p90": (uniform(attempts=[{"duration_s": 100, "timeout_s": 3600}]),
                            uniform(attempts=[{"duration_s": 500, "timeout_s": 600}])),
    "request-timed-out": (uniform(attempts=[{"infra_cause": "request_timed_out", "ok": False,
                                             "output_tokens": 30_000}]), uniform(attempts=[{}])),
}


def found(tmp: Path, rule: str, n: int, build: Build) -> tuple[Any, list[Any]]:
    build(tmp, n)
    rep = audit_history(wf({"draft": clean_step()}), read(tmp), tmp)
    return rep, [f for f in rep.findings if f.rule == rule]


def sample(rule_id: str) -> int:
    return cat.BY_ID[rule_id].min_n or 1


def test_every_c1_c2_c3_history_rule_has_a_fixture() -> None:
    """AUD-AC1: no history rule of these families is left without a raising fixture."""
    wanted = {r.id for r in cat.RULES if r.layer == "history" and r.family in ("C1", "C2", "C3") and r.owner == "audit"
              and r.built == 3 and r.id not in ("council-rounds-no-gain", "council-conformity")}
    assert wanted == set(CASES)


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_a_fixture_raises_the_rule_with_the_catalog_record(tmp_path: Path, rule_id: str) -> None:
    """AUD-AC1, ARC-AC1: the raising fixture fires the rule with the catalog's severity, confidence, cause, remedy."""
    r = cat.BY_ID[rule_id]
    _, fs = found(tmp_path, rule_id, sample(rule_id), CASES[rule_id][0])
    assert fs, rule_id
    f = fs[0]
    assert (f.layer, f.severity, f.confidence, f.cause, f.remedy) == ("history", r.severity, r.confidence, r.cause,
                                                                      r.remedy)
    assert f.unit == "draft" and f.evidence["window_days"] == 30 and f.evidence["n"] == sample(rule_id)


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_a_clean_fixture_does_not_raise_the_rule(tmp_path: Path, rule_id: str) -> None:
    """AUD-AC1: the clean fixture is quiet, and the rule is not skipped either: it ran."""
    rep, fs = found(tmp_path, rule_id, max(sample(rule_id), 5), CASES[rule_id][1])
    assert fs == []
    assert rule_id not in {s["rule"] for s in rep.rules_skipped}


@pytest.mark.parametrize("rule_id", sorted(r for r in CASES if sample(r) > 1))
def test_below_min_n_a_rule_is_skipped_with_its_n(tmp_path: Path, rule_id: str) -> None:
    """AUD-AC3 (AUD-B5, ARC-B7): `min_n - 1` runs of the raising fixture give no finding and `n=<runs> of <min>`."""
    n = sample(rule_id) - 1
    rep, fs = found(tmp_path, rule_id, n, CASES[rule_id][0])
    assert fs == []
    skipped = next(s for s in rep.rules_skipped if s["rule"] == rule_id)
    assert skipped["reason"] == f"n={n} of {sample(rule_id)}" and skipped["min_n"] == sample(rule_id)


def test_loop_driver_names_the_criterion(tmp_path: Path) -> None:
    """ARC-B9: 6 RETRYs of which 4 lead with `C3` and repeats at 25% of spend: the rule names `C3`."""
    leads = [["C3"], ["C3"], ["C3"], ["C3"], ["C1"], ["C2"]]
    each(tmp_path, 6, lambda i: {"attempts": [{"verdict": "RETRY", "blockers": leads[i], "cost": 3.0}, {"cost": 3.0}]})
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    (f,) = [f for f in rep.findings if f.rule == "loop-driver-criterion"]
    assert f.item == "C3" and f.evidence["criterion"] == "C3"
    assert (f.evidence["retries"], f.evidence["led"]) == (6, 4)


def test_loop_driver_needs_the_share_of_spend(tmp_path: Path) -> None:
    """ARC-B9: a leading criterion with repeats under 20% of spend does not fire."""
    each(tmp_path, 10, lambda i: {"attempts": [{"verdict": "RETRY", "blockers": ["c3"], "cost": 1.0},
                                               {"kind": "retry", "cost": 0.1}],
                                  "other_units": {"plan": [{"cost": 30.0}]}})
    rep = audit_history(wf({"draft": clean_step(), "plan": clean_step()}), read(tmp_path), tmp_path)
    assert not [f for f in rep.findings if f.rule == "loop-driver-criterion"]


def test_timeout_fit_recommends_one_and_a_half_times_the_p90(tmp_path: Path) -> None:
    """ARC-AC5 (ARC-B3): a 600 s limit and a 540 s p90 of passing attempts fires and recommends about 810 s."""
    each(tmp_path, 8, lambda i: {"attempts": [{"duration_s": 540.0, "timeout_s": 600}]})
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    (f,) = [f for f in rep.findings if f.rule == "timeout-below-pass-p90"]
    assert (f.evidence["limit_s"], f.evidence["p90_s"], f.evidence["recommended_s"]) == (600, 540, 810)


def test_attempts_at_limit_splits_by_shape(tmp_path: Path) -> None:
    """ARC-B11: timeouts are split by tool share (slow host), one long call (hung) and model silent."""
    shapes = ["slow_host", "slow_host", "hung", "model_silent", "model_silent", "model_silent"]
    each(tmp_path, 6, lambda i: {"attempts": [{"timed_out": True, "ok": False, "end_shape": shapes[i]}]})
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    (f,) = [f for f in rep.findings if f.rule == "attempts-at-limit"]
    assert f.evidence["shapes"] == {"slow_host": 2, "hung": 1, "model_silent": 3}


def test_hot_spots_and_the_summary_come_from_history(tmp_path: Path) -> None:
    """AUD-B3, ARC-AC5: 12 runs where `expand` repeats and its leading criterion is `reading-sets` in 9 of 11
    RETRY verdicts, while `plan` repeats rarely: the first finding is `loop-driver-criterion` on `expand`, `plan`
    raises none, hot spots are listed per unit and the summary names `expand`."""
    def make(i: int) -> dict[str, Any]:
        calls = [{"name": "Read"}, {"name": "Write"}]  # the tools both steps declare are used
        expand: list[dict[str, Any]] = [{"cost": 2.0, "duration_s": 300, "calls": calls}]
        if i < 11:
            lead = "reading-sets" if i < 9 else "other"
            expand = [{"verdict": "RETRY", "blockers": [lead], "cost": 2.0, "duration_s": 300, "calls": calls},
                      {"cost": 2.0, "duration_s": 300, "calls": calls}]
        return {"unit": "expand", "attempts": expand,
                "other_units": {"plan": [{"cost": 3.0, "duration_s": 300, "calls": calls}]}}

    each(tmp_path, 12, make)
    rep = audit_history(wf({"expand": clean_step(), "plan": clean_step()}), read(tmp_path), tmp_path)
    first = next(f for f in rep.findings if f.layer == "history")
    assert rep.summary()["highest_weight_cause"].startswith("loop-driver-criterion on expand")
    assert (first.rule, first.unit, first.severity, first.confidence) == ("loop-driver-criterion", "expand", "error",
                                                                          "high")
    assert first.evidence["criterion"] == "reading-sets" and (first.evidence["led"], first.evidence["retries"]) == (9, 11)
    assert not [f for f in rep.findings if f.unit == "plan" and f.layer == "history"]
    spots = {h["unit"]: h for h in rep.hot_spots}
    assert set(spots) == {"expand", "plan"}
    assert spots["expand"]["leading_rule"] == "loop-driver-criterion" and spots["plan"]["findings"] == 0
    assert spots["expand"]["repeat_share"] > spots["plan"]["repeat_share"] == 0
    assert spots["expand"]["first_pass_yield"] < spots["plan"]["first_pass_yield"] == 1.0
    assert rep.summary()["highest_weight_cause"].startswith("loop-driver-criterion on expand")
    assert "hot spot expand" in rep.to_text()


def test_a_history_finding_names_its_evidence_and_the_window(tmp_path: Path) -> None:
    """AUD-B3: a history finding carries its unit, the counts and the window."""
    _, fs = found(tmp_path, "low-first-pass", 6, CASES["low-first-pass"][0])
    ev = fs[0].evidence
    assert fs[0].unit == "draft" and ev["visits"] == 6 and ev["first_pass"] == 0 and ev["window_days"] == 30
