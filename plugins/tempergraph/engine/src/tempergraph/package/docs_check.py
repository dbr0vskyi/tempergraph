"""The docs check of a package's docs half, `docs-drift` (PKG §2.5, PKG-B9, PKG-AC-6).

Criterion text lives only in `outcome.json`; the docs name each criterion by id as an acceptance criterion
(`- [ ] <id> <text>`) in the spec of its unit, or the overview for a final criterion. The check compares ids
and whitespace-normalised text, and resolves every relative link under `docs/`. A miss is a warning; in
`stable` mode an error. It reads files only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from tempergraph.contracts import WorkflowSpec
from tempergraph.model.validate import Finding

OVERVIEW = "00-overview.spec.md"
SPEC_RE = re.compile(r"^\d{2}-(?P<unit>.+)\.spec\.md$")
AC_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s+(?P<id>\S+)\s+(?P<text>.+?)\s*$")
LINK_RE = re.compile(r"\[[^\]]*\]\((?P<target>[^)\s]+)\)")
AC_HEADING = re.compile(r"^##\s+6\b|^##\s+acceptance criteria\b", re.I)


def _norm(text: str) -> str:
    return " ".join(text.split())


def criteria_of(spec: WorkflowSpec, root: Path) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """(final id -> text, unit -> {id -> text}); from the attached outcome, else a tolerant read of the file."""
    if spec.outcome is not None:
        final = {c.id: c.text for c in spec.outcome.final if c.id}
        inter = {u: {c.id: c.text for c in o.criteria if c.id} for u, o in spec.outcome.intermediate.items()}
        return final, inter
    try:
        doc = json.loads((root / "outcome.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}
    if not isinstance(doc, dict):
        return {}, {}

    def ids(rows: object) -> dict[str, str]:
        return {str(r["id"]): str(r.get("text", "")) for r in rows or []  # type: ignore[attr-defined]
                if isinstance(r, dict) and r.get("id")}

    inter_doc = doc.get("intermediate") or {}
    return ids(doc.get("final")), {str(u): ids((o or {}).get("criteria")) for u, o in inter_doc.items()
                                   if isinstance(o, dict)}


def _acceptance(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = bool(AC_HEADING.match(line))
            continue
        m = AC_RE.match(line) if inside else None
        if m:
            out[m.group("id")] = _norm(m.group("text"))
    return out


def docs_check(spec: WorkflowSpec, root: Path, mode: Literal["dev", "stable"] | None = None) -> list[Finding]:
    severity: Literal["error", "warning"] = "error" if (mode or spec.improvement_mode) == "stable" else "warning"
    out: list[Finding] = []

    def drift(unit: str | None, message: str) -> None:
        out.append(Finding("docs-drift", unit, message, severity))

    specs_dir = root / "docs" / "specs"
    files: dict[str, Path] = {}  # unit (or "" for the overview) -> file
    if specs_dir.is_dir():
        for p in sorted(specs_dir.glob("*.spec.md")):
            if p.name == OVERVIEW:
                files[""] = p
            elif (m := SPEC_RE.match(p.name)) is not None:
                files[m.group("unit")] = p
    final, inter = criteria_of(spec, root)
    expected: dict[str, Mapping[str, str]] = {"": final, **{u: inter.get(u, {}) for u in spec.order}}
    known = set(final) | {cid for ids in inter.values() for cid in ids}
    if "" not in files:
        drift(None, f"docs/specs/{OVERVIEW} is missing")
    for unit in spec.order:
        if unit not in files:
            drift(unit, f"unit {unit!r} has no spec under docs/specs/ (NN-{unit}.spec.md)")
    seen: dict[str, list[str]] = {}
    for owner, path in files.items():
        rel = path.relative_to(root).as_posix()
        acs = _acceptance(path.read_text(encoding="utf-8"))
        for cid in acs:
            seen.setdefault(cid, []).append(owner)
            if cid not in known:
                drift(owner or None, f"{rel} names criterion {cid!r}, which outcome.json does not hold")
        for cid, text in expected.get(owner, {}).items():
            if cid not in acs:
                drift(owner or None, f"criterion {cid!r} is not an acceptance criterion of {rel}")
            elif acs[cid] != _norm(text):
                drift(owner or None, f"criterion {cid!r}: the text in {rel} differs from outcome.json")
    for cid, owners in seen.items():
        if cid in known and len(owners) > 1:
            drift(None, f"criterion {cid!r} is an acceptance criterion of more than one spec")
    docs = root / "docs"
    for p in sorted(docs.rglob("*.md")) if docs.is_dir() else []:
        for m in LINK_RE.finditer(p.read_text(encoding="utf-8")):
            target = m.group("target").split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target):
                continue
            if not (p.parent / target).exists():
                drift(None, f"{p.relative_to(root).as_posix()}: link {target!r} does not resolve")
    return out
