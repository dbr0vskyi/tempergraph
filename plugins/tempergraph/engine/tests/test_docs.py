"""Tolerant readers (CON-AC4, CON-B1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tempergraph.docs import NewerSchema, append_jsonl, iter_jsonl, read_json, write_json


def test_unknown_key_ignored(tmp_path: Path) -> None:
    p = tmp_path / "status.json"
    write_json(p, {"schema_version": 1, "rows": [], "brand_new_key": 3})
    data = read_json(p, "status")
    assert data["rows"] == [] and data.get("missing") is None


def test_newer_schema_refused(tmp_path: Path) -> None:
    p = tmp_path / "status.json"
    write_json(p, {"schema_version": 99})
    with pytest.raises(NewerSchema):
        read_json(p, "status")


def test_unknown_event_kind_skipped_and_counted(tmp_path: Path) -> None:
    p = tmp_path / "run.jsonl"
    append_jsonl(p, {"kind": "task", "seq": 1})
    append_jsonl(p, {"kind": "from_the_future", "seq": 2})
    with p.open("a") as fh:
        fh.write("not json\n")
    counts: dict[str, int] = {}
    recs = list(iter_jsonl(p, frozenset({"task"}), counts))
    assert [r["seq"] for r in recs] == [1]
    assert counts == {"unknown_kinds": 1, "unparsable": 1}


def test_write_is_owner_only(tmp_path: Path) -> None:
    p = tmp_path / "a" / "doc.json"
    write_json(p, {"schema_version": 1})
    assert (p.stat().st_mode & 0o777) == 0o600
    assert json.loads(p.read_text())["schema_version"] == 1
