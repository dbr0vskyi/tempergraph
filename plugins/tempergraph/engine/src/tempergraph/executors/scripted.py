"""A registry holding one scripted stand-in, for the engine's own model-free runs (the generated stand-in run
of a scaffolded package, SCF-B14, SCF-B15, SCF-B16, SCF-B17). Engine code outside this package reaches the stand-ins only here."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import answer, standin

__all__ = ["answer", "scripted_registry"]


def scripted_registry(name: str, steps: Sequence[Any], judges: Sequence[Any]) -> Registry:
    r = Registry()
    r.register(standin(name, steps=list(steps), judges=list(judges)))  # type: ignore[arg-type]
    return r
