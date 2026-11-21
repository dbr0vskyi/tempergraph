"""The engine-shipped transforms of a changelog entry (VER §2.3.4). Model-free.

A transform is a pure function over a package's files: it reads the declaration modules by syntax tree and
the model-facing text files, and rewrites only the bytes of the nodes it names, so comments, layout and line
endings stay. Each is idempotent. What a transform cannot express it leaves alone (the entry's detect rules
then still hit, and the upgrade turns the rest into an assisted item, WUP §2.4) or raises `TransformError`.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

API = "tempergraph.api"
UNIT_BUILDERS = frozenset({"Step", "Script", "Route", "Map", "Council", "Contest", "Ask", "Wait", "Subworkflow"})
PARENT_BUILDERS = {"gate": {"Gate"}, "judge": {"Judge"}, "risk": {"Risk"}, "escalation": {"Escalation"},
                   "session_options": {"SessionOptions"}, "routing": {"Routing"}, "input": {"Input"},
                   "step": set(UNIT_BUILDERS)}
SKIPPED_DIRS = frozenset({"docs", "diagram", ".git", "__pycache__", "tests", "evals"})
TEXT_SUFFIXES = frozenset({".md", ".txt"})
CAPABILITY_KEYWORDS = frozenset({"tools", "model", "views", "to", "judge_model", "alias"})


class TransformError(ValueError):
    """The change cannot be made by rule at this place; the item fails and goes to the assisted path."""


@dataclass(kw_only=True)
class Result:
    changed: list[str] = field(default_factory=list)  # package-relative files rewritten
    owner: list[dict[str, Any]] = field(default_factory=list)  # questions only the owner can answer


Edit = tuple[int, int, bytes]


def _files(root: Path, suffixes: Iterable[str]) -> list[Path]:
    want = set(suffixes)
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and not p.is_symlink() and p.suffix in want and not SKIPPED_DIRS & set(rel.parts[:-1]):
            out.append(p)
    return out


class _Module:
    """One Python file with byte offsets for its nodes and the local names of the engine's public interface."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.src = path.read_bytes()
        self.tree = ast.parse(self.src)
        self.starts = [0]
        for line in self.src.splitlines(keepends=True):
            self.starts.append(self.starts[-1] + len(line))
        self.names: dict[str, str] = {}  # local name -> public name
        self.modules: set[str] = set()  # local names bound to the interface module
        self.edits: list[Edit] = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module == API:
                for a in node.names:
                    self.names[a.asname or a.name] = a.name
            elif isinstance(node, ast.ImportFrom) and node.module == "tempergraph":
                self.modules |= {a.asname or a.name for a in node.names if a.name == "api"}
            elif isinstance(node, ast.Import):
                self.modules |= {a.asname for a in node.names if a.name == API and a.asname}

    def at(self, line: int, col: int) -> int:
        return self.starts[line - 1] + col

    def span(self, node: Any) -> tuple[int, int]:
        return self.at(node.lineno, node.col_offset), self.at(node.end_lineno, node.end_col_offset)

    def builder(self, call: ast.Call) -> str | None:
        f = call.func
        if isinstance(f, ast.Name):
            return self.names.get(f.id)
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in self.modules:
            return f.attr
        return None

    def calls(self, builders: Iterable[str]) -> list[ast.Call]:
        want = set(builders)
        return [n for n in ast.walk(self.tree) if isinstance(n, ast.Call) and self.builder(n) in want]

    def replace(self, start: int, end: int, new: str | bytes) -> None:
        self.edits.append((start, end, new.encode() if isinstance(new, str) else new))

    def save(self) -> bool:
        if not self.edits:
            return False
        out = self.src
        for start, end, new in sorted(set(self.edits), reverse=True):
            out = out[:start] + new + out[end:]
        if out == self.src:
            return False
        ast.parse(out)  # a rewrite that does not parse is never written
        self.path.write_bytes(out)
        return True


def _modules(root: Path) -> list[_Module]:
    out = []
    for p in _files(root, {".py"}):
        try:
            out.append(_Module(p))
        except (SyntaxError, ValueError):
            continue
    return out


def _finish(root: Path, mods: Iterable[_Module], res: Result) -> Result:
    for m in mods:
        if m.save():
            res.changed.append(m.path.relative_to(root).as_posix())
    res.changed = sorted(set(res.changed))
    return res


def _target(path: str) -> tuple[set[str], str]:
    """The builders whose keyword a field path names, and that keyword: `units.*.gate.x` is `x` of `Gate`."""
    parts = [p for p in path.split(".") if p]
    if not parts:
        raise TransformError("an empty field path")
    leaf, parents = parts[-1], parts[:-1]
    if not parents:
        return {"Workflow"}, leaf
    if parents[-1] in PARENT_BUILDERS:
        return set(PARENT_BUILDERS[parents[-1]]), leaf
    if parents[0] == "units" and len(parents) <= 2:
        return set(UNIT_BUILDERS), leaf
    raise TransformError(f"no builder is known for the field path {path!r}")


def _keyword(call: ast.Call, name: str) -> ast.keyword | None:
    return next((k for k in call.keywords if k.arg == name), None)


def _literal(value: Any) -> str:
    if isinstance(value, Mapping) and set(value) == {"call", "args"}:  # a builder call given as data
        args = ", ".join(f"{k}={_literal(v)}" for k, v in dict(value["args"]).items())
        return f"{value['call']}({args})"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return repr(value)


def rename_field(root: Path, *, old: str, new: str) -> Result:
    """Moves a declared value to a new field of the same builder."""
    builders, leaf = _target(old)
    builders2, leaf2 = _target(new)
    if builders != builders2:
        raise TransformError(f"{old!r} and {new!r} belong to different builders")
    mods = _modules(root)
    for m in mods:
        for call in m.calls(builders):
            kw = _keyword(call, leaf)
            if kw is None:
                continue
            if _keyword(call, leaf2) is not None:
                raise TransformError(f"{m.path.name}:{call.lineno} declares both {leaf!r} and {leaf2!r}")
            start = m.at(kw.lineno, kw.col_offset)
            m.replace(start, start + len(leaf.encode()), leaf2)
    return _finish(root, mods, Result())


def _add_keyword(m: _Module, call: ast.Call, text: str) -> None:
    if any(k.arg is None for k in call.keywords):
        raise TransformError(f"{m.path.name}:{call.lineno} passes its fields as `**`")
    close = m.span(call)[1] - 1
    i = close
    while i > 0 and m.src[i - 1:i] in (b" ", b"\t", b"\n", b"\r"):
        i -= 1
    before = m.src[i - 1:i]
    if before == b"(":
        m.replace(i, i, text)
    elif before == b",":
        m.replace(i, i, f" {text}" + ("," if i != close else ""))
    else:
        m.replace(i, i, f", {text}")


def set_field(root: Path, *, path: str, value: Any) -> Result:
    """Writes an explicit value where the field is not declared, so a changed default keeps the old behaviour."""
    builders, leaf = _target(path)
    mods = _modules(root)
    for m in mods:
        for call in m.calls(builders):
            if _keyword(call, leaf) is None:
                _add_keyword(m, call, f"{leaf}={_literal(value)}")
    return _finish(root, mods, Result())


def _remove_keyword(m: _Module, call: ast.Call, kw: ast.keyword) -> None:
    start, end = m.at(kw.lineno, kw.col_offset), m.span(kw.value)[1]
    j = end
    while m.src[j:j + 1] in (b" ", b"\t"):
        j += 1
    if m.src[j:j + 1] == b",":
        j += 1
        line_start = m.src.rfind(b"\n", 0, start) + 1
        k = j
        while m.src[k:k + 1] in (b" ", b"\t"):
            k += 1
        alone = not m.src[line_start:start].strip() and m.src[k:k + 1] in (b"\n", b"\r")
        if alone:  # the keyword had its own line: the line goes with it
            k += 2 if m.src[k:k + 2] == b"\r\n" else 1
            m.replace(line_start, k, b"")
        else:
            if m.src[k:k + 1] in (b"\n", b"\r"):  # nothing follows on the line: no trailing space is left
                while m.src[start - 1:start] in (b" ", b"\t"):
                    start -= 1
            m.replace(start, k, b"")
        return
    i = start  # the last argument: the comma before it goes
    while i > 0 and m.src[i - 1:i] in (b" ", b"\t", b"\n", b"\r"):
        i -= 1
    if m.src[i - 1:i] == b",":
        i -= 1
    else:
        i = start
    m.replace(i, end, b"")


_MISSING = object()


def drop_field(root: Path, *, path: str, default: Any = _MISSING) -> Result:
    """Removes a retired field whose value equals its default; any other value stays for a person."""
    builders, leaf = _target(path)
    mods = _modules(root)
    for m in mods:
        for call in m.calls(builders):
            kw = _keyword(call, leaf)
            if kw is None:
                continue
            if default is not _MISSING:
                try:
                    same = ast.literal_eval(kw.value) == default
                except (ValueError, SyntaxError):
                    same = False
                if not same:
                    continue
            _remove_keyword(m, call, kw)
    return _finish(root, mods, Result())


def rename_symbol(root: Path, *, old: str, new: str) -> Result:
    """Rewrites an import and every use of a name of the public interface."""
    mods = _modules(root)
    for m in mods:
        plain = False
        for node in ast.walk(m.tree):
            if isinstance(node, ast.ImportFrom) and node.module == API:
                for a in node.names:
                    if a.name == old:
                        start = m.at(a.lineno, a.col_offset)
                        m.replace(start, start + len(old.encode()), new)
                        plain = plain or a.asname is None
            elif isinstance(node, ast.Attribute) and node.attr == old and isinstance(node.value, ast.Name) \
                    and node.value.id in m.modules:
                end = m.span(node)[1]
                m.replace(end - len(old.encode()), end, new)
        if plain:
            for node in ast.walk(m.tree):
                if isinstance(node, ast.Name) and node.id == old:
                    m.replace(*m.span(node), new)
    return _finish(root, mods, Result())


def _strings(m: _Module, inside: Iterable[ast.AST] | None = None) -> list[ast.Constant]:
    """The plain string constants of a module (not the parts of an f-string), optionally under given nodes."""
    joined = {id(v) for n in ast.walk(m.tree) if isinstance(n, ast.JoinedStr) for v in ast.walk(n)}
    roots = list(inside) if inside is not None else [m.tree]
    return [n for r in roots for n in ast.walk(r)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in joined]


def _rewrite_text(root: Path, sub: Callable[[str], str], res: Result) -> None:
    for p in _files(root, TEXT_SUFFIXES):
        try:
            raw = p.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new = sub(text)
        if new != text:
            p.write_bytes(new.encode("utf-8"))
            res.changed.append(p.relative_to(root).as_posix())


def rename_template_key(root: Path, *, old: str, new: str) -> Result:
    """Rewrites a template field in templates, briefs and inline prompt text."""
    pat = re.compile(r"\{" + re.escape(old) + r"(?=[}:.\[!])")
    res = Result()
    _rewrite_text(root, lambda t: pat.sub("{" + new, t), res)
    mods = _modules(root)
    for m in mods:
        for node in _strings(m):
            if pat.search(node.value):
                start, end = m.span(node)
                m.replace(start, end, pat.sub("{" + new, m.src[start:end].decode("utf-8")))
    return _finish(root, mods, res)


def rename_tool(root: Path, *, executor: str, old: str, new: str) -> Result:
    """Rewrites an executor's tool name where it stands alone: a whole string in a declaration, a whole word
    in model-facing text. `executor` names whose tool it is and is recorded with the entry; the hits decide
    where the name is used."""
    del executor
    pat = re.compile(r"(?<![\w.-])" + re.escape(old) + r"(?![\w-])")
    res = Result()
    _rewrite_text(root, lambda t: pat.sub(new, t), res)
    mods = _modules(root)
    for m in mods:
        for node in _strings(m):
            if node.value == old:
                start, end = m.span(node)
                m.replace(start, end, m.src[start:end].decode("utf-8").replace(old, new))
    return _finish(root, mods, res)


def map_capability(root: Path, *, old: str, new: str) -> Result:
    """Rewrites a capability name or an alias tier in the declarations: a whole string under `tools`, `model`
    and the like of a builder call."""
    mods = _modules(root)
    for m in mods:
        values = [k.value for n in ast.walk(m.tree) if isinstance(n, ast.Call) and m.builder(n)
                  for k in n.keywords if k.arg in CAPABILITY_KEYWORDS]
        for node in _strings(m, values):
            if node.value == old:
                start, end = m.span(node)
                m.replace(start, end, m.src[start:end].decode("utf-8").replace(old, new))
    return _finish(root, mods, Result())


def _import_name(m: _Module, name: str) -> None:
    if name in m.names.values():
        return
    for node in ast.walk(m.tree):
        if isinstance(node, ast.ImportFrom) and node.module == API and node.names:
            after = next((a for a in node.names if a.name > name), None)
            if after is not None:
                at = m.at(after.lineno, after.col_offset)
                m.replace(at, at, f"{name}, ")
            else:
                last = node.names[-1]
                at = m.at(last.end_lineno or last.lineno, last.end_col_offset or 0)
                m.replace(at, at, f", {name}")
            return
    raise TransformError(f"{m.path.name} does not import from {API}")


def model_list_to_escalation(root: Path) -> Result:
    """LAD §2.8: a step's `model` list becomes its first alias, with an `escalation` to the second when that
    is one tier up; any other list leaves an owner item."""
    from tempergraph.model.retire import model_list_to_escalation as rewrite

    res = Result()
    mods = _modules(root)
    for m in mods:
        for call in m.calls({"Step"}):
            kw = _keyword(call, "model")
            if kw is None or not isinstance(kw.value, (ast.List, ast.Tuple)):
                continue
            try:
                rungs = [str(v) for v in ast.literal_eval(kw.value)]
            except (ValueError, SyntaxError):
                raise TransformError(f"{m.path.name}:{kw.value.lineno} builds its model list at run time") from None
            got = rewrite(rungs)
            where = f"{m.path.relative_to(root).as_posix()}:{kw.value.lineno}"
            if got["model"] is None:
                _remove_keyword(m, call, kw)
                continue
            m.replace(*m.span(kw.value), _literal(got["model"]))
            if got["escalation"]:
                if _keyword(call, "escalation") is not None:
                    res.owner.append({"where": where, "question": "this step already declares an `escalation`; "
                                      f"keep it, or use `{got['escalation']['to']}`", "was": rungs})
                    continue
                _add_keyword(m, call, f"escalation=Escalation(to={_literal(got['escalation']['to'])})")
                _import_name(m, "Escalation")
            elif got["owner_item"]:
                res.owner.append({"where": where, "question": got["owner_item"], "was": rungs})
        for call in m.calls({"Workflow"}):
            kw = _keyword(call, "model_profile")
            if kw is None or not isinstance(kw.value, ast.Dict):
                continue
            for key, val in zip(kw.value.keys, kw.value.values, strict=False):
                if isinstance(val, (ast.List, ast.Tuple)):
                    try:
                        rungs = [str(v) for v in ast.literal_eval(val)]
                    except (ValueError, SyntaxError):
                        continue
                    if not rungs:
                        continue
                    m.replace(*m.span(val), _literal(rungs[0]))
                    if len(rungs) > 1:
                        name = ast.literal_eval(key) if key is not None else "?"
                        res.owner.append({"where": f"{m.path.relative_to(root).as_posix()}:{val.lineno}",
                                          "question": f"`model_profile.{name}` was a list; a profile holds one "
                                                      "alias, so choose an `escalation.to` on the step, or none",
                                          "was": rungs})
    return _finish(root, mods, res)


TRANSFORMS: dict[str, Callable[..., Result]] = {
    "rename_field": rename_field, "set_field": set_field, "drop_field": drop_field,
    "rename_symbol": rename_symbol, "rename_template_key": rename_template_key, "rename_tool": rename_tool,
    "map_capability": map_capability, "model_list_to_escalation": model_list_to_escalation,
}
PARAMETERS = {"rename_field": {"from": "old", "to": "new"}, "rename_symbol": {"from": "old", "to": "new"},
              "rename_template_key": {"from": "old", "to": "new"}, "map_capability": {"from": "old", "to": "new"},
              "rename_tool": {"from": "old", "to": "new", "executor": "executor"},
              "set_field": {"path": "path", "value": "value"}, "drop_field": {"path": "path", "default": "default"},
              "model_list_to_escalation": {}}


def apply(root: Path, migrate: Mapping[str, Any]) -> Result:
    """Run the transform a changelog entry's `migrate` names, with the parameters it carries (VER §2.3.3)."""
    name = str(migrate.get("transform") or "")
    if name not in TRANSFORMS:
        raise TransformError(f"{name!r} is not a transform of this engine")
    given = dict(migrate.get("params") or {})
    known = PARAMETERS[name]
    unknown = sorted(set(given) - set(known))
    if unknown:
        raise TransformError(f"{name} takes no parameter {unknown[0]!r}")
    try:
        return TRANSFORMS[name](root, **{known[k]: v for k, v in given.items()})
    except TypeError as exc:
        raise TransformError(f"{name}: {exc}") from exc
