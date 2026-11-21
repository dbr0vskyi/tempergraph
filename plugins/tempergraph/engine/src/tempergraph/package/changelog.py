"""The compatibility changelog and a workflow's compatibility with the running engine (VER §2.3, §2.7).

One file per release, `tempergraph/data/changelog/<engine_version>.json`. Range selection reads the files
after the stamp up to and including the running engine, oldest first (VER-B2). Detect rules run typed kinds
first; a `text` hit at a location a typed rule already hit is dropped (VER-B3). Read-only, model-free.
"""

from __future__ import annotations

import ast
import fnmatch
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph.constants import ENGINE_VERSION
from tempergraph.contracts import WorkflowSpec
from tempergraph.package.inventory import canonical

CHANGELOG_DIR = Path(__file__).resolve().parents[1] / "data" / "changelog"
AUDIENCES = frozenset({"workflow", "operator", "state", "integration"})
KINDS = frozenset({"added", "deprecated", "renamed", "removed", "changed", "tightened", "behaviour", "executor"})
SURFACES = frozenset({"spec_field", "declaration", "callable", "template", "capability", "tool_name", "cli",
                      "document", "state"})
DETECT_KINDS = frozenset({"field", "symbol", "template_key", "tool_ref", "finding", "text"})
MIGRATE = frozenset({"transform", "assisted", "owner", "none"})
TRANSFORMS = {"rename_field": "spec_field", "set_field": "spec_field", "drop_field": "spec_field",
              "rename_symbol": "declaration", "rename_template_key": "template", "rename_tool": "tool_name",
              "map_capability": "capability", "model_list_to_escalation": "spec_field"}
TYPED = ("field", "symbol", "template_key", "tool_ref", "finding")


def semver(v: str) -> tuple[int, int, int]:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v)
    if m is None:
        raise ValueError(f"{v!r} is not a semantic version")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def entry_problems(e: Mapping[str, Any]) -> list[str]:
    """VER-AC-2: an entry against §2.3, and VER-B4: a `renamed` entry a transform fits carries it."""
    out = []
    if not re.match(r"^E\d+\.\d+\.\d+-\d+$", str(e.get("id") or "")):
        out.append("id must be E<version>-<n>")
    for key, allowed in (("audience", AUDIENCES), ("kind", KINDS), ("surface", SURFACES)):
        if e.get(key) not in allowed:
            out.append(f"{key} {e.get(key)!r} is not one of {sorted(allowed)}")
    if not isinstance(e.get("breaking"), bool):
        out.append("breaking must be true or false")
    if e.get("kind") == "added" and e.get("breaking"):
        out.append("an `added` entry is never breaking")
    for rule in e.get("detect") or []:
        if not isinstance(rule, Mapping) or rule.get("kind") not in DETECT_KINDS:
            out.append(f"detect rule {rule!r} has an unknown kind")
    mig = e.get("migrate") or {}
    if not isinstance(mig, Mapping) or mig.get("action") not in MIGRATE:
        out.append("migrate must be one of transform, assisted, owner, none")
    elif e.get("kind") == "renamed" and mig.get("action") != "transform":
        fits = [t for t, s in TRANSFORMS.items() if s == e.get("surface") and t.startswith("rename")]
        if fits:
            out.append(f"a `renamed` entry on {e.get('surface')} carries a transform: {fits[0]}")
    if e.get("kind") == "deprecated" and not e.get("removal_in"):
        out.append("a `deprecated` entry names `removal_in`")
    return out


def releases(folder: Path | None = None) -> list[tuple[tuple[int, int, int], Path]]:
    d = folder or CHANGELOG_DIR
    out = []
    for p in d.glob("*.json") if d.is_dir() else []:
        try:
            out.append((semver(p.stem), p))
        except ValueError:
            continue
    return sorted(out)


def entries_between(stamp: str | None, engine: str = ENGINE_VERSION,
                    folder: Path | None = None) -> list[dict[str, Any]]:
    """VER-B2: files after `stamp` up to and including `engine`, oldest first; all of them when unstamped."""
    lo = semver(stamp) if stamp else None
    hi = semver(engine)
    out: list[dict[str, Any]] = []
    for v, path in releases(folder):
        if (lo is None or v > lo) and v <= hi:
            doc = json.loads(path.read_text(encoding="utf-8"))
            out += [dict(e) for e in doc.get("entries") or [] if isinstance(e, Mapping)]
    return out


def breaking_since_level(level: int, folder: Path | None = None) -> list[str]:
    """PKG-B6 row 2: ids of the breaking `workflow` entries a package at interface `level` has not met. The
    level starts at 1 and grows by one with each release holding such an entry (VER §2.2), so the entries of
    every release that raised it above `level` are the ones listed, oldest first."""
    at, out = 1, []
    for _, path in releases(folder):
        doc = json.loads(path.read_text(encoding="utf-8"))
        ids = [str(e.get("id")) for e in doc.get("entries") or [] if isinstance(e, Mapping)
               and e.get("audience") == "workflow" and e.get("breaking")]
        if ids:
            at += 1
            if at > level:
                out += ids
    return out


@dataclass(frozen=True)
class Hit:
    entry: str
    rule: str
    where: str
    confidence: str


def _field_values(obj: Any, parts: list[str], prefix: str = "") -> Iterable[tuple[str, Any]]:
    if not parts:
        yield prefix, obj
        return
    head, rest = parts[0], parts[1:]
    if isinstance(obj, Mapping):
        keys = list(obj) if head == "*" else ([head] if head in obj else [])
        for k in keys:
            yield from _field_values(obj[k], rest, f"{prefix}.{k}" if prefix else str(k))


def detect(entry: Mapping[str, Any], spec: WorkflowSpec, root: Path,
           finding_codes: Iterable[str] = ()) -> list[Hit]:
    eid = str(entry.get("id"))
    hits: list[Hit] = []
    data = canonical(spec)
    codes = set(finding_codes)
    py = [p for p in sorted((root / "workflow").rglob("*.py"))] if (root / "workflow").is_dir() else []
    for i, rule in enumerate(entry.get("detect") or []):
        rid, kind = str(rule.get("id") or f"{eid}/{i}"), rule.get("kind")
        if kind == "field":
            m = re.match(r"^(?P<path>[\w.*]+)(?:\s*==\s*(?P<value>.+))?$", str(rule.get("match") or ""))
            if m:
                want = json.loads(m.group("value")) if m.group("value") else None
                for where, val in _field_values(data, m.group("path").split(".")):
                    if m.group("value") is None or val == want:
                        hits.append(Hit(eid, rid, where, "high"))
        elif kind == "symbol":
            name = str(rule.get("match") or "")
            for p in py:
                for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                    if isinstance(node, ast.ImportFrom) and node.module == "tempergraph.api" and any(
                            a.name == name for a in node.names):
                        hits.append(Hit(eid, rid, f"{p.relative_to(root).as_posix()}:{node.lineno}", "high"))
        elif kind == "finding":
            if str(rule.get("match")) in codes:
                hits.append(Hit(eid, rid, f"finding:{rule.get('match')}", "high"))
        elif kind in ("template_key", "tool_ref", "text"):
            pat = re.compile(str(rule.get("match") or "") if kind == "text" else re.escape(
                ("{" + str(rule.get("match")) + "}") if kind == "template_key" else str(rule.get("match"))))
            glob = str(rule.get("files") or "**/*")
            for p in sorted(root.rglob("*")):
                rel = p.relative_to(root).as_posix()
                if not p.is_file() or rel.startswith(("docs/", ".git/")) or not fnmatch.fnmatch(rel, glob):
                    continue
                try:
                    text = p.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for m2 in pat.finditer(text):
                    line = text.count("\n", 0, m2.start()) + 1
                    hits.append(Hit(eid, rid, f"{rel}:{line}", "low" if kind == "text" else "high"))
    typed = {h.where for h in hits if h.confidence == "high"}
    return [h for h in hits if h.confidence == "high" or h.where not in typed]


def compatibility(spec: WorkflowSpec, root: Path, stamp: Mapping[str, Any] | None, *,
                  engine: str = ENGINE_VERSION, folder: Path | None = None,
                  finding_codes: Iterable[str] = ()) -> dict[str, Any]:
    """VER §2.7: `current`, `stamp_behind`, `needs_upgrade`, `out_of_range`, `unstamped`, with the hits."""
    stamped = str(stamp.get("engine_version")) if stamp else None
    entries = [e for e in entries_between(stamped, engine, folder) if e.get("audience") == "workflow"]
    hits = {str(e["id"]): detect(e, spec, root, finding_codes) for e in entries}
    breaking = [e["id"] for e in entries if e.get("breaking") and hits.get(str(e["id"]))]
    if spec.requires_engine and not _in_range(engine, spec.requires_engine):
        state = "out_of_range"
    elif stamped is None:
        state = "unstamped"
    elif breaking:
        state = "needs_upgrade"
    elif stamped == engine or not any(hits.values()):
        state = "current"
    else:
        state = "stamp_behind"
    return {"state": state, "stamp": stamped, "engine": engine, "entries": [e["id"] for e in entries],
            "hits": {k: [h.__dict__ for h in v] for k, v in hits.items() if v}, "breaking": breaking}


def _in_range(version: str, spec_range: str) -> bool:
    v = semver(version)
    for part in (p.strip() for p in spec_range.split(",") if p.strip()):
        m = re.match(r"^(>=|<=|==|<|>|!=)\s*(\d+(?:\.\d+){0,2})$", part)
        if m is None:
            return False
        parts = [int(x) for x in m.group(2).split(".")] + [0, 0]
        b = (parts[0], parts[1], parts[2])
        ok = {">=": v >= b, "<=": v <= b, "==": v == b, "<": v < b, ">": v > b, "!=": v != b}[m.group(1)]
        if not ok:
            return False
    return True
