"""The ask unit's questions and answers (ASK-B5 to ASK-B9): pure validation and the answers file.

A person's answers are kept in a JSON file under the thread's folder, not in graph state, so a resume that
does not complete the set never moves the graph and a crash loses nothing (ASK-AC2). The file becomes the
unit's `answers` artifact when the set is complete and the author's check passes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tempergraph.contracts import AskQuestion, AskSpec
from tempergraph.docs import write_json

MAX_QUESTIONS = 20
KINDS = ("text", "choice", "choices", "number", "bool", "file", "url")
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ITEM = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+`?([a-z0-9][a-z0-9_-]{0,63})`?\s*:\s*(.+?)\s*$")
_TRUE, _FALSE = frozenset({"true", "yes", "y", "1"}), frozenset({"false", "no", "n", "0"})


class AskFault(Exception):
    """The question list cannot be used: the unit stops before its pause (ASK-B2, ASK-B2, ASK-B9)."""


class AnswerRefused(ValueError):
    """An answer does not fit its question; nothing is written (ASK-B1)."""


def question_problems(qs: Sequence[AskQuestion]) -> list[str]:
    out: list[str] = []
    if not 1 <= len(qs) <= MAX_QUESTIONS:
        out.append(f"an ask takes 1 to {MAX_QUESTIONS} questions, not {len(qs)}")
    seen: set[str] = set()
    for q in qs:
        if not SLUG.match(q.name):
            out.append(f"question name {q.name!r} is not a slug")
        if q.name in seen:
            out.append(f"question {q.name!r} is declared twice")
        seen.add(q.name)
        if q.kind not in KINDS:
            out.append(f"question {q.name!r}: kind {q.kind!r} is not one of {', '.join(KINDS)}")
        if not q.text.strip() or len(q.text) > 500:
            out.append(f"question {q.name!r}: the text is empty or over 500 characters")
        if q.kind in ("choice", "choices") and len(q.choices) < 2:
            out.append(f"question {q.name!r}: a {q.kind} needs two or more choices")
        if q.kind not in ("choice", "choices") and q.choices:
            out.append(f"question {q.name!r}: `choices` goes with kind choice or choices")
    return out


def from_list(text: str) -> list[AskQuestion]:
    """A list artifact of questions: JSON in the `Question` shape, or Markdown with one `name: question` an item."""
    stripped = text.strip()
    if stripped.startswith("["):
        try:
            doc = json.loads(stripped)
        except ValueError as exc:
            raise AskFault(f"the question list is not JSON: {exc}") from None
        out = []
        for i, item in enumerate(doc if isinstance(doc, list) else []):
            if not isinstance(item, Mapping) or not item.get("name") or not (item.get("text") or item.get("question")):
                raise AskFault(f"question {i + 1} of the list needs a name and a text")
            out.append(AskQuestion(
                name=str(item["name"]), text=str(item.get("text") or item.get("question")),
                kind=str(item.get("kind") or "text"),  # type: ignore[arg-type]
                choices=tuple(str(c) for c in item.get("choices") or ()),
                required=bool(item.get("required", True)), default=item.get("default")))
    else:
        out = []
        for n, line in enumerate(stripped.splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = _ITEM.match(line)
            if not m:
                raise AskFault(f"line {n} of the question list is not `- name: question`")
            out.append(AskQuestion(name=m.group(1), text=m.group(2)))
    problems = question_problems(out)
    if problems:
        raise AskFault(problems[0])
    return out


def questions(ask: AskSpec, state: Mapping[str, Any], workdir: Path) -> list[AskQuestion]:
    """The unit's questions at entry: declared, or read from the artifact `questions_from` names."""
    if ask.questions_from is None:
        return list(ask.questions)
    pointer = next((arts[ask.questions_from] for arts in (state.get("artifacts") or {}).values()
                    if isinstance(arts, Mapping) and ask.questions_from in arts), None)
    if pointer is None:
        raise AskFault(f"artifact {ask.questions_from!r} is missing")
    try:
        text = (workdir / str(pointer)).read_text(encoding="utf-8")
    except OSError:
        raise AskFault(f"artifact {ask.questions_from!r} cannot be read at {pointer}") from None
    return from_list(text)


def to_json(q: AskQuestion) -> dict[str, Any]:
    return {"name": q.name, "text": q.text, "kind": q.kind, "choices": list(q.choices), "required": q.required,
            "default": q.default}


def of_json(d: Mapping[str, Any]) -> AskQuestion:
    return AskQuestion(name=str(d["name"]), text=str(d.get("text") or ""), kind=d.get("kind") or "text",
                       choices=tuple(d.get("choices") or ()), required=bool(d.get("required", True)),
                       default=d.get("default"))


def parse(q: AskQuestion, raw: Any, workdir: Path | None = None) -> Any:
    """One answer as its question's kind, or `AnswerRefused` naming what is allowed."""
    text = raw if isinstance(raw, str) else json.dumps(raw) if isinstance(raw, (list, dict)) else str(raw)
    text = text.strip()
    if q.kind == "text":
        if not text:
            raise AnswerRefused(f"{q.name}: an empty answer")
        return text
    if q.kind == "choice":
        if text not in q.choices:
            raise AnswerRefused(f"{q.name}: {text!r} is not one of {', '.join(q.choices)}")
        return text
    if q.kind == "choices":
        picked = [str(x).strip() for x in raw] if isinstance(raw, list) else [p.strip() for p in text.split(",")]
        picked = [p for p in picked if p]
        bad = [p for p in picked if p not in q.choices]
        if bad or not picked:
            raise AnswerRefused(f"{q.name}: {', '.join(bad) or 'nothing'} is not among {', '.join(q.choices)}")
        return list(dict.fromkeys(picked))
    if q.kind == "number":
        try:
            return int(text) if re.fullmatch(r"[+-]?\d+", text) else float(text)
        except ValueError:
            raise AnswerRefused(f"{q.name}: {text!r} is not a number") from None
    if q.kind == "bool":
        if isinstance(raw, bool):
            return raw
        if text.lower() in _TRUE | _FALSE:
            return text.lower() in _TRUE
        raise AnswerRefused(f"{q.name}: {text!r} is not true or false")
    if q.kind == "url":
        if not re.fullmatch(r"https?://[^\s]+", text):
            raise AnswerRefused(f"{q.name}: {text!r} is not an http or https address")
        return text
    # file: a path inside the workspace (OVR-B12)
    p = Path(text)
    if not text or p.is_absolute() or ".." in p.parts:
        raise AnswerRefused(f"{q.name}: a file answer is a path inside the workspace")
    if workdir is not None and not (workdir / p).resolve().is_relative_to(workdir.resolve()):
        raise AnswerRefused(f"{q.name}: a file answer is a path inside the workspace")
    return text


def accept(qs: Sequence[AskQuestion], given: Mapping[str, Any], workdir: Path | None = None) -> dict[str, Any]:
    """Every given answer validated by kind; one bad answer refuses the whole resume."""
    by_name = {q.name: q for q in qs}
    out: dict[str, Any] = {}
    for name, raw in given.items():
        if name not in by_name:
            raise AnswerRefused(f"{name}: not a question of this ask ({', '.join(by_name)})")
        out[name] = parse(by_name[name], raw, workdir)
    return out


def unanswered(qs: Sequence[AskQuestion], answers: Mapping[str, Any], *, defaults: bool) -> list[str]:
    """Required questions with no answer; with `defaults`, a declared default counts as one."""
    return [q.name for q in qs if q.required and q.name not in answers and not (defaults and q.default is not None)]


def complete(qs: Sequence[AskQuestion], answers: Mapping[str, Any]) -> dict[str, Any]:
    """The answers with each unanswered question's default filled in."""
    out = dict(answers)
    for q in qs:
        if q.name not in out and q.default is not None:
            out[q.name] = q.default
    return out


def check_problems(ask: AskSpec, answers: Mapping[str, Any]) -> list[str]:
    """The author's pure check over the answers: a list of problems, empty when they pass."""
    if ask.check is None:
        return []
    try:
        got = ask.check.resolve()(dict(answers))
    except Exception as exc:  # noqa: BLE001 - a check that raises does not pass
        return [f"the answers check raised {type(exc).__name__}"]
    if got is None or got is True:
        return []
    if got is False:
        return ["the answers check did not pass"]
    return [str(x) for x in ([got] if isinstance(got, str) else got)]


def answers_path(run_folder: Path, unit: str) -> Path:
    return run_folder / "answers" / f"{unit}.json"


def load(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    got = doc.get("answers") if isinstance(doc, dict) else None
    return dict(got) if isinstance(got, dict) else {}


def store(path: Path, unit: str, answers: Mapping[str, Any], *, done: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(path, {"schema_version": 1, "unit": unit, "complete": done, "answers": dict(answers)})


def shown(qs: Sequence[AskQuestion], answers: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The pause payload's question list: kind, choices, default and whether it is answered (ASK-B8)."""
    return [{**to_json(q), "answered": q.name in answers} for q in qs]
