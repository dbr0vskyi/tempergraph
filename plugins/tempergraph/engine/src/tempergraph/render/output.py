"""The output contract (PRM §2.3) and step values (VAL §2.1).

A step ends with `ARTIFACT <key>: <value>` lines, or a `BLOCKED:` line, or an `UPSTREAM <unit>:` line.
A claim to a target not offered is read as blocked.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from tempergraph.contracts import ProducesKind, ValueKind
from tempergraph.security.scrub import scrub

_ARTIFACT_RE = re.compile(r"^\s*`?ARTIFACT\s+([A-Za-z0-9_.-]+)\s*:\s*(.*?)`?\s*$")
_BLOCKED_RE = re.compile(r"^\s*`?BLOCKED:\s*(.*?)`?\s*$")
_UPSTREAM_RE = re.compile(r"^\s*`?UPSTREAM\s+([A-Za-z0-9_.-]+)\s*:\s*(.*?)`?\s*$")


@dataclass
class ParsedOutput:
    artifacts: dict[str, str] = field(default_factory=dict)
    values: dict[str, str] = field(default_factory=dict)
    blocked: str | None = None
    upstream: tuple[str, str] | None = None
    issues: list[str] = field(default_factory=list)  # value_invalid:<k>, value_missing:<k>, value_clipped:<k>


def parse_output(text: str, produces: Mapping[str, ProducesKind], upstream_allowed: tuple[str, ...] = ()) -> ParsedOutput:
    out = ParsedOutput()
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    tail: list[str] = []
    for ln in reversed(lines):
        if _ARTIFACT_RE.match(ln) or _BLOCKED_RE.match(ln) or _UPSTREAM_RE.match(ln):
            tail.append(ln)
            continue
        break
    tail.reverse()
    for ln in tail:
        if m := _BLOCKED_RE.match(ln):
            out.blocked = scrub(m.group(1).strip()) or "blocked"
        elif m := _UPSTREAM_RE.match(ln):
            unit, defect = m.group(1), m.group(2).strip()
            if unit in upstream_allowed:
                out.upstream = (unit, scrub(defect))
            else:
                out.blocked = scrub(f"upstream claim on {unit}: {defect}")
        elif m := _ARTIFACT_RE.match(ln):
            out.artifacts[m.group(1)] = m.group(2).strip()
    for key, kind in produces.items():
        raw = out.artifacts.get(key)
        if isinstance(kind, ValueKind):
            if raw is None:
                if not kind.optional:
                    out.issues.append(f"value_missing:{key}")
                continue
            val = scrub(raw.strip())
            if len(val) > kind.max_chars:
                val = val[: kind.max_chars]
                out.issues.append(f"value_clipped:{key}")
            if kind.choices is not None:
                norm = val.strip().lower()
                if norm not in [c.lower() for c in kind.choices]:
                    out.issues.append(f"value_invalid:{key}")
                    continue
                val = norm
            if kind.pattern is not None and not re.fullmatch(kind.pattern, val):
                out.issues.append(f"value_invalid:{key}")
                continue
            out.values[key] = val
    return out
