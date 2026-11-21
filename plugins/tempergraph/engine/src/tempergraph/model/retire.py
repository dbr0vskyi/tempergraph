"""Retirement of release 1's retry-count model list (LAD §2.8). Pure, model-free.

A list of aliases in a step's `model` is refused from release 2. The transform here rewrites it by rule; what no
rule can decide becomes an owner item of the workflow upgrade (WUP §2.3).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from tempergraph.contracts import WorkflowSpec
from tempergraph.run.ladder import TIER_UP

TRANSFORM = "model_list_to_escalation"
OWNER_ITEM = "choose an `escalation.to`, or none"


def model_list_to_escalation(model: Sequence[str]) -> dict[str, Any]:
    """The release 2 form of a release 1 `model` list: `{model, escalation, owner_item}`."""
    rungs = [str(m) for m in model]
    if not rungs:
        return {"model": None, "escalation": None, "owner_item": None}
    first = rungs[0]
    if len(rungs) == 1:
        return {"model": first, "escalation": None, "owner_item": None}
    if len(rungs) == 2 and TIER_UP.get(first) == rungs[1]:
        return {"model": first, "escalation": {"to": rungs[1]}, "owner_item": None}
    return {"model": first, "escalation": None, "owner_item": OWNER_ITEM}


def detect(spec: WorkflowSpec) -> dict[str, dict[str, Any]]:
    """Every place of a workflow that still holds a model list, with its rewrite: `units.<name>.model` and
    `model_profile.<key>`."""
    out: dict[str, dict[str, Any]] = {}
    for name, u in spec.units.items():
        if u.step is not None and not isinstance(u.step.model, str) and u.step.model is not None:
            out[f"units.{name}.model"] = model_list_to_escalation(tuple(u.step.model))
    for key, val in spec.model_profile.items():
        if not isinstance(val, str) and val is not None:
            out[f"model_profile.{key}"] = model_list_to_escalation(tuple(val))
    return out


def describe(got: dict[str, Any]) -> str:
    """The rewrite in one line, for the refusal's message."""
    text = f"`model: {got['model']}`"
    if got["escalation"]:
        text += f" with `escalation: {{to: {got['escalation']['to']}}}`"
    if got["owner_item"]:
        text += f"; then {got['owner_item']}"
    return text
