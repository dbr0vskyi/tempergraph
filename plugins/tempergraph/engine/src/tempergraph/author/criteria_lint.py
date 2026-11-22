"""The criteria lint and the sufficiency check of AUT-B19, AUT-B20, AUT-B21, over an outcome document (`outcome.json` shape).

Model-free. Severities follow AUT-B12, AUT-B15, AUT-B19, AUT-B24, AUT-B25: in `author check` and `author verify` rung 1 every code is an error
except `criterion-overlap` and `criterion-no-seed` (warnings); validation and the readiness report show all of
them as warnings. Each finding carries the guidance the authoring skill gives for it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

VAGUE = ("complete", "good", "clear", "appropriate", "high quality", "high-quality", "user-friendly", "robust",
         "as needed", "etc.", "properly", "nice", "adequate", "reasonable")
MEASURE = re.compile(r"\d|\b(every|each|all|no|none|at least|at most)\b|`[^`]+`|(?:^|\s)[\w.-]*/[\w./-]+", re.I)
SELF = re.compile(r"\b(the )?(step|model|agent|producer|author|it)\s+(confirms?|reports?|says?|states?|declares?|"
                  r"claims?|checks? that it|verif(?:y|ies) (?:that )?it)\b|\bself[- ]check|\bconfirms? (?:that )?it\b",
                  re.I)
CLAUSE = re.compile(r"\s(?:and|or)\s+(?:also\s+)?(?:the|every|each|all|no|it|they|its|a|an)\s+\w+(?:\s+\w+){0,2}?\s+"
                    r"(?:is|are|has|have|does|do|must|should|can|will|was|were|names?|lists?|links?|matches?|"
                    r"covers?|includes?|contains?|uses?|passes?|runs?)\b", re.I)
LIST = re.compile(r";|\n\s*(?:[-*]|\d+[.)])\s|\(\s*[a-z1-9]\s*\)", re.I)
STOP = frozenset(["a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "at", "from", "as", "is", "are", "be", "been", "was", "were", "it", "its", "this", "that", "these", "those", "every", "each", "all", "any", "no", "not", "none", "must", "should", "can", "will", "has", "have", "had", "do", "does", "did", "their", "there", "than", "then", "which", "who", "what", "when", "where", "how", "into", "onto", "over", "under", "per", "since", "also", "only", "one", "two", "three"])
OVERLAP = 0.6

ERROR_IN_CHECK = frozenset({"criterion-vague", "criterion-compound", "criterion-unobservable", "criterion-self-graded",
                            "criterion-unanchored"})

GUIDANCE = {
    "criterion-vague": "Ask what the person would look at to tell it is {word}, and offer two observable rewrites",
    "criterion-compound": "Propose a split: one criterion per claim, each with its own verifier",
    "criterion-unobservable": "Ask where a reviewer would see this, listing the deliverables",
    "criterion-self-graded": "Rewrite it as a fact the gate checks, not a report of the producer",
    "criterion-unanchored": "Draft met, partial, unmet and evidence from the examples for the person to edit",
    "criterion-overlap": "Merge the two, or narrow the intermediate one to what its step decides",
    "criterion-no-seed": "Ask for one example of each, or offer a contrast pair",
    "outcome-insufficient": "Phase 2 does not end until the statement is observable and a blocker exists",
}


@dataclass(frozen=True, kw_only=True)
class LintFinding:
    code: str
    criterion: str | None  # None for the statement or the outcome as a whole
    unit: str | None  # None for a final criterion or the statement
    message: str
    guidance: str

    def severity(self, where: str = "check") -> str:
        """`check` (author check and verify rung 1) or `validate` (validation and readiness: all warnings)."""
        if where != "check":
            return "warning"
        return "error" if self.code in ERROR_IN_CHECK or self.code == "outcome-insufficient" else "warning"

    def to_json(self, where: str = "check") -> dict[str, Any]:
        return {"code": self.code, "criterion": self.criterion, "unit": self.unit, "message": self.message,
                "guidance": self.guidance, "severity": self.severity(where)}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'-]+", text.lower()) if w not in STOP and len(w) > 2}


def _overlap(a: str, b: str) -> bool:
    wa, wb = _words(a), _words(b)
    small = min(len(wa), len(wb))
    return small > 0 and len(wa & wb) / small >= OVERLAP


def vague_words(text: str) -> list[str]:
    """Vague words with no measure in the same sentence (AUT-B12, AUT-B15, AUT-B19, AUT-B24, AUT-B25)."""
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        low = sentence.lower()
        if MEASURE.search(sentence):
            continue
        for word in VAGUE:
            if re.search(r"(?<![\w-])" + re.escape(word) + (r"(?![\w-])" if word[-1].isalnum() else ""), low):
                out.append(word)
    return out


def _criteria(doc: Mapping[str, Any]) -> Iterator[tuple[str | None, Mapping[str, Any]]]:
    for c in doc.get("final") or []:
        if isinstance(c, Mapping):
            yield None, c
    for unit, io in (doc.get("intermediate") or {}).items():
        for c in (io or {}).get("criteria") or [] if isinstance(io, Mapping) else []:
            if isinstance(c, Mapping):
                yield str(unit), c


def _names(doc: Mapping[str, Any]) -> set[str]:
    keys = {str(d.get("key")) for d in doc.get("deliverables") or [] if isinstance(d, Mapping) and d.get("key")}
    return {k.lower() for k in keys}


def _observable(text: str, c: Mapping[str, Any], names: set[str]) -> bool:
    by = c.get("verified_by")
    raw = c.get("verifier")
    v: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    if by in ("person", "none"):
        return True
    if by == "check" and v:
        return True
    if by == "judge" and (v.get("references") or v.get("read_systems")):
        return True
    words = set(re.findall(r"[a-z][\w-]*", text.lower()))
    return bool(words & names) or bool(re.search(r"`[^`]+`|[\w.-]+/[\w./-]+|\.\w{1,4}\b", text))


def lint(doc: Mapping[str, Any]) -> list[LintFinding]:
    """Every code of AUT-B19, AUT-B20, AUT-B21 over the statement and each criterion."""
    out: list[LintFinding] = []
    names = _names(doc)

    def add(code: str, cid: str | None, unit: str | None, message: str, word: str = "") -> None:
        out.append(LintFinding(code=code, criterion=cid, unit=unit, message=message,
                               guidance=GUIDANCE[code].format(word=word or "that")))

    statement = str(doc.get("statement") or "")
    for word in vague_words(statement):
        add("criterion-vague", None, None, f"the statement uses {word!r} with no measure", word)
    if statement and not (set(re.findall(r"[a-z][\w-]*", statement.lower())) & names):
        add("criterion-unobservable", None, None, "the statement names no deliverable")
    by_unit: dict[str | None, list[Mapping[str, Any]]] = {}
    finals = {str(c.get("id")): c for unit, c in _criteria(doc) if unit is None}
    for unit, c in _criteria(doc):
        cid = str(c.get("id") or "") or None
        text = str(c.get("text") or "")
        label = cid or text[:40]
        for word in vague_words(text):
            add("criterion-vague", cid, unit, f"{label}: {word!r} with no measure", word)
        if LIST.search(text) or CLAUSE.search(text):
            add("criterion-compound", cid, unit, f"{label}: more than one claim")
        if not _observable(text, c, names):
            add("criterion-unobservable", cid, unit, f"{label}: nothing a verifier could look at")
        if SELF.search(text):
            add("criterion-self-graded", cid, unit, f"{label}: asks the producer to report on itself")
        if c.get("verified_by") == "judge":
            scale = (c.get("verifier") or {}).get("scale") if isinstance(c.get("verifier"), Mapping) else None
            scale = scale if isinstance(scale, Mapping) else {}
            need = ["met", "unmet", "evidence"] + (["partial"] if c.get("severity", "blocker") == "blocker" else [])
            missing = [k for k in need if not str(scale.get(k) or "").strip()]
            if missing:
                add("criterion-unanchored", cid, unit, f"{label}: the scale lacks {', '.join(missing)}")
            if len([s for s in scale.get("seeds") or [] if s]) < 2:
                add("criterion-no-seed", cid, unit, f"{label}: needs a met seed and an unmet or partial seed")
        for other in by_unit.get(unit, []):
            if _overlap(text, str(other.get("text") or "")):
                add("criterion-overlap", cid, unit, f"{label} and {other.get('id')}: most content words shared")
        if unit is not None:
            for fid in c.get("serves") or []:
                f = finals.get(str(fid))
                if f is not None and _overlap(text, str(f.get("text") or "")) and \
                        _words(text) <= _words(str(f.get("text") or "")):
                    add("criterion-overlap", cid, unit, f"{label} restates final criterion {fid} with no narrowing")
        by_unit.setdefault(unit, []).append(c)
    return out


def sufficiency(doc: Mapping[str, Any], found: list[LintFinding] | None = None) -> list[LintFinding]:
    """AUT-B19, AUT-B20, AUT-B21 sufficiency check of the outcome (before phase 2 ends); empty when it holds."""
    found = lint(doc) if found is None else found
    out = []

    def gap(message: str) -> None:
        out.append(LintFinding(code="outcome-insufficient", criterion=None, unit=None, message=message,
                               guidance=GUIDANCE["outcome-insufficient"]))

    if not str(doc.get("statement") or "").strip():
        gap("no statement")
    elif any(f.criterion is None and f.unit is None and f.code in ("criterion-vague", "criterion-unobservable")
             for f in found):
        gap("the statement is not observable")
    if not doc.get("deliverables"):
        gap("no deliverable")
    finals = [c for unit, c in _criteria(doc) if unit is None]
    if not any(c.get("severity", "blocker") == "blocker" for c in finals):
        gap("no blocker final criterion")
    bad = sorted({str(f.criterion) for f in found if f.unit is None and f.criterion and f.code in ERROR_IN_CHECK})
    if bad:
        gap(f"final criteria failing the lint: {', '.join(bad)}")
    return out


def package_doc(root: Any) -> Mapping[str, Any] | None:
    """The package's `outcome.json`, or None (a workflow with inline criteria only is not linted here)."""
    import json
    from pathlib import Path

    if root is None:
        return None
    try:
        got = json.loads((Path(root) / "outcome.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, Mapping) else None
