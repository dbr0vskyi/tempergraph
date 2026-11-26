"""Task i173: the independent review unit (IRV-B1 to IRV-B14), its findings document (RVF-B1 to RVF-B7) and the
description's list of findings that block nothing (PRD-B9).

Phase 1 holds the model-free parts: the findings document, the change and the criteria handed to the reader, the
choice of the step a blocking finding goes back to, and the checks of the session record."""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from tempergraph.constants import ExitCode
from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
review = importlib.import_module("tgwf_temperspec.review")
checks = importlib.import_module("tgwf_temperspec.checks")

DRAFT = ".tempergraph/review/findings.md"


def _doc(*items: str, earlier: tuple[str, ...] = ()) -> str:
    body = "\n".join(items) if items else ""
    text = f"# Review: i1\n\n## Findings\n\n{body}\n"
    if earlier:
        text += "\n## Earlier review\n\n" + "\n".join(earlier) + "\n"
    return text


def _work(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("".join(f"line {i}\n" for i in range(1, 51)))
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "a.spec.md").write_text("one\ntwo\n")
    return tmp_path


def _problems(tmp_path: Path, text: str) -> list[tuple[str, str]]:
    return review.form_problems(text, _work(tmp_path))


def _places(problems: list[tuple[str, str]]) -> list[str]:
    return [place for place, _ in problems]


# -- the findings document (RVF-B2 to RVF-B5) ----------------------------------------------------------------------


def test_a_finding_is_written_as_one_numbered_item() -> None:
    # AC 3, RVF-AC2 (RVF-B2)
    blocking = review.Finding(1, "src/a.py", 42, "blocking", "the loop never ends when every source fails")
    assert review.format_finding(blocking) == "1. `src/a.py:42` blocking: the loop never ends when every source fails"
    quiet = review.Finding(2, "docs/a.spec.md", 7, "not blocking", "the sentence can be read two ways")
    assert review.format_finding(quiet) == "2. `docs/a.spec.md:7` not blocking: the sentence can be read two ways"
    doc = review.parse_document(_doc(review.format_finding(blocking), review.format_finding(quiet)))
    assert doc.findings == [blocking, quiet]


def test_the_check_names_the_number_of_each_refused_finding(tmp_path: Path) -> None:
    # AC 3, RVF-AC3 (RVF-B3)
    items = ["1. `src/a.py:3` blocking: complete",
             "2. `:5` blocking: no file",
             "3. `src/a.py` blocking: no line",
             "4. `src/missing.py:1` blocking: the file does not exist",
             "5. `src/a.py:51` blocking: the line is past the end",
             "6. `src/a.py:4` maybe: a mark that is neither",
             "7. `src/a.py:4`: no mark",
             "8. `src/a.py:50` not blocking: the last line"]
    problems = _problems(tmp_path, _doc(*items))
    assert _places(problems) == [f"finding {n}" for n in (2, 3, 4, 5, 6, 7)]
    assert all(message for _, message in problems)


def test_a_complete_finding_passes(tmp_path: Path) -> None:
    # AC 3, RVF-AC3 (RVF-B3)
    assert _problems(tmp_path, _doc("1. `src/a.py:3` blocking: x", "2. `docs/a.spec.md:2` not blocking: y")) == []


def test_the_check_names_the_section_or_the_number_of_a_document_of_the_wrong_form(tmp_path: Path) -> None:
    # AC 3, RVF-AC4 (RVF-B4)
    assert _places(_problems(tmp_path, "# Review: i1\n\nno sections\n")) == ["Findings"]
    assert _places(_problems(tmp_path, _doc())) == ["Findings"]
    out_of_order = _doc("1. `src/a.py:1` blocking: a", "2. `src/a.py:2` blocking: b", "4. `src/a.py:3` blocking: c")
    assert _places(_problems(tmp_path, out_of_order)) == ["finding 4"]


def test_a_section_that_holds_only_none_passes(tmp_path: Path) -> None:
    # AC 3, RVF-AC5 (RVF-B5)
    assert _problems(tmp_path, _doc("None")) == []


# -- the built document (RVF-B6, RVF-B7) ---------------------------------------------------------------------------

FIRST = _doc("1. `src/a.py:3` blocking: first", "2. `docs/a.spec.md:1` not blocking: second",
             "3. `src/a.py:9` blocking: third")
SECOND_DRAFT = "## Findings\n\n1. `src/a.py:5` blocking: still wrong\n"


def test_a_second_review_keeps_the_first_reviews_findings_as_given() -> None:
    # AC 3, AC 8, RVF-AC6 (RVF-B6)
    built = review.parse_document(review.build_document("i1", SECOND_DRAFT, FIRST, built=True))
    assert [f.text for f in built.findings] == ["still wrong"]
    assert [(f.number, f.file, f.line, f.mark, f.text) for f in built.earlier] == [
        (1, "src/a.py", 3, "blocking", "first"), (2, "docs/a.spec.md", 1, "not blocking", "second"),
        (3, "src/a.py", 9, "blocking", "third")]


def test_each_blocking_finding_of_the_first_review_ends_with_the_visits_result() -> None:
    # AC 8, RVF-AC7 (RVF-B7)
    for built, word in ((True, "built"), (False, "refused")):
        text = review.build_document("i1", SECOND_DRAFT, FIRST, built=built)
        earlier = text.split("## Earlier review", 1)[1].splitlines()
        items = [line for line in earlier if line[:1].isdigit()]
        assert [line.endswith(f"Visit: {word}") for line in items] == [True, False, True]
        assert "Visit:" not in text.split("## Earlier review", 1)[0]


def test_a_first_review_has_no_earlier_section() -> None:
    # AC 3, RVF-AC6 (RVF-B6)
    text = review.build_document("i1", SECOND_DRAFT, None, built=True)
    assert "Earlier review" not in text and "1. `src/a.py:5` blocking: still wrong" in text


# -- the change and the criteria handed to the reader (IRV-B3, IRV-B4) ---------------------------------------------


def _git(work: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=work, check=True,
                   capture_output=True)


def _commit(work: Path, subject: str, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        path = work / rel
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", subject)


TRIAGE = """# Triage: i1

## Task

Something.

## Acceptance criteria

1. A request is refused
2. A retry is served
3. The list is sorted

## Gaps

- G1 spec gap: secretgap. Searched: nothing. Owner decision

## Owner decisions

- G1: secretquestion?
  - Options: a) x; b) y
  - Default: a
  - If wrong: nothing

## Route

- Deliver: code
- Route: plan
"""


def _run(tmp_path: Path) -> Path:
    work = tmp_path / "repo"
    work.mkdir()
    _git(work, "init", "-q")
    _commit(work, "init", {"README.md": "r\n", "src/gone.py": "x\n", "docs/specs/a.spec.md": "one\n"})
    _commit(work, "docs(temperspec): prepare for i1", {"CLAUDE.md": "block\n", ".claude/rules/temperspec/x.rule.md": "r\n"})
    _commit(work, "docs(temperspec): triage for i1", {"docs/tasks/i1.triage.md": TRIAGE})
    _commit(work, "docs(temperspec): plan for i1", {"docs/plans/i1.plan.md": "plan\n", "docs/tasks/i1.handoff.md": "h\n"})
    _commit(work, "feat(temperspec): code for i1", {
        "src/new.py": "def f():\n    return 1\n", "tests/test_new.py": "def test_f():\n    pass\n",
        "docs/specs/a.spec.md": "one\ntwo\n", "src/gone.py": None, "docs/tasks/i1.report.md": "report\n",
        "CLAUDE.md": "block\nmore\n"})
    return work


def test_the_change_holds_the_runs_files_and_no_hand_over_document(tmp_path: Path) -> None:
    # AC 2, IRV-AC3 (IRV-B3)
    work = _run(tmp_path)
    changed = review.write_inputs(work, "i1", "docs/tasks/i1.triage.md")
    diff = (work / ".tempergraph" / "review" / "change.diff").read_text()
    for held in ("src/new.py", "tests/test_new.py", "docs/specs/a.spec.md", "src/gone.py"):
        assert held in diff and held in changed
    for refused in ("i1.triage.md", "i1.plan.md", "i1.handoff.md", "i1.report.md", "CLAUDE.md", "x.rule.md"):
        assert refused not in diff and not any(refused in p for p in changed)
    assert "deleted file" in diff
    assert (work / ".tempergraph" / "review" / ".gitignore").read_text().strip() == "*"


def test_a_review_after_a_trip_back_holds_the_commits_of_both_visits(tmp_path: Path) -> None:
    # AC 2, IRV-AC3 (IRV-B3)
    work = _run(tmp_path)
    _commit(work, "docs(temperspec): independent_review for i1", {"docs/tasks/i1.review.md": "# Review\n"})
    _commit(work, "feat(temperspec): code for i1", {"src/new.py": "def f():\n    return 2\n", "src/second.py": "y = 2\n"})
    review.write_inputs(work, "i1", "docs/tasks/i1.triage.md")
    diff = (work / ".tempergraph" / "review" / "change.diff").read_text()
    assert "return 2" in diff and "src/second.py" in diff and "tests/test_new.py" in diff
    assert "i1.review.md" not in diff


def test_the_criteria_file_holds_the_numbered_criteria_and_nothing_else_of_the_note(tmp_path: Path) -> None:
    # AC 2, IRV-AC4 (IRV-B4)
    work = _run(tmp_path)
    review.write_inputs(work, "i1", "docs/tasks/i1.triage.md")
    text = (work / ".tempergraph" / "review" / "criteria.md").read_text()
    for line in ("1. A request is refused", "2. A retry is served", "3. The list is sorted"):
        assert line in text
    for refused in ("secretgap", "secretquestion", "G1", "Owner", "Route"):
        assert refused not in text


# -- the step a blocking finding goes back to, and the reason (IRV-B9 to IRV-B11) ----------------------------------

MIXED = [review.Finding(1, "src/a.py", 3, "blocking", "first wrong"),
         review.Finding(2, "src/b.py", 4, "not blocking", "quiet one"),
         review.Finding(3, "docs/c.spec.md", 9, "blocking", "third wrong")]


def test_blocking_findings_on_changed_files_go_back_to_the_code_step() -> None:
    # AC 4, IRV-AC9 (IRV-B9)
    changed = ["src/a.py", "docs/c.spec.md", "tests/test_a.py"]  # a spec the change edited counts
    assert review.choose_step(MIXED, changed) == "code"
    assert review.choose_step([MIXED[1]], []) == ""  # nothing blocks, no step


def test_a_blocking_finding_on_an_untouched_file_goes_back_to_the_plan_step() -> None:
    # AC 4, IRV-AC10 (IRV-B10)
    assert review.choose_step(MIXED, ["src/a.py"]) == "plan"
    assert review.choose_step([MIXED[0]], ["src/other.py"]) == "plan"


def test_the_reason_holds_the_blocking_findings_in_order_and_no_other() -> None:
    # AC 2, AC 4, IRV-AC11 (IRV-B11)
    reason = review.reason_text(MIXED)
    assert reason.index("src/a.py:3") < reason.index("docs/c.spec.md:9")
    assert "1." in reason and "3." in reason and "first wrong" in reason and "third wrong" in reason
    assert "quiet one" not in reason and "src/b.py" not in reason


# -- the checks of the session record (IRV-B6, IRV-B7) ---------------------------------------------------------------


def _call(capability: str, target: str | None, ok: bool = True) -> dict[str, Any]:
    names = {"read": "Read", "search": "Grep", "edit": "Edit", "write": "Write"}
    return {"name": names[capability], "capability": capability, "target": target, "ok": ok}


def _ctx(tmp_path: Path, session: list[dict[str, Any]] | None) -> CheckContext:
    work = _work(tmp_path)
    (work / "docs" / "tasks").mkdir(parents=True, exist_ok=True)
    (work / "docs" / "tasks" / "i1.review.md").write_text(_doc("None"))
    return CheckContext(unit="independent_review", workdir=work, request={"task_id": "i1"}, values={},
                        artifacts={"independent_review": {"findings": "docs/tasks/i1.review.md"}},
                        git=GitFacts(), allow=SPEC.allow_commands, out_dir=tmp_path.parent / f"{tmp_path.name}.out",
                        deadline_at=time.monotonic() + 60, session=None if session is None else tuple(session),
                        visit_session=None if session is None else tuple(session))


def _found(ctx: CheckContext, criterion: str) -> list[Any]:
    return [f for f in checks.review_check(ctx).findings if f.criterion == criterion]


def test_a_session_that_opened_a_hand_over_document_fails_naming_it(tmp_path: Path) -> None:
    # AC 1, AC 2, IRV-AC6 (IRV-B6)
    opened = [_call("read", "docs/plans/i1.plan.md"), _call("search", "docs/tasks/i1.handoff.md")]
    found = _found(_ctx(tmp_path / "a", opened), "ts-rev-session")
    failing = [f for f in found if f.status == "fail"]
    assert len(failing) == 1 and "plan" in failing[0].message and "i1.plan.md" in failing[0].place
    searched = [_call("search", "docs/plans/i1.plan.md"), _call("read", "src/a.py"), _call("read", "docs/plans/i1.plan.md", ok=False)]
    assert not [f for f in _found(_ctx(tmp_path / "b", searched), "ts-rev-session") if f.status == "fail"]
    assert [f.status for f in _found(_ctx(tmp_path / "c", None), "ts-rev-session")] == ["n_a"]


def test_a_session_that_changed_a_file_other_than_the_draft_fails_naming_it(tmp_path: Path) -> None:
    # AC 1, IRV-AC7 (IRV-B7)
    wrote = [_call("write", DRAFT), _call("edit", "src/a.py")]
    failing = [f for f in _found(_ctx(tmp_path / "a", wrote), "ts-rev-session") if f.status == "fail"]
    assert len(failing) == 1 and "src/a.py" in failing[0].place
    only = [_call("write", DRAFT), _call("write", str(tmp_path / "b" / DRAFT))]
    assert not [f for f in _found(_ctx(tmp_path / "b", only), "ts-rev-session") if f.status == "fail"]


# -- fixture runs on the loaded workflow (IRV-B1, IRV-B2, IRV-B5, IRV-B8 to IRV-B14, RVF-B1) -------------------------------
#
# The routing is the engine's own, run on the loaded package; the sessions are stand-ins, every gate check but the
# review's own passes, and the judge of the review reads the committed findings document as the real judge would.

TASK = "I-1"
NOTE = ("# Triage: I-1\n\n## Task\n\nA task.\n\n## Acceptance criteria\n\n1. A thing\n\n## Existing documents\n\n- None\n\n"
        "## Gaps\n\n- G1 spec gap: idle expiry. Searched `docs/specs/` for \"idle\": nothing. Findable\n\n"
        "## Owner decisions\n\nNone\n\n## Route\n\n- Deliver: code\n- Route: {route}\n")
PLAN_TEXT = "PLAN-SENTINEL a plan the reader may never see"
HANDOFF_TEXT = "HANDOFF-SENTINEL a hand-off the reader may never see"
REPORT_TEXT = "REPORT-SENTINEL a code report the reader may never see"
ACCOUNT = "ACCOUNT-SENTINEL what the code session said of itself"
BLOCKS = "1. `src/app.py:2` blocking: the total is wrong when the list is empty"
QUIET = "2. `src/app.py:5` not blocking: a name could be clearer"
UNTOUCHED = "1. `README.md:1` blocking: the readme describes a flag that is gone"


def passes(ctx: Any) -> Any:
    from tempergraph.api import CheckResult

    return CheckResult(result="PASS", evidence="stand-in")


def ready(ctx: Any) -> dict[str, str]:
    return {"setup_ready": "yes"}


class Stand:
    """A stand-in executor that answers by the unit of the session key. `reviews` holds the lines the reader writes
    under `Findings` in each of its sessions, in order; the last holds for every session after it."""

    def __init__(self, route: str = "plan", reviews: list[list[str]] | None = None, back_to_triage: bool = False) -> None:
        from tempergraph.executors.standins import standin

        self.inner = standin("claude")
        self.name = self.inner.name
        self.route = route
        self.reviews = reviews if reviews is not None else [["None"]]
        self.back_to_triage = back_to_triage
        self.sessions: list[dict[str, Any]] = []
        self.readers: list[dict[str, str]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def units(self, kind: str = "step") -> list[str]:
        return [str(s["unit"]) for s in self.sessions if s["kind"] == kind]

    def run_step(self, req: Any, sink: Any) -> Any:
        from tempergraph.executors.standins import answer

        unit = req.session_key.split(".")[0]
        self.sessions.append({"kind": "step", "unit": unit, "prompt": req.prompt})
        work, n = Path(req.workdir), len(self.units())

        def put(rel: str, text: str) -> None:
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            (work / rel).write_text(text, encoding="utf-8")

        if unit == "triage":
            route = "quick" if self.back_to_triage and self.units().count("triage") == 1 else self.route
            put(f"docs/tasks/{TASK}.triage.md", NOTE.replace("{route}", route))
            return answer(f"Triaged.\nARTIFACT triage_note: docs/tasks/{TASK}.triage.md\n"
                          f"ARTIFACT gaps: {'none' if route == 'quick' else 'some'}\nARTIFACT route: {route}",
                          session_id=f"s-{n}")
        if unit == "discovery":
            put(f"docs/tasks/{TASK}.handoff.md", f"# Hand-off: {TASK}\n\n{HANDOFF_TEXT}\n")
            return answer(f"Closed.\nARTIFACT handoff: docs/tasks/{TASK}.handoff.md", session_id=f"s-{n}")
        if unit == "plan":
            put(f"docs/plans/{TASK}.plan.md", f"# Plan: a goal\n\n{PLAN_TEXT} {n}\n")
            return answer(f"Planned.\nARTIFACT plan: docs/plans/{TASK}.plan.md\nARTIFACT complexity: simple",
                          session_id=f"s-{n}")
        if unit == "code":
            put("src/app.py", "".join(f"value_{n} = {i}\n" for i in range(1, 9)))
            put(f"docs/tasks/{TASK}.report.md", f"# Code report\n\n{REPORT_TEXT}\n")
            return answer(f"Coded. {ACCOUNT}\nARTIFACT code_report: docs/tasks/{TASK}.report.md\n"
                          "ARTIFACT tests_passed: yes", session_id=f"s-{n}")
        if unit == "independent_review":
            folder = work / ".tempergraph" / "review"
            seen = {name: (folder / name).read_text(encoding="utf-8") if (folder / name).is_file() else ""
                    for name in ("change.diff", "criteria.md")}
            self.readers.append({"prompt": req.prompt, **seen})
            lines = self.reviews[min(len(self.readers), len(self.reviews)) - 1]
            put(".tempergraph/review/findings.md", "## Findings\n\n" + "\n".join(lines) + "\n")
            return answer("Read.", session_id=f"s-{n}")
        raise AssertionError(f"a session of {unit} that the stand-in does not answer")

    def run_judge(self, req: Any, views: Any, sink: Any) -> Any:
        from tempergraph.executors.standins import answer

        unit = req.session_key.split(".")[0]
        self.sessions.append({"kind": "judge", "unit": unit, "prompt": req.prompt})
        criteria = SPEC.units[unit].gate.criteria if unit in SPEC.units else ()
        count = len(re.findall(r"^\d+\. \[", req.prompt, re.MULTILINE)) if unit == "outcome" else max(len(criteria), 1)
        rows = [{"n": i, "status": "MET", "evidence": "stand-in", "defect_in": None, "no_change": False}
                for i in range(1, count + 1)]
        failing: dict[str, Any] | None = None
        if unit == "independent_review":
            doc = Path(req.workdir) / "docs" / "tasks" / f"{TASK}.review.md"
            blocking = [f for f in review.parse_document(doc.read_text(encoding="utf-8")).findings if f.blocking]
            step = re.search(r"go back to the `(\w+)` step", req.prompt)
            if blocking:
                assert step is not None, "the check's finding of the step reaches the judge"
                failing = {"id": "ts-rev-blockers", "evidence": review.reason_text(blocking),
                           "defect_in": "plan" if step.group(1) == "plan" else "code_report"}
        elif unit == "code" and self.back_to_triage and self.units("judge").count("code") == 1:
            failing = {"id": criteria[0].id, "evidence": "the task is larger than the quick lane", "defect_in": "triage_note"}
        if failing is not None:
            at = next((i for i, c in enumerate(criteria) if c.id == failing["id"]), 0)
            rows[at] = {"n": at + 1, "id": failing["id"], "status": "UNMET", "evidence": failing["evidence"],
                        "place": "docs/tasks", "fix": "address each point", "defect_in": failing["defect_in"],
                        "no_change": False}
        text = "Reviewed.\n```json\n" + json.dumps({"criteria": rows, "gap": False, "confidence": 0.9}) + "\n```"
        return answer(text, tools=("Read",), session_id=f"j-{unit}-{len(self.sessions)}")


def _spec() -> Any:
    """The package's spec with every gate check but the review's replaced by one that passes, `prepare` answered by a
    callable, the code step not asked for its own check run, no last stage and no check of the outcome."""
    from tempergraph.contracts import CallableRef

    units = {}
    for name, u in SPEC.units.items():
        gate = u.gate
        if gate.check is not None and name != "independent_review":
            gate = dataclasses.replace(gate, check=CallableRef(module=__name__, qualname="passes", func=passes))
        step = dataclasses.replace(u.step, self_check=False) if u.step is not None and name == "code" else u.step
        units[name] = dataclasses.replace(u, gate=gate, step=step)
    script = dataclasses.replace(SPEC.units["prepare"].script, run=None,
                                 call=CallableRef(module=__name__, qualname="ready", func=ready))
    units["prepare"] = dataclasses.replace(units["prepare"], script=script)
    assert SPEC.outcome is not None
    return dataclasses.replace(SPEC, units=units, outcome=dataclasses.replace(SPEC.outcome, check=None),
                               finalizer=None, finalizer_outcomes=())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "Test")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "README.md").write_text("scratch\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)
    return root


def _go(repo: Path, stand: Stand) -> Any:
    from tempergraph.executors.registry import Registry
    from tempergraph.run.runner import RunSettings, start

    registry = Registry()
    registry.register(stand)
    out = start(_spec(), TASK, {"request": "x"}, repo, registry,
                RunSettings(sleep=lambda s: None, flags={"code_mode.arm": "single"}))
    return out


def _records(repo: Path, kind: str) -> list[dict[str, Any]]:
    from tempergraph.store.layout import run_dir, state_root_path

    path = run_dir(state_root_path(repo), SPEC.name, TASK) / "run.jsonl"
    return [r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r["kind"] == kind]


def _git_out(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _after(stand: Stand, unit: str, n: int = 1) -> list[str]:
    """The step units started after the n-th session of `unit`."""
    steps = stand.units()
    at = [i for i, u in enumerate(steps) if u == unit][n - 1]
    return steps[at + 1:]


def _outcome_gates(repo: Path) -> list[dict[str, Any]]:
    return [r for r in _records(repo, "gate") if r.get("unit") == "outcome"]


def _load_code_mode_tests() -> Any:
    here = str(ROOT / "tests")
    if here not in sys.path:
        sys.path.insert(0, here)  # the engine imports the module's check functions by name
    return importlib.import_module("test_code_mode")


# IRV-AC1 (IRV-B1), AC 1, AC 7
def test_irv_ac1_a_run_that_passes_the_code_step_enters_the_review_on_both_arms(repo: Path) -> None:
    modes = _load_code_mode_tests()
    for steps, task in ((modes.SINGLE, "S-1"), (modes.PHASES, "P-1")):
        out = modes._run(repo, steps, task=task)
        assert out.exit_code is ExitCode.FINISHED, json.dumps(out.payload, default=str)[:1500]
        # RGN-AC1 (RGN-B1): the regeneration unit follows the code step and the join follows it
        assert modes._entered(repo, task)[-4:] == ["code", "regeneration", "code_join", "independent_review"], task


def test_irv_ac1_a_documents_only_run_enters_no_review(repo: Path) -> None:
    stand = Stand(route="discovery-only")
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert "discovery" in stand.units() and "independent_review" not in stand.units() and "code" not in stand.units()


def test_irv_ac1_a_run_outside_the_quick_lane_enters_the_review_and_then_the_outcome_gate(repo: Path) -> None:
    stand = Stand()
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert stand.units()[-2:] == ["code", "independent_review"] and _outcome_gates(repo)
    steps = [r["unit"] for r in _records(repo, "gate")]
    assert steps.index("independent_review") < steps.index("outcome")


# IRV-AC2 (IRV-B2), AC 7
def test_irv_ac2_a_quick_lane_run_starts_no_reader_session_and_enters_the_outcome_gate_next(repo: Path) -> None:
    """The outcome gate runs after the regeneration unit (RGN-B1)."""
    stand = Stand(route="quick")
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert "independent_review" not in stand.units() and "independent_review" not in stand.units("judge")
    steps = [r["unit"] for r in _records(repo, "gate")]
    assert steps[-1] == "outcome" and "independent_review" not in steps
    assert steps.index("regeneration") < steps.index("outcome")  # RGN-AC1: the unit's gate comes before the outcome gate


def test_irv_ac2_a_run_sent_back_to_triage_and_routed_to_the_plan_step_takes_the_review(repo: Path) -> None:
    stand = Stand(route="plan", back_to_triage=True)
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert stand.units()[:3] == ["triage", "code", "triage"] and stand.units().count("triage") == 2
    assert "plan" in stand.units() and stand.units()[-1] == "independent_review"


# IRV-AC5 (IRV-B5), AC 2
def test_irv_ac5_the_readers_prompt_and_values_hold_nothing_of_the_runs_other_outputs(repo: Path) -> None:
    stand = Stand(reviews=[[BLOCKS], ["None"]])
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert len(stand.readers) == 2, "a second review follows the trip back, with the first review's findings on the branch"
    forbidden = (PLAN_TEXT, HANDOFF_TEXT, REPORT_TEXT, ACCOUNT, "the total is wrong", "Visit:", "SENTINEL",
                 ".plan.md", ".handoff.md", ".report.md", ".triage.md", ".setup.md", ".review.md", "Earlier review")
    for held in stand.readers:
        for name in ("prompt", "change.diff", "criteria.md"):
            for text in forbidden:
                assert text not in held[name], (name, text)
        assert ".tempergraph/review/change.diff" in held["prompt"] and ".tempergraph/review/criteria.md" in held["prompt"]
        assert ".tempergraph/review/findings.md" in held["prompt"]
    assert "value_" in stand.readers[0]["change.diff"] and "A thing" in stand.readers[0]["criteria.md"]


# IRV-AC8 (IRV-B8), AC 4
def test_irv_ac8_the_prompt_states_the_blocking_rule_and_the_unit_has_no_shell() -> None:
    prompt = " ".join((ROOT / "prompts" / "independent_review.md").read_text(encoding="utf-8").lower().split())
    for kind in ("wrong or missing result", "failure", "hang", "loss of data", "break of earlier behaviour"):
        assert kind in prompt, kind
    assert "every other finding" in prompt and "not blocking" in prompt and "name that could be clearer" in prompt
    step = SPEC.units["independent_review"].step
    assert step is not None and set(step.tools) == {"read", "search", "list", "write"}
    assert not step.commands and "shell" not in step.tools
    assert [s.call.qualname for s in step.before] == ["review_before"]


# IRV-AC9 to IRV-AC11 (IRV-B9 to IRV-B11), AC 4, AC 9
def test_irv_ac9_a_planted_defect_in_a_changed_file_sends_the_run_back_to_the_code_step(repo: Path) -> None:
    stand = Stand(reviews=[[BLOCKS, QUIET], ["None"]])
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert _after(stand, "independent_review")[:2] == ["code", "independent_review"]
    assert "plan" not in _after(stand, "independent_review")
    prompt = next(s["prompt"] for s in stand.sessions[::-1] if s["kind"] == "step" and s["unit"] == "code")
    assert "`src/app.py:2`" in prompt and "the total is wrong when the list is empty" in prompt
    assert "a name could be clearer" not in prompt  # IRV-AC11: no finding that is not blocking


@pytest.mark.parametrize("lines", [[UNTOUCHED], ["1. `src/app.py:2` blocking: wrong", "2. `README.md:1` blocking: stale"]])
def test_irv_ac10_a_blocking_finding_on_an_untouched_file_sends_the_run_back_to_the_plan_step(
        repo: Path, lines: list[str]) -> None:
    stand = Stand(reviews=[lines, ["None"]])
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert _after(stand, "independent_review")[0] == "plan", lines
    prompt = next(s["prompt"] for s in stand.sessions[::-1] if s["kind"] == "step" and s["unit"] == "plan")
    assert "`README.md:1`" in prompt


def test_irv_ac11_the_reason_holds_the_blocking_findings_in_order_with_number_file_line_and_text(repo: Path) -> None:
    lines = ["1. `src/app.py:2` blocking: first wrong", "2. `src/app.py:5` not blocking: quiet", "3. `src/app.py:7` blocking: third wrong"]
    stand = Stand(reviews=[lines, ["None"]])
    assert _go(repo, stand).exit_code is ExitCode.FINISHED
    prompt = next(s["prompt"] for s in stand.sessions[::-1] if s["kind"] == "step" and s["unit"] == "code")
    first, third = prompt.index("1. `src/app.py:2` first wrong"), prompt.index("3. `src/app.py:7` third wrong")
    assert first < third and "quiet" not in prompt


# IRV-AC14 (IRV-B14), AC 9
@pytest.mark.parametrize("lines", [["None"], ["1. `src/app.py:3` not blocking: a name could be clearer"]])
def test_irv_ac14_a_clean_change_and_a_change_with_only_findings_that_block_nothing_pass_with_no_trip_and_no_pause(
        repo: Path, lines: list[str]) -> None:
    stand = Stand(reviews=[lines])
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert stand.units().count("independent_review") == 1 and stand.units().count("code") == 1
    assert not _records(repo, "pause")


# IRV-AC12, IRV-AC13 (IRV-B12, IRV-B13), AC 5
SECOND = ["1. `src/app.py:2` blocking: still wrong", "2. `README.md:1` blocking: also stale",
          "3. `src/app.py:6` not blocking: a name could be clearer"]


@pytest.mark.parametrize("first", [[BLOCKS], [UNTOUCHED]])
def test_irv_ac12_a_run_sent_back_once_is_sent_back_by_its_second_review_to_neither_step(
        repo: Path, first: list[str]) -> None:
    stand = Stand(reviews=[first, SECOND])
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert len(stand.readers) == 2
    assert _after(stand, "independent_review", 2) == [], "no step starts after the second review"


def test_irv_ac13_a_second_blocking_review_pauses_and_shows_the_blocking_findings_left(repo: Path) -> None:
    stand = Stand(reviews=[[BLOCKS], SECOND])
    out = _go(repo, stand)
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert out.payload["kind"] == "budget", out.payload
    shown = json.dumps(out.payload)
    assert "`src/app.py:2` still wrong" in shown and "`README.md:1` also stale" in shown
    assert shown.index("src/app.py:2") < shown.index("README.md:1")
    assert "a name could be clearer" not in shown


# RVF-AC1 (RVF-B1), AC 3
def test_rvf_ac1_the_findings_document_is_committed_beside_the_triage_note(repo: Path) -> None:
    stand = Stand(reviews=[["1. `src/app.py:2` not blocking: a name could be clearer"]])
    assert _go(repo, stand).exit_code is ExitCode.FINISHED
    work = repo.parent / "repo.worktrees" / f"temperspec--{TASK}"  # the run's own worktree
    assert (work / "docs" / "tasks" / f"{TASK}.review.md").is_file()
    assert f"docs/tasks/{TASK}.review.md" in _git_out(work, "ls-tree", "-r", "--name-only", "HEAD")
    assert _git_out(work, "status", "--porcelain", "--untracked-files=all", "--", ".", ":(exclude).tempergraph") == ""


# -- the documents show the unit (AC 1, AC 10) ---------------------------------------------------------------------


def _ids(spec: str, prefix: str) -> tuple[set[str], set[str]]:
    text = (ROOT / "docs" / "specs" / spec).read_text()
    return (set(re.findall(rf"^### ({prefix}-B\d+) ", text, re.MULTILINE)), set(re.findall(rf"^- ({prefix}-AC\d+) ", text, re.MULTILINE)))


def test_the_specs_define_each_behaviour_with_a_criterion_and_the_documents_show_the_unit() -> None:
    # IRV-AC1, RVF-AC1 (AC 1, AC 10)
    for spec, prefix, count in (("independent-review.spec.md", "IRV", 14), ("review-findings.spec.md", "RVF", 7),
                                ("pull-request-description.spec.md", "PRD", 9)):
        behaviours, criteria = _ids(spec, prefix)
        assert behaviours == {f"{prefix}-B{n}" for n in range(1, count + 1)}, spec
        text = (ROOT / "docs" / "specs" / spec).read_text()
        named = set(re.findall(rf"^- {prefix}-AC\d+ \(([^)]*)\)", text, re.MULTILINE))
        assert criteria and {b for group in named for b in re.findall(rf"{prefix}-B\d+", group)} >= behaviours, spec
    outcome = json.loads((ROOT / "outcome.json").read_text())
    assert outcome["revision"] > 23
    ids = set(re.findall(r"ts-rev-[a-z]+", json.dumps(outcome)))
    assert {"ts-rev-form", "ts-rev-session", "ts-rev-commit", "ts-rev-step", "ts-rev-blockers"} <= ids
    for doc in ("docs/specs/overview.spec.md", "README.md", "diagram/workflow.md"):
        assert "independent_review" in (ROOT / doc).read_text(), doc
    blueprint = json.loads((ROOT / "blueprint.json").read_text())
    assert "independent_review" in json.dumps(blueprint)
