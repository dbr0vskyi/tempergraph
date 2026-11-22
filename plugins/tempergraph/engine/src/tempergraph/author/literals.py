"""`literals <workflow> [--cases]` (SCF-B13): a deterministic scan for literals that belong to one case, not to
the workflow: a ticket id, a URL, an e-mail address, a path outside the package, or a run of at least six
words from a case request or an intake example. A hit recorded in `authoring.json` decisions (by its
`literal_digest`) is not reported again. Source files of an authoring session live in the session folder,
not the package, so a packaged workflow is scanned against its cases and examples only (SCF-B11, SCF-B13, SCF-B15, SCF-B16, SCF-B17, SCF-B18, SCF-B19, SCF-B20, SCF-B22)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph.contracts import TextRef, WorkflowSpec
from tempergraph.model.text import TextUnreadable, load_text

TICKET = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d{1,6}\b")
URL = re.compile(r"\bhttps?://[^\s)>\]`'\"]+")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PATH = re.compile(r"(?<![\w.])(?:~/|/(?:home|Users|tmp|var|etc|opt|mnt|srv)/)[^\s`'\")]+")
RUN = 6
WORD = re.compile(r"[A-Za-z0-9']+")


@dataclass(frozen=True, kw_only=True)
class Hit:
    kind: str  # ticket, url, email, path, case_text
    file: str
    line: int
    text: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(f"{self.file}\0{self.kind}\0{self.text}".encode()).hexdigest()

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "file": self.file, "line": self.line, "text": self.text, "digest": self.digest}


def _read(spec: WorkflowSpec, src: str | TextRef) -> str | None:
    try:
        return load_text(spec, src)
    except TextUnreadable:
        return None


def _texts(spec: WorkflowSpec) -> Iterator[tuple[str, str]]:
    """(file, text) for prompts, briefs, stances, criteria and check methods, the outcome statement, checks."""
    root = spec.package_root
    seen: set[str] = set()
    for unit in spec.order:
        u = spec.units.get(unit)
        if u is None:
            continue
        if u.step is not None and u.step.prompt != "default":
            file = u.step.prompt.path if isinstance(u.step.prompt, TextRef) else f"inline:{unit}"
            if file not in seen:
                seen.add(file)
                text = _read(spec, u.step.prompt)
                if text is not None:
                    yield file, text
        j = u.gate.judge
        if j is not None:
            if j.file and root is not None and j.file not in seen:
                seen.add(j.file)
                text = _read(spec, TextRef(path=j.file))
                if text is not None:
                    yield j.file, text
            elif not j.file:
                yield f"inline:{unit}:judge", f"{j.stance}\n{j.brief}"
        crit = "\n".join(f"{c.text}\n{c.check_method}" for c in u.gate.criteria)
        if crit.strip() and (root is None or not (root / "outcome.json").is_file()):
            yield f"inline:{unit}:criteria", crit
    if root is not None:
        out = root / "outcome.json"
        if out.is_file():
            yield "outcome.json", out.read_text(encoding="utf-8")
        for p in sorted((root / "workflow").rglob("checks.py")):
            yield p.relative_to(root).as_posix(), p.read_text(encoding="utf-8")


def _case_texts(spec: WorkflowSpec) -> list[str]:
    texts = [str(e) for e in spec.input.examples]
    root = spec.package_root
    if root is not None:
        try:
            doc = json.loads((root / "evals" / "cases.json").read_text(encoding="utf-8"))
            texts += [str(c.get("request", "")) for c in doc.get("cases") or [] if isinstance(c, dict)]
        except (OSError, ValueError, AttributeError):
            pass
    return [t for t in texts if t]


def _recorded(root: Path | None) -> set[str]:
    if root is None:
        return set()
    try:
        doc = json.loads((root / "authoring.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(d.get("literal_digest")) for d in doc.get("decisions") or [] if isinstance(d, dict)
            and d.get("literal_digest")}


def _runs(text: str) -> set[tuple[str, ...]]:
    words = [w.lower() for w in WORD.findall(text)]
    return {tuple(words[i:i + RUN]) for i in range(len(words) - RUN + 1)}


def scan(spec: WorkflowSpec, *, cases: bool = True) -> list[Hit]:
    recorded = _recorded(spec.package_root)
    case_runs = set().union(*(_runs(t) for t in _case_texts(spec))) if cases else set()
    hits: list[Hit] = []
    for file, text in _texts(spec):
        lines = text.splitlines()
        for n, line in enumerate(lines, 1):
            for kind, pat in (("url", URL), ("email", EMAIL), ("ticket", TICKET), ("path", PATH)):
                for m in pat.finditer(line):
                    if kind == "ticket" and EMAIL.search(line) and m.group(0) in line.split("@")[-1]:
                        continue
                    hits.append(Hit(kind=kind, file=file, line=n, text=m.group(0)))
        if case_runs:
            words = [(m.group(0).lower(), text.count("\n", 0, m.start()) + 1) for m in WORD.finditer(text)]
            i = 0
            while i <= len(words) - RUN:
                if tuple(w for w, _ in words[i:i + RUN]) in case_runs:
                    j = i + RUN
                    while j < len(words) and tuple(w for w, _ in words[j - RUN + 1:j + 1]) in case_runs:
                        j += 1
                    hits.append(Hit(kind="case_text", file=file, line=words[i][1],
                                    text=" ".join(w for w, _ in words[i:j])))
                    i = j
                else:
                    i += 1
    return [h for h in hits if h.digest not in recorded]
