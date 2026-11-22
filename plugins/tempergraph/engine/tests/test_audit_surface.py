"""The session surface of the tool audit (TSA-B6, TSA-B7; TSA-AC3, TSA-AC4, PRA-AC3): one session per step and judge,
built from the executors' tool maps, the declared commands and the manifest, with the need read by prompt lint's name
reader, the use and the refusal classes from recorded tool names and scrubbed input summaries only."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tempergraph.audit import prompts, surface
from tempergraph.audit.surface import build_surface, classify_refusal
from tempergraph.executors.capabilities import DECLARED
from tempergraph.model import prompt_lint

from .test_audit import clean_step, wf
from .test_audit_history import many, read, write_run

PROMPT = "Write the notes for {request} into notes. Use `Grep` to search, then write the notes."


def spec(**kw: object):  # type: ignore[no-untyped-def]
    return wf({"draft": clean_step(prompt=PROMPT, tools=["read", "search", "shell"], commands=["pytest"], **kw)},
              allow_commands=["pytest"])


def names_to_capabilities(executor: str, session: surface.SessionSurface) -> dict[str, str]:
    """Map an executor's tool names back to the engine's capabilities (a name that two capabilities share maps once)."""
    reverse = {name: cap for cap, names in DECLARED[executor].tool_map.items() for name in names}
    return {reverse.get(n, n): n for n in session.granted}


@pytest.mark.parametrize("executor", sorted(DECLARED))
def test_each_executors_surface_comes_from_its_tool_map(executor: str) -> None:
    """TSA-AC4 (TSA-B3, TSA-B8, TSA-B6): the surface is built from the tool map, the declared commands and the
    manifest alone: no run record is read."""
    got = build_surface(spec(), DECLARED, None, None, executor=executor)
    (step,) = [s for s in got.sessions if s.role == "step"]
    tool_map = DECLARED[executor].tool_map
    assert step.executor == executor and step.session == "draft"
    assert set(step.granted) == {t for cap in ("read", "search", "shell") for t in tool_map[cap]}
    assert step.commands == ("pytest",) and step.used is None
    assert step.enforced is DECLARED[executor].enforces_step_tools


def test_the_four_executors_differ_only_in_tool_names() -> None:
    """TSA-AC4 (TSA-B3): after mapping names back to capabilities the surfaces are the same."""
    seen = {}
    for executor in DECLARED:
        (step,) = [s for s in build_surface(spec(), DECLARED, None, None, executor=executor).sessions
                   if s.role == "step"]
        seen[executor] = ({cap: step.granted[name] for cap, name in names_to_capabilities(executor, step).items()},
                          step.commands)
    capabilities = {frozenset(c) for c, _ in seen.values()}
    assert capabilities == {frozenset({"read", "search", "shell"})}
    assert {cmds for _, cmds in seen.values()} == {("pytest",)}
    claude = build_surface(spec(), DECLARED, None, None, executor="claude").sessions[0]
    assert claude.granted["Bash"] == "shell"
    messages = build_surface(spec(), DECLARED, None, None, executor="messages-api").sessions[0]
    assert messages.granted["run_command"] == "shell"


def test_a_judge_is_its_own_session_with_a_view_set() -> None:
    """TSA-B6: a judge session is listed as `<unit>:judge` with the executor after cross-executor judging."""
    got = build_surface(spec(), DECLARED, None, None, executor="claude")
    judge = next(s for s in got.sessions if s.role == "judge")
    assert judge.session == "draft:judge" and judge.executor == "claude"
    assert "Read" in judge.granted and "Bash" not in judge.granted


def test_a_recorded_tool_the_map_does_not_know_is_ambient(tmp_path: Path) -> None:
    """TSA-AC4 (TSA-B6): a recorded `session_started.tools` name outside `granted`, unknown to the map or not, is
    `ambient`."""
    many(tmp_path, 2, attempts=[{"tools_started": ["Read", "Grep", "Glob", "mcp__monitor__status"],
                                 "judge": {"tools_started": ["Read", "mcp__monitor__status"]}}])
    got = build_surface(wf({"draft": clean_step(tools=["read", "search"])}), DECLARED, None, read(tmp_path),
                        executor="claude")
    step = next(s for s in got.sessions if s.role == "step")
    assert step.ambient == {"Glob", "mcp__monitor__status"}
    judge = next(s for s in got.sessions if s.role == "judge")
    assert judge.ambient == {"mcp__monitor__status"}
    assert judge.ambient_runs["mcp__monitor__status"] == ["t000", "t001"]


def test_used_counts_calls_and_refusals_from_history(tmp_path: Path) -> None:
    """TSA-B6: `used` is per tool name: calls, ok, refused."""
    many(tmp_path, 2, attempts=[{"calls": [{"name": "Read", "ok": True}, {"name": "Read", "ok": False}],
                                 "denied": [{"name": "Bash", "input_summary": "cat x"}]}])
    got = build_surface(spec(), DECLARED, None, read(tmp_path), executor="claude")
    step = next(s for s in got.sessions if s.role == "step")
    assert step.used["Read"] == {"calls": 4, "ok": 2, "refused": 0, "subagent": 0}
    assert step.used["Bash"]["refused"] == 2


# -- refusal classes (TSA-B7, TSA-AC3) -------------------------------------------------------------------------------


@pytest.mark.parametrize(("tool", "summary", "klass"), [
    ("Bash", "grep -rn foo src", "shell_for_read"),
    ("Bash", "cat README.md", "shell_for_read"),
    ("Bash", "sed -n 1,20p x.py", "shell_for_read"),
    ("Bash", "cd /repo && git status", "dir_change_then_command"),
    ("Bash", "cd sub; pytest", "dir_change_then_command"),
    ("Bash", "pytest /etc/passwd", "outside_workspace"),
    ("Bash", "pytest ../other", "outside_workspace"),
    ("mcp__tracker__create", "{}", "undeclared_tool"),
    ("Bash", "npm run build", "needed_command"),
    ("Bash", None, "unclassified"),
    ("Bash", "", "unclassified"),
])
def test_refusals_are_classed_from_the_tool_name_and_the_summary(tool: str, summary: str | None, klass: str) -> None:
    """TSA-AC3 (TSA-B7): the class comes from the tool name and the scrubbed input summary; `unclassified` when no
    summary was recorded."""
    got = classify_refusal(tool, summary, granted={"Read", "Grep", "Bash"}, shell={"Bash"}, file_tools=True)
    assert got == klass


def test_shell_for_read_needs_file_tools() -> None:
    """TSA-B7: `shell_for_read` is a shell read while file tools are granted."""
    assert classify_refusal("Bash", "cat x", granted={"Bash"}, shell={"Bash"}, file_tools=False) == "needed_command"


def test_refusals_of_the_surface_are_counted_per_class(tmp_path: Path) -> None:
    """TSA-B2: 7 grep calls, 4 `cd … && git` calls and 3 `npm run build` calls are sorted, not just counted."""
    denied = ([{"name": "Bash", "input_summary": "grep x ."}] * 7
              + [{"name": "Bash", "input_summary": "cd /r && git status"}] * 4
              + [{"name": "Bash", "input_summary": "npm run build"}] * 3)
    many(tmp_path, 1, attempts=[{"denied": denied}])
    step = next(s for s in build_surface(spec(), DECLARED, None, read(tmp_path), executor="claude").sessions
                if s.role == "step")
    assert step.refusals == {"shell_for_read": 7, "dir_change_then_command": 4, "needed_command": 3}


def test_refusals_without_input_summaries_are_unclassified_never_dropped(tmp_path: Path) -> None:
    """TSA-B7: refusals with no summary count as `unclassified`; a run with no journal at all reads `unclassified`."""
    many(tmp_path, 1, attempts=[{"denied": [{"name": "Bash"}] * 3}])
    step = next(s for s in build_surface(spec(), DECLARED, None, read(tmp_path), executor="claude").sessions
                if s.role == "step")
    assert step.refusals == {"unclassified": 3}
    write_run(tmp_path / "old", "t000", journal=False, attempts=[{"denied": [{"name": "Bash"}]}])
    step = next(s for s in build_surface(spec(), DECLARED, None, read(tmp_path / "old"), executor="claude").sessions
                if s.role == "step")
    assert step.refusals == "unclassified"


def test_surface_reads_no_tool_result_transcript_or_output_field() -> None:
    """TSA-AC3: a source test: the surface and the refusal classes read tool names and scrubbed input summaries only."""
    src = Path(surface.__file__).read_text(encoding="utf-8")
    for forbidden in ("tool_result", "transcript", "raw.jsonl", "output_chars", "error_tail", "last_text",
                      "last_line", "model_delta", "improve.digest", "improve.review", "from tempergraph.run"):
        assert forbidden not in src, forbidden
    assert not re.search(r"\boutput\b", src)


# -- the need is read by prompt lint's reader (PRA-AC3) ---------------------------------------------------------------


def test_the_need_is_read_by_prompt_lints_name_reader() -> None:
    """PRA-AC3: one reader serves prompt lint, the prompt audit and the tool audit."""
    assert prompts.read_names is prompt_lint.names and surface.read_names is prompts.read_names
    text = "Use `Grep` to search `skills/x/SKILL.md`, then skill `plan-review`."
    assert surface.read_names(text) == prompt_lint.names(text) == prompts.read_names(text)
    got = build_surface(spec(), DECLARED, None, None, executor="claude")
    step = next(s for s in got.sessions if s.role == "step")
    assert step.needed["Grep"].startswith("template")  # found in the step's template by the reader
    assert "Bash" not in step.needed or not step.needed["Bash"].startswith("template")


def test_the_surface_module_holds_no_second_name_pattern() -> None:
    """PRA-AC3: none of the name reader's patterns is copied into the surface module."""
    src = Path(surface.__file__).read_text(encoding="utf-8")
    for pattern in ("TICKED", "SKILL_REF", "AGENT_REF", "FILE_REF", "_tool_names"):
        assert pattern not in src, pattern
    assert "`(" not in src


def test_artifact_kinds_imply_a_need() -> None:
    """TSA-B6: a produced `file` implies a write tool, a produced tracker issue implies one that can write it."""
    got = build_surface(wf({"draft": clean_step(tools=["read", "write"], produces={"notes": "file"})}), DECLARED, None,
                        None, executor="claude")
    step = got.sessions[0]
    assert step.needed["Write"] == "artifact notes"
