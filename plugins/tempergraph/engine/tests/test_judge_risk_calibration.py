"""Calibration per judge risk level: a binding, a score and a state per level, staleness of one level, stable
mode and the trust a ladder reads (JRK-AC-4, JRK-B5, JRK §2.4)."""

from __future__ import annotations

import dataclasses
import io
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Level, Risk
from tempergraph.catalog import Catalog
from tempergraph.cli.main import main
from tempergraph.contracts import RiskContext
from tempergraph.executors.registry import Registry
from tempergraph.improve import calibration as cal
from tempergraph.package.readiness import stable_findings

from .test_calibration import gold, judge_ex, spec_at


def by_src(ctx: RiskContext) -> str:
    return "code" if ctx.git.paths_by_glob(["src/**"]) else "base"


def risk(mode: str = "route", **code: Any) -> Any:
    code = code or {"model": "large"}
    return Risk(levels=[Level("base"), Level("code", **code)], rule=by_src, mode=mode)


def leveled(root: Path, mode: str = "route", **code: Any) -> Any:
    return spec_at(root, model="medium", risk=risk(mode, **code))


def test_each_level_is_a_binding_with_its_own_score_and_state(tmp_path: Path) -> None:  # JRK-AC-4
    spec = leveled(tmp_path)
    gold(spec)
    assert cal.levels(spec, "review") == ["base", "code"] and cal.levels(spec, "draft") == []
    assert cal.current_binding(spec, "review")["alias"] == "medium"
    assert cal.current_binding(spec, "review", level="code")["alias"] == "large"
    cal.score(spec, "review", judge_ex())
    assert cal.state(spec, "review").state == "accepted"
    assert cal.state(spec, "review", level="base").state == "accepted"
    assert cal.state(spec, "review", level="code").state == "unscored"
    ex = judge_ex()
    rec = cal.score(spec, "review", ex, level="code")
    assert rec["level"] == "code" and rec["binding"]["alias"] == "large"
    assert {c.request.alias for c in ex.calls} == {"large"}
    assert [(s.level, s.state) for s in cal.states(spec, every_level=True) if s.gate == "review"] == [
        (None, "accepted"), ("code", "accepted")]
    assert [s.level for s in cal.states(spec) if s.gate == "review"] == [None]


def test_a_change_to_one_level_makes_only_that_level_stale(tmp_path: Path) -> None:  # JRK-AC-4
    spec = leveled(tmp_path)
    gold(spec)
    cal.score(spec, "review", judge_ex())
    cal.score(spec, "review", judge_ex(), level="code")
    changed = leveled(tmp_path, model="large", effort="high")
    assert cal.state(changed, "review").state == "accepted"
    st = cal.state(changed, "review", level="code")
    assert st.state == "stale" and st.changed == ["sampling"]
    base_changed = spec_at(tmp_path, model="small", risk=risk())
    assert cal.state(base_changed, "review").state == "stale"
    assert cal.state(base_changed, "review", level="code").state == "accepted"


def test_an_effort_level_is_scored_at_its_effort(tmp_path: Path) -> None:
    spec = leveled(tmp_path, effort="high")
    gold(spec, bad=1, good=1)
    ex = judge_ex()
    rec = cal.score(spec, "review", ex, level="code", variants=[])
    assert rec["binding"]["alias"] == "medium" and rec["binding"]["sampling"] == {"effort": "high"}
    assert {c.request.options.effort for c in ex.calls} == {"high"}
    with pytest.raises(cal.CalibrationError, match="no risk level"):
        cal.score(spec, "review", judge_ex(), level="huge")


@pytest.mark.parametrize(("mode", "score_code", "allowed"), [("route", True, True), ("route", False, False),
                                                              ("shadow", False, True)])
def test_stable_needs_every_routed_level(tmp_path: Path, mode: str, score_code: bool, allowed: bool) -> None:  # JRK-B5
    spec = dataclasses.replace(leveled(tmp_path, mode), improvement_mode="stable")
    gold(spec)
    cal.score(spec, "review", judge_ex())
    if score_code:
        cal.score(spec, "review", judge_ex(), level="code")
    hit = [f for f in stable_findings(spec) if f.unit == "review"]
    assert (not hit) is allowed
    assert cal.has_score(spec, "review") is allowed
    if not allowed:
        assert "risk level 'code' is unscored" in hit[0].message
        assert "tempergraph evals score demo review --level code" in hit[0].message


def test_the_trust_of_an_attempt_is_its_level_s(tmp_path: Path) -> None:  # JRK §2.3, LAD §2.2
    spec = leveled(tmp_path)
    gold(spec)
    cal.score(spec, "review", judge_ex())
    name = cal.state_name_for(spec)
    assert (name("review"), name("review@base"), name("review@code")) == ("accepted", "accepted", "unscored")


def test_evals_bar_and_score_per_level(tmp_path: Path, repo: Path) -> None:  # JRK §2.4
    spec = leveled(tmp_path)
    gold(spec)
    reg = Registry()
    reg.register(judge_ex())
    cat = Catalog(specs={"demo": spec})

    def run(*argv: str) -> tuple[int, Any]:
        out = io.StringIO()
        code = main(list(argv), catalog=cat, registry=reg, cwd=repo, out=out, err=io.StringIO(), signals=({}, True))
        text = out.getvalue()
        return code, json.loads(text) if text.strip().startswith("{") else text

    code, doc = run("evals", "score", "demo", "review", "--level", "code", "--json")
    assert code == 0 and (doc["level"], doc["state"]) == ("code", "accepted")
    code, doc = run("evals", "bar", "demo", "--json")
    rows = [(g["gate"], g.get("level"), g["state"]) for g in doc["workflows"][0]["gates"] if g["gate"] == "review"]
    assert rows == [("review", None, "unscored"), ("review", "code", "accepted")]
    code, text = run("evals", "bar", "demo")
    assert "demo review level code: accepted" in text
    assert run("evals", "score", "demo", "review", "--level", "nope")[0] != 0
