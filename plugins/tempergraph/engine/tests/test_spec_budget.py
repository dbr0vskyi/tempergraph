"""Spec budget rule of the docs README: at most 400 lines and 30 KB per spec (OVR-AC-2)."""

from __future__ import annotations

from .conftest import DOCS


def test_every_spec_within_budget() -> None:
    over = []
    for p in sorted((DOCS / "specs").glob("*.spec.md")):
        data = p.read_bytes()
        if len(data) > 30 * 1024 or data.count(b"\n") > 400:
            over.append(f"{p.name}: {len(data)} bytes, {data.count(b'\n')} lines")
    assert over == [], over
