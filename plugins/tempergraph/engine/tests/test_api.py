"""Builders of the public interface (PKG §2.4, PKG-AC-4, PKG-B2)."""

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
