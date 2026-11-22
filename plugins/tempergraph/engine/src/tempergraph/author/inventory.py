"""The intake inventory of AUT-B14, AUT-B15: model-free, one record per source file and the verification candidates it
detects. The record holds names, paths, counts, line numbers and digests, never source text (AUT-AC2); the
text stays in the session folder. A source over 5 MB or binary is `kind: other` with no candidates (AUT-B15, AUT-B17, AUT-B24, AUT-B12)."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_BYTES = 5 * 1024 * 1024
KINDS = ("solution", "reference", "example_good", "example_bad", "other")
SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".tempergraph", "dist", "build"})
MAX_FILES = 500

LINTERS = {"ruff": "linter", "flake8": "linter", "pylint": "linter", "black": "linter", "eslint": "linter",
           "prettier": "linter", "markdownlint": "linter", "shellcheck": "linter", "stylelint": "linter",
           "mypy": "type_check", "pyright": "type_check", "tsc": "type_check"}
CONFIG_FILES = {"ruff.toml": "ruff", ".ruff.toml": "ruff", "mypy.ini": "mypy", ".mypy.ini": "mypy",
                ".flake8": "flake8", ".pylintrc": "pylint", "pyrightconfig.json": "pyright", "tsconfig.json": "tsc",
                ".prettierrc": "prettier", ".stylelintrc": "stylelint"}
CONFIG_PREFIXES = {".eslintrc": "eslint", "eslint.config.": "eslint", ".markdownlint": "markdownlint",
                   ".prettierrc": "prettier"}
TEST_WORDS = re.compile(r"\b(pytest|npm (?:run )?test|yarn test|pnpm test|make test|just test|go test|cargo test|"
                        r"tox|nox|bats|unittest)\b")
TASK = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+\S", re.M)
MUST_ITEM = re.compile(r"^\s*\d+[.)]\s+.*\b(must|shall|required)\b", re.M | re.I)
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.M)
AC_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(acceptance criteria|definition of (done|ready))\b", re.M | re.I)
GHERKIN = re.compile(r"^\s*(Given|When|Then)\s", re.M)
REVIEW_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+.*\b(review(er)?s? (check|guide|rules?)|code review)\b", re.M | re.I)
GREP_HEADING = re.compile(r"\bgrep\b[^\n]*['\"]#{1,6}\s")
SELF_CHECK = re.compile(r"\b(check|make sure|verify|confirm|ensure) (that )?you(?:'ve| have)? (covered|did|checked|"
                        r"included|met|done)\b|\b(rate|grade|score) your (own )?(work|answer|output)\b", re.I)


@dataclass(kw_only=True)
class Candidate:
    id: str
    source: str
    kind: str  # existing:test, existing:linter, …, fixture:must_pass, fixture:must_fail, claim:self_check
    detail: dict[str, Any] = field(default_factory=dict)  # names, counts, lines, digests; never text
    used: bool = False

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "source": self.source, "kind": self.kind, "detail": self.detail, "used": self.used}


@dataclass(kw_only=True)
class Source:
    id: str
    kind: str
    locator: str
    digest: str
    size: int
    private: bool
    candidates: list[Candidate] = field(default_factory=list)
    artifact: str | None = None
    unit: str | None = None

    def to_json(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"id": self.id, "kind": self.kind, "locator": self.locator, "digest": self.digest,
                               "size": self.size, "private": self.private,
                               "candidates": [c.id for c in self.candidates]}
        if self.artifact:
            doc["artifact"] = self.artifact
        if self.unit:
            doc["unit"] = self.unit
        return doc


def _lines(text: str, pattern: re.Pattern[str]) -> list[int]:
    return [text.count("\n", 0, m.start()) + 1 for m in pattern.finditer(text)]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _detect(name: str, rel: str, text: str, kind: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """(candidate kind, detail) pairs for one readable text file."""
    low = name.lower()
    if low == "pyproject.toml":
        try:
            tool = tomllib.loads(text).get("tool") or {}
        except tomllib.TOMLDecodeError:
            tool = {}
        if "pytest" in tool:
            yield "existing:test", {"command": "pytest", "from": "pyproject.toml [tool.pytest]"}
        for t in sorted(tool):
            if t in LINTERS:
                yield f"existing:{LINTERS[t]}", {"command": t, "from": f"pyproject.toml [tool.{t}]"}
    elif low == "package.json":
        try:
            doc = json.loads(text)
        except ValueError:
            doc = {}
        scripts = doc.get("scripts") if isinstance(doc, dict) else None
        for script in sorted(scripts or {}):
            if script == "test" or script.startswith("test:"):
                yield "existing:test", {"command": f"npm run {script}", "from": "package.json scripts"}
            elif script in ("lint", "typecheck", "type-check") or script.startswith("lint:"):
                k = "type_check" if "type" in script else "linter"
                yield f"existing:{k}", {"command": f"npm run {script}", "from": "package.json scripts"}
        deps = {**(doc.get("devDependencies") or {}), **(doc.get("dependencies") or {})} if isinstance(doc, dict) \
            else {}
        for d in sorted(deps):
            if d in LINTERS:
                yield f"existing:{LINTERS[d]}", {"command": d, "from": "package.json dependencies"}
    elif low in ("makefile", "justfile", "gnumakefile"):
        tool = "just" if low == "justfile" else "make"
        for target in re.findall(r"^([A-Za-z][\w-]*)\s*:(?!=)", text, re.M):
            if target in ("test", "tests", "check") or target.startswith("test"):
                yield "existing:test", {"command": f"{tool} {target}", "from": name}
            elif target in ("lint", "typecheck", "type-check", "fmt-check"):
                k = "type_check" if "type" in target else "linter"
                yield f"existing:{k}", {"command": f"{tool} {target}", "from": name}
    elif low in CONFIG_FILES or any(low.startswith(p) for p in CONFIG_PREFIXES):
        tool = CONFIG_FILES.get(low) or next(v for p, v in CONFIG_PREFIXES.items() if low.startswith(p))
        yield f"existing:{LINTERS[tool]}", {"command": tool, "from": name}
    elif low == ".pre-commit-config.yaml":
        for hook in sorted(set(re.findall(r"^\s*-?\s*id:\s*([\w-]+)", text, re.M))):
            base = hook.split("-")[0]
            if base in LINTERS:
                yield f"existing:{LINTERS[base]}", {"command": base, "from": ".pre-commit-config.yaml"}
    elif low == "codeowners":
        yield "existing:review_rule", {"rules": sum(1 for line in text.splitlines()
                                                     if line.strip() and not line.lstrip().startswith("#")),
                                       "from": "CODEOWNERS"}
    if "/.github/workflows/" in f"/{rel}" or rel.startswith(".github/workflows/"):
        for cmd in sorted({m.group(1) for line in re.findall(r"^\s*(?:-\s*)?run:\s*(.+)$", text, re.M)
                           if (m := TEST_WORDS.search(line))}):
            yield "existing:test", {"command": cmd, "from": "CI workflow"}
    if low.endswith((".sh", ".bash")) and (low.startswith("test") or "/tests/" in f"/{rel}"):
        yield "existing:test", {"command": f"sh {rel}", "from": "test script"}
        lines = _lines(text, GREP_HEADING)
        if lines:
            yield "existing:template", {"headings_checked": len(lines), "lines": lines, "from": "test script"}
    if low.startswith("readme"):
        for cmd in sorted({m.group(1) for m in TEST_WORDS.finditer(text)}):
            yield "existing:test", {"command": cmd, "from": "README"}
    if low.endswith(".json") and ('"$schema"' in text[:2000] or low.endswith(".schema.json")):
        yield "existing:schema", {"from": name}
    if re.match(r"openapi\.(ya?ml|json)$", low) or re.search(r"^openapi:\s*\d", text, re.M):
        yield "existing:schema", {"from": name, "format": "openapi"}
    if low.endswith((".md", ".markdown", ".txt")) or low == "codeowners":
        tasks = _lines(text, TASK)
        musts = _lines(text, MUST_ITEM)
        if "pull_request_template" in low or tasks or musts:
            for n, line in enumerate(tasks + musts, 1):
                yield "existing:checklist", {"item": n, "line": line, "from": name}
        for m in AC_HEADING.finditer(text):
            k = "acceptance_criteria" if m.group(1).lower().startswith("acceptance") else "definition_of_done"
            yield f"existing:{k}", {"line": text.count("\n", 0, m.start()) + 1, "from": name}
        if GHERKIN.search(text):
            yield "existing:acceptance_criteria", {"scenarios": len(re.findall(r"^\s*Given\s", text, re.M)),
                                                   "from": name, "format": "gherkin"}
        if REVIEW_HEADING.search(text):
            yield "existing:review_rule", {"lines": _lines(text, REVIEW_HEADING), "from": name}
        headings = [h.strip() for h in HEADING.findall(text)]
        if headings and ("template" in low or kind == "reference" and "template" in text[:200].lower()):
            yield "existing:template", {"headings": len(headings), "digest": _digest("\n".join(headings)),
                                        "from": name}
    if kind == "example_good":
        yield "fixture:must_pass", {"from": name}
    elif kind == "example_bad":
        yield "fixture:must_fail", {"from": name}
    if kind == "solution" and low.endswith((".md", ".txt", ".prompt")):
        lines = _lines(text, SELF_CHECK)
        if lines:
            yield "claim:self_check", {"lines": lines, "from": name, "note": "a claim, never a verification"}


def files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    out = []
    for p in sorted(path.rglob("*")):
        if p.is_file() and not (set(p.relative_to(path).parts[:-1]) & SKIP_DIRS):
            out.append(p)
            if len(out) >= MAX_FILES:
                break
    return out


def inventory(path: Path, rel: str, sid: str, *, kind: str, saved: bool, first_candidate: int = 1,
              artifact: str | None = None, unit: str | None = None) -> Source:
    """One source record for the file at `path` (`rel` is its workspace path, or its name when saved)."""
    data = path.read_bytes()
    src = Source(id=sid, kind=kind, locator=f"saved:{rel}" if saved else rel,
                 digest=hashlib.sha256(data).hexdigest(), size=len(data), private=saved, artifact=artifact, unit=unit)
    if len(data) > MAX_BYTES or b"\0" in data[:8192]:
        src.kind = "other"
        return src
    text = data.decode("utf-8", errors="replace")
    n = first_candidate
    seen: set[str] = set()
    for ck, detail in _detect(path.name, rel, text, kind):
        key = json.dumps([ck, detail], sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        src.candidates.append(Candidate(id=f"c{n}", source=sid, kind=ck, detail=detail))
        n += 1
    return src
