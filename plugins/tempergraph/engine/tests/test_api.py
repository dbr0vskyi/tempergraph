"""Builders of the public interface (PKG-B19, PKG-B20, PKG-AC4, PKG-B2)."""

from __future__ import annotations

import pytest

from tempergraph.api import Gate, Judge, Routing, Step, Workflow

from .fixtures.workflows import crit, draft_check


def _units() -> dict:
    return {"a": Step(prompt="x", gate=Gate(check=draft_check, judge=Judge(stance="V."), criteria=[crit("a")]))}


def test_unknown_keyword_fails_at_build() -> None:
    with pytest.raises(TypeError):
        Step(prompt="x", gate=Gate(), toolz=["read"])  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        Workflow(order=["a"], units=_units(), issue_repo="a/b")


@pytest.mark.parametrize("field", ["name", "version"])
def test_name_and_version_come_from_manifests(field: str) -> None:
    with pytest.raises(TypeError, match=field):
        Workflow(order=["a"], units=_units(), **{field: "x"})


def test_lambda_and_nested_refused() -> None:
    def nested(ctx):  # noqa: ANN001, ANN202
        return None

    with pytest.raises(TypeError, match="callable-not-importable"):
        Gate(check=lambda ctx: None)
    with pytest.raises(TypeError, match="callable-not-importable"):
        Gate(check=nested)


def test_callable_recorded_by_reference() -> None:
    g = Gate(check=draft_check)
    assert g.check is not None and g.check.ref == "tests.fixtures.workflows:draft_check"
    assert g.check.resolve() is draft_check


def test_built_spec_has_no_identity_until_loaded() -> None:
    wf = Workflow(order=["a"], units=_units(), issue_repository="a/b", routing=Routing(description="Do it"))
    assert wf.name == "" and wf.version == "0.0.0"


def test_contest_and_slot_are_real_builders() -> None:  # CTS-AC1 (CTS-B6, PKG-B19)
    from tempergraph import api
    from tempergraph.contracts import ContestSpec, SlotSpec
    from tempergraph.model.validate import errors, validate

    from .test_contest_validate import CLAUDE_ONLY, base_step, workflow

    assert api.Contest.__name__ == "Contest" and "not_in_release" not in (api.Contest.__doc__ or "")
    u = api.Contest(step=base_step(), slots=[api.Slot("a", executor="claude", model="small", prompt_variant="Go"),
                                             api.Slot("b")], writes=False, retry_scope="all", concurrency=2,
                    cost_cap_usd=0.75)
    assert u.kind == "contest" and isinstance(u.contest, ContestSpec) and u.step is not None
    assert u.contest.slots == (SlotSpec(name="a", executor="claude", model="small", prompt_variant="Go"),
                               SlotSpec(name="b"))
    assert (u.contest.retry_scope, u.contest.concurrency, u.contest.cost_cap_usd) == ("all", 2, 0.75)
    assert api.Contest(step=base_step(), slots=4).contest.slots == 4  # type: ignore[union-attr]
    assert errors(validate(workflow(u), CLAUDE_ONLY)) == []
    with pytest.raises(TypeError):
        api.Contest(step=api.Contest(step=base_step()))  # takes a unit built with Step()
    with pytest.raises(TypeError):
        api.Contest(step=base_step(), slotz=2)  # type: ignore[call-arg]
