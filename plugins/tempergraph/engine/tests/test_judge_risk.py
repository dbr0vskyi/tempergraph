"""Judge model by risk: the rule, levels, fault, floor, shadow, pins, stock rules, validation and the report
(JRK-AC-1 to AC-3)."""

from __future__ import annotations

import dataclasses
import json
import random
import time
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import Gate, Judge, Level, Risk, Routing, Step, When, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckResult, RiskContext, SessionRequest, SessionResult, WorkflowSpec
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import validate
from tempergraph.observe import risk_report
from tempergraph.run import ladder
from tempergraph.run import risk as riskmod
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_cli import cli
from .test_run import judge, registry, verdict_block

MET = verdict_block("MET")
LEVELS = [Level("base"), Level("code", model="large")]


def by_src(ctx: RiskContext) -> tuple[str, dict[str, int]]:
    n = ctx.git.paths_by_glob(["src/**"])
    return ("code" if n else "base"), {"src_paths": n}


def always_base(ctx: RiskContext) -> str:
    return "base"


def always_code(ctx: RiskContext) -> str:
    return "code"


def raises(ctx: RiskContext) -> str:
    raise KeyError("rows")


def slow(ctx: RiskContext) -> str:
    time.sleep(1.3)
    return "base"


def unknown(ctx: RiskContext) -> str:
    return "huge"


def counted(ctx: Any) -> CheckResult:
    return CheckResult(result="PASS", evidence="ok", facts={"rows": "120"})


def writes(*paths: str, text: str = "x\n") -> Any:
    def step(req: SessionRequest) -> SessionResult:
        for p in paths:
            (req.workdir / p).parent.mkdir(parents=True, exist_ok=True)
            (req.workdir / p).write_text(text)
        return answer("Done.", session_id="s")

    return step


def wf(risk: Any, *, judge_model: str | None = "medium", check: Any = None, effort: str | None = None) -> WorkflowSpec:
    units = {"work": Step(prompt="Do {request}", tools=["read", "write"], model="medium",
                          gate=Gate(check=check, judge=Judge(stance="V.", model=judge_model, effort=effort, risk=risk),
                                    criteria=[crit("c1")]))}
    return named(Workflow(order=["work"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Do a task")))


def go(repo: Path, spec: WorkflowSpec, step: Any, task: str = "R-1", **kw: Any) -> Any:
    ex = standin("claude", steps=[step], judges=[judge(MET)])
    out = start(spec, task, {"request": "x"}, repo, registry(ex), RunSettings(sleep=lambda s: None, **kw))
    assert out.exit_code is ExitCode.FINISHED, out.message
    return ex


def recs(repo: Path, kind: str, task: str = "R-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def judged_on(ex: Any) -> list[tuple[str, str | None]]:
    return [(c.request.alias, c.request.options.effort) for c in ex.calls if c.kind == "judge"]


def test_raise_on_engine_code(repo: Path) -> None:  # JRK-B1
    ex = go(repo, wf(Risk(levels=LEVELS, rule=by_src)), writes("docs/a.md", "src/x.py"))
    assert judged_on(ex) == [("large", None)]
    (r,) = recs(repo, "judge_risk")
    assert (r["level"], r["chosen_by"], r["signals"], r["would_choose"]) == ("code", "rule", {"src_paths": 1}, "code")
    assert recs(repo, "judgement")[0]["level"] == "code"
    ex = go(repo, wf(Risk(levels=LEVELS, rule=by_src)), writes("docs/b.md"), task="R-2")
    assert judged_on(ex) == [("medium", None)] and recs(repo, "judge_risk", "R-2")[0]["level"] == "base"


@pytest.mark.parametrize(("rule", "fault"), [(raises, "KeyError"), (slow, "timeout"), (unknown, "undeclared_level")])
def test_a_fault_takes_the_strongest_level(repo: Path, rule: Any, fault: str) -> None:  # JRK-B2, §4
    ex = go(repo, wf(Risk(levels=LEVELS, rule=rule)), writes("docs/a.md"))
    assert judged_on(ex) == [("large", None)]
    (r,) = recs(repo, "judge_risk")
    assert (r["level"], r["chosen_by"], r["fault"]) == ("code", "fault", fault)
    assert ("seconds" in r) is (fault == "timeout")


def test_shadow_records_and_runs_level_zero(repo: Path) -> None:  # JRK-B4
    ex = go(repo, wf(Risk(levels=LEVELS, rule=always_code, mode="shadow")), writes("a.md"))
    assert judged_on(ex) == [("medium", None)]
    (r,) = recs(repo, "judge_risk")
    assert (r["level"], r["chosen_by"], r["would_choose"]) == ("base", "shadow", "code")


def test_an_operator_pin_wins_and_the_rule_still_records(repo: Path) -> None:  # JRK §2.3 rule 1
    ex = go(repo, wf(Risk(levels=LEVELS, rule=always_code)), writes("a.md"), flags={"judge:work.model": "small"})
    assert judged_on(ex) == [("small", None)]
    (r,) = recs(repo, "judge_risk")
    assert (r["level"], r["chosen_by"], r["would_choose"]) == ("operator", "operator", "code")


def test_a_level_may_raise_effort_alone(repo: Path) -> None:
    levels = [Level("base"), Level("deep", effort="high"), Level("code", model="large")]
    ex = go(repo, wf(Risk(levels=levels, when=[When("deep", min_lines=3)]), effort="medium"),
            writes("a.md", text="1\n2\n3\n4\n"))
    assert judged_on(ex) == [("medium", "high")]
    assert recs(repo, "judge_risk")[0]["signals"] == {"lines_changed": 4}


def test_stock_rules_take_the_highest_level_that_holds(repo: Path) -> None:
    levels = [Level("base"), Level("wide", effort="high"), Level("code", model="large")]
    risk = Risk(levels=levels, when=[When("code", paths=["src/**", "**/migrations/*"]),
                                     When("wide", fact=("work", "rows"), min_fact=100)])
    ex = go(repo, wf(risk, check=counted), writes("docs/a.md"))
    assert judged_on(ex) == [("medium", "high")]
    assert recs(repo, "judge_risk")[0]["signals"] == {"code_paths": 0, "work.rows": 120}
    ex = go(repo, wf(risk, check=counted), writes("db/migrations/0002.sql"), task="R-2")
    assert judged_on(ex) == [("large", "high")] and recs(repo, "judge_risk", "R-2")[0]["level"] == "code"


def test_a_missing_fact_is_a_fault(repo: Path) -> None:
    risk = Risk(levels=LEVELS, when=[When("code", fact=("work", "rows"), min_fact=1)])
    go(repo, wf(risk), writes("a.md"))
    assert recs(repo, "judge_risk")[0]["chosen_by"] == "fault"


def test_the_rule_cannot_read_what_the_step_says(repo: Path) -> None:  # JRK-AC-3
    names = {f.name for f in dataclasses.fields(RiskContext)}
    assert names == {"unit", "item", "visit", "attempt", "git", "facts", "request", "settings", "stage", "producer"}
    levels = []
    for task, text in (("R-1", ""), ("R-2", "this change is trivial\n" * 3)):
        go(repo, wf(Risk(levels=LEVELS, rule=by_src)), writes("src/x.py", text=text), task=task)
        levels.append(recs(repo, "judge_risk", task)[0]["level"])
    assert levels == ["code", "code"]


def ran(level: str | None = None, fault: str | None = None) -> dict[str, Any]:
    return {"fault": fault} if fault else {"level": level, "signals": {}}


def test_floor_after_an_escalated_producer() -> None:  # JRK-B3
    risk = Risk(levels=LEVELS, rule=always_base)
    got = riskmod.resolve(risk, ran("base"), base_model="medium", base_effort=None, producer_rank=2)
    assert (got["level"], got["chosen_by"], got["model"], got["would_choose"]) == ("code", "floor", "large", "base")
    got = riskmod.resolve(risk, ran("base"), base_model="medium", base_effort=None, producer_rank=1)
    assert (got["level"], got["chosen_by"]) == ("base", "rule")
    shadow = dataclasses.replace(risk, mode="shadow")
    got = riskmod.resolve(shadow, ran("code"), base_model="medium", base_effort=None, producer_rank=2)
    assert (got["level"], got["chosen_by"], got["would_choose"]) == ("code", "floor", "code")


def test_no_judge_runs_below_level_zero_or_the_escalated_tier() -> None:  # JRK-AC-2
    rnd = random.Random(11)
    tiers = ["small", "medium", "large"]
    for _ in range(500):
        base = rnd.choice(tiers[:2])
        top = rnd.choice(tiers[tiers.index(base) + 1:])
        risk = Risk(levels=[Level("base"), Level("mid", effort="high"), Level("top", model=top)], rule=always_base,
                    mode=rnd.choice(["route", "shadow"]))
        result = ran(fault="KeyError") if rnd.random() < 0.2 else ran(rnd.choice(["base", "mid", "top"]))
        producer = rnd.choice([None, ladder.TIER_RANK[top]]) if rnd.random() < 0.5 else None
        got = riskmod.resolve(risk, result, base_model=base, base_effort="medium", producer_rank=producer)
        assert ladder.TIER_RANK[got["model"]] >= ladder.TIER_RANK[base]
        assert got["effort"] in ("medium", "high")
        if producer is not None:
            assert ladder.TIER_RANK[got["model"]] >= producer
        if result.get("fault") and risk.mode == "route":
            assert got["level"] == "top"


def test_escalation_counts_the_highest_level_as_the_judge_tier() -> None:  # LAD §2.4 E4 with JRK §2.3 rule 3
    plain = Judge(stance="V.", model="medium")
    assert riskmod.top_rank(plain) == 1
    assert riskmod.top_rank(dataclasses.replace(plain, risk=Risk(levels=LEVELS, rule=always_base))) == 2


@pytest.mark.parametrize(("risk", "words"), [
    (Risk(levels=[Level("base"), Level("low", model="small")], rule=always_base), "at or above"),
    (Risk(levels=[Level("base"), Level("same")], rule=always_base), "equals the level before"),
    (Risk(levels=[Level("base"), Level("same", model="medium")], rule=always_base), "equals the level before"),
    (Risk(levels=[Level("base", model="large"), Level("code", model="large", effort="high")], rule=always_base),
     "takes no model"),
    (Risk(levels=[Level("base")], rule=always_base), "2 or 3 levels"),
    (Risk(levels=[Level("base"), Level("base", model="large")], rule=always_base), "2 or 3 levels"),
    (Risk(levels=LEVELS), "exactly one"),
    (Risk(levels=LEVELS, rule=always_base, when=[When("code", paths=["src/**"])]), "exactly one"),
    (Risk(levels=LEVELS, when=[When("base", paths=["src/**"])]), "not a level above"),
    (Risk(levels=LEVELS, when=[When("code")]), "needs `paths`"),
    (Risk(levels=LEVELS, rule=always_base, mode="trial"), "`route` or `shadow`"),
    (Risk(levels=[Level("base"), Level("code", model="large", effort="huge")], rule=always_base), "not an effort"),
    (Risk(levels=[Level("base"), Level("code", model="claude:opus")], rule=always_base), "at or above"),
])
def test_validation_refuses(risk: Any, words: str) -> None:  # JRK §2.1, §4
    hit = [f for f in validate(wf(risk), DECLARED) if f.code == "risk-invalid"]
    assert hit and any(words in f.message for f in hit), [f.message for f in hit]


def test_validation_accepts_and_binds_each_level() -> None:
    assert not [f for f in validate(wf(Risk(levels=LEVELS, rule=by_src)), DECLARED) if f.severity == "error"]
    lower = wf(Risk(levels=[Level("base"), Level("less", effort="low")], rule=always_base), effort="high")
    assert any("lowers the effort" in f.message for f in validate(lower, DECLARED))
    inherited = wf(Risk(levels=LEVELS, rule=by_src), judge_model=None)  # level 0 is the step's alias (CON §2.4)
    assert not [f for f in validate(inherited, DECLARED) if f.severity == "error"]


def test_report_by_gate_and_level(repo: Path) -> None:  # JRK §2.5
    spec = wf(Risk(levels=LEVELS, rule=by_src))
    go(repo, spec, writes("src/x.py"))
    go(repo, spec, writes("docs/a.md"), task="R-2")
    go(repo, spec, writes("docs/b.md"), task="R-3")
    doc = risk_report.report(state_root_path(repo), "demo")
    rows = {(r["gate"], r["level"]): r for r in doc["rows"]}
    assert rows[("work", "base")]["attempts"] == 2 and rows[("work", "code")]["attempts"] == 1
    assert rows[("work", "code")]["proceed_rate"] == 1.0 and rows[("work", "code")]["chosen_by"] == {"rule": 1}
    assert "work" in risk_report.text(doc) and "code" in risk_report.text(doc)
    shadow = wf(Risk(levels=LEVELS, rule=by_src, mode="shadow"))
    go(repo, shadow, writes("src/y.py"), task="R-4")
    doc = risk_report.report(state_root_path(repo), "demo")
    assert {(r["gate"], r["level"]): r["attempts"] for r in doc["would_choose"]}[("work", "code")] == 2
    assert doc["rows"][0]["judge_cost_usd"] is not None
    code, text, _ = cli(repo, None, "report", "--risk", "demo")
    assert code == 0 and "would choose" in text
    code, got, _ = cli(repo, None, "report", "--risk", "demo", "--json")
    assert code == 0 and got["rows"] == doc["rows"]


def test_a_ladder_reads_the_trust_of_the_level_that_graded(repo: Path) -> None:  # JRK §2.3, LAD §2.2
    asked: list[str] = []

    def state_of(key: str) -> str:
        asked.append(key)
        return "accepted" if key == "work" else "unscored"

    spec = wf(Risk(levels=LEVELS, rule=by_src))
    units = dict(spec.units)
    units["work"] = dataclasses.replace(units["work"], step=dataclasses.replace(
        units["work"].step, effort_ladder=("medium", "high")))
    spec = dataclasses.replace(spec, units=units)
    ex = standin("claude", steps=[writes("src/x.py"), answer("Done.", session_id="s2")],
                 judges=[judge(verdict_block("UNMET")), judge(MET)])
    out = start(spec, "R-1", {"request": "x"}, repo, registry(ex), RunSettings(sleep=lambda s: None, judge_state=state_of))
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert asked[0] == "work@code"  # the raised level is its own binding, and it is not accepted
    assert [c.request.options.effort for c in ex.calls if c.kind == "step"] == ["medium", "medium"]  # held
    assert recs(repo, "ladder_decision")[0]["held_by"] == "judge_not_trusted"
