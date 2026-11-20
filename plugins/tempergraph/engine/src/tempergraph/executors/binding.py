"""The per-machine binding table (EXI §2.2, SEC-B1).

The table lives at ``<home>/config/bindings.json``. A typed alias only selects an entry; the entry's
value, never the typed text, reaches argv. With no file, each executor's built-in tiers apply.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.docs import read_json
from tempergraph.store.layout import home_path

BINDINGS_FILE = "bindings.json"

# Built-in tiers when the operator file has no row (R-001 F10: the CLI takes these model names).
DEFAULT_TIERS: dict[str, dict[str, str]] = {
    "claude": {"small": "haiku", "medium": "sonnet", "large": "opus"},
    "agent-sdk": {"small": "haiku", "medium": "sonnet", "large": "opus"},
}

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/\[\]-]{0,127}$")


class BindingError(ValueError):
    """An alias with no entry, or an entry whose value is not a plain model name."""


@dataclass(frozen=True, kw_only=True)
class Binding:
    executor: str
    tiers: Mapping[str, str] = field(default_factory=dict)
    aliases: Mapping[str, str] = field(default_factory=dict)
    prices: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    provider: str | None = None

    def qualified(self) -> frozenset[str]:
        return frozenset(f"{self.executor}:{name}" for name in self.aliases)

    def model(self, alias: str) -> str | None:
        """The bound model name for ``alias``; None for ``inherit`` (the CLI's own default)."""
        if alias == "inherit":
            return None
        if alias in self.tiers:
            value = self.tiers[alias]
        elif alias.startswith(self.executor + ":") and alias.split(":", 1)[1] in self.aliases:
            value = self.aliases[alias.split(":", 1)[1]]
        else:
            raise BindingError(f"alias-unbound: {alias} on {self.executor}")
        if not _MODEL_RE.match(value):
            raise BindingError(f"binding-value-invalid: {alias} on {self.executor}")
        return value


@dataclass(frozen=True, kw_only=True)
class BindingTable:
    rows: Mapping[str, Binding] = field(default_factory=dict)

    def for_executor(self, name: str) -> Binding:
        if name in self.rows:
            return self.rows[name]
        return Binding(executor=name, tiers=DEFAULT_TIERS.get(name, {}))


def _row(executor: str, data: Mapping[str, Any]) -> Binding:
    tiers = dict(DEFAULT_TIERS.get(executor, {}))
    tiers.update({str(k): str(v) for k, v in (data.get("tiers") or {}).items()})
    return Binding(
        executor=executor,
        tiers=tiers,
        aliases={str(k): str(v) for k, v in (data.get("aliases") or {}).items()},
        prices={str(k): dict(v) for k, v in (data.get("prices") or {}).items()},
        provider=data.get("provider"),
    )


def load(home: Path | None = None) -> BindingTable:
    """Read the operator's table; unknown keys are ignored (CON §2.10 tolerant reader)."""
    path = (home or home_path()) / "config" / BINDINGS_FILE
    if not path.exists():
        return BindingTable()
    doc = read_json(path, "bindings")
    rows = {}
    for item in doc.get("bindings", []):
        if isinstance(item, dict) and isinstance(item.get("executor"), str):
            rows[item["executor"]] = _row(item["executor"], item)
    return BindingTable(rows=rows)
