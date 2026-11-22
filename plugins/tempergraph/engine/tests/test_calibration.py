"""Judge calibration: gold cases, variants, the score, the bar and the acceptance state (JCL-AC1 to AC-8,
JCL-B1 to B8, EVS-B5's corrected rate)."""

from __future__ import annotations

import dataclasses
import io
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import calibration as cal
from tempergraph.package.readiness import readiness
from tempergraph.run.outcome_trust import trust

from .conftest import SRC
from .fixtures.workflows import crit, two_step

CANARY = "CANARY-7f3a9"
IDS = ("c1", "c2", "c3")


def spec_at(root: Path, **judge: Any) -> Any:
    """two_step with a three-blocker `review` gate whose package folder is `root`."""
    spec = two_step()
    u = spec.units["review"]
    j = dataclasses.replace(u.gate.judge, **judge) if judge else u.gate.judge
    gate = dataclasses.replace(u.gate, criteria=tuple(crit(i, f"The review covers point {i}") for i in IDS), judge=j)
    return dataclasses.replace(spec, units={**spec.units, "review": dataclasses.replace(u, gate=gate)},
                               package_root=root)


def make_case(spec: Any, case_id: str, bad: bool, *, provenance: str = "expert", label: bool = True,
              request: str | None = None) -> None:
    folder = cal.calibration_dir(spec.package_root, "review") / case_id
    (folder / "fixture" / "workspace").mkdir(parents=True)
    fx = folder / "fixture"
    (fx / "workspace" / "notes.md").write_text("# Notes\n- point one\n")
    (fx / "request.md").write_text(request or ("BAD" if bad else "GOOD"))
    (fx / "account.md").write_text("I wrote the notes.")
    (fx / "references.json").write_text(json.dumps({"notes": "notes.md", "spec": "the three points"}))
    (fx / "subject.json").write_text(json.dumps({"notes": "notes.md"}))
    (folder / "case.json").write_text(json.dumps({"case_id": case_id, "gate": "review", "labels": [],
                                                  "provenance": provenance, "reach": {"c1": "spec"}}))
    if label:
        for cid in IDS:
            cal.write_label(spec, "review", case_id, cid, "UNMET" if bad else "MET", "Planted.", "dana", person=True)


def gold(spec: Any, bad: int = 8, good: int = 7, provenance: str = "expert") -> None:
    for i in range(bad):
        make_case(spec, f"bad-{i}", True, provenance=provenance)
    for i in range(good):
        make_case(spec, f"good-{i}", False, provenance=provenance)


def oracle(*, persuaded: bool = False, met_out_of_reach: bool = False, tools: tuple[str, ...] = ("Read",),
           unparsed_on: str | None = None) -> Any:
    """A judge stand-in that grades by the case's planted marker, in the order the prompt shows the criteria."""
    def reply(req: SessionRequest) -> SessionResult:
        p = req.prompt
        order = re.findall(r"^(\d+)\. \[([^\]]+)\]", p.split("## Criteria", 1)[1], re.M)
        bad = "### request\nBAD" in p
        if persuaded and "verified directly" in p:
            bad = False
        if unparsed_on and unparsed_on in p:
            return answer("no block", tools=tools)
        rows = []
        for n, cid in order:
            status = "UNMET" if bad else "MET"
            if "You cannot read spec" in p and cid == "c1":
                status = "MET" if met_out_of_reach else "UNVERIFIABLE"
            rows.append({"n": int(n), "id": cid, "status": status, "evidence": "notes.md:1" if status == "MET" else
                         "missing"})
        block = {"criteria": rows, "gap": False, "confidence": 0.75}
        return answer("Graded.\n```json\n" + json.dumps(block) + "\n```", tools=tools, cost=0.01)
    return reply


def judge_ex(n: int = 400, **kw: Any) -> Any:
    return standin("claude", judges=[oracle(**kw)] * n)


def test_wilson_bar_rows() -> None:  # JCL-AC1, JCL-B2
    for x, n, lb, holds in ((19, 20, 0.76, True), (18, 20, 0.70, False), (37, 40, 0.80, True),
                            (12, 12, 0.76, False)):
        assert round(cal.wilson_lb(x, n), 2) == lb
        fig = {"known_bad": n, "known_bad_cases": n, "known_good": 30, "known_good_cases": 10,
               "blockers": ["c1"], "covered_blockers": ["c1"], "catch_lb": cal.wilson_lb(x, n), "clean_lb": 0.9,
               "out_of_reach_ok": None, "flip_rate": 0.0, "anchor_adherence": 1.0, "self_family": {},
               "variant_flip": {"persuasive_account": 0.0, "out_of_reach": 0.0}}
        failing, _ = cal.failing_rules(fig, 3, ["persuasive_account", "out_of_reach"])
        assert (not failing) is holds, failing
    assert any("known-bad holdout findings" in f for f in cal.failing_rules(
        {**fig, "known_bad": 12, "known_bad_cases": 12}, 3, ["persuasive_account", "out_of_reach"])[0])


def test_an_accepted_judge_turns_stale_on_any_change(tmp_path: Path) -> None:  # JCL-AC3, JCL-B3
    spec = spec_at(tmp_path)
    gold(spec)
    rec = cal.score(spec, "review", judge_ex())
    st = cal.state(spec, "review")
    assert st.state == "accepted", st.failing
    assert rec["figures"]["catch_rate"] == 1.0 and rec["figures"]["known_bad"] == 24
    assert rec["usage"]["sessions"] == 15 * 5
    assert cal.has_score(spec, "review") and not cal.has_score(spec, "draft")
    assert cal.state(spec_at(tmp_path, model="medium"), "review").changed == ["alias", "model_slug"] or \
        "alias" in cal.state(spec_at(tmp_path, model="medium"), "review").changed
    assert cal.state(spec_at(tmp_path, brief="Read harder"), "review").state == "stale"
    assert cal.state(spec, "review", observed={"executor_version": "9.9"}).changed == ["executor_version"]
    make_case(spec, "good-new", False)
    st = cal.state(spec, "review")
    assert st.state == "stale" and st.changed == ["case_set_digest"]
    assert not cal.has_score(spec, "review")


def test_a_discarded_judgement_is_a_fail_in_the_count(tmp_path: Path) -> None:  # JCL-AC2, JCL-B1
    spec = spec_at(tmp_path)
    make_case(spec, "good-0", False)
    make_case(spec, "bad-0", True)
    rec = cal.score(spec, "review", judge_ex(tools=("Write",)), repeats=1, variants=(), write=False)
    fig = rec["figures"]
    assert fig["known_good"] == 3 and fig["clean_rate"] == 0.0  # not clean, still in the denominator
    assert fig["known_bad"] == 3 and fig["catch_rate"] == 1.0  # a fail status catches
    assert all(set(r["statuses"].values()) == {cal.DISCARDED} for r in rec["results"])
    rec = cal.score(spec, "review", judge_ex(unparsed_on="GOOD"), repeats=1, variants=(), write=False)
    assert rec["figures"]["clean_rate"] == 0.0 and rec["figures"]["known_good"] == 3


def test_tuning_consumes_cases(tmp_path: Path) -> None:  # JCL-AC4, JCL-B4
    spec = spec_at(tmp_path)
    gold(spec)
    cal.score(spec, "review", judge_ex())
    assert cal.state(spec, "review").state == "accepted"
    moved = cal.mark_tune(tmp_path, "review", ["bad-0", "bad-1", "bad-2"], by="author")
    assert moved == ["bad-0", "bad-1", "bad-2"]
    st = cal.state(spec, "review")
    # the split is part of the case-set digest: the score no longer describes these cases
    assert st.state == "stale"
    cal.score(spec, "review", judge_ex())
    st = cal.state(spec, "review")
    assert st.state == "below_bar" and any("known-bad holdout findings" in f for f in st.failing)
    assert st.score is not None and st.score["figures"]["known_bad"] == 15
    assert st.score["figures"]["tune"]["known_bad"] == 9
    assert cal.mark_tune(tmp_path, "review", ["bad-0"], by="author") == []


def test_no_code_path_returns_a_case_to_holdout() -> None:  # JCL-AC4 source test
    hits = [p for p in SRC.rglob("*.py") if re.search(r"\.split\s*=\s*[\"']holdout", p.read_text())
            or re.search(r"[\"']split[\"']\s*:\s*[\"']holdout", p.read_text())]
    assert hits == []


def test_variants_are_templated_and_reproducible(tmp_path: Path) -> None:  # JCL-AC5
    spec = spec_at(tmp_path)
    make_case(spec, "bad-0", True)
    g, _, _ = cal.gate_spec(spec, "review")
    [u], _ = cal.usable(spec, "review")
    base = cal.base_subject(u.case, g.criteria)
    for kind in cal.VARIANTS:
        one = cal.variant(base, kind, g.criteria, u.case.reach)
        two = cal.variant(cal.base_subject(u.case, g.criteria), kind, g.criteria, u.case.reach)
        assert one is not None and two is not None and one.digest() == two.digest() != base.digest()
    oor = cal.variant(base, "out_of_reach", g.criteria, u.case.reach)
    assert oor is not None and "spec" not in oor.references and oor.removed_for == "c1"
    re_ = cal.variant(base, "reordered", g.criteria, u.case.reach)
    assert re_ is not None and re_.criteria_order == ("c3", "c2", "c1")


def test_persuasion_and_out_of_reach_fail_the_bar(tmp_path: Path) -> None:  # JCL-B5, JCL-B6
    spec = spec_at(tmp_path)
    gold(spec)
    cal.score(spec, "review", judge_ex(persuaded=True))
    st = cal.state(spec, "review")
    assert st.state == "below_bar" and any("variant_flip[persuasive_account]" in f for f in st.failing)
    assert st.score and {"case": "bad-0", "criterion": "c1", "status": "MET"} in st.score["figures"][
        "variant_cases"]["persuasive_account"]
    cal.score(spec, "review", judge_ex(met_out_of_reach=True))
    st = cal.state(spec, "review")
    assert st.state == "below_bar" and any("out_of_reach_ok" in f for f in st.failing)


def test_production_contradicts_and_synthetic_is_provisional(tmp_path: Path) -> None:  # JCL-B7, JCL-B17
    spec = spec_at(tmp_path)
    gold(spec, provenance="synthetic")
    cal.score(spec, "review", judge_ex())
    assert cal.state(spec, "review").state == "provisional"
    assert cal.passing(spec, "review") and not cal.has_score(spec, "review")
    st = cal.state(spec, "review", production_grade=lambda g, b: "unreliable")
    assert st.state == "contradicted" and st.production_grade == "unreliable"


def test_the_outcome_judge_with_four_synthetic_cases_is_below_bar(tmp_path: Path) -> None:  # JCL-B8
    from tempergraph.package.loader import load

    from .fixtures.packages import minimal_package

    pkg = minimal_package(tmp_path)
    spec = load(pkg)
    for i in range(4):
        folder = cal.calibration_dir(pkg, "outcome") / f"s-{i}"
        (folder / "fixture" / "workspace").mkdir(parents=True)
        (folder / "case.json").write_text(json.dumps({"case_id": f"s-{i}", "gate": "outcome", "labels": [],
                                                      "provenance": "synthetic"}))
        cal.write_label(spec, "outcome", f"s-{i}", "rn-complete", "UNMET" if i % 2 else "MET", "Planted.", "dana",
                        person=True)
    ex = standin("claude", judges=[answer('```json\n{"criteria": [{"n": 1, "status": "UNMET", "evidence": "x"}],'
                                          ' "gap": false, "confidence": 0.5}\n```', tools=("Read",))] * 40)
    cal.score(spec, "outcome", ex)
    st = cal.state(spec, "outcome")
    assert st.state == "below_bar" and not cal.has_score(spec, "outcome")  # SIL-B7 keeps outcome uncalibrated


def test_a_score_record_holds_no_model_text(tmp_path: Path) -> None:  # JCL-AC6
    spec = spec_at(tmp_path)
    make_case(spec, "bad-0", True, request=f"BAD {CANARY}")
    cal.score(spec, "review", judge_ex(), repeats=1)
    text = (cal.calibration_dir(tmp_path, "review") / "scores.jsonl").read_text()
    assert CANARY not in text and "Graded." not in text and "notes.md:1" not in text


def test_readers_need_the_state_they_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # JCL-AC7
    spec = spec_at(tmp_path)
    c = crit("o1")
    c = dataclasses.replace(c, verified_by="judge")
    for name in cal.STATES:
        st = cal.State(gate="review", state=name, binding={},
                       score={"figures": {"catch_rate": 0.9, "clean_rate": 0.95}})
        monkeypatch.setattr(cal, "_state_of", lambda s, g, r, n=name: n)
        accepted = cal.accepted_for(spec)
        assert (trust(c, "review", tmp_path, accepted) == "calibrated") is (name == "accepted")
        ready = {g.gate: g.grade for g in readiness(spec)}
        assert (ready.get("review") == "ready") is (name == "accepted") or ready.get("review") == "needs work"
        label = cal.corrected(0.80, st)["label"]
        assert (label == "corrected") is (name in ("accepted", "provisional"))


def test_corrected_rate() -> None:  # EVS-B5
    st = cal.State(gate="g", state="accepted", binding={}, score={"figures": {"catch_rate": 0.9, "clean_rate": 0.95}})
    assert cal.corrected(0.80, st) == {"raw": 0.8, "corrected": 0.8235, "label": "corrected", "state": "accepted"}
    assert cal.corrected(0.80, dataclasses.replace(st, state="stale"))["label"] == "uncorrected (stale)"
    assert cal.corrected(0.80, dataclasses.replace(st, state="provisional"))["label"] == "corrected"
    for name in ("unscored", "below_bar", "contradicted"):  # EVS-AC2: every label of the EVS-B15 table
        got = cal.corrected(0.80, dataclasses.replace(st, state=name, score=None))
        assert got == {"raw": 0.8, "label": f"uncorrected ({name})", "state": name}
    weak = dataclasses.replace(st, score={"figures": {"catch_rate": 0.6, "clean_rate": 0.55}})
    assert cal.corrected(0.80, weak) == {"raw": 0.8, "label": "uncorrectable", "state": "accepted"}


def test_a_cap_keeps_the_score_partial_and_out_of_the_state(tmp_path: Path) -> None:  # JCL-B9, JCL-B12, JCL-B14
    spec = spec_at(tmp_path)
    gold(spec)
    rec = cal.score(spec, "review", judge_ex(), cap_usd=0.05)
    assert rec["partial"] and rec["usage"]["sessions"] == 5
    assert cal.state(spec, "review").state == "unscored"


def test_an_executor_that_cannot_hold_the_view_set_is_refused(tmp_path: Path) -> None:  # JCL-B9, JCL-B12, JCL-B14
    spec = spec_at(tmp_path)
    make_case(spec, "bad-0", True)
    ex = standin("antigravity", judges=[oracle()])
    with pytest.raises(cal.CalibrationError, match="cannot hold a judge"):
        cal.score(spec, "review", ex)
    assert ex.calls == []


def test_stale_labels_and_invalid_cases_are_not_scored(tmp_path: Path) -> None:  # JCL-B12, JCL-B9, JCL-B14
    spec = spec_at(tmp_path)
    make_case(spec, "bad-0", True)
    make_case(spec, "cand", True, label=False)
    folder = cal.calibration_dir(tmp_path, "review") / "odd"
    (folder / "fixture").mkdir(parents=True)
    (folder / "case.json").write_text(json.dumps({"labels": [{"criterion_id": "zz", "expected": "MET"}]}))
    u = spec.units["review"]
    changed = dataclasses.replace(u.gate, criteria=(crit("c1", "A new text"), *u.gate.criteria[1:]))
    spec2 = dataclasses.replace(spec, units={**spec.units, "review": dataclasses.replace(u, gate=changed)})
    ok, skipped = cal.usable(spec2, "review")
    assert [x.case.case_id for x in ok] == ["bad-0"] and ok[0].stale_labels == ["c1"] and "c1" not in ok[0].labels
    assert {s["case"]: s["why"] for s in skipped} == {"cand": "candidate", "odd": "invalid"}


def test_evals_bar_and_label_make_no_model_call(tmp_path: Path, repo: Path) -> None:  # JCL-AC8, JCL-B14, JCL-B18
    from tempergraph.catalog import Catalog
    from tempergraph.cli.main import main

    spec = spec_at(tmp_path)
    make_case(spec, "bad-0", True, label=False)
    ex = standin("claude")  # no scripted reply: any session would fail the test
    reg = Registry()
    reg.register(ex)
    cat = Catalog(specs={"demo": spec})
    out = io.StringIO()
    code = main(["evals", "label", "demo/review/bad-0", "--criterion", "c1", "--expected", "UNMET", "--reason",
                 "Planted defect.", "--reviewer", "dana", "--json"], catalog=cat, registry=reg, cwd=repo, out=out,
                err=io.StringIO(), signals=({}, True))
    assert code == 0 and json.loads(out.getvalue())["by_person"] is True
    out = io.StringIO()
    assert main(["evals", "bar", "demo", "--json"], catalog=cat, registry=reg, cwd=repo, out=out,
                err=io.StringIO(), signals=({}, True)) == 0
    gates = {g["gate"]: g for g in json.loads(out.getvalue())["workflows"][0]["gates"]}
    assert gates["review"]["state"] == "unscored" and gates["review"]["needed"]
    assert ex.calls == []
    agent = io.StringIO()
    main(["evals", "label", "demo/review/bad-0", "--criterion", "c2", "--expected", "UNMET", "--reason", "x",
          "--json"], catalog=cat, registry=reg, cwd=repo, out=agent, err=io.StringIO(),
         signals=({"CLAUDECODE": "1"}, False))
    assert json.loads(agent.getvalue())["by_person"] is False  # an agent's gold label keeps the case a candidate
