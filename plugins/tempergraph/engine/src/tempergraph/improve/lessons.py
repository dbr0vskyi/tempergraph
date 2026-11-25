"""Per-step lessons: the file, its validation, the rendered block and its digest (LSN; ADR `lessons-are-versioned-workflow-content`).

A lessons file is workflow content (`lessons/<unit>.json` in the package). Runs read it and never write it;
it changes only through a `lessons` proposal, whose delta rules are `classify_change` (LSN-B9).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph.contracts import WorkflowSpec

MAX_ACTIVE = 12
MAX_CHARS = 2500
MAX_TEXT = 300
CRITERION_OVERLAP = 0.8
ID_RE = re.compile(r"^L-[1-9][0-9]*$")
SOURCE_RE = re.compile(r"^(person|proposal:[A-Za-z0-9_.:-]+)$")

# The literal floor of SCF-B13 applied to one sentence: a ticket id, a URL, an e-mail, a path, a number from a
# run (three or more digits), a quote (four or more words in quotation marks).
LITERALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ticket_id", re.compile(r"\b[A-Z][A-Z0-9]+-[0-9]+\b")),
    ("url", re.compile(r"\b(?:https?|ftp)://|\bwww\.", re.I)),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("path", re.compile(r"(?:^|\s)(?:/|~/|[A-Za-z]:\\)\S+")),
    ("number", re.compile(r"\d{3,}")),
    ("quote", re.compile(r"[\"“”'‘’](?:\S+\s+){3,}\S+[\"“”'‘’]")),
)


class LessonsError(ValueError):
    pass


@dataclass(frozen=True, kw_only=True)
class Lesson:
    id: str
    text: str
    status: str = "active"


def path(root: Path, unit: str) -> Path:
    return root / "lessons" / f"{unit}.json"


def literals(text: str) -> list[str]:
    return [name for name, rx in LITERALS if rx.search(text)]


def check(doc: Any, unit: str, units: Sequence[str]) -> list[tuple[str, str]]:
    """Validation findings `(code, message)` for one lessons document (LSN-B6, LSN-B7, LSN-B2)."""
    where = f"lessons/{unit}.json"
    if unit not in units:
        return [("lessons-unknown-unit", f"{where}: the workflow declares no unit {unit!r}")]
    if not isinstance(doc, dict) or doc.get("schema_version") != 1 or not isinstance(doc.get("lessons"), list):
        return [("lessons-malformed", f"{where}: needs schema_version 1 and a list `lessons`")]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    active = 0
    chars = 0
    for i, e in enumerate(doc["lessons"]):
        if not isinstance(e, dict):
            out.append(("lessons-malformed", f"{where}: entry {i} is not an object"))
            continue
        lid, text, status = str(e.get("id") or ""), e.get("text"), e.get("status")
        if not ID_RE.match(lid) or lid in seen:
            out.append(("lessons-id", f"{where}: entry {i} id {lid!r} is not a new L-<n>"))
        seen.add(lid)
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT or "\n" in text:
            out.append(("lessons-text", f"{where}: {lid} text must be one line of at most {MAX_TEXT} characters"))
            continue
        if status not in ("active", "retired"):
            out.append(("lessons-status", f"{where}: {lid} status must be active or retired"))
        if not SOURCE_RE.match(str(e.get("source") or "")):
            out.append(("lessons-source", f"{where}: {lid} source must be `person` or `proposal:<id>`"))
        hits = literals(text)
        if hits:
            out.append(("lessons-literal", f"{where}: {lid} holds a literal ({', '.join(hits)})"))
        if status == "active":
            active += 1
            chars += len(text)
    if active > MAX_ACTIVE or chars > MAX_CHARS:
        out.append(("lessons-budget", f"{where}: {active} active entries, {chars} characters "
                                      f"(at most {MAX_ACTIVE} and {MAX_CHARS})"))
    return out


def validate(spec: WorkflowSpec) -> list[tuple[str, str | None, str]]:
    """Every lessons file of the package: `(code, unit, message)`; nothing when the package has none."""
    root = spec.package_root
    folder = root / "lessons" if root is not None else None
    if folder is None or not folder.is_dir():
        return []
    out: list[tuple[str, str | None, str]] = []
    for f in sorted(folder.iterdir()):
        if f.suffix != ".json":
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = None
        out += [(code, f.stem, msg) for code, msg in check(doc, f.stem, list(spec.units))]
    return out


def load(spec: WorkflowSpec, unit: str) -> tuple[Lesson, ...]:
    """Active entries in id order; a malformed file raises, so a run never starts on half-read lessons."""
    root = spec.package_root
    if root is None:
        return ()
    p = path(root, unit)
    if not p.exists():
        return ()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LessonsError(f"lessons/{unit}.json: {type(exc).__name__}") from None
    problems = check(doc, unit, list(spec.units))
    if problems:
        raise LessonsError(problems[0][1])
    entries = [Lesson(id=e["id"], text=e["text"]) for e in doc["lessons"] if e.get("status") == "active"]
    return tuple(sorted(entries, key=lambda e: int(e.id[2:])))


def block(entries: Sequence[Lesson]) -> str:
    if not entries:
        return ""
    return "## Lessons from earlier runs\n" + "\n".join(f"- {e.id}: {e.text}" for e in entries)


def digest(text: str) -> str | None:
    return hashlib.sha256(text.encode()).hexdigest()[:16] if text else None


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def overlap(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / max(1, min(len(wa), len(wb))) if wa and wb else 0.0


def classify_change(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]],
                    criteria: Sequence[str]) -> str | None:
    """LSN-B9 for a `lessons` proposal: None when allowed, else the refusal code."""
    before = {str(e.get("id")): e for e in old}
    after = {str(e.get("id")): e for e in new}
    if [i for i in after if i in before] != [i for i in before if i in after]:
        return "lessons_rewrite"  # a reorder
    if set(before) - set(after):
        return "lessons_rewrite"  # an entry removed instead of retired
    changed = [i for i in after if i not in before or before[i] != after[i]]
    if len(changed) > 2:
        return "lessons_rewrite"
    for i in changed:
        text = str(after[i].get("text") or "")
        if after[i].get("status") == "active" and any(overlap(text, c) >= CRITERION_OVERLAP for c in criteria):
            return "lesson_is_criterion"
    return None
