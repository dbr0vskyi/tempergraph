"""Retirement of the release 1 model list: the refusal, the transform by rule, one alias per `model`, and the
loop's alias as a setting (LAD-AC-6, LAD §2.6, §2.8)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tempergraph.executors.capabilities import DECLARED
from tempergraph.model import retire
from tempergraph.model.validate import validate
from tempergraph.package import changelog
from tempergraph.settings import ConfigFiles, effective_spec, options_snapshot, resolve, run_values

from .fixtures.workflows import two_step


def with_model(model: Any, **step: Any) -> Any:
    spec = two_step()
    units = dict(spec.units)
    units["draft"] = dataclasses.replace(units["draft"], step=dataclasses.replace(units["draft"].step, model=model, **step))
    return dataclasses.replace(spec, units=units)


@pytest.mark.parametrize(("r1", "model", "to", "owner"), [
    (["small"], "small", None, False),
    (["small", "medium"], "small", "medium", False),
    (["medium", "large"], "medium", "large", False),
    (["small", "large"], "small", None, True),  # a jump of two tiers
    (["small", "medium", "large"], "small", None, True),  # three rungs
    (["claude:haiku", "claude:sonnet"], "claude:haiku", None, True),  # qualified aliases
    (["medium", "small"], "medium", None, True),
    (["large", "large"], "large", None, True),
])
def test_transform_rewrites_each_row_of_the_table(r1: list[str], model: str, to: str | None, owner: bool) -> None:
    got = retire.model_list_to_escalation(r1)
    assert got["model"] == model
    assert got["escalation"] == ({"to": to} if to else None)  # default stages: none stated
    assert (got["owner_item"] == retire.OWNER_ITEM) is owner


def test_a_model_list_is_refused_with_its_rewrite() -> None:
    findings = validate(with_model(("small", "medium")), DECLARED)
    hit = [f for f in findings if f.code == "model-ladder-retired"]
    assert len(hit) == 1 and hit[0].severity == "error" and hit[0].unit == "draft"
    assert "model: small" in hit[0].message and "escalation: {to: medium}" in hit[0].message
    assert not [f for f in validate(with_model("small"), DECLARED) if f.code == "model-ladder-retired"]


def test_a_one_alias_list_and_a_profile_list_are_refused_too() -> None:
    assert [f.code for f in validate(with_model(("small",)), DECLARED) if f.severity == "error"] == ["model-ladder-retired"]
    spec = dataclasses.replace(two_step(), model_profile={"draft": ("small", "large")})
    hit = [f for f in validate(spec, DECLARED) if f.code == "model-ladder-retired"]
    assert len(hit) == 1 and retire.OWNER_ITEM in hit[0].message


def test_the_rewritten_workflow_validates() -> None:
    from tempergraph.contracts import EscalationSpec

    spec = with_model(("small", "medium"))
    got = retire.detect(spec)["units.draft.model"]
    fixed = with_model(got["model"], escalation=EscalationSpec(to=got["escalation"]["to"]))
    assert not [f for f in validate(fixed, DECLARED) if f.severity == "error"]
    assert retire.detect(fixed) == {}


def settle(flags: dict[str, Any]) -> tuple[Any, list[Any]]:
    opts, findings = options_snapshot(two_step(), flags, (), ConfigFiles())
    return resolve(two_step(), opts), findings


def test_a_setting_takes_one_alias_per_model() -> None:
    for value in ("small,medium", ["small", "medium"]):
        _, bad = settle({"draft.model": value})
        assert [f.code for f in bad] == ["setting_value"] and "one alias" in bad[0].message
    res, bad = settle({"draft.model": "large"})
    assert not bad and effective_spec(two_step(), res).units["draft"].step.model == "large"


def test_the_transform_is_a_known_changelog_transform() -> None:
    assert changelog.TRANSFORMS[retire.TRANSFORM] == "spec_field"


def test_the_loop_alias_is_a_run_setting(tmp_path: Path) -> None:
    from tempergraph.improve import child

    assert run_values(settle({})[0])["loop_model"] == "medium"
    assert run_values(settle({"run.loop_model": "large"})[0])["loop_model"] == "large"
    assert [f.code for f in settle({"run.loop_model": "huge"})[1]] == ["setting_value"]
    summary = {"lenses": {"friction": True}, "fault_fingerprints": ["f1"], "fingerprints": ["f1"]}
    kw: dict[str, Any] = {"dry_run": True, "judge_executor": "claude", "home": tmp_path}
    path = child.hand_off(tmp_path, two_step(), "T-1", "th", summary, loop_model="large", **kw)
    assert path is not None and __import__("json").loads(path.read_text())["alias"] == "large"
    path = child.hand_off(tmp_path, two_step(), "T-2", "th", summary, **kw)
    assert path is not None and child.alias_of(__import__("json").loads(path.read_text())) == "medium"
