"""The template grammar of CON-B8.

Literal text, doubled braces for literal braces, and plain fields ``{name}`` where ``name`` is an engine
key, a declared input, an earlier artifact key, or ``settings.<name>``. Nothing else between braces is
valid. A field without a value renders as the visible marker ``⟨missing:name⟩``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from tempergraph.constants import MISSING_MARKER

FIELD_RE = re.compile(r"^(?:settings\.)?[A-Za-z_][A-Za-z0-9_]*$")


class TemplateError(ValueError):
    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} at offset {position}")
        self.position = position


@dataclass(frozen=True)
class Part:
    literal: str | None = None
    field: str | None = None


def parse(template: str) -> list[Part]:
    parts: list[Part] = []
    buf: list[str] = []
    i, n = 0, len(template)
    while i < n:
        ch = template[i]
        if ch == "{":
            if i + 1 < n and template[i + 1] == "{":
                buf.append("{")
                i += 2
                continue
            end = template.find("}", i + 1)
            if end < 0:
                raise TemplateError("unbalanced '{'", i)
            name = template[i + 1 : end]
            if not FIELD_RE.match(name):
                raise TemplateError(f"invalid field {{{name}}}", i)
            if buf:
                parts.append(Part(literal="".join(buf)))
                buf = []
            parts.append(Part(field=name))
            i = end + 1
            continue
        if ch == "}":
            if i + 1 < n and template[i + 1] == "}":
                buf.append("}")
                i += 2
                continue
            raise TemplateError("unbalanced '}'", i)
        buf.append(ch)
        i += 1
    if buf:
        parts.append(Part(literal="".join(buf)))
    return parts


def fields(template: str) -> list[str]:
    return [p.field for p in parse(template) if p.field is not None]


def render(template: str, values: Mapping[str, str | None]) -> tuple[str, list[str]]:
    """Render; return the text and the fields rendered as the missing marker (CON-AC2)."""
    out: list[str] = []
    missing: list[str] = []
    for p in parse(template):
        if p.literal is not None:
            out.append(p.literal)
            continue
        assert p.field is not None
        val = values.get(p.field)
        if val is None:
            missing.append(p.field)
            out.append(MISSING_MARKER.format(name=p.field))
        else:
            out.append(str(val))
    return "".join(out), missing
