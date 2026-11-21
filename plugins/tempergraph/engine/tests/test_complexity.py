"""Complexity switches: measures, the rules file, zones, one-way re-arm, exploration (CXR-AC-1 to AC-3, AC-5)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import (
    ComplexitySwitch,
    Gate,
    Judge,
    Map,
    Measure,
    Rearm,
    Routing,
    Step,
    Value,
    Workflow,
    stock,
)
from tempergraph.constants import ExitCode
from tempergraph.contracts import (
    CheckResult,
    FlowSpec,
    SessionRequest,
    SessionResult,
    SettingDecl,
    WorkflowSpec,
)
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import validate
from tempergraph.run import complexity
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_run import judge, registry, verdict_block

NO_SLEEP = RunSettings(sleep=lambda s: None)
FAIL = verdict_block("UNMET")
RULES = {"schema_version": 1, "arms": {"direct": {"when": {"criteria": {"max": 3}, "files": {"max": 2}}}},
         "margin": {"criteria": {"from": 4, "to": 5}}}
REARM = Rearm(from_arm="direct", to="planned", units=["do_all"], on=["budget_spent", "timeout"])
MEASURES = (Measure("criteria", stock.fact("triage", "criteria")), Measure("files", stock.fact("triage", "files")))


def sizing(ctx: Any) -> CheckResult:
    """The triage check: it verifies the counts and records them as facts (CXR §2.3)."""
    return CheckResult(result="PASS", evidence="counted", facts={k: str(v) for k, v in
                                                                 json.loads(ctx.read_text("size.json")).items()})


def raising(ctx: Any) -> int:
    raise RuntimeError("no")


def a_list(ctx: Any) -> Any:
    return [1, 2]


def wf(*, measures: Any = MEASURES, direct_makes: str = "change", triage_makes: dict[str, Any] | None = None,
       spec_fields: dict[str, Any] | None = None, **sw: Any) -> WorkflowSpec:
    def step(prompt: str, cid: str, **kw: Any) -> Any:
        gate = Gate(judge=Judge(stance="V."), criteria=[crit(cid)], **kw.pop("gate", {}))
        return Step(prompt=prompt, tools=["read", "write"], gate=gate, **kw)

    sw.setdefault("joins_at", "verify")
    units = {
        "triage": step("Triage {request}", "c1", gate={"check": sizing}, produces=triage_makes or {}),
        "size": ComplexitySwitch(arms={"direct": "do_all", "planned": "plan"}, measures=measures, **sw),
        "plan": step("Plan {request}", "c2", produces={"phases": "file"}),
        "items": Map(items_from=("plan", "phases"), step=step("Do {item}", "c3", produces={"note": Value()})),
        "join": step("Join", "c4", produces={"change": Value()}),
        "do_all": step("Do all of {request}", "c5", produces={direct_makes: Value()}, timeout_s=1800),
        "verify": step("Verify {change}", "c6"),
    }
    return named(Workflow(order=list(units), units=units, flow={"join": FlowSpec(next="verify")},
                          issue_repository="acme/x", routing=Routing(description="Do a task"),
                          **(spec_fields or {})))


def planner(req: SessionRequest) -> SessionResult:
    (req.workdir / "phases.json").write_text(json.dumps([{"id": "p1", "text": "Only phase"}]))
    return answer("Planned.\nARTIFACT phases: phases.json", session_id="plan")


def said(text: str, sid: str) -> SessionResult:
    return answer(text, session_id=sid)


SIZE: dict[str, Any] = {}


def triage(req: SessionRequest, text: str = "Triaged.") -> SessionResult:
    (req.workdir / "size.json").write_text(json.dumps(SIZE))
    return said(text, "t")


def claiming(req: SessionRequest) -> SessionResult:
    return triage(req, "Triaged.\nARTIFACT size: trivial")


TRIAGE, DONE, VERIFIED = triage, said("Did it.\nARTIFACT change: done", "d"), said("Fine.", "v")
DIRECT = [TRIAGE, DONE, VERIFIED]
PLANNED = [TRIAGE, planner, said("Item.\nARTIFACT note: ok", "i"), said("Joined.\nARTIFACT change: done", "jn"),
           VERIFIED]


def setup(repo: Path, size: dict[str, Any], rules: Any = RULES) -> None:
    SIZE.clear()
    SIZE.update(size)
    if rules is not None:
        p = complexity.override_path(state_root_path(repo), "demo", "size")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(rules if isinstance(rules, str) else json.dumps(rules))


def go(repo: Path, spec: WorkflowSpec, steps: list[Any], judges: list[Any] | None = None, task: str = "C-1",
       **kw: Any) -> Any:
    ex = standin("claude", steps=list(steps), judges=judges if judges is not None else [judge() for _ in steps])
    return start(spec, task, {"request": "x"}, repo, registry(ex), dataclasses.replace(NO_SLEEP, **kw))


def recs(repo: Path, kind: str, task: str = "C-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def entered(repo: Path, task: str = "C-1") -> list[str]:
    return [r["unit"] for r in recs(repo, "unit_entered", task)]


def test_the_fixture_is_valid() -> None:
    assert [f for f in validate(wf(rearm=[REARM]), DECLARED) if f.severity == "error"] == []


@pytest.mark.parametrize(("size", "zone", "arm"), [
    ({"criteria": 2, "files": 1}, "simple", "direct"),
    ({"criteria": 2, "files": 4}, "complex", "planned"),
    ({"criteria": 4, "files": 1}, "margin", "planned"),
    ({"files": 1}, "fault", "planned"),
])
def test_zones(repo: Path, size: dict[str, Any], zone: str, arm: str) -> None:  # CXR-B1
    setup(repo, size)
    out = go(repo, wf(), DIRECT if arm == "direct" else PLANNED)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert entered(repo) == (["triage", "do_all", "verify"] if arm == "direct" else
                             ["triage", "plan", "items", "join", "verify"])
    (r,) = recs(repo, "route")
    assert (r["unit"], r["zone"], r["arm"], r["rules_source"]) == ("size", zone, arm, "repository")
    assert r["measures"] == {"criteria": size.get("criteria", "fault"), "files": size["files"]}
    assert len(r["rules_digest"]) == 16


@pytest.mark.parametrize("rules", [None, "{not json", {"schema_version": 1, "arms": {"quick": {"when": {"x": {}}}}},
                                   {"schema_version": 1, "arms": {"direct": {"when": {"lines": {"max": 3}}}}},
                                   {"schema_version": 1, "arms": {"planned": {"when": {"files": {"max": 3}}}}}])
def test_unusable_rules_take_the_safe_arm(repo: Path, rules: Any) -> None:  # CXR §2.4 row 1, §4 row 5 at run time
    setup(repo, {"criteria": 1, "files": 1}, rules)
    out = go(repo, wf(), PLANNED)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (r,) = recs(repo, "route")
    assert (r["zone"], r["arm"]) == ("fault", "planned") and r["rules_error"]


@pytest.mark.parametrize("measure", [raising, a_list])
def test_a_faulting_measure_takes_the_safe_arm(repo: Path, measure: Any) -> None:  # CXR §2.3
    setup(repo, {"criteria": 1, "files": 1})
    out = go(repo, wf(measures=[*MEASURES, Measure("odd", measure)]), PLANNED)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (r,) = recs(repo, "route")
    assert (r["zone"], r["arm"], r["measures"]["odd"]) == ("fault", "planned", "fault")


def test_shadow_first(repo: Path) -> None:  # CXR-B2
    setup(repo, {"criteria": 2, "files": 1})
    out = go(repo, wf(mode="shadow"), PLANNED)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (r,) = recs(repo, "route")
    assert (r["arm"], r["would_choose"], r["zone"], r["shadow"]) == ("planned", "direct", "simple", True)


def test_a_step_value_is_no_measure(repo: Path) -> None:  # CXR-AC-2
    setup(repo, {"criteria": 2, "files": 4})
    spec = wf(triage_makes={"size": Value(optional=True)})
    claimed = [claiming, *PLANNED[1:]]
    for task, steps in (("C-1", claimed), ("C-2", PLANNED)):
        assert go(repo, spec, steps, task=task).exit_code is ExitCode.FINISHED
    one, two = recs(repo, "route", "C-1")[0], recs(repo, "route", "C-2")[0]
    assert (one["zone"], one["arm"], one["measures"]) == (two["zone"], two["arm"], two["measures"]) == (
        "complex", "planned", {"criteria": 2, "files": 4})


def test_a_budget_spent_on_blockers_re_arms_once(repo: Path) -> None:  # CXR-B3 rows 1 and 4, CXR-AC-5
    setup(repo, {"criteria": 2, "files": 1})
    spec = wf(rearm=[REARM])
    steps = [TRIAGE, DONE, DONE, DONE, *PLANNED[1:4], VERIFIED, VERIFIED, VERIFIED]
    judges = [judge(), judge(FAIL), judge(FAIL), judge(FAIL), judge(), judge(), judge(), judge(FAIL), judge(FAIL),
              judge(FAIL)]
    out = go(repo, spec, steps, judges, judge_state=lambda unit: "accepted")
    assert entered(repo) == ["triage", "do_all", "plan", "items", "join", "verify"]
    first, second = recs(repo, "route")
    assert (first["arm"], first["chosen_by"], first["zone"]) == ("direct", "predicate", "simple")
    assert (second["arm"], second["chosen_by"], second["rearmed_from"], second["zone"]) == (
        "planned", "rearm", "direct", "simple")
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"  # after one re-arm: the gate's policy


def test_an_untrusted_judge_does_not_re_arm(repo: Path) -> None:  # CXR-B3 row 1: an `accepted` judge
    setup(repo, {"criteria": 2, "files": 1})
    out = go(repo, wf(rearm=[REARM]), [TRIAGE, DONE, DONE, DONE], [judge(), judge(FAIL), judge(FAIL), judge(FAIL)],
             judge_state=lambda unit: "below_bar")
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    assert entered(repo) == ["triage", "do_all"]


def test_a_step_timeout_re_arms(repo: Path) -> None:  # CXR-B3 row 2
    setup(repo, {"criteria": 2, "files": 1})
    slow = SessionResult(ok=False, timed_out=True, session_id="slow")
    out = go(repo, wf(rearm=[REARM]), [TRIAGE, slow, *PLANNED[1:]], [judge() for _ in range(5)])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert entered(repo) == ["triage", "do_all", "plan", "items", "join", "verify"]


def test_a_budget_spent_on_held_causes_keeps_the_gates_policy(repo: Path) -> None:  # CXR-B3 row 3
    setup(repo, {"criteria": 2, "files": 1})
    no_artifact = said("Did it.", "d")  # an output contract miss carries no climbing evidence
    out = go(repo, wf(rearm=[REARM]), [TRIAGE, no_artifact, no_artifact, no_artifact], [judge()])
    assert out.exit_code is ExitCode.PAUSED and out.payload["kind"] == "budget"
    assert entered(repo) == ["triage", "do_all"] and [r["chosen_by"] for r in recs(repo, "route")] == ["predicate"]


def explored_task(want: bool, skip: int = 0) -> str:
    for i in range(10_000):
        task = f"E-{i}"
        draw = int(hashlib.sha256(f"demo/{task}\0size".encode()).hexdigest(), 16) % 1000
        if (draw < 200) is want:
            if skip == 0:
                return task
            skip -= 1
    raise AssertionError


def test_exploration_in_the_margin(repo: Path) -> None:  # CXR-B5, CXR §2.6
    setup(repo, {"criteria": 4, "files": 1})
    spec = wf(explore={"rate": 0.2, "per_week": 2}, spec_fields={"improvement_mode": "stable"})
    unlucky = explored_task(False)
    assert go(repo, spec, PLANNED, task=unlucky).exit_code is ExitCode.FINISHED
    assert recs(repo, "route", unlucky)[0]["zone"] == "margin"
    for n in range(2):  # one explored run this week leaves room for a second
        task = explored_task(True, n)
        assert go(repo, spec, DIRECT, task=task).exit_code is ExitCode.FINISHED
        (r,) = recs(repo, "route", task)
        assert (r["zone"], r["arm"]) == ("explore", "direct")
    assert complexity.explored_recent(state_root_path(repo), "demo", "size") == 2
    third = explored_task(True, 2)
    assert go(repo, spec, PLANNED, task=third).exit_code is ExitCode.FINISHED
    assert recs(repo, "route", third)[0]["zone"] == "margin"
    trial = explored_task(True, 3)  # a trial never explores
    assert go(repo, dataclasses.replace(spec), PLANNED, task=trial, origin="trial").exit_code is ExitCode.FINISHED
    assert recs(repo, "route", trial)[0]["zone"] == "margin"


@pytest.mark.parametrize(("stage", "origin", "recent", "want"), [
    ("local-stable", "cli", 1, True), ("pipeline", "cli", 0, False), ("local-stable", "schedule", 0, False),
    ("local-stable", "trial", 0, False), ("local-stable", "cli", 2, False), ("local-dev", "cli", 0, True),
])
def test_exploration_stays_out_of_the_pipeline(stage: str, origin: str, recent: int, want: bool) -> None:  # CXR-B5
    comp = wf(explore={"rate": 0.2, "per_week": 2}).units["size"].switch.complexity  # type: ignore[union-attr]
    assert comp is not None
    assert complexity.explores(comp, f"demo/{explored_task(True)}", "size", stage, origin, recent) is want
    assert complexity.explores(comp, f"demo/{explored_task(False)}", "size", stage, origin, recent) is False


def test_other_parameters(repo: Path) -> None:  # CXR-B6
    rules = {"schema_version": 1, "arms": {"direct": {"when": {"review_depth": {"in": ["light"]}}}}}
    setup(repo, {"criteria": 2, "files": 1}, rules)
    spec = wf(measures=[Measure("review_depth", stock.setting("review_depth"))], spec_fields={"settings": {
        "review_depth": SettingDecl(kind="choice", default="light", choices=("light", "thorough"))}})
    assert go(repo, spec, DIRECT, task="C-0").exit_code is ExitCode.FINISHED
    assert recs(repo, "route", "C-0")[0]["zone"] == "simple"
    thorough = {"settings.review_depth": "thorough"}
    assert go(repo, spec, PLANNED, flags=thorough).exit_code is ExitCode.FINISHED
    (r,) = recs(repo, "route")
    assert (r["zone"], r["arm"], r["measures"]) == ("complex", "planned", {"review_depth": "thorough"})
    out = go(repo, spec, DIRECT, task="C-2", flags={**thorough, "size.arm": "direct"})
    assert out.exit_code is ExitCode.FINISHED, out.message
    (r,) = recs(repo, "route", "C-2")
    assert (r["arm"], r["chosen_by"], r["zone"], r["would_choose"]) == ("direct", "operator", "complex", "planned")


def test_stock_measures(repo: Path, tmp_path: Path) -> None:  # CXR §2.3
    setup(repo, {"criteria": 2, "files": 1}, {"schema_version": 1, "arms": {"direct": {"when": {"phases": {"max": 0}}}}})
    measures = [Measure("phases", stock.count_items("plan", "phases")), Measure("depth", stock.input("request")),
                Measure("lines", stock.count_lines("plan", "phases", "id")), Measure("touched", stock.changed_paths())]
    units = dict(wf().units)
    order = ["triage", "plan", "size", "items", "join", "do_all", "verify"]
    units["size"] = ComplexitySwitch(arms={"direct": "do_all", "planned": "items"}, measures=measures,
                                     joins_at="verify")
    spec = dataclasses.replace(wf(), order=tuple(order), units=units)
    assert [f for f in validate(spec, DECLARED) if f.severity == "error"] == []
    out = go(repo, spec, PLANNED)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (r,) = recs(repo, "route")
    assert r["zone"] == "complex" and r["measures"]["phases"] == 1 and r["measures"]["depth"] == "x"
    assert r["measures"]["lines"] == 1 and r["measures"]["touched"] >= 1


def codes(spec: WorkflowSpec) -> set[str]:
    return {f.code for f in validate(spec, DECLARED) if f.severity == "error"}


def with_switch(spec: WorkflowSpec, **changes: Any) -> WorkflowSpec:
    sw = spec.units["size"].switch
    assert sw is not None and sw.complexity is not None
    comp = dataclasses.replace(sw.complexity, **{k: v for k, v in changes.items() if k in ("joins_at", "size")})
    sw = dataclasses.replace(sw, complexity=comp, **{k: v for k, v in changes.items() if k not in ("joins_at", "size")})
    return dataclasses.replace(spec, units={**spec.units, "size": dataclasses.replace(spec.units["size"], switch=sw)})


def package(tmp_path: Path, rules: Any) -> Path:
    (tmp_path / "routing").mkdir()
    if rules is not None:
        (tmp_path / "routing" / "size.json").write_text(json.dumps(rules))
    return tmp_path


def test_validation_codes(tmp_path: Path) -> None:  # CXR-AC-3, CXR-B4, CXR §4
    predicate = wf().units["triage"].gate.check
    assert "complexity-predicate" in codes(with_switch(wf(), predicate=predicate))
    found = [f for f in validate(wf(direct_makes="patch"), DECLARED) if f.code == "arm-contract"]  # CXR-B4
    assert len(found) == 1 and all(w in found[0].message for w in ("'direct'", "'change'", "'verify'"))
    assert "complexity-joins" in codes(with_switch(wf(), joins_at="join"))  # `direct` never reaches it
    assert "complexity-joins" in codes(with_switch(wf(), joins_at="nowhere"))
    back = Rearm(from_arm="planned", to="direct", units=["join"], on=["budget_spent"])
    assert "complexity-rearm" in codes(wf(rearm=[back]))
    assert "complexity-explore" in codes(wf(explore={"rate": 0.3, "per_week": 2}))
    assert "complexity-explore" in codes(wf(explore={"rate": 0.2, "per_week": 6}))
    assert "complexity-invalid" in codes(with_switch(wf(), size="lines"))
    assert "complexity-invalid" in codes(wf(measures=[]))
    assert "complexity-invalid" in codes(wf(measures=[Measure("n", stock.fact("nowhere", "k"))]))
    assert "complexity-invalid" in codes(with_switch(wf(), default="direct"))
    bad = {"schema_version": 1, "arms": {"direct": {"when": {"lines": {"max": 3}}}, "quick": {"when": {}}}}
    spec = dataclasses.replace(wf(), package_root=package(tmp_path, bad))
    rules = [f.message for f in validate(spec, DECLARED) if f.code == "complexity-rules"]
    assert len(rules) == 1 and "'quick'" in rules[0] and "'lines'" in rules[0]


def test_package_rules_and_a_missing_file(tmp_path: Path) -> None:  # CXR §2.1 `rules`, §2.4
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    good = dataclasses.replace(wf(), package_root=package(tmp_path / "a", RULES))
    assert codes(good) == set()
    assert complexity.load_rules(good, "size", None)["source"] == "package"
    assert "complexity-rules" in codes(dataclasses.replace(wf(), package_root=package(tmp_path / "b", None)))


def test_bounds() -> None:  # CXR §2.4
    assert complexity._holds(3, {"max": 3}) and not complexity._holds(4, {"max": 3})
    assert complexity._holds("3", {"min": 2, "max": 3}) and not complexity._holds("many", {"max": 3})
    assert complexity._holds("light", {"in": ["light"]}) and complexity._holds(2, {"in": [2, 3]})
    assert not complexity._holds("thorough", {"in": ["light"]})


def logged(root: Path, task: str, arm: str, zone: str, *, first: str = "PROCEED", rearm: bool = False,
           usd: float = 1.0, files: int = 2, code: int = 0) -> None:
    from tempergraph.run.log import RunLog

    log = RunLog(run_dir(root, "demo", task) / "run.jsonl")
    use = {"input_tokens": 1, "output_tokens": 1, "reported_cost_usd": usd, "estimated_cost_usd": usd}
    unit = "do_all" if arm == "direct" else "plan"
    log.write("run_started", workflow_version="0.1.0")
    log.write("route", unit="size", arm=arm, target=unit, chosen_by="predicate", zone=zone,
              measures={"files": files}, shadow=False, would_choose=arm)
    log.write("agent_run", unit=unit, attempt=1, executor="claude", session_kind="step", usage=use)
    log.write("gate", unit=unit, verdict=first)
    if rearm:
        log.write("route", unit="size", arm="planned", target="plan", chosen_by="rearm", zone=zone,
                  rearmed_from="direct")
    log.write("gate", unit="verify", verdict="RETRY")  # after `joins_at`: outside the yield
    log.write("outcome", verdict="met")
    log.write("run_exit", exit_code=code, reason="finished")


def test_the_switch_report(repo: Path) -> None:  # CXR-AC-4, CXR §2.7
    from tempergraph.catalog import Catalog
    from tempergraph.observe import switch_report as swr

    from .test_cli import cli

    root = state_root_path(repo)
    for i in range(6):
        logged(root, f"D-{i}", "direct", "simple", first="RETRY" if i == 0 else "PROCEED")
    for i in range(2):
        logged(root, f"P-{i}", "planned", "complex")
    for i in range(2):
        logged(root, f"R-{i}", "direct", "simple", first="RETRY", rearm=True, usd=9.0)
    logged(root, "U-0", "planned", "margin", code=3)
    (run_dir(root, "demo", "open") / "x").parent.mkdir(parents=True)  # an unfinished run has no log to count
    doc = swr.report(root, "demo", "size", None, units={"do_all", "plan", "items", "join"}, size="files")
    cells = {(c["arm"], c["zone"]): c for c in doc["cells"]}
    direct = cells[("direct", "simple")]
    assert (direct["runs"], direct["comparable"], direct["first_pass_yield"]) == (6, True, round(5 / 6, 3))
    assert direct["cost_per_completed_run_usd"] == 1.0 and direct["cost_per_size_usd"] == 0.5  # no re-armed run in
    assert direct["outcomes"] == {"met": 6}
    assert (cells[("planned", "complex")]["runs"], cells[("planned", "complex")]["comparable"]) == (2, False)
    assert cells[("planned", "margin")]["completed"] == 0
    (apart,) = doc["rearmed"]
    assert (apart["from_arm"], apart["runs"], apart["rearm_rate"]) == ("direct", 2, 0.25)
    assert doc["rearm_rate"] == {"direct": 0.25, "planned": 0.0} and doc["runs"] == 11
    cat = Catalog(specs={"demo": wf(size="files")})
    code, text, _ = cli(repo, None, "report", "all", "--switch", "demo/size", catalog=cat)
    assert code == 0 and "direct / simple: 6 runs, first pass 83%, $1.00 per completed run, $0.50 per unit" in text
    assert "planned / complex: 2 runs, too few to compare" in text and "re-armed from direct (25% of its runs)" in text
    code, doc, _ = cli(repo, None, "report", "all", "--switch", "demo/size", "--json", catalog=cat)
    assert code == 0 and doc["switch"] == "size" and doc["size"] == "files"
    assert cli(repo, None, "report", "--switch", "demo", catalog=cat)[0] != 0
    assert cli(repo, None, "report", "--switch", "demo/size")[0] != 0  # the stock catalog's demo has no such switch
